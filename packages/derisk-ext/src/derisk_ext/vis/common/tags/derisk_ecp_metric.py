"""ECP Metric Query VIS Component.

Renders execute_metric_query results with the ECP trust protocol:
- Trust badge: verified (✅ 可信口径) / error state with gate code
- Result table (columns/rows)
- Collapsible lineage footer: metric@version, entity, table, SQL, executed_at

Usage:
    ```d-ecp-metric
    {
        "trust": "verified",
        "metric_id": "mtr.weekly_sales",
        "columns": ["Store", "value"],
        "rows": [[1, 222402808.85]],
        "row_count": 45,
        "sql": "SELECT Store, SUM(Weekly_Sales) AS value FROM walmart_sales GROUP BY Store",
        "lineage": {"metric_id": "mtr.weekly_sales", "metric_version": 1,
                    "entity_id": "ent.store", "table": "walmart_sales",
                    "datasource_id": 1, "executed_at": "..."}
    }
    ```

Error shape (gate rejection):
    ```d-ecp-metric
    {"trust": "none", "metric_id": "mtr.x", "error": "...", "code": "PAYLOAD_INVALID"}
    ```
"""

from typing import Any, Dict, Optional

from derisk.vis import Vis


class DeriskEcpMetric(Vis):
    """ECP metric query visualization component (trust protocol aware)."""

    @classmethod
    def vis_tag(cls) -> str:
        return "d-ecp-metric"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        columns = kwargs.get("columns")
        rows = kwargs.get("rows")
        # executor 返回 dict 行({"col": val}),前端表格统一按数组行渲染
        # (与 d-sql-query 契约一致);此处归一,两种输入都兼容。
        if columns and rows and isinstance(rows[0], dict):
            rows = [[row.get(c) for c in columns] for row in rows]
        result: Dict[str, Any] = {
            "trust": kwargs.get("trust", "none"),
            "metric_id": kwargs.get("metric_id", ""),
        }
        # 成功字段
        for key in ("columns", "rows", "row_count", "sql", "lineage"):
            value = rows if key == "rows" else kwargs.get(key)
            if value is not None:
                result[key] = value
        # 回忆标记(resolution cache 命中重放)
        if kwargs.get("cache_hit"):
            result["cache_hit"] = True
        # 失败字段
        for key in ("error", "code"):
            if kwargs.get(key) is not None:
                result[key] = kwargs[key]
        return result

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self.sync_generate_param(**kwargs)
