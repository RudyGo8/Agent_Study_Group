#!/usr/bin/env python3
"""
基础测试：验证各组件都能正常工作。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_game_environment():
    """测试游戏环境可用。"""
    print("Testing game environment...")
    from game_environment import TreasureHuntGame

    game = TreasureHuntGame(seed=42)

    # 测试初始状态
    state = game.get_state_description()
    assert "entrance" in state.lower()
    print("  ✓ Game initialization works")

    # 测试动作
    actions = game.get_available_actions()
    assert len(actions) > 0
    print("  ✓ Actions generation works")

    # 测试动作执行
    feedback, reward, done = game.execute_action("look around")
    assert isinstance(feedback, str)
    assert isinstance(reward, float)
    assert isinstance(done, bool)
    print("  ✓ Action execution works")

    # 测试重置
    game.reset()
    assert game.moves == 0
    print("  ✓ Game reset works")
    
    print("✅ Game environment tests passed!\n")


def test_rl_agent():
    """测试 RL 智能体可用。"""
    print("Testing RL agent...")
    from game_environment import TreasureHuntGame
    from rl_agent import QLearningAgent

    game = TreasureHuntGame(seed=42)
    agent = QLearningAgent()

    # 测试动作选择
    action = agent.choose_action(game, training=True)
    assert isinstance(action, str)
    print("  ✓ Action selection works")

    # 测试 Q 值更新
    state = agent._get_state_hash(game)
    feedback, reward, done = game.execute_action(action)
    next_state = agent._get_state_hash(game)
    next_actions = game.get_available_actions()

    agent.update_q_value(state, action, reward, next_state, next_actions, done)
    print("  ✓ Q-value update works")

    # 测试训练（为提速只跑 10 局）
    results = agent.train(num_episodes=10, verbose=False)
    assert "total_episodes" in results
    print("  ✓ Training works")
    
    print("✅ RL agent tests passed!\n")


def test_llm_agent():
    """测试 LLM 智能体可用（不调用 API）。"""
    print("Testing LLM agent structure...")
    from game_environment import TreasureHuntGame
    from llm_agent import LLMAgent, GameExperience

    # 测试经验存储
    exp = GameExperience(
        state_description="test state",
        action="test action",
        feedback="test feedback",
        reward=1.0,
        success=True
    )
    assert exp.action == "test action"
    print("  ✓ Experience dataclass works")
    
    # 测试上下文构建（不调 API）
    try:
        # 没有 API key 时会失败，但可以借此测试结构
        agent = LLMAgent(api_key="dummy-key-for-testing")
        
        game = TreasureHuntGame()
        state = game.get_state_description()
        actions = game.get_available_actions()
        
        context = agent._build_context(state, actions)
        assert "treasure hunt" in context.lower()
        print("  ✓ Context building works")
        
        # 测试经验更新
        agent.update_experience(state, "test action", "test feedback", 1.0)
        assert len(agent.experiences) == 1
        print("  ✓ Experience storage works")
        
    except ValueError as e:
        if "MOONSHOT_API_KEY" in str(e):
            print("  ⚠ LLM agent requires API key for full testing")
        else:
            raise
    
    print("✅ LLM agent structure tests passed!\n")


def test_experiment_runner():
    """测试实验运行器可用。"""
    print("Testing experiment runner...")
    from experiment import ExperimentRunner

    runner = ExperimentRunner(results_dir="test_results")
    assert runner.results_dir.exists()
    print("  ✓ Experiment runner initialization works")

    # 清理测试目录
    import shutil
    if runner.results_dir.exists():
        shutil.rmtree(runner.results_dir)
    
    print("✅ Experiment runner tests passed!\n")


def main():
    """运行全部测试。"""
    print("\n" + "="*60)
    print("RUNNING BASIC TESTS")
    print("="*60 + "\n")
    
    try:
        test_game_environment()
        test_rl_agent()
        test_llm_agent()
        test_experiment_runner()
        
        print("="*60)
        print("ALL TESTS PASSED! ✅")
        print("="*60)
        print("\nThe experiment is ready to run.")
        print("To run the full experiment: python experiment.py")
        print("To play interactively: python demo.py")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
