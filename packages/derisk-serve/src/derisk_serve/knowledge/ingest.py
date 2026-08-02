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

Job tracking: in-flight state lives in the in-memory IngestJobStore; every
transition is also persisted to the space's `ingest_jobs` ledger (local
backend, `.ks/index.db`) so history survives restarts. `list_jobs` merges
both (memory wins for in-flight rows).
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import logging
import mimetypes
import os
import time
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
# Job tracking (in-memory for in-flight state; mirrored to the space's
# `ingest_jobs` SQLite ledger on every transition so history survives
# restarts — see IngestOrchestrator._persist_job / list_jobs)
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
        # RFC-005 Phase 2 switch: cross-document entity curation after wiki
        # generation (default on for personal / agent_memory spaces).
        self.entity_curation_enabled: bool = True

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
            # The durable copy lives at <vault>/raw/<filename> (the job
            # handler reads from there); the caller's file_path is a temp
            # copy — unlink it after submit so temp files don't leak.
            # Never unlink the durable raw itself (raw_file_create passes
            # the raw path directly).
            try:
                durable = vault.root / "raw" / original_filename
                if Path(file_path).resolve() != durable.resolve():
                    Path(file_path).unlink(missing_ok=True)
            except OSError:
                pass
            return IngestJob(
                id=job_id, space_slug=space.slug, source_file=original_filename,
            )

        job = IngestJob(
            id=f"ij_{uuid.uuid4().hex[:12]}",
            space_slug=space.slug,
            source_file=original_filename,
        )
        self.jobs.add(job)
        await self._persist_job(vault, job.id)

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

    # ------------------------------------------------------------------
    # Job ledger persistence
    # ------------------------------------------------------------------

    async def _persist_job(self, vault: Any, job_id: str) -> None:
        """Mirror the in-memory job row to the space's job ledger.

        Only local vaults carry a ledger (`.ks/index.db`); other backends
        skip via getattr — same pattern as the llm_call_log ledger.
        """
        save = getattr(vault, "ingest_job_save", None) if vault is not None else None
        if save is None:
            return
        job = self.jobs.get(job_id)
        if job is None:
            return
        try:
            await save(dataclasses.asdict(job))
        except Exception as e:
            logger.warning("ingest job persist failed for %s: %s", job_id, e)

    async def _job_update(self, vault: Any, job_id: str, **fields) -> None:
        """Update in-memory job state and persist the transition."""
        self.jobs.update(job_id, **fields)
        await self._persist_job(vault, job_id)

    async def list_jobs(
        self, space_slug: str, vault: Any = None, limit: int = 50
    ) -> List[IngestJob]:
        """List jobs for a space, merging the in-memory store with the
        persisted ledger (newest first). In-memory rows win for in-flight
        jobs; persisted rows keep history queryable after a restart.
        """
        merged: Dict[str, IngestJob] = {}
        list_fn = getattr(vault, "ingest_job_list", None) if vault is not None else None
        if list_fn is not None:
            try:
                for row in await list_fn(limit=limit):
                    merged[row["id"]] = IngestJob(**row)
            except Exception as e:
                logger.warning(
                    "ingest job ledger read failed for %s: %s", space_slug, e
                )
        for j in self.jobs.list_for_space(space_slug, limit=limit):
            merged[j.id] = j
        jobs = sorted(merged.values(), key=lambda j: j.started_at, reverse=True)
        return jobs[:limit]

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
        await self._persist_job(vault, job.id)
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
            model_caller = self._make_model_caller(space, vault=vault, job_id=job.id)

            # 5. Extract
            await self._job_update(vault, job.id, status="extracting")
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
            await self._job_update(
                vault, job.id, status="generating_wiki", verbat_ids=verbat_ids
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
                        job_id=job.id,
                    )
                    if doc_id:
                        job.wiki_doc_ids.append(doc_id)
                        await self._job_update(
                            vault, job.id, wiki_doc_ids=list(job.wiki_doc_ids)
                        )
                except Exception as e:
                    logger.exception(
                        "Wiki generation failed for verbat %s in space %s",
                        vid,
                        space.slug,
                    )
                    # Don't fail the whole job — other verbats may succeed

            # 7b. RFC-005 Phase 2: cross-document entity curation over the
            # freshly generated wiki docs (sequential, same LLM-hammering
            # rationale as the wiki loop above).
            await self._curate_entities_for_docs(
                space, vault, job.wiki_doc_ids, llm_model, job_id=job.id
            )

            await self._job_update(
                vault, job.id, status="done", finished_at=datetime.utcnow().isoformat()
            )

            # 8. Clean up temp file
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass

        except Exception as e:
            logger.exception("Ingest pipeline failed for job %s", job.id)
            await self._job_update(
                vault,
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
        job_id: Optional[str] = None,
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
        model_caller = self._make_model_caller(space, vault=vault, job_id=job_id)

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
                    job_id=job_id,
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

        # 7b. RFC-005 Phase 2: cross-document entity curation.
        await self._curate_entities_for_docs(
            space, vault, wiki_doc_ids, llm_model, job_id=job_id
        )

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
            job_id=getattr(job, "id", None),
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
            await self._job_update(vault, job.id, status="generating_wiki")
            doc_id = await self._generate_wiki(
                space=space,
                vault=vault,
                verbat_id=verbat_id,
                llm_model=llm_model_override or space.llm_model,
                force_rebuild=True,
                job_id=job.id,
            )
            if doc_id:
                job.wiki_doc_ids = [doc_id]
                await self._job_update(vault, job.id, wiki_doc_ids=[doc_id])
            await self._job_update(
                vault, job.id, status="done", finished_at=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.exception("Wiki rebuild failed for verbat %s", verbat_id)
            await self._job_update(
                vault,
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

    # RFC-005 Phase 2: cross-document entity curation. Runs after wiki
    # generation for personal / agent_memory spaces. Tests route LLM stubs
    # on the "实体归并" marker in this system prompt — keep it.
    ENTITY_CURATE_PROMPT = (
        "你是一个知识库实体归并助手。输入一篇刚生成的 wiki 文档和知识空间内现有的"
        "实体页索引，完成跨文档实体归并。要求：\n"
        "1. 只抽取文档中的关键实体（3-8 个：人/组织/产品/模型/关键概念），控制成本\n"
        "2. 对照现有实体页索引，为每个实体判断 action：\n"
        "   - new：索引中没有对应实体页 → 给 new_body（完整 markdown，含 YAML "
        "frontmatter：type: entity、title、description）\n"
        "   - merge：已有实体页且本文档是补充（不矛盾）→ 给 existing_path + "
        "merged_body（frontmatter 取并集、正文合并两份来源后的完整 markdown）\n"
        "   - supersede：已有实体页但本文档与之矛盾 → 给 existing_path + new_body"
        "（新版完整 markdown）+ reason（矛盾点）\n"
        "3. 只输出严格 JSON，不要输出任何解释性文字：\n"
        '{"entities": [{"name": "...", "action": "new|merge|supersede", '
        '"existing_path": "entities/xxx.md", "new_body": "...", '
        '"merged_body": "...", "summary": "...", "reason": "..."}]}\n'
        '4. 没有值得归并的实体时输出 {"entities": []}'
    )

    async def _generate_wiki(
        self,
        space: Space,
        vault: Any,
        verbat_id: VerbatId,
        llm_model: Optional[str],
        force_rebuild: bool = False,
        job_id: Optional[str] = None,
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
            vault=vault,
            job_id=job_id,
            task_name="wiki_generate",
        )
        if not markdown or not markdown.strip():
            logger.warning("LLM returned empty markdown for verbat %s", verbat_id)
            return None

        # Ensure frontmatter has source_verbat (LLM may forget)
        markdown = self._ensure_frontmatter(
            markdown, verbat_id, verbat.source_file,
            provenance=(
                "agent" if getattr(space, "space_type", "personal") == "agent_memory"
                else "human"
            ),
        )

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
        self, markdown: str, verbat_id: VerbatId, source_file: str,
        provenance: Optional[str] = None,
    ) -> str:
        """Guarantee the markdown has a frontmatter block with source_verbat set.

        RFC-005 Phase 1: also stamps the provenance convention key
        ("human" for personal spaces, "agent" for agent_memory spaces)
        when the LLM didn't write one.
        """
        if not markdown.startswith("---"):
            # Inject a minimal frontmatter
            fm = (
                f"---\n"
                f"type: source\n"
                f"title: {source_file}\n"
                f"source_verbat: {verbat_id}\n"
                + (f"provenance: {provenance}\n" if provenance else "")
                + f"---\n\n"
            )
            return fm + markdown
        parts = markdown.split("---", 2)
        if len(parts) >= 3:
            fm_block = parts[1]
            if f"source_verbat:" not in fm_block:
                fm_block = fm_block.rstrip() + f"\nsource_verbat: {verbat_id}\n"
            if provenance and "provenance:" not in fm_block:
                fm_block = fm_block.rstrip() + f"\nprovenance: {provenance}\n"
            return "---" + fm_block + "---" + parts[2]
        return markdown

    @staticmethod
    def _slugify(name: str) -> str:
        import re

        base = re.sub(r"[^a-zA-Z0-9_\-]", "-", name).strip("-").lower()
        return base or "untitled"

    @staticmethod
    def _slugify_unicode(name: str) -> str:
        """Slug that keeps CJK characters (entity names are often Chinese)."""
        import re

        base = re.sub(r"[^\w\-]+", "-", name).strip("-").lower()
        return base or "untitled"

    # ------------------------------------------------------------------
    # Entity curation (RFC-005 Phase 2)
    # ------------------------------------------------------------------

    async def _curate_entities_for_docs(
        self,
        space: Space,
        vault: Any,
        doc_ids: List[DocId],
        llm_model: Optional[str],
        job_id: Optional[str] = None,
    ) -> None:
        """Run entity curation over freshly generated wiki docs.

        Gated on the orchestrator switch + dual-form space type. Failures
        are logged, never raised — curation must not fail the ingest job.
        """
        if not self.entity_curation_enabled:
            return
        if getattr(space, "space_type", "personal") not in ("personal", "agent_memory"):
            return
        for doc_id in doc_ids or []:
            try:
                await self._curate_entities(
                    space, vault, doc_id, llm_model, job_id=job_id
                )
            except Exception:
                logger.exception(
                    "Entity curation failed for doc %s in space %s",
                    doc_id, space.slug,
                )

    async def _curate_entities(
        self,
        space: Space,
        vault: Any,
        doc_id: DocId,
        llm_model: Optional[str],
        job_id: Optional[str] = None,
    ) -> None:
        """LLM-assisted entity merge for one wiki doc (llm_wiki-style).

        1. Read the wiki doc + the space's existing entity page index.
        2. LLM (ENTITY_CURATE_PROMPT) returns strict JSON with per-entity
           action: new | merge | supersede.
        3. Dispatch: doc_create / doc_edit + about edges; supersede also
           adds a supersedes edge and invalidates the old page's edges.
        """
        import json as _json

        # 1. Resolve the wiki doc (doc_id -> path -> Document)
        docs = await vault.doc_list(limit=10000)
        meta = next((d for d in docs if d.id == doc_id), None)
        if meta is None:
            return
        doc = await vault.doc_read(meta.path)
        if doc is None:
            return

        # 2. Existing entity page index (title + one-line description)
        index_lines: List[str] = []
        ent_metas = await vault.doc_list(type="entity", limit=50)
        for em in ent_metas:
            try:
                full = await vault.doc_read(em.path)
                desc = ""
                if full is not None:
                    desc = str(full.frontmatter.get("description") or "")
                index_lines.append(f"- {em.path} | {em.title} | {desc}")
            except Exception:
                index_lines.append(f"- {em.path} | {em.title} |")
        entity_index = (
            "\n".join(index_lines) if index_lines else "(空 — 尚无任何实体页)"
        )

        user_prompt = (
            f"现有实体页索引（path | title | description）：\n{entity_index}\n\n"
            f"刚生成的 wiki 文档（path: {doc.path}）：\n\n{doc.raw_content[:12000]}"
        )
        resp = await self._call_llm(
            model=llm_model,
            system_prompt=self.ENTITY_CURATE_PROMPT,
            user_prompt=user_prompt,
            vault=vault,
            job_id=job_id,
            task_name="entity_curate",
        )
        entities = self._parse_curation_json(resp)
        if not entities:
            return

        for ent in entities[:8]:  # hard cap, matches the prompt's 3-8 limit
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "").strip()
            action = str(ent.get("action") or "").strip().lower()
            if not name:
                continue
            try:
                if action == "merge":
                    await self._curate_merge(vault, ent, doc_id)
                elif action == "supersede":
                    await self._curate_supersede(vault, ent, name, doc_id)
                else:  # default: new
                    await self._curate_new(vault, ent, name, doc_id)
            except Exception:
                logger.exception(
                    "Entity curation action=%s failed for '%s' in space %s",
                    action, name, space.slug,
                )

    @staticmethod
    def _parse_curation_json(resp: str) -> List[dict]:
        """Parse the LLM's strict-JSON curation response (tolerant of
        markdown fences and surrounding prose)."""
        import json as _json

        if not resp:
            return []
        text = resp.strip()
        if text.startswith("```"):
            # strip ```json ... ``` fence
            text = text.split("\n", 1)[-1] if "\n" in text else text
            if text.endswith("```"):
                text = text[: text.rfind("```")]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = _json.loads(text[start : end + 1])
        except Exception as e:
            logger.warning("entity curation JSON parse failed: %s", e)
            return []
        entities = data.get("entities") if isinstance(data, dict) else None
        return entities if isinstance(entities, list) else []

    @staticmethod
    def _ensure_entity_frontmatter(markdown: str, name: str) -> str:
        """Guarantee an entity page has frontmatter with type: entity."""
        if markdown.startswith("---"):
            parts = markdown.split("---", 2)
            if len(parts) >= 3:
                fm_block = parts[1]
                if "type:" not in fm_block:
                    fm_block = fm_block.rstrip() + "\ntype: entity\n"
                if "title:" not in fm_block:
                    fm_block = fm_block.rstrip() + f"\ntitle: {name}\n"
                return "---" + fm_block + "---" + parts[2]
            return markdown
        return f"---\ntype: entity\ntitle: {name}\n---\n\n" + markdown

    async def _entity_doc_id_by_path(self, vault: Any, path: str) -> Optional[DocId]:
        docs = await vault.doc_list(type="entity", limit=10000)
        meta = next((d for d in docs if d.path == path), None)
        return meta.id if meta else None

    async def _add_about_edge(
        self, vault: Any, entity_doc_id: DocId, source_doc_id: DocId
    ) -> None:
        """Anchor an entity page to a source doc via an `about` edge.

        source_document_id is deliberately NULL: doc_edit on either
        endpoint invalidates edges sourced from that doc, and entity pages
        are edited on every merge — the about chain is managed explicitly
        by curation (supersede invalidates old edges) instead.
        """
        try:
            await vault.edge_add(
                Edge(
                    id=new_edge_id(),
                    space_id=vault.space_id,
                    subject=f"doc:{entity_doc_id}",
                    predicate="about",
                    object=f"doc:{source_doc_id}",
                )
            )
        except Exception as e:
            logger.warning("about edge add failed (%s -> %s): %s",
                           entity_doc_id, source_doc_id, e)

    async def _free_entity_path(self, vault: Any, base_slug: str) -> str:
        """Pick a collision-free entities/<slug>.md path."""
        path = f"entities/{base_slug}.md"
        if await self._entity_doc_id_by_path(vault, path) is None:
            return path
        for i in range(2, 100):
            candidate = f"entities/{base_slug}-{i}.md"
            if await self._entity_doc_id_by_path(vault, candidate) is None:
                return candidate
        return f"entities/{base_slug}-{uuid.uuid4().hex[:6]}.md"

    async def _curate_new(
        self, vault: Any, ent: dict, name: str, source_doc_id: DocId
    ) -> None:
        body = str(ent.get("new_body") or "").strip()
        if not body:
            body = f"# {name}\n\n{ent.get('summary') or ''}\n"
        body = self._ensure_entity_frontmatter(body, name)
        path = await self._free_entity_path(vault, self._slugify_unicode(name))
        entity_doc_id = await vault.doc_create(path=path, content=body)
        await self._add_about_edge(vault, entity_doc_id, source_doc_id)

    async def _curate_merge(
        self, vault: Any, ent: dict, source_doc_id: DocId
    ) -> None:
        existing_path = str(ent.get("existing_path") or "").strip()
        merged = str(ent.get("merged_body") or "").strip()
        if not existing_path or not merged:
            logger.warning(
                "merge action missing existing_path/merged_body: %s", ent
            )
            return
        # doc_edit's drift guard is safe here: the entity page was written
        # through the vault, so file hash and DB hash are in sync.
        await vault.doc_edit(path=existing_path, content=merged)
        entity_doc_id = await self._entity_doc_id_by_path(vault, existing_path)
        if entity_doc_id:
            await self._add_about_edge(vault, entity_doc_id, source_doc_id)

    async def _curate_supersede(
        self, vault: Any, ent: dict, name: str, source_doc_id: DocId
    ) -> None:
        existing_path = str(ent.get("existing_path") or "").strip()
        new_body = str(ent.get("new_body") or "").strip()
        if not existing_path or not new_body:
            logger.warning(
                "supersede action missing existing_path/new_body: %s", ent
            )
            return
        old_doc_id = await self._entity_doc_id_by_path(vault, existing_path)

        # New version lives at entities/<slug>-v2.md (next free -vN).
        base = existing_path.rsplit("/", 1)[-1]
        base_slug = base[:-3] if base.endswith(".md") else base
        new_path = None
        for i in range(2, 100):
            candidate = f"entities/{base_slug}-v{i}.md"
            if await self._entity_doc_id_by_path(vault, candidate) is None:
                new_path = candidate
                break
        if new_path is None:
            new_path = f"entities/{base_slug}-v{uuid.uuid4().hex[:6]}.md"

        new_doc_id = await vault.doc_create(
            path=new_path, content=self._ensure_entity_frontmatter(new_body, name)
        )
        if old_doc_id:
            # Invalidate the old version's active edges FIRST (kept in
            # history via valid_to, not deleted) — doing this before adding
            # the supersedes edge so the fresh edge isn't swept up.
            try:
                old_edges = await vault.graph_query(
                    entity=f"doc:{old_doc_id}", include_invalid=False
                )
                for e in old_edges.edges:
                    await vault.edge_invalidate(e.id)
            except Exception as e:
                logger.warning("invalidating old entity edges failed: %s", e)
            # supersedes edge: new -> old (source_document_id NULL — must
            # survive doc_edit on either endpoint; see _add_about_edge)
            try:
                await vault.edge_add(
                    Edge(
                        id=new_edge_id(),
                        space_id=vault.space_id,
                        subject=f"doc:{new_doc_id}",
                        predicate="supersedes",
                        object=f"doc:{old_doc_id}",
                    )
                )
            except Exception as e:
                logger.warning("supersedes edge add failed: %s", e)
        await self._add_about_edge(vault, new_doc_id, source_doc_id)

    # ------------------------------------------------------------------
    # LLM + model_caller
    # ------------------------------------------------------------------

    def _make_model_caller(
        self,
        space: Space,
        vault: Any = None,
        job_id: Optional[str] = None,
    ) -> ModelCaller:
        """Build a callable for extractors that need an LLM (image/audio)."""

        async def caller(
            model: str,
            prompt: str,
            images: Optional[List[Path]] = None,
            videos: Optional[List[Path]] = None,
        ) -> str:
            # Build a multimodal user message if images/videos are provided
            return await self._call_llm(
                model=model,
                system_prompt=None,
                user_prompt=prompt,
                image_paths=images,
                video_paths=videos,
                vault=vault,
                job_id=job_id,
                task_name="extract",
            )

        return caller

    async def _call_llm(
        self,
        model: Optional[str],
        system_prompt: Optional[str],
        user_prompt: str,
        image_paths: Optional[List[Path]] = None,
        video_paths: Optional[List[Path]] = None,
        vault: Any = None,
        job_id: Optional[str] = None,
        task_name: str = "extract",
    ) -> str:
        """Call the LLM via the Agent's ModelConfigCache + AIWrapper.

        Returns the model's text output. Returns "" on failure.
        When `vault` is provided, the call's token usage is recorded in the
        vault's llm_call_log ledger under `task_name`.
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

        # Multimodal: build content array with text + image_url / video_url (base64)
        if image_paths or video_paths:
            content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for img_path in image_paths or []:
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
            for vid_path in video_paths or []:
                try:
                    b64 = base64.b64encode(Path(vid_path).read_bytes()).decode("ascii")
                    mime = mimetypes.guess_type(str(vid_path))[0] or "video/mp4"
                    content.append(
                        {
                            "type": "video_url",
                            "video_url": {"url": f"data:{mime};base64,{b64}"},
                        }
                    )
                except Exception as e:
                    logger.warning("Could not encode video %s: %s", vid_path, e)
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})

        gen_kwargs: Dict[str, Any] = {
            "messages": messages,
            "llm_model": model,
            "stream_out": False,
        }

        result_text = ""
        usage: Optional[Dict[str, Any]] = None
        error_code = 0
        started = time.monotonic()
        async for result in ai_wrapper.create(**gen_kwargs):
            if result and result.content:
                result_text += result.content
            if result is not None:
                result_usage = getattr(result, "usage", None)
                if result_usage:
                    usage = result_usage
                result_error = getattr(result, "error_code", 0) or 0
                if result_error:
                    error_code = result_error
        latency_ms = int((time.monotonic() - started) * 1000)

        if vault is not None:
            try:
                await vault.llm_call_log_add(
                    job_id=job_id,
                    task_name=task_name,
                    model=model,
                    usage=usage,
                    latency_ms=latency_ms,
                    error_code=error_code,
                )
            except Exception as e:
                logger.warning("llm_call_log_add failed (%s): %s", task_name, e)
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
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".avi": "video/x-msvideo",
        }
        return mapping.get(ext)


__all__ = ["IngestOrchestrator", "IngestJob", "IngestJobStore"]
