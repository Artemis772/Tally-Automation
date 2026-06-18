# Verifying Writes

Accounting writes are irreversible, so Phase 2 is built around **confirming
correctness at every step**. There are five layers, from "no Tally needed" to
"eyes on Tally".

## The write flow

```
prepare_voucher  ──►  (review preview)  ──►  post_voucher  ──►  verify_voucher
   stage only          GUI / text table     confirm + post     independent read-back
```

Nothing is written until you approve `post_voucher`.

## Layer 1 — Preview before anything posts

`prepare_voucher` validates the voucher (balanced, supported type, company lock)
and returns a **preview table** of exactly what will be written — ledger, debit,
credit, totals, and the target company — plus a `draft_id`. No data is sent.

```
**Journal voucher** — 2026-04-03
Company: ZZ Test Co

| Ledger      | Debit    | Credit   |
| ----------- | -------- | -------- |
| Office Rent | 20000.00 |          |
| Cash        |          | 20000.00 |
| Total       | 20000.00 | 20000.00 |
```

## Layer 2 — Confirmation dialog at post time

`post_voucher(draft_id)` shows the entries again in a **confirmation dialog**
(MCP *elicitation*, supported by Claude Code) and only posts if you accept. If
your client doesn't support the dialog, call `post_voucher(draft_id, confirm=true)`
explicitly.

## Layer 3 — Tally's own import counters

On a successful post, `post_voucher` returns Tally's acknowledgement parsed into
counters:

```json
{ "posted": true, "created": 1, "altered": 0, "errors": 0, "last_vch_id": 4521 }
```

A failure returns `posted: false`, `errors: 1`, and Tally's verbatim message in
`lineerror` (e.g. *"Ledger 'Office Rent' does not exist."*). These counters —
not the HTTP status — are Tally's source of truth, because Tally returns errors
with HTTP 200.

## Layer 4 — Independent read-back (`verify_voucher`)

`verify_voucher` re-queries Tally's **day book** for the date range and confirms
a matching voucher exists (by type / party ledger / absolute amount). This is
proof from Tally's own stored data, separate from the write call:

```json
{ "verified": true, "match_count": 1, "matches": [ { "voucher_type": "Journal", "amount": -20000.0, ... } ] }
```

## Layer 5 — The safe real-world check (test company)

Before trusting writes against live books:

1. In Tally, create a throwaway company, e.g. **"ZZ Test Co"**.
2. Set `TALLY_WRITE_COMPANY=ZZ Test Co`. Now every write **refuses** any other
   company — you cannot accidentally touch real data.
3. Post a voucher via Claude, then **eyeball it in the Tally UI**:
   *Gateway of Tally → Display More Reports → Day Book*.
4. Check the `Tally.imp` log (in Tally's application folder) for the import line.
5. When satisfied, delete the test company and point `TALLY_WRITE_COMPANY` at
   your real company (or clear it).

## Offline checks (no Tally, run anywhere)

The test suite proves the mechanics without a live Tally:

```bash
pytest
```

- `tests/test_writes.py` — guards (writes disabled, company lock), validation
  (type, balance, entries), prepare→post, success vs Tally-error handling, and
  `verify_voucher` matching.
- `tests/test_xml_parser.py::test_parse_import_response_*` — counters parsed from
  `import_success.xml` / `import_error.xml`.
- `tests/test_xml_builder.py` — each voucher import envelope is well-formed and
  carries the right type/date/entries.

## Quick end-to-end on your machine

```text
TALLY_ALLOW_WRITES=true
TALLY_WRITE_COMPANY=ZZ Test Co
```

1. *"Prepare a Journal: debit Office Rent 20000, credit Cash 20000, today."*
2. Review the preview table.
3. *"Post it."* → approve the dialog → `created=1`.
4. *"Verify that voucher."* → `verified: true`. Cross-check in Tally's Day Book.
