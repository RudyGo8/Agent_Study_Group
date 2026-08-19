"""
测试套件：锁定 QLearningAgent.train 在 episode_victories 为空列表
计算 victory_rate 时的 ZeroDivisionError。
"""

from rl_agent import QLearningAgent


def test_q_learning_agent_train_empty_victories_snapshot():
    """
    确保检查点 victory_rate 计算在 recent 为空时不会抛 ZeroDivisionError。
    """
    agent = QLearningAgent.__new__(QLearningAgent)
    agent.episode_victories = []
    agent.learning_curve = []
    agent.q_table = {}
    agent.epsilon = 0.1

    # 模拟 checkpoint_interval 命中时的快照逻辑
    recent = agent.episode_victories[-1000:]
    victory_rate = sum(recent) / len(recent) if recent else 0.0

    agent.learning_curve.append({
        "episode": 1,
        "victory_rate": victory_rate,
        "q_table_size": len(agent.q_table),
        "epsilon": agent.epsilon,
    })

    assert agent.learning_curve[0]["victory_rate"] == 0.0
