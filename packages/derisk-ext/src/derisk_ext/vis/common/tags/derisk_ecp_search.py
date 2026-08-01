"""ECP Semantic Search VIS Component.

Renders search_semantics results as structured semantic catalog cards:
- Query header with result count
- Each result: type badge (指标/实体/维度/关系), id, name, aliases, one_line
- Empty state guidance (fallback to execute_raw_sql / propose_semantic)

Usage:
    ```d-ecp-search
    {
        "query": "销售",
        "workspace_id": "default",
        "total": 2,
        "results": [
            {"id": "mtr.weekly_sales", "type": "metric", "name": "周销售额",
             "aliases": ["Weekly Sales"], "one_line": "门店的周销售总额"}
        ]
    }
    ```
"""

from typing import Any, Dict, Optional

from derisk.vis import Vis


class DeriskEcpSearch(Vis):
    """ECP semantic search result visualization component."""

    @classmethod
    def vis_tag(cls) -> str:
        return "d-ecp-search"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        results = kwargs.get("results") or []
        return {
            "query": kwargs.get("query", ""),
            "workspace_id": kwargs.get("workspace_id", "default"),
            "total": kwargs.get("total", len(results)),
            "results": results,
        }

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self.sync_generate_param(**kwargs)
