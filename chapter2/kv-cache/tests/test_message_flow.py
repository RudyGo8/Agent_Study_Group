#!/usr/bin/env python3
"""
验证正确与错误模式下消息流转的测试脚本
"""

def test_message_flow_logic():
    """模拟不同模式下消息的处理方式"""
    
    print("🔍 Testing Message Flow Logic")
    print("="*60)
    
    # 模拟 CORRECT 模式
    print("\n✅ CORRECT Mode:")
    print("-"*40)
    
    messages_correct = None
    history_correct = []
    
    for iteration in range(1, 4):
        print(f"\nIteration {iteration}:")
        
        if iteration == 1:
            # 第一次迭代：创建 messages
            messages_correct = ["system", "task"]
            print(f"  • Created messages: {messages_correct}")
        else:
            print(f"  • Using existing messages: {messages_correct}")
        
        # 模拟工具调用
        print(f"  • API returns tool call")
        messages_correct.append(f"assistant_iter{iteration}")
        history_correct.append(f"assistant_iter{iteration}")
        
        # 模拟工具结果
        print(f"  • Tool executed")
        messages_correct.append(f"tool_result_iter{iteration}")
        history_correct.append(f"tool_result_iter{iteration}")
        
        print(f"  • Messages now: {messages_correct}")
        print(f"  • History now: {history_correct}")
    
    # 模拟错误模式
    print("\n\n❌ INCORRECT Mode (e.g., DYNAMIC_SYSTEM):")
    print("-"*40)
    
    history_incorrect = []
    
    for iteration in range(1, 4):
        print(f"\nIteration {iteration}:")
        
        # 每次都从历史重建 messages
        messages_incorrect = ["system_with_timestamp", "task"] + history_incorrect
        print(f"  • Recreated messages: {messages_incorrect}")
        
        # 模拟工具调用
        print(f"  • API returns tool call")
        messages_incorrect.append(f"assistant_iter{iteration}")
        history_incorrect.append(f"assistant_iter{iteration}")
        
        # 模拟工具结果
        print(f"  • Tool executed")
        messages_incorrect.append(f"tool_result_iter{iteration}")
        history_incorrect.append(f"tool_result_iter{iteration}")
        
        print(f"  • Messages now: {messages_incorrect}")
        print(f"  • History now: {history_incorrect}")
    
    print("\n\n📊 Key Observations:")
    print("="*60)
    print("\n1. CORRECT Mode:")
    print("   • Messages list persists across iterations")
    print("   • Each iteration adds to the same list")
    print("   • Context remains stable → KV cache works")
    
    print("\n2. INCORRECT Mode:")
    print("   • Messages list recreated each iteration")
    print("   • System prompt changes (timestamp)")
    print("   • Context changes → KV cache invalidated")
    
    print("\n3. Both Modes:")
    print("   • Within an iteration, tool results are appended")
    print("   • This ensures the API sees complete conversation")
    print("   • History is maintained for reconstruction")

if __name__ == "__main__":
    test_message_flow_logic()
