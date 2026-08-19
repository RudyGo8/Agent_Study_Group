"""
演示 KV cache 重要性的主脚本
以不同实现运行 ReAct Agent 并对比性能
"""

import os
import sys
import glob
import json
import argparse
import logging
from typing import Dict, List, Any
from datetime import datetime
from dataclasses import asdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent import KVCacheAgent, KVCacheMode, AgentMetrics, compare_implementations

# 默认模型（Moonshot / Kimi）。当前整个 Kimi 家族（k2.5/k2.6/k2.7/k3）既
# 会上报自动前缀缓存的 cached_tokens，又会思考，因此只接受 temperature=1
# （agent.py 已自动处理）。在上报缓存的模型里，kimi-k2.6 的思考开销最轻，
# TTFT 最干净，同时仍暴露本演示所需的前缀缓存命中指标。
# （非思考型的 moonshot-v1-* 模型不上报 cached_tokens，无法演示缓存效果。）
DEFAULT_MODEL = "kimi-k2.6"
DEFAULT_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kv_cache_demo.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 指标辅助函数（在线对比与离线报告共用）
# ---------------------------------------------------------------------------

def _coerce_metrics(metrics: Any) -> Dict[str, Any]:
    """把存储的 metrics 值归一化为普通字典。

    处理结果文件里的两种格式：
      - dict：由 --compare（asdict）及修复后的 --mode 路径产生
      - str ：旧版单模式文件，因 json.dump 用了 default=str
              而存成 repr(AgentMetrics(...))
    """
    if isinstance(metrics, dict):
        return metrics
    if isinstance(metrics, str) and metrics.startswith("AgentMetrics("):
        # 安全的 eval：只暴露 AgentMetrics，不提供内建函数。
        try:
            obj = eval(metrics, {"__builtins__": {}}, {"AgentMetrics": AgentMetrics})
            return asdict(obj)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Could not parse legacy metrics string: {e}")
    return {}


def _avg_ttft(m: Dict[str, Any]) -> float:
    """各次迭代 TTFT 的平均值；无数据时回退到首次迭代的 TTFT。"""
    lst = m.get("ttft_per_iteration") or []
    return sum(lst) / len(lst) if lst else float(m.get("ttft", 0.0) or 0.0)


def _hit_rate(m: Dict[str, Any]) -> float:
    total = (m.get("cache_hits", 0) or 0) + (m.get("cache_misses", 0) or 0)
    return (m.get("cache_hits", 0) or 0) / total * 100 if total else 0.0


def _billable_tokens(m: Dict[str, Any], cache_price_ratio: float) -> float:
    """按 prompt cache 折扣估算的计费 prompt token 数（示意）。

    缓存 token 按 cache_price_ratio 的比例计费，其余按原价。
    这只是"实测 token 数 + 用户给定比例"的透明函数 ——
    不是虚构的某家服务商报价。
    """
    prompt = m.get("prompt_tokens", 0) or 0
    cached = m.get("cached_tokens", 0) or 0
    cached = min(cached, prompt)
    return (prompt - cached) + cached * cache_price_ratio


def print_comparison_table(results: Dict[str, Any], cache_price_ratio: float = 0.1) -> None:
    """渲染跨策略对比表（延迟 / 缓存 / 成本）。"""
    print(f"\n{'Mode':<16} {'Iters':<6} {'1st TTFT':<10} {'Avg TTFT':<10} "
          f"{'Total(s)':<10} {'Prompt':<9} {'Cached':<9} {'Hit%':<7} "
          f"{'Cache%':<8} {'Bill.Tok':<10} {'Save%':<7}")
    print("-" * 112)

    for mode, data in results.items():
        m = _coerce_metrics(data.get("metrics", {}))
        prompt = m.get("prompt_tokens", 0) or 0
        cached = m.get("cached_tokens", 0) or 0
        iters = data.get("iterations", m.get("iterations", 0)) or 0
        cache_pct = cached / prompt * 100 if prompt else 0.0
        billable = _billable_tokens(m, cache_price_ratio)
        save_pct = (prompt - billable) / prompt * 100 if prompt else 0.0

        print(f"{mode:<16} {iters:<6} {float(m.get('ttft', 0.0) or 0.0):<10.3f} "
              f"{_avg_ttft(m):<10.3f} {float(m.get('total_time', 0.0) or 0.0):<10.3f} "
              f"{prompt:<9,} {cached:<9,} {_hit_rate(m):<7.1f} "
              f"{cache_pct:<8.1f} {billable:<10,.0f} {save_pct:<7.1f}")

    print("-" * 112)
    print(f"注：Bill.Tok / Save% 假设缓存 token 按正常价的 {cache_price_ratio:.0%} 计费"
          f"（可用 --cache-price-ratio 调整），仅为成本示意，非某家服务商实际报价。")


