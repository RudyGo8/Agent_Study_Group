#!/usr/bin/env python3
"""
验证对话历史持久化的测试脚本
"""

import os

from _bootstrap import add_project_root

add_project_root()

from dotenv import load_dotenv
from agent import ContextAwareAgent, ContextMode
import json

# 加载环境变量
load_dotenv()

def test_conversation_history():
    """测试对话历史在多个任务之间持久保存"""
    print("🧪 Testing Conversation History Persistence")
    print("=" * 50)
    
    # 获取 API Key（用任一可用的提供商）
    api_key = (
        os.getenv("ARK_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("MOONSHOT_API_KEY")
        or os.getenv("SILICONFLOW_API_KEY")
    )
    provider = (
        "doubao"
        if os.getenv("ARK_API_KEY")
        else (
            "dashscope"
            if os.getenv("DASHSCOPE_API_KEY")
            else ("kimi" if os.getenv("MOONSHOT_API_KEY") else "siliconflow")
        )
    )
    
    if not api_key:
        print("❌ No API key found. Please set one of:")
        print("  - ARK_API_KEY")
        print("  - DASHSCOPE_API_KEY")
        print("  - MOONSHOT_API_KEY")
        print("  - SILICONFLOW_API_KEY")
        return False
    
    print(f"Using provider: {provider}")
    print("-" * 50)
    
    try:
        # 创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider=provider,
            context_mode=ContextMode.FULL,
            verbose=False
        )
        
        # 测试 1：第一轮查询
        print("\n📝 Test 1: First query")
        query1 = "Remember that my favorite number is 42. What is 10 + 5?"
        result1 = agent.execute_task(query1)
        print(f"Query: {query1}")
        print(f"Response: {result1.get('final_answer', 'No answer')}")
        
        # 检查对话历史
        print(f"\n📚 Conversation history after first query:")
        print(f"  Total messages: {len(agent.conversation_history)}")

        # 打印各消息的角色
        for i, msg in enumerate(agent.conversation_history):
            role = msg.get('role', 'unknown')
            content_preview = str(msg.get('content', ''))[:50] + "..." if len(str(msg.get('content', ''))) > 50 else str(msg.get('content', ''))
            print(f"  Message {i}: Role={role}, Content={content_preview}")
        
        # 测试 2：引用第一轮的第二轮查询
        print("\n📝 Test 2: Second query (should remember context)")
        query2 = "What was my favorite number that I mentioned earlier?"
        result2 = agent.execute_task(query2)
        print(f"Query: {query2}")
        print(f"Response: {result2.get('final_answer', 'No answer')}")
        
        # 检查响应中是否提到 42
        if "42" in str(result2.get('final_answer', '')):
            print("✅ SUCCESS: Agent remembered the favorite number from conversation history!")
        else:
            print("⚠️  WARNING: Agent might not have remembered the number. Check response above.")
        
        # 检查对话历史的增长
        print(f"\n📚 Conversation history after second query:")
        print(f"  Total messages: {len(agent.conversation_history)}")
        
        # 测试 3：验证系统提示词未被修改
        print("\n📝 Test 3: Verify system prompt remains unchanged")
        system_prompt = agent.conversation_history[0].get('content', '')
        if "favorite number" not in system_prompt and "42" not in system_prompt:
            print("✅ SUCCESS: System prompt remains unchanged!")
        else:
            print("❌ FAILURE: System prompt was modified!")
        
        # 测试 4：重置并验证历史已清空
        print("\n📝 Test 4: Test reset functionality")
        agent.reset()
        print(f"  Messages after reset: {len(agent.conversation_history)}")
        
        if len(agent.conversation_history) == 1 and agent.conversation_history[0]['role'] == 'system':
            print("✅ SUCCESS: Reset properly cleared history and kept system prompt!")
        else:
            print("❌ FAILURE: Reset did not work correctly!")
        
        # 测试 5：重置后的新对话
        print("\n📝 Test 5: New conversation after reset")
        query3 = "What was my favorite number?"
        result3 = agent.execute_task(query3)
        print(f"Query: {query3}")
        print(f"Response: {result3.get('final_answer', 'No answer')}")
        
        if "42" not in str(result3.get('final_answer', '')) and "don't" in str(result3.get('final_answer', '').lower()):
            print("✅ SUCCESS: Agent correctly doesn't remember after reset!")
        else:
            print("⚠️  Check if agent properly forgot the previous conversation")
        
        print("\n" + "=" * 50)
        print("Conversation history tests complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_conversation_history()
    exit(0 if success else 1)
