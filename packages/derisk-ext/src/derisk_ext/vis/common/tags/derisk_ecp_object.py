"""ECP Semantic Object Detail VIS Component.

Renders get_semantic_object result: object header (type badge + id + version +
status) + key payload fields + collapsible full payload JSON.

Usage:
    ```d-ecp-object
    {
        "id": "mtr.weekly_sales",
        "version": 1,
        "type": "metric",
        "status": "confirmed",
        "payload": {"name": "周销售额", "entity": "ent.store",
                    "expression": "SUM(Weekly_Sales)", ...}
    }
    ```

Error shape:
    ```d-ecp-object
    {"error": "对象 x 不存在或未确认"}
    ```
"""

from typing import Any, Dict, Optional

from derisk.vis import Vis


class DeriskEcpObject(Vis):
    """ECP semantic object detail visualization component."""

    @classmethod
    def vis_tag(cls) -> str:
        return "d-ecp-object"

    def sync_generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        result: Dict[str, Any] = {
            "id": kwargs.get("id", ""),
            "version": kwargs.get("version"),
            "type": kwargs.get("type", ""),
            "status": kwargs.get("status", ""),
            "payload": kwargs.get("payload") or {},
        }
        if kwargs.get("error") is not None:
            result["error"] = kwargs["error"]
        return result

    async def generate_param(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self.sync_generate_param(**kwargs)
