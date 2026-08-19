#!/usr/bin/env python3
"""
演示对话历史持久化的脚本
"""

import os

from _bootstrap import add_project_root

add_project_root()

from dotenv import load_dotenv
from agent import ContextAwareAgent, ContextMode

# 加载环境变量
load_dotenv()

def main():
    # 获取 API Key（用任一可用的提供商）
    if os.getenv("ARK_API_KEY"):
        api_key, provider = os.getenv("ARK_API_KEY"), "doubao"
    elif os.getenv("DASHSCOPE_API_KEY"):
        api_key, provider = os.getenv("DASHSCOPE_API_KEY"), "dashscope"
    elif os.getenv("MOONSHOT_API_KEY"):
        api_key, provider = os.getenv("MOONSHOT_API_KEY"), "kimi"
    elif os.getenv("DEEPSEEK_API_KEY"):
        api_key, provider = os.getenv("DEEPSEEK_API_KEY"), "deepseek"
    elif os.getenv("SILICONFLOW_API_KEY"):
        api_key, provider = os.getenv("SILICONFLOW_API_KEY"), "siliconflow"
    else:
        api_key, provider = None, None
    
    if not api_key:
        print("❌ No API key found. Please set one of:")
        print("  - ARK_API_KEY")
        print("  - DASHSCOPE_API_KEY")
        print("  - MOONSHOT_API_KEY")
        print("  - DEEPSEEK_API_KEY")
        print("  - SILICONFLOW_API_KEY")
        return
    
    print("🎭 Conversation History Demo")
    print("=" * 50)
    print(f"Provider: {provider.upper()}")
    print("-" * 50)
    
    # 创建 Agent
    agent = ContextAwareAgent(
        api_key=api_key,
        provider=provider,
        context_mode=ContextMode.FULL,
        verbose=False
    )
    
    # 对话 1：设定上下文
    print("\n💬 Turn 1: Setting context...")
    result = agent.execute_task("My name is Alice and I have a budget of $5,000. What is 20% of my budget?")
    print(f"Agent: {result.get('final_answer', 'No answer')}")
    
    # 对话 2：引用之前的上下文
    print("\n💬 Turn 2: Referencing previous context...")
    result = agent.execute_task("Convert that 20% amount to EUR please.")
    print(f"Agent: {result.get('final_answer', 'No answer')}")
    
    # 对话 3：回忆信息
    print("\n💬 Turn 3: Recalling information...")
    result = agent.execute_task("What was my name and total budget that I mentioned?")
    print(f"Agent: {result.get('final_answer', 'No answer')}")
    
    print("\n" + "-" * 50)
    print(f"📊 Final Statistics:")
    print(f"  Total messages in history: {len(agent.conversation_history)}")
    print(f"  Total tool calls made: {len(agent.trajectory.tool_calls)}")
    
    # 验证系统提示词未被修改
    system_prompt = agent.conversation_history[0]['content']
    if "Alice" not in system_prompt and "5000" not in system_prompt:
        print("  ✅ System prompt remained unchanged")
    else:
        print("  ❌ System prompt was modified")
    
    print("\n✨ Demo complete!")

if __name__ == "__main__":
    main()
