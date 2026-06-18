"""Tests for the real TallyClient HTTP layer, against the mock Tally gateway."""

from __future__ import annotations

import socket

import pytest

from tally_mcp.client import TallyClient, TallyConnectionError
from tally_mcp.config import TallyConfig
from tally_mcp.xml_builder import build_collection_export
from tally_mcp.xml_parser import TallyResponseError


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _ledger_request(company: str | None = None) -> str:
    return build_collection_export(
        "TMCP_Ledgers", object_type="Ledger", fetch=["Name"], company=company
    )


def test_post_returns_sanitized_text(mock_client):
    text = mock_client.post(_ledger_request())
    assert "<LEDGER" in text
    assert text == text.strip()


def test_request_parses_to_element(mock_client):
    root = mock_client.request(_ledger_request())
    assert root.tag == "ENVELOPE"
    assert root.find(".//LEDGER") is not None


def test_request_raises_on_lineerror(mock_client):
    with pytest.raises(TallyResponseError, match="Nonexistent Co"):
        mock_client.request(_ledger_request(company="Nonexistent Co"))


def test_ping_true_against_mock(mock_client):
    assert mock_client.ping() is True


def test_ping_false_when_unreachable():
    cfg = TallyConfig(host="127.0.0.1", port=_free_port(), timeout=1)
    assert TallyClient(cfg, retries=0).ping() is False


def test_connection_error_after_retries():
    cfg = TallyConfig(host="127.0.0.1", port=_free_port(), timeout=1)
    with pytest.raises(TallyConnectionError, match="Could not reach Tally"):
        TallyClient(cfg, retries=0).post("<ENVELOPE/>")


def test_dirty_latin1_response_is_decoded_and_sanitized(mock_client):
    # The mock returns latin-1 bytes containing a raw \x04 for bodies with "DIRTY".
    text = mock_client.post("<ENVELOPE>DIRTY</ENVELOPE>")
    assert "\x04" not in text       # control char stripped
    assert "caf\xe9" in text         # latin-1 'é' decoded correctly


def test_retry_then_success(mock_tally):
    cfg = TallyConfig(host=mock_tally.host, port=mock_tally.port, timeout=1)
    client = TallyClient(cfg, retries=2)
    # First request stalls past the timeout, forcing one read-timeout + retry.
    mock_tally.controller.delay_next(count=1, seconds=2.0)
    root = client.request(_ledger_request())
    assert root.find(".//LEDGER") is not None
    assert mock_tally.controller.request_count >= 2
