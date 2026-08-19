"""
对比传统 RL 与基于 LLM 的上下文学习的实验运行器。
复现 "The Second Half" 博文中的核心观点。
"""

import os
import json
import time
import random
import argparse
from datetime import datetime
from typing import Dict, Any, List
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()

from game_environment import TreasureHuntGame
from rl_agent import QLearningAgent
from llm_agent import LLMAgent


class ExperimentRunner:
    """
    运行对比不同学习方法的实验。
    """

    def __init__(self, results_dir: str = "results"):
        """初始化实验运行器。"""
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # 为本次实验运行创建时间戳
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.experiment_dir = self.results_dir / self.timestamp
        self.experiment_dir.mkdir(exist_ok=True)
        
        self.results = {}
    
    def run_rl_experiment(self,
                         num_training_episodes: int = 10000,
                         num_eval_episodes: int = 100,
                         verbose: bool = True,
                         stochastic: bool = False,
                         learning_rate: float = 0.2,
                         discount_factor: float = 0.99,
                         epsilon_decay: float = 0.9995,
                         epsilon_min: float = 0.1,
                         checkpoint_interval: int = 1000) -> Dict[str, Any]:
        """
        用传统 Q-learning 智能体跑实验。

        Args:
            num_training_episodes: 训练局数
            num_eval_episodes: 评估局数
            verbose: 是否打印细节
            stochastic: 是否使用随机环境
            learning_rate: Q-learning 学习率（alpha）
            discount_factor: 折扣因子（gamma）
            epsilon_decay: 每局的 epsilon 衰减系数
            epsilon_min: 最小探索率
            checkpoint_interval: 每 N 局记录/打印一行学习曲线
        """
        print("\n" + "="*60)
        print("TRADITIONAL RL EXPERIMENT (Q-Learning)")
        print("="*60)

        # 用给定超参数初始化智能体
        agent = QLearningAgent(
            learning_rate=learning_rate,
            discount_factor=discount_factor,
            epsilon=1.0,
            epsilon_decay=epsilon_decay,
            epsilon_min=epsilon_min
        )

        # 训练阶段
        print(f"\nTraining for {num_training_episodes} episodes...")
        start_time = time.time()

        train_results = agent.train(
            num_episodes=num_training_episodes,
            verbose=verbose,
            stochastic=stochastic,
            checkpoint_interval=checkpoint_interval
        )

        training_time = time.time() - start_time

        # 展示学习曲线（胜率随局数的变化）——这是实验 7-1 的核心：
        # 智能体在经验中缓慢地"学习"。
        self._print_learning_curve(train_results.get("learning_curve", []),
                                    checkpoint_interval)

        # 评估阶段
        print(f"\nEvaluating on {num_eval_episodes} episodes...")
        eval_results = agent.evaluate(
            num_episodes=num_eval_episodes,
            verbose=False,
            stochastic=stochastic
        )

        # 汇总结果
        results = {
            "method": "Q-Learning",
            "training_episodes": num_training_episodes,
            "training_time": training_time,
            "q_table_size": train_results["q_table_size"],
            "training_victories": train_results["total_victories"],
            "training_victory_rate": train_results["victory_rate"],
            "eval_victories": eval_results["victories"],
            "eval_victory_rate": eval_results["victory_rate"],
            "eval_avg_reward": eval_results["avg_reward"],
            "eval_avg_steps": eval_results["avg_length"],
            "episode_rewards": train_results["episode_rewards"],
            "episode_lengths": train_results["episode_lengths"],
            "learning_curve": train_results.get("learning_curve", [])
        }

        # 保存智能体
        agent.save(self.experiment_dir / "rl_agent.pkl")
        
        print(f"\nRL Training Summary:")
        print(f"  Training time: {training_time:.2f} seconds")
        print(f"  Q-table size: {train_results['q_table_size']} states")
        print(f"  Training victory rate: {train_results['victory_rate']:.2%}")
        print(f"  Evaluation victory rate: {eval_results['victory_rate']:.2%}")
        
        return results
    
    def _print_learning_curve(self, learning_curve: List[Dict[str, Any]],
                              checkpoint_interval: int):
        """打印 Q-learning 胜率随局数变化的表格。

        这正是实验 7-1 的意义所在：观察胜率从 0%（盲目探索）
        经数千局之后才爬升到约 100%。
        """
        if not learning_curve:
            return

        window = checkpoint_interval if checkpoint_interval > 0 else 1000
        print("\n" + "-"*60)
        print(f"LEARNING CURVE (Q-Learning success rate over episodes)")
        print(f"胜率按最近 {window} 局的滑动窗口统计")
        print("-"*60)
        print(f"{'Episodes':>10} | {'Victory rate':>12} | {'Q-table':>8} | {'epsilon':>8}")
        print(f"{'-'*10}-+-{'-'*12}-+-{'-'*8}-+-{'-'*8}")
        for row in learning_curve:
            print(f"{row['episode']:>10} | {row['victory_rate']*100:>11.1f}% | "
                  f"{row['q_table_size']:>8} | {row['epsilon']:>8.3f}")
        print("-"*60)

    def run_llm_experiment(self,
                          num_training_episodes: int = 20,
                          num_eval_episodes: int = 10,
                          verbose: bool = True,
                          stochastic: bool = False,
                          model: str = "kimi-k3") -> Dict[str, Any]:
        """
        用基于 LLM 上下文学习的智能体跑实验。

        Args:
            num_training_episodes: 训练局数
            num_eval_episodes: 评估局数
            verbose: 是否打印细节
            stochastic: 是否使用随机环境
        """
        print("\n" + "="*70)
        print(f"LLM-BASED IN-CONTEXT LEARNING EXPERIMENT ({model})")
        print("="*70)

        # 检查 API key
        provider = os.getenv("LLM_PROVIDER", "moonshot").lower()
        api_key = os.getenv("DASHSCOPE_API_KEY") if provider in {"dashscope", "qwen", "bailian"} else os.getenv("MOONSHOT_API_KEY")
        if not api_key and not os.getenv("OPENROUTER_API_KEY"):
            print(f"\n⚠️ Warning: API key for provider '{provider}' not set. Skipping LLM experiment.")
            print("📝 Set DASHSCOPE_API_KEY for dashscope/qwen/bailian or MOONSHOT_API_KEY for moonshot/kimi")
            print("🔗 Get your key at: https://platform.moonshot.cn/")
            print("💡 Or set OPENROUTER_API_KEY as a universal fallback.")
            return None

        print("\n✅ API key found. Initializing LLM agent...")
        print(f"🧠 Using {model} model for reasoning and in-context learning")
        print("📖 The LLM will show its complete thought process for each decision")

        # 初始化智能体
        agent = LLMAgent(
            api_key=api_key,
            model=model,
            provider=provider,
            temperature=0.7,
            max_experiences=50
        )
        
        # 训练阶段（收集经验）
        print(f"\n🎓 Training Phase: Playing {num_training_episodes} episodes")
        print("💡 Watch how the LLM learns from experience without any parameter updates!")
        print("-"*70)
        
        start_time = time.time()
        
        train_results = agent.train(
            num_episodes=num_training_episodes,
            verbose=verbose,
            stochastic=stochastic
        )
        
        training_time = time.time() - start_time

        # 评估阶段
        print(f"\nEvaluating on {num_eval_episodes} episodes...")
        eval_results = agent.evaluate(
            num_episodes=num_eval_episodes,
            verbose=False,
            stochastic=stochastic
        )

        # 汇总结果
        results = {
            "method": "LLM In-Context Learning",
            "provider": agent.provider,
            "base_url": agent.base_url,
            "model": agent.model,
            "using_openrouter": agent.using_openrouter,
            "training_episodes": num_training_episodes,
            "evaluation_episodes": num_eval_episodes,
            "training_time": training_time,
            "experiences_collected": train_results["experiences_collected"],
            "api_calls": agent.api_calls,
            "api_attempts": len(agent.api_records),
            "api_errors": sum(1 for item in agent.api_records if item.get("error")),
            "fallback_actions": sum(
                1 for item in agent.api_records if item.get("fallback_used")
            ),
            "total_tokens": agent.total_tokens,
            "training_victories": train_results["total_victories"],
            "training_victory_rate": train_results["victory_rate"],
            "eval_victories": eval_results["victories"],
            "eval_victory_rate": eval_results["victory_rate"],
            "eval_avg_reward": eval_results["avg_reward"],
            "eval_avg_steps": eval_results["avg_length"],
            "episode_rewards": train_results["episode_rewards"],
            "episode_lengths": train_results["episode_lengths"],
            "training_trajectories": [
                item for item in agent.episode_trajectories
                if item["phase"] == "training"
            ],
        }
        
        # 保存经验
        agent.save_experiences(self.experiment_dir / "llm_experiences.json")
        
        print(f"\nLLM Training Summary:")
        print(f"  Training time: {training_time:.2f} seconds")
        print(f"  Experiences collected: {train_results['experiences_collected']}")
        print(f"  API calls: {train_results['total_api_calls']}")
        print(f"  Training victory rate: {train_results['victory_rate']:.2%}")
        print(f"  Evaluation victory rate: {eval_results['victory_rate']:.2%}")
        
        return results
    
    def compare_learning_curves(self, rl_results: Dict, llm_results: Dict):
        """
        生成对比两种方法学习曲线的可视化图。
        """
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # 图 1：胜率随局数的变化
        ax = axes[0, 0]

        # RL 胜率（按窗口计算）
        rl_rewards = rl_results["episode_rewards"]
        window_size = 100
        rl_victories = []
        for i in range(0, len(rl_rewards), window_size):
            window = rl_rewards[i:i+window_size]
            victories = sum(1 for r in window if r > 50) / len(window)
            rl_victories.append(victories)
        
        ax.plot(range(0, len(rl_rewards), window_size), rl_victories, 
                label=f"Q-Learning ({len(rl_rewards)} episodes)", linewidth=2)
        
        # LLM 胜率（逐局）
        if llm_results:
            llm_rewards = llm_results["episode_rewards"]
            llm_victories = [1 if r > 50 else 0 for r in llm_rewards]
            llm_cumulative = np.cumsum(llm_victories) / (np.arange(len(llm_victories)) + 1)
            ax.plot(range(len(llm_cumulative)), llm_cumulative,
                   label=f"LLM In-Context ({len(llm_rewards)} episodes)", linewidth=2)
        
        ax.set_xlabel("Episodes")
        ax.set_ylabel("Victory Rate")
        ax.set_title("Learning Progress: Victory Rate Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 图 2：平均奖励随局数的变化
        ax = axes[0, 1]

        # RL 奖励（平滑后）
        rl_smooth = []
        for i in range(0, len(rl_rewards), window_size):
            window = rl_rewards[i:i+window_size]
            rl_smooth.append(np.mean(window))
        
        ax.plot(range(0, len(rl_rewards), window_size), rl_smooth,
                label="Q-Learning", linewidth=2)
        
        # LLM 奖励
        if llm_results:
            llm_rewards = llm_results["episode_rewards"]
            ax.plot(range(len(llm_rewards)), llm_rewards,
                   label="LLM In-Context", linewidth=2, alpha=0.7)
        
        ax.set_xlabel("Episodes")
        ax.set_ylabel("Episode Reward")
        ax.set_title("Learning Progress: Reward Over Time")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 图 3：样本效率对比
        ax = axes[1, 0]
        
        categories = ["Training\nEpisodes", "Evaluation\nVictory Rate", "Training\nTime (s)"]
        rl_values = [
            rl_results["training_episodes"],
            rl_results["eval_victory_rate"] * 100,
            rl_results["training_time"]
        ]
        
        if llm_results:
            llm_values = [
                llm_results["training_episodes"],
                llm_results["eval_victory_rate"] * 100,
                llm_results["training_time"]
            ]
        else:
            llm_values = [0, 0, 0]
        
        x = np.arange(len(categories))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, rl_values, width, label='Q-Learning')
        bars2 = ax.bar(x + width/2, llm_values, width, label='LLM In-Context')
        
        ax.set_ylabel('Value')
        ax.set_title('Sample Efficiency Comparison')
        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        ax.legend()
        
        # 在柱子上标注数值
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f'{height:.1f}',
                           xy=(bar.get_x() + bar.get_width() / 2, height),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom')
        
        # 图 4：关键结论文字
        ax = axes[1, 1]
        ax.axis('off')
        
        insights = [
            "KEY INSIGHTS (Replicating 'The Second Half' Findings):",
            "",
            "1. SAMPLE EFFICIENCY:",
            f"   • Q-Learning: {rl_results['training_episodes']} episodes needed",
            f"   • LLM: {llm_results['training_episodes'] if llm_results else 'N/A'} episodes needed",
            f"   • Improvement: {rl_results['training_episodes'] / (llm_results['training_episodes'] if llm_results and llm_results['training_episodes'] > 0 else 1):.1f}x fewer samples",
            "",
            "2. GENERALIZATION:",
            "   • Q-Learning: Learns specific state-action mappings",
            "   • LLM: Reasons about patterns and transfers knowledge",
            "",
            "3. HIDDEN MECHANICS DISCOVERY:",
            "   • Q-Learning: Requires extensive exploration",
            "   • LLM: Can hypothesize and test theories",
            "",
            "4. COMPUTATIONAL TRADE-OFF:",
            f"   • Q-Learning: Fast inference, slow learning",
            f"   • LLM: Slower inference (API calls), fast adaptation"
        ]
        
        y_pos = 0.9
        for line in insights:
            if line.startswith("KEY INSIGHTS"):
                ax.text(0.5, y_pos, line, transform=ax.transAxes,
                       fontsize=12, fontweight='bold', ha='center')
            elif line.startswith(("1.", "2.", "3.", "4.")):
                ax.text(0.1, y_pos, line, transform=ax.transAxes,
                       fontsize=11, fontweight='bold')
            else:
                ax.text(0.1, y_pos, line, transform=ax.transAxes,
                       fontsize=10)
            y_pos -= 0.06
        
        plt.tight_layout()
        plt.savefig(self.experiment_dir / "comparison_plots.png", dpi=150)
        plt.show()
        
        print(f"\nPlots saved to {self.experiment_dir / 'comparison_plots.png'}")
    
    def run_full_experiment(self,
                           rl_episodes: int = 10000,
                           llm_episodes: int = 20,
                           eval_episodes: int = 100,
                           verbose: bool = False,
                           stochastic: bool = False,
                           model: str = "kimi-k3",
                           checkpoint_interval: int = 1000,
                           rl_hyperparams: Dict[str, float] = None):
        """
        运行完整的对比实验。

        Args:
            rl_episodes: RL 训练局数
            llm_episodes: LLM 训练局数
            eval_episodes: RL 评估局数
            verbose: 是否打印细节
            stochastic: 是否使用随机环境
            model: LLM 模型名（Moonshot/Kimi）
            checkpoint_interval: 学习曲线采样间隔（RL）
            rl_hyperparams: 可选字典，用于覆盖 Q-learning 超参数
        """
        print("\n" + "="*70)
        print("EXPERIMENT: Traditional RL vs LLM In-Context Learning")
        print("Replicating insights from 'The Second Half' by Shunyu Yao")
        print("="*70)

        # 展示游戏规则供参考
        game = TreasureHuntGame(stochastic=stochastic)
        print("\n" + game.get_hidden_rules())

        rl_hyperparams = rl_hyperparams or {}

        # 跑 RL 实验
        rl_results = self.run_rl_experiment(
            num_training_episodes=rl_episodes,
            num_eval_episodes=eval_episodes,
            verbose=verbose,
            stochastic=stochastic,
            checkpoint_interval=checkpoint_interval,
            **rl_hyperparams
        )
        self.results["rl"] = rl_results

        # 跑 LLM 实验
        llm_results = self.run_llm_experiment(
            num_training_episodes=llm_episodes,
            num_eval_episodes=10,
            verbose=verbose,
            stochastic=stochastic,
            model=model
        )
        self.results["llm"] = llm_results

        # 保存合并结果
        with open(self.experiment_dir / "experiment_results.json", 'w') as f:
            json.dump(self.results, f, indent=2)

        # 生成对比图
        if llm_results:
            self.compare_learning_curves(rl_results, llm_results)

        # 打印最终对比
        print("\n" + "="*70)
        print("EXPERIMENT RESULTS SUMMARY")
        print("="*70)
        
        print("\n1. SAMPLE EFFICIENCY:")
        print(f"   Q-Learning needed {rl_results['training_episodes']} episodes")
        if llm_results:
            print(f"   LLM needed {llm_results['training_episodes']} episodes")
            print(f"   → LLM is {rl_results['training_episodes'] / llm_results['training_episodes']:.1f}x more sample efficient")
        
        print("\n2. PERFORMANCE:")
        print(f"   Q-Learning eval victory rate: {rl_results['eval_victory_rate']:.2%}")
        if llm_results:
            print(f"   LLM eval victory rate: {llm_results['eval_victory_rate']:.2%}")
        
        print("\n3. COMPUTATIONAL COST:")
        print(f"   Q-Learning: {rl_results['training_time']:.2f} seconds, {rl_results['q_table_size']} states")
        if llm_results:
            print(f"   LLM: {llm_results['training_time']:.2f} seconds, {llm_results['api_calls']} API calls")
        
        print(f"\nResults saved to: {self.experiment_dir}")
        
        return self.results


