import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import content_cache  # noqa: E402
import llm_rating_scorer  # noqa: E402
from rubric_engine import UnknownRatingError, UnknownThemeError  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    return content_cache.connect(tmp_path / "test_cache.sqlite")


def test_record_rating_then_get_rating_round_trips(conn):
    llm_rating_scorer.record_rating(
        conn, "Guessed Show", "TV-Y7", ["scary_imagery"],
        rationale="Wikipedia summary mentions a chase scene, genre=adventure",
    )
    result = llm_rating_scorer.get_rating(conn, "Guessed Show")
    assert result["maturity_rating"] == "TV-Y7"
    assert result["source"] == "llm_inferred"
    assert "chase scene" in result["rationale"]


def test_record_rating_rejects_unrecognized_rating_string(conn):
    with pytest.raises(UnknownRatingError):
        llm_rating_scorer.record_rating(conn, "Show", "NOT-A-RATING", [], rationale="guessing")


def test_record_rating_rejects_unrecognized_theme_tag(conn):
    with pytest.raises(UnknownThemeError):
        llm_rating_scorer.record_rating(conn, "Show", "TV-Y7", ["made_up_theme"], rationale="guessing")


def test_get_rating_returns_none_when_unscored(conn):
    assert llm_rating_scorer.get_rating(conn, "Never Scored") is None


def test_titles_needing_rating_excludes_already_scored(conn):
    llm_rating_scorer.record_rating(conn, "Scored Show", "TV-Y", [], rationale="calm synopsis")
    missing = llm_rating_scorer.titles_needing_rating(conn, ["Scored Show", "New Show"])
    assert missing == ["New Show"]
