"""P2: write drift detection for L1 docs (hermes _detect_external_drift
alignment).

FS-as-truth: if an external writer modifies wiki/*.md directly, the
vault's documents.content_hash no longer matches the file. Overwrite
(doc_edit) and delete (doc_delete / curate_merge) must snapshot the
on-disk content to .bak.<ts> and refuse, never silently clobber.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from derisk.knowledge.types import new_space_id
from derisk_ext.knowledge.vaultfs import LocalVaultFS
from derisk_ext.knowledge.vaultfs.base import DocDriftError
from derisk_ext.storage.memory.knowledge_vault_store import (
    KnowledgeVaultMemoryConfig,
    KnowledgeVaultMemoryStore,
)

_DOC_MD = "---\ntype: concept\ntitle: Alpha\n---\n\nOriginal body about zephyr.\n"


@pytest_asyncio.fixture
async def vault(tmp_path: Path):
    v = LocalVaultFS(space_id=new_space_id(), root=tmp_path / "space")
    await v.initialize()
    yield v
    await v.close()


def _external_edit(vault: LocalVaultFS, path: str, content: str) -> None:
    """Simulate an external writer editing the markdown directly."""
    (vault.root / "wiki" / path).write_text(content, encoding="utf-8")


def _bak_files(vault: LocalVaultFS, path: str) -> list[Path]:
    return sorted((vault.root / "wiki").rglob(f"{Path(path).name}.bak.*"))


class TestDocEditDrift:
    @pytest.mark.asyncio
    async def test_normal_edit_after_write_not_flagged(self, vault):
        """The LLM read-then-write path must never trip the guard."""
        await vault.doc_create("concepts/a.md", _DOC_MD)
        await vault.doc_edit(
            "concepts/a.md",
            "---\ntype: concept\ntitle: Alpha\n---\n\nEdited by vault.\n",
        )
        doc = await vault.doc_read("concepts/a.md")
        assert doc.content.strip() == "Edited by vault."
        assert _bak_files(vault, "concepts/a.md") == []

    @pytest.mark.asyncio
    async def test_external_edit_triggers_snapshot_and_refusal(self, vault):
        await vault.doc_create("concepts/a.md", _DOC_MD)
        _external_edit(vault, "concepts/a.md", "---\ntype: concept\ntitle: Alpha\n---\n\nExternal change.\n")

        with pytest.raises(DocDriftError) as exc_info:
            await vault.doc_edit(
                "concepts/a.md",
                "---\ntype: concept\ntitle: Alpha\n---\n\nVault overwrite.\n",
            )

        # Snapshot path surfaced in the error; .bak holds external content.
        baks = _bak_files(vault, "concepts/a.md")
        assert len(baks) == 1
        assert exc_info.value.backup_path == f"concepts/a.md.bak.{baks[0].name.split('.bak.')[1]}"
        assert "External change." in baks[0].read_text(encoding="utf-8")
        # On-disk content untouched by the refused write.
        assert "External change." in (vault.root / "wiki" / "concepts" / "a.md").read_text(
            encoding="utf-8"
        )
        assert "Vault overwrite." not in (
            vault.root / "wiki" / "concepts" / "a.md"
        ).read_text(encoding="utf-8")


class TestDocDeleteDrift:
    @pytest.mark.asyncio
    async def test_delete_without_drift_works(self, vault):
        await vault.doc_create("concepts/a.md", _DOC_MD)
        await vault.doc_delete("concepts/a.md")
        assert await vault.doc_read("concepts/a.md") is None

    @pytest.mark.asyncio
    async def test_external_edit_blocks_delete(self, vault):
        await vault.doc_create("concepts/a.md", _DOC_MD)
        _external_edit(vault, "concepts/a.md", "---\ntype: concept\ntitle: Alpha\n---\n\nExternal change.\n")

        with pytest.raises(DocDriftError):
            await vault.doc_delete("concepts/a.md")

        assert len(_bak_files(vault, "concepts/a.md")) == 1
        assert await vault.doc_read("concepts/a.md") is not None


class TestCurateMergeDrift:
    @pytest.mark.asyncio
    async def test_merge_refused_when_source_drifted(self, vault):
        store = KnowledgeVaultMemoryStore(
            config=KnowledgeVaultMemoryConfig(space_slug="memory-test"),
            vault=vault,
        )
        await vault.doc_create("concepts/s1.md", _DOC_MD)
        await vault.doc_create(
            "concepts/s2.md",
            "---\ntype: concept\ntitle: Beta\n---\n\nSecond doc.\n",
        )
        _external_edit(vault, "concepts/s1.md", "---\ntype: concept\ntitle: Alpha\n---\n\nUser edit.\n")

        with pytest.raises(DocDriftError):
            await store.curate_merge(
                source_paths=["concepts/s1.md", "concepts/s2.md"],
                target_path="concepts/merged.md",
                merged_content="merged body",
                frontmatter={"type": "concept", "title": "Merged"},
            )

        # Pre-flight refusal: no partial merge — sources intact, no target.
        assert len(_bak_files(vault, "concepts/s1.md")) == 1
        assert await vault.doc_read("concepts/s1.md") is not None
        assert await vault.doc_read("concepts/s2.md") is not None
        assert await vault.doc_read("concepts/merged.md") is None

    @pytest.mark.asyncio
    async def test_merge_without_drift_succeeds(self, vault):
        store = KnowledgeVaultMemoryStore(
            config=KnowledgeVaultMemoryConfig(space_slug="memory-test"),
            vault=vault,
        )
        await vault.doc_create("concepts/s1.md", _DOC_MD)
        await vault.doc_create(
            "concepts/s2.md",
            "---\ntype: concept\ntitle: Beta\n---\n\nSecond doc.\n",
        )
        target_id = await store.curate_merge(
            source_paths=["concepts/s1.md", "concepts/s2.md"],
            target_path="concepts/merged.md",
            merged_content="merged body",
            frontmatter={"type": "concept", "title": "Merged"},
        )
        assert target_id
        assert await vault.doc_read("concepts/merged.md") is not None
        assert await vault.doc_read("concepts/s1.md") is None
        assert await vault.doc_read("concepts/s2.md") is None
