"""End-to-end report tests: real TallyClient + mock gateway, no fakes.

Exercises the full path build XML -> HTTP POST -> sanitize -> parse -> shape.
"""

from __future__ import annotations

import pytest

from tally_mcp import reports


def test_list_companies(mock_client):
    out = reports.list_companies(mock_client)
    assert out[0]["name"] == "RAL Associates"


def test_list_groups(mock_client):
    names = {g["name"] for g in reports.list_groups(mock_client)}
    assert {"Sundry Debtors", "Sales Accounts", "Cash-in-Hand"} <= names


def test_list_ledgers(mock_client):
    out = reports.list_ledgers(mock_client)
    by_name = {l["name"]: l for l in out}
    assert by_name["Cash"]["closing_balance"] == 25000.0


def test_list_ledgers_with_group_filter_sends_childof(mock_tally, mock_client):
    out = reports.list_ledgers(mock_client, group="Sundry Debtors")
    # The request actually transmitted to Tally must carry the CHILDOF filter.
    assert "<CHILDOF>Sundry Debtors</CHILDOF>" in mock_tally.controller.last_body
    assert isinstance(out, list)


def test_get_ledger_balance(mock_client):
    led = reports.get_ledger_balance(mock_client, "cash")
    assert led["closing_balance"] == 25000.0


def test_get_ledger_balance_not_found(mock_client):
    with pytest.raises(ValueError, match="not found"):
        reports.get_ledger_balance(mock_client, "Nope Ledger")


def test_list_stock_items(mock_client):
    items = reports.list_stock_items(mock_client)
    by_name = {i["name"]: i for i in items}
    assert by_name["Blue Jeans"]["closing_value"] == 60000.0
    assert by_name["Blue Jeans"]["units"] == "Nos"


def test_bills_receivable_and_payable(mock_client):
    rec = reports.bills_outstanding(mock_client, "receivable")
    pay = reports.bills_outstanding(mock_client, "payable")
    assert [b["bill"] for b in rec] == ["INV-001"]
    assert [b["bill"] for b in pay] == ["PUR-009"]


def test_day_book(mock_client):
    vouchers = reports.day_book(mock_client, "2026-04-01", "2026-04-30")
    assert len(vouchers) == 3


def test_ledger_statement_filters_party(mock_client):
    rows = reports.ledger_statement(
        mock_client, "ABC Traders & Co", "2026-04-01", "2026-04-30"
    )
    assert {r["voucher_type"] for r in rows} == {"Sales", "Receipt"}


def test_trial_balance(mock_client):
    tb = reports.trial_balance(mock_client)
    assert tb["total_debit"] == 67500.50
    assert tb["total_credit"] == 150000.0
    assert tb["balanced"] is False


def test_profit_and_loss(mock_client):
    pnl = reports.profit_and_loss(mock_client, "2026-04-01", "2026-04-30")
    names = {r["name"] for r in pnl["rows"]}
    assert "Nett Profit" in names


def test_balance_sheet(mock_client):
    bs = reports.balance_sheet(mock_client, "2026-04-30")
    assert bs["as_on"] == "2026-04-30"
    names = {r["name"] for r in bs["rows"]}
    assert "Capital Account" in names
