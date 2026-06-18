"""End-to-end tests over the real MCP protocol (in-memory client+server).

Drives tools the way a client (Claude Code) would: list_tools and call_tool over
an in-memory transport, including the elicitation round-trip for post_voucher.
server.client is pointed at the mock Tally gateway.
"""

from __future__ import annotations

import json

import mcp.types as types
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from tally_mcp import server, writes
from tally_mcp.client import TallyClient
from tally_mcp.config import TallyConfig


@pytest.fixture
def wired(mock_tally, monkeypatch):
    """Point the server's client at the mock gateway and enable writes."""
    cfg = TallyConfig(host=mock_tally.host, port=mock_tally.port, timeout=5)
    monkeypatch.setattr(server, "client", TallyClient(cfg))
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=True))
    return mock_tally


def _data(result):
    if result.structuredContent is not None:
        sc = result.structuredContent
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    return json.loads(result.content[0].text)


async def _accept(context, params):
    return types.ElicitResult(action="accept", content={"confirm": True})


async def _decline(context, params):
    return types.ElicitResult(action="decline", content=None)


async def test_list_tools_and_schema(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        tools = (await session.list_tools()).tools
        names = {t.name for t in tools}
    assert len(names) == 16
    assert {"prepare_voucher", "post_voucher", "verify_voucher", "create_ledger"} <= names
    post = next(t for t in tools if t.name == "post_voucher")
    assert "ctx" not in post.inputSchema.get("properties", {})


async def test_read_tools_over_protocol(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        health = _data(await session.call_tool("tally_health", {}))
        assert health["ok"] is True

        ledgers = _data(await session.call_tool("list_ledgers", {}))
        assert any(l["name"] == "Cash" for l in ledgers)

        tb = _data(await session.call_tool("trial_balance", {}))
        assert tb["balanced"] is False


async def test_error_envelope_over_protocol(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        out = _data(await session.call_tool("list_ledgers", {"company": "Nonexistent Co"}))
    assert "error" in out
    assert "Nonexistent Co" in out["error"]


async def test_prepare_then_post_confirm_true(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        prep = _data(await session.call_tool(
            "prepare_voucher",
            {
                "voucher_type": "Journal",
                "voucher_date": "2026-04-03",
                "entries": [
                    {"ledger": "Office Rent", "amount": 20000},
                    {"ledger": "Cash", "amount": -20000},
                ],
            },
        ))
        draft_id = prep["draft_id"]
        posted = _data(await session.call_tool(
            "post_voucher", {"draft_id": draft_id, "confirm": True}
        ))
    assert posted["posted"] is True
    assert posted["created"] == 1


async def test_post_voucher_via_elicitation_accept(wired):
    async with create_connected_server_and_client_session(
        server.mcp, elicitation_callback=_accept
    ) as session:
        prep = _data(await session.call_tool(
            "prepare_voucher",
            {
                "voucher_type": "Payment",
                "voucher_date": "2026-04-05",
                "entries": [
                    {"ledger": "Office Rent", "amount": 5000},
                    {"ledger": "Cash", "amount": -5000},
                ],
            },
        ))
        posted = _data(await session.call_tool("post_voucher", {"draft_id": prep["draft_id"]}))
    assert posted["posted"] is True


async def test_post_voucher_via_elicitation_decline(wired):
    async with create_connected_server_and_client_session(
        server.mcp, elicitation_callback=_decline
    ) as session:
        prep = _data(await session.call_tool(
            "prepare_voucher",
            {
                "voucher_type": "Contra",
                "voucher_date": "2026-04-06",
                "entries": [
                    {"ledger": "Cash", "amount": 1000},
                    {"ledger": "Bank", "amount": -1000},
                ],
            },
        ))
        posted = _data(await session.call_tool("post_voucher", {"draft_id": prep["draft_id"]}))
    assert posted["posted"] is False


async def test_create_ledger_dry_run_vs_confirm(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        dry = _data(await session.call_tool(
            "create_ledger", {"name": "New Client", "parent_group": "Sundry Debtors"}
        ))
        assert dry["posted"] is False
        assert "<LEDGER" in dry["xml_preview"]

        live = _data(await session.call_tool(
            "create_ledger",
            {"name": "New Client", "parent_group": "Sundry Debtors", "confirm": True},
        ))
        assert live["posted"] is True


async def test_all_read_tools_over_protocol(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        for name, args in [
            ("list_companies", {}),
            ("list_groups", {}),
            ("get_ledger_balance", {"ledger": "Cash"}),
            ("profit_and_loss", {"from_date": "2026-04-01", "to_date": "2026-04-30"}),
            ("balance_sheet", {"as_on": "2026-04-30"}),
            ("day_book", {"from_date": "2026-04-01", "to_date": "2026-04-30"}),
            ("ledger_statement", {"ledger": "ABC Traders & Co",
                                  "from_date": "2026-04-01", "to_date": "2026-04-30"}),
            ("bills_outstanding", {"kind": "receivable"}),
            ("bills_outstanding", {"kind": "payable"}),
            ("list_stock_items", {}),
        ]:
            result = await session.call_tool(name, args)
            assert result.isError is False, name


async def test_bills_outstanding_bad_kind(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        out = _data(await session.call_tool("bills_outstanding", {"kind": "nonsense"}))
    assert "error" in out


async def test_verify_voucher_over_protocol(wired):
    async with create_connected_server_and_client_session(server.mcp) as session:
        out = _data(await session.call_tool(
            "verify_voucher",
            {
                "from_date": "2026-04-01",
                "to_date": "2026-04-30",
                "voucher_type": "Sales",
                "amount": 15000,
            },
        ))
    assert out["verified"] is True
