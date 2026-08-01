"""Confirmed-catalog text builder for agent prompt injection.

Small catalogs (a few hundred objects, ~2-5KB) are injected wholesale — full-
catalog parsing beats embedding retrieval at this scale and is fully
explainable (ECP 5.2). Beyond ServeConfig.catalog_inject_threshold, agents
fall back to the search_semantics tool (L0/L1 layered disclosure switch).
"""

import logging
from typing import Optional

from ..config import DEFAULT_WORKSPACE_ID
from ..models.models import SemanticObjectDao

logger = logging.getLogger(__name__)

BEHAVIOR_GUIDE = """回答数字问题时，区分两条轨道：

【可信轨】已确认概念 → 指标路径
1. 先用 search_semantics / get_semantic_object 找 confirmed 指标
2. 用 execute_metric_query 执行（唯一产出 ✅ 可信数字的路径）

【探索轨】目录未覆盖 → 自由探索（正当且鼓励）
3. 目录没有的概念、开放性的分析角度（分布/相关性/新维度/自定义口径），
   主动用 execute_raw_sql 自由探索——这不是"兜底"，是语义层的侦察兵
4. 探索的数字必须向用户声明为 ⚠️ 未验证口径
5. 探索的 reasoning 参数写清"发现了什么目录没有的概念"（这是飞轮原料，
   会被聚类学习）
6. 探索出有价值且可复用的口径时，用 propose_semantic 提案沉淀
   （只进收件箱，不影响查询；确认后下次同类问题就能走可信轨）

【锚定优先】开放性/全面分析也必须先锚定
7. 做全面分析时：目录已确认的指标（见上方目录）必须先用可信轨查出 ✅
   头部数字，再对未覆盖的角度自由探索（⚠️）。探索轨不是全量裸查的
   许可证——能用指标回答的部分，不许绕过指标。

【通用】
8. 概念歧义时用 ask_user 反问，不要猜
9. 目录是起点不是边界：指标查询失败或未覆盖 ≠ 停止分析，转探索轨继续
10. 使用数据分析等技能时以上规则仍然优先：技能教分析方法，
    数据获取路径以本约定为准，技能流程中的取数/SQL 步骤按两轨执行
11. 分析收尾时说明：哪些数字是 ✅ 可信口径，哪些是 ⚠️ 探索发现，
    以及本次探索沉淀了哪些提案（让用户看到语义层在生长）

【文档类问题】(知识空间被 ECP 托管时适用)
12. 事实型问题(制度/条款/定义/标准)：search_semantics 找
    claim/terminology/policy 条目 → query_canon 带引用回答（✅）
13. 目录未覆盖时用 explore_docs 在托管空间自由检索（⚠️ 须声明未验证
    口径）；发现的可信口径用 propose_semantic 提案（必须带
    source_quote 原文摘录和 anchor 定位）
14. 锚定优先同 DB：已确认条目不许绕过；探索检索结果不是可信依据，
    只是提案素材"""

_TYPE_TITLES = {
    "metric": "指标",
    "entity": "实体",
    "dimension": "维度",
    "relation": "关系",
}


def build_catalog_text(workspace_id: Optional[str] = None) -> str:
    """Render the confirmed catalog as compact prompt text (~2-5KB)."""
    entries = SemanticObjectDao().list_catalog(workspace_id or DEFAULT_WORKSPACE_ID)
    if not entries:
        return ""
    by_type: dict = {}
    for e in entries:
        by_type.setdefault(e.obj_type, []).append(e)
    parts = ["【已确认语义目录】"]
    for tp, title in _TYPE_TITLES.items():
        items = by_type.get(tp)
        if not items:
            continue
        lines = []
        for e in items:
            line = f"  {e.id} {e.name or ''}"
            if e.aliases:
                line += f" 别名:{'/'.join(e.aliases)}"
            if e.grain:
                line += f" 粒度:{','.join(e.grain)}"
            lines.append(line)
        parts.append(f"[{title}]\n" + "\n".join(lines))
    return "\n".join(parts)
