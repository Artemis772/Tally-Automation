"""Tests for the read-side report logic using fixture-backed fake client."""

from __future__ import annotations

from tally_mcp import reports


def test_list_companies(fake_client):
    companies = reports.list_companies(fake_client)
    assert companies == [
        {
            "name": "RAL Associates",
            "starting_from": "20250401",
            "ending_at": "20260331",
        }
    ]


def test_list_ledgers_parses_balances(fake_client):
    ledgers = reports.list_ledgers(fake_client)
    by_name = {l["name"]: l for l in ledgers}
    assert by_name["Cash"]["closing_balance"] == 25000.0
    assert by_name["Sales Account"]["closing_balance"] == -150000.0
    assert by_name["ABC Traders & Co"]["group"] == "Sundry Debtors"


def test_get_ledger_balance_case_insensitive(fake_client):
    led = reports.get_ledger_balance(fake_client, "cash")
    assert led["closing_balance"] == 25000.0


def test_trial_balance_totals(fake_client):
    tb = reports.trial_balance(fake_client)
    assert tb["total_debit"] == 67500.50   # Cash + ABC
    assert tb["total_credit"] == 150000.0  # Sales
    assert tb["balanced"] is False


def test_day_book_lists_all_vouchers(fake_client):
    vouchers = reports.day_book(fake_client, "2026-04-01", "2026-04-30")
    assert len(vouchers) == 3
    assert vouchers[0]["voucher_type"] == "Sales"
    assert vouchers[0]["amount"] == -15000.0


def test_ledger_statement_filters_by_party(fake_client):
    rows = reports.ledger_statement(
        fake_client, "ABC Traders & Co", "2026-04-01", "2026-04-30"
    )
    assert len(rows) == 2
    assert {r["voucher_type"] for r in rows} == {"Sales", "Receipt"}


def test_bills_receivable_vs_payable(fake_client):
    receivable = reports.bills_outstanding(fake_client, "receivable")
    payable = reports.bills_outstanding(fake_client, "payable")
    assert [b["bill"] for b in receivable] == ["INV-001"]
    assert receivable[0]["amount"] == 42500.50
    assert [b["bill"] for b in payable] == ["PUR-009"]
    assert payable[0]["amount"] == 18000.0
