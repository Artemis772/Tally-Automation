"""Direct tests for the grouped-report row flattener (_report_rows)."""

from __future__ import annotations

from conftest import load_fixture
from tally_mcp import reports
from tally_mcp.xml_parser import parse


def test_report_rows_pairs_names_with_amounts():
    root = parse(load_fixture("pnl.xml"))
    rows = reports._report_rows(root)
    by_name = {r["name"]: r.get("amount") for r in rows}
    assert by_name["Sales Accounts"] == 150000.0
    assert by_name["Purchase Accounts"] == 60000.0
    assert by_name["Nett Profit"] == 90000.0


def test_report_rows_balance_sheet():
    root = parse(load_fixture("balance_sheet.xml"))
    rows = reports._report_rows(root)
    assert {r["name"] for r in rows} == {"Capital Account", "Current Assets"}
    assert all(r["amount"] == 200000.0 for r in rows)


def test_report_rows_empty_when_no_names():
    root = parse("<ENVELOPE></ENVELOPE>")
    assert reports._report_rows(root) == []
