#!/usr/bin/env python3
"""针对零局数除法保护的回归测试。

缺陷：train()/evaluate() 用局数去除胜场数，因此 num_episodes=0
（experiment.py 的 argparse 曾接受该值）会以 ZeroDivisionError 崩溃。
修复方式：给除法加保护，并在 experiment.py 入口处拒绝小于 1 的局数。
"""

import sys

import experiment
from llm_agent import LLMAgent
from rl_agent import QLearningAgent


def test_rl_train_zero_episodes_no_zero_division():
    result = QLearningAgent().train(num_episodes=0, verbose=False)
    assert result["total_episodes"] == 0
    assert result["victory_rate"] == 0.0


def test_rl_evaluate_zero_episodes_no_zero_division():
    result = QLearningAgent().evaluate(num_episodes=0)
    assert result["num_episodes"] == 0
    assert result["victory_rate"] == 0.0


def test_llm_evaluate_zero_episodes_no_zero_division():
    # 虚假 key：构造客户端不会发起网络请求，
    # evaluate(num_episodes=0) 也绝不会走到 API 调用。
    agent = LLMAgent(api_key="dummy-key")
    result = agent.evaluate(num_episodes=0)
    assert result["victory_rate"] == 0.0
    assert result["avg_reward"] == 0.0
    assert result["avg_length"] == 0.0


def test_experiment_rejects_zero_episodes(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["experiment.py", "--mode", "qlearning",
                                      "--rl-episodes", "0"])
    experiment.main()  # 必须先报错返回，不得开始运行
    assert "must all be >= 1" in capsys.readouterr().out
