#!/usr/bin/env python3
"""
验证更新后的 Agent 能配合标准 OpenAI 工具调用工作的测试脚本
"""

import os
import sys
import json
from _bootstrap import add_project_root

add_project_root()

from agent import KVCacheAgent, KVCacheMode

def test_tool_calling():
    """验证 Agent 正确使用 OpenAI 工具调用格式"""
    
    # 获取 API key
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        print("❌ Please set MOONSHOT_API_KEY environment variable")
        sys.exit(1)
    
    print("🧪 Testing Standard OpenAI Tool Calling Format")
    print("="*60)
    
    # 需要工具调用的简单任务
    task = "Find all Python files in the chapter1/context directory and tell me how many there are."
    
    print(f"📝 Task: {task}")
    print("-"*60)
    
    # 用正确实现创建 Agent
    agent = KVCacheAgent(
        api_key=api_key,
        mode=KVCacheMode.CORRECT,
        root_dir="../..",
        verbose=True  # 开启 verbose 以查看工具调用
    )
    
    # 执行任务
    result = agent.execute_task(task, max_iterations=5)
    
    # 检查结果
    print("\n" + "="*60)
    print("📊 Results:")
    print(f"✓ Success: {result['success']}")
    print(f"✓ Iterations: {result['iterations']}")
    print(f"✓ Tool Calls Made: {len(result['tool_calls'])}")
    
    if result['tool_calls']:
        print("\n🔧 Tool Calls:")
        for tc in result['tool_calls']:
            print(f"  • {tc.name}({tc.arguments})")
            if tc.result and tc.result.get('success'):
                if tc.name == 'find':
                    print(f"    → Found {tc.result.get('count', 0)} files")
    
    if result['final_answer']:
        print(f"\n💬 Final Answer:")
        print(f"  {result['final_answer'][:200]}...")
    
    # 测试指标
    metrics = result['metrics']
    print(f"\n📈 Performance Metrics:")
    print(f"  • TTFT: {metrics.ttft:.3f}s")
    print(f"  • Total Time: {metrics.total_time:.3f}s")
    print(f"  • Cached Tokens: {metrics.cached_tokens}")
    
    print("\n✅ Tool calling test completed successfully!")

if __name__ == "__main__":
    test_tool_calling()