def main():
    """实验入口。"""
    parser = argparse.ArgumentParser(
        description="实验 7-1 / 7-2：在寻宝游戏中对比 Q-learning 与 LLM 的\"从经验中学习\"。"
                    "Q-learning 完全离线运行（无需 API），LLM 模式需要 Moonshot/Kimi API Key。",
        epilog="示例：\n"
               "  python experiment.py --mode qlearning              # 只跑 Q-learning（离线，输出学习曲线）\n"
               "  python experiment.py --mode qlearning --rl-episodes 10000 --seed 42\n"
               "  python experiment.py --mode both --model kimi-k3  # RL vs LLM 对比\n"
               "  python experiment.py --mode llm --llm-episodes 20   # 只跑 LLM 智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--mode", choices=["both", "qlearning", "rl", "llm"], default="both",
        help="运行哪种智能体：qlearning/rl 只跑 Q-learning（离线），"
             "llm 只跑 LLM 智能体（需 API），both 两者对比（默认）"
    )
    parser.add_argument(
        "--rl-episodes", type=int, default=10000,
        help="Q-learning 训练局数（默认 10000，对应实验 7-1）"
    )
    parser.add_argument(
        "--llm-episodes", type=int, default=20,
        help="LLM 智能体的训练局数（默认 20）"
    )
    parser.add_argument(
        "--eval-episodes", type=int, default=100,
        help="Q-learning 训练后贪婪评估的局数（默认 100）"
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=1000,
        help="学习曲线采样间隔：每 N 局记录一次胜率/Q 表规模（默认 1000）"
    )
    parser.add_argument(
        "--model", type=str, default=os.getenv("MOONSHOT_MODEL", "kimi-k3"),
        help="LLM 模型名称（Moonshot/Kimi，默认 kimi-k3，可用 MOONSHOT_MODEL 环境变量覆盖）"
    )
    parser.add_argument(
        "--output", type=str, default="results",
        help="结果输出目录（默认 results/，每次运行会新建时间戳子目录）"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="随机种子，用于复现 Q-learning 的学习曲线（默认不固定）"
    )
    # Q-learning 超参数
    parser.add_argument("--learning-rate", type=float, default=0.2,
                        help="Q-learning 学习率 alpha（默认 0.2）")
    parser.add_argument("--discount", type=float, default=0.99,
                        help="折扣因子 gamma（默认 0.99）")
    parser.add_argument("--epsilon-decay", type=float, default=0.9995,
                        help="每局 epsilon 衰减系数（默认 0.9995）")
    parser.add_argument("--epsilon-min", type=float, default=0.1,
                        help="最小探索率 epsilon（默认 0.1）")
    parser.add_argument(
        "--verbose", action="store_true",
        help="训练过程中打印详细信息"
    )
    parser.add_argument(
        "--skip-llm", action="store_true",
        help="[兼容旧用法] 跳过 LLM 实验，等价于 --mode qlearning"
    )
    parser.add_argument(
        "--stochastic", action="store_true",
        help="使用随机环境（奖励与动作带随机扰动）"
    )
    parser.add_argument(
        "--deterministic", action="store_true",
        help="使用确定性环境（默认）"
    )

    args = parser.parse_args()

    # 处理环境模式
    if args.deterministic and args.stochastic:
        print("Error: Cannot specify both --deterministic and --stochastic")
        return

    # 局数必须为正；若为 0，train/evaluate 计算胜率和均值时会除零。
    if args.rl_episodes < 1 or args.llm_episodes < 1 or args.eval_episodes < 1:
        print("Error: --rl-episodes, --llm-episodes and --eval-episodes must all be >= 1")
        return

    # 解析运行模式（--skip-llm 保留为向后兼容的别名）
    mode = "qlearning" if args.skip_llm else args.mode

    # 固定种子以复现 Q-learning 学习曲线
    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        print(f"\n🎲 Random seed set to {args.seed} for reproducibility")

    stochastic = args.stochastic  # 默认为 False（确定性）

    if stochastic:
        print("\n🎲 Running experiment with STOCHASTIC environment")
        print("  - Random reward variations")
        print("  - 3% chance of action failure")
        print("  - Combat and crafting variations\n")
    else:
        print("\n🎯 Running experiment with DETERMINISTIC environment\n")

    rl_hyperparams = {
        "learning_rate": args.learning_rate,
        "discount_factor": args.discount,
        "epsilon_decay": args.epsilon_decay,
        "epsilon_min": args.epsilon_min,
    }

    # 运行实验
    runner = ExperimentRunner(results_dir=args.output)

    if mode in ("qlearning", "rl"):
        # 只跑 Q-learning 实验（完全离线，无需 API）
        rl_results = runner.run_rl_experiment(
            num_training_episodes=args.rl_episodes,
            num_eval_episodes=args.eval_episodes,
            verbose=args.verbose,
            stochastic=stochastic,
            checkpoint_interval=args.checkpoint_interval,
            **rl_hyperparams
        )
        runner.results["rl"] = rl_results
        with open(runner.experiment_dir / "experiment_results.json", 'w') as f:
            json.dump(runner.results, f, indent=2)
        print(f"\nResults saved to: {runner.experiment_dir}")
        print("\nSkipped LLM experiment. Use --mode both with an API key to compare.")
    elif mode == "llm":
        # 只跑 LLM 实验
        llm_results = runner.run_llm_experiment(
            num_training_episodes=args.llm_episodes,
            verbose=args.verbose,
            stochastic=stochastic,
            model=args.model
        )
        runner.results["llm"] = llm_results
        with open(runner.experiment_dir / "experiment_results.json", 'w') as f:
            json.dump(runner.results, f, indent=2)
        print(f"\nResults saved to: {runner.experiment_dir}")
    else:
        # 跑完整对比
        results = runner.run_full_experiment(
            rl_episodes=args.rl_episodes,
            llm_episodes=args.llm_episodes,
            eval_episodes=args.eval_episodes,
            verbose=args.verbose,
            stochastic=stochastic,
            model=args.model,
            checkpoint_interval=args.checkpoint_interval,
            rl_hyperparams=rl_hyperparams
        )

    print("\nExperiment complete!")


if __name__ == "__main__":
    main()
