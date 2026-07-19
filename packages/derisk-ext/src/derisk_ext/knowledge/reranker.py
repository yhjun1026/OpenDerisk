"""Lightweight reranker for hybrid doc search (RFC 004 extension point).

derisk has no wired reranker-model runtime (the `RerankEmbeddings` ABC in
derisk.core.interface.embeddings exists but no provider is registered for
the knowledge stack), so this module provides an LLM-based reranker built
on the same model infrastructure the ingest pipeline uses
(`ModelConfigCache` + `AIWrapper`).

Extension point: `BaseVaultFS.configure_reranker()` accepts any object
with `async rerank(query, hits) -> hits`, so a real cross-encoder
reranker (bge-reranker etc.) can be mounted later without touching
VaultFS code.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Protocol

from derisk.knowledge.types import DocHit

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """Reranker contract consumed by BaseVaultFS hybrid search."""

    async def rerank(self, query: str, hits: List[DocHit]) -> List[DocHit]:
        """Return `hits` re-ordered by relevance to `query`."""
        ...


class LLMReranker:
    """Score-and-resort reranker backed by a single LLM call.

    Sends the query plus numbered candidates (title / path / snippet) and
    asks for a 0-10 relevance score per candidate. On any failure (no
    model registered, bad JSON, network error) the original order is
    preserved — rerank is best-effort and never breaks search.
    """

    _PROMPT = (
        "你是检索结果重排器。给定查询和若干候选文档，为每个候选打出 0-10 "
        "的相关性分数（10 = 完全回答查询）。只输出 JSON 对象，格式：\n"
        '{"scores": {"1": 8, "2": 3, ...}}\n'
        "不要输出任何解释性文字。"
    )

    def __init__(self, model: str):
        self._model = model

    async def rerank(self, query: str, hits: List[DocHit]) -> List[DocHit]:
        if len(hits) <= 1:
            return hits
        try:
            scores = await self._score(query, hits)
        except Exception as e:
            logger.warning("LLMReranker scoring failed (%s): %s", self._model, e)
            return hits
        if not scores:
            return hits
        # Stable re-sort: scored hits first by LLM score desc, unscored
        # keep their relative RRF order at the tail.
        indexed = list(enumerate(hits))
        indexed.sort(
            key=lambda kv: (-scores.get(kv[0], -1.0), kv[0])
        )
        reranked: List[DocHit] = []
        for original_idx, hit in indexed:
            score = scores.get(original_idx)
            if score is not None:
                hit = DocHit(
                    document_id=hit.document_id,
                    path=hit.path,
                    title=hit.title,
                    type=hit.type,
                    score=float(score),
                    snippet=hit.snippet,
                    verbats=hit.verbats,
                )
            reranked.append(hit)
        return reranked

    async def _score(self, query: str, hits: List[DocHit]) -> Dict[int, float]:
        candidates = []
        for i, h in enumerate(hits, start=1):
            snippet = (h.snippet or "").replace("\n", " ")[:200]
            candidates.append(f"[{i}] {h.title} ({h.path})\n{snippet}")
        user_prompt = (
            f"查询: {query}\n\n候选文档:\n" + "\n\n".join(candidates)
        )
        text = await self._call_llm(user_prompt)
        return self._parse_scores(text, len(hits))

    def _parse_scores(self, text: str, n: int) -> Dict[int, float]:
        """Parse the {"scores": {"1": 8, ...}} payload. Tolerant of
        markdown fences and trailing prose around the JSON object."""
        if not text:
            return {}
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except (ValueError, TypeError):
            return {}
        raw = data.get("scores") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return {}
        scores: Dict[int, float] = {}
        for key, value in raw.items():
            try:
                idx = int(key) - 1  # candidates are numbered from 1
                scores[idx] = float(value)
            except (TypeError, ValueError):
                continue
        return {i: s for i, s in scores.items() if 0 <= i < n}

    async def _call_llm(self, user_prompt: str) -> str:
        """One-shot LLM call via the Agent model stack (same pattern as
        the ingest pipeline's `_call_llm`, minus the usage ledger —
        rerank is a read-path concern, not ingest)."""
        from derisk.agent.core.llm_config import AgentLLMConfig
        from derisk.agent.util.llm.llm_client import AIWrapper
        from derisk.agent.util.llm.model_config_cache import ModelConfigCache

        model = self._model
        if not model:
            all_models = ModelConfigCache.get_all_models()
            if not all_models:
                raise RuntimeError("No LLM models registered for rerank")
            model = all_models[0]

        model_config = ModelConfigCache.get_config(model)
        agent_llm_config: Optional[AgentLLMConfig] = None
        if model_config:
            try:
                agent_llm_config = AgentLLMConfig.from_dict(model_config)
            except Exception as e:
                logger.warning("Parse model config for %s failed: %s", model, e)

        ai_wrapper = AIWrapper(llm_config=agent_llm_config)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        result_text = ""
        async for result in ai_wrapper.create(
            messages=messages, llm_model=model, stream_out=False
        ):
            if result and result.content:
                result_text += result.content
        return result_text


__all__ = ["Reranker", "LLMReranker"]
