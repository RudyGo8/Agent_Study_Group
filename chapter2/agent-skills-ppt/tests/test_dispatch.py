#!/usr/bin/env python3
"""针对 demo.py 中 dispatch() 的回归测试。

缺陷背景：agentic loop 解析工具调用参数时，遇到 JSONDecodeError 会回退成 {}，
随后调用 dispatch() 且没有 try/except 保护。dispatch() 过去直接取
args["name"] / args["payload"] 等字段，因此任何格式错误或不完整的 LLM 工具调用
都会以 KeyError 让整次运行崩溃。现已修复为返回 "[error] ..." 字符串，Agent
可据此在后续轮次自行恢复。
"""

import os
from pathlib import Path

from demo import dispatch, scan_skill_catalog

OUT = Path("/tmp/test_dispatch_out.pptx")


def test_missing_name_returns_error_not_keyerror():
    catalog = scan_skill_catalog()
    # {} 正是 run_agent 中 JSONDecodeError 回退后产生的输入
    result = dispatch(catalog, "read_skill", {}, OUT)
    assert result.startswith("[error]")
    assert "name" in result


def test_missing_payload_returns_error_not_keyerror():
    catalog = scan_skill_catalog()
    result = dispatch(catalog, "run_skill_script",
                      {"name": "pptx", "script": "generate_pptx.py"}, OUT)
    assert result.startswith("[error]")
    assert "payload" in result


def test_unknown_tool_still_returns_error():
    catalog = scan_skill_catalog()
    result = dispatch(catalog, "no_such_tool", {}, OUT)
    assert result.startswith("[error]")


def test_valid_read_skill_still_works():
    catalog = scan_skill_catalog()
    result = dispatch(catalog, "read_skill", {"name": "pptx"}, OUT)
    assert not result.startswith("[error]")
    assert len(result) > 0


def test_run_skill_script_rejects_absolute_path(tmp_path):
    """run_skill_script 会直接执行该文件，因此必须限制在 scripts/ 目录内。"""
    outside = tmp_path / "evil.py"
    outside.write_text("raise AssertionError('executed out-of-tree script')")
    catalog = scan_skill_catalog()
    result = dispatch(catalog, "run_skill_script",
                      {"name": "pptx", "script": str(outside), "payload": "{}"}, OUT)
    assert result.startswith("[error]")


def test_run_skill_script_rejects_parent_traversal(tmp_path):
    outside = tmp_path / "evil.py"
    outside.write_text("raise AssertionError('executed out-of-tree script')")
    catalog = scan_skill_catalog()
    scripts_dir = (catalog["pptx"]["dir"] / "scripts").resolve()
    rel = os.path.relpath(outside, scripts_dir)
    result = dispatch(catalog, "run_skill_script",
                      {"name": "pptx", "script": rel, "payload": "{}"}, OUT)
    assert result.startswith("[error]")
