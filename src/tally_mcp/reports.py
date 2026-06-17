"""Read-side business logic: turn Tally responses into clean Python structures.

The robust, well-tested core uses **custom collections** (predictable flat XML).
A few inherently-grouped reports (Profit & Loss, Balance Sheet) use Tally's
built-in report export and a generic row parser; their exact shape can vary by
Tally version, so they are best-effort and easy to adjust.
"""

from __future__ import annotations

from typing import Any

from .client import TallyClient
from .config import config
from .xml_builder import (
    build_collection_export,
    build_company_collection,
    build_report_export,
)
from .xml_parser import extract_objects, to_amount


def _company(override: str | None) -> str | None:
    """Resolve the company to use: explicit override > config default > Tally active."""
    name = (override or config.company or "").strip()
    return name or None


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

def list_companies(client: TallyClient) -> list[dict[str, Any]]:
    root = client.request(build_company_collection())
    out = []
    for obj in extract_objects(root, "COMPANY"):
        out.append(
            {
                "name": obj.get("NAME", ""),
                "starting_from": obj.get("STARTINGFROM", ""),
                "ending_at": obj.get("ENDINGAT", ""),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Masters: groups, ledgers, stock
# ---------------------------------------------------------------------------

def list_groups(client: TallyClient, company: str | None = None) -> list[dict[str, Any]]:
    xml = build_collection_export(
        "TMCP_Groups",
        object_type="Group",
        fetch=["Name", "Parent", "IsRevenue", "IsDeemedPositive"],
        company=_company(company),
    )
    root = client.request(xml)
    return [
        {
            "name": o.get("NAME", ""),
            "parent": o.get("PARENT", ""),
            "is_revenue": o.get("ISREVENUE", ""),
        }
        for o in extract_objects(root, "GROUP")
    ]


def list_ledgers(
    client: TallyClient,
    company: str | None = None,
    group: str | None = None,
) -> list[dict[str, Any]]:
    xml = build_collection_export(
        "TMCP_Ledgers",
        object_type="Ledger",
        fetch=["Name", "Parent", "OpeningBalance", "ClosingBalance"],
        company=_company(company),
        child_of=group or None,
        belongs_to=bool(group),
    )
    root = client.request(xml)
    return [
        {
            "name": o.get("NAME", ""),
            "group": o.get("PARENT", ""),
            "opening_balance": to_amount(o.get("OPENINGBALANCE")),
            "closing_balance": to_amount(o.get("CLOSINGBALANCE")),
        }
        for o in extract_objects(root, "LEDGER")
    ]


def get_ledger_balance(
    client: TallyClient,
    ledger: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Closing balance for a single ledger (case-insensitive match)."""
    matches = [
        led for led in list_ledgers(client, company=company)
        if led["name"].strip().lower() == ledger.strip().lower()
    ]
    if not matches:
        raise ValueError(f"Ledger not found: {ledger!r}")
    return matches[0]


def list_stock_items(
    client: TallyClient,
    company: str | None = None,
) -> list[dict[str, Any]]:
    xml = build_collection_export(
        "TMCP_StockItems",
        object_type="StockItem",
        fetch=["Name", "Parent", "BaseUnits", "ClosingBalance", "ClosingValue"],
        company=_company(company),
    )
    root = client.request(xml)
    return [
        {
            "name": o.get("NAME", ""),
            "group": o.get("PARENT", ""),
            "units": o.get("BASEUNITS", ""),
            "closing_qty": o.get("CLOSINGBALANCE", ""),
            "closing_value": to_amount(o.get("CLOSINGVALUE")),
        }
        for o in extract_objects(root, "STOCKITEM")
    ]


# ---------------------------------------------------------------------------
# Outstanding bills
# ---------------------------------------------------------------------------

def bills_outstanding(
    client: TallyClient,
    kind: str = "receivable",
    company: str | None = None,
) -> list[dict[str, Any]]:
    """Outstanding bills, split by sign of closing balance.

    ``kind="receivable"`` returns debit balances (money owed to you);
    ``kind="payable"`` returns credit balances (money you owe).
    """
    xml = build_collection_export(
        "TMCP_Bills",
        object_type="Bills",
        fetch=["Name", "Parent", "BillDate", "ClosingBalance"],
        company=_company(company),
    )
    root = client.request(xml)
    rows = []
    for o in extract_objects(root, "BILLS"):
        bal = to_amount(o.get("CLOSINGBALANCE"))
        if bal is None or bal == 0:
            continue
        is_receivable = bal > 0
        if (kind == "receivable") != is_receivable:
            continue
        rows.append(
            {
                "bill": o.get("NAME", ""),
                "party": o.get("PARENT", ""),
                "bill_date": o.get("BILLDATE", ""),
                "amount": abs(bal),
                "type": "receivable" if is_receivable else "payable",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Transactions: day book / ledger statement (Voucher collection)
# ---------------------------------------------------------------------------

def _vouchers(
    client: TallyClient,
    from_date: str,
    to_date: str,
    company: str | None,
) -> list[dict[str, Any]]:
    xml = build_collection_export(
        "TMCP_Vouchers",
        object_type="Voucher",
        fetch=[
            "Date",
            "VoucherTypeName",
            "VoucherNumber",
            "PartyLedgerName",
            "Amount",
            "Narration",
            "Reference",
        ],
        company=_company(company),
        from_date=from_date,
        to_date=to_date,
    )
    root = client.request(xml)
    rows = []
    for o in extract_objects(root, "VOUCHER"):
        rows.append(
            {
                "date": o.get("DATE", ""),
                "voucher_type": o.get("VOUCHERTYPENAME", ""),
                "voucher_number": o.get("VOUCHERNUMBER", ""),
                "party": o.get("PARTYLEDGERNAME", ""),
                "amount": to_amount(o.get("AMOUNT")),
                "narration": o.get("NARRATION", ""),
                "reference": o.get("REFERENCE", ""),
            }
        )
    return rows


def day_book(
    client: TallyClient,
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> list[dict[str, Any]]:
    """All vouchers within the given date range."""
    return _vouchers(client, from_date, to_date, company)


def ledger_statement(
    client: TallyClient,
    ledger: str,
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> list[dict[str, Any]]:
    """Vouchers in the range whose party ledger matches ``ledger``.

    Note: matches on the voucher's *party ledger*. For a full multi-leg ledger
    statement, use Tally's ledger report directly; this view covers the common
    party-centric case (sales/purchase/payment/receipt against a party).
    """
    target = ledger.strip().lower()
    return [
        v for v in _vouchers(client, from_date, to_date, company)
        if v["party"].strip().lower() == target
    ]


# ---------------------------------------------------------------------------
# Trial balance (derived from ledgers — predictable & robust)
# ---------------------------------------------------------------------------

def trial_balance(
    client: TallyClient,
    company: str | None = None,
) -> dict[str, Any]:
    """Ledger-level trial balance derived from closing balances.

    Returns per-ledger debit/credit columns plus totals. In Tally's sign
    convention a positive closing balance is a debit and negative is a credit.
    """
    ledgers = list_ledgers(client, company=company)
    rows = []
    total_debit = 0.0
    total_credit = 0.0
    for led in ledgers:
        bal = led["closing_balance"]
        if bal is None or bal == 0:
            continue
        debit = bal if bal > 0 else 0.0
        credit = -bal if bal < 0 else 0.0
        total_debit += debit
        total_credit += credit
        rows.append(
            {
                "ledger": led["name"],
                "group": led["group"],
                "debit": round(debit, 2),
                "credit": round(credit, 2),
            }
        )
    return {
        "rows": rows,
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "balanced": round(total_debit - total_credit, 2) == 0,
    }


# ---------------------------------------------------------------------------
# Grouped reports via built-in report export (best-effort)
# ---------------------------------------------------------------------------

def _report_rows(root) -> list[dict[str, Any]]:
    """Generic flattener: pair Tally's DSPACCNAME / DSPACCINFO display rows.

    Tally renders most grouped reports as a sequence of ``DSPDISPNAME`` (label)
    and a nearby amount field (``DSPCLDRAMT`` / ``DSPCLCRAMT`` / ``DSPACCINFO``).
    We collect any element whose tag carries a name plus a sibling amount.
    """
    rows: list[dict[str, Any]] = []
    for name_el in root.iter("DSPDISPNAME"):
        label = (name_el.text or "").strip()
        if label:
            rows.append({"name": label})
    # Attach amounts positionally where present.
    amounts = [
        to_amount(a.text)
        for tag in ("DSPCLDRAMT", "DSPCLCRAMT", "DSPACCINFO")
        for a in root.iter(tag)
    ]
    for row, amt in zip(rows, amounts):
        row["amount"] = amt
    return rows


def profit_and_loss(
    client: TallyClient,
    from_date: str,
    to_date: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Profit & Loss report (best-effort parse of Tally's built-in report)."""
    xml = build_report_export(
        "Profit and Loss",
        company=_company(company),
        from_date=from_date,
        to_date=to_date,
    )
    root = client.request(xml)
    return {"report": "Profit and Loss", "rows": _report_rows(root)}


def balance_sheet(
    client: TallyClient,
    as_on: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Balance Sheet as on a date (best-effort parse of Tally's built-in report)."""
    xml = build_report_export(
        "Balance Sheet",
        company=_company(company),
        to_date=as_on,
    )
    root = client.request(xml)
    return {"report": "Balance Sheet", "as_on": as_on, "rows": _report_rows(root)}
