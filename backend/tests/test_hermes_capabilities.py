"""Hermes GET /v1/capabilities 探测（路线第四步）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.services.hermes_client import (
    fetch_hermes_capabilities,
    hermes_capabilities_support_runs,
    invalidate_hermes_capabilities_cache,
    parse_hermes_capabilities,
)


def test_parse_hermes_capabilities_features():
    raw = {
        "object": "hermes.api_server.capabilities",
        "features": {
            "chat_completions_streaming": True,
            "run_events_sse": True,
            "run_stop": True,
            "tool_progress_events": True,
        },
    }
    caps = parse_hermes_capabilities(raw)
    assert caps["chat_completions_streaming"] is True
    assert caps["run_events_sse"] is True


def test_hermes_capabilities_support_runs():
    assert hermes_capabilities_support_runs(
        {"run_events_sse": True, "run_stop": True, "run_submission": True}
    )
    assert not hermes_capabilities_support_runs({"run_events_sse": False, "run_stop": True})


@patch("backend.services.hermes_client.settings")
@patch("backend.services.hermes_client.httpx.Client")
def test_fetch_hermes_capabilities_cached(mock_client_cls, mock_settings):
    invalidate_hermes_capabilities_cache()
    mock_settings.hermes_configured = True
    mock_settings.hermes_base_url = "http://127.0.0.1:8642"
    mock_settings.hermes_internal_token = "tok"

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "features": {"run_events_sse": True, "run_stop": True, "run_submission": True},
    }
    mock_client_cls.return_value.__enter__.return_value.get.return_value = resp

    a = fetch_hermes_capabilities()
    b = fetch_hermes_capabilities()
    assert a["run_events_sse"] is True
    assert mock_client_cls.return_value.__enter__.return_value.get.call_count == 1
    assert b is a
