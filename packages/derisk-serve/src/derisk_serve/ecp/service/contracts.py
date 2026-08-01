"""ECP payload 契约 —— 写入协议与消费协议的单一事实来源。

问题背景(对话 52ea9cf2 / e3cfdbd4):propose_semantic 工具的 payload 是裸
``{"type": "object"}``,confirm 晋升无校验,executor(DbBindingExecutor)对
payload 结构有硬期望——三方各自漂移,导致"已确认但不可执行"的对象入库,
execute_metric_query 全线 PAYLOAD_INVALID,可信查询路径名存实亡。

协议设计:
- 本模块是四类对象(payload schema)的**唯一定义点**。写入路径(propose
  normalize / confirm 晋升门禁)与消费路径(executor 运行时门禁)都调这里的
  同一组函数,物理上不可能再漂移。
- 两级校验:
  - ``level="proposal"``:结构最小集(payload 是 dict、id 必填字段存在)。
    提案是候选,允许不完整(如 relation path 待定)。
  - ``level="executable"``:可执行全集。confirm 晋升(机器背书人类确认)
    与 executor 运行前都必须过这一级。
- ``normalize_payload``:机械升级已知的扁平/旧形态(扁平台账字段→嵌套
  binding、单数 code→codes 列表),写入时自愈,不改语义的部分不碰。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ 契约定义
# level="executable" 时各类型的必填约束。message 与 GateError 文案对齐(中文)。
_REQUIRED_EXECUTABLE: Dict[str, List[tuple]] = {
    "entity": [
        # (dotted_path, problem_message)
        ("binding", "实体缺少 binding 定义"),
        ("binding.table", "实体 binding 缺少 table"),
    ],
    "metric": [
        ("entity", "指标缺少 entity 绑定"),
        ("expression", "指标缺少冻结 expression"),
    ],
    "dimension": [
        ("column", "维度缺少 column 定义"),
    ],
    "relation": [
        ("from", "relation 缺少 from 端点"),
        ("to", "relation 缺少 to 端点"),
    ],
    # ---- 文档类(ECP-unstructured-design P0) ----
    "claim": [
        ("text", "claim 缺少陈述文本"),
        ("binding", "claim 缺少 binding"),
        ("binding.doc_id", "claim binding 缺少 doc_id"),
        ("source_quote", "claim 缺少 source_quote(确认判据)"),
    ],
    "terminology": [
        ("definition", "术语缺少 definition"),
        ("binding", "术语缺少 binding"),
        ("binding.doc_id", "术语 binding 缺少 doc_id"),
    ],
    "policy": [
        ("rule", "policy 缺少 rule"),
        ("binding", "policy 缺少 binding"),
        ("binding.doc_id", "policy binding 缺少 doc_id"),
        ("source_quote", "policy 缺少 source_quote(确认判据)"),
    ],
}

# level="proposal" 时各类型最小必填(候选可以不完整,但标识性字段必须在)。
_REQUIRED_PROPOSAL: Dict[str, List[tuple]] = {
    "entity": [("binding.table", "实体提案至少需 binding.table")],
    "metric": [("expression", "指标提案至少需 expression")],
    "dimension": [("column", "维度提案至少需 column")],
    "relation": [
        ("from", "relation 提案至少需 from"),
        ("to", "relation 提案至少需 to"),
    ],
    # 文档类提案:允许 anchor 待定(confirm 前补齐),但核心内容必须在
    "claim": [("text", "claim 提案至少需 text")],
    "terminology": [("definition", "术语提案至少需 definition")],
    "policy": [("rule", "policy 提案至少需 rule")],
}


def _dig(payload: Dict[str, Any], dotted: str) -> Any:
    cur: Any = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def validate_payload(
    obj_type: str, payload: Any, level: str = "executable"
) -> List[str]:
    """按契约校验 payload,返回问题列表(空=通过)。

    executable 级在 proposal 级之上追加:
    - entity: binding 需含 datasource_id 或 connector(执行取连接用)
    - dimension: values 若存在,每项需 codes 列表(筛选映射用)
    """
    if not isinstance(payload, dict):
        return ["payload 必须是 object"]
    rules = list(_REQUIRED_PROPOSAL.get(obj_type, []))
    if level == "executable":
        rules += [r for r in _REQUIRED_EXECUTABLE.get(obj_type, []) if r not in rules]
    problems = [msg for path, msg in rules if not _dig(payload, path)]
    if level == "executable":
        if obj_type == "entity":
            binding = payload.get("binding") or {}
            if not (binding.get("datasource_id") or binding.get("connector")):
                problems.append("实体 binding 缺少 datasource_id")
        if obj_type == "dimension":
            for v in payload.get("values") or []:
                if not v.get("codes"):
                    problems.append(
                        f"维度值 {v.get('label') or '?'} 缺少 codes 列表"
                    )
    return problems


# ------------------------------------------------------------------ 归一化
def normalize_payload(
    obj_type: str, payload: Any, datasource_id: Optional[int] = None
) -> Dict[str, Any]:
    """把已知的扁平/旧形态机械升级为契约形态(幂等)。不改语义,只做结构搬移。

    - entity: 扁平 table_name/datasource_id → binding{kind,table,datasource_id}
      (datasource_id 参数 > payload 扁平值 > binding 已有值)
    - metric: 扁平 table_name/datasource_id 不搬(归属 entity 的 binding),
      仅确保 grain/extra_filters 是 list
    - dimension: values[].code(单数) → codes(列表);确保 values 是 list
    """
    if not isinstance(payload, dict):
        return payload
    p = dict(payload)

    if obj_type == "entity":
        binding = dict(p.get("binding") or {})
        table = binding.get("table") or p.pop("table_name", None)
        if table:
            binding.setdefault("kind", "db")
            binding["table"] = table
        ds_id = (
            datasource_id
            or p.pop("datasource_id", None)
            or binding.get("datasource_id")
        )
        if ds_id is not None and "datasource_id" not in binding:
            binding["datasource_id"] = ds_id
        pk = binding.get("pk") or p.pop("pk", None)
        if pk:
            binding["pk"] = pk
        if binding:
            p["binding"] = binding

    elif obj_type == "metric":
        for key in ("grain", "extra_filters"):
            if p.get(key) is not None and not isinstance(p[key], list):
                p[key] = [p[key]]

    elif obj_type == "dimension":
        values = p.get("values")
        if isinstance(values, list):
            new_values = []
            for v in values:
                if not isinstance(v, dict):
                    new_values.append(v)
                    continue
                v = dict(v)
                if "codes" not in v and "code" in v:
                    code = v.pop("code")
                    v["codes"] = [str(code)]
                new_values.append(v)
            p["values"] = new_values

    elif obj_type in ("claim", "terminology", "policy"):
        # 文档类归一化:扁平 space/doc_id/anchor/section → binding{kind:doc};
        # quote → source_quote(照 entity binding 归一先例,机械搬移不改语义)
        binding = dict(p.get("binding") or {})
        binding.setdefault("kind", "doc")
        for src_key, dst_key in (
            ("space", "space"),
            ("doc_id", "doc_id"),
            ("doc", "doc_id"),
            ("document", "doc_id"),
            ("anchor", "anchor"),
            ("section", "anchor"),
        ):
            if dst_key not in binding and p.get(src_key) is not None:
                binding[dst_key] = p.pop(src_key)
        if binding.get("doc_id") or binding.get("space"):
            p["binding"] = binding
        if "source_quote" not in p and p.get("quote") is not None:
            p["source_quote"] = p.pop("quote")

    # 通用:entity_bindings(数组) → entity(契约单值字段,取首个)。
    # 提案 agent 常见漂移形态(对话 1ad61a82 学习产物实测)。
    if "entity" not in p and isinstance(p.get("entity_bindings"), list):
        bindings = [b for b in p["entity_bindings"] if isinstance(b, str) and b]
        if bindings:
            p["entity"] = bindings[0]

    return p
