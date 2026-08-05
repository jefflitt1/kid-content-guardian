#!/usr/bin/env python3
"""
Wikipedia client -- replaces an earlier TMDB-based client that was removed
after reading TMDB's actual API Terms of Use: Section 1.C flatly restricts
using the TMDB API/Content "in connection with... a machine learning (ML) or
artificial intelligence (AI) based Application", independent of personal vs.
commercial use, and Section 2.A separately lists LLM/chatbot use as a
commercial-use trigger requiring a paid agreement. This client's whole job is
to feed a synopsis to Claude's reasoning (llm_rating_scorer.py) -- exactly
the restricted combination -- so TMDB was not a compliant source for that.

Wikipedia is: CC0 for structured data, CC BY-SA for article text
(https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content), free, no
API key, and Wikimedia explicitly frames their data as usable for AI/LLM
grounding (see Wikimedia Enterprise's own positioning) -- no restriction
comparable to TMDB's was found. Attribution requirement under CC BY-SA is
satisfied by linking back to the source article, which this client always
returns alongside the extract.

Per Wikimedia's API etiquette (https://meta.wikimedia.org/wiki/User-Agent_policy),
requests must carry a descriptive User-Agent identifying the application and
a contact point -- generic/empty User-Agents can be rate-limited or blocked.
The default below identifies this project; if you fork or redistribute this,
update WIKIPEDIA_USER_AGENT to point at your own contact info.

NOT an authoritative maturity-rating source -- Wikipedia articles don't carry
CSM-style age ratings. This only supplies a synopsis (the `extract` field)
for Claude to reason over in the same way the TMDB-based version did; the
rating/theme judgment itself is still Claude's own inference
(llm_rating_scorer.py), recorded as `rating_source="llm_inferred"`.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Optional

WIKIPEDIA_API_BASE = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIPEDIA_USER_AGENT = (
    "KidContentGuardian/0.1 (https://github.com/jefflitt1/kid-content-guardian; "
    "no-contact-set-update-me) requests"
)

WIKIPEDIA_RAW_SCHEMA = """
CREATE TABLE IF NOT EXISTS wikipedia_raw (
    title_key TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    page_title TEXT,           -- resolved Wikipedia article title, NULL if no match found
    extract TEXT,               -- CC BY-SA article summary text
    description TEXT,           -- short one-line description, if present
    source_url TEXT,            -- attribution link, required under CC BY-SA
    fetched_at TEXT NOT NULL
);
"""


def _normalize(title: str) -> str:
    return title.strip().lower()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(WIKIPEDIA_RAW_SCHEMA)
    conn.commit()


def get_cached(conn: sqlite3.Connection, title: str) -> Optional[dict]:
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT page_title, extract, description, source_url, fetched_at "
        "FROM wikipedia_raw WHERE title_key = ?",
        (_normalize(title),),
    ).fetchone()
    if row is None:
        return None
    page_title, extract, description, source_url, fetched_at = row
    return {
        "page_title": page_title,
        "extract": extract,
        "description": description,
        "source_url": source_url,
        "fetched_at": fetched_at,
    }


def _store(conn: sqlite3.Connection, title: str, page_title: Optional[str], extract: Optional[str],
           description: Optional[str], source_url: Optional[str], fetched_at: str) -> None:
    _ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO wikipedia_raw (title_key, display_name, page_title, extract, description, source_url, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(title_key) DO UPDATE SET
            display_name = excluded.display_name,
            page_title = excluded.page_title,
            extract = excluded.extract,
            description = excluded.description,
            source_url = excluded.source_url,
            fetched_at = excluded.fetched_at
        """,
        (_normalize(title), title, page_title, extract, description, source_url, fetched_at),
    )
    conn.commit()


class WikipediaClient:
    def __init__(self, conn: sqlite3.Connection,
                 search_fetch: Optional[Callable[[str], dict]] = None,
                 summary_fetch: Optional[Callable[[str], dict]] = None):
        self.conn = conn
        self._search_fetch = search_fetch or self._http_search
        self._summary_fetch = summary_fetch or self._http_summary

    def _http_search(self, title: str) -> dict:
        import requests  # lazy import so caching logic is testable without the dependency

        resp = requests.get(
            WIKIPEDIA_API_BASE,
            params={"action": "query", "list": "search", "srsearch": title, "srlimit": 1, "format": "json"},
            headers={"User-Agent": WIKIPEDIA_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _http_summary(self, page_title: str) -> dict:
        import requests

        resp = requests.get(
            f"{WIKIPEDIA_SUMMARY_BASE}/{page_title}",
            headers={"User-Agent": WIKIPEDIA_USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def lookup(self, title: str) -> Optional[dict]:
        from datetime import datetime, timezone

        cached = get_cached(self.conn, title)
        if cached is not None:
            return cached

        search_payload = self._search_fetch(title)
        results = search_payload.get("query", {}).get("search", [])
        fetched_at = datetime.now(timezone.utc).isoformat()

        if not results:
            _store(self.conn, title, None, None, None, None, fetched_at)
            return get_cached(self.conn, title)

        page_title = results[0]["title"]
        summary = self._summary_fetch(page_title)
        extract = summary.get("extract")
        description = summary.get("description")
        source_url = summary.get("content_urls", {}).get("desktop", {}).get("page")

        _store(self.conn, title, page_title, extract, description, source_url, fetched_at)
        return get_cached(self.conn, title)
