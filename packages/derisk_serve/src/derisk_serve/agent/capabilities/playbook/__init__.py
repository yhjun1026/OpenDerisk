"""Playbook capability —— 剧本能力自管目录(RFC-005,serve 层)。

PlaybookResource 已是 ResourceProtocol(import 已用 core interface)。
连 serve PlaybookService(查 DB playbook 声明),故归 serve 层。

本目录逻辑归位 capability 自管体系:导出 PlaybookResource + register_wrappers
注册双轨 wrapper(PlaybookResource 本身已是 ResourceProtocol,facade 直识别,
无需谓词;此处保 register_wrappers 统一入口占位)。

工具(build_playbook_tools)实现暂留 playbook/resource/(连 serve service),
物理迁移为后续清理。
"""

__all__ = ["PlaybookResource"]


def register(registry) -> None:
    pass


def register_wrappers(facade) -> None:
    """Playbook 已是 ResourceProtocol,facade 直识别(isinstance 命中)。
    无 legacy 包装需求,占位以符合 capability 目录约定。"""
    pass


def __getattr__(name):
    """延迟导出 PlaybookResource(避免 serve 不可用时 import 失败)。"""
    if name == "PlaybookResource":
        from derisk_serve.playbook.resource.playbook_resource import PlaybookResource
        return PlaybookResource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")