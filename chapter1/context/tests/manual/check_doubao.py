#!/usr/bin/env python3
"""
Doubao 提供商的快速测试
"""

import os

from _bootstrap import add_project_root

add_project_root()

from agent import ContextAwareAgent, ContextMode

def test_doubao():
    """用简单任务测试 Doubao 提供商"""
    
    print("\n" + "="*60)
    print("🧪 DOUBAO PROVIDER TEST")
    print("="*60)
    
    # 检查 API Key
    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        print("❌ ARK_API_KEY not found. Please set it to test Doubao provider.")
        print("   export ARK_API_KEY=your_key_here")
        return
    
    print("✅ ARK API key found")
    
    # 用 Doubao 提供商创建 Agent
    try:
        agent = ContextAwareAgent(api_key, ContextMode.FULL, provider="doubao")
        print(f"✅ Agent created with Doubao provider")
        print(f"   Model: {agent.model}")
        print(f"   Base URL: {agent.client.base_url}")
        
        # 简单测试任务（尽量省 token）
        print("\n📝 Running simple test task...")
        task = "Calculate: What is 15 + 27? Provide FINAL ANSWER with the result."
        
        result = agent.execute_task(task, max_iterations=3)
        
        if result.get('success'):
            print("✅ Task executed successfully!")
            if result.get('final_answer'):
                print(f"   Answer: {result['final_answer'][:100]}...")
        else:
            print(f"⚠️ Task did not complete successfully")
            if result.get('error'):
                print(f"   Error: {result['error']}")
        
        print(f"\n📊 Execution stats:")
        print(f"   Iterations: {result.get('iterations', 0)}")
        print(f"   Tool calls: {len(result['trajectory'].tool_calls)}")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\nNote: Make sure your ARK_API_KEY is valid and has access to the doubao model.")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    test_doubao()
