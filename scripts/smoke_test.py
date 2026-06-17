#!/usr/bin/env python3
"""Direct connectivity check against a live Tally (no MCP involved).

Run this on the machine where TallyPrime is running with the XML gateway
enabled. It verifies the server can be reached and that a basic collection
export parses correctly.

    python scripts/smoke_test.py

Configuration is read from environment / .env (TALLY_HOST, TALLY_PORT,
TALLY_COMPANY). See .env.example.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running straight from a checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tally_mcp.client import TallyClient, TallyConnectionError  # noqa: E402
from tally_mcp.config import config  # noqa: E402
from tally_mcp import reports  # noqa: E402
from tally_mcp.xml_parser import TallyResponseError  # noqa: E402


def main() -> int:
    print(f"Tally endpoint: {config.base_url}")
    print(f"Default company: {config.company or '(active company)'}")
    client = TallyClient()

    print("\n[1/3] Pinging Tally ...")
    if not client.ping():
        print("  FAILED: could not reach Tally. Is it running with the gateway enabled?")
        return 1
    print("  OK")

    print("\n[2/3] Listing companies ...")
    try:
        companies = reports.list_companies(client)
        for c in companies:
            print(f"  - {c['name']}  ({c['starting_from']} .. {c['ending_at']})")
        if not companies:
            print("  (no companies reported)")
    except (TallyConnectionError, TallyResponseError) as exc:
        print(f"  FAILED: {exc}")
        return 1

    print("\n[3/3] Trial balance (first 10 ledgers) ...")
    try:
        tb = reports.trial_balance(client)
        for row in tb["rows"][:10]:
            print(f"  {row['ledger']:<40} Dr {row['debit']:>14} Cr {row['credit']:>14}")
        print(f"  TOTAL  Dr {tb['total_debit']}  Cr {tb['total_credit']}  balanced={tb['balanced']}")
    except (TallyConnectionError, TallyResponseError) as exc:
        print(f"  FAILED: {exc}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
