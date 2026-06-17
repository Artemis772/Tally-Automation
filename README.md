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
- **Phase 2 — writes (implemented but disabled by default):** create ledgers and
  vouchers. Guarded by `TALLY_ALLOW_WRITES` **and** a per-call dry-run. See
  [docs/SETUP.md](docs/SETUP.md#enabling-writes-phase-2).

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
Tally** (Gateway of Tally → company → Backup). Every write tool defaults to a
dry run that returns the exact XML it *would* send so you can review it first.
