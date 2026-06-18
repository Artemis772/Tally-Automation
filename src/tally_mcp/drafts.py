"""In-memory store for pending write drafts (prepare -> post flow).

A draft holds a validated voucher spec plus its computed preview. It is created
by ``prepare_voucher`` and consumed by ``post_voucher``, so a write always
requires a prior, explicit preview step. Drafts expire after a short TTL.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TTL_SECONDS = 600  # 10 minutes


@dataclass
class _Entry:
    created_at: float
    payload: dict[str, Any]


@dataclass
class DraftStore:
    ttl: float = DEFAULT_TTL_SECONDS
    _items: dict[str, _Entry] = field(default_factory=dict)

    def _purge(self) -> None:
        cutoff = time.time() - self.ttl
        for key in [k for k, v in self._items.items() if v.created_at < cutoff]:
            del self._items[key]

    def put(self, payload: dict[str, Any]) -> str:
        self._purge()
        draft_id = uuid.uuid4().hex[:12]
        self._items[draft_id] = _Entry(created_at=time.time(), payload=payload)
        return draft_id

    def get(self, draft_id: str) -> dict[str, Any] | None:
        self._purge()
        entry = self._items.get(draft_id)
        return entry.payload if entry else None

    def pop(self, draft_id: str) -> dict[str, Any] | None:
        self._purge()
        entry = self._items.pop(draft_id, None)
        return entry.payload if entry else None


# Process-wide store shared by the server tools.
drafts = DraftStore()
