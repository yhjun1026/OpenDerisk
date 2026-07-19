"""Structure-aware chunking tests (vaultfs/_util.chunk_text).

Covers: heading/code/list block boundaries, fenced code never split,
overlap between consecutive chunks, content-hash stability (idempotent
vector rebuilds), and hard-split fallback for oversize blocks.
"""

from __future__ import annotations

from derisk_ext.knowledge.vaultfs._util import (
    _split_markdown_blocks,
    chunk_text,
    chunk_text_plain,
)


def test_code_fence_kept_whole():
    md = "Before text.\n\n```python\ndef foo():\n    return 42\n```\n\nAfter text."
    blocks = _split_markdown_blocks(md)
    code = [b for b in blocks if "```" in b]
    assert len(code) == 1
    assert "def foo():" in code[0] and "return 42" in code[0]

    # Even with a small max_chars the fence stays intact (hard-split only
    # applies when the block alone exceeds max_chars).
    chunks = chunk_text(md, max_chars=60)
    fenced = [t for _, t, _ in chunks if "```" in t]
    assert fenced
    assert all(t.count("```") % 2 == 0 for t in fenced)


def test_heading_starts_new_block():
    md = "# One\n\nbody one\n\n## Two\n\nbody two"
    blocks = _split_markdown_blocks(md)
    assert blocks[0] == "# One"
    assert "## Two" in blocks


def test_list_kept_as_one_block():
    md = "Intro.\n\n- a\n- b\n- c\n\nOutro."
    blocks = _split_markdown_blocks(md)
    assert any(b == "- a\n- b\n- c" for b in blocks)


def test_chunks_respect_max_chars():
    md = "\n\n".join(f"Paragraph {i} with some text." for i in range(20))
    chunks = chunk_text(md, max_chars=100, overlap_chars=0)
    assert len(chunks) > 1
    assert all(len(t) <= 100 for _, t, _ in chunks)


def test_overlap_carries_trailing_block():
    md = "\n\n".join(f"Block {i} abcdefgh" for i in range(6))  # ~18 chars each
    chunks = chunk_text(md, max_chars=80, overlap_chars=40)
    assert len(chunks) >= 2
    # Some block text appears in two consecutive chunks (the overlap).
    first_blocks = set(chunks[0][1].split("\n\n"))
    second_blocks = set(chunks[1][1].split("\n\n"))
    assert first_blocks & second_blocks


def test_no_overlap_when_disabled():
    md = "\n\n".join(f"Block {i} abcdefgh" for i in range(6))
    chunks = chunk_text(md, max_chars=80, overlap_chars=0)
    all_blocks = [b for _, t, _ in chunks for b in t.split("\n\n")]
    assert len(all_blocks) == len(set(all_blocks))


def test_hash_stability_across_calls():
    md = "# Title\n\nSome **markdown** body.\n\n- one\n- two"
    c1 = chunk_text(md, max_chars=2000)
    c2 = chunk_text(md, max_chars=2000)
    assert [x[2] for x in c1] == [x[2] for x in c2]
    # Unchanged prefix chunk keeps its hash when the tail changes.
    long_md = "\n\n".join(f"Paragraph {i} lorem ipsum dolor." for i in range(10))
    a = chunk_text(long_md, max_chars=100, overlap_chars=0)
    b = chunk_text(long_md + "\n\nExtra trailing paragraph.", max_chars=100, overlap_chars=0)
    assert a[0][2] == b[0][2]


def test_oversize_block_hard_split():
    big = "x" * 500
    chunks = chunk_text(big, max_chars=120)
    assert all(len(t) <= 120 for _, t, _ in chunks)
    assert "".join(t for _, t, _ in chunks) == big


def test_empty_and_trivial_inputs():
    assert chunk_text("") == [(0, "", chunk_text("")[0][2])]
    assert chunk_text_plain("hello") == ["hello"]


def test_indices_sequential():
    md = "\n\n".join(f"Paragraph {i} with some more text here." for i in range(10))
    chunks = chunk_text(md, max_chars=100)
    assert [i for i, _, _ in chunks] == list(range(len(chunks)))
