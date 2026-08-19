#!/usr/bin/env python3
"""
GPT-5 原生工具 Agent 快速入门演示
演示 web_search 和 code_interpreter 工具的基本用法
"""

import os
import sys
from agent import GPT5NativeAgent
from config import Config

def demo_web_search():
    """演示网页搜索能力"""
    print("\n" + "="*60)
    print("DEMO: Web Search Tool")
    print("="*60)
    
    agent = GPT5NativeAgent(
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL
    )
    
    result = agent.process_request(
        "What are the latest developments in GPT-5 and its capabilities?",
        use_tools=True,
        reasoning_effort="low"
    )
    
    if result["success"]:
        print("\n✅ Web Search Result:")
        print(result["response"][:500] + "...")
        if result["tool_calls"]:
            print(f"\n🔧 Tools used: {len(result['tool_calls'])}")
    else:
        print(f"❌ Error: {result['error']}")

def demo_code_interpreter():
    """演示代码生成与分析能力"""
    print("\n" + "="*60)
    print("DEMO: Code Generation and Analysis")
    print("="*60)
    
    agent = GPT5NativeAgent(
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL
    )
    
    result = agent.process_request(
        """Create Python code to:
        1. Generate the first 20 Fibonacci numbers
        2. Calculate their sum and average
        3. Find the golden ratio approximation using consecutive pairs
        4. Explain the mathematical significance""",
        use_tools=True,
        reasoning_effort="medium"
    )
    
    if result["success"]:
        print("\n✅ Code and Analysis Result:")
        print(result["response"][:500] + "...")
        if result["tool_calls"]:
            print(f"\n🔧 Tools used: {len(result['tool_calls'])}")
    else:
        print(f"❌ Error: {result['error']}")

def demo_combined_tools():
    """演示两个工具的组合使用"""
    print("\n" + "="*60)
    print("DEMO: Combined Web Search + Code Analysis")
    print("="*60)
    
    agent = GPT5NativeAgent(
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL
    )
    
    result = agent.search_and_analyze(
        topic="Current S&P 500 performance and major tech stocks",
        analysis_code="""
# Analyze market data
import random
import statistics

# Simulate stock prices based on search results
stocks = {
    'AAPL': [175 + random.uniform(-5, 5) for _ in range(10)],
    'GOOGL': [140 + random.uniform(-3, 3) for _ in range(10)],
    'MSFT': [380 + random.uniform(-8, 8) for _ in range(10)]
}

# Calculate metrics
for symbol, prices in stocks.items():
    avg = statistics.mean(prices)
    vol = statistics.stdev(prices)
    trend = "↑" if prices[-1] > prices[0] else "↓"
    print(f"{symbol}: Avg=${avg:.2f}, Volatility=${vol:.2f}, Trend={trend}")
"""
    )
    
    if result["success"]:
        print("\n✅ Combined Analysis Result:")
        print(result["response"][:500] + "...")
        if result["tool_calls"]:
            print(f"\n🔧 Tools used: {len(result['tool_calls'])}")
    else:
        print(f"❌ Error: {result['error']}")

def main():
    """运行全部演示"""
    print("\n" + "="*60)
    print("      GPT-5 Native Tools Agent - Quick Start Demo")
    print("="*60)
    
    # 检查配置
    if not Config.validate():
        print("\n❌ Configuration Error!")
        print("Please set up your .env file with OPENROUTER_API_KEY")
        print("\nSteps:")
        print("1. Copy env.example to .env")
        print("2. Add your OpenRouter API key")
        print("3. Get a key at: https://openrouter.ai/keys")
        sys.exit(1)
    
    print("\n✅ Configuration valid")
    print(f"Using model: {Config.MODEL_NAME}")
    
    # 询问用户运行哪个演示
    print("\nSelect demo to run:")
    print("1. Web Search only")
    print("2. Code Generation and Analysis")
    print("3. Combined Tools")
    print("4. All demos")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        demo_web_search()
    elif choice == "2":
        demo_code_interpreter()
    elif choice == "3":
        demo_combined_tools()
    elif choice == "4":
        demo_web_search()
        demo_code_interpreter()
        demo_combined_tools()
    else:
        print("Invalid choice. Running all demos...")
        demo_web_search()
        demo_code_interpreter()
        demo_combined_tools()
    
    print("\n" + "="*60)
    print("Demo complete! 🎉")
    print("\nNext steps:")
    print("- Run 'python main.py' for interactive mode")
    print("- Run 'python main.py --mode test' for live manual cases")
    print("- Check README.md for more examples")
    print("="*60)

if __name__ == "__main__":
    main()
