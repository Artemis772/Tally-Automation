# Test Plan

How every part of the Tally MCP server is verified. The automated suite needs
**no live Tally** — a mock HTTP gateway stands in — so it runs in CI and on any
machine. A separate live harness covers the one thing only your machine can do:
talk to real Tally.

## Running

```bash
pip install -e ".[dev]"
pytest                      # full suite + coverage gate (fails under 95%)
pytest -o addopts="" -q     # quick run without the coverage gate
```

Live, on the Tally machine:

```bash
python scripts/smoke_test.py                     # connectivity sanity
python scripts/e2e_test.py                        # every read tool, PASS/FAIL table
python scripts/e2e_test.py --write --company "ZZ Test Co" \
    --debit-ledger "Office Rent" --credit-ledger "Cash" --amount 100
```

## Test infrastructure

| Piece | Where | Purpose |
|-------|-------|---------|
| Mock Tally gateway | `tests/mock_tally.py` | Real HTTP server that mimics Tally; routes by request body; can inject delays (timeout/retry) and HTTP 500. |
| Fixtures | `tests/fixtures/*.xml` | Captured Tally responses incl. dirty XML, errors, import results. |
| Fakes / fixtures | `tests/conftest.py` | `FakeTallyClient` (unit), `mock_tally` + `mock_client` (integration). |

## Coverage matrix

| Area / aspect | Test(s) |
|---------------|---------|
| **Config** env parsing, bool/int, defaults, lock | `test_config.py` |
| **Draft store** put/get/pop, TTL, uniqueness | `test_drafts.py` |
| **XML build** report/collection/import envelopes, dates, escaping, filters | `test_xml_builder.py`, `test_coverage_edges.py` |
| **XML parse** sanitize (control chars, char-refs, `&`), decode (latin-1/utf-16), amounts, import counters, errors | `test_xml_parser.py`, `test_coverage_edges.py` |
| **HTTP client** post/request/ping, LINEERROR, retry-then-success, connection error, HTTP 500, dirty bytes over the wire | `test_client.py`, `test_coverage_edges.py` |
| **Reports (unit, fakes)** ledgers, trial balance, day book, statement, bills | `test_reports.py` |
| **Reports (integration, real client+mock)** every read function end-to-end | `test_integration_reports.py` |
| **Report parsing** P&L / Balance Sheet row flattener | `test_reports_parsing.py` |
| **Writes logic** guards (disabled, company lock), validation (type/balance/entries), prepare, post (success + Tally error), verify | `test_writes.py`, `test_coverage_edges.py` |
| **Elicitation flow** accept / decline / cancel / unsupported / confirm-bypass / expired draft / draft consumed / connection error | `test_server_elicitation.py` |
| **MCP protocol** list_tools (schema, `ctx` hidden), every read tool, error envelope, prepare→post (confirm + elicitation accept/decline), create_ledger dry-run/confirm, verify | `test_server_tools.py` |
| **Smoke script** success vs unreachable | `test_smoke_script.py` |

## Manual Tally-UI checklist (after a `--write` run)

1. `Gateway of Tally → Display More Reports → Day Book` shows the test voucher
   with the expected date, type, ledgers, and amounts.
2. The two ledgers' balances moved by the expected amount.
3. `Tally.imp` (Tally application folder) logged the import with no errors.
4. The write was on the **test company** only — confirm the company name.
5. Delete the test company (or its vouchers) when done.

## CI

`.github/workflows/tests.yml` runs the full suite + coverage gate on Python
3.10–3.12 for every push and pull request.
