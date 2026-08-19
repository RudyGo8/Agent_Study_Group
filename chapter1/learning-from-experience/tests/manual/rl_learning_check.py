#!/usr/bin/env python3
"""
手动验证脚本：检验 Q-learning 能学会这个简化游戏。
"""

import sys
import argparse
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game_environment import TreasureHuntGame
from rl_agent import QLearningAgent


def run_rl_learning_check(stochastic=False, episodes=None):
    """检验 Q-learning 能否学会这个游戏。

    Args:
        stochastic: 若为 True，使用随机环境
        episodes: 要测试的局数列表（默认：多个不同局数）
    """
    env_type = "STOCHASTIC" if stochastic else "DETERMINISTIC"
    print(f"Testing Q-Learning on simplified game ({env_type} environment)...")
    print("="*50)
    
    # 展示游戏规则
    game = TreasureHuntGame(stochastic=stochastic)
    print(game.get_hidden_rules())
    if stochastic:
        print("\n⚠️  Stochastic Mode Active:")
        print("  - Random reward variations")
        print("  - 3% chance of action failure")
        print("  - 10% critical hit / 5% miss chance in combat")
        print("  - 10% crafting failure chance")
    print("\n" + "="*50)
    
    # 初始化智能体
    agent = QLearningAgent(
        learning_rate=0.2,
        discount_factor=0.99,
        epsilon=1.0,
        epsilon_decay=0.9997,  # 衰减更慢，便于探索
        epsilon_min=0.1
    )

    # 按不同局数分别训练
    if episodes:
        episode_counts = episodes
    else:
        episode_counts = [100, 500, 1000, 2000, 5000, 10000]

    for num_episodes in episode_counts:
        print(f"\nTraining for {num_episodes} episodes...")

        # 重置智能体
        agent = QLearningAgent(
            learning_rate=0.2,
            discount_factor=0.99,
            epsilon=1.0,
            epsilon_decay=0.9997,
            epsilon_min=0.1
        )

        # 训练
        game = TreasureHuntGame(stochastic=stochastic)
        victories = 0
        recent_rewards = []
        
        for episode in range(num_episodes):
            game.reset()
            total_reward = 0
            
            while not game.game_over:
                state_hash = agent._get_state_hash(game)
                action = agent.choose_action(game, training=True)
                feedback, reward, done = game.execute_action(action)
                
                next_state_hash = agent._get_state_hash(game)
                next_actions = game.get_available_actions() if not done else []
                
                agent.update_q_value(
                    state_hash, action, reward, 
                    next_state_hash, next_actions, done
                )
                
                total_reward += reward
            
            # 衰减 epsilon
            agent.epsilon = max(agent.epsilon_min, agent.epsilon * agent.epsilon_decay)

            recent_rewards.append(total_reward)
            if game.victory:
                victories += 1

            # 打印进度
            progress_every = max(1, num_episodes // 10)
            if (episode + 1) % progress_every == 0:
                recent_wins = sum(1 for r in recent_rewards[-100:] if r > 50)
                avg_reward = np.mean(recent_rewards[-100:]) if recent_rewards else 0
                print(f"  Episode {episode+1}: Recent wins={recent_wins}/100, "
                      f"Avg reward={avg_reward:.1f}, Epsilon={agent.epsilon:.3f}")
        
        # 评估
        print(f"\nEvaluating after {num_episodes} episodes...")
        eval_victories = 0
        eval_rewards = []
        
        for _ in range(100):
            game.reset()
            total_reward = 0
            
            # 评估时把 epsilon 置 0
            old_epsilon = agent.epsilon
            agent.epsilon = 0
            
            while not game.game_over:
                action = agent.choose_action(game, training=False)
                feedback, reward, done = game.execute_action(action)
                total_reward += reward
            
            agent.epsilon = old_epsilon
            
            eval_rewards.append(total_reward)
            if game.victory:
                eval_victories += 1
        
        print(f"  Evaluation: {eval_victories}/100 victories")
        print(f"  Average reward: {np.mean(eval_rewards):.2f}")
        print(f"  Q-table size: {len(agent.q_table)} states")
        
        # 若有胜局，展示一条成功轨迹
        if eval_victories > 0:
            print("\n  Sample successful trajectory:")
            game.reset()
            agent.epsilon = 0
            steps = []
            
            while not game.game_over:
                action = agent.choose_action(game, training=False)
                steps.append(f"    {len(steps)+1}. {action}")
                feedback, reward, done = game.execute_action(action)
                if game.victory:
                    steps.append(f"    → Victory! Total moves: {game.moves}")
                    break
            
            if len(steps) <= 20:  # 步数合理才展示
                print("\n".join(steps[:15]))  # 只展示前 15 步


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Q-learning agent on the treasure hunt game")
    parser.add_argument(
        '--stochastic', 
        action='store_true',
        help='Use stochastic environment (adds randomness to rewards and actions)'
    )
    parser.add_argument(
        '--deterministic',
        action='store_true',
        help='Use deterministic environment (default)'
    )
    parser.add_argument(
        '--episodes',
        type=int,
        nargs='+',
        help='Episode counts to test (e.g., --episodes 1000 5000 10000)'
    )
    
    args = parser.parse_args()

    # 处理环境模式
    if args.deterministic and args.stochastic:
        print("Error: Cannot specify both --deterministic and --stochastic")
        sys.exit(1)

    stochastic = args.stochastic  # 默认为 False（确定性）
    
    run_rl_learning_check(stochastic=stochastic, episodes=args.episodes)
