"""propose_semantics: AI proposal pipeline for semantic assets (ECP 5.1).

Pluggable proposer registry keyed by asset kind. The DB proposer consumes
learned table specs (Layer 1, unchanged) + sample data and asks the LLM for
entity/metric/relation/dimension candidates, including DISTINCT value label
guesses for dimension columns. All output lands in `proposed` (write rule 1);
nothing here bypasses the confirmation gate.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..api.schemas import GenerateProposalsVO
from ..config import DEFAULT_WORKSPACE_ID, OBJECT_TYPES, STATUS_PROPOSED

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10
_MAX_SAMPLE_ROWS = 3
_MAX_DISTINCT_VALUES = 30

_SYSTEM_PROMPT = """你是企业语义资产分析师。根据数据库表结构规格（table spec）提炼语义资产提案。
【规则】
1. 只输出 JSON，不要输出任何其他文字
2. 所有 id 使用约定前缀：ent.<名称> 实体 / mtr.<名称> 指标 / rel.<a>__<b> 关系 / dim.<名称> 维度
3. 每个提案给出 confidence (0-1) 和 questions（需要人确认的口径疑点，中文）
4. 拿不准的字段口径在 fields 里标 {"meaning": null, "status": "unknown"}
5. 提案是给人确认的候选，宁可少提、不可编造
【输出格式】
{
  "proposals": [
    {"id": "ent.xxx", "obj_type": "entity", "confidence": 0.8,
     "payload": {"name": "中文名", "aliases": ["别名"],
       "binding": {"kind": "db", "table": "表名", "pk": "主键列", "datasource_id": <提示中给出的数据源ID>},
       "authoritative": true, "default_filters": [],
       "fields": {"列名": {"meaning": "含义", "role": "identifier|measure|dimension|time", "unit": "可选"}}},
     "questions": ["口径疑点"]},
    {"id": "mtr.xxx", "obj_type": "metric", "confidence": 0.7,
     "payload": {"name": "中文名", "aliases": [], "entity": "ent.xxx",
       "expression": "SUM(列名)", "extra_filters": [], "grain": ["可下钻的维度列名/维度名"], "unit": "CNY"},
     "questions": []},
    {"id": "rel.a__b", "obj_type": "relation", "confidence": 0.6,
     "payload": {"from": "ent.a", "to": "ent.b",
       "path": "表1.列 = 表2.列", "cardinality": "n:1"},
     "questions": []},
    {"id": "dim.xxx", "obj_type": "dimension", "confidence": 0.7,
     "payload": {"name": "中文名", "entity": "ent.xxx", "column": "列名",
       "values": [{"label": "显示名", "aliases": [], "codes": ["原始值"]}]},
     "questions": []}
  ]
}"""


class SemanticsProposer:
    """Base class for asset-kind proposers (plugin interface)."""

    asset_kind: str = ""

    def __init__(self, service):
        self._service = service

    async def generate(self, **kwargs) -> GenerateProposalsVO:
        raise NotImplementedError


class DbSemanticsProposer(SemanticsProposer):
    """Propose semantic objects from a datasource's learned table specs."""

    asset_kind = "db"
    SYSTEM_PROMPT = _SYSTEM_PROMPT

    def __init__(self, service):
        super().__init__(service)
        self._llm_config_cache: Optional[Dict[str, str]] = None

    async def generate(
        self,
        datasource_id: int,
        workspace_id: Optional[str] = None,
        table_names: Optional[List[str]] = None,
        max_tables: int = 50,
        domain_hint: Optional[str] = None,
    ) -> GenerateProposalsVO:
        from derisk_serve.datasource.manages.table_spec_db import TableSpecDao

        ws = workspace_id or DEFAULT_WORKSPACE_ID
        result = GenerateProposalsVO(datasource_id=datasource_id)

        dao = TableSpecDao()
        specs = dao.get_all_by_datasource(datasource_id)
        if table_names:
            wanted = set(table_names)
            specs = [s for s in specs if s.table_name in wanted]
        specs = specs[:max_tables]
        if not specs:
            result.errors.append(
                f"No learned table specs for datasource {datasource_id}; "
                "run schema learning first"
            )
            return result

        # Recall flywheel: proposals build on the confirmed catalog (consistency,
        # no duplicates), not from scratch each time.
        existing_catalog = self._service.catalog(workspace_id=ws)

        distinct_values = await self._sample_distinct_values(datasource_id, specs)

        for i in range(0, len(specs), _BATCH_SIZE):
            batch = specs[i : i + _BATCH_SIZE]
            result.tables_processed += len(batch)
            try:
                proposals = await self._propose_batch(
                    batch, datasource_id, distinct_values,
                    existing_catalog, domain_hint,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[ECP] propose batch failed: {e}")
                result.errors.append(f"batch {i // _BATCH_SIZE}: {e}")
                continue
            for p in proposals:
                try:
                    vo = self._service.propose(
                        object_id=p["id"],
                        obj_type=p["obj_type"],
                        payload=p["payload"],
                        workspace_id=ws,
                        confidence=p.get("confidence"),
                        evidence=p.get("evidence"),
                        created_by="llm",
                        source=f"discovery:ds{datasource_id}",
                    )
                    # 去重命中(返回已有 confirmed VO)不计为新提案
                    if vo.status == STATUS_PROPOSED:
                        result.proposals_created += 1
                        result.proposal_ids.append(p["id"])
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[ECP] proposal write failed {p.get('id')}: {e}")
                    result.errors.append(f"{p.get('id')}: {e}")
        return result

    # ------------------------------------------------------------------ prompt
    def _build_batch_prompt(
        self,
        batch: List[Any],
        datasource_id: int,
        distinct_values: Dict[str, Dict[str, List[str]]],
        existing_catalog: Optional[List[Any]] = None,
        domain_hint: Optional[str] = None,
    ) -> str:
        parts = []
        if domain_hint:
            parts.append(f"【领域背景】\n{domain_hint}\n")
        if existing_catalog:
            lines = [
                f"  {e.id} ({e.obj_type}) {e.name or ''}"
                + (f" 别名:{'/'.join(e.aliases)}" if e.aliases else "")
                for e in existing_catalog[:200]
            ]
            parts.append(
                "【已确认资产目录】（提案必须与之口径一致；已存在的概念不要重复提案，"
                "可为其补充别名或维度值）\n" + "\n".join(lines) + "\n"
            )
        parts.append(f"数据源 ID: {datasource_id}\n")
        for spec in batch:
            columns = _spec_get(spec, "columns", "columns_json") or []
            samples = _spec_get(spec, "sample_data", "sample_data_json") or {}
            fks = _spec_get(spec, "foreign_keys", "foreign_keys_json") or []
            rows = (samples.get("rows") or [])[:_MAX_SAMPLE_ROWS]
            col_lines = []
            for c in columns:
                line = f"    {c.get('name')} {c.get('type')}"
                if c.get("pk"):
                    line += " [PK]"
                if c.get("comment"):
                    line += f"  # {c.get('comment')}"
                table_distinct = distinct_values.get(_spec_attr(spec, "table_name"), {})
                if c.get("name") in table_distinct:
                    line += f"  DISTINCT值: {table_distinct[c['name']]}"
                col_lines.append(line)
            fk_lines = [
                f"    {fk.get('constrained_columns')} -> "
                f"{fk.get('referred_table')}.{fk.get('referred_columns')}"
                for fk in fks
            ]
            parts.append(
                f"表: {_spec_attr(spec, 'table_name')}  注释: {_spec_attr(spec, 'table_comment') or '无'}  "
                f"行数: {_spec_attr(spec, 'row_count') or '未知'}\n"
                f"  列:\n" + ("\n".join(col_lines) or "    (无)") + "\n"
                f"  外键:\n" + ("\n".join(fk_lines) or "    (无)") + "\n"
                f"  采样行: {json.dumps(rows, ensure_ascii=False, default=str)[:800]}\n"
            )
        parts.append(
            "\n请为以上表提炼语义资产提案：\n"
            "- entity：业务实体（判断哪张是权威表并给理由放进 questions）\n"
            "- metric：可从 measure 列聚合出的核心业务指标（expression 用真实列名）\n"
            "- relation：表间 join 路径（优先依据外键，非外键的放进 questions）\n"
            "- dimension：低基数字段的维度值字典（label 用业务语言猜测，codes 用真实值）"
        )
        return "\n".join(parts)

    async def _propose_batch(
        self,
        batch: List[Any],
        datasource_id: int,
        distinct_values: Dict[str, Dict[str, List[str]]],
        existing_catalog: Optional[List[Any]] = None,
        domain_hint: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        prompt = self._build_batch_prompt(
            batch, datasource_id, distinct_values, existing_catalog, domain_hint
        )
        text = await self._call_llm(prompt)
        if not text:
            raise RuntimeError("LLM unavailable or returned empty")
        proposals = self._parse_proposals(text)
        known_tables = {s.table_name for s in batch}
        return self._validate(proposals, known_tables, datasource_id=datasource_id)

    # -------------------------------------------------------------- validation
    @staticmethod
    def _parse_proposals(text: str) -> List[Dict[str, Any]]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        proposals = data.get("proposals")
        return proposals if isinstance(proposals, list) else []

    @staticmethod
    def _validate(
        proposals: List[Dict[str, Any]],
        known_tables: set,
        datasource_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Deterministic validation: drop proposals that violate hard rules.

        结构校验走 contracts 单一事实来源(proposal 级);entity 的 binding 在此
        补齐 kind/datasource_id(proposer 上下文可知,LLM 易漏)。
        """
        from .contracts import validate_payload

        valid = []
        for p in proposals:
            obj_type = p.get("obj_type")
            object_id = p.get("id")
            payload = p.get("payload")
            if not object_id or obj_type not in OBJECT_TYPES or not isinstance(
                payload, dict
            ):
                continue
            if obj_type == "entity":
                binding = payload.get("binding") or {}
                table = binding.get("table")
                if table not in known_tables:
                    continue
                binding["kind"] = "db"
                if datasource_id is not None:
                    binding.setdefault("datasource_id", datasource_id)
                payload["binding"] = binding
            problems = validate_payload(obj_type, payload, level="proposal")
            if problems:
                logger.info(
                    f"[ECP] proposal {object_id} dropped by contract: {problems}"
                )
                continue
            valid.append(p)
        return valid

    # ------------------------------------------------------- DISTINCT sampling
    async def _sample_distinct_values(
        self, datasource_id: int, specs: List[Any]
    ) -> Dict[str, Dict[str, List[str]]]:
        """SELECT DISTINCT low-cardinality text columns (dimension candidates).

        Best-effort: any failure returns an empty dict and labels are left to
        the LLM's sample-data guesses.
        """
        result: Dict[str, Dict[str, List[str]]] = {}
        try:
            from derisk._private.config import Config
            from derisk_serve.datasource.manages.connect_config_db import (
                ConnectConfigDao,
            )

            config = ConnectConfigDao().get_one({"id": datasource_id})
            db_name = getattr(config, "db_name", None)
            if not db_name:
                return result
            connector = Config().local_db_manager.get_connector(db_name)
        except Exception as e:  # noqa: BLE001
            logger.info(f"[ECP] connector unavailable for ds{datasource_id}: {e}")
            return result

        def _run(sql: str):
            return connector.run(sql)

        for spec in specs:
            columns = _spec_get(spec, "columns", "columns_json") or []
            row_count = _spec_attr(spec, "row_count") or 0
            table_name = _spec_attr(spec, "table_name")
            for c in columns:
                col_type = (c.get("type") or "").lower()
                if c.get("pk") or not any(
                    t in col_type for t in ("char", "text", "enum")
                ):
                    continue
                if row_count and row_count > 10_000_000:
                    continue
                sql = (
                    f"SELECT DISTINCT {c['name']} FROM {table_name} "
                    f"LIMIT {_MAX_DISTINCT_VALUES + 1}"
                )
                try:
                    rows = await asyncio.to_thread(_run, sql)
                except Exception:  # noqa: BLE001
                    continue
                values = [str(r[0]) for r in rows if r and r[0] is not None]
                if 0 < len(values) <= _MAX_DISTINCT_VALUES:
                    result.setdefault(table_name, {})[c["name"]] = values
        return result

    # -------------------------------------------------------------- LLM client
    def _get_llm_config(self) -> Optional[Dict[str, str]]:
        """Lazy-init LLM API config from ModelConfigCache (same pattern as
        SchemaLearningService)."""
        if self._llm_config_cache is not None:
            return self._llm_config_cache or None
        try:
            from derisk.agent.util.llm.model_config_cache import ModelConfigCache

            all_models = ModelConfigCache.get_all_models()
            if not all_models:
                self._llm_config_cache = {}
                return None
            config = ModelConfigCache.get_config(all_models[0]) or {}
            base_url = (config.get("base_url") or config.get("api_base") or "").rstrip(
                "/"
            )
            if not base_url:
                self._llm_config_cache = {}
                return None
            if "/v1" not in base_url:
                base_url += "/v1"
            self._llm_config_cache = {
                "base_url": base_url,
                "api_key": config.get("api_key", ""),
                "model": config.get("model") or all_models[0],
            }
            return self._llm_config_cache
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[ECP] LLM config init failed: {e}")
            self._llm_config_cache = {}
            return None

    async def _call_llm(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
        import httpx

        config = self._get_llm_config()
        if not config:
            return None
        headers = {"Content-Type": "application/json"}
        if config["api_key"]:
            headers["Authorization"] = f"Bearer {config['api_key']}"
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{config['base_url']}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                choices = resp.json().get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    return text.strip() if text else None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[ECP] LLM call failed: {e}")
        return None


def _loads(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw


def _spec_get(spec: Any, parsed_key: str, json_key: str) -> Any:
    """Read a table-spec field from a to_response dict (``parsed_key``, already
    parsed) or an entity (``json_key``, JSON string). Returns the parsed value."""
    if isinstance(spec, dict):
        return spec.get(parsed_key)
    return _loads(getattr(spec, json_key, None))


def _spec_attr(spec: Any, key: str) -> Any:
    """Read a plain attribute from a dict or entity spec."""
    if isinstance(spec, dict):
        return spec.get(key)
    return getattr(spec, key, None)


_DOC_SYSTEM_PROMPT = """你是企业语义资产分析师。根据文档原文提炼可信知识口径提案。
【规则】
1. 只输出 JSON，不要输出任何其他文字
2. 对象类型：claim（事实陈述）/ terminology（术语定义）/ policy（带条件的规则条款）
3. 每条必须满足：
   - source_quote 为原文**逐字摘录**（不许改写一个字，系统会做原文子串校验）
   - binding.doc_id 用给定文档 id，binding.space 用给定空间 slug
   - binding.anchor 给章节定位（如 sec:3 或 sec:3#p2，按文档结构估计）
   - text/definition/rule 是对 quote 的口径化提炼（可概括，但不得超出 quote 含义）
4. id 约定：clm.<名> claim / trm.<名> terminology / pol.<名> policy
5. 每个提案给出 confidence (0-1) 和 questions（需要人确认的口径疑点，中文）
6. 拿不准的条目不要提，宁少勿造
【输出格式】
{
  "proposals": [
    {"id": "clm.xxx", "obj_type": "claim", "confidence": 0.8,
     "payload": {"name": "简短名", "text": "口径化陈述",
       "binding": {"kind": "doc", "space": "<空间>", "doc_id": "<文档id>", "anchor": "sec:X#pY"},
       "source_quote": "原文逐字摘录"},
     "questions": []},
    {"id": "trm.xxx", "obj_type": "terminology", "confidence": 0.7,
     "payload": {"name": "术语", "aliases": ["别名"], "definition": "权威定义",
       "binding": {"kind": "doc", "space": "<空间>", "doc_id": "<文档id>", "anchor": "sec:X"},
       "source_quote": "原文逐字摘录"},
     "questions": []},
    {"id": "pol.xxx", "obj_type": "policy", "confidence": 0.7,
     "payload": {"name": "规则名", "condition": "适用条件", "rule": "规则内容",
       "binding": {"kind": "doc", "space": "<空间>", "doc_id": "<文档id>", "anchor": "sec:X"},
       "source_quote": "原文逐字摘录"},
     "questions": []}
  ]
}"""


class DocSemanticsProposer(DbSemanticsProposer):
    """Propose canon entries (claim/terminology/policy) from knowledge docs.

    与 DbSemanticsProposer 对称(复用 LLM 配置/调用/JSON 解析),文档侧精髓是
    ④ quote ∈ 原文的代码子串校验——LLM 可以写错提炼文本,但摘录必须是原文
    真实子串,防幻觉从 LLM 自觉变成代码保证(ECP-unstructured-design §6.1)。
    """

    asset_kind = "doc"
    SYSTEM_PROMPT = _DOC_SYSTEM_PROMPT

    async def generate(
        self,
        space_slug: str,
        workspace_id: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        max_docs: int = 20,
        domain_hint: Optional[str] = None,
    ) -> GenerateProposalsVO:
        ws = workspace_id or DEFAULT_WORKSPACE_ID
        result = GenerateProposalsVO(datasource_id=0)

        # ① 取空间文档(verbat 原文块)
        docs = await self._load_space_docs(space_slug, doc_ids, max_docs, result)
        if not docs:
            if not result.errors:
                result.errors.append(f"空间 {space_slug} 无可用文档")
            return result

        existing_catalog = self._service.catalog(workspace_id=ws)

        for doc_id, text in docs.items():
            try:
                proposals = await self._propose_doc(
                    space_slug, doc_id, text, existing_catalog, domain_hint
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[ECP] doc propose failed {doc_id}: {e}")
                result.errors.append(f"{doc_id}: {e}")
                continue
            # ④ 确定性校验:契约 proposal 级 + quote ∈ 原文(防幻觉硬闸)
            valid = self._validate_doc_proposals(proposals, space_slug, doc_id, text)
            for p in valid:
                try:
                    self._service.propose(
                        object_id=p["id"],
                        obj_type=p["obj_type"],
                        payload=p["payload"],
                        workspace_id=ws,
                        confidence=p.get("confidence"),
                        evidence=p.get("evidence"),
                        created_by="llm",
                        source=f"discovery:doc:{space_slug}",
                    )
                    result.proposals_created += 1
                    result.proposal_ids.append(p["id"])
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[ECP] proposal write failed {p.get('id')}: {e}")
                    result.errors.append(f"{p.get('id')}: {e}")
            result.tables_processed += 1  # 复用字段计处理文档数
        return result

    # ------------------------------------------------------------------ 文档加载
    @staticmethod
    async def _load_space_docs(
        space_slug: str,
        doc_ids: Optional[List[str]],
        max_docs: int,
        result: GenerateProposalsVO,
    ) -> Dict[str, str]:
        """{doc_id(verbat_id): 原文文本}。"""
        docs: Dict[str, str] = {}
        try:
            from derisk._private.config import Config

            system_app = Config().SYSTEM_APP
            from derisk_serve.knowledge.config import (
                SERVE_SERVICE_COMPONENT_NAME as KNOWLEDGE_SERVICE,
            )
            from derisk_serve.knowledge.service.service import (
                Service as KnowledgeService,
            )

            ks = system_app.get_component(KNOWLEDGE_SERVICE, KnowledgeService)
            vault = await ks.get_vault(space_slug)
            if doc_ids:
                for did in doc_ids[:max_docs]:
                    v = await vault.verbat_get(did)
                    if v is not None:
                        content = getattr(v, "content", None) or getattr(v, "text", None)
                        if content:
                            docs[did] = content
            else:
                page = await vault.verbat_list(limit=max_docs)
                items = getattr(page, "items", page) or []
                for v in items:
                    vid = getattr(v, "id", None) or getattr(v, "verbat_id", None)
                    content = getattr(v, "content", None) or getattr(v, "text", None)
                    if vid and content:
                        docs[vid] = content
        except Exception as e:  # noqa: BLE001
            result.errors.append(f"加载空间 {space_slug} 文档失败: {e}")
        return docs

    # ------------------------------------------------------------------ 提案生成
    async def _propose_doc(
        self,
        space_slug: str,
        doc_id: str,
        text: str,
        existing_catalog: Optional[List[Any]],
        domain_hint: Optional[str],
    ) -> List[Dict[str, Any]]:
        parts = []
        if domain_hint:
            parts.append(f"【领域背景】\n{domain_hint}\n")
        if existing_catalog:
            lines = [
                f"  {e.id} ({e.obj_type}) {e.name or ''}"
                for e in existing_catalog[:200]
            ]
            parts.append(
                "【已确认资产目录】(提案必须与之口径一致;已存在的概念不要重复提案)\n"
                + "\n".join(lines)
                + "\n"
            )
        parts.append(f"空间: {space_slug}  文档 id: {doc_id}\n")
        parts.append(f"【文档原文】\n{text[:6000]}\n")
        parts.append(
            "\n请为该文档提炼可信知识口径提案(claim/terminology/policy),"
            "source_quote 必须逐字摘自上面的原文。"
        )
        llm_text = await self._call_llm("\n".join(parts))
        if not llm_text:
            raise RuntimeError("LLM unavailable or returned empty")
        return self._parse_proposals(llm_text)

    @staticmethod
    def _validate_doc_proposals(
        proposals: List[Dict[str, Any]],
        space_slug: str,
        doc_id: str,
        original_text: str,
    ) -> List[Dict[str, Any]]:
        """确定性校验:结构 + 契约(proposal 级) + quote ∈ 原文(防幻觉硬闸)。"""
        from .contracts import validate_payload

        norm_original = " ".join(original_text.split())
        valid = []
        for p in proposals:
            obj_type = p.get("obj_type")
            object_id = p.get("id")
            payload = p.get("payload")
            if obj_type not in ("claim", "terminology", "policy"):
                continue
            if not object_id or not isinstance(payload, dict):
                continue
            # 结构修正:绑定到本文档(防 LLM 臆造 doc_id)
            binding = dict(payload.get("binding") or {})
            binding["kind"] = "doc"
            binding["space"] = space_slug
            binding["doc_id"] = doc_id
            payload["binding"] = binding
            # 契约 proposal 级
            if validate_payload(obj_type, payload, level="proposal"):
                continue
            # quote ∈ 原文(空白归一后子串)
            quote = payload.get("source_quote") or ""
            if " ".join(quote.split()) not in norm_original:
                logger.info(
                    f"[ECP] proposal {object_id} dropped: quote not in original"
                )
                continue
            valid.append(p)
        return valid


# Proposer registry: new asset kinds register here (API proposer in P3).
PROPOSERS: Dict[str, type] = {
    DbSemanticsProposer.asset_kind: DbSemanticsProposer,
    DocSemanticsProposer.asset_kind: DocSemanticsProposer,
}
