"""Tally MCP server: exposes TallyPrime data to Claude as MCP tools.

Phase 1 tools are read-only.

Phase 2 write tools use a **prepare -> confirm -> post -> verify** flow:
- ``prepare_voucher`` validates and stages a voucher, returning a preview.
- ``post_voucher`` shows the entries in a confirmation dialog (MCP *elicitation*,
  supported by Claude Code) and only posts on approval. If the client doesn't
  support elicitation, pass ``confirm=true`` explicitly.
- ``verify_voucher`` independently re-reads Tally to confirm the result.

Writes are guarded by ``TALLY_ALLOW_WRITES`` and, optionally, locked to a single
``TALLY_WRITE_COMPANY`` (e.g. a test company).

Run with stdio transport (the default for Claude Desktop / Claude Code):

    tally-mcp
    # or
    python -m tally_mcp
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from . import reports, writes
from .client import TallyClient, TallyConnectionError
from .config import config
from .drafts import drafts
from .xml_builder import build_ledger_master
from .xml_parser import TallyResponseError
from .writes import WriteError

mcp = FastMCP("tally")
client = TallyClient()


def _safe(fn, *args, **kwargs) -> Any:
    """Run a report call, converting Tally/connection errors into clear messages."""
    try:
        return fn(client, *args, **kwargs)
    except (TallyConnectionError, TallyResponseError, ValueError) as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Phase 1 — read-only tools
# ---------------------------------------------------------------------------

@mcp.tool()
def tally_health() -> dict[str, Any]:
    """Check connectivity to Tally and list the companies currently open.

    Use this first to confirm the MCP server can reach TallyPrime.
    """
    if not client.ping():
        return {
            "ok": False,
            "message": (
                f"Cannot reach Tally at {config.base_url}. Ensure TallyPrime is "
                "running and its XML/HTTP gateway is enabled on the configured port."
            ),
        }
    companies = _safe(reports.list_companies)
    return {"ok": True, "endpoint": config.base_url, "companies": companies}


@mcp.tool()
def list_companies() -> list[dict[str, Any]] | dict[str, Any]:
    """List the companies currently loaded/open in Tally."""
    return _safe(reports.list_companies)


@mcp.tool()
def list_groups(company: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """List account groups (chart-of-accounts groups). Optional company override."""
    return _safe(reports.list_groups, company=company)


@mcp.tool()
def list_ledgers(
    group: str | None = None,
    company: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """List ledgers with opening/closing balances.

    Args:
        group: Optional account group to restrict to (includes sub-groups).
        company: Optional company name (defaults to configured/active company).
    """
    return _safe(reports.list_ledgers, company=company, group=group)


@mcp.tool()
def get_ledger_balance(
    ledger: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Get the closing balance for a single ledger by name."""
    return _safe(reports.get_ledger_balance, ledger, company=company)


@mcp.tool()
def trial_balance(company: str | None = None) -> dict[str, Any]:
    """Ledger-level trial balance (debit/credit columns and totals)."""
    return _safe(reports.trial_balance, company=company)


