#!/usr/bin/env python3
"""
验证 Kimi K3 模型集成的快速测试脚本
"""

import os

from _bootstrap import add_project_root

add_project_root()

from dotenv import load_dotenv
from agent import ContextAwareAgent, ContextMode

# 加载环境变量
load_dotenv()

def main():
    # 获取 API Key
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        print("❌ ERROR: MOONSHOT_API_KEY not set")
        print("Please add to your .env file:")
        print("  MOONSHOT_API_KEY=your_api_key_here")
        return
    
    print("🚀 Testing Kimi K3 Model (kimi-k3)")
    print("=" * 50)
    
    try:
        # 用 Kimi 提供商创建 Agent
        agent = ContextAwareAgent(
            api_key=api_key,
            provider="kimi",
            context_mode=ContextMode.FULL,
            verbose=False
        )
        
        print(f"✅ Agent created successfully")
        print(f"   Provider: {agent.provider}")
        print(f"   Model: {agent.model}")
        print(f"   Base URL: {agent.client.base_url}")
        
        # 测试简单查询
        print("\n📝 Testing basic query...")
        query = "What is 2 + 2?"
        response = agent.process(query)
        print(f"   Query: {query}")
        print(f"   Response: {response}")
        
        print("\n✅ Kimi K3 integration is working!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
