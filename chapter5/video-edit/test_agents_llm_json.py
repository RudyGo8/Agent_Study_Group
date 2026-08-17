"""LLM 返回的 JSON 缺字段/为 null 时，Agent 解析应按约定哨兵处理，不应崩溃。"""
import types

import pytest

import agents
import ffmpeg_utils


def _fake_client(content):
    resp = types.SimpleNamespace(
        choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=content))],
        usage=None)
    completions = types.SimpleNamespace(create=lambda **kw: resp)
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))


def _stub_io(monkeypatch, content):
    """替换掉网络与帧抽取 IO，让 Agent 直接吃到给定的 LLM 回复文本。"""
    monkeypatch.setattr(agents, "client", lambda: _fake_client(content))
    monkeypatch.setattr(agents, "extract_frame", lambda *a, **k: None)
    monkeypatch.setattr(agents, "_img_part",
                        lambda p: {"type": "image_url", "image_url": {"url": "data:,"}})


def test_vision_locate_missing_keys(monkeypatch):
    """模型省略 start/end → 按 -1 哨兵返回（走兜底逻辑），不抛 KeyError。"""
    _stub_io(monkeypatch, '{"reason": "画面里看不到目标场景"}')
    start, end, reason = agents.VideoAnalyzerAgent()._vision_locate(
        "fake.mp4", [0.0], "目标", "frames")
    assert (start, end) == (-1.0, -1.0)
    assert reason == "画面里看不到目标场景"


def test_vision_locate_null_fields(monkeypatch):
    """模型返回显式 null → 同样按 -1 哨兵返回，不抛 TypeError。"""
    _stub_io(monkeypatch, '{"start": null, "end": null, "reason": "not visible"}')
    start, end, _ = agents.VideoAnalyzerAgent()._vision_locate(
        "fake.mp4", [0.0], "目标", "frames")
    assert (start, end) == (-1.0, -1.0)


def test_revise_bounds_null_start_keeps_current(monkeypatch):
    """修正区间为 null/缺失时维持当前值，正常数值仍生效。"""
    _stub_io(monkeypatch, '{"start": null, "end": 5}')
    ns, ne = agents.ProposerAgent().revise_bounds(1.0, 3.0, "反馈", 10.0)
    assert ns == 1.0
    assert ne == 5.0


def test_probe_duration_na(monkeypatch):
    """ffprobe 输出 N/A（无时长元数据）→ 清晰的 RuntimeError，而非 ValueError。"""
    fake_proc = types.SimpleNamespace(stdout="N/A\n")
    monkeypatch.setattr(ffmpeg_utils, "run", lambda *a, **k: fake_proc)
    with pytest.raises(RuntimeError, match="时长"):
        ffmpeg_utils.probe_duration("no_duration.bin")


def test_probe_duration_normal(monkeypatch):
    fake_proc = types.SimpleNamespace(stdout="12.5\n")
    monkeypatch.setattr(ffmpeg_utils, "run", lambda *a, **k: fake_proc)
    assert ffmpeg_utils.probe_duration("a.mp4") == 12.5
