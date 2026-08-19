"""
用真实 LLM（Ollama）做并行工具调用的端到端测试。

覆盖：
1. 并行执行的确定性验证：两个各睡 2s 的工具必须经每个 Agent 的工具执行
   路径在约 2s（而非约 4s）内完成。
2. 用真实模型跑书中「温哥华时间 + 天气」示例，覆盖：
   - OllamaNativeAgent.chat / chat_stream（原生工具调用）
   - OllamaOpenAICompatible.chat（OpenAI 兼容端点，原生工具）
   - VLLMToolAgent.chat / chat_stream（OpenAI 兼容的结构化工具调用；
     用 Ollama 的 OpenAI 兼容端点顶替 vLLM 服务端）

在本目录运行:  python3 test_parallel_tools.py
依赖: ollama serve + ollama pull qwen2.5:7b-instruct-q8_0
"""
import json
import logging
import time
from types import SimpleNamespace

from ollama_native import OllamaNativeAgent, OllamaOpenAICompatible
from agent import VLLMToolAgent

logging.basicConfig(level=logging.WARNING)

SLEEP = 2
QUERY = "What time is it in Vancouver and what's the current weather in Vancouver?"
# qwen3:0.6b 是项目默认模型，但原生工具调用不稳定；
# qwen2.5:7b-instruct-q8_0（本地也已拉取）调用工具更可靠。
REAL_MODEL = "qwen2.5:7b-instruct-q8_0"
MAX_ATTEMPTS = 4  # 小模型偶尔会跳过工具调用；需重试


# ---------------------------------------------------------------- 辅助函数

def _sleep_tool(name):
    def fn(tag: str = "") -> dict:
        time.sleep(SLEEP)
        return {"tool": name, "slept": SLEEP, "success": True}
    return fn


SLEEP_SCHEMA = {
    "type": "object",
    "properties": {"tag": {"type": "string", "description": "optional tag"}},
    "required": [],
}


def _register_sleep_tools(registry):
    registry.register_tool("sleep_a", _sleep_tool("sleep_a"), "Sleep tool A", SLEEP_SCHEMA)
    registry.register_tool("sleep_b", _sleep_tool("sleep_b"), "Sleep tool B", SLEEP_SCHEMA)


def _check_parallel(label, elapsed, n=2):
    status = "PARALLEL OK" if elapsed < SLEEP * 1.8 else "NOT PARALLEL"
    print(f"  [{label}] {n} x {SLEEP}s tools finished in {elapsed:.1f}s -> {status}")
    assert elapsed < SLEEP * 1.8, f"{label}: tool calls were not executed in parallel"


# ------------------------------------- 1. 确定性并行验证

def test_native_execute_parallel():
    print("\n== OllamaNativeAgent._execute_tool_calls (sleep tools) ==")
    agent = OllamaNativeAgent(model=REAL_MODEL)
    _register_sleep_tools(agent.tool_registry)
    calls = [
        {"function": {"name": "sleep_a", "arguments": {}}},
        {"function": {"name": "sleep_b", "arguments": {}}},
    ]
    start = time.time()
    results = agent._execute_tool_calls(calls)
    _check_parallel("native _execute_tool_calls", time.time() - start)
    assert all(json.loads(r)["success"] for r in results)


