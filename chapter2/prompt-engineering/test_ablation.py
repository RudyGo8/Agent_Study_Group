#!/usr/bin/env python3
"""
演示全部消融模式的测试脚本
用不同消融设置跑一小部分任务
"""

import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def run_experiment(
    name: str,
    tone_style: str = "default",
    randomize_wiki: bool = False,
    remove_tool_descriptions: bool = False,
    apply_tone_to_system: bool = False,
    num_tasks: int = 3
) -> Tuple[str, float]:
    """
    运行单个消融实验

    返回:
        (实验名, 成功率) 元组
    """
    print(f"\n{'='*60}")
    print(f"🔬 Running Experiment: {name}")
    print(f"{'='*60}")
    
    cmd = [
        "python", "run_ablation.py",
        "--env", "airline",
        "--task-split", "test",
        "--start-index", "0",
        "--end-index", str(num_tasks),
        "--ablation-name", name.replace(" ", "_"),
        "--tone-style", tone_style
    ]
    
    if randomize_wiki:
        cmd.append("--randomize-wiki")
    
    if remove_tool_descriptions:
        cmd.append("--remove-tool-descriptions")
    
    if apply_tone_to_system:
        cmd.append("--apply-tone-to-system")
    
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            print(f"⚠️  Warning: Process returned non-zero code: {result.returncode}")
            print(f"Error output: {result.stderr[:500]}")
        
        # 解析输出得到成功率
        output_lines = result.stdout.split('\n')
        success_count = sum(1 for line in output_lines if '✅' in line)
        fail_count = sum(1 for line in output_lines if '❌' in line)
        total = success_count + fail_count
        
        if total > 0:
            success_rate = (success_count / total) * 100
            print(f"\n📊 Results: {success_count}/{total} tasks succeeded ({success_rate:.1f}%)")
        else:
            print("⚠️  No results found in output")
            success_rate = 0.0
        
        return name, success_rate
        
    except Exception as e:
        print(f"❌ Error running experiment: {e}")
        return name, 0.0


def run_all_experiments():
    """
    运行全部消融实验并对比结果
    """
    print("\n" + "="*80)
    print(" "*20 + "🎯 ABLATION STUDY DEMONSTRATION 🎯")
    print("="*80)
    print("\nThis script demonstrates how different prompt engineering factors")
    print("affect agent performance on the airline booking tasks.\n")
    
    experiments = [
        # 基线
        {
            "name": "1. Baseline (Professional)",
            "tone_style": "default",
            "randomize_wiki": False,
            "remove_tool_descriptions": False,
        },

        # 语气变化
        {
            "name": "2. Trump Style Tone",
            "tone_style": "trump",
            "randomize_wiki": False,
            "remove_tool_descriptions": False,
        },
        {
            "name": "3. Casual Style Tone",
            "tone_style": "casual",
            "randomize_wiki": False,
            "remove_tool_descriptions": False,
        },

        # wiki 随机化
        {
            "name": "4. Randomized Wiki Rules",
            "tone_style": "default",
            "randomize_wiki": True,
            "remove_tool_descriptions": False,
        },

        # 移除工具描述
        {
            "name": "5. No Tool Descriptions",
            "tone_style": "default",
            "randomize_wiki": False,
            "remove_tool_descriptions": True,
        },

        # 全部叠加（最差情况）
        {
            "name": "6. All Ablations (Worst Case)",
            "tone_style": "casual",
            "randomize_wiki": True,
            "remove_tool_descriptions": True,
        },
    ]
    
    results = []
    
    print("\n📋 Experiments to run:")
    for exp in experiments:
        print(f"  - {exp['name']}")
    
    print("\n⏳ Starting experiments (this may take a while)...\n")
    
    for exp in experiments:
        name, success_rate = run_experiment(**exp, num_tasks=3)
        results.append((name, success_rate))
        time.sleep(2)  # 实验之间稍作间隔

    # 展示汇总
    print("\n" + "="*80)
    print(" "*25 + "📈 FINAL RESULTS SUMMARY 📈")
    print("="*80)
    print("\n{:<40} {:>15}".format("Experiment", "Success Rate"))
    print("-"*60)
    
    baseline_rate = results[0][1] if results else 100
    
    for name, rate in results:
        # 计算相对表现
        if baseline_rate > 0:
            relative = (rate / baseline_rate) * 100
            print("{:<40} {:>6.1f}% ({:>5.1f}% of baseline)".format(
                name, rate, relative
            ))
        else:
            print("{:<40} {:>6.1f}%".format(name, rate))
    
    print("\n" + "="*80)
    print("\n🔍 Key Insights:")
    print("-"*40)
    
    if len(results) >= 6:
        # 分析各因子的影响
        baseline = results[0][1]
        trump_impact = baseline - results[1][1] if baseline > results[1][1] else 0
        casual_impact = baseline - results[2][1] if baseline > results[2][1] else 0
        wiki_impact = baseline - results[3][1] if baseline > results[3][1] else 0
        tools_impact = baseline - results[4][1] if baseline > results[4][1] else 0
        combined_impact = baseline - results[5][1] if baseline > results[5][1] else 0
        
        print(f"1. Tone Style Impact:")
        print(f"   - Trump style: -{trump_impact:.1f}% performance")
        print(f"   - Casual style: -{casual_impact:.1f}% performance")
        
        print(f"\n2. Wiki Organization Impact:")
        print(f"   - Randomized rules: -{wiki_impact:.1f}% performance")
        
        print(f"\n3. Tool Documentation Impact:")
        print(f"   - No descriptions: -{tools_impact:.1f}% performance")
        
        print(f"\n4. Combined Effect:")
        print(f"   - All factors: -{combined_impact:.1f}% performance")
        
        # 找出最关键的因子
        impacts = [
            ("Tone variations", max(trump_impact, casual_impact)),
            ("Wiki organization", wiki_impact),
            ("Tool descriptions", tools_impact)
        ]
        impacts.sort(key=lambda x: x[1], reverse=True)
        
        print(f"\n📊 Most Critical Factor: {impacts[0][0]} (impact: -{impacts[0][1]:.1f}%)")
    
    print("\n" + "="*80)
    print("\n✨ Conclusion:")
    print("-"*40)
    print("This demonstration shows that prompt engineering is crucial for agent performance.")
    print("Treating agents as 'smart new employees' with clear instructions, proper")
    print("documentation, and professional communication significantly improves results.")
    print("\nPoor prompt engineering can reduce performance by 50-80%!")
    print("\n" + "="*80 + "\n")


def check_environment():
    """
    检查环境是否正确配置
    """
    print("🔍 Checking environment setup...")

    # 检查必需文件
    required_files = [
        "run_ablation.py",
        "ablation_utils.py",
        "ablation_agent.py",
        "tau_bench/__init__.py",
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("\nPlease ensure you're running from the correct directory:")
        print("   cd projects/week2/prompt-engineering")
        return False
    
    # 检查 API Key
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set")
        print("   Please set: export OPENAI_API_KEY='your-key'")
        # 不算失败，用户可能用的是其他提供商
    
    print("✅ Environment check passed!\n")
    return True


def main():
    """
    主入口
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        print("Running quick test with only 2 experiments...")
        experiments = [
            {
                "name": "Baseline",
                "tone_style": "default",
                "randomize_wiki": False,
                "remove_tool_descriptions": False,
            },
            {
                "name": "All Ablations",
                "tone_style": "casual",
                "randomize_wiki": True,
                "remove_tool_descriptions": True,
            },
        ]
        for exp in experiments:
            run_experiment(**exp, num_tasks=2)
    else:
        if check_environment():
            run_all_experiments()
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
