"""
GPT-5 原生工具 Agent 的联网手动用例。

这些用例演示 OpenRouter 格式的 web_search，需要设置
OPENROUTER_API_KEY。
"""

import json
import logging
import sys
from typing import Dict, Any, List
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent import GPT5NativeAgent, GPT5AgentChain
from config import Config

# 配置日志
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)


class TestGPT5Agent:
    """GPT-5 原生工具 Agent 的联网手动用例套件"""
    
    def __init__(self):
        """初始化手动用例套件"""
        if not Config.validate():
            raise ValueError("Invalid configuration. Please check your .env file")
        
        self.agent = GPT5NativeAgent(
            api_key=Config.OPENROUTER_API_KEY,
            base_url=Config.OPENROUTER_BASE_URL,
            model=Config.MODEL_NAME
        )
        self.results = []
    
    def test_web_search_basic(self) -> Dict[str, Any]:
        """
        测试用例 1：基础网页搜索
        """
        print("\n" + "="*60)
        print("TEST 1: Basic Web Search")
        print("="*60)
        
        request = """Search for the latest information about GPT-5 capabilities and features."""
        
        result = self.agent.process_request(
            request,
            use_tools=True,
            reasoning_effort="low"
        )
        
        self._print_result(result)
        return result
    
    def test_web_search_with_analysis(self) -> Dict[str, Any]:
        """
        测试用例 2：带分析请求的网页搜索
        """
        print("\n" + "="*60)
        print("TEST 2: Web Search with Analysis")
        print("="*60)
        
        request = """Search for current cryptocurrency market trends and Bitcoin price. 
        Then analyze the data to identify patterns and provide insights."""
        
        result = self.agent.process_request(
            request,
            use_tools=True,
            reasoning_effort="medium"
        )
        
        self._print_result(result)
        return result
    
    def test_complex_research(self) -> Dict[str, Any]:
        """
        测试用例 3：复杂研究任务
        """
        print("\n" + "="*60)
        print("TEST 3: Complex Research Task")
        print("="*60)
        
        request = """Research the current state of renewable energy adoption globally.
        Find statistics on solar, wind, and hydroelectric capacity.
        Analyze growth trends and project future adoption rates.
        Provide a comprehensive summary with data-driven insights."""
        
        result = self.agent.process_request(
            request,
            use_tools=True,
            reasoning_effort="high"
        )
        
        self._print_result(result)
        return result
    
    def test_search_and_code(self) -> Dict[str, Any]:
        """
        测试用例 4：搜索与代码生成
        """
        print("\n" + "="*60)
        print("TEST 4: Search and Code Generation")
        print("="*60)
        
        request = """Search for the latest Python web frameworks in 2025.
        Then create a simple comparison table and sample code for the top 3 frameworks."""
        
        result = self.agent.process_request(
            request,
            use_tools=True,
            reasoning_effort="medium"
        )
        
        self._print_result(result)
        return result
    
    def test_reasoning_efforts(self) -> List[Dict[str, Any]]:
        """
        测试用例 5：对比不同推理力度
        """
        print("\n" + "="*60)
        print("TEST 5: Reasoning Effort Comparison")
        print("="*60)
        
        request = "What are the implications of quantum computing on current encryption methods?"
        
        results = []
        for effort in ["low", "medium", "high"]:
            print(f"\n--- Testing with {effort} reasoning effort ---")
            result = self.agent.process_request(
                request,
                use_tools=True,
                reasoning_effort=effort
            )
            self._print_result(result)
            results.append({
                "effort": effort,
                "result": result
            })
        
        return results
    
    def test_search_and_analyze_method(self) -> Dict[str, Any]:
        """
        测试用例 6：使用 search_and_analyze 便捷方法
        """
        print("\n" + "="*60)
        print("TEST 6: Search and Analyze Method")
        print("="*60)
        
        analysis_code = """
# Analyze stock market data
import statistics

# Sample data processing
prices = [100, 102, 98, 105, 103, 107, 104]
returns = [(prices[i] - prices[i-1])/prices[i-1] * 100 for i in range(1, len(prices))]

avg_return = statistics.mean(returns)
volatility = statistics.stdev(returns)

print(f"Average Return: {avg_return:.2f}%")
print(f"Volatility: {volatility:.2f}%")
"""
        
        result = self.agent.search_and_analyze(
            topic="Current S&P 500 performance and market outlook for 2025",
            analysis_code=analysis_code
        )
        
        self._print_result(result)
        return result
    
    def test_agent_chain(self) -> List[Dict[str, Any]]:
        """
        测试用例 7：串联多个请求
        """
        print("\n" + "="*60)
        print("TEST 7: Agent Chain")
        print("="*60)
        
        chain = GPT5AgentChain(self.agent)
        
        # 第 1 步：检索信息
        chain.add_step(
            "Search for information about the latest AI developments in 2025",
            use_tools=True,
            reasoning_effort="low"
        )
        
        # 第 2 步：深入挖掘
        chain.add_step(
            "Based on the previous findings, search for more details about the most promising AI breakthrough",
            use_tools=True,
            reasoning_effort="medium"
        )
        
        # 第 3 步：分析
        chain.add_step(
            "Analyze the impact of these AI developments on various industries",
            use_tools=True,
            reasoning_effort="high"
        )
        
        results = chain.execute()
        
        for i, step_result in enumerate(results, 1):
            print(f"\n--- Chain Step {i} ---")
            self._print_result(step_result["result"])
        
        return results
    
    def _print_result(self, result: Dict[str, Any]):
        """
        以易读格式打印测试结果
        
        参数:
            result: 测试结果字典
        """
        if result["success"]:
            print(f"\n✅ Test Passed")
            print(f"\nResponse Preview:")
            print("-"*60)
            response = result["response"]
            if len(response) > 500:
                print(response[:500] + "...")
            else:
                print(response)
            print("-"*60)
            
            if result.get("usage"):
                usage = result["usage"]
                print(f"\n📊 Token Usage:")
                print(f"  - Input: {usage.get('input_tokens', 'N/A')}")
                print(f"  - Output: {usage.get('output_tokens', 'N/A')}")
                print(f"  - Total: {usage.get('total_tokens', 'N/A')}")
                if usage.get("input_tokens_details"):
                    print(f"  - Cached: {usage['input_tokens_details'].get('cached_tokens', 0)}")
                if usage.get("output_tokens_details"):
                    print(f"  - Reasoning: {usage['output_tokens_details'].get('reasoning_tokens', 0)}")
        else:
            print(f"\n❌ Test Failed")
            print(f"Error: {result.get('error', 'Unknown error')}")
    
    def run_all_tests(self):
        """运行全部联网手动用例"""
        print("\n" + "="*60)
        print("RUNNING GPT-5 NATIVE TOOLS MANUAL CASES")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Model: {Config.MODEL_NAME}")
        print("="*60)
        
        case_methods = [
            ("Basic Web Search", self.test_web_search_basic),
            ("Web Search with Analysis", self.test_web_search_with_analysis),
            ("Complex Research", self.test_complex_research),
            ("Search and Code", self.test_search_and_code),
            ("Reasoning Efforts", self.test_reasoning_efforts),
            ("Search and Analyze Method", self.test_search_and_analyze_method),
            ("Agent Chain", self.test_agent_chain)
        ]
        
        results_summary = []
        
        for case_name, case_method in case_methods:
            try:
                print(f"\n🧪 Running: {case_name}")
                result = case_method()
                
                # 处理不同类型的结果
                if isinstance(result, list):
                    # 针对返回多个结果的用例
                    if all(isinstance(r, dict) and "result" in r for r in result):
                        success = all(r["result"]["success"] for r in result)
                    else:
                        success = all(r.get("success", False) for r in result if isinstance(r, dict))
                else:
                    success = result.get("success", False)
                
                results_summary.append({
                    "case": case_name,
                    "success": success,
                    "result": result
                })
                
            except Exception as e:
                logger.error(f"Manual case {case_name} failed with exception: {str(e)}")
                results_summary.append({
                    "case": case_name,
                    "success": False,
                    "error": str(e)
                })
        
        # 打印汇总
        print("\n" + "="*60)
        print("MANUAL CASE SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in results_summary if r["success"])
        total = len(results_summary)
        
        for result in results_summary:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{result['case']}: {status}")
        
        print(f"\nTotal: {passed}/{total} manual cases passed")
        print("="*60)
        
        return results_summary


def run_single_test(test_name: str = "basic"):
    """
    运行单个联网手动用例
    
    参数:
        test_name: 要运行的手动用例名称
    """
    tester = TestGPT5Agent()
    
    test_map = {
        "basic": tester.test_web_search_basic,
        "analysis": tester.test_web_search_with_analysis,
        "complex": tester.test_complex_research,
        "code": tester.test_search_and_code,
        "reasoning": tester.test_reasoning_efforts,
        "search_analyze": tester.test_search_and_analyze_method,
        "chain": tester.test_agent_chain
    }
    
    if test_name in test_map:
        test_map[test_name]()
    else:
        print(f"Unknown test: {test_name}")
        print(f"Available tests: {', '.join(test_map.keys())}")


if __name__ == "__main__":
    # 先检查配置
    Config.display()
    
    if not Config.validate():
        print("\n❌ Configuration validation failed!")
        print("Please set up your .env file with OPENROUTER_API_KEY")
        sys.exit(1)
    
    # 运行手动用例
    if len(sys.argv) > 1:
        # 运行指定用例
        run_single_test(sys.argv[1])
    else:
        # 运行全部用例
        tester = TestGPT5Agent()
        tester.run_all_tests()
