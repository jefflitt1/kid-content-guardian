#!/usr/bin/env python3
"""
Pacing/stimulation score cache for Kid Content Guardian.

Deliberately NOT an LLM API client. No rating API exposes a "how calm is
this show" score (confirmed during market research -- Common Sense Media,
TMDB, and TheTVDB all lack it), so this score is produced by Claude itself,
reading each title's synopsis during the skill's `score` step, and persisted
here. That avoids needing a second API key/credential for a service that
would just be calling an LLM anyway, when the skill is already running
inside one.

Workflow (see SKILL.md): for every title returned by
`titles_needing_pacing_score()`, Claude reads the synopsis (from the CSM
lookup, wikipedia_client.py, or the platform's own description text) and
reasons about pacing --
cut frequency, scene length, sound/music intensity, narrative complexity --
then calls `record_score()` with a 1-10 score and a one-line rationale.
Score 1 = slow, calm, long takes (e.g. Bluey, Mister Rogers). Score 10 =
frenetic, rapid-cut, high-stimulus (e.g. most tie-in game-show-style kids
content).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import content_cache


def titles_needing_pacing_score(conn: sqlite3.Connection, candidate_titles: list[str]) -> list[str]:
    return content_cache.titles_missing_pacing_score(conn, candidate_titles)


def record_score(conn: sqlite3.Connection, title: str, score: int, rationale: str) -> None:
    if not 1 <= score <= 10:
        raise ValueError(f"pacing score must be 1-10, got {score}")
    if not rationale.strip():
        raise ValueError("rationale is required -- a bare number isn't reviewable by a parent")
    content_cache.upsert_pacing_score(
        conn, title, score, rationale,
        scored_at=datetime.now(timezone.utc).isoformat(),
    )


def get_score(conn: sqlite3.Connection, title: str) -> dict | None:
    cached = content_cache.get(conn, title)
    if cached is None or cached["pacing_score"] is None:
        return None
    return {
        "pacing_score": cached["pacing_score"],
        "rationale": cached["pacing_rationale"],
        "scored_at": cached["pacing_scored_at"],
    }
