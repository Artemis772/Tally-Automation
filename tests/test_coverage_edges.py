"""Targeted tests for the remaining error/edge branches across modules."""

from __future__ import annotations

import pytest

from tally_mcp import reports, writes
from tally_mcp import xml_builder as xb
from tally_mcp import xml_parser as xp
from tally_mcp.client import TallyConnectionError


# --- client: non-connection HTTP error is wrapped, not retried ---------------

def test_http_status_error_becomes_connection_error(mock_client):
    with pytest.raises(TallyConnectionError, match="HTTP error"):
        mock_client.post("<ENVELOPE>HTTP500</ENVELOPE>")


# --- reports: zero-balance ledgers are skipped in the trial balance ----------

class _RootClient:
    def __init__(self, root):
        self._root = root

    def request(self, xml_body):
        return self._root


def test_trial_balance_skips_zero_balances():
    root = xp.parse(
        "<ENVELOPE><COLLECTION>"
        "<LEDGER NAME='Zero'><NAME>Zero</NAME><PARENT>X</PARENT>"
        "<CLOSINGBALANCE>0.00</CLOSINGBALANCE></LEDGER>"
        "<LEDGER NAME='Real'><NAME>Real</NAME><PARENT>X</PARENT>"
        "<CLOSINGBALANCE>100.00</CLOSINGBALANCE></LEDGER>"
        "</COLLECTION></ENVELOPE>"
    )
    tb = reports.trial_balance(_RootClient(root))
    assert [r["ledger"] for r in tb["rows"]] == ["Real"]
    assert tb["total_debit"] == 100.0


# --- writes: entry validation errors -----------------------------------------

def test_normalize_missing_ledger():
    with pytest.raises(writes.WriteError, match="missing a ledger"):
        writes.normalize_entries([{"amount": 100}, {"ledger": "Cash", "amount": -100}])


def test_normalize_invalid_amount():
    with pytest.raises(writes.WriteError, match="invalid amount"):
        writes.normalize_entries(
            [{"ledger": "Rent", "amount": "lots"}, {"ledger": "Cash", "amount": -100}]
        )


# --- xml_builder: collection filters -----------------------------------------

def test_collection_export_with_filters():
    from xml.etree import ElementTree as ET

    xml = xb.build_collection_export(
        "C", object_type="Ledger", fetch=["Name"],
        filters={"only_debtors": "$$IsEqual:$Parent:'Sundry Debtors'"},
    )
    root = ET.fromstring(xml)
    assert root.findtext(".//FILTER") == "only_debtors"
    assert root.find(".//SYSTEM").get("NAME") == "only_debtors"


# --- xml_parser: error / edge branches ---------------------------------------

def test_parse_raises_on_malformed_xml():
    with pytest.raises(xp.TallyResponseError, match="Could not parse"):
        xp.parse("<A><B></A>")


def test_parse_raises_on_response_errors_counter():
    with pytest.raises(xp.TallyResponseError, match="reported errors"):
        xp.parse(
            "<ENVELOPE><BODY><DATA><RESPONSE><ERRORS>1</ERRORS></RESPONSE>"
            "</DATA></BODY></ENVELOPE>"
        )


def test_int_text_non_numeric_falls_back():
    from xml.etree import ElementTree as ET

    res = xp.parse_import_response(ET.fromstring("<R><CREATED>NaN</CREATED></R>"))
    assert res["created"] == 0


def test_element_to_dict_three_repeats_and_name_attr():
    d = xp.element_to_dict(xp.parse("<V><L>A</L><L>B</L><L>C</L></V>"))
    assert d["L"] == ["A", "B", "C"]
    d2 = xp.element_to_dict(xp.parse("<LEDGER NAME='X'><PARENT>P</PARENT></LEDGER>"))
    assert d2["NAME"] == "X"  # filled from the attribute (no child NAME)


def test_decode_utf16_with_bom():
    raw = b"\xff\xfe" + "hi".encode("utf-16-le")
    assert xp.decode(raw) == "hi"
