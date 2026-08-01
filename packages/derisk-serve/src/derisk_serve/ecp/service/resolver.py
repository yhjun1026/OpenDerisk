"""Resolution cache: normalized question -> frozen tool-call params (ECP 3.1).

The cache is an asset: on hit, the frozen execute_metric_query params are
replayed directly, skipping the whole agent loop (zero cost, zero drift) —
this is also how scheduled reports reproduce identically week over week.
Invalidation happens on confirm/deprecate (service layer).
"""

import logging
import re
from typing import Any, Dict, Optional

from ..models.models import ResolutionCacheDao

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[，。！？、；：,.!?;:\"'“”‘’（）()\[\]【】]")


def normalize_question(question: str) -> str:
    """Normalize a question into a cache key pattern.

    Punctuation is removed entirely (not replaced) so Chinese phrasing
    variants converge; whitespace is collapsed.
    """
    q = _PUNCT_RE.sub("", question.strip().lower())
    return _WS_RE.sub(" ", q).strip()


def lookup(question: str, workspace_id: str) -> Optional[Dict[str, Any]]:
    """Return cached tool-call params for a question, recording the hit."""
    dao = ResolutionCacheDao()
    norm = normalize_question(question)
    entry = dao.get(norm, workspace_id)
    if not entry:
        return None
    dao.record_hit(norm, workspace_id)
    return entry.resolution


def backfill(
    question: str,
    workspace_id: str,
    tool_params: Dict[str, Any],
    validated_by: str = "execution_confirmed",
) -> None:
    """Cache a successful, uncorrected execute_metric_query call's params."""
    ResolutionCacheDao().put(
        normalize_question(question), workspace_id, tool_params, validated_by
    )


def replay(cached: Dict[str, Any]) -> Dict[str, Any]:
    """Replay a cached execute_metric_query call (cache-hit fast path)."""
    from .executor import execute_metric_query

    params = dict(cached.get("params") or {})
    result = execute_metric_query(
        metric_id=params.pop("metric_id"),
        workspace_id=params.pop("workspace_id"),
        group_by=params.pop("group_by", None),
        filters=params.pop("filters", None),
        time_range=params.pop("time", None),
    )
    result["cache_hit"] = True
    return result
