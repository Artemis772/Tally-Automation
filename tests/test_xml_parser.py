"""Tests for the defensive XML parsing layer."""

from __future__ import annotations

import pytest

from tally_mcp import xml_parser as xp
from conftest import load_fixture


def test_sanitize_strips_raw_control_chars():
    raw = "<A>val\x04ue</A>"
    assert "\x04" not in xp.sanitize(raw)
    assert "value" in xp.sanitize(raw)


def test_sanitize_strips_invalid_numeric_charref():
    # Tally emits "&#4;" which ElementTree would reject.
    raw = "<A>Sales &#4;Account</A>"
    cleaned = xp.sanitize(raw)
    assert "&#4;" not in cleaned
    # A valid charref is preserved.
    assert xp.sanitize("<A>&#65;</A>").count("&#65;") == 1


def test_sanitize_escapes_bare_ampersand():
    raw = "<A>Tom & Jerry</A>"
    assert "&amp;" in xp.sanitize(raw)
    # Existing entities are not double-escaped.
    assert xp.sanitize("<A>Tom &amp; Jerry</A>").count("&amp;") == 1


def test_parse_ledgers_fixture_has_clean_data():
    root = xp.parse(load_fixture("ledgers.xml"))
    ledgers = xp.extract_objects(root, "LEDGER")
    assert len(ledgers) == 3
    names = {l["NAME"] for l in ledgers}
    assert "Cash" in names
    assert "ABC Traders & Co" in names  # entity decoded


def test_parse_raises_on_lineerror():
    with pytest.raises(xp.TallyResponseError) as exc:
        xp.parse(load_fixture("error_lineerror.xml"))
    assert "Nonexistent Co" in str(exc.value)


def test_parse_raises_on_empty():
    with pytest.raises(xp.TallyResponseError):
        xp.parse("   ")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("15000.00", 15000.0),
        ("-150000.00", -150000.0),
        ("1,25,000.50", 125000.5),
        ("5000 Dr", 5000.0),
        ("5000 Cr", -5000.0),
        ("", None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_to_amount(raw, expected):
    assert xp.to_amount(raw) == expected


def test_element_to_dict_collapses_repeated_tags():
    root = xp.parse("<V><L>A</L><L>B</L><X>1</X></V>")
    d = xp.element_to_dict(root)
    assert d["L"] == ["A", "B"]
    assert d["X"] == "1"


def test_parse_import_response_success():
    res = xp.parse_import_response(load_fixture("import_success.xml"))
    assert res["ok"] is True
    assert res["created"] == 1
    assert res["errors"] == 0
    assert res["last_vch_id"] == 4521
    assert res["lineerror"] == ""


def test_parse_import_response_error_does_not_raise():
    res = xp.parse_import_response(load_fixture("import_error.xml"))
    assert res["ok"] is False
    assert res["errors"] == 1
    assert "Office Rent" in res["lineerror"]
