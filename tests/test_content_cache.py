import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import content_cache  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    return content_cache.connect(tmp_path / "test_cache.sqlite")


def test_get_returns_none_for_unknown_title(conn):
    assert content_cache.get(conn, "Never Heard Of It") is None


def test_upsert_csm_rating_then_get_round_trips(conn):
    content_cache.upsert_maturity_rating(
        conn, "Bluey", "TV-Y", ["mild_conflict"], source="csm", fetched_at="2026-08-05T00:00:00Z"
    )
    row = content_cache.get(conn, "bluey")  # case-insensitive lookup
    assert row["maturity_rating"] == "TV-Y"
    assert row["themes"] == ["mild_conflict"]
    assert row["rating_source"] == "csm"
    assert row["rating_rationale"] is None
    assert row["pacing_score"] is None


def test_upsert_llm_inferred_rating_requires_rationale(conn):
    with pytest.raises(ValueError, match="rationale"):
        content_cache.upsert_maturity_rating(
            conn, "Guessed Show", "TV-Y7", [], source="llm_inferred", fetched_at="t1", rationale=""
        )


def test_upsert_llm_inferred_rating_with_rationale_round_trips(conn):
    content_cache.upsert_maturity_rating(
        conn, "Guessed Show", "TV-Y7", ["mild_peril"], source="llm_inferred",
        fetched_at="t1", rationale="synopsis mentions mild peril, Wikipedia summary genre = adventure",
    )
    row = content_cache.get(conn, "Guessed Show")
    assert row["rating_source"] == "llm_inferred"
    assert "mild peril" in row["rating_rationale"]


def test_upsert_maturity_rating_rejects_unknown_source(conn):
    with pytest.raises(ValueError, match="rating_source"):
        content_cache.upsert_maturity_rating(
            conn, "Show", "TV-Y", [], source="made_up_source", fetched_at="t1"
        )


def test_upsert_pacing_score_then_get_round_trips(conn):
    content_cache.upsert_pacing_score(conn, "Bluey", 2, "slow scenes, calm music", scored_at="2026-08-05T00:00:00Z")
    row = content_cache.get(conn, "Bluey")
    assert row["pacing_score"] == 2
    assert row["pacing_rationale"] == "slow scenes, calm music"


def test_upsert_pacing_score_rejects_out_of_range(conn):
    with pytest.raises(ValueError):
        content_cache.upsert_pacing_score(conn, "Bad Show", 11, "invalid", scored_at="now")


def test_rating_and_pacing_upserts_on_same_title_both_persist(conn):
    content_cache.upsert_maturity_rating(conn, "Bluey", "TV-Y", [], source="csm", fetched_at="t1")
    content_cache.upsert_pacing_score(conn, "Bluey", 2, "calm", scored_at="t2")
    row = content_cache.get(conn, "Bluey")
    assert row["maturity_rating"] == "TV-Y"
    assert row["pacing_score"] == 2


def test_titles_missing_maturity_rating(conn):
    content_cache.upsert_maturity_rating(conn, "Bluey", "TV-Y", [], source="csm", fetched_at="t1")
    missing = content_cache.titles_missing_maturity_rating(conn, ["Bluey", "New Show"])
    assert missing == ["New Show"]


def test_titles_missing_pacing_score(conn):
    content_cache.upsert_pacing_score(conn, "Bluey", 2, "calm", scored_at="t1")
    missing = content_cache.titles_missing_pacing_score(conn, ["Bluey", "New Show"])
    assert missing == ["New Show"]
