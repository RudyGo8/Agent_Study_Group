"""模型映射与提供商选择的单元测试。"""

import pytest
from config import map_model_to_openrouter, resolve_llm_backend


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("openai/gpt-5.6-luna", "openai/gpt-5.6-luna"),
        ("gpt-5.6-luna", "openai/gpt-5.6-luna"),
        ("o3-mini", "openai/o3-mini"),
        ("claude-sonnet-4.6", "anthropic/claude-sonnet-4.6"),
        ("claude-haiku-4.5", "anthropic/claude-haiku-4.5"),
        ("claude-opus-4.8", "anthropic/claude-opus-4.8"),
        ("kimi-k3", "moonshotai/kimi-k2.6"),
    ],
)
def test_map_model_to_openrouter(model, expected):
    assert map_model_to_openrouter(model) == expected


def test_unknown_model_uses_configured_openrouter_default(monkeypatch):
    """替换是可选行为，供无法发送未映射 id 的调用方使用。"""
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/fallback-model")

    mapped = map_model_to_openrouter("unknown-model", substitute_unknown=True)
    assert mapped == "vendor/fallback-model"


def test_unknown_model_is_kept_when_not_substituting(monkeypatch):
    """因凭据原因改走路由时，仍保留读者指定的模型。"""
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/fallback-model")

    assert map_model_to_openrouter("unknown-model") == "unknown-model"


def test_primary_provider_is_preserved_when_its_key_exists():
    assert resolve_llm_backend(
        "moonshot-key", "https://moonshot.test/v1", "kimi-k3"
    ) == (
        "moonshot-key",
        "https://moonshot.test/v1",
        "kimi-k3",
        False,
    )


def test_openrouter_is_used_when_primary_key_is_missing(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.test/v1")

    assert resolve_llm_backend(None, "https://moonshot.test/v1", "kimi-k3") == (
        "openrouter-key",
        "https://openrouter.test/v1",
        "moonshotai/kimi-k2.6",
        True,
    )


def test_gpt5_prefers_openrouter_when_both_keys_exist(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")

    resolved = resolve_llm_backend(
        "primary-key", "https://primary.test/v1", "gpt-5.6-luna"
    )

    assert resolved == (
        "openrouter-key",
        "https://openrouter.ai/api/v1",
        "openai/gpt-5.6-luna",
        True,
    )


def test_provider_resolution_requires_a_key():
    with pytest.raises(ValueError, match="No API key found"):
        resolve_llm_backend(None, "https://moonshot.test/v1", "kimi-k3")
