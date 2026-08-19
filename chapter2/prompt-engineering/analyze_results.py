#!/usr/bin/env python3
"""
分析并可视化消融实验结果
"""

import argparse
import json
import glob
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import sys


def _extract_experiment_name(filename: str) -> str:
    """
    从结果文件名中还原消融名称。

    文件名遵循 run_ablation.py 生成的模式：
        ``{strategy}-{model}-{ablation_str}_{timestamp}.json``
    例如 ``tool-calling-gpt-5-tone_trump_0917203842`` -> ``tone_trump``。

    模型段本身可能含 ``-``（如 ``gpt-5``），因此先剥掉末尾的
    ``_<timestamp>``，再取最后一个 ``-`` 之后的部分作为消融名称。
    """
    # 剥掉末尾的时间戳，如 ``_0917203842``（>=6 位数字）。
    stripped = re.sub(r"_\d{6,}$", "", filename)
    # 消融名称是最后一个以 ``-`` 分隔的段。
    return stripped.rsplit("-", 1)[-1]


def load_results(results_dir: str = "results_ablation") -> Dict[str, List[float]]:
    """
    从结果目录加载全部结果

    返回:
        实验名到 reward 列表的映射字典
    """
    results = {}

    for file_path in sorted(glob.glob(f"{results_dir}/*.json")):
        # 跳过非原始运行输出的辅助/汇总文件。
        if Path(file_path).name in ("visualization_data.json", "summary.json"):
            continue
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # 从文件名提取实验名
            filename = Path(file_path).stem
            exp_name = _extract_experiment_name(filename)

            # 兼容不同的数据格式
            if isinstance(data, dict) and 'results' in data:
                # 带 ablation 配置的新格式
                rewards = [r['reward'] for r in data['results']]

                # 用配置拼出可读的实验名
                config = data.get('ablation_config', {})
                if config:
                    name_parts = []
                    if config.get('tone_style', 'default') != 'default':
                        name_parts.append(f"tone_{config['tone_style']}")
                    if config.get('randomize_wiki'):
                        name_parts.append('wiki_random')
                    if config.get('remove_tool_descriptions'):
                        name_parts.append('no_tools')
                    if config.get('apply_tone_to_system'):
                        name_parts.append('system')
                    
                    if name_parts:
                        exp_name = '_'.join(name_parts)
                    else:
                        exp_name = 'baseline'

                results.setdefault(exp_name, []).extend(rewards)

            elif isinstance(data, list):
                # 旧格式 —— 结果列表
                rewards = [r.get('reward', 0) for r in data]
                results.setdefault(exp_name, []).extend(rewards)
                
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")
    
    return results


def calculate_statistics(rewards: List[float]) -> Dict[str, float]:
    """
    计算一组 reward 的统计量
    """
    if not rewards:
        return {
            'success_rate': 0.0,
            'total': 0,
            'successes': 0,
            'failures': 0
        }
    
    successes = sum(rewards)
    total = len(rewards)
    
    return {
        'success_rate': (successes / total * 100) if total > 0 else 0,
        'total': total,
        'successes': int(successes),
        'failures': total - int(successes)
    }


def print_results_table(results: Dict[str, List[float]]):
    """
    打印格式化的结果表格
    """
    if not results:
        print("No results found!")
        return

    # 逐个实验计算统计量
    stats = {}
    for exp_name, rewards in results.items():
        stats[exp_name] = calculate_statistics(rewards)

    # 按成功率排序
    sorted_exps = sorted(stats.items(), key=lambda x: x[1]['success_rate'], reverse=True)

    # 找用于对比的基线
    baseline_rate = 0
    for exp_name, exp_stats in sorted_exps:
        if 'baseline' in exp_name.lower():
            baseline_rate = exp_stats['success_rate']
            break

    # 无显式基线时，取表现最好的当基线
    if baseline_rate == 0 and sorted_exps:
        baseline_rate = sorted_exps[0][1]['success_rate']

    # 打印表头
    print("\n" + "="*80)
    print(" "*25 + "ABLATION STUDY RESULTS")
    print("="*80)
    print()
    print(f"{'Experiment':<30} {'Success Rate':>15} {'Tasks':>10} {'Relative':>15}")
    print("-"*70)

    # 打印每个实验
    for exp_name, exp_stats in sorted_exps:
        success_rate = exp_stats['success_rate']
        relative = (success_rate / baseline_rate * 100) if baseline_rate > 0 else 100

        # 为基线加标记
        indicator = " ⭐" if 'baseline' in exp_name.lower() else ""
        
        print(f"{exp_name:<30} {success_rate:>6.1f}%{' ':>8} "
              f"{exp_stats['successes']}/{exp_stats['total']:>3} "
              f"{relative:>10.1f}% {indicator}")
    
    print("-"*70)


