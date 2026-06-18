#!/usr/bin/env python3
"""End-to-end test harness against a LIVE TallyPrime.

Run this on the machine where Tally is reachable. By default it exercises every
read tool and prints a PASS/FAIL table. With ``--write`` it additionally runs the
full prepare -> post -> verify loop for a Journal voucher (use a TEST company!).

    python scripts/e2e_test.py
    python scripts/e2e_test.py --from 2026-04-01 --to 2026-04-30
    python scripts/e2e_test.py --write --company "ZZ Test Co" \\
        --debit-ledger "Office Rent" --credit-ledger "Cash" --amount 100

Reads connection settings from the environment / .env (see .env.example). Writes
require TALLY_ALLOW_WRITES=true; pairing with TALLY_WRITE_COMPANY (or --company)
is strongly recommended so you can only touch a throwaway company.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tally_mcp import reports, writes  # noqa: E402
from tally_mcp.client import TallyClient, TallyConnectionError  # noqa: E402
from tally_mcp.config import config  # noqa: E402
from tally_mcp.xml_parser import TallyResponseError  # noqa: E402

PASS, FAIL = "PASS", "FAIL"


class Runner:
    def __init__(self) -> None:
        self.client = TallyClient()
        self.results: list[tuple[str, str, str]] = []

    def check(self, name: str, fn) -> None:
        try:
            value = fn()
            summary = self._summarize(value)
            self.results.append((name, PASS, summary))
            print(f"  [{PASS}] {name}: {summary}")
        except (TallyConnectionError, TallyResponseError, ValueError, AssertionError) as exc:
            self.results.append((name, FAIL, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")

    @staticmethod
    def _summarize(value) -> str:
        if isinstance(value, list):
            return f"{len(value)} rows"
        if isinstance(value, dict):
            keys = ", ".join(list(value)[:4])
            return f"keys: {keys}"
        return str(value)

    def report(self) -> int:
        passed = sum(1 for _, status, _ in self.results if status == PASS)
        total = len(self.results)
        print(f"\n{passed}/{total} checks passed.")
        return 0 if passed == total else 1


def run_reads(r: Runner, from_date: str, to_date: str) -> None:
    print("\n== Read tools ==")
    c = r.client
    r.check("tally_health (ping)", lambda: ("ok" if c.ping() else _raise("ping failed")))
    r.check("list_companies", lambda: reports.list_companies(c))
    r.check("list_groups", lambda: reports.list_groups(c))
    r.check("list_ledgers", lambda: reports.list_ledgers(c))
    r.check("list_stock_items", lambda: reports.list_stock_items(c))
    r.check("trial_balance", lambda: reports.trial_balance(c))
    r.check("profit_and_loss", lambda: reports.profit_and_loss(c, from_date, to_date))
    r.check("balance_sheet", lambda: reports.balance_sheet(c, to_date))
    r.check("day_book", lambda: reports.day_book(c, from_date, to_date))
    r.check("bills_outstanding (receivable)", lambda: reports.bills_outstanding(c, "receivable"))
    r.check("bills_outstanding (payable)", lambda: reports.bills_outstanding(c, "payable"))


def run_write(r: Runner, args) -> None:
    print("\n== Write loop (prepare -> post -> verify) ==")
    today = date.today().isoformat()
    entries = [
        {"ledger": args.debit_ledger, "amount": args.amount},
        {"ledger": args.credit_ledger, "amount": -args.amount},
    ]
    try:
        prep = writes.prepare_voucher("Journal", today, entries,
                                      narration="e2e test", company=args.company)
        print(prep["preview"]["text"])
        draft = writes.drafts.get(prep["draft_id"])
        result = writes.post_draft(r.client, draft)
        ok = result.get("posted")
        r.results.append(("post_voucher", PASS if ok else FAIL, str(result)))
        print(f"  [{PASS if ok else FAIL}] post_voucher: {result}")

        verify = writes.verify_voucher(r.client, today, today,
                                       voucher_type="Journal", amount=args.amount,
                                       company=args.company)
        vok = verify.get("verified")
        r.results.append(("verify_voucher", PASS if vok else FAIL, str(verify)))
        print(f"  [{PASS if vok else FAIL}] verify_voucher: matched {verify.get('match_count')}")
        print("\n  Now confirm manually in Tally: Gateway > Display More Reports > Day Book.")
    except (writes.WriteError, TallyConnectionError, TallyResponseError) as exc:
        r.results.append(("write_loop", FAIL, str(exc)))
        print(f"  [{FAIL}] write loop: {exc}")


def _raise(msg: str):
    raise AssertionError(msg)


def main() -> int:
    p = argparse.ArgumentParser(description="Live Tally end-to-end test harness.")
    p.add_argument("--from", dest="from_date", default=f"{date.today().year}-04-01")
    p.add_argument("--to", dest="to_date", default=date.today().isoformat())
    p.add_argument("--write", action="store_true", help="also run the write loop")
    p.add_argument("--company", default=None, help="target company for the write loop")
    p.add_argument("--debit-ledger", default="Office Rent")
    p.add_argument("--credit-ledger", default="Cash")
    p.add_argument("--amount", type=float, default=100.0)
    args = p.parse_args()

    print(f"Tally endpoint: {config.base_url}")
    r = Runner()
    run_reads(r, args.from_date, args.to_date)

    if args.write:
        if not config.allow_writes:
            print("\nWrite loop skipped: set TALLY_ALLOW_WRITES=true to enable.")
        else:
            run_write(r, args)

    return r.report()


if __name__ == "__main__":
    raise SystemExit(main())
