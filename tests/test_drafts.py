"""Tests for the in-memory draft store (prepare -> post handoff)."""

from __future__ import annotations

import time

from tally_mcp.drafts import DraftStore


def test_put_get_returns_payload():
    store = DraftStore()
    draft_id = store.put({"x": 1})
    assert store.get(draft_id) == {"x": 1}
    # get does not consume.
    assert store.get(draft_id) == {"x": 1}


def test_pop_consumes():
    store = DraftStore()
    draft_id = store.put({"x": 1})
    assert store.pop(draft_id) == {"x": 1}
    assert store.get(draft_id) is None
    assert store.pop(draft_id) is None


def test_unknown_id_returns_none():
    store = DraftStore()
    assert store.get("nope") is None
    assert store.pop("nope") is None


def test_ttl_expiry_purges(monkeypatch):
    store = DraftStore(ttl=0.05)
    draft_id = store.put({"x": 1})
    assert store.get(draft_id) is not None
    time.sleep(0.06)
    assert store.get(draft_id) is None


def test_ids_are_unique():
    store = DraftStore()
    ids = {store.put({"i": i}) for i in range(50)}
    assert len(ids) == 50