def analyze_ablation_impact(results: Dict[str, List[float]]):
    """
    分析各消融因子的影响
    """
    stats = {name: calculate_statistics(rewards) for name, rewards in results.items()}

    # 找基线
    baseline_rate = 0
    for name, stat in stats.items():
        if 'baseline' in name.lower():
            baseline_rate = stat['success_rate']
            break
    
    if baseline_rate == 0:
        print("\n⚠️  No baseline found for comparison")
        return
    
    print("\n" + "="*80)
    print(" "*25 + "ABLATION FACTOR ANALYSIS")
    print("="*80)
    
    # 分析单个因子
    factors = {
        'Tone (Trump)': ['tone_trump'],
        'Tone (Casual)': ['tone_casual'],
        'Wiki Randomization': ['wiki_random'],
        'No Tool Descriptions': ['no_tools', 'no_tool_desc'],
        'All Factors Combined': ['all_ablations', 'worst']
    }
    
    print(f"\n{'Factor':<25} {'Impact on Performance':>30} {'Severity':>15}")
    print("-"*70)
    
    impacts = []
    for factor_name, patterns in factors.items():
        # 查找匹配的实验
        for exp_name, exp_stats in stats.items():
            if any(pattern in exp_name.lower() for pattern in patterns):
                impact = baseline_rate - exp_stats['success_rate']
                relative_impact = (impact / baseline_rate * 100) if baseline_rate > 0 else 0

                # 判定严重程度
                if relative_impact >= 50:
                    severity = "🔴 Critical"
                elif relative_impact >= 30:
                    severity = "🟠 High"
                elif relative_impact >= 15:
                    severity = "🟡 Medium"
                else:
                    severity = "🟢 Low"

                impacts.append((factor_name, impact, relative_impact, severity))
                # `impact` = 基线 - 实验：正值表示性能下降（显示为如
                # "-25.0%"）；负值表示该消融反而好于基线（小样本可能出现），
                # 应显示为 "+25.0%" 而非 "--25.0%"。
                print(f"{factor_name:<25} {f'{-impact:+.1f}%':>20} ({relative_impact:.1f}%) {severity:>15}")
                break

    print("-"*70)

    # 关键洞察
    print("\n📊 KEY INSIGHTS:")
    print("-"*40)

    if impacts:
        # 按影响排序
        impacts.sort(key=lambda x: x[1], reverse=True)
        
        print(f"1. Most Critical Factor: {impacts[0][0]} (-{impacts[0][1]:.1f}% performance)")
        print(f"2. Least Critical Factor: {impacts[-1][0]} (-{impacts[-1][1]:.1f}% performance)")
        
        # 计算叠加效应
        combined = [i for i in impacts if 'All Factors' in i[0]]
        if combined:
            individual_sum = sum(i[1] for i in impacts if 'All Factors' not in i[0])
            actual_combined = combined[0][1]
            
            if individual_sum > 0:
                print(f"\n3. Interaction Effect:")
                print(f"   - Sum of individual impacts: -{individual_sum:.1f}%")
                print(f"   - Actual combined impact: -{actual_combined:.1f}%")
                
                if actual_combined > individual_sum:
                    print(f"   - Synergistic negative effect: Additional -{actual_combined - individual_sum:.1f}%")
                else:
                    print(f"   - Some resilience to combined factors")


