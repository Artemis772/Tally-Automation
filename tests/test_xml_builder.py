"""Tests for XML request envelope construction."""

from __future__ import annotations

import pytest
from xml.etree import ElementTree as ET

from tally_mcp import xml_builder as xb


def _well_formed(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_to_tally_date_formats():
    assert xb.to_tally_date("2026-04-01") == "20260401"
    assert xb.to_tally_date("2026/4/1") == "20260401"
    assert xb.to_tally_date("20260401") == "20260401"
    with pytest.raises(ValueError):
        xb.to_tally_date("01-04-2026-bad")


def test_report_export_is_well_formed_and_has_dates():
    xml = xb.build_report_export(
        "Balance Sheet", company="Acme", from_date="2026-04-01", to_date="2026-04-30"
    )
    root = _well_formed(xml)
    assert root.findtext(".//ID") == "Balance Sheet"
    assert root.findtext(".//SVFROMDATE") == "20260401"
    assert root.findtext(".//SVTODATE") == "20260430"
    assert root.findtext(".//SVCURRENTCOMPANY") == "Acme"


def test_collection_export_declares_type_and_fetch():
    xml = xb.build_collection_export(
        "TMCP_Ledgers",
        object_type="Ledger",
        fetch=["Name", "ClosingBalance"],
        company="Acme",
    )
    root = _well_formed(xml)
    assert root.findtext(".//TYPE") == "Collection"  # header
    coll = root.find(".//COLLECTION")
    assert coll.get("NAME") == "TMCP_Ledgers"
    assert coll.findtext("TYPE") == "Ledger"
    assert "ClosingBalance" in coll.findtext("FETCH")


def test_collection_child_of_adds_childof():
    xml = xb.build_collection_export(
        "TMCP_Ledgers",
        object_type="Ledger",
        fetch=["Name"],
        child_of="Sundry Debtors",
        belongs_to=True,
    )
    root = _well_formed(xml)
    assert root.findtext(".//CHILDOF") == "Sundry Debtors"
    assert root.findtext(".//BELONGSTO") == "Yes"


def test_user_input_is_escaped():
    xml = xb.build_collection_export(
        "C", object_type="Ledger", fetch=["Name"], company="Tom & Jerry"
    )
    # Must remain well-formed despite the ampersand.
    root = _well_formed(xml)
    assert root.findtext(".//SVCURRENTCOMPANY") == "Tom & Jerry"


def test_voucher_import_balances_signs():
    xml = xb.build_voucher_import(
        voucher_type="Payment",
        voucher_date="2026-04-03",
        entries=[
            {"ledger": "Office Rent", "amount": 20000},   # debit
            {"ledger": "Cash", "amount": -20000},          # credit
        ],
        narration="April rent",
    )
    root = _well_formed(xml)
    assert root.findtext(".//VOUCHERTYPENAME") == "Payment"
    assert root.findtext(".//DATE") == "20260403"
    entries = root.findall(".//ALLLEDGERENTRIES.LIST")
    assert len(entries) == 2
    # Debit entry => ISDEEMEDPOSITIVE No, negative AMOUNT in Tally convention.
    rent = entries[0]
    assert rent.findtext("LEDGERNAME") == "Office Rent"


def test_ledger_master_create_action():
    xml = xb.build_ledger_master("New Client", parent_group="Sundry Debtors")
    root = _well_formed(xml)
    ledger = root.find(".//LEDGER")
    assert ledger.get("ACTION") == "Create"
    assert ledger.findtext("PARENT") == "Sundry Debtors"


def test_to_tally_date_accepts_date_objects():
    from datetime import date, datetime

    assert xb.to_tally_date(date(2026, 4, 1)) == "20260401"
    assert xb.to_tally_date(datetime(2026, 4, 1, 13, 0)) == "20260401"


def test_esc_handles_none_and_specials():
    assert xb.esc(None) == ""
    assert xb.esc("a & b < c > d") == "a &amp; b &lt; c &gt; d"


def test_report_export_extra_static():
    xml = xb.build_report_export("Day Book", extra_static={"SVLEDGER": "Cash"})
    root = _well_formed(xml)
    assert root.findtext(".//SVLEDGER") == "Cash"


def test_company_collection_requests_company_type():
    root = _well_formed(xb.build_company_collection())
    coll = root.find(".//COLLECTION")
    assert coll.findtext("TYPE") == "Company"


def test_ledger_master_with_opening_balance():
    xml = xb.build_ledger_master("Cash", parent_group="Cash-in-Hand", opening_balance=5000)
    root = _well_formed(xml)
    assert root.findtext(".//OPENINGBALANCE") == "5000"


def test_voucher_import_with_party_ledger():
    xml = xb.build_voucher_import(
        voucher_type="Sales",
        voucher_date="2026-04-01",
        entries=[{"ledger": "ABC", "amount": -15000}, {"ledger": "Sales", "amount": 15000}],
        party_ledger="ABC Traders",
    )
    root = _well_formed(xml)
    assert root.findtext(".//PARTYLEDGERNAME") == "ABC Traders"
