# Setup Guide

This guide takes you from a fresh checkout to asking Claude about your Tally
data.

## 1. Prerequisites

- **TallyPrime** running on a Windows PC.
- **Python 3.10+** on the same PC (or a PC on the same LAN as Tally).
- **Claude Desktop** (recommended) or **Claude Code** installed locally.

## 2. Enable Tally's XML/HTTP gateway

In TallyPrime:

1. Press **F1 (Help) → Settings → Connectivity**.
2. Open **Client/Server configuration**.
3. Set **TallyPrime is acting as** → **Server**.
4. Set **Port** → **9000** (the default).
5. Accept and keep TallyPrime running with your company open.

**Verify:** open `http://localhost:9000` in a browser on the Tally PC. You should
see a short Tally XML/HTML response (not a connection error).

> Tally ERP 9 (older): the same gateway lives under **F12 → Advanced
> Configuration → set "Tally acts as" = Both/Server, Port 9000**. Everything
> else here is identical.

## 3. Install the server

From the repository root:

```bash
pip install -e .
```

(Use `pip install -e ".[dev]"` if you also want to run the tests.)

## 4. Configure

Copy the example env file and edit it:

```bash
cp .env.example .env
```

Set at least:

- `TALLY_COMPANY` — your company name **exactly** as it appears in Tally. Leave
  blank to use whichever company is currently active in Tally.
- `TALLY_HOST` — `localhost` if the server runs on the Tally PC, otherwise the
  Tally PC's LAN IP.

## 5. Smoke-test the connection (no Claude yet)

```bash
python scripts/smoke_test.py
```

This pings Tally, lists your companies, and prints a short trial balance. If it
fails, re-check step 2 and that the company is open in Tally.

## 6. Connect to Claude Desktop

1. Open Claude Desktop → **Settings → Developer → Edit Config**. This opens
   `claude_desktop_config.json`.
2. Merge in the contents of [`claude_desktop_config.example.json`](../claude_desktop_config.example.json),
   adjusting the Windows paths to your checkout. Example:

   ```json
   {
     "mcpServers": {
       "tally": {
         "command": "python",
         "args": ["-m", "tally_mcp"],
         "cwd": "C:\\Users\\you\\Tally-Automation",
         "env": {
           "PYTHONPATH": "C:\\Users\\you\\Tally-Automation\\src",
           "TALLY_HOST": "localhost",
           "TALLY_PORT": "9000",
           "TALLY_COMPANY": "Your Company Name",
           "TALLY_ALLOW_WRITES": "false"
         }
       }
     }
   }
   ```

   > If you ran `pip install -e .`, you can drop `PYTHONPATH` and use
   > `"command": "tally-mcp", "args": []` instead.

3. **Fully quit and reopen** Claude Desktop.
4. In a new chat, the `tally` tools should appear. Try: *"Run a Tally health
   check."*

## 7. Connect to local Claude Code (alternative)

From the repository root:

```bash
claude mcp add tally -- python -m tally_mcp
```

Set the same environment variables in your shell or `.env` first. Confirm with
`claude mcp list`.

## 8. Try it

Ask Claude:

- "Run a Tally health check."
- "What's my closing cash balance?"
- "Show the trial balance."
- "List outstanding receivables."
- "Show the day book for April 2026."

---

## Enabling writes (Phase 2)

Write tools are **disabled by default**. This iteration supports **accounting
vouchers only** (Payment, Receipt, Contra, Journal) plus `create_ledger`.

**Before enabling, back up your company** in Tally (Gateway of Tally → select
company → **Backup**).

To enable:

1. Set `TALLY_ALLOW_WRITES=true` in `.env` (or the Claude Desktop / Claude Code
   config `env` block) and restart.
2. **Strongly recommended while testing:** set `TALLY_WRITE_COMPANY` to a
   throwaway test company name. Writes will then refuse any other company, so
   you cannot touch real books by accident.

The voucher flow is **prepare → confirm → post → verify**:

1. *"Prepare a Journal: debit Office Rent 20000, credit Cash 20000, today."* →
   `prepare_voucher` returns a preview table + `draft_id`. Nothing is written.
2. *"Post it."* → `post_voucher` shows a **confirmation dialog** with the entries
   (this uses MCP *elicitation*, supported by Claude Code). Approve to post; you
   get back `created=1, voucher_id=N`. (If your client has no dialog support,
   say "post with confirm=true".)
3. *"Verify it."* → `verify_voucher` re-reads Tally's day book and confirms it.

Vouchers must balance (debits/credits net to zero) or the tool refuses before
sending. For the full verification playbook see
[VERIFYING_WRITES.md](VERIFYING_WRITES.md).

## Troubleshooting

- **"Could not reach Tally"** — Tally not running, gateway not enabled, wrong
  host/port, or a firewall blocking port 9000 (allow it for LAN access).
- **"Could not find Company ..."** — `TALLY_COMPANY` must match the Tally
  company name exactly; or leave it blank to use the active company.
- **Empty results** — make sure the right company is open and has data in the
  requested period.
- **Import errors on writes** — check Tally's `Tally.imp` log file (in Tally's
  application folder) for the detailed reason; usually a missing ledger/stock
  item that must exist before the voucher.
