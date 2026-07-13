"""Playbook capability —— serve 层自管目录(RFC-005)。

PlaybookResource 已是 ResourceProtocol。连 serve PlaybookService,故归 serve 层。
逻辑归位 capability 体系;工具实现暂留 playbook/resource/(连 serve service)。
"""

import logging

__all__ = ["PlaybookResource"]

log = logging.getLogger(__name__)

try:
    from derisk_serve.playbook.resource.playbook_resource import PlaybookResource
except Exception as _e:  # noqa: BLE001
    log.debug(f"PlaybookResource import skipped: {_e}")
    PlaybookResource = None


def register(registry) -> None:
    pass


def register_wrappers(facade) -> None:
    """Playbook 已是 ResourceProtocol,facade isinstance 命中,无需 legacy 包装。"""
    pass