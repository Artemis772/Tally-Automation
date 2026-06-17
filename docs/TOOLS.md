# Tool Reference

All tools accept an optional `company` argument; when omitted they use
`TALLY_COMPANY` from your config, or Tally's currently active company. Dates are
`YYYY-MM-DD`.

## Read-only tools (Phase 1)

| Tool | Arguments | Returns |
|------|-----------|---------|
| `tally_health` | – | Connectivity check + open companies |
| `list_companies` | – | Companies loaded in Tally with financial-year range |
| `list_groups` | `company?` | Account groups (chart of accounts) |
| `list_ledgers` | `group?`, `company?` | Ledgers with opening/closing balances |
| `get_ledger_balance` | `ledger`, `company?` | Closing balance for one ledger |
| `trial_balance` | `company?` | Ledger-level trial balance with debit/credit totals |
| `profit_and_loss` | `from_date`, `to_date`, `company?` | P&L rows (best-effort) |
| `balance_sheet` | `as_on`, `company?` | Balance sheet rows (best-effort) |
| `day_book` | `from_date`, `to_date`, `company?` | All vouchers in the range |
| `ledger_statement` | `ledger`, `from_date`, `to_date`, `company?` | Vouchers for a party ledger |
| `bills_outstanding` | `kind` ("receivable"\|"payable"), `company?` | Outstanding bills |
| `list_stock_items` | `company?` | Stock items with closing qty/value |

### Notes

- **`trial_balance`** is derived from ledger closing balances (positive =
  debit, negative = credit). It is robust and version-independent.
- **`profit_and_loss` / `balance_sheet`** parse Tally's built-in grouped report
  output, whose XML shape can vary slightly by Tally version. If the rows look
  off on your setup, the parser in `src/tally_mcp/reports.py` (`_report_rows`)
  is the single place to adjust.
- **`ledger_statement`** matches on the voucher's *party ledger* — ideal for
  party-centric flows (a customer/supplier's transactions).

## Write tools (Phase 2 — disabled by default)

These require `TALLY_ALLOW_WRITES=true` **and** `dry_run=false, confirm=true` to
actually post. By default they return an `xml_preview` without sending anything.
See [SETUP.md](SETUP.md#enabling-writes-phase-2).

| Tool | Arguments | Notes |
|------|-----------|-------|
| `create_ledger` | `name`, `parent_group`, `opening_balance?`, `company?`, `dry_run=true`, `confirm=false` | Creates a ledger master |
| `create_voucher` | `voucher_type`, `voucher_date`, `entries`, `narration?`, `party_ledger?`, `company?`, `dry_run=true`, `confirm=false` | Creates an accounting voucher; entries must net to zero |

`entries` is a list of `{"ledger": str, "amount": float}` where a **positive
amount is a debit** and a **negative amount is a credit**.

## Example prompts

- "Run a Tally health check and tell me which companies are open."
- "What's the closing balance of my Cash ledger?"
- "Show me the trial balance and tell me if it's balanced."
- "List all sundry debtors and their balances."
- "What are my outstanding receivables right now?"
- "Show the day book for 2026-04-01 to 2026-04-30."
- "Show ABC Traders' statement for last month."
- "Draft a payment voucher of 20000 from Cash to Office Rent dated today
  (dry run first), then post it once I confirm."
