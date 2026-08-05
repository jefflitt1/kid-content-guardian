import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rubric_engine import (  # noqa: E402
    Title,
    UnknownRatingError,
    UnknownThemeError,
    evaluate_catalog,
    evaluate_title_for_kid,
    load_family_profile,
    rating_rank,
    reconcile_kids_sharing_profile,
    validate_themes,
)

KID_TODDLER = {
    "name": "Toddler",
    "age": 3,
    "max_maturity_rating": "TV-Y",
    "banned_themes": ["violence", "scary_imagery"],
    "max_pacing_score": 3,
    "allow_titles": ["Special Exception Show"],
    "block_titles": ["Banned By Name"],
}

KID_TWEEN = {
    "name": "Tween",
    "age": 10,
    "max_maturity_rating": "TV-Y7",
    "banned_themes": ["sexual_content"],
    "max_pacing_score": 7,
    "allow_titles": [],
    "block_titles": [],
}


def test_rating_rank_known_values_ordered():
    assert rating_rank("TV-Y") < rating_rank("TV-Y7") < rating_rank("TV-14") < rating_rank("TV-MA")


def test_rating_rank_unknown_raises():
    with pytest.raises(UnknownRatingError):
        rating_rank("NOT-A-REAL-RATING")


def test_allow_within_limits():
    title = Title(name="Calm Show", maturity_rating="TV-Y", themes=[], pacing_score=2)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "allow"


def test_block_on_maturity_rating_exceeded():
    title = Title(name="Big Kid Show", maturity_rating="TV-14", themes=[], pacing_score=2)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "block"
    assert any("maturity rating" in r for r in v.reasons)


def test_block_on_banned_theme():
    title = Title(name="Scary Cartoon", maturity_rating="TV-Y", themes=["scary_imagery"], pacing_score=1)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "block"
    assert any("banned theme" in r for r in v.reasons)


def test_block_on_pacing_exceeded():
    title = Title(name="Frenetic Show", maturity_rating="TV-Y", themes=[], pacing_score=9)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "block"
    assert any("pacing score" in r for r in v.reasons)


def test_needs_review_when_rating_missing():
    title = Title(name="Unrated Show", maturity_rating=None, themes=[], pacing_score=5)
    v = evaluate_title_for_kid(KID_TWEEN, title)
    assert v.status == "needs_review"


def test_needs_review_when_pacing_missing_even_if_rating_fine():
    title = Title(name="Rated But Unscored", maturity_rating="TV-Y7", themes=[], pacing_score=None)
    v = evaluate_title_for_kid(KID_TWEEN, title)
    assert v.status == "needs_review"


def test_needs_review_on_unrecognized_rating():
    title = Title(name="Weird Rating Show", maturity_rating="XYZ-9", themes=[], pacing_score=1)
    v = evaluate_title_for_kid(KID_TWEEN, title)
    assert v.status == "needs_review"


def test_explicit_block_override_wins_even_if_otherwise_allowed():
    title = Title(name="Banned By Name", maturity_rating="TV-Y", themes=[], pacing_score=1)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "block"
    assert "override" in v.reasons[0]


def test_explicit_allow_override_wins_even_if_otherwise_blocked():
    title = Title(name="Special Exception Show", maturity_rating="TV-MA", themes=["violence"], pacing_score=10)
    v = evaluate_title_for_kid(KID_TODDLER, title)
    assert v.status == "allow"
    assert "override" in v.reasons[0]


def test_evaluate_catalog_covers_every_kid():
    titles = [Title(name="Calm Show", maturity_rating="TV-Y", themes=[], pacing_score=2)]
    results = evaluate_catalog({"kids": [KID_TODDLER, KID_TWEEN]}, titles)
    assert set(results.keys()) == {"Toddler", "Tween"}
    assert len(results["Toddler"]) == 1
    assert len(results["Tween"]) == 1


def test_load_family_profile_example_file_is_valid():
    example_path = Path(__file__).resolve().parent.parent / "data" / "family-profile.example.json"
    profile = load_family_profile(example_path)
    assert len(profile["kids"]) == 2


def test_load_family_profile_rejects_missing_required_field(tmp_path):
    bad = {"kids": [{"name": "No Age Kid", "max_maturity_rating": "TV-Y"}]}
    p = tmp_path / "bad-profile.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="missing required field"):
        load_family_profile(p)


