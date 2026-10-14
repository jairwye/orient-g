from backend.services.hermes_client import hermes_idle_stall_seconds


def test_lite_idle_stall_allows_long_mcp_rounds():
    assert hermes_idle_stall_seconds(orientg_route="hermes_lite", read_timeout=600) == 480.0


def test_full_idle_stall_avoids_premature_og_recovery():
    """深度档勿过早 stall→tier2_error_recovery 推算成稿；floor≥600、cap≤900。"""
    assert hermes_idle_stall_seconds(orientg_route="hermes_full", read_timeout=600) == 600.0
    assert hermes_idle_stall_seconds(orientg_route="hermes_full", read_timeout=1200) == 900.0


def test_unknown_route_short_stall():
    assert hermes_idle_stall_seconds(orientg_route="", read_timeout=300) == 60.0
