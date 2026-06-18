"""Tests for Phase 2 write logic: guards, validation, prepare/post, verify.

No live Tally — uses the fixture-backed FakeTallyClient and a patched config.
"""

from __future__ import annotations

import pytest

from conftest import FakeTallyClient
from tally_mcp import writes
from tally_mcp.config import TallyConfig
from tally_mcp.drafts import drafts


@pytest.fixture
def writes_enabled(monkeypatch):
    """Patch the config writes sees so writes are enabled, no company lock."""
    cfg = TallyConfig(allow_writes=True, company="", write_company="")
    monkeypatch.setattr(writes, "config", cfg)
    return cfg


def _balanced_entries():
    return [
        {"ledger": "Office Rent", "amount": 20000},   # debit
        {"ledger": "Cash", "amount": -20000},          # credit
    ]


# --- guards -----------------------------------------------------------------

def test_writes_disabled_blocks_prepare(monkeypatch):
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=False))
    with pytest.raises(writes.WriteError, match="disabled"):
        writes.prepare_voucher("Journal", "2026-04-03", _balanced_entries())


def test_write_company_lock_rejects_other_company(monkeypatch):
    monkeypatch.setattr(
        writes, "config", TallyConfig(allow_writes=True, write_company="ZZ Test Co")
    )
    with pytest.raises(writes.WriteError, match="locked to company"):
        writes.resolve_write_company("Real Company")


def test_write_company_lock_defaults_to_locked_company(monkeypatch):
    monkeypatch.setattr(
        writes, "config", TallyConfig(allow_writes=True, write_company="ZZ Test Co")
    )
    assert writes.resolve_write_company(None) == "ZZ Test Co"


# --- validation -------------------------------------------------------------

def test_unsupported_voucher_type_rejected(writes_enabled):
    with pytest.raises(writes.WriteError, match="not supported"):
        writes.validate_voucher("Sales", _balanced_entries())


def test_unbalanced_voucher_rejected(writes_enabled):
    bad = [{"ledger": "Office Rent", "amount": 20000}, {"ledger": "Cash", "amount": -19000}]
    with pytest.raises(writes.WriteError, match="does not balance"):
        writes.validate_voucher("Journal", bad)


def test_single_entry_rejected(writes_enabled):
    with pytest.raises(writes.WriteError, match="at least two"):
        writes.validate_voucher("Journal", [{"ledger": "Cash", "amount": 100}])


def test_zero_amount_rejected(writes_enabled):
    bad = [{"ledger": "Cash", "amount": 0}, {"ledger": "Rent", "amount": 0}]
    with pytest.raises(writes.WriteError):
        writes.validate_voucher("Journal", bad)


# --- preview ----------------------------------------------------------------

def test_preview_has_balanced_table(writes_enabled):
    out = writes.prepare_voucher("Journal", "2026-04-03", _balanced_entries(),
                                 narration="April rent")
    preview = out["preview"]
    assert preview["total_debit"] == 20000.0
    assert preview["total_credit"] == 20000.0
    assert preview["balanced"] is True
    assert "| Ledger | Debit | Credit |" in preview["text"]
    assert "Office Rent" in preview["text"]
    assert out["draft_id"]


# --- post -------------------------------------------------------------------

def test_post_draft_success(writes_enabled):
    out = writes.prepare_voucher("Journal", "2026-04-03", _balanced_entries())
    draft = drafts.get(out["draft_id"])
    client = FakeTallyClient(post_fixture="import_success.xml")
    result = writes.post_draft(client, draft)
    assert result["posted"] is True
    assert result["created"] == 1
    assert result["last_vch_id"] == 4521
    assert result["errors"] == 0
    # The posted XML must be a Journal import envelope.
    assert "<VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>" in client.last_post


def test_post_draft_surfaces_tally_error(writes_enabled):
    out = writes.prepare_voucher("Journal", "2026-04-03", _balanced_entries())
    draft = drafts.get(out["draft_id"])
    client = FakeTallyClient(post_fixture="import_error.xml")
    result = writes.post_draft(client, draft)
    assert result["posted"] is False
    assert result["errors"] == 1
    assert "Office Rent" in result["lineerror"]


# --- verify -----------------------------------------------------------------

def test_verify_voucher_finds_match(fake_client):
    # vouchers.xml has a Sales voucher for "ABC Traders & Co" of 15000.
    out = writes.verify_voucher(
        fake_client, "2026-04-01", "2026-04-30",
        voucher_type="Sales", ledger="ABC Traders & Co", amount=15000,
    )
    assert out["verified"] is True
    assert out["match_count"] == 1


def test_verify_voucher_no_match(fake_client):
    out = writes.verify_voucher(
        fake_client, "2026-04-01", "2026-04-30", amount=999999,
    )
    assert out["verified"] is False
    assert out["match_count"] == 0
