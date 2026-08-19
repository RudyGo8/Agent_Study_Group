"""Web Search Agent 测试套件共用的 pytest fixtures。"""

import json
import socket
from types import SimpleNamespace

import pytest

PROVIDER_ENV_VARS = (
    "MOONSHOT_API_KEY",
    "KIMI_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
)


@pytest.fixture(autouse=True)
def isolate_provider_environment(monkeypatch):
    """把开发者凭据和提供商覆盖配置排除在每个测试之外。"""
    for variable in PROVIDER_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """单元测试若意外发起网络连接，立即快速失败。"""

    def deny_network(*args, **kwargs):
        raise AssertionError("Unit tests must not access the external network")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)


@pytest.fixture
def make_tool_call():
    """构造一个最小的 SDK 形态工具调用对象，用于模拟模型回复。"""

    def factory(
        *,
        name="web_search",
        arguments=None,
        call_id="call-1",
    ):
        payload = arguments if arguments is not None else {"query": "example"}
        return SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(
                name=name,
                arguments=json.dumps(payload, ensure_ascii=False),
            ),
        )

    return factory


@pytest.fixture
def make_choice():
    """构造一个最小的 SDK 形态对话 choice 对象，用于确定性的 Agent 测试。"""

    def factory(
        *,
        finish_reason="stop",
        content="",
        reasoning_content=None,
        tool_calls=None,
    ):
        return SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=list(tool_calls or []),
            ),
        )

    return factory
