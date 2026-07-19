"""BaseVaultFS — shared orchestration for all VaultFS backends.

Holds the backend-agnostic high-level logic (schema validation, ID
generation, event publishing, lock flow, vector convenience methods)
and declares abstract storage methods that LocalVaultFS /
DistributedVaultFS implement against their respective backends.

The split:
- High-level methods (verbat_add, doc_create, edge_add, …) live here,
  call abstract storage methods.
- Abstract storage methods (_verbat_insert, _doc_fetch_by_path, …) are
  implemented per backend with raw SQL/FS/S3/vector calls.

Both backends thus share orchestration; only the storage seam differs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Callable, Optional

from derisk.knowledge.frontmatter import parse_markdown
from derisk.knowledge.schema import (
    default_schema_md,
    parse_schema,
    validate_predicate,
)
from derisk.knowledge.types import (
    ChangeEvent,
    DocHit,
    DocId,
    Document,
    DocumentMeta,
    Edge,
    EdgeId,
    EmbedderIdentity,
    EmbedderState,
    ExtractMode,
    FtsHit,
    LintIssue,
    ReindexReport,
    SpaceId,
    Subgraph,
    Verbat,
    VerbatHit,
    VerbatId,
    VectorHit,
    WriteLock,
    new_doc_id,
    new_edge_id,
    new_verbat_id,
    sha256_hash,
)
from derisk.knowledge.vaultfs import Subscription, Watcher

from ._util import (
    INLINE_THRESHOLD,
    PROTECTED_FILES,
    chunk_text,
    make_snippet,
    normalize_wiki_path,
    parse_dt,
    serialize_markdown,
    validate_wiki_path,
)

logger = logging.getLogger(__name__)


class EmbedderMismatchError(Exception):
    """Raised when embedder identity doesn't match and force_swap=False."""


class DocDriftError(Exception):
    """Raised when an L1 doc on disk diverged from the vault's last write.

    FS-as-truth: an external writer (user edit, another process) modified
    the markdown under wiki/ without going through the vault, so the
    documents table's content_hash no longer matches the file. The vault
    snapshots the on-disk content to ``<path>.bak.<ts>`` and refuses the
    overwrite/delete instead of silently clobbering the external edit
    (hermes-agent `_detect_external_drift` alignment).
    """

    def __init__(self, path: str, backup_path: str):
        self.path = path
        self.backup_path = backup_path
        super().__init__(
            f"External drift detected on {path}: on-disk content differs "
            f"from the vault's last write. Snapshot saved to {backup_path}; "
            f"refusing to overwrite/delete. Re-read the doc and retry."
        )


# Recall trust score (hermes Holographic fact_feedback alignment).
# trust_score lives in L1 frontmatter; recall multiplies it into the
# ranking score and drops results below TRUST_MIN_RECALL.
TRUST_DEFAULT = 1.0
TRUST_MIN_RECALL = 0.3
TRUST_DELTA_HELPFUL = 0.05
TRUST_DELTA_UNHELPFUL = -0.10


def trust_of(frontmatter: Optional[dict]) -> float:
    """Read trust_score from a doc's frontmatter. Missing/invalid -> 1.0."""
    if not frontmatter:
        return TRUST_DEFAULT
    try:
        return min(1.0, max(0.0, float(frontmatter.get("trust_score", TRUST_DEFAULT))))
    except (TypeError, ValueError):
        return TRUST_DEFAULT


class _BaseSubscription(Subscription):
    def __init__(self, queue: asyncio.Queue, subscribers: set, task: Optional[asyncio.Task] = None):
        self._queue = queue
        self._subscribers = subscribers
        self._task = task

    def cancel(self) -> None:
        self._subscribers.discard(self._queue)
        if self._task is not None:
            self._task.cancel()


class _BaseWriteLock(WriteLock):
    """Generic write lock handle — wraps a backend-specific lock handle
    and releases the in-process asyncio.Lock on release().
    """

    def __init__(self, space_id: SpaceId, backend: str, handle: Any, async_lock: asyncio.Lock, release_fn: Callable[[Any], Any]):
        super().__init__(
            space_id=space_id,
            acquired_at=datetime.utcnow(),
            backend=backend,
            handle=handle,
        )
        self._async_lock = async_lock
        self._release_fn = release_fn
        self._released = False

    async def __aenter__(self) -> "_BaseWriteLock":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        try:
            result = self._release_fn(self.handle)
            if asyncio.iscoroutine(result):
                await result
        finally:
            self._released = True
            if self._async_lock is not None:
                self._async_lock.release()
                self._async_lock = None


