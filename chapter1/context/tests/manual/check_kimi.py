#!/usr/bin/env python3
"""
Kimi K3 模型集成的测试脚本
用多种任务测试 Kimi K3 模型（kimi-k3）
"""

import os
import sys

from _bootstrap import add_project_root

add_project_root()

from dotenv import load_dotenv
from agent import ContextAwareAgent, ContextMode
from config import Config

# 加载环境变量
load_dotenv()


def test_basic_conversation():
    """测试基础对话能力"""
    print("\n" + "="*60)
    print("TEST 1: Basic Conversation")
    print("="*60)

    try:
        # 获取 API Key
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            print("❌ ERROR: MOONSHOT_API_KEY not set in environment")
            print("Please set it in your .env file or as environment variable")
            return False

        # 创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider="kimi",
            context_mode=ContextMode.FULL,
            verbose=False
        )
        
        # 测试基础对话
        query = "What is 25 * 4 + 10?"
        print(f"\n📝 Query: {query}")

        response = agent.process(query)
        print(f"\n🤖 Response: {response}")

        # 验证响应包含正确答案
        if "110" in response:
            print("\n✅ Basic conversation test passed!")
            return True
        else:
            print("\n❌ Test failed - incorrect answer")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False


def test_tool_usage():
    """测试工具调用能力"""
    print("\n" + "="*60)
    print("TEST 2: Tool Usage (Calculator)")
    print("="*60)

    try:
        # 获取 API Key
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            print("❌ ERROR: MOONSHOT_API_KEY not set")
            return False

        # 创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider="kimi",
            context_mode=ContextMode.FULL,
            verbose=False
        )

        # 测试需要计算器工具的复杂计算
        query = "Calculate: (123.45 * 67.89) / 12.34 + sqrt(144) - 2^8"
        print(f"\n📝 Query: {query}")

        response = agent.process(query)
        print(f"\n🤖 Response: {response}")

        # 检查是否用到了计算器
        if agent.trajectory.tool_calls:
            print(f"\n🔧 Tools used: {len(agent.trajectory.tool_calls)}")
            for call in agent.trajectory.tool_calls:
                print(f"  - {call.tool_name}: {call.arguments}")
            print("\n✅ Tool usage test passed!")
            return True
        else:
            print("\n⚠️  No tools were used")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False


def test_currency_conversion():
    """测试货币换算工具"""
    print("\n" + "="*60)
    print("TEST 3: Currency Conversion")
    print("="*60)

    try:
        # 获取 API Key
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            print("❌ ERROR: MOONSHOT_API_KEY not set")
            return False

        # 创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider="kimi",
            context_mode=ContextMode.FULL,
            verbose=False
        )

        # 测试货币换算
        query = "Convert 100 USD to EUR and JPY"
        print(f"\n📝 Query: {query}")

        response = agent.process(query)
        print(f"\n🤖 Response: {response}")

        # 检查是否用到了货币换算器
        tool_names = [call.tool_name for call in agent.trajectory.tool_calls]
        if "convert_currency" in tool_names:
            print(f"\n🔧 Currency converter was used")
            print("\n✅ Currency conversion test passed!")
            return True
        else:
            print("\n⚠️  Currency converter was not used")
            return False
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False


def test_model_info():
    """测试并展示模型信息"""
    print("\n" + "="*60)
    print("TEST 4: Model Information")
    print("="*60)

    try:
        # 获取 API Key
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            print("❌ ERROR: MOONSHOT_API_KEY not set")
            return False

        # 创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider="kimi",
            context_mode=ContextMode.FULL,
            verbose=False
        )
        
        print(f"\n📊 Model Configuration:")
        print(f"  Provider: {agent.provider}")
        print(f"  Model: {agent.model}")
        print(f"  Base URL: {agent.client.base_url}")
        print(f"  Context Mode: {agent.context_mode.value}")
        
        # 测试模型自述身份
        query = "What model are you?"
        print(f"\n📝 Query: {query}")
        
        response = agent.process(query)
        print(f"\n🤖 Response: {response}")
        
        print("\n✅ Model info test completed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False


def main():
    """运行全部测试"""
    print("\n" + "="*60)
    print("KIMI K3 MODEL INTEGRATION TEST SUITE")
    print("="*60)
    print("\nModel: kimi-k3")
    print("Provider: Moonshot AI")
    print("API: https://api.moonshot.cn/v1")

    # 检查环境变量
    if not os.getenv("MOONSHOT_API_KEY"):
        print("\n❌ ERROR: MOONSHOT_API_KEY not found in environment")
        print("\nPlease set up your .env file with:")
        print("  MOONSHOT_API_KEY=your_api_key_here")
        print("\nYou can get an API key from: https://platform.moonshot.cn/")
        sys.exit(1)

    # 运行测试
    results = []

    # 测试 1：基础对话
    results.append(("Basic Conversation", test_basic_conversation()))

    # 测试 2：工具调用
    results.append(("Tool Usage", test_tool_usage()))

    # 测试 3：货币换算
    results.append(("Currency Conversion", test_currency_conversion()))

    # 测试 4：模型信息
    results.append(("Model Information", test_model_info()))

    # 汇总
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Kimi K3 integration is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
