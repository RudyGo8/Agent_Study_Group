"""
使用 Q-learning 的传统强化学习智能体。
演示需要大量训练的经典 RL 方法。
"""

import numpy as np
import pickle
from collections import defaultdict
from typing import Dict, List, Tuple, Any
import random
from game_environment import TreasureHuntGame


class QLearningAgent:
    """
    寻宝游戏专用的 Q-learning 智能体。
    采用基于状态-动作对的表格型 Q-learning。
    """

    def __init__(self,
                 learning_rate: float = 0.2,
                 discount_factor: float = 0.99,
                 epsilon: float = 1.0,
                 epsilon_decay: float = 0.9995,
                 epsilon_min: float = 0.1):
        """
        初始化 Q-learning 智能体。

        Args:
            learning_rate: Q 值更新的学习率（alpha）
            discount_factor: 未来奖励的折扣因子（gamma）
            epsilon: 初始探索率
            epsilon_decay: epsilon 的衰减速率
            epsilon_min: 最小探索率
        """
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min

        # Q 表：state_hash -> action -> Q 值
        self.q_table = defaultdict(lambda: defaultdict(float))

        # 统计信息
        self.episode_rewards = []
        self.episode_lengths = []
        self.episode_victories = []  # 每局胜负标记（1/0），用于学习曲线
        self.victories = 0
        self.total_episodes = 0
        self.learning_curve = []  # train() 在检查点记录的快照

    def _get_state_hash(self, game: TreasureHuntGame) -> str:
        """
        把游戏状态转成可哈希的表示。
        这对表格型 Q-learning 至关重要。
        """
        # 纳入相关的状态信息
        state_parts = [
            game.current_room.name,
            tuple(sorted([item.name for item in game.inventory])),
            tuple(sorted([item.name for item in game.current_room.items])),
            tuple(sorted(game.current_room.locked_exits.items())),
            game.current_room.has_guard and not game.current_room.guard_defeated
        ]
        
        return str(state_parts)
    
    def choose_action(self, game: TreasureHuntGame, training: bool = True) -> str:
        """
        使用 epsilon-greedy 策略选择动作。
        """
        available_actions = game.get_available_actions()

        if not available_actions:
            return "look around"

        # 探索与利用的权衡
        if training and random.random() < self.epsilon:
            # 探索：随机选动作
            return random.choice(available_actions)
        else:
            # 利用：按 Q 值选最优动作
            state_hash = self._get_state_hash(game)

            # 获取所有可用动作的 Q 值
            action_values = {
                action: self.q_table[state_hash][action]
                for action in available_actions
            }

            # 若所有 Q 值均为 0（未探索过），随机选择
            if all(v == 0 for v in action_values.values()):
                return random.choice(available_actions)

            # 选 Q 值最高的动作
            return max(action_values, key=action_values.get)
    
    def update_q_value(self, state: str, action: str, reward: float, 
                       next_state: str, next_actions: List[str], done: bool):
        """
        按 Q-learning 更新规则更新 Q 值。
        Q(s,a) <- Q(s,a) + α[r + γ max Q(s',a') - Q(s,a)]
        """
        current_q = self.q_table[state][action]

        if done:
            # 终止状态
            target = reward
        else:
            # 取下一状态的最大 Q 值
            if next_actions:
                max_next_q = max(
                    self.q_table[next_state][a] for a in next_actions
                )
            else:
                max_next_q = 0

            target = reward + self.discount_factor * max_next_q

        # 更新 Q 值
        self.q_table[state][action] = (
            current_q + self.learning_rate * (target - current_q)
        )
    
    def train_episode(self, game: TreasureHuntGame) -> Tuple[float, int, bool]:
        """
        训练一局。

        Returns:
            总奖励、步数、是否获胜
        """
        game.reset()
        total_reward = 0
        steps = 0

        while not game.game_over:
            # 获取当前状态
            state_hash = self._get_state_hash(game)

            # 选择动作
            action = self.choose_action(game, training=True)

            # 执行动作
            feedback, reward, done = game.execute_action(action)

            # 获取下一状态
            next_state_hash = self._get_state_hash(game)
            next_actions = game.get_available_actions() if not done else []

            # 更新 Q 值
            self.update_q_value(
                state_hash, action, reward,
                next_state_hash, next_actions, done
            )

            total_reward += reward
            steps += 1

        # 衰减 epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        # 更新统计
        self.episode_rewards.append(total_reward)
        self.episode_lengths.append(steps)
        self.episode_victories.append(1 if game.victory else 0)
        if game.victory:
            self.victories += 1
        self.total_episodes += 1

        return total_reward, steps, game.victory

    def train(self, num_episodes: int = 1000, verbose: bool = True,
              stochastic: bool = False, checkpoint_interval: int = 0) -> Dict[str, Any]:
        """
        训练多局。

        Args:
            num_episodes: 训练局数
            verbose: 是否打印进度
            stochastic: 是否使用随机环境
            checkpoint_interval: 若 > 0，每训练这么多局记录一次学习曲线快照
                （局数、滑动窗口胜率、Q 表大小、epsilon）。
                快照存入 self.learning_curve。
        """
        game = TreasureHuntGame(stochastic=stochastic)

        # 针对随机环境调整超参数
        if stochastic:
            # 随机环境下 epsilon 衰减略放缓
            original_decay = self.epsilon_decay
            self.epsilon_decay = min(0.9999, self.epsilon_decay * 1.001)
            if verbose:
                print(f"Adjusted epsilon_decay from {original_decay:.4f} to {self.epsilon_decay:.4f} for stochastic environment\n")
        
        window = checkpoint_interval if checkpoint_interval and checkpoint_interval > 0 else 1000

        for episode in range(num_episodes):
            reward, steps, victory = self.train_episode(game)

            # 在每个检查点记录学习曲线快照
            if checkpoint_interval and checkpoint_interval > 0 and (episode + 1) % checkpoint_interval == 0:
                recent = self.episode_victories[-window:]
                self.learning_curve.append({
                    "episode": episode + 1,
                    "victory_rate": sum(recent) / len(recent) if recent else 0.0,
                    "q_table_size": len(self.q_table),
                    "epsilon": self.epsilon,
                })

            if verbose and (episode + 1) % 100 == 0:
                recent_rewards = self.episode_rewards[-100:]
                recent_victories = sum(
                    1 for r in recent_rewards if r > 50  # 以奖励 > 50 近似判定获胜
                )
                avg_reward = np.mean(recent_rewards)
                
                print(f"Episode {episode + 1}/{num_episodes}")
                print(f"  Avg Reward (last 100): {avg_reward:.2f}")
                print(f"  Victories (last 100): {recent_victories}")
                print(f"  Epsilon: {self.epsilon:.3f}")
                print(f"  Q-table size: {len(self.q_table)}")
                print()
        
        return {
            "total_episodes": self.total_episodes,
            "total_victories": self.victories,
            "victory_rate": self.victories / self.total_episodes if self.total_episodes else 0.0,
            "final_epsilon": self.epsilon,
            "q_table_size": len(self.q_table),
            "episode_rewards": self.episode_rewards,
            "episode_lengths": self.episode_lengths,
            "learning_curve": self.learning_curve,
        }

    def evaluate(self, num_episodes: int = 100, verbose: bool = False, stochastic: bool = False) -> Dict[str, Any]:
        """
        不再学习，直接评估训练好的智能体。

        Args:
            num_episodes: 评估局数
            verbose: 是否打印细节
            stochastic: 是否使用随机环境
        """
        game = TreasureHuntGame(stochastic=stochastic)
        eval_rewards = []
        eval_lengths = []
        eval_victories = 0

        # 保存原 epsilon 并置 0 用于评估
        original_epsilon = self.epsilon
        self.epsilon = 0
        
        for episode in range(num_episodes):
            game.reset()
            total_reward = 0
            steps = 0
            
            while not game.game_over:
                action = self.choose_action(game, training=False)
                feedback, reward, done = game.execute_action(action)
                total_reward += reward
                steps += 1
                
                if verbose and episode == 0:  # 只展示第一局评估
                    print(f"Step {steps}: {action}")
                    print(f"Feedback: {feedback}")
                    print()
            
            eval_rewards.append(total_reward)
            eval_lengths.append(steps)
            if game.victory:
                eval_victories += 1
        
        # 恢复 epsilon
        self.epsilon = original_epsilon
        
        return {
            "num_episodes": num_episodes,
            "victories": eval_victories,
            "victory_rate": eval_victories / num_episodes if num_episodes else 0.0,
            "avg_reward": sum(eval_rewards) / len(eval_rewards) if len(eval_rewards) > 0 else 0.0,
            "std_reward": float(np.std(eval_rewards)) if len(eval_rewards) > 0 else 0.0,
            "avg_length": sum(eval_lengths) / len(eval_lengths) if len(eval_lengths) > 0 else 0.0,
            "std_length": float(np.std(eval_lengths)) if len(eval_lengths) > 0 else 0.0
        }
    
    def save(self, filepath: str):
        """保存 Q 表和参数。"""
        data = {
            "q_table": dict(self.q_table),
            "epsilon": self.epsilon,
            "learning_rate": self.learning_rate,
            "discount_factor": self.discount_factor,
            "statistics": {
                "total_episodes": self.total_episodes,
                "victories": self.victories,
                "episode_rewards": self.episode_rewards,
                "episode_lengths": self.episode_lengths
            }
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
    
    def load(self, filepath: str):
        """加载已保存的 Q 表和参数。"""
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        
        self.q_table = defaultdict(lambda: defaultdict(float))
        for state, actions in data["q_table"].items():
            for action, value in actions.items():
                self.q_table[state][action] = value
        
        self.epsilon = data["epsilon"]
        self.learning_rate = data["learning_rate"]
        self.discount_factor = data["discount_factor"]
        
        stats = data.get("statistics", {})
        self.total_episodes = stats.get("total_episodes", 0)
        self.victories = stats.get("victories", 0)
        self.episode_rewards = stats.get("episode_rewards", [])
        self.episode_lengths = stats.get("episode_lengths", [])


class DQNAgent:
    """
    用于对比的 Deep Q-Network 智能体。
    用神经网络做函数逼近，而非表格型 Q-learning。
    """
    
    def __init__(self, 
                 state_dim: int = 128,
                 hidden_dim: int = 256,
                 learning_rate: float = 0.001,
                 discount_factor: float = 0.95,
                 epsilon: float = 1.0,
                 epsilon_decay: float = 0.995,
                 epsilon_min: float = 0.01,
                 batch_size: int = 32,
                 memory_size: int = 10000):
        """
        初始化带神经网络的 DQN 智能体。
        注意：为演示而做的简化实现。
        """
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.batch_size = batch_size
        
        # 经验回放缓冲区
        self.memory = []
        self.memory_size = memory_size

        # 统计信息
        self.episode_rewards = []
        self.episode_lengths = []
        self.victories = 0
        self.total_episodes = 0
        
        # 注：完整实现应使用 PyTorch 或 TensorFlow
        # 这里只是简化的占位实现
        print("Note: DQN implementation requires neural network library.")
        print("Using simplified random policy for demonstration.")
    
    def choose_action(self, game: TreasureHuntGame, training: bool = True) -> str:
        """选择动作（演示用简化版）。"""
        available_actions = game.get_available_actions()
        if not available_actions:
            return "look around"

        # 简化处理：只做带随机选择的 epsilon-greedy
        if training and random.random() < self.epsilon:
            return random.choice(available_actions)
        else:
            # 完整实现中，这里应走神经网络
            return random.choice(available_actions)

    def train_episode(self, game: TreasureHuntGame) -> Tuple[float, int, bool]:
        """训练一局（简化版）。"""
        game.reset()
        total_reward = 0
        steps = 0
        
        while not game.game_over:
            action = self.choose_action(game, training=True)
            feedback, reward, done = game.execute_action(action)
            total_reward += reward
            steps += 1
        
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        self.episode_rewards.append(total_reward)
        self.episode_lengths.append(steps)
        if game.victory:
            self.victories += 1
        self.total_episodes += 1
        
        return total_reward, steps, game.victory
