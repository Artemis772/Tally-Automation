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

    def __init__(self) -> None:
        self.last_request: str | None = None

    def request(self, xml_body: str) -> ET.Element:
        self.last_request = xml_body
        for marker, fixture in self.ROUTES.items():
            if marker in xml_body:
                return parse(load_fixture(fixture))
        raise AssertionError(f"No fixture route matched request:\n{xml_body}")

    def ping(self) -> bool:
        return True


@pytest.fixture
def fake_client() -> FakeTallyClient:
    return FakeTallyClient()
