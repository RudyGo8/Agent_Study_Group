#!/usr/bin/env python3
"""
上下文感知 Agent 的测试脚本
验证安装与基础功能
"""

from agent import ContextAwareAgent, ContextMode, ToolRegistry
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestToolRegistry(unittest.TestCase):
    """测试工具注册表的各个函数"""

    def test_calculator(self):
        """测试计算器工具"""
        tools = ToolRegistry()

        # 基础算术
        result = tools.calculate("2 + 2")
        self.assertEqual(result["result"], 4)

        # 复杂表达式
        result = tools.calculate("(10 * 5) + (20 / 4)")
        self.assertEqual(result["result"], 55.0)

        # 带数学函数
        result = tools.calculate("sqrt(16) + abs(-5)")
        self.assertEqual(result["result"], 9.0)

    def test_currency_converter(self):
        """测试货币换算工具"""
        tools = ToolRegistry()

        # USD 换算成 EUR
        result = tools.convert_currency(100, "USD", "EUR")
        self.assertIn("converted_amount", result)
        self.assertIn("exchange_rate", result)
        self.assertGreater(result["converted_amount"], 0)

        # 货币符号归一化（US$、S$、A$、C$、$）
        result_us = tools.convert_currency(100, "US$", "EUR")
        self.assertEqual(result_us["from_currency"], "USD")
        self.assertEqual(result_us["converted_amount"], 92.0)

        result_s = tools.convert_currency(100, "S$", "USD")
        self.assertEqual(result_s["from_currency"], "SGD")
        self.assertIn("converted_amount", result_s)

        result_a = tools.convert_currency(100, "A$", "USD")
        self.assertEqual(result_a["from_currency"], "AUD")
        self.assertIn("converted_amount", result_a)

        result_c = tools.convert_currency(100, "C$", "USD")
        self.assertEqual(result_c["from_currency"], "CAD")
        self.assertIn("converted_amount", result_c)
        # 无效货币
        result = tools.convert_currency(100, "XXX", "YYY")
        self.assertIn("error", result)
        result_invalid_s = tools.convert_currency(100, "S$INVALID", "USD")
        self.assertIn("error", result_invalid_s)

    def test_convert_currency_string_and_formatted_amounts(self):
        """
        验证 convert_currency 能接受字符串和带格式的数字金额。

        LLM 的工具调用常把数字参数传成字符串（如 "100"、"$1,000.00"）。
        以前传字符串会在浮点除法时抛 TypeError。本测试断言数字字符串和
        带格式货币字符串都能正确换算，以锁定该行为、防止回归。
        """
        tools = ToolRegistry()
        result_str = tools.convert_currency("100", "USD", "EUR")
        self.assertEqual(result_str["converted_amount"], 92.0)
        self.assertEqual(result_str["original_amount"], 100.0)

        result_formatted = tools.convert_currency("$1,000.00", "USD", "EUR")
        self.assertEqual(result_formatted["converted_amount"], 920.0)
        self.assertEqual(result_formatted["original_amount"], 1000.0)

        result_us_dollar = tools.convert_currency("US$100", "USD", "EUR")
        self.assertEqual(result_us_dollar["converted_amount"], 92.0)
        self.assertEqual(result_us_dollar["original_amount"], 100.0)

        result_currency_code = tools.convert_currency("USD$1,000", "USD$", "EUR")
        self.assertEqual(result_currency_code["converted_amount"], 920.0)
        self.assertEqual(result_currency_code["original_amount"], 1000.0)

        result_comma_large = tools.convert_currency("1,234,567.89", "USD", "EUR")
        self.assertEqual(result_comma_large["original_amount"], 1234567.89)

        result_euro_sym = tools.convert_currency("€ 500.25", "EUR", "USD")
        self.assertIn("converted_amount", result_euro_sym)

        result_invalid_str = tools.convert_currency("invalid_str", "USD", "EUR")
        self.assertIn("error", result_invalid_str)
    
    def test_pdf_parser_structure(self):
        """测试 PDF 解析器的结构（不依赖真实 PDF）"""
        tools = ToolRegistry()

        # 用无效 URL 测试（应优雅处理而不是崩溃）
        result = tools.parse_pdf("http://invalid-url-for-testing.com/test.pdf")
        self.assertIn("error", result)


