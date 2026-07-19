"""Pure helpers shared by all VaultFS backends.

No I/O, no DB, no asyncio — just path manipulation, markdown serialization,
datetime parsing, and text chunking. Both LocalVaultFS and DistributedVaultFS
import these to avoid duplication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ParsedMarkdown:
    """Result of parsing a markdown file with optional YAML frontmatter."""

    content: str
    frontmatter: dict


# Files protected from deletion (spec llm-wiki.md + RFC 001 §4.5)
PROTECTED_FILES = {
    "index.md",
    "log.md",
    "overview.md",
    "schema.md",
    "purpose.md",
}

# Inline content threshold: verbats smaller than this are stored inline,
# larger ones are stored as blobs (file on disk, S3 object, etc.) and
# referenced by path.
#
# 设为 0 让所有 verbat 都落盘到 raw/{extract_mode}/{id}.txt —— 这样
# raw/convos/ 目录成为可信的"原始证据"层，UI 的 raw view 直接读文件，
# SQLite 退回纯索引（content_ref 指向文件）。L1/L2 抽取失败时 raw 仍
# 可作为兜底重新抽取。
INLINE_THRESHOLD = 0


def normalize_wiki_path(path: str) -> str:
    """Normalize a wiki path: strip leading slashes, prevent path traversal.

    Also strips a leading ``wiki/`` segment so callers may pass either the
    bare doc path (``sources/foo.md``) or the path as returned by the wiki
    tree endpoint (``wiki/sources/foo.md``). DB rows and the on-disk wiki/
    directory both use the bare form.
    """
    p = path.strip().lstrip("/")
    if p.startswith("wiki/"):
        p = p[len("wiki/"):]
    if ".." in p.split("/"):
        raise ValueError(f"Illegal path traversal: {path}")
    return p


def validate_wiki_path(path: str) -> None:
    if not path:
        raise ValueError("Empty wiki path")
    if path.startswith("/"):
        raise ValueError(f"Absolute path not allowed: {path}")
    if ".." in path.split("/"):
        raise ValueError(f"Path traversal not allowed: {path}")


def serialize_markdown(frontmatter: dict, body: str) -> str:
    """Reconstruct markdown with YAML frontmatter fence."""
    import yaml as _yaml

    if not frontmatter:
        return body
    fm_text = _yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm_text}\n---\n\n{body}"


def parse_markdown(raw: str) -> ParsedMarkdown:
    """Split a markdown file into YAML frontmatter and body.

    Supports the ``---`` fence style. If no frontmatter is present, the whole
    text is returned as content and frontmatter is empty.
    """
    import yaml as _yaml

    raw = raw.replace("\r\n", "\n")
    if raw.startswith("---\n"):
        # Find the closing fence on its own line.
        close_idx = raw.find("\n---", 4)
        if close_idx != -1:
            fm_text = raw[4:close_idx]
            try:
                frontmatter = _yaml.safe_load(fm_text) or {}
            except Exception:
                frontmatter = {}
            content = raw[close_idx + 4 :].lstrip("\n")
            return ParsedMarkdown(content=content, frontmatter=frontmatter)
    return ParsedMarkdown(content=raw, frontmatter={})


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def make_snippet(content: str, query: str, context: int = 50) -> str:
    """Extract a snippet around the first occurrence of query."""
    idx = content.lower().find(query.lower())
    if idx == -1:
        return content[:200]
    start = max(0, idx - context)
    end = min(len(content), idx + len(query) + context)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


def _split_markdown_blocks(text: str) -> list[str]:
    """Split markdown into semantic blocks at structural boundaries.

    Block boundaries:
    - ATX headings (``# …``) start a new block
    - fenced code blocks (``` … ```) are kept whole (never split mid-code)
    - consecutive list lines (``- ``/``* ``/``1. ``) form one block
    - blank-line-separated paragraphs form one block each
    """
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    in_list = False

    def _flush() -> None:
        nonlocal current
        block = "\n".join(current).strip()
        if block:
            blocks.append(block)
        current = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if in_fence:
                # Closing fence — end the code block.
                current.append(line)
                _flush()
                in_fence = False
            else:
                # Opening fence — start a fresh block.
                _flush()
                current.append(line)
                in_fence = True
                in_list = False
            continue
        if in_fence:
            current.append(line)
            continue
        if stripped.startswith("#"):
            _flush()
            in_list = False
            current.append(line)
            continue
        is_list_item = bool(
            re.match(r"^(\s*[-*+] |\s*\d+[.)] )", line)
        ) if stripped else False
        if not stripped:
            _flush()
            in_list = False
            continue
        if is_list_item:
            if not in_list:
                _flush()
                in_list = True
            current.append(line)
            continue
        if in_list:
            # Non-list line ends the list block.
            _flush()
            in_list = False
        current.append(line)
    _flush()
    return blocks


def chunk_text(
    text: str, max_chars: int = 2000, overlap_chars: int = 200
) -> list[tuple[int, str, str]]:
    """Markdown structure-aware chunking with content-hash IDs.

    Splits into semantic blocks (headings / fenced code / lists /
    paragraphs — see `_split_markdown_blocks`), then greedily packs whole
    blocks into chunks up to `max_chars`. Consecutive chunks overlap by
    carrying over the trailing block(s) of the previous chunk that fit in
    `overlap_chars`, so context that spans a boundary stays retrievable.
    A single block larger than `max_chars` is hard-split on the size
    boundary (last resort — structure is preserved whenever possible).

    Returns a list of `(chunk_index, chunk_text, content_hash)` tuples
    where `content_hash = sha256(chunk_text)[:16]`. The hash is stable
    across re-chunking for unchanged chunks, so vector IDs derived from
    it (`doc:{doc_id}:chunk:{hash}`) survive edits to other parts of the
    document.
    """
    import hashlib

    def _hash(piece: str) -> str:
        return hashlib.sha256(piece.encode("utf-8")).hexdigest()[:16]

    blocks = _split_markdown_blocks(text)
    if not blocks:
        return [(0, text, _hash(text))]

    pieces: list[str] = []
    current = ""
    for block in blocks:
        candidate = current + "\n\n" + block if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
            # Overlap: carry trailing blocks of the emitted chunk into the
            # next one, bounded by overlap_chars.
            overlap = ""
            for prev_block in reversed(_split_markdown_blocks(current)):
                candidate_overlap = (
                    prev_block + "\n\n" + overlap if overlap else prev_block
                )
                if len(candidate_overlap) > overlap_chars:
                    break
                overlap = candidate_overlap
            current = overlap
        # A block that (even without overlap) exceeds max_chars is
        # hard-split on the size boundary.
        while len(block) > max_chars:
            head, block = block[:max_chars], block[max_chars:]
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        candidate = current + "\n\n" + block if current else block
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = block
    if current.strip():
        pieces.append(current)
    if not pieces:
        pieces = [text]

    return [(i, piece, _hash(piece)) for i, piece in enumerate(pieces)]


def chunk_text_plain(text: str, max_chars: int = 2000) -> list[str]:
    """Return just the chunk texts (no indices/hashes)."""
    return [c[1] for c in chunk_text(text, max_chars)]
