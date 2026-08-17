from replay import _eval_assertion


def test_latency_under_null_latency_ms():
    assertion = {
        "type": "latency_under",
        "params": {"tool": "test_tool", "threshold": 150},
    }
    traj = {
        "turns": [
            {"tool": "test_tool", "latency_ms": None},
            {"tool": "test_tool", "latency_ms": 120},
        ]
    }
    ok, msg = _eval_assertion(assertion, traj)
    assert ok
    assert "最大延迟 120.0ms" in msg


def test_latency_under_missing_threshold():
    assertion = {"type": "latency_under", "params": {"tool": "test_tool"}}
    traj = {"turns": [{"tool": "test_tool", "latency_ms": 100}]}
    ok, msg = _eval_assertion(assertion, traj)
    assert not ok
    assert "断言缺失阈值设置" in msg
