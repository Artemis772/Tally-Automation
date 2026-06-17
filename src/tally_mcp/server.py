"""Tally MCP server: exposes TallyPrime data to Claude as MCP tools.

Phase 1 tools are read-only. Phase 2 write tools (create_ledger / create_voucher)
are registered but guarded twice: the global ``TALLY_ALLOW_WRITES`` flag must be
enabled, and each call defaults to ``dry_run=True`` (returns the XML it *would*
send without posting it).

Run with stdio transport (the default for Claude Desktop / Claude Code):

    tally-mcp
    # or
    python -m tally_mcp
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import reports
from .client import TallyClient, TallyConnectionError
from .config import config
from .xml_builder import build_ledger_master, build_voucher_import
from .xml_parser import TallyResponseError

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
# Phase 2 — write tools (guarded). Enabled only when TALLY_ALLOW_WRITES=true.
# Each defaults to dry_run=True so Claude/users can review the XML first.
# ---------------------------------------------------------------------------

def _write_guard(xml_body: str, dry_run: bool, confirm: bool) -> dict[str, Any] | None:
    """Return a short-circuit response if the write should not be posted yet."""
    if not config.allow_writes:
        return {
            "posted": False,
            "reason": (
                "Writes are disabled. Set TALLY_ALLOW_WRITES=true in your .env "
                "(and back up your company) to enable creating data in Tally."
            ),
            "xml_preview": xml_body,
        }
    if dry_run or not confirm:
        return {
            "posted": False,
            "reason": "Dry run: review the XML, then call again with dry_run=false and confirm=true.",
            "xml_preview": xml_body,
        }
    return None


@mcp.tool()
def create_ledger(
    name: str,
    parent_group: str,
    opening_balance: float | None = None,
    company: str | None = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create a ledger master under ``parent_group``.

    Guarded: requires TALLY_ALLOW_WRITES=true, plus dry_run=false and confirm=true
    to actually post. Defaults to a dry run that returns the XML preview.
    """
    xml_body = build_ledger_master(
        name,
        parent_group=parent_group,
        opening_balance=opening_balance,
        company=reports._company(company),
    )
    guarded = _write_guard(xml_body, dry_run, confirm)
    if guarded is not None:
        return guarded
    try:
        client.request(xml_body)
    except (TallyConnectionError, TallyResponseError) as exc:
        return {"posted": False, "error": str(exc), "xml_preview": xml_body}
    return {"posted": True, "ledger": name, "parent_group": parent_group}


@mcp.tool()
def create_voucher(
    voucher_type: str,
    voucher_date: str,
    entries: list[dict[str, Any]],
    narration: str = "",
    party_ledger: str | None = None,
    company: str | None = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    """Create an accounting voucher.

    Args:
        voucher_type: Payment, Receipt, Contra, Journal, Sales, Purchase, ...
        voucher_date: YYYY-MM-DD.
        entries: list of {"ledger": str, "amount": float}; positive = debit,
            negative = credit. Debits and credits must net to zero.
        narration / party_ledger: optional.

    Guarded: requires TALLY_ALLOW_WRITES=true, plus dry_run=false and confirm=true.
    """
    total = sum(float(e["amount"]) for e in entries)
    if round(total, 2) != 0:
        return {
            "posted": False,
            "error": f"Voucher does not balance: debits/credits net to {total:.2f}, must be 0.",
        }
    xml_body = build_voucher_import(
        voucher_type=voucher_type,
        voucher_date=voucher_date,
        entries=entries,
        narration=narration,
        party_ledger=party_ledger,
        company=reports._company(company),
    )
    guarded = _write_guard(xml_body, dry_run, confirm)
    if guarded is not None:
        return guarded
    try:
        client.request(xml_body)
    except (TallyConnectionError, TallyResponseError) as exc:
        return {"posted": False, "error": str(exc), "xml_preview": xml_body}
    return {"posted": True, "voucher_type": voucher_type, "date": voucher_date}


def main() -> None:
    """Console-script / module entry point. Runs the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