def _make_chunk(text=None, tool_calls=None):
    delta = SimpleNamespace(content=text, tool_calls=tool_calls or [])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_fragment(index, *, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_vllm_stream_parallel():
    print("\n== VLLMToolAgent.chat_stream (fake stream with 2 tool calls) ==")
    agent = VLLMToolAgent(api_base="http://localhost:11434/v1", api_key="ollama")
    _register_sleep_tools(agent.tool_registry)

    state = {"n": 0}

    def fake_create(**kwargs):
        state["n"] += 1
        if state["n"] == 1:
            # 把参数拆到多个分片，并交错两个调用的 index。
            return iter([
                _make_chunk(tool_calls=[
                    _tool_fragment(
                        0, call_id="call_a", name="sleep_a", arguments='{"tag":'
                    ),
                    _tool_fragment(
                        1, call_id="call_b", name="sleep_b", arguments='{"tag":'
                    ),
                ]),
                _make_chunk(tool_calls=[
                    _tool_fragment(0, arguments='"a"}'),
                    _tool_fragment(1, arguments='"b"}'),
                ]),
            ])
        return iter([_make_chunk("done")])

    agent.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    start = time.time()
    events = list(agent.chat_stream("run both sleep tools"))
    elapsed = time.time() - start

    types = [e["type"] for e in events]
    print(f"  event types: {types}")
    assert types.count("tool_call") == 2, f"expected 2 tool_call events: {types}"
    assert types.count("tool_result") == 2, f"expected 2 tool_result events: {types}"
    _check_parallel("vllm chat_stream", elapsed)


# ------------------------------------- 2. 真实模型端到端运行

def test_native_real_model():
    print(f"\n== OllamaNativeAgent.chat (real {REAL_MODEL}) ==")
    agent = OllamaNativeAgent(model=REAL_MODEL)
    response, tool_msgs = "", []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        agent.reset_conversation()
        response = agent.chat(QUERY)
        tool_msgs = [m for m in agent.conversation_history if m.get("role") == "tool"]
        if tool_msgs:
            break
        print(f"  attempt {attempt}: model made no tool call, retrying")
    assistant_tc = [m for m in agent.conversation_history if m.get("tool_calls")]
    batch = len(assistant_tc[0]["tool_calls"]) if assistant_tc else 0
    print(f"  tool calls in one turn: {batch} ({'PARALLEL BATCH' if batch > 1 else 'single'})")
    for m in tool_msgs:
        print(f"    - {m['content'][:120]}")
    print(f"  final response: {response[:300]}")
    assert tool_msgs, "model did not call any tool"

    print(f"\n== OllamaNativeAgent.chat_stream (real {REAL_MODEL}) ==")
    events = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        agent.reset_conversation()
        events = list(agent.chat_stream(QUERY))
        if any(e["type"] == "tool_result" for e in events):
            break
        print(f"  attempt {attempt}: no tool call, retrying")
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    print(f"  tool_call events: {len(tool_calls)}, tool_result events: {len(tool_results)}")
    for e in tool_calls:
        print(f"    - {e['content']['name']}({e['content']['arguments']})")
    final = "".join(e["content"] for e in events if e["type"] == "content")
    print(f"  final content: {final[:300]}")
    assert tool_results, "streaming path produced no tool results"


def test_openai_compat_real_model():
    print(f"\n== OllamaOpenAICompatible.chat (real {REAL_MODEL}) ==")
    agent = OllamaOpenAICompatible(model=REAL_MODEL)
    response, tool_msgs = "", []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        agent.reset_conversation()
        response = agent.chat(QUERY)
        tool_msgs = [m for m in agent.conversation_history if m.get("role") == "tool"]
        if tool_msgs:
            break
        print(f"  attempt {attempt}: model made no tool call, retrying")
    print(f"  tool results in history: {len(tool_msgs)}")
    print(f"  final response: {response[:300]}")
    assert tool_msgs, "model did not call any tool"


def test_vllm_agent_real_model():
    print(f"\n== VLLMToolAgent.chat (real {REAL_MODEL} via OpenAI endpoint) ==")
    agent = VLLMToolAgent(api_base="http://localhost:11434/v1", api_key="ollama")

    # 用 Ollama 的 OpenAI 端点顶替 vLLM 服务端。保留原生
    # tools 负载，让两条 chat 路径都收到结构化 tool_calls。
    real_create = agent.client.chat.completions.create

    def create_structured_mode(**kwargs):
        kwargs["model"] = REAL_MODEL
        return real_create(**kwargs)

    agent.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_structured_mode))
    )

    response, tool_msgs, batch = "", [], 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        agent.reset_conversation()
        # 手工拼接的 XML 格式下，temperature 0.7 采样可能退化成
        # 工具调用死循环；0.3 比较稳定
        response = agent.chat(QUERY, temperature=0.3)
        tool_msgs = [m for m in agent.conversation_history if m.get("name")]
        assistant_tc = [m for m in agent.conversation_history if m.get("tool_calls")]
        batch = len(assistant_tc[0]["tool_calls"]) if assistant_tc else 0
        if tool_msgs and batch <= 10:
            break
        print(f"  attempt {attempt}: no tool call or degenerate run ({batch} calls), retrying")
    print(f"  tool calls in one turn: {batch} ({'PARALLEL BATCH' if batch > 1 else 'single'})")
    for m in tool_msgs:
        print(f"    - {m['name']}: {m['content'][:100]}")
    print(f"  final response: {response[:300]}")
    assert tool_msgs, "model did not emit a structured tool call"

    print(f"\n== VLLMToolAgent.chat_stream (real {REAL_MODEL}) ==")
    events = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        agent.reset_conversation()
        # 手工拼接的 XML 格式下，temperature 0.7 采样可能退化成
        # 工具调用死循环；0.3 比较稳定
        events = list(agent.chat_stream(QUERY, temperature=0.3))
        n_calls = sum(1 for e in events if e["type"] == "tool_call")
        if any(e["type"] == "tool_result" for e in events) and n_calls <= 10:
            break
        print(f"  attempt {attempt}: no tool call or degenerate run ({n_calls} calls), retrying")
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    print(f"  tool_call events: {len(tool_calls)}, tool_result events: {len(tool_results)}")
    for e in tool_calls:
        print(f"    - {e['content']}")
    final = "".join(e["content"] for e in events if e["type"] == "content")
    print(f"  final content: {final[:300]}")
    assert tool_results, "streaming path produced no tool results"


if __name__ == "__main__":
    test_native_execute_parallel()
    test_vllm_stream_parallel()
    test_native_real_model()
    test_openai_compat_real_model()
    test_vllm_agent_real_model()
    print("\nALL TESTS PASSED")
