#!/usr/bin/env python3
"""
Local SQLite cache shared by csm_client.py, llm_rating_scorer.py, wikipedia_client.py,
and pacing_scorer.py.

Every title is looked up here first. Nothing outside this module ever hits
Common Sense Media, Wikipedia, or re-derives a rating/pacing score for a title
that's already cached -- that's what keeps this usable within CSM's 5
req/min rate limit (when a partnership key is available) once more than one
household is pulling from it, and what keeps re-syncs fast either way.

Ratings can come from more than one source with different trust levels --
a real Common Sense Media review vs. Claude's own inference from a synopsis
when no CSM key is configured. `rating_source` is never omitted so the diff
report can flag lower-confidence entries instead of presenting every rating
as equally authoritative.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "content_cache.sqlite"

RATING_SOURCES = {"csm", "llm_inferred"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS titles (
    title_key TEXT PRIMARY KEY,      -- normalized (lowercased, trimmed) title name
    display_name TEXT NOT NULL,
    maturity_rating TEXT,
    themes_json TEXT,                -- JSON array of theme strings, or NULL if not fetched
    rating_source TEXT,              -- 'csm' | 'llm_inferred', NULL until a rating is on file
    rating_rationale TEXT,           -- required when rating_source = 'llm_inferred'
    rating_fetched_at TEXT,          -- ISO timestamp, NULL until a rating lookup has run
    pacing_score INTEGER,            -- 1-10, NULL until scored
    pacing_rationale TEXT,
    pacing_scored_at TEXT
);
"""


def _normalize(title: str) -> str:
    return title.strip().lower()


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def get(conn: sqlite3.Connection, title: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT display_name, maturity_rating, themes_json, rating_source, rating_rationale, "
        "rating_fetched_at, pacing_score, pacing_rationale, pacing_scored_at "
        "FROM titles WHERE title_key = ?",
        (_normalize(title),),
    ).fetchone()
    if row is None:
        return None
    (display_name, maturity_rating, themes_json, rating_source, rating_rationale,
     rating_fetched_at, pacing_score, pacing_rationale, pacing_scored_at) = row
    return {
        "display_name": display_name,
        "maturity_rating": maturity_rating,
        "themes": json.loads(themes_json) if themes_json else [],
        "rating_source": rating_source,
        "rating_rationale": rating_rationale,
        "rating_fetched_at": rating_fetched_at,
        "pacing_score": pacing_score,
        "pacing_rationale": pacing_rationale,
        "pacing_scored_at": pacing_scored_at,
    }


def upsert_maturity_rating(conn: sqlite3.Connection, title: str, maturity_rating: str, themes: list[str],
                            source: str, fetched_at: str, rationale: Optional[str] = None) -> None:
    if source not in RATING_SOURCES:
        raise ValueError(f"rating_source must be one of {sorted(RATING_SOURCES)}, got {source!r}")
    if source == "llm_inferred" and not (rationale and rationale.strip()):
        raise ValueError("an llm_inferred rating requires a non-empty rationale a parent can review")
    conn.execute(
        """
        INSERT INTO titles (title_key, display_name, maturity_rating, themes_json, rating_source, rating_rationale, rating_fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(title_key) DO UPDATE SET
            display_name = excluded.display_name,
            maturity_rating = excluded.maturity_rating,
            themes_json = excluded.themes_json,
            rating_source = excluded.rating_source,
            rating_rationale = excluded.rating_rationale,
            rating_fetched_at = excluded.rating_fetched_at
        """,
        (_normalize(title), title, maturity_rating, json.dumps(themes), source, rationale, fetched_at),
    )
    conn.commit()


def upsert_pacing_score(conn: sqlite3.Connection, title: str, score: int, rationale: str, scored_at: str) -> None:
    if not 1 <= score <= 10:
        raise ValueError(f"pacing score must be 1-10, got {score}")
    conn.execute(
        """
        INSERT INTO titles (title_key, display_name, pacing_score, pacing_rationale, pacing_scored_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(title_key) DO UPDATE SET
            display_name = excluded.display_name,
            pacing_score = excluded.pacing_score,
            pacing_rationale = excluded.pacing_rationale,
            pacing_scored_at = excluded.pacing_scored_at
        """,
        (_normalize(title), title, score, rationale, scored_at),
    )
    conn.commit()


def titles_missing_maturity_rating(conn: sqlite3.Connection, candidate_titles: list[str]) -> list[str]:
    known = {
        _normalize(row[0])
        for row in conn.execute("SELECT title_key FROM titles WHERE maturity_rating IS NOT NULL")
    }
    return [t for t in candidate_titles if _normalize(t) not in known]


def titles_missing_pacing_score(conn: sqlite3.Connection, candidate_titles: list[str]) -> list[str]:
    known = {
        _normalize(row[0])
        for row in conn.execute("SELECT title_key FROM titles WHERE pacing_score IS NOT NULL")
    }
    return [t for t in candidate_titles if _normalize(t) not in known]
