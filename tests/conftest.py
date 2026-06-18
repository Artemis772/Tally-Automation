"""Shared test helpers: load XML fixtures and a fake Tally client."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from tally_mcp.xml_parser import parse

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeTallyClient:
    """Stands in for TallyClient, returning fixtures based on the request body.

    Routes on the collection ``<TYPE>...</TYPE>`` declared inside the request so
    that report functions (which build their own XML) get the right fixture.
    """

    ROUTES = {
        "<TYPE>Company</TYPE>": "companies.xml",
        "<TYPE>Ledger</TYPE>": "ledgers.xml",
        "<TYPE>Voucher</TYPE>": "vouchers.xml",
        "<TYPE>Bills</TYPE>": "bills.xml",
    }

    def __init__(self, post_fixture: str = "import_success.xml") -> None:
        self.last_request: str | None = None
        self.last_post: str | None = None
        self.post_fixture = post_fixture

    def request(self, xml_body: str) -> ET.Element:
        self.last_request = xml_body
        for marker, fixture in self.ROUTES.items():
            if marker in xml_body:
                return parse(load_fixture(fixture))
        raise AssertionError(f"No fixture route matched request:\n{xml_body}")

    def post(self, xml_body: str) -> str:
        """Used by write paths; returns the configured import-response fixture."""
        self.last_post = xml_body
        return load_fixture(self.post_fixture).decode("utf-8")

    def ping(self) -> bool:
        return True


@pytest.fixture
def fake_client() -> FakeTallyClient:
    return FakeTallyClient()


@pytest.fixture
def mock_tally():
    """A running mock Tally gateway (real HTTP server on an ephemeral port)."""
    from mock_tally import MockTally

    server = MockTally().start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def mock_client(mock_tally):
    """A real TallyClient pointed at the mock gateway."""
    from tally_mcp.client import TallyClient
    from tally_mcp.config import TallyConfig

    cfg = TallyConfig(host=mock_tally.host, port=mock_tally.port, timeout=5)
    return TallyClient(cfg)
