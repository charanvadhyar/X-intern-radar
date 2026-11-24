"""Thin client for the X API v2 recent-search endpoint."""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


@dataclass
class Post:
    id: str
    text: str
    created_at: str
    author_username: str
    author_name: str = ""
    author_bio: str = ""
    urls: list[str] = field(default_factory=list)

    @property
    def link(self) -> str:
        return f"https://x.com/{self.author_username}/status/{self.id}"


class XClient:
    def __init__(self, bearer_token: str, session: requests.Session | None = None):
        if not bearer_token:
            raise ValueError("X_BEARER_TOKEN is not set")
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = f"Bearer {bearer_token}"

    def search_recent(self, query: str, max_results: int = 20, since_id: str | None = None) -> tuple[list[Post], str | None]:
        """Return (posts, newest_id). Only posts newer than since_id are billed and returned."""
        params = {
            "query": query,
            "max_results": max(10, min(100, max_results)),
            "tweet.fields": "created_at,author_id,entities",
            "expansions": "author_id",
            "user.fields": "username,name,description",
        }
        if since_id:
            params["since_id"] = since_id
        resp = self.session.get(SEARCH_URL, params=params, timeout=30)
        if resp.status_code == 429:
            raise RuntimeError("X API rate limit hit; try again later")
        resp.raise_for_status()
        return parse_search_response(resp.json())


def parse_search_response(payload: dict) -> tuple[list[Post], str | None]:
    users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
    posts = []
    for t in payload.get("data", []) or []:
        u = users.get(t.get("author_id"), {})
        urls = [e.get("expanded_url") or e.get("url") for e in t.get("entities", {}).get("urls", [])]
        posts.append(
            Post(
                id=t["id"],
                text=t.get("text", ""),
                created_at=t.get("created_at", ""),
                author_username=u.get("username", "i"),
                author_name=u.get("name", ""),
                author_bio=u.get("description", ""),
                urls=[x for x in urls if x],
            )
        )
    return posts, payload.get("meta", {}).get("newest_id")