@mcp.tool()
def profit_and_loss(
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Profit & Loss for a period. Dates as YYYY-MM-DD."""
    return _safe(reports.profit_and_loss, from_date, to_date, company=company)


@mcp.tool()
def balance_sheet(as_on: str, company: str | None = None) -> dict[str, Any]:
    """Balance Sheet as on a date (YYYY-MM-DD)."""
    return _safe(reports.balance_sheet, as_on, company=company)


@mcp.tool()
def day_book(
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """All vouchers within a date range (YYYY-MM-DD)."""
    return _safe(reports.day_book, from_date, to_date, company=company)


@mcp.tool()
def ledger_statement(
    ledger: str,
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Vouchers for a party ledger within a date range (YYYY-MM-DD)."""
    return _safe(reports.ledger_statement, ledger, from_date, to_date, company=company)


@mcp.tool()
def bills_outstanding(
    kind: str = "receivable",
    company: str | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Outstanding bills. ``kind`` is "receivable" (owed to you) or "payable"."""
    if kind not in ("receivable", "payable"):
        return {"error": 'kind must be "receivable" or "payable"'}
    return _safe(reports.bills_outstanding, kind, company=company)


@mcp.tool()
def list_stock_items(company: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """List stock items with closing quantity and value."""
    return _safe(reports.list_stock_items, company=company)


# ---------------------------------------------------------------------------
# Phase 2 — write tools. Flow: prepare -> (elicit) confirm -> post -> verify.
# Enabled only when TALLY_ALLOW_WRITES=true; optionally locked to one company.
# ---------------------------------------------------------------------------

class _ConfirmPost(BaseModel):
    """Schema for the post confirmation dialog (MCP elicitation)."""

    confirm: bool = Field(
        default=False,
        description="Post this voucher to Tally now? Review the entries above first.",
    )


@mcp.tool()
def prepare_voucher(
    voucher_type: str,
    voucher_date: str,
    entries: list[dict[str, Any]],
    narration: str = "",
    company: str | None = None,
) -> dict[str, Any]:
    """Stage an accounting voucher and return a preview to review (no write).

    Args:
        voucher_type: Payment, Receipt, Contra, or Journal.
        voucher_date: YYYY-MM-DD.
        entries: list of {"ledger": str, "amount": float}; positive = debit,
            negative = credit. Must net to zero.
        narration: optional note.
        company: optional; ignored/validated against TALLY_WRITE_COMPANY if set.

    Returns a ``draft_id`` and a ``preview`` (with a ready-to-read ``text`` table).
    Call ``post_voucher(draft_id)`` to actually post it after review.
    """
    try:
        return writes.prepare_voucher(
            voucher_type, voucher_date, entries, narration=narration, company=company
        )
    except WriteError as exc:
        return {"error": str(exc)}


@mcp.tool()
async def post_voucher(
    draft_id: str,
    confirm: bool = False,
    ctx: Context = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Post a previously prepared voucher to Tally.

    Shows the staged entries in a confirmation dialog (elicitation) and posts only
    on approval. If the client does not support elicitation, pass ``confirm=true``.
    """
    draft = drafts.get(draft_id)
    if draft is None:
        return {"posted": False, "error": f"Unknown or expired draft_id {draft_id!r}. Call prepare_voucher again."}

    preview = writes.build_preview(
        draft["voucher_type"], draft["voucher_date"], draft["entries"],
        draft.get("narration", ""), draft.get("company"),
    )

    # Confirmation gate: explicit confirm flag, else an elicitation dialog.
    if not confirm:
        approved = False
        if ctx is not None:
            try:
                result = await ctx.elicit(
                    message="Confirm posting this voucher to Tally:\n\n" + preview["text"],
                    schema=_ConfirmPost,
                )
                approved = result.action == "accept" and bool(result.data and result.data.confirm)
            except Exception:
                approved = False  # client lacks elicitation support
        if not approved:
            return {
                "posted": False,
                "reason": "Not confirmed. Review the preview, then approve the dialog or call post_voucher(draft_id, confirm=true).",
                "preview": preview,
            }

    drafts.pop(draft_id)  # consume the draft
    try:
        return writes.post_draft(client, draft)
    except (TallyConnectionError, TallyResponseError, WriteError) as exc:
        return {"posted": False, "error": str(exc), "preview": preview}


@mcp.tool()
def verify_voucher(
    from_date: str,
    to_date: str,
    voucher_type: str | None = None,
    ledger: str | None = None,
    amount: float | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Independently confirm a voucher exists by re-reading Tally's day book.

    Filters the day book in the date range by voucher type, party ledger, and/or
    absolute amount. Read-only — proof from Tally's own data.
    """
    try:
        return writes.verify_voucher(
            client, from_date, to_date,
            voucher_type=voucher_type, ledger=ledger, amount=amount, company=company,
        )
    except (TallyConnectionError, TallyResponseError) as exc:
        return {"verified": False, "error": str(exc)}


@mcp.tool()
def create_ledger(
    name: str,
    parent_group: str,
    opening_balance: float | None = None,
    company: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a ledger master under ``parent_group``.

    Guarded by TALLY_ALLOW_WRITES and the optional TALLY_WRITE_COMPANY lock.
    Defaults to a dry run (returns the XML preview); pass ``confirm=true`` to post.
    """
    try:
        writes.ensure_writes_enabled()
        target = writes.resolve_write_company(company)
    except WriteError as exc:
        xml_body = build_ledger_master(name, parent_group=parent_group,
                                       opening_balance=opening_balance)
        return {"posted": False, "reason": str(exc), "xml_preview": xml_body}

    xml_body = build_ledger_master(
        name, parent_group=parent_group, opening_balance=opening_balance, company=target,
    )
    if not confirm:
        return {
            "posted": False,
            "reason": "Dry run: review the XML, then call again with confirm=true.",
            "xml_preview": xml_body,
        }
    try:
        from .xml_parser import parse_import_response
        result = parse_import_response(client.post(xml_body))
    except (TallyConnectionError, TallyResponseError) as exc:
        return {"posted": False, "error": str(exc), "xml_preview": xml_body}
    result["posted"] = bool(result.get("ok"))
    result["ledger"] = name
    return result


def main() -> None:  # pragma: no cover
    """Console-script / module entry point. Runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
