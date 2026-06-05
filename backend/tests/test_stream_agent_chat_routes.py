"""stream_agent_chat 在配置 + capabilities 满足时走 Runs API。"""

from __future__ import annotations

from unittest.mock import patch

from backend.services.hermes_client import stream_agent_chat


@patch("backend.services.hermes_client.settings")
@patch("backend.services.hermes_client.fetch_hermes_capabilities")
@patch("backend.services.hermes_client.stream_agent_chat_runs")
def test_stream_delegates_to_runs_when_enabled(mock_runs, mock_caps, mock_settings):
    mock_settings.hermes_configured = True
    mock_settings.hermes_agent_use_runs_api = True
    mock_caps.return_value = {
        "run_events_sse": True,
        "run_stop": True,
        "run_submission": True,
    }

    def _fake_runs(**kwargs):
        yield {"type": "status", "message": "runs", "step": "hermes_runs"}
        yield {
            "type": "done",
            "reply": "ok",
            "hermes_stream_mode": "runs",
            "hermes_used": True,
        }

    mock_runs.side_effect = _fake_runs

    events = list(
        stream_agent_chat(
            messages=[{"role": "user", "content": "hi"}],
            username="u",
            user_token="tok",
        )
    )
    mock_runs.assert_called_once()
    assert any(e.get("hermes_stream_mode") == "runs" for e in events)


@patch("backend.services.hermes_client.settings")
@patch("backend.services.hermes_client.fetch_hermes_capabilities")
@patch("backend.services.hermes_client.stream_agent_chat_runs")
def test_stream_auto_runs_for_hermes_full_without_env_flag(mock_runs, mock_caps, mock_settings):
    mock_settings.hermes_configured = True
    mock_settings.hermes_agent_use_runs_api = False
    mock_caps.return_value = {
        "run_events_sse": True,
        "run_stop": True,
        "run_submission": True,
    }

    def _fake_runs(**kwargs):
        yield {"type": "done", "reply": "ok", "hermes_stream_mode": "runs"}

    mock_runs.side_effect = _fake_runs

    events = list(
        stream_agent_chat(
            messages=[{"role": "user", "content": "hi"}],
            username="u",
            user_token="tok",
            orientg_route="hermes_full",
        )
    )
    mock_runs.assert_called_once()
    assert any(e.get("step") == "hermes_runs_mode" for e in events)


@patch("backend.services.hermes_client.settings")
@patch("backend.services.hermes_client.fetch_hermes_capabilities")
@patch("backend.services.hermes_client.stream_agent_chat_runs")
def test_stream_stays_on_chat_completions_when_runs_disabled(mock_runs, mock_caps, mock_settings):
    mock_settings.hermes_configured = False
    mock_settings.hermes_agent_use_runs_api = True
    events = list(
        stream_agent_chat(
            messages=[{"role": "user", "content": "hi"}],
            username="u",
            user_token="tok",
        )
    )
    mock_runs.assert_not_called()
    assert events[0]["type"] == "error"
