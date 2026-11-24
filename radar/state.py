"""Small JSON state: last seen post per query, posts already handled, monthly X spend."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text()) if path.exists() else {}
        self.since_ids: dict[str, str] = data.get("since_ids", {})
        self.seen: list[str] = data.get("seen", [])
        self.usage: dict[str, int] = data.get("usage", {})

    @staticmethod
    def query_key(query: str) -> str:
        return hashlib.sha1(query.encode()).hexdigest()[:12]

    @staticmethod
    def month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def posts_read_this_month(self) -> int:
        return self.usage.get(self.month(), 0)

    def add_reads(self, n: int) -> None:
        m = self.month()
        self.usage[m] = self.usage.get(m, 0) + n

    def is_seen(self, post_id: str) -> bool:
        return post_id in self._seen_set()

    def mark_seen(self, post_ids) -> None:
        s = self._seen_set()
        for pid in post_ids:
            if pid not in s:
                self.seen.append(pid)
                s.add(pid)
        self.seen = self.seen[-5000:]

    def _seen_set(self) -> set[str]:
        return set(self.seen)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"since_ids": self.since_ids, "seen": self.seen, "usage": self.usage}, indent=1))
