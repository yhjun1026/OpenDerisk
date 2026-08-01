"""ECP 自动 miss 学习 cron —— 让飞轮全自动运转(人只守 confirm 闸门)。

设计:
- 懒注册:execute_raw_sql 记录 fallback miss 后调用 ensure_auto_learn_cron,
  只有真正产生过 miss 的工作空间才会有学习任务(无 miss 不注册,零噪音)
- 幂等:job_id 固定 ecp-auto-learn-{ws},已存在则跳过
- 内容:每日 04:00 派提案 Agent(AGENT_TURN)自学——调 get_miss_report →
  对照已确认目录/收件箱 → 只为高频且确实缺失的概念 propose_semantic。
  去重与价值判断由提案 Agent(LLM)做,比机械阈值更准
- 安全:提案只进收件箱(status=proposed),confirm 人工闸门不变;
  注册失败静默,不阻塞查询路径
"""

import logging
from typing import Optional

from ..config import DEFAULT_WORKSPACE_ID

logger = logging.getLogger(__name__)

_JOB_PREFIX = "ecp-auto-learn"

_AUTO_LEARN_MESSAGE = """[自动 miss 学习] 工作空间 {ws}:
1. 调用 get_miss_report(min_count=2) 查看按频次聚类的未覆盖查询
2. 对照已确认目录(search_semantics)与收件箱已有提案,只为"高频且目录确实没有的概念"用 propose_semantic 提案
3. 已有概念不要重复提案;没有值得提案的内容就直接结束
4. 提案只进收件箱,不影响任何查询(人工 confirm 后生效)"""


async def ensure_auto_learn_cron(workspace_id: Optional[str] = None) -> None:
    """幂等注册工作空间级自动 miss 学习 cron(每日 04:00)。失败静默。"""
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    try:
        from derisk._private.config import Config

        system_app = Config().SYSTEM_APP
        if system_app is None:
            return
    except Exception:  # noqa: BLE001
        return
    try:
        from ..models.models import WorkspaceConfigDao

        cfg = WorkspaceConfigDao().get(ws)
        agent_id = getattr(cfg, "proposal_agent_id", None) if cfg else None
        if not agent_id:
            return  # 未配置提案 Agent 的工作空间不自动学习
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ecp-auto-learn] workspace config unavailable: {e}")
        return
    try:
        from derisk.cron.types import (
            CronJobCreate,
            CronPayload,
            CronSchedule,
            PayloadKind,
            ScheduleKind,
            SessionMode,
        )
        from derisk_serve.cron.config import SERVE_SERVICE_COMPONENT_NAME
        from derisk_serve.cron.service.service import Service as CronService

        cron = system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, CronService)
        job_id = f"{_JOB_PREFIX}-{ws}"
        if await cron.get_job(job_id) is not None:
            return
        await cron.add_job(
            CronJobCreate(
                id=job_id,
                name=f"ECP Auto-Learn for {ws}",
                description="每日自动 miss 学习:聚类未覆盖问题 → 提案进收件箱(人只守 confirm)",
                enabled=True,
                schedule=CronSchedule(
                    kind=ScheduleKind.CRON, expr="0 4 * * *", tz="Asia/Shanghai"
                ),
                payload=CronPayload(
                    kind=PayloadKind.AGENT_TURN,
                    message=_AUTO_LEARN_MESSAGE.format(ws=ws),
                    agent_id=agent_id,
                    session_mode=SessionMode.ISOLATED,
                    timeout_seconds=1800,
                ),
            )
        )
        logger.info(f"[ecp-auto-learn] registered cron {job_id} (0 4 * * *)")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[ecp-auto-learn] register cron failed (non-blocking): {e}")