class TestContextModes(unittest.TestCase):
    """测试不同的上下文模式"""

    @patch.dict('os.environ', {'SILICONFLOW_API_KEY': 'test_key'})
    def setUp(self):
        """准备测试夹具"""
        self.api_key = "test_key"

    def test_context_mode_initialization(self):
        """测试用不同上下文模式初始化 Agent"""
        for mode in ContextMode:
            agent = ContextAwareAgent(self.api_key, mode)
            self.assertEqual(agent.context_mode, mode)
            self.assertEqual(agent.trajectory.context_mode, mode)
    
    def test_message_preparation_by_mode(self):
        """消融作用在真正发给模型的消息列表上（_prepare_messages_for_api）"""

        def prepared(mode):
            agent = ContextAwareAgent(self.api_key, mode)
            # 模拟 execute_task 已运行一轮后的历史形态：
            # system + user 任务 + assistant 决策 + tool 结果 + 新 user 消息
            agent.conversation_history += [
                {"role": "user", "content": "task"},
                {
                    "role": "assistant",
                    "content": "plan",
                    "reasoning_content": "thinking",
                    "tool_calls": [],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "4"},
                {"role": "user", "content": "go on"},
            ]
            return agent._prepare_messages_for_api()

        # Full 模式发送完整轨迹
        full = prepared(ContextMode.FULL)
        self.assertEqual(
            [m["role"] for m in full],
            ["system", "user", "assistant", "tool", "user"],
        )
        # 保留思考过程
        self.assertEqual(full[2]["reasoning_content"], "thinking")

        # No history 模式只保留静态系统提示词和最新用户任务
        no_history = prepared(ContextMode.NO_HISTORY)
        self.assertEqual([m["role"] for m in no_history], ["system", "user"])

    def test_no_reasoning_strips_reasoning_content(self):
        """No reasoning 模式在消息写回历史前剥离 reasoning_content"""
        agent = ContextAwareAgent(self.api_key, ContextMode.NO_REASONING)
        message = SimpleNamespace(
            model_dump=lambda: {
                "role": "assistant",
                "content": "ok",
                "reasoning_content": "secret",
            }
        )
        msg = agent._prepare_assistant_message(message)
        self.assertNotIn("reasoning_content", msg)
        self.assertEqual(msg["content"], "ok")


class TestAblationScenarios(unittest.TestCase):
    """测试消融场景"""

    def test_tool_execution(self):
        """测试工具执行"""
        agent = ContextAwareAgent("test_key", ContextMode.FULL)

        # 测试计算器执行
        result = agent._execute_tool("calculate", {"expression": "2 + 2"})
        self.assertEqual(result["result"], 4)

        # 测试未知工具
        result = agent._execute_tool("unknown_tool", {})
        self.assertIn("error", result)

    def test_trajectory_reset(self):
        """测试轨迹重置"""
        agent = ContextAwareAgent("test_key", ContextMode.FULL)

        # 向轨迹添加一些数据
        agent.trajectory.reasoning_steps.append("Test step")
        agent.trajectory.tool_calls.append(
            MagicMock(tool_name="test", arguments={})
        )

        # 重置
        agent.reset()

        # 检查是否已清空
        self.assertEqual(len(agent.trajectory.reasoning_steps), 0)
        self.assertEqual(len(agent.trajectory.tool_calls), 0)
        self.assertEqual(agent.trajectory.context_mode, ContextMode.FULL)


def run_integration_test():
    """对真实提供商跑一个简单的集成测试（需要 API Key）。"""
    import os

    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("⚠️ Skipping integration test (no API key found)")
        print("Set SILICONFLOW_API_KEY to run integration tests")
        return False

    agent = ContextAwareAgent(api_key, ContextMode.FULL)
    simple_task = "Calculate: What is 15% of $2500? Then convert the result to EUR."
    print(f"\nTest task: {simple_task}")

    try:
        result = agent.execute_task(simple_task, max_iterations=3)
        print("\n✅ Integration test completed!")
        print(f"Completed: {result.get('completed', False)}")
        print(f"Tool calls: {len(result['trajectory'].tool_calls)}")

        if result.get('final_answer'):
            print(f"Answer preview: {result['final_answer'][:100]}...")

        return True
    except Exception as e:
        print(f"❌ Integration test failed: {str(e)}")
        return False


if __name__ == "__main__":
    # 单元测试；如需真实 API 集成测试，显式调用 run_integration_test()
    unittest.main(verbosity=2)
