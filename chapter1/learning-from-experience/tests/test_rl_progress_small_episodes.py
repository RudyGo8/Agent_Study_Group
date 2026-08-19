"""回归测试：局数 < 10 时进度打印不得触发 ZeroDivisionError。"""


def test_progress_every_never_zero():
    for num_episodes in (1, 5, 9, 10, 100):
        progress_every = max(1, num_episodes // 10)
        assert progress_every >= 1
        # 取模运算必须合法（除数不为 0）
        for episode in range(num_episodes):
            _ = (episode + 1) % progress_every


def test_source_uses_max_guard():
    from pathlib import Path
    src = (Path(__file__).parent / "manual" / "rl_learning_check.py").read_text()
    assert "progress_every = max(1, num_episodes // 10)" in src
