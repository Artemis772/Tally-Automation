"""Tests for environment-driven configuration."""

from __future__ import annotations

import pytest

from tally_mcp.config import TallyConfig


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in (
        "TALLY_HOST", "TALLY_PORT", "TALLY_COMPANY", "TALLY_TIMEOUT",
        "TALLY_ALLOW_WRITES", "TALLY_WRITE_COMPANY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults():
    cfg = TallyConfig.from_env()
    assert cfg.host == "localhost"
    assert cfg.port == 9000
    assert cfg.company == ""
    assert cfg.timeout == 30
    assert cfg.allow_writes is False
    assert cfg.write_company == ""
    assert cfg.base_url == "http://localhost:9000"


def test_reads_values(monkeypatch):
    monkeypatch.setenv("TALLY_HOST", "192.168.1.5")
    monkeypatch.setenv("TALLY_PORT", "9001")
    monkeypatch.setenv("TALLY_COMPANY", "Acme Co")
    monkeypatch.setenv("TALLY_TIMEOUT", "15")
    monkeypatch.setenv("TALLY_WRITE_COMPANY", "ZZ Test Co")
    cfg = TallyConfig.from_env()
    assert cfg.host == "192.168.1.5"
    assert cfg.port == 9001
    assert cfg.company == "Acme Co"
    assert cfg.timeout == 15
    assert cfg.write_company == "ZZ Test Co"
    assert cfg.base_url == "http://192.168.1.5:9001"


@pytest.mark.parametrize(
    "raw,expected",
    [("true", True), ("1", True), ("yes", True), ("on", True), ("TRUE", True),
     ("false", False), ("0", False), ("no", False), ("", False), ("maybe", False)],
)
def test_allow_writes_bool_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("TALLY_ALLOW_WRITES", raw)
    assert TallyConfig.from_env().allow_writes is expected


def test_invalid_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("TALLY_PORT", "not-a-number")
    monkeypatch.setenv("TALLY_TIMEOUT", "")
    cfg = TallyConfig.from_env()
    assert cfg.port == 9000
    assert cfg.timeout == 30


def test_blank_host_falls_back(monkeypatch):
    monkeypatch.setenv("TALLY_HOST", "   ")
    assert TallyConfig.from_env().host == "localhost"
