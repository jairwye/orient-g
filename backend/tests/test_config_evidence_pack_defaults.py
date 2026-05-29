"""Evidence Pack 相关配置默认值（code review C1）。"""

from backend.config import Settings


def test_default_hermes_agent_kb_prefetch_enabled():
    field = Settings.model_fields["hermes_agent_kb_prefetch"]
    assert field.default is True


def test_default_hermes_agent_kb_multi_query_enabled():
    field = Settings.model_fields["hermes_agent_kb_multi_query"]
    assert field.default is True
