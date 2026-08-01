"""Structural lint tests (RFC 003 §7) — BaseVaultFS.doc_lint.

The lint implementation lives on BaseVaultFS and is backend-agnostic
(public VaultFS methods only); these tests run it against LocalVaultFS
and cover the six rules declared in schema.md `## Lint Rules`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import (
    Edge,
    ExtractMode,
    Verbat,
    new_edge_id,
    new_space_id,
)
from derisk_ext.knowledge.vaultfs import LocalVaultFS


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "lint_space")
    await v.initialize()
    yield v
    await v.close()


@pytest.mark.asyncio
async def test_orphan_doc_rule(vault):
    await vault.doc_create(
        path="concepts/lonely.md",
        content=(
            "---\ntype: concept\ntitle: Lonely\ncreated: 2026-07-19\n"
            "updated: 2026-07-19\n---\n\nNo links here.\n"
        ),
    )
    issues = await vault.doc_lint()
    orphan = [i for i in issues if i.rule == "orphan_doc"]
    assert any(i.path == "concepts/lonely.md" for i in orphan)


@pytest.mark.asyncio
async def test_broken_wikilink_rule(vault):
    await vault.doc_create(
        path="concepts/a.md",
        content=(
            "---\ntype: concept\ntitle: A\ncreated: 2026-07-19\nupdated: 2026-07-19\n"
            "---\n\nLinks to [[missing-page]].\n"
        ),
    )
    issues = await vault.doc_lint()
    broken = [i for i in issues if i.rule == "broken_wikilink"]
    assert any("missing-page" in i.message for i in broken)
    assert all(i.severity == "warning" for i in broken)


@pytest.mark.asyncio
async def test_verbat_without_wiki_rule(vault):
    v = Verbat.create(
        space_id=vault.space_id,
        content="raw note with no derived wiki",
        source_file="note.md",
        extract_mode=ExtractMode.UPLOAD,
    )
    vid = await vault.verbat_add(v)
    issues = await vault.doc_lint()
    uncited = [i for i in issues if i.rule == "verbat_without_wiki"]
    assert any(i.verbat_id == vid for i in uncited)


@pytest.mark.asyncio
async def test_stale_edge_rule(vault):
    # Edge sourced from a verbat that gets deprecated → stale.
    v = Verbat.create(
        space_id=vault.space_id,
        content="will be deprecated",
        source_file="stale.md",
        extract_mode=ExtractMode.UPLOAD,
    )
    vid = await vault.verbat_add(v)
    await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="doc:x",
            predicate="derived-from",
            object=f"verbat:{vid}",
            source_verbat_id=vid,
        )
    )
    await vault.verbat_deprecate(vid)
    issues = await vault.doc_lint()
    stale = [i for i in issues if i.rule == "stale_edge"]
    assert any(i.verbat_id == vid for i in stale)


@pytest.mark.asyncio
async def test_frontmatter_missing_rule(vault):
    # Default schema requires [type, title, created, updated].
    await vault.doc_create(
        path="concepts/nofm.md",
        content="---\ntype: concept\ntitle: NoDates\n---\n\nBody.\n",
    )
    issues = await vault.doc_lint()
    missing = [
        i for i in issues
        if i.rule == "frontmatter_missing" and i.path == "concepts/nofm.md"
    ]
    assert missing
    assert "created" in missing[0].message


@pytest.mark.asyncio
async def test_contradiction_rule(vault):
    # Same pair asserts (part-of) and contradicts at once.
    for pred in ("part-of", "contradicts"):
        await vault.edge_add(
            Edge(
                id=new_edge_id(),
                space_id=vault.space_id,
                subject="alpha",
                predicate=pred,
                object="beta",
            )
        )
    issues = await vault.doc_lint()
    contra = [i for i in issues if i.rule == "contradiction"]
    assert contra
    assert "alpha" in contra[0].message


@pytest.mark.asyncio
async def test_lint_path_narrows_scope(vault):
    await vault.doc_create(
        path="concepts/one.md",
        content="---\ntype: concept\ntitle: One\n---\n\nA.\n",
    )
    await vault.doc_create(
        path="concepts/two.md",
        content="---\ntype: concept\ntitle: Two\n---\n\nB.\n",
    )
    issues = await vault.doc_lint(path="concepts/one.md")
    paths = {i.path for i in issues if i.path}
    assert paths <= {"concepts/one.md"}


@pytest.mark.asyncio
async def test_lint_respects_schema_toggle(vault):
    """Turning a rule off in schema.md suppresses its findings."""
    schema_md = await vault.read_schema_md()
    await vault.write_schema_md(
        schema_md.replace("orphan_pages: true", "orphan_pages: false")
    )
    await vault.doc_create(
        path="concepts/lonely2.md",
        content="---\ntype: concept\ntitle: Lonely2\n---\n\nAlone.\n",
    )
    issues = await vault.doc_lint()
    assert not any(i.rule == "orphan_doc" for i in issues)


# ---------------------------------------------------------------------------
# Schema-drift rules (RFC 003 §5.2/§5.4/§5.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_type_rule(vault):
    """Doc whose type was removed from schema.md Page Types (RFC 003 §5.2)."""
    await vault.doc_create(
        path="concepts/orphan-type.md",
        content=(
            "---\ntype: concept\ntitle: Orphan Type\n"
            "created: 2026-07-19\nupdated: 2026-07-19\n---\n\nBody.\n"
        ),
    )
    # Remove the 'concept' row from schema.md Page Types
    schema_md = await vault.read_schema_md()
    await vault.write_schema_md(
        schema_md.replace(
            "| concept | wiki/concepts/ | 抽象概念、理论、方法 |\n", ""
        )
    )
    issues = await vault.doc_lint()
    unknown = [
        i for i in issues
        if i.rule == "unknown_type" and i.path == "concepts/orphan-type.md"
    ]
    assert unknown
    assert "concept" in unknown[0].message


@pytest.mark.asyncio
async def test_unknown_predicate_rule(vault):
    """Edge whose predicate was removed from schema.md Relation Types
    (RFC 003 §5.4)."""
    await vault.edge_add(
        Edge(
            id=new_edge_id(),
            space_id=vault.space_id,
            subject="alpha",
            predicate="links-to",
            object="beta",
        )
    )
    # Remove 'links-to' from schema.md Relation Types
    schema_md = await vault.read_schema_md()
    await vault.write_schema_md(
        schema_md.replace(
            "| links-to | linked-by | wikilink 关联 |\n", ""
        )
    )
    issues = await vault.doc_lint()
    unknown = [i for i in issues if i.rule == "unknown_predicate"]
    assert unknown
    assert any("links-to" in i.message for i in unknown)


@pytest.mark.asyncio
async def test_path_mismatch_rule(vault):
    """Doc whose directory doesn't match its type's declared dir
    (RFC 003 §5.5)."""
    # concept type declares dir wiki/concepts/, but we put it in entities/
    await vault.doc_create(
        path="entities/misplaced.md",
        content=(
            "---\ntype: concept\ntitle: Misplaced\n"
            "created: 2026-07-19\nupdated: 2026-07-19\n---\n\nBody.\n"
        ),
    )
    issues = await vault.doc_lint()
    mismatch = [
        i for i in issues
        if i.rule == "path_mismatch" and i.path == "entities/misplaced.md"
    ]
    assert mismatch
    assert "entities/" in mismatch[0].message
    assert "wiki/concepts/" in mismatch[0].message


@pytest.mark.asyncio
async def test_path_mismatch_no_false_positive(vault):
    """Doc in the correct dir should not trigger path_mismatch."""
    await vault.doc_create(
        path="concepts/correct.md",
        content=(
            "---\ntype: concept\ntitle: Correct\n"
            "created: 2026-07-19\nupdated: 2026-07-19\n---\n\nBody.\n"
        ),
    )
    issues = await vault.doc_lint()
    assert not any(
        i.rule == "path_mismatch" and i.path == "concepts/correct.md"
        for i in issues
    )
