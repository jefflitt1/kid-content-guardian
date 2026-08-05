#!/usr/bin/env python3
"""
Common Sense Media API client: cache-first, rate-limit-aware.

CSM's public API is capped at 5 requests/minute (confirmed via their
developer docs: https://www.commonsensemedia.org/developers/api-overview).
That's fine for one household doing incremental lookups, but it's the hard
constraint that makes the local SQLite cache (content_cache.py) mandatory
rather than optional -- every title is looked up once, ever, across however
many times you re-run a sync.

Getting an API key: https://www.commonsensemedia.org/developers/developer-center
Set it as the COMMONSENSE_API_KEY environment variable before running a sync
that needs to fetch titles not already in the cache.

NOTE ON THE HTTP CONTRACT: CSM's exact endpoint path and response JSON shape
for a title lookup were not verifiable without a live API key at the time
this was written (their docs describe methods like `review/browse` behind
auth). `_parse_response()` below is the single place that translates their
JSON into our (maturity_rating, themes) shape -- confirm the real response
schema against your own API key and update only that function; the rest of
this module (caching, rate limiting) doesn't need to change.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import content_cache

CSM_API_BASE = "https://api.commonsensemedia.org"
MAX_REQUESTS_PER_MINUTE = 5


class MissingAPIKeyError(RuntimeError):
    def __init__(self):
        super().__init__(
            "COMMONSENSE_API_KEY is not set. Get a key at "
            "https://www.commonsensemedia.org/developers/developer-center "
            "and export it before running a sync that needs new titles."
        )


class RateLimiter:
    """Simple token-bucket limiter, blocking (sleeps) rather than dropping requests."""

    def __init__(self, max_per_minute: int = MAX_REQUESTS_PER_MINUTE, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.max_per_minute = max_per_minute
        self._clock = clock
        self._sleep = sleep
        self._request_times: list[float] = []

    def acquire(self) -> None:
        now = self._clock()
        window_start = now - 60.0
        self._request_times = [t for t in self._request_times if t > window_start]
        if len(self._request_times) >= self.max_per_minute:
            wait_for = 60.0 - (now - self._request_times[0])
            if wait_for > 0:
                self._sleep(wait_for)
            now = self._clock()
            window_start = now - 60.0
            self._request_times = [t for t in self._request_times if t > window_start]
        self._request_times.append(now)


def _parse_response(payload: dict) -> tuple[str, list[str]]:
    """Translate a CSM API response into (maturity_rating, themes).

    Placeholder mapping pending confirmation against a live API key -- see
    module docstring. Raises KeyError loudly on an unexpected shape rather
    than guessing, so a schema drift is caught instead of silently cached
    as wrong data.
    """
    maturity_rating = payload["age_rating"]
    themes = payload.get("content_themes", [])
    return maturity_rating, themes


class CSMClient:
    def __init__(self, conn: sqlite3.Connection, api_key: Optional[str] = None,
                 fetch: Optional[Callable[[str, str], dict]] = None,
                 rate_limiter: Optional[RateLimiter] = None):
        self.conn = conn
        self.api_key = api_key if api_key is not None else os.environ.get("COMMONSENSE_API_KEY")
        self._fetch = fetch or self._http_fetch
        self.rate_limiter = rate_limiter or RateLimiter()

    def _http_fetch(self, title: str, api_key: str) -> dict:
        import requests  # imported lazily so the cache/rate-limit logic is testable without the dependency

        resp = requests.get(
            f"{CSM_API_BASE}/v2/review/browse",
            params={"title": title, "media_type": "tv,movie"},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def lookup(self, title: str) -> Optional[dict]:
        """Return {maturity_rating, themes} for a title, fetching + caching on a miss.
        Returns None if CSM has no review for this title (not an error)."""
        cached = content_cache.get(self.conn, title)
        if cached is not None and cached["maturity_rating"] is not None:
            return {"maturity_rating": cached["maturity_rating"], "themes": cached["themes"]}

        if not self.api_key:
            raise MissingAPIKeyError()

        self.rate_limiter.acquire()
        payload = self._fetch(title, self.api_key)
        if not payload:
            return None

        maturity_rating, themes = _parse_response(payload)
        content_cache.upsert_maturity_rating(
            self.conn, title, maturity_rating, themes, source="csm",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        return {"maturity_rating": maturity_rating, "themes": themes}
