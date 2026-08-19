#!/usr/bin/env python3
"""
演示如何在 chat template Agent 中使用流式输出的简单示例
"""

import sys
import time


def print_with_typing_effect(text, delay=0.03):
    """以打字机效果打印文本"""
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def demo_vllm_streaming():
    """演示 vLLM 后端的流式输出"""
    from agent import VLLMToolAgent
    from config import OPENAI_API_BASE, OPENAI_API_KEY
    
    print("="*60)
    print("🚀 vLLM Streaming Demo")
    print("="*60)
    
    try:
        agent = VLLMToolAgent(
            api_base=OPENAI_API_BASE,
            api_key=OPENAI_API_KEY
        )
        
        query = "What's the weather in New York and calculate 32°F in Celsius?"
        print(f"\n📝 Query: {query}\n")
        print("Streaming response:\n")
        print("-"*40)
        
        for chunk in agent.chat_stream(query):
            chunk_type = chunk.get("type")
            content = chunk.get("content", "")
            
            if chunk_type == "thinking":
                print(f"\n💭 [Thinking]: \033[90m{content}\033[0m")
            elif chunk_type == "tool_call":
                print(f"\n🔧 [Tool Call]: {content['name']}({content['arguments']})")
            elif chunk_type == "tool_result":
                print(f"   ✓ Result: {content}")
            elif chunk_type == "content":
                # 逐字符流式输出内容
                print(content, end="", flush=True)
        
        print("\n" + "-"*40)
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure vLLM server is running!")


def demo_ollama_streaming():
    """演示 Ollama 后端的流式输出"""
    from ollama_native import OllamaNativeAgent
    import ollama
    
    print("="*60)
    print("🦙 Ollama Streaming Demo")
    print("="*60)
    
    try:
        # 检查可用模型
        client = ollama.Client()
        models = [m['name'] for m in client.list()['models']]
        
        # 默认使用 qwen3:0.6b
        model = "qwen3:0.6b"
        
        if model not in models:
            print(f"⚠️ Recommended model {model} not found")
            print("Install with: ollama pull qwen3:0.6b")
            if models:
                model = models[0]
                print(f"Using fallback model: {model}")
            else:
                print("❌ No Ollama models found. Install with: ollama pull qwen3:0.6b")
                return
        
        print(f"Using model: {model}")
        agent = OllamaNativeAgent(model=model)
        
        query = "What's 15 * 23? Also get the current time in Tokyo."
        print(f"\n📝 Query: {query}\n")
        print("Streaming response:\n")
        print("-"*40)
        
        for chunk in agent.chat_stream(query):
            chunk_type = chunk.get("type")
            content = chunk.get("content", "")
            
            if chunk_type == "thinking":
                print(f"\n💭 [Thinking]: \033[90m{content}\033[0m")
            elif chunk_type == "tool_call":
                print(f"\n🔧 [Tool Call]: {content['name']}({content['arguments']})")
            elif chunk_type == "tool_result":
                print(f"   ✓ Result: {content}")
            elif chunk_type == "content":
                # 流式输出内容
                print(content, end="", flush=True)
        
        print("\n" + "-"*40)
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure Ollama is running: ollama serve")


def demo_unified_streaming():
    """演示自动选择后端的统一 ToolCallingAgent"""
    from main import ToolCallingAgent
    
    print("="*60)
    print("🎯 Unified Streaming Demo (Auto-detect Backend)")
    print("="*60)
    
    # 初始化 Agent（自动检测最合适的后端）
    print("\n⚙️  Initializing agent...")
    agent = ToolCallingAgent()
    print(f"✅ Using {agent.backend_type} backend\n")
    
    # 示例查询
    queries = [
        "Calculate the compound interest on $1000 at 5% for 3 years",
        "What's the weather in London and what time is it there?",
        "Convert 50 EUR to USD and JPY"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n{'='*60}")
        print(f"Query {i}: {query}")
        print("-"*60)
        
        # 记录已显示过哪些区块
        sections_shown = set()
        last_chunk_type = None
        
        for chunk in agent.chat(query, stream=True):
            chunk_type = chunk.get("type")
            content = chunk.get("content", "")
            
            if chunk_type == "thinking":
                if "thinking" not in sections_shown:
                    print("\n💭 Thinking: ", end="", flush=True)
                    sections_shown.add("thinking")
                # 以灰色逐字符流式输出思考内容
                print(f"\033[90m{content}\033[0m", end="", flush=True)
            
            elif chunk_type == "tool_call":
                if "tools" not in sections_shown:
                    print("\n🔧 Tool Calls:")
                    sections_shown.add("tools")
                print(f"  → {content['name']}: {content['arguments']}")
                # 移除 response 区块标记，让工具执行后重新显示标题
                sections_shown.discard("response")
            
            elif chunk_type == "tool_result":
                result_str = str(content)
                print(f"    ✓ {result_str}")
                # 移除 response 区块标记，让工具执行后重新显示标题
                sections_shown.discard("response")
            
            elif chunk_type == "content":
                if "response" not in sections_shown:
                    if last_chunk_type in ["tool_result", "tool_call"]:
                        print("\n📝 Response (after tools):")
                    else:
                        print("\n📝 Response:")
                    sections_shown.add("response")
                    print("  ", end="")
                print(content, end="", flush=True)
            
            last_chunk_type = chunk_type
        
        print()  # 响应结束后换行
        
        # 为下一个查询重置对话
        agent.reset_conversation()

    print("\n" + "="*60)
    print("✅ Demo completed!")
    print("="*60)


def main():
    """演示主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Streaming Demo for Chat Template Agents")
    parser.add_argument(
        "--backend",
        choices=["vllm", "ollama", "auto"],
        default="auto",
        help="Backend to use for demo"
    )
    
    args = parser.parse_args()
    
    if args.backend == "vllm":
        demo_vllm_streaming()
    elif args.backend == "ollama":
        demo_ollama_streaming()
    else:
        demo_unified_streaming()


if __name__ == "__main__":
    main()
