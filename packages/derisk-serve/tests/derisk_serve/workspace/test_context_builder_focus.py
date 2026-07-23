"""Tests for focus_artifact_id loading in build_workspace_context (new snapshot)."""
from unittest.mock import MagicMock, patch

from derisk_serve.workspace.agent_tools.context_builder import build_workspace_context


def _mock_workspace_service():
    ws = MagicMock()
    ws.get_by_id.return_value = MagicMock(
        id=1, workspace_code="ws1", name="SRE", scenario_type="sre",
        default_agent_app_code="chat_normal",
    )
    return ws


def _system_app_with(art_service):
    """system_app whose get_component returns ws service / artifact service / empty-list others."""
    system_app = MagicMock()

    def get_component(name, cls=None):
        if name == "serve_workspace_service":
            return _mock_workspace_service()
        if name == "serve_artifact_service":
            return art_service
        svc = MagicMock()
        svc.list_tasks.return_value = []
        svc.list_playbooks.return_value = []
        return svc

    system_app.get_component.side_effect = get_component
    return system_app


def test_focus_artifact_loaded_into_snapshot():
    art = MagicMock(id=42, title="周报", type="report", content_text="正文")
    art_service = MagicMock()
    art_service.get_by_id.return_value = art
    system_app = _system_app_with(art_service)

    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mock_mat:
        mock_mat.return_value = MagicMock(dynamic_resources=[], extra_agents=[])
        ctx = build_workspace_context(system_app, workspace_id=1, focus_artifact_id=42)

    assert ctx.focused_artifact is art
    art_service.get_by_id.assert_called_once_with(42)


def test_focus_artifact_failure_degrades_to_none():
    art_service = MagicMock()
    art_service.get_by_id.side_effect = Exception("boom")
    system_app = _system_app_with(art_service)

    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mock_mat:
        mock_mat.return_value = MagicMock(dynamic_resources=[], extra_agents=[])
        ctx = build_workspace_context(system_app, workspace_id=1, focus_artifact_id=999)

    assert ctx.focused_artifact is None


def test_no_focus_artifact_when_omitted():
    art_service = MagicMock()
    system_app = _system_app_with(art_service)

    with patch(
        "derisk_serve.workspace.agent_tools.context_builder.materialize_resources"
    ) as mock_mat:
        mock_mat.return_value = MagicMock(dynamic_resources=[], extra_agents=[])
        ctx = build_workspace_context(system_app, workspace_id=1)

    assert ctx.focused_artifact is None
    art_service.get_by_id.assert_not_called()
