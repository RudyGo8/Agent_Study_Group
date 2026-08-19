#!/usr/bin/env python3
"""
验证缓存 token 能从 Kimi API 响应中被正确解析的测试脚本
"""

import os
import sys
from _bootstrap import add_project_root

add_project_root()

from agent import KVCacheAgent, KVCacheMode

def test_cached_tokens():
    """验证缓存 token 从 API 响应中被正确解析"""
    
    # 获取 API key
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        print("❌ Please set MOONSHOT_API_KEY environment variable")
        sys.exit(1)
    
    print("🔍 Testing Cached Tokens Parsing")
    print("="*60)
    
    # 需要几轮迭代的简单任务
    task = "Find Python files in chapter1/context directory and tell me how many there are."
    
    print(f"Task: {task}")
    print("-"*40)
    
    # 用正确实现运行（应能命中缓存）
    print("\nRunning agent with CORRECT implementation...")
    agent = KVCacheAgent(
        api_key=api_key,
        mode=KVCacheMode.CORRECT,
        root_dir="../..",
        verbose=True  # 开启 verbose 以查看 token 日志
    )
    
    result = agent.execute_task(task, max_iterations=5)
    metrics = result["metrics"]
    
    print("\n" + "="*60)
    print("📊 Cache Token Results:")
    print(f"  • Total iterations: {result['iterations']}")
    print(f"  • Cached tokens accumulated: {metrics.cached_tokens}")
    print(f"  • Cache hits: {metrics.cache_hits}")
    print(f"  • Cache misses: {metrics.cache_misses}")
    
    # 查看每次迭代的 TTFT
    if metrics.ttft_per_iteration:
        print(f"\n  • TTFT per iteration:")
        for i, ttft in enumerate(metrics.ttft_per_iteration, 1):
            status = "🔴 No cache" if i == 1 else "🟢 With cache"
            print(f"      Iteration {i}: {ttft:.3f}s {status}")
    
    # 验证缓存是否生效
    print("\n✅ Verification:")
    if metrics.cached_tokens > 0:
        print(f"  ✓ Cached tokens detected: {metrics.cached_tokens}")
    else:
        print(f"  ⚠️ No cached tokens detected - cache may not be working")
    
    if len(metrics.ttft_per_iteration) > 1:
        first_ttft = metrics.ttft_per_iteration[0]
        second_ttft = metrics.ttft_per_iteration[1]
        if second_ttft < first_ttft * 0.8:  # 至少改善 20%
            print(f"  ✓ TTFT improved from {first_ttft:.3f}s to {second_ttft:.3f}s")
        else:
            print(f"  ⚠️ TTFT did not improve significantly")
    
    print("\n💡 Note: Kimi API should return cached_tokens in the usage object")
    print("   starting from the second iteration when context is stable.")

if __name__ == "__main__":
    test_cached_tokens()
