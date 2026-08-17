"""Regression test: malformed numeric env vars must not crash config load.

BROWSER_TIMEOUT / SMTP_PORT / HITL_TIMEOUT_SECONDS (config.py) and
OPENAI_TIMEOUT / OPENAI_MAX_RETRIES (subagent_tools.py) were parsed with bare
int()/float(); malformed values crashed with ValueError at import/startup.
They now fall back to defaults with a warning.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Ensure the real local modules are imported.
for _mod in ("config", "subagent_tools", "llm_fallback"):
    sys.modules.pop(_mod, None)

import config as cfg
import subagent_tools as sa


def test_env_int_falls_back_on_malformed(monkeypatch, capsys):
    monkeypatch.setenv("SMTP_PORT", "smtp")
    assert cfg._env_int("SMTP_PORT", 587) == 587
    assert "invalid SMTP_PORT" in capsys.readouterr().err


def test_load_config_survives_malformed_env(monkeypatch):
    monkeypatch.setenv("BROWSER_TIMEOUT", "soon")
    monkeypatch.setenv("SMTP_PORT", "smtp")
    monkeypatch.setenv("HITL_TIMEOUT_SECONDS", "never")
    c = cfg.load_config()
    assert c.browser.timeout == 30000
    assert c.email.smtp_port == 587
    assert c.hitl.timeout_seconds == 3600


def test_load_config_parses_valid_env(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "2525")
    assert cfg.load_config().email.smtp_port == 2525


def test_subagent_env_or_default_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT", "abc")
    assert sa._env_or_default("OPENAI_TIMEOUT", 60.0, float) == 60.0


def test_subagent_env_or_default_parses_valid(monkeypatch):
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")
    assert sa._env_or_default("OPENAI_MAX_RETRIES", 2, int) == 5