def load_result_files(paths: List[str]) -> Dict[str, Any]:
    """把 result_*.json 文件加载成 {mode: {...}} 字典，供离线报告使用。"""
    results: Dict[str, Any] = {}
    for path in sorted(paths):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Skipping {path}: {e}")
            continue

        # comparison_*.json 含多个模式；result_*.json 只含一个。
        if "mode" not in data and all(isinstance(v, dict) and "metrics" in v
                                      for v in data.values()):
            for mode, entry in data.items():
                results[mode] = {"metrics": _coerce_metrics(entry.get("metrics", {})),
                                 "iterations": entry.get("iterations"),
                                 "_source": path}
        else:
            mode = data.get("mode", os.path.splitext(os.path.basename(path))[0])
            results[mode] = {"metrics": _coerce_metrics(data.get("metrics", {})),
                             "iterations": data.get("iterations"),
                             "_source": path}
    return results


def run_report(inputs: List[str] = None, cache_price_ratio: float = 0.1) -> None:
    """离线：从已有的 result_*.json 文件生成对比表。

    无需 API key —— 读取之前保存的运行结果，一条命令即可查看
    最终结果，不必再次调用模型。
    """
    if not inputs:
        inputs = ["result_*.json", "comparison_*.json"]

    paths: List[str] = []
    for item in inputs:
        if os.path.isdir(item):
            paths.extend(glob.glob(os.path.join(item, "result_*.json")))
            paths.extend(glob.glob(os.path.join(item, "comparison_*.json")))
        else:
            paths.extend(glob.glob(item))

    paths = sorted(set(paths))
    if not paths:
        logger.error("未找到任何 result_*.json / comparison_*.json 结果文件。"
                     "请先运行 --mode 或 --compare 生成结果，或用 --input 指定路径。")
        sys.exit(1)

    results = load_result_files(paths)

    print("\n" + "=" * 112)
    print("KV CACHE 离线对比报告（基于已保存的实测结果）")
    print("=" * 112)
    print(f"数据来源（{len(paths)} 个文件）:")
    for mode, data in results.items():
        print(f"  • {mode:<16} ← {os.path.basename(data.get('_source', '?'))}")

    print_comparison_table(results, cache_price_ratio)

    print("\n📝 说明：不同结果文件可能来自不同任务/时间，绝对数值仅供同一次运行内横向对比；"
          "如需严格对照，请用 --compare 在同一任务下一次性生成全部模式的数据。")


def create_summary_task() -> str:
    """构造一个需要读取多个文件的任务"""
    return """Please analyze and summarize all the projects in the chapter1 and chapter2 directories.
For each project:
1. Find all Python files
2. Read the main files and understand the functionality
3. Identify the key features and purpose
4. Provide a comprehensive summary

Start with chapter1 projects, then move to chapter2. Be thorough in your analysis."""


