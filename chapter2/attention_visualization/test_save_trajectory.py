#!/usr/bin/env python3
"""agent.py 中 save_trajectory() 的回归测试。

缺陷：save_trajectory() 引用了不在其作用域内的裸名 `temperature` 和
`max_new_tokens`，导致每次调用都抛 NameError
（generate_with_attention 默认以 save_trajectory=True 调用它）。
修复方式是仿照 save_react_trajectory，把二者加为参数。
"""

import json

from agent import AttentionVisualizationAgent, GenerationResult


def _make_agent():
    # 绕过 __init__（它会下载 HF 模型）；save_trajectory 只需要
    # model_name 和 device。
    ag = AttentionVisualizationAgent.__new__(AttentionVisualizationAgent)
    ag.model_name = "stub-model"
    ag.device = "cpu"
    return ag


def _make_result():
    return GenerationResult(
        input_text="What is 2+2?",
        output_text="4",
        input_tokens=["What", " is", "2", "+", "2", "?"],
        output_tokens=["4"],
        attention_steps=[],
        context_length=6,
    )


def test_save_trajectory_writes_json_with_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ag = _make_agent()
    path = ag.save_trajectory(_make_result(), query="q", category="Math",
                              temperature=0.2, max_new_tokens=50)
    with open(path) as f:
        data = json.load(f)
    assert data["metadata"]["temperature"] == 0.2
    assert data["metadata"]["max_tokens"] == 50
    assert data["metadata"]["model"] == "stub-model"
    assert data["test_case"]["category"] == "Math"


def test_save_trajectory_default_params_no_nameerror(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ag = _make_agent()
    # 按 generate_with_attention 过去的调用方式调用（不带
    # temperature/max_new_tokens）：不得抛出 NameError。
    path = ag.save_trajectory(_make_result())
    with open(path) as f:
        data = json.load(f)
    assert data["metadata"]["temperature"] == 0.7
    assert data["metadata"]["max_tokens"] == 100
