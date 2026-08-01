"""Space-level tools: schema.md and lint (RFC 004 §3)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from derisk.agent.tools.context import ToolContext
from derisk.agent.tools.result import ToolResult

from derisk_ext.knowledge.tools.base import KnowledgeToolBase


class SchemaReadTool(KnowledgeToolBase):
    """Read the raw schema.md content of a space."""

    @classmethod
    def tool_name(cls) -> str:
        return "schema_read"

    @classmethod
    def tool_description(cls) -> str:
        return "Read the raw schema.md content of the space. Use this before adding new page types or relation types."

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            raw = await vault.read_schema_md()
            return self.ok({"schema_md": raw})
        except Exception as e:
            return self.fail(str(e))


class SchemaWriteTool(KnowledgeToolBase):
    """Replace schema.md content. Caller is responsible for triggering reindex."""

    @classmethod
    def tool_name(cls) -> str:
        return "schema_write"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Replace schema.md content. Editing schema.md immediately affects "
            "future doc_create / edge_add validation."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            await vault.write_schema_md(args["content"])
            return self.ok({"ok": True})
        except Exception as e:
            return self.fail(str(e))


class LintRunTool(KnowledgeToolBase):
    """Run lint checks per schema.md ## Lint Rules."""

    @classmethod
    def tool_name(cls) -> str:
        return "lint_run"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Run structural lint checks (orphan pages, stale edges, "
            "contradictions, dangling links, schema drift, etc.) per "
            "schema.md Lint Rules. Pass path to lint a single page; omit "
            "for a full-space scan. After reviewing issues, use doc_create "
            "to fill missing pages, doc_edit to fix broken wikilinks, and "
            "edge_invalidate to retire stale edges."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Optional: narrow lint to a single page (relative "
                        "to wiki/, e.g. 'concepts/attention.md'). Omit for "
                        "a full-space scan."
                    ),
                },
            },
        }

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            if not hasattr(vault, "doc_lint"):
                return self.fail(
                    "vault backend does not implement doc_lint()",
                    error_code="NOT_IMPLEMENTED",
                )
            issues = await vault.doc_lint(path=args.get("path"))
            return self.ok(
                {
                    "issues": [
                        {
                            "rule": i.rule,
                            "severity": i.severity,
                            "path": i.path,
                            "edge_id": i.edge_id,
                            "verbat_id": i.verbat_id,
                            "message": i.message,
                        }
                        for i in issues
                    ]
                }
            )
        except Exception as e:
            return self.fail(str(e))


class LintSuggestTool(KnowledgeToolBase):
    """Gather wiki-health context for LLM-driven analysis (llm-wiki.md:41).

    Unlike ``lint_run`` (deterministic structural checks), this tool
    collects the context the agent needs to produce generative
    suggestions: lint issues, a doc inventory, index.md, and a
    broken-wikilink frequency map (which missing concepts are
    referenced most). The agent — being the LLM — analyzes the returned
    report to suggest new pages to create, data gaps to fill, and
    questions to investigate. This is the generative side of the
    llm-wiki Lint operation that ``lint_run`` alone cannot cover.
    """

    @classmethod
    def tool_name(cls) -> str:
        return "lint_suggest"

    @classmethod
    def tool_description(cls) -> str:
        return (
            "Gather wiki-health context (lint issues, doc inventory, "
            "index.md, broken-wikilink frequency) for LLM-driven analysis. "
            "Returns a structured report — analyze it to suggest new pages "
            "to create, data gaps to fill, and research questions to pursue. "
            "This complements lint_run (structural) with generative, "
            "LLM-driven health-check guidance."
        )

    def _define_own_parameters(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(
        self, args: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> ToolResult:
        try:
            vault = await self._get_vault(args, context)
            if not hasattr(vault, "doc_lint"):
                return self.fail(
                    "vault backend does not implement doc_lint()",
                    error_code="NOT_IMPLEMENTED",
                )

            # 1. Structural lint issues (grouped by rule for quick scan)
            issues = await vault.doc_lint()
            issue_counts: Dict[str, int] = {}
            for i in issues:
                issue_counts[i.rule] = issue_counts.get(i.rule, 0) + 1

            # 2. Doc inventory (path | title | type — compact)
            docs = await vault.doc_list(limit=10000)
            doc_inventory = [
                {"path": d.path, "title": d.title, "type": d.type}
                for d in docs
            ]

            # 3. index.md content (the LLM-maintained catalog)
            index_md = await vault.read_wiki_file("index.md")

            # 4. Broken-wikilink frequency: which missing concepts are
            #    referenced most often. These are the highest-value pages
            #    to create (llm-wiki "important concepts mentioned but
            #    lacking their own page").
            missing_pages = await self._missing_page_frequency(vault, docs)

            return self.ok(
                {
                    "issue_counts": issue_counts,
                    "total_issues": len(issues),
                    "doc_count": len(docs),
                    "doc_inventory": doc_inventory,
                    "index_md": index_md,
                    "missing_pages": missing_pages,
                    "guidance": (
                        "Analyze this report as the wiki's LLM maintainer. "
                        "1) For top missing_pages, suggest concrete page "
                        "titles/types to create via doc_create. "
                        "2) For issue_counts with many orphan_doc, suggest "
                        "cross-references to add. "
                        "3) Identify data gaps (topics with sparse coverage) "
                        "and suggest sources to seek. "
                        "4) Propose 3-5 research questions worth investigating. "
                        "Then act: create missing pages, fix broken links "
                        "via doc_edit, and retire stale edges."
                    ),
                }
            )
        except Exception as e:
            return self.fail(str(e))

    async def _missing_page_frequency(
        self, vault, docs: list
    ) -> list[Dict[str, Any]]:
        """Count how often each dangling [[wikilink]] target appears.

        Returns a list sorted by frequency (desc), each entry:
        ``{"target": str, "count": int, "referenced_by": [paths]}``.
        Caps at 50 entries to keep the report compact.
        """
        from derisk.knowledge.frontmatter import extract_wikilinks

        doc_paths = {d.path for d in docs}
        counts: Dict[str, int] = {}
        refs: Dict[str, list[str]] = {}

        for d in docs:
            full = await vault.doc_read(d.path)
            if not full:
                continue
            for link in extract_wikilinks(full.content):
                target = link.split("|")[0].strip().lstrip("/")
                target_path = target if target.endswith(".md") else f"{target}.md"
                exists = any(
                    p == target_path or p.endswith(target) for p in doc_paths
                )
                if not exists:
                    counts[target] = counts.get(target, 0) + 1
                    refs.setdefault(target, []).append(d.path)

        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:50]
        return [
            {"target": t, "count": c, "referenced_by": refs[t][:10]}
            for t, c in ranked
        ]
