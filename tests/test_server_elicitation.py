"""Tests for post_voucher's confirmation (elicitation) behaviour.

Drives the async tool directly with a stub Context, covering accept / decline /
cancel / elicitation-unsupported, plus the explicit confirm=true bypass and
expired-draft handling. No live Tally and no MCP transport needed.
"""

from __future__ import annotations

import pytest

from conftest import FakeTallyClient
from tally_mcp import server, writes
from tally_mcp.config import TallyConfig


class _StubData:
    def __init__(self, confirm: bool):
        self.confirm = confirm


class _StubResult:
    def __init__(self, action: str, confirm: bool | None):
        self.action = action
        self.data = _StubData(confirm) if confirm is not None else None


class StubContext:
    """Mimics mcp Context.elicit for the confirmation dialog."""

    def __init__(self, action: str = "accept", confirm: bool | None = True, raises: bool = False):
        self._action = action
        self._confirm = confirm
        self._raises = raises
        self.called = False

    async def elicit(self, message, schema):
        self.called = True
        if self._raises:
            raise RuntimeError("client does not support elicitation")
        return _StubResult(self._action, self._confirm)


@pytest.fixture
def writes_on(monkeypatch):
    """Enable writes and route posting at an in-memory fake client."""
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=True))
    fake = FakeTallyClient(post_fixture="import_success.xml")
    monkeypatch.setattr(server, "client", fake)
    return fake


def _stage_draft() -> str:
    out = writes.prepare_voucher(
        "Journal", "2026-04-03",
        [{"ledger": "Office Rent", "amount": 20000}, {"ledger": "Cash", "amount": -20000}],
    )
    return out["draft_id"]


async def test_accept_posts(writes_on):
    draft_id = _stage_draft()
    ctx = StubContext(action="accept", confirm=True)
    result = await server.post_voucher(draft_id, ctx=ctx)
    assert ctx.called is True
    assert result["posted"] is True
    assert result["created"] == 1
    assert result["last_vch_id"] == 4521


async def test_decline_does_not_post(writes_on):
    draft_id = _stage_draft()
    result = await server.post_voucher(draft_id, ctx=StubContext(action="decline", confirm=None))
    assert result["posted"] is False
    assert "Not confirmed" in result["reason"]
    assert writes_on.last_post is None  # nothing was sent


async def test_accept_but_confirm_false_does_not_post(writes_on):
    draft_id = _stage_draft()
    result = await server.post_voucher(draft_id, ctx=StubContext(action="accept", confirm=False))
    assert result["posted"] is False
    assert writes_on.last_post is None


async def test_elicitation_unsupported_falls_back_to_not_posted(writes_on):
    draft_id = _stage_draft()
    result = await server.post_voucher(draft_id, ctx=StubContext(raises=True))
    assert result["posted"] is False
    assert writes_on.last_post is None


async def test_confirm_true_bypasses_dialog(writes_on):
    draft_id = _stage_draft()
    result = await server.post_voucher(draft_id, confirm=True, ctx=None)
    assert result["posted"] is True
    assert writes_on.last_post is not None


async def test_unknown_draft_returns_error(writes_on):
    result = await server.post_voucher("deadbeef", confirm=True, ctx=None)
    assert result["posted"] is False
    assert "expired" in result["error"].lower() or "unknown" in result["error"].lower()


async def test_draft_consumed_after_post(writes_on):
    draft_id = _stage_draft()
    await server.post_voucher(draft_id, confirm=True, ctx=None)
    # Posting again should fail because the draft was consumed.
    again = await server.post_voucher(draft_id, confirm=True, ctx=None)
    assert again["posted"] is False


# --- server error branches when Tally is unreachable -------------------------

import socket  # noqa: E402

from tally_mcp.client import TallyClient  # noqa: E402


def _dead_client() -> TallyClient:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return TallyClient(TallyConfig(host="127.0.0.1", port=port, timeout=1), retries=0)


async def test_post_voucher_connection_error(monkeypatch):
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=True))
    monkeypatch.setattr(server, "client", _dead_client())
    draft_id = _stage_draft()
    result = await server.post_voucher(draft_id, confirm=True, ctx=None)
    assert result["posted"] is False
    assert "error" in result


def test_create_ledger_write_disabled(monkeypatch):
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=False))
    result = server.create_ledger("New Client", parent_group="Sundry Debtors")
    assert result["posted"] is False
    assert "disabled" in result["reason"].lower()
    assert "<LEDGER" in result["xml_preview"]


def test_create_ledger_connection_error(monkeypatch):
    monkeypatch.setattr(writes, "config", TallyConfig(allow_writes=True))
    monkeypatch.setattr(server, "client", _dead_client())
    result = server.create_ledger("New Client", parent_group="Sundry Debtors", confirm=True)
    assert result["posted"] is False
    assert "error" in result


def test_verify_voucher_connection_error(monkeypatch):
    monkeypatch.setattr(server, "client", _dead_client())
    result = server.verify_voucher("2026-04-01", "2026-04-30")
    assert result["verified"] is False
    assert "error" in result
