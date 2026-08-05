import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from diff_report import build_diff, render_text  # noqa: E402
from rubric_engine import Title  # noqa: E402

FAMILY_PROFILE = {
    "kids": [
        {
            "name": "Toddler",
            "age": 3,
            "max_maturity_rating": "TV-Y",
            "banned_themes": ["violence"],
            "max_pacing_score": 3,
            "allow_titles": [],
            "block_titles": [],
        }
    ],
    "platform_profiles": {
        "netflix": {"Toddler": "Kids"},
    },
}


def test_build_diff_blocks_over_pacing_title():
    catalog = {"Kids": ["Calm Show", "Frenetic Show"]}
    metadata = {
        "Calm Show": Title(name="Calm Show", maturity_rating="TV-Y", themes=[], pacing_score=2),
        "Frenetic Show": Title(name="Frenetic Show", maturity_rating="TV-Y", themes=[], pacing_score=9),
    }
    diffs = build_diff(FAMILY_PROFILE, "netflix", catalog, metadata)
    assert len(diffs) == 1
    d = diffs[0]
    assert d.to_block == [{"title": "Frenetic Show", "rating_source": None}]
    assert d.allowed_count == 1
    assert d.needs_review == []


def test_build_diff_flags_unscored_title_as_needs_review_not_block():
    catalog = {"Kids": ["Mystery Show"]}
    metadata = {"Mystery Show": Title(name="Mystery Show", maturity_rating="TV-Y", themes=[], pacing_score=None)}
    diffs = build_diff(FAMILY_PROFILE, "netflix", catalog, metadata)
    d = diffs[0]
    assert d.to_block == []
    assert len(d.needs_review) == 1
    assert d.needs_review[0]["title"] == "Mystery Show"


def test_build_diff_skips_kid_with_no_mapped_profile_on_platform():
    catalog = {"SomeOtherProfileName": ["Calm Show"]}
    diffs = build_diff(FAMILY_PROFILE, "netflix", catalog, {})
    assert diffs == []  # "Kids" profile not present in catalog -> no diff for Toddler


def test_render_text_mentions_blocked_title():
    catalog = {"Kids": ["Frenetic Show"]}
    metadata = {"Frenetic Show": Title(name="Frenetic Show", maturity_rating="TV-Y", themes=[], pacing_score=9)}
    diffs = build_diff(FAMILY_PROFILE, "netflix", catalog, metadata)
    text = render_text(diffs)
    assert "Frenetic Show" in text
    assert "BLOCK" in text


def test_render_text_no_diffs_message():
    assert "No mapped kid profiles" in render_text([])


SHARED_PROFILE_FAMILY = {
    "kids": [
        {"name": "Milo", "age": 3, "max_maturity_rating": "TV-Y", "banned_themes": ["violence"],
         "max_pacing_score": 3, "allow_titles": [], "block_titles": []},
        {"name": "Nora", "age": 6, "max_maturity_rating": "TV-Y7", "banned_themes": [],
         "max_pacing_score": 5, "allow_titles": [], "block_titles": []},
        {"name": "Ivy", "age": 6, "max_maturity_rating": "TV-Y7", "banned_themes": [],
         "max_pacing_score": 5, "allow_titles": [], "block_titles": []},
    ],
    "platform_profiles": {
        "netflix": {"Milo": "Girls", "Nora": "Girls", "Ivy": "Girls"},
    },
}


def test_build_diff_reconciles_three_kids_sharing_one_profile():
    catalog = {"Girls": ["Toddler-safe Show", "TV-Y7 Show"]}
    metadata = {
        "Toddler-safe Show": Title(name="Toddler-safe Show", maturity_rating="TV-Y", themes=[], pacing_score=2),
        # Fine for the 6-year-olds alone (TV-Y7), but must be BLOCKED on the
        # shared profile because Milo's ceiling is TV-Y.
        "TV-Y7 Show": Title(name="TV-Y7 Show", maturity_rating="TV-Y7", themes=[], pacing_score=2),
    }
    diffs = build_diff(SHARED_PROFILE_FAMILY, "netflix", catalog, metadata)
    assert len(diffs) == 1  # one diff for the shared profile, not three
    d = diffs[0]
    assert d.platform_profile_name == "Girls"
    assert "Milo" in d.kid_name and "Nora" in d.kid_name and "Ivy" in d.kid_name
    assert d.allowed_count == 1
    assert [b["title"] for b in d.to_block] == ["TV-Y7 Show"]


def test_build_diff_flags_llm_inferred_source():
    catalog = {"Kids": ["Frenetic Show"]}
    metadata = {
        "Frenetic Show": Title(
            name="Frenetic Show", maturity_rating="TV-Y", themes=[], pacing_score=9,
            rating_source="llm_inferred",
        )
    }
    diffs = build_diff(FAMILY_PROFILE, "netflix", catalog, metadata)
    d = diffs[0]
    assert d.to_block == [{"title": "Frenetic Show", "rating_source": "llm_inferred"}]
    assert d.llm_inferred_count == 1
    text = render_text(diffs)
    assert "LLM-inferred rating" in text
    assert "Claude's own inference" in text