def run_single_mode(api_key: str, mode: str, task: str = None, root_dir: str = DEFAULT_ROOT_DIR,
                    model: str = DEFAULT_MODEL, output: str = None):
    """
    以单个模式运行 Agent

    参数:
        api_key: Kimi 的 API key
        mode: 要使用的 KV cache 模式
        task: 自定义任务（可选）
        root_dir: 文件操作的根目录（默认: "../.." = 仓库根目录）
        model: 使用的模型
        output: 结果 JSON 的输出路径（可选；缺省时自动命名）
    """
    # 解析模式
    mode_map = {
        "correct": KVCacheMode.CORRECT,
        "dynamic_system": KVCacheMode.DYNAMIC_SYSTEM,
        "shuffled_tools": KVCacheMode.SHUFFLED_TOOLS,
        "dynamic_profile": KVCacheMode.DYNAMIC_PROFILE,
        "sliding_window": KVCacheMode.SLIDING_WINDOW,
        "text_format": KVCacheMode.TEXT_FORMAT
    }
    
    if mode not in mode_map:
        logger.error(f"Invalid mode: {mode}")
        logger.info(f"Valid modes: {', '.join(mode_map.keys())}")
        return
    
    # 未提供任务时使用默认任务
    if not task:
        task = create_summary_task()
    
    logger.info(f"Running in mode: {mode}")
    logger.info(f"Task: {task}")
    logger.info("="*80)
    
    # 创建 Agent 并执行任务
    agent = KVCacheAgent(
        api_key=api_key,
        mode=mode_map[mode],
        model=model,
        root_dir=root_dir,
        verbose=True
    )
    
    result = agent.execute_task(task, max_iterations=30)
    
    # 打印结果
    print("\n" + "="*80)
    print(f"EXECUTION RESULTS - Mode: {mode}")
    print("="*80)
    
    metrics = result["metrics"]
    print(f"\n📊 Performance Metrics:")
    print(f"  • Time to First Token (TTFT): {metrics.ttft:.3f} seconds")
    
    # 显示 TTFT 变化
    if metrics.ttft_per_iteration:
        print(f"  • TTFT per iteration:")
        for i, ttft in enumerate(metrics.ttft_per_iteration, 1):
            print(f"      Iteration {i}: {ttft:.3f}s")

        # 显示改善幅度
        if len(metrics.ttft_per_iteration) > 1:
            first_ttft = metrics.ttft_per_iteration[0]
            last_ttft = metrics.ttft_per_iteration[-1]
            avg_after_first = sum(metrics.ttft_per_iteration[1:]) / len(metrics.ttft_per_iteration[1:])
            print(f"  • TTFT Analysis:")
            print(f"      First iteration: {first_ttft:.3f}s")
            print(f"      Last iteration: {last_ttft:.3f}s")
            print(f"      Average (after first): {avg_after_first:.3f}s")
            improvement = (first_ttft - last_ttft) / first_ttft * 100
            print(f"      Improvement: {improvement:.1f}%")
    
    print(f"  • Total Execution Time: {metrics.total_time:.3f} seconds")
    print(f"  • Iterations: {result['iterations']}")
    print(f"  • Tool Calls: {len(result['tool_calls'])}")
    
    print(f"\n🔄 Cache Statistics:")
    print(f"  • Cached Tokens: {metrics.cached_tokens:,}")
    print(f"  • Cache Hits: {metrics.cache_hits}")
    print(f"  • Cache Misses: {metrics.cache_misses}")
    if metrics.cache_hits + metrics.cache_misses > 0:
        hit_rate = metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses) * 100
        print(f"  • Cache Hit Rate: {hit_rate:.1f}%")
    
    print(f"\n💰 Token Usage:")
    print(f"  • Prompt Tokens: {metrics.prompt_tokens:,}")
    print(f"  • Completion Tokens: {metrics.completion_tokens:,}")
    print(f"  • Total Tokens: {metrics.prompt_tokens + metrics.completion_tokens:,}")
    if metrics.prompt_tokens > 0:
        cache_ratio = metrics.cached_tokens / metrics.prompt_tokens * 100
        print(f"  • Cache Ratio: {cache_ratio:.1f}% of prompt tokens cached")
    
    # 显示工具调用摘要
    if result["tool_calls"]:
        print(f"\n🔧 Tool Calls Summary:")
        tool_counts = {}
        for tc in result["tool_calls"]:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
        for tool_name, count in tool_counts.items():
            print(f"  • {tool_name}: {count} calls")
    
    # 保存详细结果
    output_file = output or f"result_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        # 转成可序列化格式。metrics 经 asdict 存为字典，
        # 这样文件之后可被 --report 重新加载；tool_calls 同理。
        result_copy = result.copy()
        result_copy["metrics"] = asdict(result["metrics"])
        result_copy["tool_calls"] = [
            {
                "name": tc.name,
                "arguments": tc.arguments,
                "timestamp": tc.timestamp
            }
            for tc in result["tool_calls"]
        ]
        json.dump(result_copy, f, indent=2, default=str)

    print(f"\n💾 Detailed results saved to: {output_file}")


