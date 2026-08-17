import json
import os

import github_mcp


def test_create_issues_bare_filename(tmp_path, monkeypatch):
    """out_path 为不带目录的裸文件名时，落盘不应崩溃（dirname 为空串）。"""
    monkeypatch.chdir(tmp_path)
    problems = [{"priority": "P1", "module": "refund",
                 "title": "退款未校验", "description": "描述"}]
    issues = github_mcp.create_issues(problems, [], mock=True,
                                      out_path="issues.json")
    assert os.path.exists("issues.json")
    with open("issues.json", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["issues"] == issues


def test_create_issues_with_directory(tmp_path):
    """带目录的 out_path 保持原行为：自动创建父目录。"""
    out = tmp_path / "sub" / "issues.json"
    github_mcp.create_issues([], [], mock=True, out_path=str(out))
    assert out.exists()
