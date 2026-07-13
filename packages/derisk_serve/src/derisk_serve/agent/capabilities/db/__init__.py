"""DB capability(serve 层) —— 自管目录(RFC-005)。

DB 工具连 serve 服务(spec_service/connector),放 serve 层避免 core→serve 反向依赖。
resource/executor 的纯 core 鸭子类型在 derisk.agent.capabilities.db;
本 serve 层放工具 + 与 serve 服务的桥接。

工具:tools/(execute_sql 等,设 capability_id="db")。
"""

from .tools import register_db_tools_capability  # noqa: F401

__all__ = ["register_db_tools_capability"]


def register(registry) -> None:
    from .tools import register_db_tools_capability
    register_db_tools_capability(registry)