def select_mode_interactive():
    """
    交互式模式选择菜单
    
    返回:
        选中的模式字符串（选择全部模式时为特殊值）
    """
    modes = [
        ("correct", "✅ Correct Implementation - Optimal KV cache usage"),
        ("dynamic_system", "❌ Dynamic System Prompt - Adds timestamps"),
        ("shuffled_tools", "❌ Shuffled Tools - Randomizes tool order"),
        ("dynamic_profile", "❌ Dynamic Profile - Updates user credits"),
        ("sliding_window", "❌ Sliding Window - Keeps only recent messages"),
        ("text_format", "❌ Text Format - Plain text instead of structured"),
        ("compare", "📊 Compare All - Run all modes and compare"),
    ]
    
    print("\n" + "="*60)
    print("KV CACHE DEMONSTRATION - MODE SELECTION")
    print("="*60)
    print("\nSelect a mode to run:\n")
    
    for i, (mode, description) in enumerate(modes, 1):
        print(f"  {i}. {description}")
    
    print("\n  0. Exit")
    print("-"*60)
    
    while True:
        try:
            choice = input("\nEnter your choice (0-7): ").strip()
            choice_num = int(choice)
            
            if choice_num == 0:
                print("Exiting...")
                sys.exit(0)
            elif 1 <= choice_num <= 6:
                selected = modes[choice_num - 1][0]
                print(f"\n✓ Selected: {modes[choice_num - 1][1]}")
                return selected
            elif choice_num == 7:
                print("\n✓ Selected: Compare all modes")
                return "compare"
            else:
                print("Invalid choice. Please enter a number between 0 and 7.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\n\nExiting...")
            sys.exit(0)