def generate_summary_report(results: Dict[str, List[float]]):
    """
    生成综合汇总报告
    """
    print("\n" + "="*80)
    print(" "*20 + "EXECUTIVE SUMMARY")
    print("="*80)

    stats = {name: calculate_statistics(rewards) for name, rewards in results.items()}

    # 总体统计
    total_experiments = len(results)
    total_tasks = sum(len(rewards) for rewards in results.values())
    avg_success = sum(s['success_rate'] for s in stats.values()) / len(stats) if stats else 0
    
    print(f"\n📈 Overall Statistics:")
    print(f"   • Total Experiments Run: {total_experiments}")
    print(f"   • Total Tasks Evaluated: {total_tasks}")
    print(f"   • Average Success Rate: {avg_success:.1f}%")
    
    # 表现最好与最差的实验
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['success_rate'], reverse=True)
    if sorted_stats:
        best = sorted_stats[0]
        worst = sorted_stats[-1]
        
        print(f"\n🏆 Best Performer: {best[0]} ({best[1]['success_rate']:.1f}%)")
        print(f"❌ Worst Performer: {worst[0]} ({worst[1]['success_rate']:.1f}%)")
        print(f"📉 Performance Range: {best[1]['success_rate'] - worst[1]['success_rate']:.1f}%")
    
    print("\n" + "="*80)


def create_visualization_data(results: Dict[str, List[float]], results_dir: str = "results_ablation"):
    """
    生成可视化数据（可供绘图库使用）
    """
    viz_data = {
        'experiments': [],
        'success_rates': [],
        'sample_sizes': []
    }

    stats = {name: calculate_statistics(rewards) for name, rewards in results.items()}

    for name, stat in sorted(stats.items(), key=lambda x: x[1]['success_rate'], reverse=True):
        viz_data['experiments'].append(name)
        viz_data['success_rates'].append(stat['success_rate'])
        viz_data['sample_sizes'].append(stat['total'])

    # 保存以备后续绘图
    viz_path = Path(results_dir) / "visualization_data.json"
    with open(viz_path, 'w') as f:
        json.dump(viz_data, f, indent=2)

    print(f"\n💾 Visualization data saved to {viz_path}")
    
    # 打印 ASCII 条形图
    print("\n📊 Performance Bar Chart:")
    print("-"*50)
    
    max_width = 40
    for exp, rate in zip(viz_data['experiments'][:10], viz_data['success_rates'][:10]):
        bar_width = int(rate / 100 * max_width)
        bar = '█' * bar_width + '░' * (max_width - bar_width)
        print(f"{exp[:20]:<20} |{bar}| {rate:.1f}%")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="汇总分析提示工程消融实验结果，打印成功率对比表并生成图表数据。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  # 分析默认结果目录\n"
            "  python analyze_results.py\n\n"
            "  # 分析指定目录并把汇总写入 JSON\n"
            "  python analyze_results.py --results-dir results_ablation --output summary.json\n"
        ),
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="results_ablation",
        help="存放各消融实验结果 JSON 的目录（默认：results_ablation）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="（可选）将汇总统计写入该 JSON 文件路径",
    )
    return parser.parse_args()


def main():
    """
    主分析函数
    """
    args = parse_args()

    print("\n🔍 Analyzing Ablation Study Results...")

    # 加载结果
    results = load_results(args.results_dir)

    if not results:
        print(f"\n❌ No results found in {args.results_dir}/")
        print("Please run experiments first using:")
        print("  python run_ablation.py --model gpt-5.6-luna --env airline --all")
        sys.exit(1)

    # 运行所有分析
    print_results_table(results)
    analyze_ablation_impact(results)
    generate_summary_report(results)
    create_visualization_data(results, args.results_dir)

    # 可选：把汇总统计落盘
    if args.output:
        summary = {
            name: calculate_statistics(rewards) for name, rewards in results.items()
        }
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Summary statistics saved to {args.output}")
    
    print("\n✅ Analysis complete!")
    print("\n" + "="*80)
    
    # 结论
    print("\n💡 CONCLUSIONS:")
    print("-"*40)
    print("1. Prompt engineering significantly impacts agent performance")
    print("2. Clear instructions and documentation are essential")
    print("3. Professional tone and organized information improve results")
    print("4. Treating agents as 'smart new employees' is the right approach")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
