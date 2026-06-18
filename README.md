# Tally-Automation

Connect **Claude** directly to your **TallyPrime** accounting data via a custom
**MCP (Model Context Protocol) server**. Ask Claude things like *"What's my cash
balance?"*, *"Show the trial balance"*, or *"List outstanding receivables"* and it
queries Tally live.

It talks to TallyPrime's built-in **XML-over-HTTP gateway** (default
`http://localhost:9000`) — no third-party cloud service, your data stays on your
machine.

```
Claude Desktop / Claude Code
        │  MCP (stdio)
        ▼
  Tally MCP Server (this repo, Python — runs on your machine)
        │  HTTP POST text/xml
        ▼
  TallyPrime XML Gateway  http://localhost:9000
```

> **Important:** This server must run on the machine where Tally is reachable
> (the Tally PC itself, or a PC on the same LAN). It connects to **Claude
> Desktop** or **local Claude Code** — not to Claude on the web, which cannot
> reach your local Tally.

## Status

- **Phase 1 — read-only (implemented):** companies, groups, ledgers & balances,
  trial balance, P&L, balance sheet, day book, ledger statement, outstanding
  bills, stock items.
- **Phase 2 — writes (implemented, disabled by default):** accounting vouchers
  (Payment, Receipt, Contra, Journal) and ledgers, via a **prepare → confirm →
  post → verify** flow. `post_voucher` shows the exact entries in a
  **confirmation dialog** (MCP elicitation, supported by Claude Code) before
  anything is written. Guarded by `TALLY_ALLOW_WRITES` and an optional
  `TALLY_WRITE_COMPANY` lock. See
  [docs/VERIFYING_WRITES.md](docs/VERIFYING_WRITES.md).

## Quick start

1. Install Python 3.10+ and this package's dependencies:
   ```bash
   pip install -e .
   ```
2. In TallyPrime, enable the XML/HTTP gateway: **F1 (Help) → Settings →
   Connectivity → Client/Server configuration → set TallyPrime as *Server*,
   Port `9000`**. (Already done if you can open `http://localhost:9000` in a
   browser and see a Tally banner.)
3. Copy `.env.example` to `.env` and set `TALLY_COMPANY` to your company name.
4. Verify the connection:
   ```bash
   python scripts/smoke_test.py
   ```
5. Wire it into Claude — see [docs/SETUP.md](docs/SETUP.md).

## Tools

See [docs/TOOLS.md](docs/TOOLS.md) for the full tool reference and example
prompts.

## Tests

Offline unit tests (no Tally required) cover XML building, the defensive
response parser, and the report logic against captured fixtures:

```bash
pip install -e ".[dev]"
pytest
```

## Safety

Writes are **off by default**. Before enabling them, **back up your company in
Tally** (Gateway of Tally → company → Backup). Vouchers are previewed and then
confirmed in a dialog before posting, and writes can be **locked to a single
test company** via `TALLY_WRITE_COMPANY`. See
[docs/VERIFYING_WRITES.md](docs/VERIFYING_WRITES.md).
