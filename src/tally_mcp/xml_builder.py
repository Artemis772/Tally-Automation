"""Build Tally XML request envelopes.

Two request shapes are produced here:

1. **Report export** (``TYPE=Data``, ``ID=<report>``) for Tally's built-in reports
   such as Trial Balance, Profit & Loss, Balance Sheet and Day Book.

2. **Collection export** (``TYPE=Collection``) with an inline TDL collection that
   declares exactly which fields to ``FETCH``.  This returns clean, flat XML and
   is the preferred path for master/list data (ledgers, groups, stock items,
   outstanding bills, companies).

Phase 2 (writes) helpers build ``TALLYREQUEST=Import`` envelopes for vouchers and
ledger masters; they are defined here but only used once writes are enabled.

All user-supplied text is XML-escaped via :func:`esc`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping, Sequence
from xml.sax.saxutils import escape


def esc(value: object) -> str:
    """XML-escape a value for safe inclusion in a request body."""
    return escape("" if value is None else str(value))


def to_tally_date(value: str | date | datetime) -> str:
    """Convert an ISO date (``YYYY-MM-DD``) or date object to Tally's ``YYYYMMDD``.

    Already-``YYYYMMDD`` strings are passed through unchanged.
    """
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y%m%d")
    s = str(value).strip()
    if len(s) == 8 and s.isdigit():
        return s  # already YYYYMMDD
    # Accept YYYY-MM-DD or YYYY/MM/DD
    for sep in ("-", "/"):
        if sep in s:
            parts = s.split(sep)
            if len(parts) == 3:
                y, m, d = parts
                return f"{int(y):04d}{int(m):02d}{int(d):02d}"
    raise ValueError(f"Unrecognised date format: {value!r} (use YYYY-MM-DD)")


def _static_variables(
    *,
    company: str | None = None,
    from_date: str | date | datetime | None = None,
    to_date: str | date | datetime | None = None,
    extra: Mapping[str, str] | None = None,
    export_format: str = "$$SysName:XML",
) -> str:
    rows = [f"<SVEXPORTFORMAT>{esc(export_format)}</SVEXPORTFORMAT>"]
    if company:
        rows.append(f"<SVCURRENTCOMPANY>{esc(company)}</SVCURRENTCOMPANY>")
    if from_date is not None:
        rows.append(f"<SVFROMDATE TYPE=\"Date\">{esc(to_tally_date(from_date))}</SVFROMDATE>")
    if to_date is not None:
        rows.append(f"<SVTODATE TYPE=\"Date\">{esc(to_tally_date(to_date))}</SVTODATE>")
    if extra:
        for key, val in extra.items():
            rows.append(f"<{key}>{esc(val)}</{key}>")
    return "<STATICVARIABLES>" + "".join(rows) + "</STATICVARIABLES>"


def build_report_export(
    report_id: str,
    *,
    company: str | None = None,
    from_date: str | date | datetime | None = None,
    to_date: str | date | datetime | None = None,
    extra_static: Mapping[str, str] | None = None,
) -> str:
    """Envelope to export a built-in Tally report as XML."""
    static = _static_variables(
        company=company, from_date=from_date, to_date=to_date, extra=extra_static
    )
    return (
        "<ENVELOPE>"
        "<HEADER>"
        "<VERSION>1</VERSION>"
        "<TALLYREQUEST>Export</TALLYREQUEST>"
        "<TYPE>Data</TYPE>"
        f"<ID>{esc(report_id)}</ID>"
        "</HEADER>"
        "<BODY><DESC>"
        f"{static}"
        "</DESC></BODY>"
        "</ENVELOPE>"
    )


def build_collection_export(
    collection_name: str,
    *,
    object_type: str,
    fetch: Sequence[str],
    company: str | None = None,
    from_date: str | date | datetime | None = None,
    to_date: str | date | datetime | None = None,
    filters: Mapping[str, str] | None = None,
    child_of: str | None = None,
    belongs_to: bool = False,
) -> str:
    """Envelope to export a custom TDL collection as flat XML.

    Args:
        collection_name: Arbitrary name for the temporary collection.
        object_type: Tally object the collection is built from (e.g. ``Ledger``,
            ``Group``, ``StockItem``, ``Voucher``, ``Bill``, ``Company``).
        fetch: Field names to fetch for each object.
        company: Company to scope the request to.
        from_date / to_date: Optional period (used by voucher collections).
        filters: Mapping of ``filter_name -> $$-style filter expression``. Each is
            emitted as a ``<FILTER>`` reference plus a ``<SYSTEM TYPE="Formula">``.
        child_of: Restrict to objects under this parent (e.g. a group name).
        belongs_to: When ``child_of`` is set, include the whole sub-tree.
    """
    fetch_line = ", ".join(fetch)
    filter_refs = ""
    system_filters = ""
    if filters:
        names = list(filters.keys())
        filter_refs = "".join(f"<FILTER>{esc(n)}</FILTER>" for n in names)
        system_filters = "".join(
            f'<SYSTEM TYPE="Formula" NAME="{esc(n)}">{expr}</SYSTEM>'
            for n, expr in filters.items()
        )

    child_lines = ""
    if child_of:
        child_lines += f"<CHILDOF>{esc(child_of)}</CHILDOF>"
        if belongs_to:
            child_lines += "<BELONGSTO>Yes</BELONGSTO>"

    collection = (
        f'<COLLECTION NAME="{esc(collection_name)}" ISMODIFY="No" ISFIXED="No" '
        f'ISINITIALIZE="No" ISOPTION="No" ISINTERNAL="No">'
        f"<TYPE>{esc(object_type)}</TYPE>"
        f"{child_lines}"
        f"<FETCH>{esc(fetch_line)}</FETCH>"
        f"{filter_refs}"
        "</COLLECTION>"
    )

    static = _static_variables(company=company, from_date=from_date, to_date=to_date)

    return (
        "<ENVELOPE>"
        "<HEADER>"
        "<VERSION>1</VERSION>"
        "<TALLYREQUEST>Export</TALLYREQUEST>"
        "<TYPE>Collection</TYPE>"
        f"<ID>{esc(collection_name)}</ID>"
        "</HEADER>"
        "<BODY><DESC>"
        f"{static}"
        "<TDL><TDLMESSAGE>"
        f"{collection}"
        f"{system_filters}"
        "</TDLMESSAGE></TDL>"
        "</DESC></BODY>"
        "</ENVELOPE>"
    )


def build_company_collection() -> str:
    """Collection of companies currently loaded/open in Tally."""
    return build_collection_export(
        "TMCP_Companies",
        object_type="Company",
        fetch=["Name", "StartingFrom", "EndingAt"],
    )


# ---------------------------------------------------------------------------
# Phase 2: write envelopes (Import). Defined now; gated by config at call site.
# ---------------------------------------------------------------------------

# Accounting (non-inventory) voucher types supported this iteration.
ACCOUNTING_VOUCHER_TYPES = ("Payment", "Receipt", "Contra", "Journal")

def build_ledger_master(
    name: str,
    *,
    parent_group: str,
    opening_balance: float | None = None,
    company: str | None = None,
) -> str:
    """Import envelope that creates (or alters) a ledger master."""
    opening = ""
    if opening_balance is not None:
        opening = f"<OPENINGBALANCE>{esc(opening_balance)}</OPENINGBALANCE>"
    static = _static_variables(company=company) if company else "<STATICVARIABLES></STATICVARIABLES>"
    return (
        "<ENVELOPE>"
        "<HEADER>"
        "<VERSION>1</VERSION>"
        "<TALLYREQUEST>Import</TALLYREQUEST>"
        "<TYPE>Data</TYPE>"
        "<ID>All Masters</ID>"
        "</HEADER>"
        "<BODY><DESC>"
        f"{static}"
        "</DESC>"
        "<DATA><TALLYMESSAGE>"
        f'<LEDGER NAME="{esc(name)}" ACTION="Create">'
        f"<NAME>{esc(name)}</NAME>"
        f"<PARENT>{esc(parent_group)}</PARENT>"
        f"{opening}"
        "</LEDGER>"
        "</TALLYMESSAGE></DATA>"
        "</BODY>"
        "</ENVELOPE>"
    )


def build_voucher_import(
    *,
    voucher_type: str,
    voucher_date: str | date | datetime,
    entries: Iterable[Mapping[str, object]],
    narration: str = "",
    party_ledger: str | None = None,
    company: str | None = None,
) -> str:
    """Import envelope that creates an accounting voucher.

    Args:
        voucher_type: e.g. ``Payment``, ``Receipt``, ``Contra``, ``Journal``,
            ``Sales``, ``Purchase``.
        voucher_date: Date of the voucher.
        entries: Iterable of ``{"ledger": str, "amount": float}`` where a positive
            amount is a debit and a negative amount is a credit (Tally convention:
            ``ISDEEMEDPOSITIVE=Yes`` and a negative ``AMOUNT`` for debit). See
            reports/writes layer for the exact sign handling.
        narration: Optional narration text.
        party_ledger: Optional party ledger name (for sales/purchase).
    """
    d = to_tally_date(voucher_date)
    static = _static_variables(company=company) if company else "<STATICVARIABLES></STATICVARIABLES>"

    entry_xml = []
    for e in entries:
        ledger = esc(e["ledger"])
        amount = float(e["amount"])  # type: ignore[arg-type]
        deemed_positive = "Yes" if amount < 0 else "No"
        entry_xml.append(
            "<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{ledger}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{deemed_positive}</ISDEEMEDPOSITIVE>"
            f"<AMOUNT>{amount:.2f}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
        )

    party = f"<PARTYLEDGERNAME>{esc(party_ledger)}</PARTYLEDGERNAME>" if party_ledger else ""

    return (
        "<ENVELOPE>"
        "<HEADER>"
        "<VERSION>1</VERSION>"
        "<TALLYREQUEST>Import</TALLYREQUEST>"
        "<TYPE>Data</TYPE>"
        "<ID>Vouchers</ID>"
        "</HEADER>"
        "<BODY><DESC>"
        f"{static}"
        "</DESC>"
        "<DATA><TALLYMESSAGE>"
        f'<VOUCHER VCHTYPE="{esc(voucher_type)}" ACTION="Create">'
        f"<DATE>{d}</DATE>"
        f"<VOUCHERTYPENAME>{esc(voucher_type)}</VOUCHERTYPENAME>"
        f"<NARRATION>{esc(narration)}</NARRATION>"
        f"{party}"
        f"{''.join(entry_xml)}"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA>"
        "</BODY>"
        "</ENVELOPE>"
    )
