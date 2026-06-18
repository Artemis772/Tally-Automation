"""Tests that scripts/smoke_test.py runs end-to-end against the mock gateway."""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path

import tally_mcp.client as client_mod
import tally_mcp.config as config_mod
from tally_mcp.config import TallyConfig

SCRIPT = Path(__file__).parent.parent / "scripts" / "smoke_test.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("smoke_test_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_smoke_success_against_mock(mock_tally, monkeypatch, capsys):
    cfg = TallyConfig(host=mock_tally.host, port=mock_tally.port, timeout=5)
    monkeypatch.setattr(client_mod, "default_config", cfg)
    monkeypatch.setattr(config_mod, "config", cfg)
    rc = _load_script().main()
    assert rc == 0
    assert "All checks passed" in capsys.readouterr().out


def test_smoke_failure_when_unreachable(monkeypatch, capsys):
    cfg = TallyConfig(host="127.0.0.1", port=_free_port(), timeout=1)
    monkeypatch.setattr(client_mod, "default_config", cfg)
    monkeypatch.setattr(config_mod, "config", cfg)
    rc = _load_script().main()
    assert rc == 1
