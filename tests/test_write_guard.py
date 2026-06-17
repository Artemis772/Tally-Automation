"""Tests for the write-tool safety guards (no live Tally involved)."""

from __future__ import annotations

import importlib

import tally_mcp.config as config_mod
import tally_mcp.server as server_mod


def _reload_with_writes(monkeypatch, allow: bool):
    """Reload config + server so TALLY_ALLOW_WRITES is re-read from env."""
    monkeypatch.setenv("TALLY_ALLOW_WRITES", "true" if allow else "false")
    importlib.reload(config_mod)
    importlib.reload(server_mod)
    return server_mod


def test_create_voucher_rejected_when_writes_disabled(monkeypatch):
    srv = _reload_with_writes(monkeypatch, allow=False)
    result = srv.create_voucher(
        voucher_type="Payment",
        voucher_date="2026-04-03",
        entries=[
            {"ledger": "Office Rent", "amount": 20000},
            {"ledger": "Cash", "amount": -20000},
        ],
    )
    assert result["posted"] is False
    assert "disabled" in result["reason"].lower()
    assert "xml_preview" in result


def test_create_voucher_dry_run_when_writes_enabled(monkeypatch):
    srv = _reload_with_writes(monkeypatch, allow=True)
    result = srv.create_voucher(
        voucher_type="Payment",
        voucher_date="2026-04-03",
        entries=[
            {"ledger": "Office Rent", "amount": 20000},
            {"ledger": "Cash", "amount": -20000},
        ],
        dry_run=True,
    )
    assert result["posted"] is False
    assert "dry run" in result["reason"].lower()
    assert "<VOUCHER" in result["xml_preview"]


def test_create_voucher_unbalanced_rejected(monkeypatch):
    srv = _reload_with_writes(monkeypatch, allow=True)
    result = srv.create_voucher(
        voucher_type="Payment",
        voucher_date="2026-04-03",
        entries=[
            {"ledger": "Office Rent", "amount": 20000},
            {"ledger": "Cash", "amount": -19000},  # does not net to zero
        ],
        dry_run=False,
        confirm=True,
    )
    assert result["posted"] is False
    assert "balance" in result["error"].lower()


def test_create_ledger_disabled_returns_preview(monkeypatch):
    srv = _reload_with_writes(monkeypatch, allow=False)
    result = srv.create_ledger("New Client", parent_group="Sundry Debtors")
    assert result["posted"] is False
    assert "<LEDGER" in result["xml_preview"]


def teardown_module(module):
    # Restore default modules for other tests.
    importlib.reload(config_mod)
    importlib.reload(server_mod)
