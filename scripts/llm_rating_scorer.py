#!/usr/bin/env python3
"""
LLM-inferred maturity rating + themes -- the fallback path when no Common
Sense Media partnership key is configured (see csm_client.py and the README
for why CSM access isn't self-serve).

Same pattern as pacing_scorer.py: this is not an LLM API client. Claude
itself (running the skill) reads a title's synopsis (wikipedia_client.py --
TMDB was considered and rejected here; its API Terms of Use flatly restrict
using TMDB data "in connection with... a machine learning (ML) or artificial
intelligence (AI) based Application", which is exactly this use, regardless
of personal/commercial status) plus whatever it already knows, reasons about
the likely US maturity rating and any Common-Sense-Media-style theme tags
(violence, scary_imagery, sexual_content, etc.), and calls `record_rating()`
with the result and a rationale.

This is explicitly lower-confidence than a real CSM review -- every rating
recorded here is tagged `rating_source="llm_inferred"` in the cache
(content_cache.py enforces a rationale is present) and the diff report
surfaces that distinction to the parent rather than presenting it with the
same confidence as an independent reviewer's rating.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import content_cache
from rubric_engine import rating_rank, validate_themes  # re-used to reject values outside the known vocabularies


def titles_needing_rating(conn: sqlite3.Connection, candidate_titles: list[str]) -> list[str]:
    return content_cache.titles_missing_maturity_rating(conn, candidate_titles)


def record_rating(conn: sqlite3.Connection, title: str, maturity_rating: str, themes: list[str],
                   rationale: str) -> None:
    rating_rank(maturity_rating)  # raises UnknownRatingError on anything outside RATING_RANK -- don't invent a scale
    validate_themes(themes)  # raises UnknownThemeError on any tag outside THEME_TAGS -- same reasoning
    content_cache.upsert_maturity_rating(
        conn, title, maturity_rating, themes,
        source="llm_inferred", rationale=rationale,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def get_rating(conn: sqlite3.Connection, title: str) -> dict | None:
    cached = content_cache.get(conn, title)
    if cached is None or cached["maturity_rating"] is None:
        return None
    return {
        "maturity_rating": cached["maturity_rating"],
        "themes": cached["themes"],
        "source": cached["rating_source"],
        "rationale": cached["rating_rationale"],
    }
