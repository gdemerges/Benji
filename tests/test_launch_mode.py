import sys

import benji.launch_mode as lm


def test_env_var_window_wins(monkeypatch):
    monkeypatch.setenv("BENJI_LAUNCH_MODE", "window")
    assert lm.launch_mode() == "window"


def test_env_var_overlay_wins(monkeypatch):
    monkeypatch.setenv("BENJI_LAUNCH_MODE", "overlay")
    monkeypatch.setattr(sys, "executable", "/Applications/Benji.app/Contents/MacOS/Benji")
    assert lm.launch_mode() == "overlay"


def test_app_bundle_executable(monkeypatch):
    monkeypatch.delenv("BENJI_LAUNCH_MODE", raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Benji.app/Contents/MacOS/Benji")
    assert lm.launch_mode() == "window"


def test_cli_default(monkeypatch):
    monkeypatch.delenv("BENJI_LAUNCH_MODE", raising=False)
    monkeypatch.setattr(sys, "executable", "/Users/me/.venv/bin/python")
    assert lm.launch_mode() == "overlay"