class BaseVaultFS(ABC):
    """Shared base for VaultFS backends.

    Subclasses MUST implement all `@abstractmethod` methods. The
    high-level L0/L1/L2 methods here orchestrate by calling those
    abstract methods.
    """

    def __init__(self, space_id: SpaceId):
        self._space_id = space_id
        self._subscribers: set[asyncio.Queue] = set()
        self._async_lock: Optional[asyncio.Lock] = None
        self._vector_store = None  # lazy
        self._schema_cache: Optional[tuple[str, Any]] = None  # (raw_hash, parsed_schema)
        # Embedder provisioning (lazy): service layer calls
        # `configure_embedder_hint(...)` after construction so we can
        # auto-set embedder_identity on first vector op without forcing
        # admins to call set_embedder_identity explicitly.
        self._embedder_model_hint: Optional[str] = None
        self._system_app: Optional[object] = None
        self._embedder_cache: Any = None  # EmbedderCache, lazy
        # L0 verbat embedding (off by default; service layer enables it for
        # spaces with embed_verbats=true). When on, verbat_add /
        # verbat_append_content upsert a `verbat:{id}` vector so
        # verbat_search can run semantic/hybrid modes.
        self._embed_verbats_enabled: bool = False
        # Optional reranker applied after hybrid RRF (per-space, default
        # off). Any object with `async rerank(query, hits) -> hits`.
        self._reranker: Any = None

    def configure_embedder_hint(
        self,
        model_hint: Optional[str],
        system_app: Optional[object] = None,
        embed_verbats: bool = False,
    ) -> None:
        """Service-layer hook: provide the model name to use for lazy
        embedder identity provisioning.

        Called by `Service._make_vault` after constructing the vault.
        The hint is read by `_ensure_embedder_identity` on first vector
        op. If None, vector ops are skipped (FTS still works).

        `embed_verbats` enables L0 verbat embedding on the write path
        (per-space config, default off).
        """
        self._embedder_model_hint = model_hint
        self._embed_verbats_enabled = embed_verbats
        if system_app is not None:
            self._system_app = system_app

    def configure_reranker(self, reranker: Any) -> None:
        """Service-layer hook: mount a reranker for hybrid doc search.

        The reranker is any object with
        `async rerank(query: str, hits: list[DocHit]) -> list[DocHit]`
        (see `derisk_ext.knowledge.reranker`). Called with None to disable.
        """
        self._reranker = reranker

    # ----- metadata -----
    @property
    def space_id(self) -> SpaceId:
        return self._space_id

    @property
    @abstractmethod
    def backend_type(self) -> str: ...

    @property
    @abstractmethod
    def root(self) -> str: ...

    # ----- lifecycle -----
    async def initialize(self) -> None:
        self._async_lock = asyncio.Lock()

    async def close(self) -> None:
        pass

    # ===================================================================
    # Schema (config layer)
    # ===================================================================
    @abstractmethod
    async def read_schema_md(self) -> str: ...

    @abstractmethod
    async def write_schema_md(self, content: str) -> None: ...

    @abstractmethod
    async def read_purpose_md(self) -> str: ...

    async def _get_schema(self):
        """Read and parse schema.md. Cached by raw content hash."""
        raw = await self.read_schema_md()
        if not raw:
            raw = default_schema_md(str(self._space_id))
        cache_hash = sha256_hash(raw)
        if self._schema_cache and self._schema_cache[0] == cache_hash:
            return self._schema_cache[1]
        parsed = parse_schema(raw)
        self._schema_cache = (cache_hash, parsed)
        return parsed

    # ===================================================================
    # L0 Verbatim — high-level orchestration
    # ===================================================================
    async def verbat_add(self, v: Verbat) -> VerbatId:
        assert v.space_id == self._space_id, "verbat belongs to another space"
        async with self.write_lock():
            existing = await self._verbat_exists_by_hash(v.content_hash)
            if existing is not None:
                return existing

            content_ref = None
            inline_content = None
            if len(v.content) <= INLINE_THRESHOLD:
                inline_content = v.content
            else:
                # .md 后缀——verbat 内容是 markdown（对话文本 + [交付]
                # section，含表格/列表）。UI 的 RawEditor 也基于 .md 启用
                # 编辑按钮。 uploads 仍走 raw/sources/ 并保留原始扩展名，
                # 不受这里影响。
                content_ref = f"raw/{v.extract_mode.value}/{v.id}.md"
                await self._raw_write(content_ref, v.content)

            await self._verbat_insert(v, inline_content, content_ref)
            # Optional L0 embedding (per-space embed_verbats). Best-effort:
            # failures are logged but never fail the write.
            await self._embed_verbat_best_effort(v.id, v)

        await self.publish_event(
            ChangeEvent(space_id=self._space_id, layer="L0", op="create", id=v.id)
        )
        return v.id

    async def _embed_verbat_best_effort(
        self, vid: VerbatId, v: Optional[Verbat] = None
    ) -> None:
        """Embed a verbat's content and upsert vector `verbat:{id}`.

        Only runs when the space enabled embed_verbats (see
        `configure_embedder_hint`). Best-effort like
        `_embed_chunks_for_doc`: no embedder / store failure → log + skip.
        The vector ID is stable (`verbat:{verbat_id}`), so re-embedding a
        growing CONVO transcript overwrites in place.
        """
        if not self._embed_verbats_enabled:
            return
        try:
            if v is None:
                v = await self._verbat_fetch(vid)
            if v is None or not v.content or not v.content.strip():
                return
            embedder = await self._ensure_embedder_identity()
            if embedder is None:
                return
            meta = {
                "verbat_id": str(v.id),
                "space_id": str(self._space_id),
                "source_file": v.source_file,
                "extract_mode": v.extract_mode.value,
            }
            # Cap embedded text — verbat content can be arbitrarily large.
            await self.vector_upsert_text(
                f"verbat:{v.id}", v.content[:8000], embedder, meta
            )
        except Exception as e:
            logger.warning(
                "verbat embedding failed for %s on space %s: %s",
                vid, self._space_id, e,
            )

    @abstractmethod
    async def _verbat_exists_by_hash(self, content_hash: str) -> Optional[VerbatId]: ...

    @abstractmethod
    async def _verbat_insert(
        self, v: Verbat, inline_content: Optional[str], content_ref: Optional[str]
    ) -> None: ...

    async def verbat_get(self, vid: VerbatId) -> Optional[Verbat]:
        return await self._verbat_fetch(vid)

    @abstractmethod
    async def _verbat_fetch(self, vid: VerbatId) -> Optional[Verbat]: ...

    async def verbat_list(
        self, extract_mode: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[Verbat]:
        return await self._verbat_list_rows(extract_mode, limit, offset)

    @abstractmethod
    async def _verbat_list_rows(
        self, extract_mode: Optional[str], limit: int, offset: int
    ) -> list[Verbat]: ...

    async def verbat_search(
        self,
        query: str,
        limit: int = 10,
        extract_mode: Optional[str] = None,
        mode: str = "keyword",
    ) -> list[VerbatHit]:
        """Search L0 verbats.

        Modes:
        - "keyword" (default): SQL LIKE on content — always available.
        - "semantic": vector recall over embedded verbats. Requires the
          space's embed_verbats enabled (write-path embedding); returns []
          when no embedder is available.
        - "hybrid": keyword + semantic fused via RRF (k=60).

        Semantic/hybrid degrade to keyword-only when embed_verbats is off.
        """
        # Legacy singular alias: ExtractMode.CONVO's stored value is
        # "convos" (plural, aligned with the raw/convos/ dir).
        if extract_mode == "convo":
            extract_mode = ExtractMode.CONVO.value
        if mode == "keyword" or not self._embed_verbats_enabled:
            return await self._verbat_search_keyword(query, limit, extract_mode)
        if mode == "semantic":
            return await self._verbat_search_semantic(query, limit, extract_mode)
        if mode == "hybrid":
            kw_hits, sem_hits = await asyncio.gather(
                self._verbat_search_keyword(query, limit * 2, extract_mode),
                self._verbat_search_semantic(query, limit * 2, extract_mode),
                return_exceptions=True,
            )
            if isinstance(kw_hits, Exception):
                logger.warning("keyword branch of verbat hybrid failed: %s", kw_hits)
                kw_hits = []
            if isinstance(sem_hits, Exception):
                logger.warning("semantic branch of verbat hybrid failed: %s", sem_hits)
                sem_hits = []
            rrf_k = 60
            scores: dict[str, float] = {}
            meta: dict[str, VerbatHit] = {}
            for rank, h in enumerate(kw_hits):
                scores[h.verbat_id] = scores.get(h.verbat_id, 0.0) + 1.0 / (rrf_k + rank)
                meta.setdefault(h.verbat_id, h)
            for rank, h in enumerate(sem_hits):
                scores[h.verbat_id] = scores.get(h.verbat_id, 0.0) + 1.0 / (rrf_k + rank)
                meta.setdefault(h.verbat_id, h)
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
            return [
                VerbatHit(
                    verbat_id=vid,
                    score=score,
                    snippet=meta[vid].snippet,
                    source_file=meta[vid].source_file,
                    extract_mode=meta[vid].extract_mode,
                )
                for vid, score in ranked
            ]
        raise ValueError(f"Unknown verbat search mode: {mode}")

    async def _verbat_search_keyword(
        self, query: str, limit: int, extract_mode: Optional[str]
    ) -> list[VerbatHit]:
        verbats = await self._verbat_search_rows(query, limit, extract_mode)
        return [
            VerbatHit(
                verbat_id=v.id,
                score=1.0,
                snippet=make_snippet(v.content, query),
                source_file=v.source_file,
                extract_mode=v.extract_mode,
            )
            for v in verbats
        ]

    async def _verbat_search_semantic(
        self, query: str, limit: int, extract_mode: Optional[str]
    ) -> list[VerbatHit]:
        """Vector-only verbat recall. Returns [] when no embedder is
        available. Deprecated verbats are filtered out post-recall."""
        embedder = await self._ensure_embedder_identity()
        if embedder is None:
            logger.info(
                "verbat semantic search skipped on space %s — no embedder configured",
                self._space_id,
            )
            return []
        hits = await self.vector_query_text(query, embedder, top_k=limit * 3)
        result: list[VerbatHit] = []
        for h in hits:
            vid = (h.metadata or {}).get("verbat_id") if h.metadata else None
            if not vid:
                continue  # doc-chunk vector, not a verbat
            if extract_mode and h.metadata.get("extract_mode") != extract_mode:
                continue
            v = await self._verbat_fetch(str(vid))
            if v is None or v.deprecated:
                continue
            result.append(
                VerbatHit(
                    verbat_id=v.id,
                    score=float(h.score),
                    snippet=make_snippet(v.content, query),
                    source_file=v.source_file,
                    extract_mode=v.extract_mode,
                )
            )
            if len(result) >= limit:
                break
        return result

    @abstractmethod
    async def _verbat_search_rows(
        self, query: str, limit: int, extract_mode: Optional[str]
    ) -> list[Verbat]: ...

    async def verbat_deprecate(self, vid: VerbatId) -> None:
        async with self.write_lock():
            await self._verbat_deprecate_row(vid)
            # Best-effort vector cleanup when L0 embedding is enabled.
            if self._embed_verbats_enabled:
                try:
                    await self.vector_delete(f"verbat:{vid}")
                except Exception as e:
                    logger.debug("vector_delete failed for verbat:%s: %s", vid, e)
        await self.publish_event(
            ChangeEvent(space_id=self._space_id, layer="L0", op="delete", id=vid)
        )

    @abstractmethod
    async def _verbat_deprecate_row(self, vid: VerbatId) -> None: ...

    async def verbat_find_by_session(
        self, conv_session_id: str
    ) -> Optional[Verbat]:
        """Find the most recent non-deprecated CONVO verbat for a session.

        Used by tier1 memory writes to co-locate all turns of a session in
        one verbat (one file on disk). Returns None if no session verbat
        exists yet.
        """
        return await self._verbat_find_by_session(conv_session_id)

    @abstractmethod
    async def _verbat_find_by_session(
        self, conv_session_id: str
    ) -> Optional[Verbat]: ...

    async def verbat_append_content(
        self, vid: VerbatId, additional: str
    ) -> None:
        """Append content to an existing verbat (CONVO session transcripts).

        Relaxes the L0 immutability rule for CONVO mode only: a session
        transcript grows turn-by-turn. Updates both the file on disk and
        the DB row (content + content_hash). No-op if vid not found or
        deprecated.
        """
        async with self.write_lock():
            await self._verbat_append_content(vid, additional)
            # Refresh the verbat vector (stable ID overwrites in place).
            await self._embed_verbat_best_effort(vid)
        await self.publish_event(
            ChangeEvent(space_id=self._space_id, layer="L0", op="update", id=vid)
        )

    @abstractmethod
    async def _verbat_append_content(
        self, vid: VerbatId, additional: str
    ) -> None: ...

    # ===================================================================
    # L1 Document — high-level orchestration
    # ===================================================================
    async def doc_create(
        self, path: str, content: str, frontmatter: Optional[dict] = None
    ) -> DocId:
        norm_path = normalize_wiki_path(path)
        validate_wiki_path(norm_path)

        parsed = parse_markdown(content)
        fm = frontmatter if frontmatter is not None else parsed.frontmatter
        body = parsed.content

        page_type = fm.get("type", "concept")
        schema = await self._get_schema()
        if page_type not in schema.page_types:
            raise ValueError(
                f"page type '{page_type}' not declared in schema.md Page Types"
            )

        raw_md = serialize_markdown(fm, body)
        doc_id = new_doc_id()
        now = datetime.utcnow()

        async with self.write_lock():
            await self._wiki_write(norm_path, raw_md)
            await self._doc_insert(
                doc_id=doc_id,
                norm_path=norm_path,
                page_type=fm.get("type", "concept"),
                title=fm.get("title", norm_path),
                raw_frontmatter=parsed.raw_frontmatter,
                content_hash=sha256_hash(raw_md),
                now=now,
            )
            await self._chunks_replace_for_doc(doc_id, body)
            await self._doc_invalidate_edges(doc_id, now.isoformat())
            await self._rebuild_doc_edges(doc_id, fm, body)
            # Embed L1 chunks for semantic + hybrid search. Best-effort:
            # failures are logged but do not fail the doc write — FTS
            # still works.
            await self._embed_chunks_for_doc(doc_id, norm_path, body)

        await self.publish_event(
            ChangeEvent(
                space_id=self._space_id, layer="L1", op="create", id=doc_id, path=norm_path
            )
        )
        return doc_id

    async def check_doc_drift(self, path: str) -> None:
        """Round-trip guard for overwrite/delete ops on L1 docs.

        Re-reads the file from disk and compares its content hash with
        the content_hash the vault recorded at its last write. A mismatch
        means an external writer modified the file (FS-as-truth) — the
        on-disk content is snapshotted to ``<path>.bak.<ts>`` and
        DocDriftError is raised instead of silently clobbering it.

        Normal vault writes keep file and DB hash in sync, so the
        read-then-write LLM path never trips this guard. No-op when the
        doc or file is missing (nothing to lose).
        """
        norm_path = normalize_wiki_path(path)
        meta = await self._doc_fetch_meta_by_path(norm_path)
        if not meta:
            return
        doc_id, _version = meta
        row = await self._doc_fetch_row(doc_id)
        if not row:
            return
        expected_hash = row.get("content_hash")
        disk_raw = await self._wiki_read(norm_path)
        if not expected_hash or not disk_raw:
            return
        if sha256_hash(disk_raw) == expected_hash:
            return
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = f"{norm_path}.bak.{ts}"
        await self._wiki_write(backup_path, disk_raw)
        logger.warning(
            "External drift on %s (space %s) — snapshot at %s, refusing write",
            norm_path, self._space_id, backup_path,
        )
        raise DocDriftError(norm_path, backup_path)

    async def doc_edit(self, path: str, content: str) -> None:
        norm_path = normalize_wiki_path(path)
        validate_wiki_path(norm_path)

        parsed = parse_markdown(content)
        fm = parsed.frontmatter
        body = parsed.content
        raw_md = serialize_markdown(fm, body)
        now = datetime.utcnow()

        async with self.write_lock():
            await self.check_doc_drift(norm_path)
            await self._wiki_write(norm_path, raw_md)
            existing = await self._doc_fetch_meta_by_path(norm_path)
            if existing:
                doc_id, _version = existing
                await self._doc_update_version(
                    doc_id=doc_id,
                    page_type=fm.get("type", "concept"),
                    title=fm.get("title", norm_path),
                    raw_frontmatter=parsed.raw_frontmatter,
                    content_hash=sha256_hash(raw_md),
                    now=now,
                )
            else:
                doc_id = new_doc_id()
                await self._doc_insert(
                    doc_id=doc_id,
                    norm_path=norm_path,
                    page_type=fm.get("type", "concept"),
                    title=fm.get("title", norm_path),
                    raw_frontmatter=parsed.raw_frontmatter,
                    content_hash=sha256_hash(raw_md),
                    now=now,
                )

            await self._chunks_replace_for_doc(doc_id, body)
            await self._doc_invalidate_edges(doc_id, now.isoformat())
            await self._rebuild_doc_edges(doc_id, fm, body)
            # Re-embed chunks (stable IDs keep unchanged chunks' vectors).
            await self._embed_chunks_for_doc(doc_id, norm_path, body)

        await self.publish_event(
            ChangeEvent(
                space_id=self._space_id, layer="L1", op="update", id=doc_id, path=norm_path
            )
        )

    async def doc_read(self, path: str) -> Optional[Document]:
        norm_path = normalize_wiki_path(path)
        meta = await self._doc_fetch_meta_by_path(norm_path)
        if not meta:
            return None
        doc_id, _version = meta
        raw_md = await self._wiki_read(norm_path)
        parsed = parse_markdown(raw_md)
        row = await self._doc_fetch_row(doc_id)
        if not row:
            return None
        return Document(
            id=doc_id,
            space_id=self._space_id,
            path=norm_path,
            type=row["type"],
            title=row["title"],
            frontmatter=parsed.frontmatter,
            content=parsed.content,
            raw_content=raw_md,
            content_hash=row["content_hash"],
            version=row["version"],
            status=row["status"],
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )

    async def doc_feedback(self, path: str, helpful: bool) -> dict:
        """Adjust a doc's trust_score from recall-quality feedback.

        hermes Holographic fact_feedback alignment: helpful +0.05 /
        unhelpful -0.10, clamped to [0, 1]. The new score is written back
        into the frontmatter via doc_edit, so the drift guard applies —
        if the file was externally modified since the vault's last write,
        DocDriftError is raised and the feedback is refused.

        Returns {"path", "trust_score", "previous_trust"}.
        """
        doc = await self.doc_read(path)
        if doc is None:
            raise FileNotFoundError(f"doc not found: {normalize_wiki_path(path)}")
        old = trust_of(doc.frontmatter)
        delta = TRUST_DELTA_HELPFUL if helpful else TRUST_DELTA_UNHELPFUL
        new = min(1.0, max(0.0, old + delta))
        fm = dict(doc.frontmatter)
        fm["trust_score"] = new
        await self.doc_edit(doc.path, serialize_markdown(fm, doc.content))
        logger.info(
            "doc_feedback %s (space %s): trust %.2f -> %.2f",
            doc.path, self._space_id, old, new,
        )
        return {"path": doc.path, "trust_score": new, "previous_trust": old}

    async def doc_delete(self, path: str) -> None:
        norm_path = normalize_wiki_path(path)
        if norm_path.split("/")[-1] in PROTECTED_FILES:
            raise PermissionError(f"Refusing to delete protected file: {norm_path}")

        async with self.write_lock():
            meta = await self._doc_fetch_meta_by_path(norm_path)
            if not meta:
                return
            await self.check_doc_drift(norm_path)
            doc_id, _version = meta
            # Fetch chunk hashes before the row is gone so we can clean
            # the corresponding vectors.
            chunk_hashes = await self._doc_list_chunk_hashes(doc_id)
            await self._wiki_delete(norm_path)
            now_iso = datetime.utcnow().isoformat()
            await self._doc_invalidate_edges(doc_id, now_iso)
            await self._doc_delete_row(doc_id)
            # Best-effort vector cleanup.
            await self._delete_doc_vectors(doc_id, chunk_hashes)

        await self.publish_event(
            ChangeEvent(
                space_id=self._space_id, layer="L1", op="delete", id=doc_id, path=norm_path
            )
        )

    async def _delete_doc_vectors(
        self, doc_id: DocId, chunk_hashes: list[str]
    ) -> None:
        """Delete all chunk vectors for a doc. Best-effort — swallows
        errors (vector store may be uninitialized, in which case there
        is nothing to delete).
        """
        if not chunk_hashes:
            return
        try:
            for chunk_hash in chunk_hashes:
                vector_id = f"doc:{doc_id}:chunk:{chunk_hash}"
                try:
                    await self.vector_delete(vector_id)
                except Exception as e:
                    logger.debug(
                        "vector_delete failed for %s: %s", vector_id, e
                    )
        except Exception as e:
            logger.warning(
                "Failed to clean vectors for doc %s: %s", doc_id, e
            )

    async def doc_list(
        self, type: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[DocumentMeta]:
        return await self._doc_list_rows(type, limit, offset)

    async def doc_search(
        self, query: str, mode: str = "documents", limit: int = 10,
        include_invalid: bool = False,
    ) -> list[DocHit]:
        if mode == "documents":
            return await self._doc_search_documents(query, limit)
        elif mode == "references":
            return await self._doc_search_references(query, limit)
        elif mode == "semantic":
            return await self._doc_search_semantic(query, limit)
        elif mode == "hybrid":
            return await self._doc_search_hybrid(query, limit)
        elif mode == "graph":
            return await self._doc_search_graph(query, limit, include_invalid)
        raise ValueError(f"Unknown search mode: {mode}")

    # Predicates followed for graph expansion (RFC-005 Phase 3).
    _GRAPH_EXPANSION_PREDICATES = ("about", "relates-to")
    # Graph-expansion neighbors are downweighted vs direct hybrid hits.
    _GRAPH_EXPANSION_SCORE_FACTOR = 0.5

    async def _doc_search_graph(
        self, query: str, limit: int, include_invalid: bool = False
    ) -> list[DocHit]:
        """Graph-expanded search (RFC-005 Phase 3).

        1. Hybrid (FTS + vector RRF) top-K seeds.
        2. For each seed, follow active `about`/`relates-to` edges to the
           entity page, then the entity page's edges to OTHER source docs
           — those are graph-expansion neighbors, marked
           ``source="graph_expansion"`` and downweighted.
        3. Temporal policy (skipped when ``include_invalid=True``): docs
           that are the object of an active `supersedes` edge are dropped
           (only-latest-version on chains); expansion follows active edges
           only, so expired `about` edges never pull their doc in.
        4. Final ordering: stable sort by `confidence` frontmatter desc
           (missing = 1.0, so personal-space order is preserved).
        """
        seeds = await self._doc_search_hybrid(query, limit)

        # Docs superseded by a newer version (object of an active
        # supersedes edge) — filtered unless include_invalid.
        superseded_ids: set[str] = set()
        if not include_invalid:
            sup = await self.graph_query(
                entity=None, predicate="supersedes", include_invalid=False
            )
            superseded_ids = {
                e.object[len("doc:"):]
                for e in sup.edges
                if (e.object or "").startswith("doc:")
            }
        if superseded_ids:
            seeds = [s for s in seeds if s.document_id not in superseded_ids]

        seed_ids = {s.document_id for s in seeds}
        # id -> meta map for neighbor hydration (doc_list carries path,
        # unlike _doc_fetch_row).
        metas = {d.id: d for d in await self.doc_list(limit=10000)}
        neighbors: dict[str, DocHit] = {}
        for seed in seeds:
            if len(neighbors) >= limit:
                break
            seed_node = f"doc:{seed.document_id}"
            try:
                hop1 = await self.graph_query(
                    entity=seed_node, include_invalid=include_invalid
                )
            except Exception as e:
                logger.warning("graph expansion hop1 failed for %s: %s", seed_node, e)
                continue
            entity_nodes: set[str] = set()
            for e in hop1.edges:
                if e.predicate not in self._GRAPH_EXPANSION_PREDICATES:
                    continue
                other = e.object if e.subject == seed_node else e.subject
                if other.startswith("doc:") and other != seed_node:
                    entity_nodes.add(other)
            for ent_node in entity_nodes:
                if len(neighbors) >= limit:
                    break
                try:
                    hop2 = await self.graph_query(
                        entity=ent_node, include_invalid=include_invalid
                    )
                except Exception as e:
                    logger.warning("graph expansion hop2 failed for %s: %s", ent_node, e)
                    continue
                for e in hop2.edges:
                    if e.predicate not in self._GRAPH_EXPANSION_PREDICATES:
                        continue
                    other = e.object if e.subject == ent_node else e.subject
                    if not other.startswith("doc:") or other == ent_node:
                        continue
                    nid = other[len("doc:"):]
                    if nid in seed_ids or nid in neighbors or nid in superseded_ids:
                        continue
                    if nid == seed.document_id:
                        continue
                    meta = metas.get(nid)
                    if meta is None or meta.status != "active":
                        continue
                    neighbors[nid] = DocHit(
                        document_id=nid,
                        path=meta.path,
                        title=meta.title,
                        type=meta.type,
                        score=seed.score * self._GRAPH_EXPANSION_SCORE_FACTOR,
                        snippet="",
                        verbats=[],
                        source="graph_expansion",
                    )
                    if len(neighbors) >= limit:
                        break

        hits = list(seeds) + list(neighbors.values())

        # Agent-memory ordering: confidence frontmatter desc (default 1.0).
        # Stable sort preserves score order when all confidences are equal.
        conf: dict[str, float] = {}
        for h in hits:
            try:
                doc = await self.doc_read(h.path)
                raw = (doc.frontmatter or {}).get("confidence", 1.0) if doc else 1.0
                conf[h.document_id] = float(raw)
            except (TypeError, ValueError):
                conf[h.document_id] = 1.0
            except Exception:
                conf[h.document_id] = 1.0
        hits.sort(
            key=lambda h: conf.get(h.document_id, 1.0), reverse=True
        )
        return hits

    async def _doc_search_documents(self, query: str, limit: int) -> list[DocHit]:
        fts_hits = await self._fts_search_chunks(query, limit)
        result: list[DocHit] = []
        for h in fts_hits:
            verbats = await self._lookup_doc_verbats(h.document_id)
            result.append(
                DocHit(
                    document_id=h.document_id,
                    path=h.path,
                    title=h.title,
                    type="",  # filled by backend if available; not critical
                    score=h.score,
                    snippet=h.snippet,
                    verbats=verbats,
                )
            )
        return result

    async def _doc_search_semantic(
        self, query: str, limit: int
    ) -> list[DocHit]:
        """Vector-only semantic search. Returns docs ranked by cosine
        similarity to `query`. If embedder is unavailable, returns [].
        """
        embedder = await self._ensure_embedder_identity()
        if embedder is None:
            logger.info(
                "semantic search skipped on space %s — no embedder configured",
                self._space_id,
            )
            return []
        hits = await self.vector_query_text(query, embedder, top_k=limit * 2)
        # Dedupe by document_id — multiple chunks may match the same doc.
        by_doc: dict[str, VectorHit] = {}
        for h in hits:
            doc_id = (h.metadata or {}).get("document_id") if h.metadata else None
            if not doc_id:
                continue
            doc_id = str(doc_id)
            if doc_id not in by_doc or h.score > by_doc[doc_id].score:
                by_doc[doc_id] = h
        result: list[DocHit] = []
        for doc_id, vh in by_doc.items():
            row = await self._doc_fetch_row(doc_id)
            if not row:
                continue
            verbats = await self._lookup_doc_verbats(doc_id)
            result.append(
                DocHit(
                    document_id=doc_id,
                    path=row.get("path", ""),
                    title=row.get("title", ""),
                    type=row.get("type", ""),
                    score=float(vh.score),
                    snippet="",  # vector store doesn't keep chunk text
                    verbats=verbats,
                )
            )
            if len(result) >= limit:
                break
        return result

    async def _doc_search_hybrid(
        self, query: str, limit: int
    ) -> list[DocHit]:
        """Hybrid search: FTS + vector recall fused via reciprocal rank
        fusion (RRF, k=60). Falls back to FTS-only when embedder is
        unavailable.
        """
        fts_task = asyncio.create_task(self._doc_search_documents(query, limit * 2))
        sem_task = asyncio.create_task(self._doc_search_semantic(query, limit * 2))
        fts_hits, sem_hits = await asyncio.gather(
            fts_task, sem_task, return_exceptions=True
        )
        if isinstance(fts_hits, Exception):
            logger.warning("FTS branch of hybrid failed: %s", fts_hits)
            fts_hits = []
        if isinstance(sem_hits, Exception):
            logger.warning("Semantic branch of hybrid failed: %s", sem_hits)
            sem_hits = []

        # RRF: score(d) = sum(1 / (k + rank)) for each recall channel.
        rrf_k = 60
        scores: dict[str, float] = {}
        meta: dict[str, DocHit] = {}

        for rank, h in enumerate(fts_hits):
            scores[h.document_id] = scores.get(h.document_id, 0.0) + 1.0 / (rrf_k + rank)
            meta.setdefault(h.document_id, h)
        for rank, h in enumerate(sem_hits):
            scores[h.document_id] = scores.get(h.document_id, 0.0) + 1.0 / (rrf_k + rank)
            if h.document_id in meta:
                # Prefer FTS hit for the snippet; keep the higher score.
                continue
            meta[h.document_id] = h

        ranked = sorted(
            scores.items(), key=lambda kv: kv[1], reverse=True
        )[: limit * 2 if self._reranker is not None else limit]
        hits = [
            DocHit(
                document_id=doc_id,
                path=meta[doc_id].path,
                title=meta[doc_id].title,
                type=meta[doc_id].type,
                score=score,
                snippet=meta[doc_id].snippet,
                verbats=meta[doc_id].verbats,
            )
            for doc_id, score in ranked
        ]
        # Optional rerank stage (per-space rerank_model, default off).
        # Reorders the top candidates; failures fall back to RRF order.
        if self._reranker is not None and hits:
            try:
                hits = await self._reranker.rerank(query, hits)
            except Exception as e:
                logger.warning(
                    "rerank failed on space %s (keeping RRF order): %s",
                    self._space_id, e,
                )
        return hits[:limit]

    @abstractmethod
    async def _doc_search_references(self, query: str, limit: int) -> list[DocHit]: ...

    async def doc_lint(self, path: Optional[str] = None) -> list[LintIssue]:
        """Structural lint over L1 docs / L0 verbats / L2 edges.

        Implements the rules declared in schema.md `## Lint Rules`
        (RFC 003 §3.6). Rule toggles are read from the parsed schema;
        `path` narrows the doc set to a single page when given.

        Backend-agnostic: uses only public VaultFS methods (doc_list /
        doc_read / verbat_list / graph_query), so Local and Distributed
        share this implementation. Note: graph_query pages at the
        backend's edge cap (500), so very large spaces may lint against a
        truncated edge set.

        Rule name → schema toggle:
        - orphan_doc          → orphan_pages
        - broken_wikilink     → dangling_links
        - verbat_without_wiki → uncited_sources
        - stale_edge          → stale_edges
        - frontmatter_missing → frontmatter_required
        - contradiction       → contradiction_detection (structural proxy:
          an active `contradicts` edge coexisting with another active
          predicate between the same entity pair; semantic contradiction
          detection needs an LLM and is out of scope for lint)
        """
        from derisk.knowledge.frontmatter import extract_wikilinks

        schema = await self._get_schema()
        rules = schema.lint_rules
        issues: list[LintIssue] = []

        docs = await self.doc_list(limit=10000)
        if path:
            norm = normalize_wiki_path(path)
            docs = [d for d in docs if d.path == norm]

        # Load the active edge set once (backend pages at its own cap).
        subgraph = await self.graph_query(
            entity=None, predicate=None, include_invalid=False
        )
        edges = subgraph.edges

        # 1. orphan_pages: docs with no incoming edge pointing at doc:{id}
        if rules.orphan_pages:
            inbound_doc_objects = {
                e.object for e in edges if (e.object or "").startswith("doc:")
            }
            for d in docs:
                if f"doc:{d.id}" not in inbound_doc_objects:
                    issues.append(
                        LintIssue(
                            rule="orphan_doc",
                            severity="info",
                            path=d.path,
                            message=f"文档 {d.path} 没有入边（孤岛文档）",
                        )
                    )

        # 2. dangling_links: [[X]] wikilinks whose target page doesn't exist
        if rules.dangling_links:
            doc_paths = {d.path for d in docs}
            for d in docs:
                full = await self.doc_read(d.path)
                if not full:
                    continue
                for link in extract_wikilinks(full.content):
                    target = link.split("|")[0].strip().lstrip("/")
                    target_path = target if target.endswith(".md") else f"{target}.md"
                    exists = any(
                        p == target_path or p.endswith(target) for p in doc_paths
                    )
                    if not exists:
                        issues.append(
                            LintIssue(
                                rule="broken_wikilink",
                                severity="warning",
                                path=d.path,
                                message=(
                                    f"文档 {d.path} 中的 wikilink [[{link}]] "
                                    f"指向不存在的页面"
                                ),
                            )
                        )

        # 3. uncited_sources: non-deprecated verbats with no derived-from edge
        if rules.uncited_sources:
            cited_verbat_ids = {
                e.source_verbat_id for e in edges if e.source_verbat_id
            }
            verbats = await self.verbat_list(limit=10000)
            for v in verbats:
                if v.deprecated:
                    continue
                if v.id not in cited_verbat_ids:
                    issues.append(
                        LintIssue(
                            rule="verbat_without_wiki",
                            severity="info",
                            verbat_id=v.id,
                            message=(
                                f"原文 {v.source_file} ({v.id}) 还没有派生的 wiki 文档"
                            ),
                        )
                    )
        else:
            verbats = None

        # 4. stale_edges: active edges whose source doc/verbat is gone
        if rules.stale_edges:
            active_doc_ids = {d.id for d in docs if d.status == "active"}
            if verbats is None:
                verbats = await self.verbat_list(limit=10000)
            live_verbat_ids = {v.id for v in verbats if not v.deprecated}
            for e in edges:
                if e.source_document_id and e.source_document_id not in active_doc_ids:
                    issues.append(
                        LintIssue(
                            rule="stale_edge",
                            severity="warning",
                            edge_id=e.id,
                            message=(
                                f"边 {e.id} ({e.subject} -[{e.predicate}]-> {e.object}) "
                                f"的源文档 {e.source_document_id} 已不存在或已下线"
                            ),
                        )
                    )
                elif e.source_verbat_id and e.source_verbat_id not in live_verbat_ids:
                    issues.append(
                        LintIssue(
                            rule="stale_edge",
                            severity="warning",
                            edge_id=e.id,
                            verbat_id=e.source_verbat_id,
                            message=(
                                f"边 {e.id} ({e.subject} -[{e.predicate}]-> {e.object}) "
                                f"的源原文 {e.source_verbat_id} 已不存在或已废弃"
                            ),
                        )
                    )

        # 5. frontmatter_required: docs missing required frontmatter fields
        if rules.frontmatter_required:
            required = list(rules.frontmatter_required)
            for d in docs:
                full = await self.doc_read(d.path)
                if not full:
                    continue
                missing = [f for f in required if f not in full.frontmatter]
                if missing:
                    issues.append(
                        LintIssue(
                            rule="frontmatter_missing",
                            severity="info",
                            path=d.path,
                            message=(
                                f"文档 {d.path} 缺少 frontmatter 字段: "
                                f"{', '.join(missing)}"
                            ),
                        )
                    )

        # 6. contradiction_detection (structural proxy): an active
        # `contradicts` edge between a pair that also has another active
        # predicate — the pair asserts and contradicts at once.
        if rules.contradiction_detection:
            pair_predicates: dict[frozenset, set] = {}
            for e in edges:
                pair = frozenset((e.subject, e.object))
                pair_predicates.setdefault(pair, set()).add(e.predicate)
            seen_pairs: set[frozenset] = set()
            for e in edges:
                if e.predicate != "contradicts":
                    continue
                pair = frozenset((e.subject, e.object))
                if pair in seen_pairs:
                    continue
                others = pair_predicates.get(pair, set()) - {"contradicts"}
                if others:
                    seen_pairs.add(pair)
                    issues.append(
                        LintIssue(
                            rule="contradiction",
                            severity="warning",
                            edge_id=e.id,
                            message=(
                                f"实体对 ({e.subject}, {e.object}) 同时存在 "
                                f"'contradicts' 与 {sorted(others)} 关系，可能矛盾"
                            ),
                        )
                    )

        return issues

    async def doc_append_log(self, entry: str) -> None:
        existing = await self._wiki_read("log.md")
        if not existing:
            existing = "# Operation Log\n\n"
        await self._wiki_write("log.md", existing + entry + "\n")

    async def read_wiki_file(self, path: str) -> str:
        """Read raw wiki file content by path. Returns "" if missing.

        Public access for tests and tooling that need to verify raw file
        contents (e.g., log.md) without going through the document
        metadata layer.
        """
        return await self._wiki_read(normalize_wiki_path(path))

    # ----- L1 abstract storage methods -----
    @abstractmethod
    async def _doc_insert(
        self,
        doc_id: DocId,
        norm_path: str,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None: ...

    @abstractmethod
    async def _doc_fetch_meta_by_path(self, norm_path: str) -> Optional[tuple[DocId, int]]:
        """Return (doc_id, version) or None."""

    @abstractmethod
    async def _doc_fetch_row(self, doc_id: DocId) -> Optional[dict]:
        """Return dict with keys: type, title, content_hash, version, status,
        created_at, updated_at. Or None."""

    @abstractmethod
    async def _doc_update_version(
        self,
        doc_id: DocId,
        page_type: str,
        title: str,
        raw_frontmatter: str,
        content_hash: str,
        now: datetime,
    ) -> None: ...

    @abstractmethod
    async def _doc_delete_row(self, doc_id: DocId) -> None: ...

    @abstractmethod
    async def _doc_list_rows(
        self, type: Optional[str], limit: int, offset: int
    ) -> list[DocumentMeta]: ...

    @abstractmethod
    async def _doc_invalidate_edges(self, doc_id: DocId, now_iso: str) -> None: ...

    @abstractmethod
    async def _chunks_replace_for_doc(self, doc_id: DocId, body: str) -> None: ...

    @abstractmethod
    async def _doc_list_chunk_hashes(self, doc_id: DocId) -> list[str]: ...

    @abstractmethod
    async def _fts_search_chunks(self, query: str, limit: int) -> list[FtsHit]: ...

    @abstractmethod
    async def _lookup_doc_verbats(self, doc_id: DocId) -> list[VerbatId]: ...

    # ----- File I/O (abstract) -----
    @abstractmethod
    async def _raw_write(self, rel_path: str, content: str) -> None: ...

    @abstractmethod
    async def _raw_read(self, rel_path: str) -> str: ...

    @abstractmethod
    async def _raw_delete(self, rel_path: str) -> None: ...

    @abstractmethod
    async def _wiki_write(self, norm_path: str, content: str) -> None: ...

    @abstractmethod
    async def _wiki_read(self, norm_path: str) -> str: ...

    @abstractmethod
    async def _wiki_delete(self, norm_path: str) -> None: ...

    # ===================================================================
    # L2 Graph — high-level orchestration
    # ===================================================================
    async def edge_add(self, e: Edge) -> EdgeId:
        if not e.id:
            e.id = new_edge_id()
        if e.created_at is None:
            e.created_at = datetime.utcnow()
        if e.valid_from is None:
            e.valid_from = datetime.utcnow()

        schema = await self._get_schema()
        if not validate_predicate(schema, e.predicate):
            raise ValueError(
                f"predicate '{e.predicate}' not declared in schema.md Relation Types"
            )

        async with self.write_lock():
            await self._edge_insert(e)

        await self.publish_event(
            ChangeEvent(space_id=self._space_id, layer="L2", op="create", id=e.id)
        )
        return e.id

    @abstractmethod
    async def _edge_insert(self, e: Edge) -> None: ...

    async def edge_invalidate(
        self, eid: EdgeId, valid_to: Optional[datetime] = None
    ) -> None:
        vt = (valid_to or datetime.utcnow()).isoformat()
        async with self.write_lock():
            await self._edge_invalidate_row(eid, vt)
        await self.publish_event(
            ChangeEvent(space_id=self._space_id, layer="L2", op="invalidate", id=eid)
        )

    @abstractmethod
    async def _edge_invalidate_row(self, eid: EdgeId, valid_to_iso: str) -> None: ...

    async def graph_query(
        self,
        entity: Optional[str] = None,
        predicate: Optional[str] = None,
        hop: int = 1,
        include_invalid: bool = False,
    ) -> Subgraph:
        edges = await self._edges_query(entity, predicate, include_invalid)
        nodes: set[str] = set()
        for e in edges:
            nodes.add(e.subject)
            nodes.add(e.object)
        return Subgraph(nodes=sorted(nodes), edges=edges, root=entity)

    @abstractmethod
    async def _edges_query(
        self,
        entity: Optional[str],
        predicate: Optional[str],
        include_invalid: bool,
    ) -> list[Edge]: ...

    async def graph_traverse(self, entity: str, hop: int = 2, mode: str = "bfs") -> Subgraph:
        if mode != "bfs":
            raise NotImplementedError("Only BFS supported in MVP")

        visited: set[str] = set()
        edges: list[Edge] = []
        frontier: list[str] = [entity]
        for _ in range(hop):
            next_frontier: list[str] = []
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                node_edges = await self._edges_for_node(node)
                for e in node_edges:
                    if e not in edges:
                        edges.append(e)
                    neighbor = e.object if e.subject == node else e.subject
                    if neighbor not in visited:
                        next_frontier.append(neighbor)
            frontier = next_frontier

        all_nodes = sorted({entity} | {e.subject for e in edges} | {e.object for e in edges})
        return Subgraph(nodes=all_nodes, edges=edges, root=entity)

    @abstractmethod
    async def _edges_for_node(self, node: str) -> list[Edge]: ...

    async def graph_timeline(self, entity: str) -> list[Edge]:
        return await self._edges_timeline(entity)

    @abstractmethod
    async def _edges_timeline(self, entity: str) -> list[Edge]: ...

    async def graph_backlinks(self, entity: str) -> list[Edge]:
        return await self._edges_backlinks(entity)

    @abstractmethod
    async def _edges_backlinks(self, entity: str) -> list[Edge]: ...

    @abstractmethod
    async def _rebuild_doc_edges(
        self, doc_id: DocId, frontmatter: dict, body: str
    ) -> None: ...

    # ===================================================================
    # Cross-cutting: vector (lazy)
    # ===================================================================
    async def vector_upsert(self, id: str, embedding: list[float], meta: dict) -> None:
        store = await self._get_vector_store()
        await store.upsert(id, embedding, meta)

    async def vector_query(
        self, embedding: list[float], top_k: int = 10, filter: Optional[dict] = None
    ) -> list[VectorHit]:
        store = await self._get_vector_store()
        return await store.query(embedding, top_k, filter)

    async def vector_delete(self, id: str) -> None:
        store = await self._get_vector_store()
        await store.delete(id)

    async def vector_upsert_text(
        self, id: str, text: str, embedder: Any, meta: Optional[dict] = None
    ) -> list[float]:
        """Embed `text` with `embedder` and upsert the vector.

        Convenience for the ingest pipeline: callers pass an `Embeddings`
        instance (from `embedder_factory.get_embedder`) instead of a
        pre-computed vector. Returns the embedding so callers can persist
        dimension info if needed.
        """
        if hasattr(embedder, "aembed_query"):
            embedding = await embedder.aembed_query(text)
        else:
            embedding = await asyncio.to_thread(embedder.embed_query, text)
        await self.vector_upsert(id, embedding, meta or {})
        return embedding

    async def vector_query_text(
        self,
        query: str,
        embedder: Any,
        top_k: int = 10,
        filter: Optional[dict] = None,
    ) -> list[VectorHit]:
        """Embed `query` and run vector search. Symmetric to
        `vector_upsert_text` for the read path.
        """
        if hasattr(embedder, "aembed_query"):
            embedding = await embedder.aembed_query(query)
        else:
            embedding = await asyncio.to_thread(embedder.embed_query, query)
        return await self.vector_query(embedding, top_k, filter)

    async def _get_vector_store(self):
        if self._vector_store is None:
            self._vector_store = await self._make_vector_store()
        return self._vector_store

    async def _ensure_embedder_identity(self) -> Any:
        """Lazily provision an embedder for this space.

        - If `embedder_identity` is already set and state is KNOWN_MATCH,
          return a cached `Embeddings` instance for the stored model.
        - If unset: read `self._embedder_model_hint` (set by the service
          layer from `space.embedder_model` or
          `ServeConfig.default_embedder_model`). If the hint is empty,
          return None (caller skips vector ops — FTS still works).
        - If a hint is available: probe the embedder for its dimension by
          embedding a single short string once, then call
          `set_embedder_identity(model_name, dimension)` to lock it.
          Subsequent calls hit the first branch.

        On EmbedderMismatchError or init failure: log a warning and
        return None. Vector ops are best-effort; ingest must not fail
        the whole doc write when the embedder is unavailable.
        """
        try:
            existing = await self.get_embedder_identity()
        except Exception as e:
            logger.warning("get_embedder_identity failed: %s", e)
            return None

        if existing is not None:
            if existing.state == EmbedderState.KNOWN_MISMATCH:
                logger.warning(
                    "Embedder mismatch on space %s — call "
                    "set_embedder_identity(force_swap=True) to rebuild vectors",
                    self._space_id,
                )
                return None
            if existing.state != EmbedderState.KNOWN_MATCH:
                return None
            return self._build_embedder(existing.model_name)

        # No identity yet — try to provision from the hint.
        hint = self._embedder_model_hint
        if not hint:
            return None

        embedder = self._build_embedder(hint)
        if embedder is None:
            return None

        # Probe dimension with a single short embedding.
        try:
            if hasattr(embedder, "aembed_query"):
                probe = await embedder.aembed_query("dimension probe")
            else:
                probe = await asyncio.to_thread(embedder.embed_query, "dimension probe")
            dim = len(probe)
        except Exception as e:
            logger.warning(
                "Embedder probe failed for model %s on space %s: %s",
                hint, self._space_id, e,
            )
            return None

        try:
            await self.set_embedder_identity(model_name=hint, dimension=dim)
        except Exception as e:
            # set_embedder_identity raises EmbedderMismatchError if a
            # concurrent caller set a different identity. Treat as
            # best-effort — re-read and use the stored identity.
            logger.warning(
                "set_embedder_identity failed for space %s: %s", self._space_id, e
            )
            return None

        return embedder

    def _build_embedder(self, model_name: str) -> Any:
        """Build or fetch a cached `Embeddings` for `model_name`."""
        if not model_name:
            return None
        if self._embedder_cache is None:
            try:
                from derisk_ext.knowledge.embedder_factory import EmbedderCache
                self._embedder_cache = EmbedderCache(self._system_app)
            except ImportError as e:
                logger.warning(
                    "embedder_factory unavailable; vector ops disabled: %s", e
                )
                return None
        try:
            return self._embedder_cache.get(model_name)
        except Exception as e:
            logger.warning(
                "Failed to build embedder for model %s: %s", model_name, e
            )
            return None

    async def _embed_chunks_for_doc(
        self, doc_id: DocId, norm_path: str, body: str
    ) -> None:
        """Embed every chunk of `body` and upsert into the vector store.

        Best-effort: any failure (no embedder, vector store unreachable,
        embedder API error) is logged and returned silently. The caller
        (`doc_create` / `doc_edit`) continues — FTS still indexes the
        chunks via `_chunks_replace_for_doc`.

        Vector IDs are `doc:{doc_id}:chunk:{chunk_hash}` — stable across
        re-chunking for unchanged chunks (idempotent upserts).
        """
        if not body or not body.strip():
            return
        embedder = await self._ensure_embedder_identity()
        if embedder is None:
            return  # vector ops disabled — FTS still works

        chunks = chunk_text(body, max_chars=2000)
        for idx, chunk_text_body, chunk_hash in chunks:
            vector_id = f"doc:{doc_id}:chunk:{chunk_hash}"
            meta = {
                "document_id": str(doc_id),
                "path": norm_path,
                "chunk_index": idx,
                "space_id": str(self._space_id),
            }
            try:
                await self.vector_upsert_text(vector_id, chunk_text_body, embedder, meta)
            except Exception as e:
                logger.warning(
                    "vector_upsert_text failed for %s (chunk %d of doc %s): %s",
                    vector_id, idx, doc_id, e,
                )
                return  # stop embedding this doc; likely systemic error

    @abstractmethod
    async def _make_vector_store(self):
        """Construct the backend-appropriate VectorStore.

        Called lazily on first vector op. Implementations should read
        embedder_identity to determine dimension, then build the store.
        """

    # ===================================================================
    # Cross-cutting: full-text
    # ===================================================================
    async def fts_search(
        self, query: str, limit: int = 10, filter: Optional[dict] = None
    ) -> list[FtsHit]:
        return await self._fts_search_chunks(query, limit)

    # ===================================================================
    # Cross-cutting: writer lock
    # ===================================================================
    async def acquire_write_lock(self, timeout: int = 30) -> _BaseWriteLock:
        if self._async_lock is None:
            raise RuntimeError("VaultFS not initialized — call initialize() first")
        try:
            await asyncio.wait_for(self._async_lock.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Could not acquire in-process lock for space {self._space_id} within {timeout}s"
            )

        try:
            handle = await self._acquire_distributed_lock(timeout)
        except Exception:
            self._async_lock.release()
            raise

        return _BaseWriteLock(
            space_id=self._space_id,
            backend=self.backend_type,
            handle=handle,
            async_lock=self._async_lock,
            release_fn=self._release_distributed_lock,
        )

    @asynccontextmanager
    async def write_lock(self, timeout: int = 30):
        lock = await self.acquire_write_lock(timeout=timeout)
        try:
            yield lock
        finally:
            await lock.release()

    @abstractmethod
    async def _acquire_distributed_lock(self, timeout: int) -> Any:
        """Acquire a cross-process lock. Return an opaque handle.

        For LocalVaultFS: opened fd (flock). For DistributedVaultFS:
        Postgres advisory lock key or MySQL GET_LOCK name.
        """

    @abstractmethod
    async def _release_distributed_lock(self, handle: Any) -> None: ...

    # ===================================================================
    # Cross-cutting: events (in-process; both backends for v1)
    # ===================================================================
    async def publish_event(self, event: ChangeEvent) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"Event queue full, dropping event {event}")

    async def subscribe_events(
        self, callback: Callable[[ChangeEvent], None]
    ) -> _BaseSubscription:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)

        async def _pump():
            try:
                while True:
                    event = await queue.get()
                    try:
                        result = callback(event)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception("Event subscriber raised")
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(_pump())
        return _BaseSubscription(queue, self._subscribers, task)

    # ===================================================================
    # Cross-cutting: filesystem watcher
    # ===================================================================
    async def watch_changes(
        self, callback: Callable[[ChangeEvent], None]
    ) -> Watcher:
        """Default: no-op watcher. Backends with FS access (LocalVaultFS) override."""

        class _NoopWatcher(Watcher):
            def stop(self) -> None:
                pass

        return _NoopWatcher()

    # ===================================================================
    # Rebuild
    # ===================================================================
    async def reindex(self, layer: str = "all") -> ReindexReport:
        start = time.time()
        report = ReindexReport(layer=layer)

        async with self.write_lock(timeout=300):
            if layer in ("chunks", "all"):
                await self._reindex_chunks(report)
            if layer in ("L2", "all"):
                await self._reindex_l2(report)
            if layer in ("vectors", "all"):
                await self._reindex_vectors(report)

        report.duration_seconds = time.time() - start
        return report

    async def _reindex_chunks(self, report: ReindexReport) -> None:
        await self._chunks_clear_all()
        docs = await self.doc_list(limit=10000)
        for meta in docs:
            doc = await self.doc_read(meta.path)
            if doc:
                await self._chunks_replace_for_doc(doc.id, doc.content)
                report.chunks_built += 1
        report.documents_processed = len(docs)

    async def _reindex_vectors(self, report: ReindexReport) -> None:
        """Clear all vectors for this space and re-embed every doc's chunks.

        Best-effort — if no embedder is configured, the report records 0
        vectors and returns silently. FTS reindex (`_reindex_chunks`)
        runs independently and is unaffected.
        """
        # Clear existing vectors so stale entries don't linger.
        try:
            store = await self._get_vector_store()
            await store.clear()
            # Drop reference so a fresh store is built (in case dimension
            # changed after a force_swap).
            self._vector_store = None
        except Exception as e:
            report.errors.append(f"vector clear failed: {e}")
            return  # no point embedding if we can't even open the store

        docs = await self.doc_list(limit=10000)
        for meta in docs:
            doc = await self.doc_read(meta.path)
            if not doc or not doc.content or not doc.content.strip():
                continue
            try:
                await self._embed_chunks_for_doc(doc.id, doc.path, doc.content)
                report.vectors_rebuilt += 1
            except Exception as e:
                report.errors.append(
                    f"vector embed failed for doc {doc.id}: {e}"
                )

    async def _reindex_l2(self, report: ReindexReport) -> None:
        now_iso = datetime.utcnow().isoformat()
        await self._edges_invalidate_all(now_iso)
        docs = await self.doc_list(limit=10000)
        for meta in docs:
            doc = await self.doc_read(meta.path)
            if doc and doc.status == "active":
                await self._rebuild_doc_edges(doc.id, doc.frontmatter, doc.content)
                report.edges_built += 1

    @abstractmethod
    async def _chunks_clear_all(self) -> None: ...

    @abstractmethod
    async def _edges_invalidate_all(self, now_iso: str) -> None: ...

    # ===================================================================
    # Embedder identity
    # ===================================================================
    async def get_embedder_identity(self) -> Optional[EmbedderIdentity]:
        return await self._embedder_identity_get()

    @abstractmethod
    async def _embedder_identity_get(self) -> Optional[EmbedderIdentity]: ...

    async def set_embedder_identity(
        self, model_name: str, dimension: int, force_swap: bool = False
    ) -> None:
        existing = await self.get_embedder_identity()
        now = datetime.utcnow()

        if existing is None:
            await self._embedder_identity_upsert(
                model_name=model_name,
                dimension=dimension,
                state=EmbedderState.KNOWN_MATCH,
                now=now,
            )
            return

        if existing.model_name == model_name and existing.dimension == dimension:
            return

        if not force_swap:
            await self._embedder_identity_update_state(EmbedderState.KNOWN_MISMATCH, now)
            raise EmbedderMismatchError(
                f"Embedder identity mismatch: stored={existing.model_name}/"
                f"{existing.dimension}, requested={model_name}/{dimension}. "
                f"Call with force_swap=True to rebuild vectors."
            )

        await self._embedder_identity_upsert(
            model_name=model_name,
            dimension=dimension,
            state=EmbedderState.KNOWN_MATCH,
            now=now,
        )
        if self._vector_store is not None:
            await self._vector_store.clear()
            self._vector_store = None  # force re-create with new dim

    @abstractmethod
    async def _embedder_identity_upsert(
        self, model_name: str, dimension: int, state: EmbedderState, now: datetime
    ) -> None: ...

    @abstractmethod
    async def _embedder_identity_update_state(
        self, state: EmbedderState, now: datetime
    ) -> None: ...
