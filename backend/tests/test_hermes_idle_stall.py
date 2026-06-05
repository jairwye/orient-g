from backend.services.hermes_client import hermes_idle_stall_seconds


def test_lite_idle_stall_allows_long_mcp_rounds():
    assert hermes_idle_stall_seconds(orientg_route="hermes_lite", read_timeout=600) == 480.0


def test_full_idle_stall_capped():
    assert hermes_idle_stall_seconds(orientg_route="hermes_full", read_timeout=600) == 300.0


def test_unknown_route_short_stall():
    assert hermes_idle_stall_seconds(orientg_route="", read_timeout=300) == 60.0
