"""RFC-005 scenario B complement: include_invalid=True recalls everything.

The pre-written acceptance tests (test_doc_search_graph.py) cover the
default temporal policy — expired about edges don't expand, superseded
docs are filtered. This file pins the inverse: with include_invalid=True,
graph mode recalls both the superseded doc and the doc behind an expired
about edge (full history recall).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import Edge, new_edge_id, new_space_id
from derisk_ext.knowledge.vaultfs import LocalVaultFS


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    root = tmp_path / "ks_graph_inv"
    v = LocalVaultFS(space_id=new_space_id(), root=root)
    await v.initialize()
    yield v
    await v.close()


async def _mkdoc(vault, path, title, body):
    md = f"---\ntype: source\ntitle: {title}\n---\n\n{body}\n"
    return await vault.doc_create(path=path, content=md)


@pytest.mark.asyncio
async def test_include_invalid_recalls_superseded_doc(vault):
    """graph mode + include_invalid=True keeps the superseded old doc."""
    old_doc = await _mkdoc(vault, "sources/old.md", "Old", "scoring card old version")
    new_doc = await _mkdoc(vault, "sources/new.md", "New", "scoring card new version")
    now = datetime.utcnow()
    await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject=f"doc:{new_doc}",
            predicate="supersedes",
            object=f"doc:{old_doc}",
            source_document_id=new_doc,
            valid_from=now,
            created_at=now,
        )
    )

    default_hits = await vault.doc_search("scoring", mode="graph", limit=10)
    assert old_doc not in {h.document_id for h in default_hits}

    all_hits = await vault.doc_search(
        "scoring", mode="graph", limit=10, include_invalid=True
    )
    all_ids = {h.document_id for h in all_hits}
    assert old_doc in all_ids
    assert new_doc in all_ids


@pytest.mark.asyncio
async def test_include_invalid_expands_through_expired_about_edge(vault):
    """graph mode + include_invalid=True follows expired about edges too."""
    seed = await _mkdoc(vault, "sources/seed.md", "Seed", "scoring card main entry")
    stale = await _mkdoc(vault, "sources/stale.md", "Stale", "stale expired content")
    ent_md = "---\ntype: entity\ntitle: e1\n---\n\nentity\n"
    ent = await vault.doc_create(path="entities/e1.md", content=ent_md)
    now = datetime.utcnow()
    await vault.edge_add(
        Edge(
            id=new_edge_id(), space_id=vault.space_id,
            subject=f"doc:{ent}", predicate="about", object=f"doc:{seed}",
            valid_from=now, created_at=now,
        )
    )
    await vault.edge_add(
        Edge(
            id=new_edge_id(), space_id=vault.space_id,
            subject=f"doc:{ent}", predicate="about", object=f"doc:{stale}",
            valid_from=now - timedelta(days=2),
            valid_to=now - timedelta(days=1),
            created_at=now - timedelta(days=2),
        )
    )

    default_hits = await vault.doc_search("scoring", mode="graph", limit=10)
    assert stale not in {h.document_id for h in default_hits}

    all_hits = await vault.doc_search(
        "scoring", mode="graph", limit=10, include_invalid=True
    )
    assert stale in {h.document_id for h in all_hits}