TODDLER_ON_SHARED_PROFILE = {
    "name": "Milo", "age": 3, "max_maturity_rating": "TV-Y",
    "banned_themes": ["violence", "scary_imagery"], "max_pacing_score": 3,
    "allow_titles": [], "block_titles": ["Only Milo Blocks This"],
}
SIX_YEAR_OLD_ON_SHARED_PROFILE = {
    "name": "Nora", "age": 6, "max_maturity_rating": "TV-Y7",
    "banned_themes": ["sexual_content"], "max_pacing_score": 5,
    "allow_titles": ["Shared Favorite"], "block_titles": [],
}
OTHER_SIX_YEAR_OLD_ON_SHARED_PROFILE = {
    "name": "Ivy", "age": 6, "max_maturity_rating": "TV-Y7",
    "banned_themes": ["romance"], "max_pacing_score": 5,
    "allow_titles": [],  # doesn't explicitly allow "Shared Favorite" -- intersection should exclude it
    "block_titles": [],
}


def test_reconcile_single_kid_returns_kid_unchanged():
    result = reconcile_kids_sharing_profile([SIX_YEAR_OLD_ON_SHARED_PROFILE])
    assert result is SIX_YEAR_OLD_ON_SHARED_PROFILE


def test_reconcile_requires_at_least_one_kid():
    with pytest.raises(ValueError):
        reconcile_kids_sharing_profile([])


def test_reconcile_maturity_ceiling_is_strictest_of_the_group():
    result = reconcile_kids_sharing_profile([TODDLER_ON_SHARED_PROFILE, SIX_YEAR_OLD_ON_SHARED_PROFILE])
    assert result["max_maturity_rating"] == "TV-Y"  # toddler's stricter ceiling wins, not TV-Y7


def test_reconcile_pacing_ceiling_is_strictest_of_the_group():
    result = reconcile_kids_sharing_profile([TODDLER_ON_SHARED_PROFILE, SIX_YEAR_OLD_ON_SHARED_PROFILE])
    assert result["max_pacing_score"] == 3


def test_reconcile_banned_themes_is_union():
    result = reconcile_kids_sharing_profile([TODDLER_ON_SHARED_PROFILE, SIX_YEAR_OLD_ON_SHARED_PROFILE])
    assert set(result["banned_themes"]) == {"violence", "scary_imagery", "sexual_content"}


def test_reconcile_block_titles_is_union():
    result = reconcile_kids_sharing_profile([TODDLER_ON_SHARED_PROFILE, SIX_YEAR_OLD_ON_SHARED_PROFILE])
    assert result["block_titles"] == ["Only Milo Blocks This"]  # original casing preserved


def test_reconcile_allow_titles_requires_unanimous_agreement():
    # Nora explicitly allows "Shared Favorite"; Ivy doesn't -- on a
    # shared profile, that override must NOT silently clear it for Ivy too.
    result = reconcile_kids_sharing_profile(
        [SIX_YEAR_OLD_ON_SHARED_PROFILE, OTHER_SIX_YEAR_OLD_ON_SHARED_PROFILE]
    )
    assert result["allow_titles"] == []


def test_reconcile_allow_titles_included_when_all_agree():
    twin = dict(OTHER_SIX_YEAR_OLD_ON_SHARED_PROFILE, allow_titles=["Shared Favorite"])
    result = reconcile_kids_sharing_profile([SIX_YEAR_OLD_ON_SHARED_PROFILE, twin])
    assert result["allow_titles"] == ["Shared Favorite"]  # original casing preserved


def test_reconcile_matches_live_netflix_observation():
    # Real-world check (2026-08-05): a shared "Girls" Netflix profile with a
    # 3-year-old and two 6-year-olds was already set to TV-G live, matching
    # the toddler's ceiling -- not the 6-year-olds' looser TV-Y7. This test
    # pins that the reconciliation logic reproduces that same outcome.
    result = reconcile_kids_sharing_profile(
        [TODDLER_ON_SHARED_PROFILE, SIX_YEAR_OLD_ON_SHARED_PROFILE, OTHER_SIX_YEAR_OLD_ON_SHARED_PROFILE]
    )
    assert rating_rank(result["max_maturity_rating"]) == rating_rank("TV-G")


def test_load_family_profile_rejects_unknown_rating(tmp_path):
    bad = {
        "kids": [
            {"name": "Kid", "age": 5, "max_maturity_rating": "NOT-REAL", "max_pacing_score": 5}
        ]
    }
    p = tmp_path / "bad-rating.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(UnknownRatingError):
        load_family_profile(p)


def test_load_family_profile_rejects_unknown_theme(tmp_path):
    bad = {
        "kids": [
            {
                "name": "Kid", "age": 5, "max_maturity_rating": "TV-Y", "max_pacing_score": 5,
                "banned_themes": ["made_up_theme"],
            }
        ]
    }
    p = tmp_path / "bad-theme.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(UnknownThemeError):
        load_family_profile(p)


def test_validate_themes_accepts_known_tags():
    validate_themes(["violence", "scary_imagery"])  # should not raise


def test_validate_themes_rejects_unknown_tag():
    with pytest.raises(UnknownThemeError, match="made_up"):
        validate_themes(["violence", "made_up"])