def run_comparison(api_key: str, task: str = None, root_dir: str = DEFAULT_ROOT_DIR,
                   model: str = DEFAULT_MODEL, output: str = None,
                   cache_price_ratio: float = 0.1):
    """
    跨全部模式运行对比

    参数:
        api_key: Kimi 的 API key
        task: 自定义任务（可选）
        root_dir: 文件操作的根目录（默认: "../.." = 仓库根目录）
        model: 所有模式共用的模型
        output: 对比 JSON 的输出路径（可选；缺省时自动命名）
        cache_price_ratio: 缓存 token 相对普通 token 的假定价格（成本列）
    """
    # 未提供任务时使用默认任务
    if not task:
        task = create_summary_task()

    logger.info("Starting KV Cache Comparison Study")
    logger.info(f"Task: {task[:200]}...")
    logger.info("="*80)

    # 运行对比
    results = compare_implementations(api_key, task, root_dir, model=model)

    # 打印对比表
    print("\n" + "="*112)
    print("KV CACHE COMPARISON RESULTS")
    print("="*112)

    print_comparison_table(results, cache_price_ratio)

    # 分析结果
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    
    # 找出表现最好与最差的模式
    correct_metrics = results["correct"]["metrics"]
    
    print("\n🏆 Performance Impact (compared to correct implementation):")
    for mode, data in results.items():
        if mode == "correct":
            continue
        
        metrics = data["metrics"]
        ttft_diff = ((metrics["ttft"] - correct_metrics["ttft"]) / correct_metrics["ttft"]) * 100
        total_diff = ((metrics["total_time"] - correct_metrics["total_time"]) / correct_metrics["total_time"]) * 100
        cache_diff = correct_metrics["cached_tokens"] - metrics["cached_tokens"]
        
        print(f"\n{mode}:")
        print(f"  • TTFT: {'+' if ttft_diff > 0 else ''}{ttft_diff:.1f}% "
              f"({'slower' if ttft_diff > 0 else 'faster'})")
        print(f"  • Total Time: {'+' if total_diff > 0 else ''}{total_diff:.1f}% "
              f"({'slower' if total_diff > 0 else 'faster'})")
        print(f"  • Lost Cached Tokens: {cache_diff:,}")
    
    # 显示 TTFT 变化对比
    print("\n📈 TTFT Progression (first 5 iterations):")
    for mode, data in results.items():
        metrics = data["metrics"]
        ttft_list = metrics.get("ttft_per_iteration", [])[:5]
        if ttft_list:
            ttft_str = " → ".join([f"{t:.2f}s" for t in ttft_list])
            print(f"  {mode:<20}: {ttft_str}")
    
    # 关键结论
    print("\n📝 Key Insights:")
    print("  1. The correct implementation maintains stable context for optimal KV cache usage")
    print("  2. TTFT improves dramatically after first iteration when cache is utilized")
    print("  3. Dynamic system prompts invalidate the entire cache on each request")
    print("  4. Shuffling tools breaks cache even though the functionality is identical")
    print("  5. Dynamic user profiles add unnecessary context changes")
    print("  6. Sliding windows may seem to reduce context but actually harm cache efficiency")
    print("  7. Text formatting breaks the structured message format that enables caching")
    
    # 保存对比结果
    output_file = output or f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n💾 Comparison results saved to: {output_file}")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="KV Cache 实验：用 ReAct Agent 对比不同上下文构造策略对前缀缓存"
                    "（KV Cache / Prompt Cache）命中率、TTFT 延迟与成本的影响。",
        epilog="示例：\n"
               "  python main.py --mode correct                  # 运行单个策略\n"
               "  python main.py --compare                       # 一次跑完所有策略并打印对比表\n"
               "  python main.py --report                        # 离线：读取已有 result_*.json 打印对比表（无需 API Key）\n"
               "  python main.py --mode sliding_window --model kimi-k2.6 --output run.json\n"
               "\n可选策略（--mode）：correct, dynamic_system, shuffled_tools,\n"
               "                      dynamic_profile, sliding_window, text_format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--api-key", type=str,
                        help="Moonshot/Kimi API Key（也可用环境变量 MOONSHOT_API_KEY）")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"使用的模型名（默认：{DEFAULT_MODEL}）")
    parser.add_argument("--mode", type=str,
                        help="运行单个策略：correct / dynamic_system / shuffled_tools / "
                             "dynamic_profile / sliding_window / text_format")
    parser.add_argument("--compare", action="store_true",
                        help="依次运行全部策略并打印横向对比表（需要 API Key）")
    parser.add_argument("--report", action="store_true",
                        help="离线模式：从已保存的 result_*.json / comparison_*.json 生成对比表（无需 API Key）")
    parser.add_argument("--input", type=str, nargs="*", default=None,
                        help="配合 --report：指定结果文件、通配符或目录（默认：当前目录下的 result_*.json 与 comparison_*.json）")
    parser.add_argument("--output", type=str,
                        help="结果 JSON 的输出路径（默认按模式和时间戳自动命名）")
    parser.add_argument("--cache-price-ratio", type=float, default=0.1,
                        help="成本估算中缓存 token 相对正常 token 的计费比例（默认：0.1，即缓存读取按一折计），仅作示意")
    parser.add_argument("--task", type=str, help="自定义任务描述（默认：分析并总结项目代码）")
    parser.add_argument("--root-dir", type=str, default=DEFAULT_ROOT_DIR,
                        help="文件工具的根目录（默认：仓库根目录，供 Agent 读取代码）")
    parser.add_argument("--interactive", action="store_true", default=True,
                        help="交互式菜单选择策略（默认开启）")
    parser.add_argument("--no-interactive", dest="interactive", action="store_false",
                        help="关闭交互式菜单")

    args = parser.parse_args()

    # 离线报告无需 API key —— 优先处理。
    if args.report:
        run_report(args.input, args.cache_price_ratio)
        return

    # 获取 API key。优先 Moonshot/Kimi 官方 key；缺失时回退到 OPENROUTER_API_KEY
    # （KVCacheAgent 会据此自动切换到 OpenRouter 端点并映射模型名）。
    api_key = (args.api_key or os.getenv("MOONSHOT_API_KEY")
               or os.getenv("KIMI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))
    if not api_key:
        logger.error("请通过 --api-key 或环境变量 MOONSHOT_API_KEY / KIMI_API_KEY / "
                     "OPENROUTER_API_KEY 提供 API Key；"
                     "若只想查看已有结果，可使用 --report（无需 API Key）。")
        sys.exit(1)

    # 按模式运行
    if args.compare:
        # 显式 --compare 参数优先于交互模式
        run_comparison(api_key, args.task, args.root_dir, args.model, args.output,
                       args.cache_price_ratio)
    elif args.mode:
        # 显式 --mode 参数优先于交互模式
        run_single_mode(api_key, args.mode, args.task, args.root_dir, args.model, args.output)
    elif args.interactive and not args.task:
        # 交互式选择模式（默认）
        selected_mode = select_mode_interactive()
        if selected_mode == "compare":
            run_comparison(api_key, args.task, args.root_dir, args.model, args.output,
                           args.cache_price_ratio)
        else:
            run_single_mode(api_key, selected_mode, args.task, args.root_dir, args.model, args.output)
    else:
        # 只给了任务未给模式时，询问用哪个模式
        if args.task:
            print(f"\n📝 Custom task provided: {args.task}")
            selected_mode = select_mode_interactive()
            if selected_mode == "compare":
                run_comparison(api_key, args.task, args.root_dir, args.model, args.output,
                               args.cache_price_ratio)
            else:
                run_single_mode(api_key, selected_mode, args.task, args.root_dir, args.model, args.output)
        else:
            # 回退到交互模式
            selected_mode = select_mode_interactive()
            if selected_mode == "compare":
                run_comparison(api_key, args.task, args.root_dir, args.model, args.output,
                               args.cache_price_ratio)
            else:
                run_single_mode(api_key, selected_mode, args.task, args.root_dir, args.model, args.output)


if __name__ == "__main__":
    main()
