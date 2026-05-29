"""POST /api/agent/cancel 联动 Hermes POST /v1/runs/{id}/stop（路线第三步）。"""

from __future__ import annotations

from unittest.mock import patch

from backend.routers.agent import AgentCancelBody, agent_cancel
from backend.services.agent_run_registry import bind_hermes_run, register


@patch("backend.routers.agent.settings")
@patch("backend.routers.agent.stop_hermes_run")
def test_agent_cancel_stops_bound_hermes_run(mock_stop, mock_settings):
    mock_settings.hermes_configured = True
    mock_stop.return_value = True
    register("og-cancel-1")
    bind_hermes_run("og-cancel-1", "run_hermes_xyz")

    out = agent_cancel(AgentCancelBody(run_id="og-cancel-1"))

    mock_stop.assert_called_once_with("run_hermes_xyz")
    assert out["cancelled"] is True
    assert out["hermes_run_stopping"] is True
