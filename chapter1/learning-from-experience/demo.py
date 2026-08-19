#!/usr/bin/env python3
"""
交互式演示：手动游玩本游戏，或观看智能体游玩。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 从 .env 文件加载环境变量
load_dotenv()

# 把父目录加入 sys.path 以便导入
sys.path.append(str(Path(__file__).parent))

from game_environment import TreasureHuntGame
from rl_agent import QLearningAgent
from llm_agent import LLMAgent


def play_manual():
    """让用户手动游玩游戏。"""
    print("\n" + "="*60)
    print("MANUAL PLAY MODE")
    print("="*60)
    print("\nYou are playing the treasure hunt game!")
    print("Try to find the dragon's treasure by exploring and discovering hidden mechanics.")
    
    game = TreasureHuntGame()
    
    while not game.game_over:
        print("\n" + "-"*40)
        print(game.get_state_description())
        print("\nAvailable actions:")
        actions = game.get_available_actions()
        for i, action in enumerate(actions, 1):
            print(f"  {i}. {action}")
        
        # 获取用户输入
        choice = input("\nEnter action number or type custom action: ").strip()

        # 解析输入
        if choice.isdigit() and 1 <= int(choice) <= len(actions):
            action = actions[int(choice) - 1]
        else:
            action = choice
        
        # 执行动作
        feedback, reward, done = game.execute_action(action)
        print(f"\nFeedback: {feedback}")
        print(f"Reward: {reward:.2f}")

    if game.victory:
        print("\n🎉 CONGRATULATIONS! You won!")
    else:
        print("\n💀 GAME OVER! Better luck next time.")
    
    print(f"Final score: {game.score}")


def watch_rl_agent():
    """观看训练好的 RL 智能体游玩。"""
    print("\n" + "="*60)
    print("WATCHING Q-LEARNING AGENT")
    print("="*60)
    
    # 检查是否已有训练好的智能体存档
    agent_path = Path("results") / "rl_agent_demo.pkl"
    
    agent = QLearningAgent()
    
    if agent_path.exists():
        print("Loading pre-trained agent...")
        agent.load(agent_path)
    else:
        print("No pre-trained agent found. Training one now...")
        print("This will take a few minutes...\n")
        
        game = TreasureHuntGame()
        agent.train(num_episodes=2000, verbose=True)
        
        # 保存以便下次复用
        agent_path.parent.mkdir(exist_ok=True)
        agent.save(agent_path)

    # 观看智能体游玩
    print("\nWatching agent play...")
    game = TreasureHuntGame()
    total_reward = 0
    steps = 0
    
    while not game.game_over:
        print("\n" + "-"*40)
        print(game.get_state_description())
        
        action = agent.choose_action(game, training=False)
        print(f"\nAgent chooses: {action}")
        
        feedback, reward, done = game.execute_action(action)
        print(f"Feedback: {feedback}")
        print(f"Reward: {reward:.2f}")
        
        total_reward += reward
        steps += 1
        
        input("\nPress Enter to continue...")
    
    if game.victory:
        print("\n🎉 Agent won!")
    else:
        print("\n💀 Agent failed.")
    
    print(f"Total reward: {total_reward:.2f}")
    print(f"Steps taken: {steps}")


def watch_llm_agent():
    """观看带推理过程的 LLM 智能体游玩。"""
    print("\n" + "="*60)
    print("WATCHING LLM AGENT (with reasoning)")
    print("="*60)
    
    # 检查 API key
    provider = os.getenv("LLM_PROVIDER", "moonshot").lower()
    api_key = os.getenv("DASHSCOPE_API_KEY") if provider in {"dashscope", "qwen", "bailian"} else os.getenv("MOONSHOT_API_KEY")
    if not api_key and not os.getenv("OPENROUTER_API_KEY"):
        print(f"\nError: API key for provider '{provider}' not set.")
        print("Please set your Kimi API key:")
        print("  export DASHSCOPE_API_KEY='your-key-here'  # for dashscope/qwen/bailian")
        print("  export MOONSHOT_API_KEY='your-key-here'   # for moonshot/kimi")
        print("Or set OPENROUTER_API_KEY as a universal fallback.")
        return
    
    agent = LLMAgent(api_key=api_key, provider=provider)
    
    # 如有历史经验则加载
    exp_path = Path("results") / "llm_experiences_demo.json"
    if exp_path.exists():
        print("Loading previous experiences...")
        agent.load_experiences(exp_path)
        print(f"Loaded {len(agent.experiences)} experiences")
    
    # 以详细输出模式游玩一局
    print("\nWatching LLM agent play with reasoning...")
    print("(The agent will explain its thought process)\n")
    
    game = TreasureHuntGame()
    reward, steps, victory = agent.play_episode(game, verbose=True)
    
    if victory:
        print("\n🎉 LLM agent won!")
    else:
        print("\n💀 LLM agent failed.")
    
    print(f"Total reward: {reward:.2f}")
    print(f"Steps taken: {steps}")
    print(f"API calls made: {agent.api_calls}")
    
    # 保存经验
    exp_path.parent.mkdir(exist_ok=True)
    agent.save_experiences(exp_path)


def show_hidden_rules():
    """揭示游戏的隐藏机制。"""
    print("\n" + "="*60)
    print("HIDDEN GAME MECHANICS (SPOILERS!)")
    print("="*60)
    
    game = TreasureHuntGame()
    print(game.get_hidden_rules())
    
    print("\nThese are the rules that agents must discover through experience.")
    print("Traditional RL requires thousands of episodes to learn these patterns,")
    print("while LLMs can often figure them out in just 20-30 episodes through reasoning.")


def main():
    """演示主菜单。"""
    while True:
        print("\n" + "="*70)
        print("LEARNING FROM EXPERIENCE DEMO")
        print("Comparing RL vs LLM In-Context Learning")
        print("="*70)
        
        print("\nChoose an option:")
        print("1. Play the game manually")
        print("2. Watch Q-Learning agent play (pre-trained)")
        print("3. Watch LLM agent play with reasoning")
        print("4. Show hidden game mechanics (spoilers!)")
        print("5. Run full experiment")
        print("6. Exit")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        if choice == "1":
            play_manual()
        elif choice == "2":
            watch_rl_agent()
        elif choice == "3":
            watch_llm_agent()
        elif choice == "4":
            show_hidden_rules()
        elif choice == "5":
            print("\nRunning full experiment...")
            os.system("python experiment.py")
        elif choice == "6":
            print("\nGoodbye!")
            break
        else:
            print("\nInvalid choice. Please try again.")


if __name__ == "__main__":
    main()
