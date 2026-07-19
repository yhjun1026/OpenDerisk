"""Ingest job ledger tests — jobs persist to `.ks/index.db` (ingest_jobs
table) and remain queryable after a restart (fresh orchestrator + reopened
vault). The in-memory store stays the live view for in-flight jobs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import Space, new_space_id
from derisk_ext.knowledge.extractors.registry_init import register_builtin_extractors
from derisk_ext.knowledge.vaultfs import LocalVaultFS


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "job_space")
    await v.initialize()
    yield v
    await v.close()


@pytest.fixture
def space(vault):
    return Space(id=vault.space_id, slug="job-space", name="Job Space")


@pytest.fixture(autouse=True, scope="module")
def _ensure_builtins():
    register_builtin_extractors()
    yield


def _patch_aiwrapper(monkeypatch, wiki_md: str):
    class _FakeResult:
        content = wiki_md
        usage = None
        error_code = 0

    async def _fake_create(self, **config):
        yield _FakeResult()

    from derisk.agent.util.llm.llm_client import AIWrapper

    monkeypatch.setattr(AIWrapper, "create", _fake_create)
    from derisk.agent.util.llm.model_config_cache import ModelConfigCache

    if not ModelConfigCache.has_model("test-model"):
        ModelConfigCache.register_configs(
            {
                "stub/test-model": {
                    "provider": "openai",
                    "model": "test-model",
                    "api_key": "sk-x",
                    "base_url": "http://x",
                    "protocol": "openai",
                }
            }
        )


async def _wait(orch, job_id, timeout=8.0):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = orch.jobs.get(job_id)
        if job and job.status in ("done", "failed"):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} timed out")


@pytest.mark.asyncio
async def test_job_transitions_persist_to_ledger(vault, space, tmp_path, monkeypatch):
    _patch_aiwrapper(monkeypatch, "---\ntype: source\ntitle: T\n---\n\nbody\n")
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    orch = IngestOrchestrator(system_app=None)
    f = tmp_path / "in.txt"
    f.write_text("raw content for ledger test", encoding="utf-8")
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename="in.txt"
    )
    finished = await _wait(orch, job.id)
    assert finished.status == "done", finished.error

    row = await vault.ingest_job_get(job.id)
    assert row is not None
    assert row["status"] == "done"
    assert row["space_slug"] == "job-space"
    assert row["source_file"] == "in.txt"
    assert row["verbat_ids"] == finished.verbat_ids
    assert row["finished_at"] is not None


@pytest.mark.asyncio
async def test_list_jobs_merges_memory_and_ledger(vault, space, tmp_path, monkeypatch):
    _patch_aiwrapper(monkeypatch, "---\ntype: source\ntitle: T2\n---\n\nbody\n")
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    orch = IngestOrchestrator(system_app=None)
    f = tmp_path / "in2.txt"
    f.write_text("second raw content", encoding="utf-8")
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename="in2.txt"
    )
    await _wait(orch, job.id)

    # Simulate restart: a fresh orchestrator has empty in-memory state,
    # but list_jobs still returns the persisted job from the ledger.
    restarted = IngestOrchestrator(system_app=None)
    jobs = await restarted.list_jobs(space.slug, vault, limit=10)
    assert any(j.id == job.id and j.status == "done" for j in jobs)

    # In-flight (in-memory) rows win over ledger rows on id conflict.
    merged = await orch.list_jobs(space.slug, vault, limit=10)
    assert any(j.id == job.id for j in merged)


@pytest.mark.asyncio
async def test_ledger_survives_vault_reopen(vault, space, tmp_path, monkeypatch):
    _patch_aiwrapper(monkeypatch, "---\ntype: source\ntitle: T3\n---\n\nbody\n")
    from derisk_serve.knowledge.ingest import IngestOrchestrator

    orch = IngestOrchestrator(system_app=None)
    f = tmp_path / "in3.txt"
    f.write_text("third raw content", encoding="utf-8")
    job = await orch.ingest_file(
        space=space, vault=vault, file_path=f, original_filename="in3.txt"
    )
    await _wait(orch, job.id)

    root, space_id = vault.root, vault.space_id
    await vault.close()

    v2 = LocalVaultFS(space_id=space_id, root=root)
    await v2.initialize()
    try:
        rows = await v2.ingest_job_list(limit=10)
        assert any(r["id"] == job.id and r["status"] == "done" for r in rows)
    finally:
        await v2.close()
