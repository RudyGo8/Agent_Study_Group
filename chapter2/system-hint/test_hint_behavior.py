#!/usr/bin/env python
"""
测试脚本，演示并验证：system hint 只在发送给 LLM 前临时作为
user 消息附加，不会存入对话历史。
"""

import os
import json
from agent import SystemHintAgent, SystemHintConfig

def test_hint_behavior():
    """测试并演示 system hint 的行为"""
    api_key = os.getenv("KIMI_API_KEY")
    if not api_key:
        print("❌ Please set KIMI_API_KEY environment variable")
        return
    
    # 创建启用 system hint 的 Agent
    config = SystemHintConfig(
        enable_timestamps=True,
        enable_system_state=True,
        enable_todo_list=True,
        save_trajectory=True,
        trajectory_file="test_hint_trajectory.json"
    )
    
    agent = SystemHintAgent(
        api_key=api_key,
        provider="kimi",
        config=config,
        verbose=False
    )
    
    # 执行一个简单任务
    task = "Create a file called test.txt with content 'Testing hint behavior'"
    result = agent.execute_task(task, max_iterations=5)
    
    if result['success']:
        print("✅ Task completed successfully\n")
    
    # 分析对话历史
    print("=" * 60)
    print("CONVERSATION HISTORY ANALYSIS")
    print("=" * 60)
    
    # 加载已保存的轨迹
    with open("test_hint_trajectory.json", 'r') as f:
        trajectory = json.load(f)
    
    conversation = trajectory['conversation_history']
    
    print(f"\nTotal messages in conversation history: {len(conversation)}")
    print("\nMessage roles and previews:")
    
    for i, msg in enumerate(conversation, 1):
        role = msg['role']
        content = msg.get('content', '')
        
        # 检查内容是否包含 system hint
        has_system_state = 'SYSTEM STATE' in content
        has_todo_list = 'CURRENT TASKS' in content
        
        preview = content[:80].replace('\n', ' ')
        if len(content) > 80:
            preview += "..."
        
        print(f"\n{i}. [{role.upper()}]")
        print(f"   Preview: {preview}")
        
        if has_system_state or has_todo_list:
            print(f"   ⚠️ Contains system hints: System State={has_system_state}, TODO List={has_todo_list}")
    
    # 总结
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    # 检查是否有消息包含 system hint
    hints_in_history = any(
        'SYSTEM STATE' in msg.get('content', '') or 
        'CURRENT TASKS' in msg.get('content', '')
        for msg in conversation
    )
    
    if hints_in_history:
        print("❌ System hints found in conversation history (unexpected!)")
    else:
        print("✅ No system hints stored in conversation history (expected behavior)")
        print("   System hints are added as temporary user messages before LLM calls")
        print("   but are NOT stored in the conversation history.")
    
    # 清理测试文件
    if os.path.exists("test.txt"):
        os.remove("test.txt")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_hint_behavior()
