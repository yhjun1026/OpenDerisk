"""Ingest orchestrator — turn an uploaded file into L0 verbats + L1 wiki docs.

Pipeline (RFC 004 §6):
1. Save uploaded bytes to a temp path (caller-managed) — orchestrator reads from there.
2. Detect MIME.
3. Resolve extractor from the registry.
4. Resolve model: caller override → space config → ModelConfigCache default.
5. extractor.extract(path, mime, model, model_caller) → list[VerbatimSpec]
6. For each spec: vault.verbat_add(Verbat.create(...))
7. For each new verbat: schedule generate_wiki(space, verbat, agent_id, llm_model)

`generate_wiki` uses Option A (v1): a one-shot LLM call to produce markdown,
then `vault.doc_create(...)` with `source_verbat` in frontmatter and an
`edge_add` of `derived-from` (subject=wiki path, object=verbat id).

Idempotency: if a wiki doc with `source_verbat=<id>` already exists, the
rebuild path first invalidates (deletes) the old doc, then regenerates.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from derisk.knowledge.types import (
    DocId,
    Edge,
    ExtractMode,
    Space,
    Verbat,
    VerbatId,
    new_edge_id,
)

from derisk_ext.knowledge.extractors import (
    Extractor,
    ModelCaller,
    VerbatimSpec,
    get_extractor_registry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job payload schemas (exposed via GET /jobs/types so the admin UI can render
# a dynamic form for each knowledge job type).
# ---------------------------------------------------------------------------

try:
    from derisk._private.pydantic import BaseModel, Field  # type: ignore
except Exception:  # pragma: no cover - pydantic always available in derisk
    from pydantic import BaseModel, Field  # type: ignore


class KnowledgeIngestPayload(BaseModel):
    """Payload for the ``knowledge_ingest`` job type."""

    filename: str = Field(..., description="文件名:raw/ 下已落盘的原始文件")
    extract_mode: str = Field("upload", description="抽取模式:upload/rewrite")
    model_override: Optional[str] = Field(None, description="抽取模型覆盖")
    agent_id_override: Optional[str] = Field(None, description="agent id 覆盖")
    llm_model_override: Optional[str] = Field(None, description="wiki 生成 LLM 覆盖")


class KnowledgeRebuildWikiPayload(BaseModel):
    """Payload for the ``knowledge_rebuild_wiki`` job type."""

    llm_model: Optional[str] = Field(None, description="wiki 生成 LLM 覆盖")


# ---------------------------------------------------------------------------
# Job tracking (in-memory; lost on restart, good enough for v1)
# ---------------------------------------------------------------------------


@dataclass
class IngestJob:
    id: str
    space_slug: str
    source_file: str
    verbat_ids: List[VerbatId] = field(default_factory=list)
    wiki_doc_ids: List[DocId] = field(default_factory=list)
    status: str = "pending"  # pending | extracting | embedding | generating_wiki | done | failed
    error: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: Optional[str] = None


class IngestJobStore:
    """In-memory job store, keyed by job_id. Capped at 200 jobs per space."""

    MAX_PER_SPACE = 200

    def __init__(self) -> None:
        self._jobs: Dict[str, IngestJob] = {}

    def add(self, job: IngestJob) -> None:
        self._jobs[job.id] = job
        # Trim
        per_space = [j for j in self._jobs.values() if j.space_slug == job.space_slug]
        if len(per_space) > self.MAX_PER_SPACE:
            per_space.sort(key=lambda j: j.started_at)
            for old in per_space[: len(per_space) - self.MAX_PER_SPACE]:
                self._jobs.pop(old.id, None)

    def get(self, job_id: str) -> Optional[IngestJob]:
        return self._jobs.get(job_id)

    def list_for_space(self, space_slug: str, limit: int = 50) -> List[IngestJob]:
        jobs = [j for j in self._jobs.values() if j.space_slug == space_slug]
        jobs.sort(key=lambda j: j.started_at, reverse=True)
        return jobs[:limit]

    def update(self, job_id: str, **fields) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        for k, v in fields.items():
            setattr(job, k, v)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class IngestOrchestrator:
    """Coordinates file → verbat → wiki generation for one knowledge serve.

    One instance per system_app. Holds the job store and the model caller
    closure so the serve layer can hand it to extractors.
    """

    def __init__(self, system_app: Any):
        self._system_app = system_app
        self.jobs = IngestJobStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_file(
        self,
        space: Space,
        vault: Any,
        file_path: Path,
        original_filename: str,
        extract_mode: ExtractMode = ExtractMode.UPLOAD,
        model_override: Optional[str] = None,
        agent_id_override: Optional[str] = None,
        llm_model_override: Optional[str] = None,
    ) -> IngestJob:
        """Ingest one file end-to-end. Wiki generation runs in the background.

        If a JobService is registered on the system app, the ingest is
        dispatched as a durable ``knowledge_ingest`` job (id ``job_…``,
        survives restart). Otherwise it falls back to an in-memory
        IngestJob (id ``ij_…``) driven by an asyncio task.
        """
        job_svc = self._get_job_service()
        if job_svc is not None:
            payload = {
                "filename": original_filename,
                "extract_mode": extract_mode.value,
                "model_override": model_override,
                "agent_id_override": agent_id_override,
                "llm_model_override": llm_model_override,
            }
            job_id = await job_svc.submit(
                "knowledge_ingest", payload, space_slug=space.slug,
            )
            return IngestJob(
                id=job_id, space_slug=space.slug, source_file=original_filename,
            )

        job = IngestJob(
            id=f"ij_{uuid.uuid4().hex[:12]}",
            space_slug=space.slug,
            source_file=original_filename,
        )
        self.jobs.add(job)

        # Kick off the pipeline in the background so the HTTP upload returns
        # immediately with the job_id. The caller polls /ingest-jobs.
        asyncio.create_task(
            self._run_pipeline(
                job=job,
                space=space,
                vault=vault,
                file_path=file_path,
                original_filename=original_filename,
                extract_mode=extract_mode,
                model_override=model_override,
                agent_id_override=agent_id_override,
                llm_model_override=llm_model_override,
            )
        )
        return job

    def _get_job_service(self) -> Any:
        """Return the JobService component if registered, else None."""
        if self._system_app is None:
            return None
        try:
            from derisk_serve.job.config import (
                SERVE_SERVICE_COMPONENT_NAME as _JOB_SERVICE_COMPONENT_NAME,
            )
            from derisk_serve.job.service.service import (
                Service as _JobService,
            )
        except Exception:
            # Lazy import so knowledge doesn't hard depend on job at load time.
            return None
        try:
            return self._system_app.get_component(
                _JOB_SERVICE_COMPONENT_NAME, _JobService, default_component=None,
            )
        except Exception:
            return None

    async def rebuild_wiki_for_verbat(
        self,
        space: Space,
        vault: Any,
        verbat_id: VerbatId,
        llm_model_override: Optional[str] = None,
    ) -> IngestJob:
        """Regenerate the L1 wiki for one existing verbat."""
        job = IngestJob(
            id=f"ij_{uuid.uuid4().hex[:12]}",
            space_slug=space.slug,
            source_file=f"rebuild:{verbat_id}",
        )
        self.jobs.add(job)
        asyncio.create_task(
            self._run_wiki_only(
                job=job,
                space=space,
                vault=vault,
                verbat_id=verbat_id,
                llm_model_override=llm_model_override,
            )
        )
        return job

    async def rebuild_wiki_for_space(
        self,
        space: Space,
        vault: Any,
        llm_model_override: Optional[str] = None,
    ) -> List[IngestJob]:
        """Regenerate L1 wiki for all (non-deprecated) verbats in a space."""
        verbats = await vault.verbat_list(limit=10000)
        jobs: List[IngestJob] = []
        for v in verbats:
            if v.deprecated:
                continue
            job = await self.rebuild_wiki_for_verbat(
                space, vault, v.id, llm_model_override
            )
            jobs.append(job)
        return jobs

    # ------------------------------------------------------------------
    # Pipeline implementation
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        job: IngestJob,
        space: Space,
        vault: Any,
        file_path: Path,
        original_filename: str,
        extract_mode: ExtractMode,
        model_override: Optional[str],
        agent_id_override: Optional[str],
        llm_model_override: Optional[str],
    ) -> None:
        try:
            # 1. Detect MIME
            mime, _ = mimetypes.guess_type(original_filename)
            if not mime:
                # Fall back to sniffing by extension via the multimodal processor
                mime = self._guess_mime_from_ext(original_filename) or "application/octet-stream"

            # 2. Resolve extractor
            registry = get_extractor_registry()
            extractor = registry.get(mime)
            if extractor is None:
                raise ValueError(
                    f"No extractor registered for mime '{mime}' "
                    f"(file: {original_filename}). Register one via "
                    f"@extractor(name, [mime_patterns])."
                )

            # 3. Resolve model
            model = self._resolve_extract_model(space, mime, model_override)

            # 4. Build model_caller closure
            model_caller = self._make_model_caller(space)

            # 5. Extract
            self.jobs.update(job.id, status="extracting")
            specs: List[VerbatimSpec] = await extractor.extract(
                path=file_path,
                mime=mime,
                model=model,
                model_caller=model_caller,
            )
            if not specs:
                raise RuntimeError(
                    f"Extractor '{extractor.name}' returned no verbats for {original_filename}"
                )

            # 6. Persist verbats
            verbat_ids: List[VerbatId] = []
            for spec in specs:
                # Extractors only see the temp file path and set
                # spec.source_file = path.name (e.g. "ks_upload_<uuid>.md"),
                # which produces ugly wiki slugs. Prefer original_filename
                # unless the extractor set something that isn't the temp
                # file basename (genuine sub-document distinction).
                spec_source = spec.source_file
                if not spec_source or spec_source == file_path.name:
                    spec_source = original_filename
                v = Verbat.create(
                    space_id=vault.space_id,
                    content=spec.content,
                    source_file=spec_source,
                    extract_mode=spec.extract_mode,
                    source_path=str(file_path),
                    content_date=datetime.fromisoformat(spec.content_date)
                    if spec.content_date
                    else None,
                    source_mtime=spec.source_mtime,
                )
                vid = await vault.verbat_add(v)
                # verbat_add dedupes by content_hash and returns existing id
                verbat_ids.append(vid)
            job.verbat_ids = verbat_ids
            self.jobs.update(
                job.id, status="generating_wiki", verbat_ids=verbat_ids
            )

            # 7. Generate wiki for each verbat (sequential to avoid hammering the LLM)
            llm_model = llm_model_override or space.llm_model
            for vid in verbat_ids:
                try:
                    doc_id = await self._generate_wiki(
                        space=space,
                        vault=vault,
                        verbat_id=vid,
                        llm_model=llm_model,
                    )
                    if doc_id:
                        job.wiki_doc_ids.append(doc_id)
                        self.jobs.update(
                            job.id, wiki_doc_ids=list(job.wiki_doc_ids)
                        )
                except Exception as e:
                    logger.exception(
                        "Wiki generation failed for verbat %s in space %s",
                        vid,
                        space.slug,
                    )
                    # Don't fail the whole job — other verbats may succeed

            self.jobs.update(
                job.id, status="done", finished_at=datetime.utcnow().isoformat()
            )

            # 8. Clean up temp file
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass

        except Exception as e:
            logger.exception("Ingest pipeline failed for job %s", job.id)
            self.jobs.update(
                job.id,
                status="failed",
                error=str(e),
                finished_at=datetime.utcnow().isoformat(),
            )

    async def _extract_and_wiki(
        self,
        space: Space,
        vault: Any,
        file_path: Path,
        original_filename: str,
        extract_mode: ExtractMode,
        model_override: Optional[str],
        agent_id_override: Optional[str],
        llm_model_override: Optional[str],
        *,
        on_status: Any = None,
        on_verbat_ids: Any = None,
        on_wiki_doc_id: Any = None,
    ) -> tuple:
        """Core extract → persist → generate-wiki pipeline.

        Shared by ``_run_pipeline`` (in-memory tracking) and the job-engine
        handler (DB-backed). The optional callbacks let each caller record
        progress where it likes. Returns ``(verbat_ids, wiki_doc_ids)``.
        """
        def _noop(*args, **kwargs):
            pass
        on_status = on_status or _noop
        on_verbat_ids = on_verbat_ids or _noop
        on_wiki_doc_id = on_wiki_doc_id or _noop

        # 1. Detect MIME
        mime, _ = mimetypes.guess_type(original_filename)
        if not mime:
            mime = self._guess_mime_from_ext(original_filename) or "application/octet-stream"

        # 2. Resolve extractor
        registry = get_extractor_registry()
        extractor = registry.get(mime)
        if extractor is None:
            raise ValueError(
                f"No extractor registered for mime '{mime}' "
                f"(file: {original_filename}). Register one via "
                f"@extractor(name, [mime_patterns])."
            )

        # 3. Resolve model + 4. model caller
        model = self._resolve_extract_model(space, mime, model_override)
        model_caller = self._make_model_caller(space)

        # 5. Extract
        on_status("extracting")
        specs: List[VerbatimSpec] = await extractor.extract(
            path=file_path, mime=mime, model=model, model_caller=model_caller,
        )
        if not specs:
            raise RuntimeError(
                f"Extractor '{extractor.name}' returned no verbats for {original_filename}"
            )

        # 6. Persist verbats
        verbat_ids: List[VerbatimId] = []
        for spec in specs:
            spec_source = spec.source_file
            if not spec_source or spec_source == file_path.name:
                spec_source = original_filename
            v = Verbat.create(
                space_id=vault.space_id,
                content=spec.content,
                source_file=spec_source,
                extract_mode=spec.extract_mode,
                source_path=str(file_path),
                content_date=datetime.fromisoformat(spec.content_date)
                if spec.content_date
                else None,
                source_mtime=spec.source_mtime,
            )
            vid = await vault.verbat_add(v)
            verbat_ids.append(vid)
        on_status("generating_wiki")
        on_verbat_ids(verbat_ids)

        # 7. Generate wiki for each verbat (sequential to avoid LLM hammering)
        wiki_doc_ids: List[DocId] = []
        llm_model = llm_model_override or space.llm_model
        for vid in verbat_ids:
            try:
                doc_id = await self._generate_wiki(
                    space=space, vault=vault, verbat_id=vid, llm_model=llm_model,
                )
                if doc_id:
                    wiki_doc_ids.append(doc_id)
                    on_wiki_doc_id(doc_id)
            except Exception:
                logger.exception(
                    "Wiki generation failed for verbat %s in space %s",
                    vid, space.slug,
                )
                # Don't fail the whole job — other verbats may succeed

        return verbat_ids, wiki_doc_ids

    async def handle_ingest_job(self, job: Any) -> Optional[Dict[str, Any]]:
        """Job-engine handler for knowledge ingest jobs.

        Dispatched by the persistent JobService. Supports two job types:

        - ``knowledge_ingest``: payload ``{filename, extract_mode?, ...}`` —
          reads the durable raw file (saved by the upload endpoint at
          ``<vault>/raw/<filename>``), extracts verbats, generates wiki.
        - ``knowledge_rebuild_wiki``: payload ``{llm_model?}`` — regenerates
          L1 wiki for all non-deprecated verbats in the space.

        The space slug is read from ``job.space_slug``. Returns a result dict
        consumed by the job engine (``verbat_ids`` / ``wiki_doc_ids`` etc.).
        """
        ksvc = self._get_knowledge_service()
        if ksvc is None:
            raise RuntimeError(
                "KnowledgeService not registered; cannot run ingest job"
            )

        space_slug = getattr(job, "space_slug", None)
        if not space_slug:
            raise ValueError("ingest job missing space_slug")
        space = await ksvc.get_space_config(space_slug)
        vault = await ksvc.get_vault(space_slug)

        job_type = getattr(job, "job_type", "knowledge_ingest")
        if job_type == "knowledge_rebuild_wiki":
            payload = getattr(job, "payload", None) or {}
            jobs = await self.rebuild_wiki_for_space(
                space=space, vault=vault, llm_model_override=payload.get("llm_model"),
            )
            return {"space_slug": space_slug, "rebuild_count": len(jobs)}

        # knowledge_ingest
        payload = getattr(job, "payload", None) or {}
        filename = payload.get("filename")
        if not filename:
            raise ValueError("knowledge_ingest payload missing 'filename'")
        extract_mode = ExtractMode(payload.get("extract_mode", "upload"))

        file_path = vault.root / "raw" / filename
        if not file_path.exists():
            raise FileNotFoundError(
                f"raw file not found for ingest job: {file_path}"
            )

        verbat_ids, wiki_doc_ids = await self._extract_and_wiki(
            space=space,
            vault=vault,
            file_path=file_path,
            original_filename=filename,
            extract_mode=extract_mode,
            model_override=payload.get("model_override"),
            agent_id_override=payload.get("agent_id_override"),
            llm_model_override=payload.get("llm_model_override"),
        )
        return {
            "space_slug": space_slug,
            "verbat_ids": [str(v) for v in verbat_ids],
            "wiki_doc_ids": [str(d) for d in wiki_doc_ids],
        }

    def _get_knowledge_service(self) -> Any:
        """Return the KnowledgeService component if registered, else None."""
        if self._system_app is None:
            return None
        from .config import SERVE_SERVICE_COMPONENT_NAME
        from .service.service import Service as _KnowledgeService
        try:
            return self._system_app.get_component(
                SERVE_SERVICE_COMPONENT_NAME, _KnowledgeService, default_component=None,
            )
        except Exception:
            return None

    def register_job_handlers(self, job_svc: Any) -> None:
        """Register knowledge handlers with the persistent JobService.

        Call after both the knowledge and job serves are initialized (e.g.
        from ``KnowledgeServe.after_init``). Safe to call when no handlers
        are expected — failures are logged, never raised, so a disabled job
        engine never blocks knowledge startup.
        """
        try:
            job_svc.register_handler(
                "knowledge_ingest",
                self.handle_ingest_job,
                description="知识库整理:从 raw/ 文件抽取 verbat 并生成 L1 wiki",
                params_schema=KnowledgeIngestPayload,
            )
            job_svc.register_handler(
                "knowledge_rebuild_wiki",
                self.handle_ingest_job,
                description="知识库整理:重生成空间内全部 L1 wiki",
                params_schema=KnowledgeRebuildWikiPayload,
            )
            logger.info("registered knowledge job handlers with job engine")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("failed to register knowledge job handlers: %s", e)

    async def _run_wiki_only(
        self,
        job: IngestJob,
        space: Space,
        vault: Any,
        verbat_id: VerbatId,
        llm_model_override: Optional[str],
    ) -> None:
        try:
            self.jobs.update(job.id, status="generating_wiki")
            doc_id = await self._generate_wiki(
                space=space,
                vault=vault,
                verbat_id=verbat_id,
                llm_model=llm_model_override or space.llm_model,
                force_rebuild=True,
            )
            if doc_id:
                job.wiki_doc_ids = [doc_id]
                self.jobs.update(job.id, wiki_doc_ids=[doc_id])
            self.jobs.update(
                job.id, status="done", finished_at=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.exception("Wiki rebuild failed for verbat %s", verbat_id)
            self.jobs.update(
                job.id,
                status="failed",
                error=str(e),
                finished_at=datetime.utcnow().isoformat(),
            )

    # ------------------------------------------------------------------
    # Wiki generation (Option A: one-shot LLM call + doc_create + edge_add)
    # ------------------------------------------------------------------

    WIKI_SYSTEM_PROMPT = (
        "你是一个知识库编辑助手。根据用户提供的 L0 原文 verbatim，生成一份 L1 wiki 文档。"
        "要求：\n"
        "1. 输出合法的 markdown，开头是 YAML frontmatter（用 --- 包裹）\n"
        "2. frontmatter 必须包含字段：type (page type)、title、source_verbat (verbatim id)\n"
        "3. type 必须是 schema.md 中已声明的 Page Type 之一\n"
        "4. 正文用 markdown，引用原文具体段落时用 [^N] 脚注\n"
        "5. 不要输出任何解释性文字，只输出 markdown 文档本身"
    )

    async def _generate_wiki(
        self,
        space: Space,
        vault: Any,
        verbat_id: VerbatId,
        llm_model: Optional[str],
        force_rebuild: bool = False,
    ) -> Optional[DocId]:
        """Generate or rebuild the L1 wiki doc for one verbat."""
        verbat = await vault.verbat_get(verbat_id)
        if not verbat:
            raise ValueError(f"Verbat {verbat_id} not found in space {space.slug}")

        # Idempotency: find existing wiki doc with source_verbat=<id>
        existing_path = await self._find_doc_by_source_verbat(vault, verbat_id)
        if existing_path and not force_rebuild:
            logger.info(
                "Wiki doc already exists for verbat %s at %s, skipping",
                verbat_id,
                existing_path,
            )
            return None
        if existing_path and force_rebuild:
            try:
                await vault.doc_delete(existing_path)
            except Exception as e:
                logger.warning("Could not delete old wiki doc %s: %s", existing_path, e)

        # Read schema.md so we can list available page types in the prompt
        schema = await vault._get_schema()
        page_types = ", ".join(schema.page_types.keys()) if schema.page_types else "concept"

        user_prompt = (
            f"verbatim id: {verbat_id}\n"
            f"source file: {verbat.source_file}\n"
            f"extract mode: {verbat.extract_mode.value}\n\n"
            f"可选 Page Types: {page_types}\n\n"
            f"原文内容：\n\n{verbat.content[:12000]}"
        )

        # Call the LLM
        markdown = await self._call_llm(
            model=llm_model,
            system_prompt=self.WIKI_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        if not markdown or not markdown.strip():
            logger.warning("LLM returned empty markdown for verbat %s", verbat_id)
            return None

        # Ensure frontmatter has source_verbat (LLM may forget)
        markdown = self._ensure_frontmatter(markdown, verbat_id, verbat.source_file)

        # Derive a path: wiki/sources/<slug>.md
        slug = self._slugify(verbat.source_file or verbat_id)
        path = f"sources/{slug}.md"

        doc_id = await vault.doc_create(path=path, content=markdown)

        # Add L2 edge: doc → derived-from → verbat
        try:
            await vault.edge_add(
                Edge(
                    id=new_edge_id(),
                    space_id=vault.space_id,
                    subject=f"doc:{doc_id}",
                    predicate="derived-from",
                    object=f"verbat:{verbat_id}",
                    source_document_id=doc_id,
                    source_verbat_id=verbat_id,
                )
            )
        except Exception as e:
            logger.warning("Could not add derived-from edge: %s", e)

        return doc_id

    async def _find_doc_by_source_verbat(
        self, vault: Any, verbat_id: VerbatId
    ) -> Optional[str]:
        """Scan wiki docs' frontmatter for source_verbat=<id>. Returns path or None."""
        try:
            docs = await vault.doc_list(limit=10000)
            for d in docs:
                # doc_list returns DocumentMeta which doesn't carry frontmatter;
                # we need to read each doc. Cheap for small spaces, OK for v1.
                full = await vault.doc_read(d.path)
                if full and full.frontmatter.get("source_verbat") == verbat_id:
                    return d.path
        except Exception as e:
            logger.warning("_find_doc_by_source_verbat failed: %s", e)
        return None

    def _ensure_frontmatter(
        self, markdown: str, verbat_id: VerbatId, source_file: str
    ) -> str:
        """Guarantee the markdown has a frontmatter block with source_verbat set."""
        if not markdown.startswith("---"):
            # Inject a minimal frontmatter
            fm = (
                f"---\n"
                f"type: source\n"
                f"title: {source_file}\n"
                f"source_verbat: {verbat_id}\n"
                f"---\n\n"
            )
            return fm + markdown
        if f"source_verbat:" not in markdown.split("---")[1]:
            # Insert source_verbat into the existing frontmatter
            parts = markdown.split("---", 2)
            if len(parts) >= 3:
                parts[1] = parts[1].rstrip() + f"\nsource_verbat: {verbat_id}\n"
                return "---" + parts[1] + "---" + parts[2]
        return markdown

    @staticmethod
    def _slugify(name: str) -> str:
        import re

        base = re.sub(r"[^a-zA-Z0-9_\-]", "-", name).strip("-").lower()
        return base or "untitled"

    # ------------------------------------------------------------------
    # LLM + model_caller
    # ------------------------------------------------------------------

    def _make_model_caller(self, space: Space) -> ModelCaller:
        """Build a callable for extractors that need an LLM (image/audio)."""

        async def caller(
            model: str,
            prompt: str,
            images: Optional[List[Path]] = None,
        ) -> str:
            # Build a multimodal user message if images are provided
            return await self._call_llm(
                model=model,
                system_prompt=None,
                user_prompt=prompt,
                image_paths=images,
            )

        return caller

    async def _call_llm(
        self,
        model: Optional[str],
        system_prompt: Optional[str],
        user_prompt: str,
        image_paths: Optional[List[Path]] = None,
    ) -> str:
        """Call the LLM via the Agent's ModelConfigCache + AIWrapper.

        Returns the model's text output. Returns "" on failure.
        """
        try:
            from derisk.agent.util.llm.llm_client import AIWrapper
            from derisk.agent.util.llm.model_config_cache import ModelConfigCache
            from derisk.agent.core.llm_config import AgentLLMConfig
        except ImportError as e:
            raise RuntimeError(
                "Agent LLM stack not available; cannot call LLM for wiki generation"
            ) from e

        # Resolve model: explicit → first registered model
        if not model:
            all_models = ModelConfigCache.get_all_models()
            if not all_models:
                raise RuntimeError(
                    "No LLM models registered. Configure agent.llm.provider first."
                )
            model = all_models[0]

        model_config = ModelConfigCache.get_config(model)
        agent_llm_config = None
        if model_config:
            try:
                agent_llm_config = AgentLLMConfig.from_dict(model_config)
            except Exception as e:
                logger.warning("Parse model config for %s failed: %s", model, e)

        ai_wrapper = AIWrapper(llm_config=agent_llm_config)

        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Multimodal: build content array with text + image_url (base64)
        if image_paths:
            content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for img_path in image_paths:
                try:
                    b64 = base64.b64encode(Path(img_path).read_bytes()).decode("ascii")
                    mime = mimetypes.guess_type(str(img_path))[0] or "image/png"
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        }
                    )
                except Exception as e:
                    logger.warning("Could not encode image %s: %s", img_path, e)
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})

        gen_kwargs: Dict[str, Any] = {
            "messages": messages,
            "llm_model": model,
            "stream_out": False,
        }

        result_text = ""
        async for result in ai_wrapper.create(**gen_kwargs):
            if result and result.content:
                result_text += result.content
        return result_text

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_extract_model(
        self,
        space: Space,
        mime: str,
        model_override: Optional[str],
    ) -> Optional[str]:
        """Resolve which model an extractor should use for this file."""
        if model_override:
            return model_override
        # Image/audio → space.multimodal_model
        if mime.startswith(("image/", "audio/", "video/")):
            return space.multimodal_model
        # Plain text → no model needed
        return None

    def _guess_mime_from_ext(self, filename: str) -> Optional[str]:
        """Fallback mime detection when mimetypes.guess_type returns None."""
        ext = os.path.splitext(filename.lower())[1]
        mapping = {
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }
        return mapping.get(ext)


__all__ = ["IngestOrchestrator", "IngestJob", "IngestJobStore"]
