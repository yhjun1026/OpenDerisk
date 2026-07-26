"""Tests for _build_user_query: user query should be just the task goal.

skills/resources are injected as agent tools; deliverables/distill are rendered
into the system prompt. The user query must NOT repeat them, otherwise the task
input is cluttered with irrelevant content.
"""
from unittest.mock import MagicMock

from derisk_serve.playbook.runtime import _build_user_query


def _playbook():
    pb = MagicMock()
    pb.name = "周报剧本"
    return pb


def _task(title="排查 CPU 飙高", description=None):
    t = MagicMock()
    t.title = title
    t.description = description
    t.id = 10
    return t


def _workspace():
    ws = MagicMock()
    ws.name = "Ops空间"
    ws.scenario_type = "data_ops"
    return ws


DECL = {
    "skills": ["db_query_skill"],
    "context": {"resources": [{"type": "datasource", "ref": "prod_db"}]},
    "deliverables": [{"type": "report", "title": "数据运营周报"}],
    "distill": {"forced": True, "produce": []},
}


def test_user_query_is_just_task_goal():
    q = _build_user_query(_playbook(), _task(), _workspace(), DECL)
    assert q == "排查 CPU 飙高"


def test_user_query_includes_description():
    q = _build_user_query(_playbook(), _task("排查 CPU", "重点关注 prod-db-01"), _workspace(), DECL)
    assert "排查 CPU" in q
    assert "重点关注 prod-db-01" in q


def test_user_query_excludes_playbook_skills_resources_deliverables():
    q = _build_user_query(_playbook(), _task(), _workspace(), DECL)
    assert "周报剧本" not in q          # playbook name
    assert "db_query_skill" not in q    # skills (injected as tools)
    assert "prod_db" not in q           # resources (injected as tools)
    assert "数据运营周报" not in q       # deliverables (in system prompt)
    assert "Execute playbook" not in q
    assert "Required skills" not in q
    assert "Expected deliverables" not in q


def test_user_query_fallback_when_no_title():
    q = _build_user_query(_playbook(), _task(title=None), _workspace(), DECL)
    assert "Execute playbook" in q
