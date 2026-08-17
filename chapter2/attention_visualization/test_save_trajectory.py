#!/usr/bin/env python3
"""Regression tests for save_trajectory() in agent.py.

Bug: save_trajectory() referenced bare names `temperature` and
`max_new_tokens` that are not in its scope -> NameError on every call
(generate_with_attention calls it with save_trajectory=True by default).
Fixed by adding them as parameters, mirroring save_react_trajectory.
"""

import json

from agent import AttentionVisualizationAgent, GenerationResult


def _make_agent():
    # Bypass __init__ (downloads a HF model); save_trajectory only needs
    # model_name and device.
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
    # Called exactly as generate_with_attention used to call it (no
    # temperature/max_new_tokens): must not raise NameError.
    path = ag.save_trajectory(_make_result())
    with open(path) as f:
        data = json.load(f)
    assert data["metadata"]["temperature"] == 0.7
    assert data["metadata"]["max_tokens"] == 100
