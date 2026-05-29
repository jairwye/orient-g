"""diagnose_hermes 暴露 capabilities（路线第四步）。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.hermes_settings import diagnose_hermes


@patch("backend.services.hermes_settings.settings")
@patch("backend.services.hermes_settings.fetch_hermes_capabilities")
def test_diagnose_includes_capabilities_when_configured(mock_fetch, mock_settings):
    mock_settings.hermes_enabled = True
    mock_settings.hermes_base_url = "http://127.0.0.1:8642"
    mock_settings.hermes_configured = True
    mock_settings.hermes_dev_mock = False
    mock_settings.hermes_agent_kb_prefetch = True
    mock_settings.hermes_agent_kb_synthesize = True
    mock_settings.hermes_agent_kb_fast_path = False
    mock_settings.hermes_agent_route_default = "hermes_lite"
    mock_settings.hermes_agent_kb_ask_budget_lite = 1
    mock_settings.hermes_agent_simple_query_fast = True
    mock_settings.hermes_agent_stream = True
    mock_settings.hermes_agent_use_runs_api = False
    mock_fetch.return_value = {
        "run_events_sse": True,
        "run_stop": True,
        "run_submission": True,
        "tool_progress_events": True,
    }

    d = diagnose_hermes()

    assert d["hermes_configured"] is True
    assert d["hermes_capabilities"]["run_events_sse"] is True
    assert d["hermes_runs_api_ready"] is True
