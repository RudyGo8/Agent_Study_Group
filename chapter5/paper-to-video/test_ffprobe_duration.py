"""ffprobe 输出 N/A（无时长元数据）时，ffprobe_duration 应给出清晰报错。"""
import pytest

import demo


def test_ffprobe_duration_na(monkeypatch):
    monkeypatch.setattr(demo, "run", lambda *a, **k: "N/A\n")
    with pytest.raises(RuntimeError, match="时长"):
        demo.ffprobe_duration("no_duration.bin")


def test_ffprobe_duration_empty(monkeypatch):
    monkeypatch.setattr(demo, "run", lambda *a, **k: "")
    with pytest.raises(RuntimeError, match="时长"):
        demo.ffprobe_duration("empty.bin")


def test_ffprobe_duration_normal(monkeypatch):
    monkeypatch.setattr(demo, "run", lambda *a, **k: "12.345\n")
    assert demo.ffprobe_duration("a.mp4") == 12.345
