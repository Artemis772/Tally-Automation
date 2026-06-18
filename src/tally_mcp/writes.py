"""Write-side business logic: prepare / post / verify accounting vouchers.

Kept free of MCP/FastMCP specifics so it is unit-testable without a server or a
live Tally. The server layer (`server.py`) wraps these in tools and adds the
elicitation confirmation UI.

Sign convention for ``entries``: each entry is ``{"ledger": str, "amount": float}``
where a **positive amount is a debit** and a **negative amount is a credit**.
Debits and credits must net to zero.
"""

from __future__ import annotations

from typing import Any

from .client import TallyClient
from .config import config
from .drafts import drafts
from .xml_builder import ACCOUNTING_VOUCHER_TYPES, build_voucher_import
from .xml_parser import parse_import_response

ROUND = 2


class WriteError(RuntimeError):
    """Raised when a write is disallowed or invalid (before anything is sent)."""


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def ensure_writes_enabled() -> None:
    if not config.allow_writes:
        raise WriteError(
            "Writes are disabled. Set TALLY_ALLOW_WRITES=true in your environment "
            "(and back up your company) to enable creating data in Tally."
        )


def resolve_write_company(company: str | None) -> str | None:
    """Resolve the target company and enforce the optional test-company lock."""
    target = (company or config.company or "").strip()
    lock = config.write_company.strip()
    if lock:
        if not target:
            target = lock  # default to the locked company
        if target.lower() != lock.lower():
            raise WriteError(
                f"Writes are locked to company {lock!r} (TALLY_WRITE_COMPANY); "
                f"refusing to write to {target!r}."
            )
    return target or None


# ---------------------------------------------------------------------------
# Validation + preview
# ---------------------------------------------------------------------------

def normalize_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries or len(entries) < 2:
        raise WriteError("A voucher needs at least two ledger entries.")
    out = []
    for i, e in enumerate(entries):
        if "ledger" not in e or str(e["ledger"]).strip() == "":
            raise WriteError(f"Entry {i + 1} is missing a ledger name.")
        try:
            amount = float(e["amount"])
        except (KeyError, TypeError, ValueError):
            raise WriteError(f"Entry {i + 1} ({e.get('ledger')!r}) has an invalid amount.")
        if amount == 0:
            raise WriteError(f"Entry {i + 1} ({e['ledger']!r}) has a zero amount.")
        out.append({"ledger": str(e["ledger"]).strip(), "amount": round(amount, ROUND)})
    return out


def validate_voucher(voucher_type: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if voucher_type not in ACCOUNTING_VOUCHER_TYPES:
        raise WriteError(
            f"Voucher type {voucher_type!r} is not supported. This iteration handles "
            f"accounting vouchers only: {', '.join(ACCOUNTING_VOUCHER_TYPES)}."
        )
    norm = normalize_entries(entries)
    net = round(sum(e["amount"] for e in norm), ROUND)
    if net != 0:
        raise WriteError(
            f"Voucher does not balance: debits and credits net to {net:.2f}, must be 0."
        )
    return norm


def build_preview(
    voucher_type: str,
    voucher_date: str,
    entries: list[dict[str, Any]],
    narration: str,
    company: str | None,
) -> dict[str, Any]:
    """Return a structured + text preview (no side effects)."""
    rows = []
    total_debit = 0.0
    total_credit = 0.0
    for e in entries:
        amt = e["amount"]
        debit = amt if amt > 0 else 0.0
        credit = -amt if amt < 0 else 0.0
        total_debit += debit
        total_credit += credit
        rows.append({"ledger": e["ledger"], "debit": round(debit, ROUND), "credit": round(credit, ROUND)})
    return {
        "voucher_type": voucher_type,
        "date": voucher_date,
        "company": company or "(Tally active company)",
        "narration": narration,
        "rows": rows,
        "total_debit": round(total_debit, ROUND),
        "total_credit": round(total_credit, ROUND),
        "balanced": round(total_debit - total_credit, ROUND) == 0,
        "text": _format_preview_text(voucher_type, voucher_date, company, narration, rows,
                                     total_debit, total_credit),
    }


def _format_preview_text(voucher_type, date, company, narration, rows, td, tc) -> str:
    lines = [
        f"**{voucher_type} voucher** — {date}",
        f"Company: {company or '(Tally active company)'}",
        "",
        "| Ledger | Debit | Credit |",
        "| --- | ---: | ---: |",
    ]
    for r in rows:
        lines.append(
            f"| {r['ledger']} | {r['debit']:.2f} | {r['credit']:.2f} |"
            if r["debit"] or r["credit"]
            else f"| {r['ledger']} | | |"
        )
    lines.append(f"| **Total** | **{td:.2f}** | **{tc:.2f}** |")
    if narration:
        lines.append(f"\nNarration: {narration}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prepare -> Post -> Verify
# ---------------------------------------------------------------------------

def prepare_voucher(
    voucher_type: str,
    voucher_date: str,
    entries: list[dict[str, Any]],
    narration: str = "",
    company: str | None = None,
) -> dict[str, Any]:
    """Validate and stage a voucher; returns a preview + ``draft_id``. No write."""
    ensure_writes_enabled()
    target_company = resolve_write_company(company)
    norm = validate_voucher(voucher_type, entries)
    preview = build_preview(voucher_type, voucher_date, norm, narration, target_company)
    draft_id = drafts.put(
        {
            "voucher_type": voucher_type,
            "voucher_date": voucher_date,
            "entries": norm,
            "narration": narration,
            "company": target_company,
        }
    )
    return {"draft_id": draft_id, "preview": preview}


def post_draft(client: TallyClient, draft: dict[str, Any]) -> dict[str, Any]:
    """Post a staged draft to Tally and return parsed import counters."""
    ensure_writes_enabled()
    resolve_write_company(draft.get("company"))  # re-check the lock at post time
    xml_body = build_voucher_import(
        voucher_type=draft["voucher_type"],
        voucher_date=draft["voucher_date"],
        entries=draft["entries"],
        narration=draft.get("narration", ""),
        company=draft.get("company"),
    )
    raw = client.post(xml_body)
    result = parse_import_response(raw)
    result["voucher_type"] = draft["voucher_type"]
    result["date"] = draft["voucher_date"]
    result["company"] = draft.get("company")
    result["posted"] = bool(result.get("ok"))
    return result


def verify_voucher(
    client: TallyClient,
    from_date: str,
    to_date: str,
    voucher_type: str | None = None,
    ledger: str | None = None,
    amount: float | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Independently confirm a voucher exists by re-reading Tally's day book.

    Filters the day book in the date range by any provided criteria (type, party
    ledger, absolute amount). This is read-only proof from Tally's own data.
    """
    from . import reports  # local import to avoid a cycle

    vouchers = reports.day_book(client, from_date, to_date, company=company)
    matches = []
    for v in vouchers:
        if voucher_type and v.get("voucher_type", "").lower() != voucher_type.lower():
            continue
        if ledger and v.get("party", "").lower() != ledger.lower():
            continue
        if amount is not None:
            v_amt = v.get("amount")
            if v_amt is None or abs(abs(v_amt) - abs(amount)) > 0.01:
                continue
        matches.append(v)
    return {
        "verified": len(matches) > 0,
        "match_count": len(matches),
        "matches": matches,
        "searched": {
            "from_date": from_date,
            "to_date": to_date,
            "voucher_type": voucher_type,
            "ledger": ledger,
            "amount": amount,
        },
    }
