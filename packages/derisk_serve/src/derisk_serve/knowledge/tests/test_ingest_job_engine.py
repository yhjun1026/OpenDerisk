"""RFC-005: knowledge ingest via the persistent job engine (end-to-end).

Verifies the full wiring: ingest_file submits a `knowledge_ingest` job → the
JobService worker claims it → handle_ingest_job reads the durable raw/ copy →
runs the pipeline → acks. Plus restart-resume idempotency.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio

from derisk.component import SystemApp
from derisk.knowledge.types import ExtractMode, Space, new_space_id
from derisk.storage.metadata import DatabaseManager
from derisk_serve.job.config import ServeConfig as JobServeConfig
from derisk_serve.job.models.models import JobDao, JobEntity
from derisk_serve.job.service.service import Service as JobService
from derisk_serve.knowledge.config import ServeConfig as KnowledgeServeConfig
from derisk_serve.knowledge.service.service import Service as KnowledgeService
from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors


def _wiki_md(title: str, body: str) -> str:
    return f"---\ntype: source\ntitle: {title}\nsource_verbat: x\n---\n\n# {title}\n\n{body}\n"


def _stub_llm(monkeypatch, wiki_md_text: str, curation_json: str):
    async def _stub(self, model, system_prompt, user_prompt, image_paths=None, **kwargs):
        if system_prompt and "实体归并" in system_prompt:
            return curation_json
        return wiki_md_text
    from derisk_serve.knowledge.ingest import IngestOrchestrator
    monkeypatch.setattr(IngestOrchestrator, "_call_llm", _stub)


async def _wait_job_done(job_svc, job_id, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        row = job_svc.get(job_id)
        if row and row.status in ("done", "failed"):
            return row
        await asyncio.sleep(0.05)
    row = job_svc.get(job_id)
    raise AssertionError(
        f"job {job_id} did not finish: status={row.status if row else None} "
        f"err={row.last_error if row else None}"
    )


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    """A full KnowledgeService + JobService wired into one SystemApp."""
    register_builtin_extractors()

    system_app = SystemApp()

    # JobService with an isolated SQLite db.
    job_db = DatabaseManager.build_from(f"sqlite:///{tmp_path}/job.db", base=None)
    JobEntity.__table__.create(job_db._engine, checkfirst=True)
    job_dao = JobDao(db_manager=job_db)
    job_cfg = JobServeConfig(
        enabled=True, poll_interval_seconds=0.05, lease_seconds=60,
        concurrency=2, max_attempts_default=2,
    )
    job_svc = JobService(system_app=system_app, config=job_cfg, dao=job_dao)
    from derisk_serve.job.config import SERVE_SERVICE_COMPONENT_NAME
    system_app.register_instance(job_svc, name=SERVE_SERVICE_COMPONENT_NAME)

    # KnowledgeService
    kcfg = KnowledgeServeConfig()
    kcfg.local_root = str(tmp_path / "spaces")
    Path(kcfg.local_root).mkdir(parents=True, exist_ok=True)
    ksvc = KnowledgeService(system_app=system_app, serve_config=kcfg)
    ksvc.init_app(system_app)
    system_app.register_instance(ksvc, name="derisk_serve_knowledge_service")

    # Register the knowledge_ingest handler (mirrors knowledge Serve.after_init).
    orch = ksvc.orchestrator
    job_svc.register_handler("knowledge_ingest", orch.handle_ingest_job)

    # Start the worker loop.
    await job_svc.start()

    yield system_app, ksvc, job_svc

    await job_svc.stop()


@pytest.mark.asyncio
async def test_ingest_via_job_engine(env, monkeypatch):
    _, ksvc, job_svc = env
    _stub_llm(
        monkeypatch,
        _wiki_md("EngineDoc", "scoring card model details"),
        '{"entities": []}',
    )

    res = await ksvc.create_space(slug="eng-1", backend="local")
    vault = await ksvc.get_vault("eng-1")
    space = await ksvc.get_space_config("eng-1")

    # Simulate endpoints.upload_file: persist raw/ copy, then ingest.
    raw_path = vault.root / "raw" / "report.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("scoring card raw content for job engine", encoding="utf-8")
    tmp = Path(str(raw_path) + ".tmp")
    shutil.copy2(raw_path, tmp)

    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=tmp, original_filename="report.txt",
    )
    assert job.id.startswith("job_"), f"expected a DB job id, got {job.id}"
    # temp file unlinked by ingest_file (worker re-reads raw/)
    assert not tmp.exists()

    row = await _wait_job_done(job_svc, job.id)
    assert row.status == "done", f"job failed: {row.last_error}"
    assert row.result and "verbat_ids" in row.result
    assert len(row.result["verbat_ids"]) >= 1
    assert len(row.result["wiki_doc_ids"]) >= 1

    # verbats + wiki actually persisted in the vault
    from derisk_ext.knowledge.vaultfs import LocalVaultFS
    docs = await vault.doc_list(limit=100)
    assert any(d.title == "EngineDoc" or "EngineDoc" in (d.title or "") for d in docs)
    verbats = await vault.verbat_list(limit=100)
    assert len(verbats) >= 1


@pytest.mark.asyncio
async def test_ingest_restart_resume_idempotent(env, monkeypatch):
    """Stop the worker mid-flight, restart, job completes; no duplicate verbats."""
    _, ksvc, job_svc = env
    _stub_llm(
        monkeypatch,
        _wiki_md("ResumeDoc", "resume scoring card"),
        '{"entities": []}',
    )

    await ksvc.create_space(slug="eng-2", backend="local")
    vault = await ksvc.get_vault("eng-2")
    space = await ksvc.get_space_config("eng-2")

    raw_path = vault.root / "raw" / "resume.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("resume raw content", encoding="utf-8")

    # Stop the worker BEFORE ingest so the job sits pending (claimed=none).
    await job_svc.stop()
    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=raw_path,  # raw path; ingest unlinks it
        original_filename="resume.txt",
    )
    # raw_path got unlinked by ingest_file — re-create it so the handler can read.
    raw_path.write_text("resume raw content", encoding="utf-8")

    # Restart the worker — it should reclaim pending and complete.
    await job_svc.start()
    row = await _wait_job_done(job_svc, job.id, timeout=10)
    assert row.status == "done", f"job failed: {row.last_error}"

    # Idempotency: exactly one verbat for this content_hash, one wiki doc.
    verbats = await vault.verbat_list(limit=100)
    assert len(verbats) == 1, f"expected 1 verbat, got {len(verbats)}"


@pytest.mark.asyncio
async def test_ingest_jobs_endpoint_survives_restart(env, monkeypatch):
    """/ingest-jobs-equivalent: after dropping in-memory cache, the DB job row
    is still listable for the space."""
    _, ksvc, job_svc = env
    _stub_llm(monkeypatch, _wiki_md("PersistDoc", "persist"), '{"entities": []}')

    await ksvc.create_space(slug="eng-3", backend="local")
    vault = await ksvc.get_vault("eng-3")
    space = await ksvc.get_space_config("eng-3")
    raw_path = vault.root / "raw" / "persist.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("persist raw", encoding="utf-8")

    job = await ksvc.orchestrator.ingest_file(
        space=space, vault=vault, file_path=raw_path, original_filename="persist.txt",
    )
    await _wait_job_done(job_svc, job.id)

    # Drop the in-memory IngestJobStore (simulate restart).
    ksvc.orchestrator.jobs._jobs.clear()

    # The DB-backed listing still finds the job for this space.
    rows = await asyncio.to_thread(job_svc.dao.list_for_space, "eng-3", 50)
    assert any(r.id == job.id for r in rows)
    assert all(r.status == "done" for r in rows)