#!/usr/bin/env python3
"""
Rubric engine for Kid Content Guardian.

Pure logic, no network/browser dependency: given a family profile (kid ages,
maturity ceilings, banned themes, pacing ceilings) and a title's metadata,
produces a verdict. Deliberately has no side effects so it's fully unit
testable and reusable from diff_report.py or directly from SKILL.md workflow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Unified 0-5 severity scale spanning both the TV-rating and MPAA-rating
# systems, so a kid's max_maturity_rating (whichever system it's expressed
# in) can be compared against a title's rating regardless of which system
# the title uses. Deliberately explicit and exhaustive rather than a
# `.get(rating, some_default)` lookup -- an unrecognized rating must be
# surfaced as "needs_review", never silently treated as safe or unsafe.
RATING_RANK = {
    "TV-Y": 0,
    "G": 0,
    "TV-G": 0,
    "TV-Y7": 1,
    "TV-Y7-FV": 1,
    "PG": 2,
    "TV-PG": 2,
    "TV-14": 3,
    "PG-13": 3,
    "TV-MA": 4,
    "R": 4,
    "NC-17": 5,
}


class UnknownRatingError(ValueError):
    """Raised when a rating string isn't in RATING_RANK -- caller must treat as needs_review, not guess."""


# Canonical theme vocabulary. banned_themes matching is exact-string (after
# normalization), so if the scorer that *writes* a title's themes and the
# family profile that *bans* a theme don't draw from the same fixed set, a
# ban can silently never match -- e.g. a profile banning "scary_imagery"
# while an LLM-inferred rating writes "scary content" for the same concept.
# Every theme ever recorded (record_rating in llm_rating_scorer.py, or a
# CSM response once mapped in csm_client.py's _parse_response) must be one
# of these, and every banned_themes entry in a family profile is validated
# against the same list at load time.
THEME_TAGS = frozenset({
    "violence",
    "scary_imagery",
    "sexual_content",
    "romance",
    "language",  # coarse/crude language
    "substance_use",
    "consumerism",
    "mature_themes",  # death, grief, other heavy real-world topics
    "gambling",
    "disrespectful_behavior",
})


class UnknownThemeError(ValueError):
    """Raised when a theme string isn't in THEME_TAGS -- caller must not silently accept a made-up tag."""


def validate_themes(themes: list[str]) -> None:
    unknown = sorted(t for t in themes if t not in THEME_TAGS)
    if unknown:
        raise UnknownThemeError(
            f"Unrecognized theme tag(s): {', '.join(unknown)}. Use one of {sorted(THEME_TAGS)}, "
            "or add the new tag to THEME_TAGS explicitly if it's genuinely a new category -- "
            "don't let free-text theme names drift, or banned_themes matching silently breaks."
        )


def rating_rank(rating: str) -> int:
    key = rating.strip().upper()
    if key not in RATING_RANK:
        raise UnknownRatingError(
            f"Unrecognized maturity rating {rating!r}. Add it to RATING_RANK "
            "explicitly once you've confirmed where it sits on the severity "
            "scale -- do not default it to a rank."
        )
    return RATING_RANK[key]


@dataclass
class Title:
    name: str
    maturity_rating: Optional[str] = None
    themes: list[str] = field(default_factory=list)
    pacing_score: Optional[int] = None  # 1 (calmest) - 10 (most frenetic); None = not yet scored
    rating_source: Optional[str] = None  # "csm" | "llm_inferred" | None -- informational, not used in verdict logic


@dataclass
class Verdict:
    kid_name: str
    title: str
    status: str  # "allow" | "block" | "needs_review"
    reasons: list[str]

    @property
    def allowed(self) -> bool:
        return self.status == "allow"


def _normalize(s: str) -> str:
    return s.strip().lower()


def evaluate_title_for_kid(kid: dict, title: Title) -> Verdict:
    kid_name = kid["name"]
    title_key = _normalize(title.name)

    block_titles = {_normalize(t) for t in kid.get("block_titles", [])}
    allow_titles = {_normalize(t) for t in kid.get("allow_titles", [])}

    if title_key in block_titles:
        return Verdict(kid_name, title.name, "block", ["explicit block override in family profile"])

    if title_key in allow_titles:
        return Verdict(kid_name, title.name, "allow", ["explicit allow override in family profile"])

    reasons: list[str] = []

    if title.maturity_rating is None:
        return Verdict(kid_name, title.name, "needs_review", ["no maturity rating on file for this title yet"])

    try:
        title_rank = rating_rank(title.maturity_rating)
    except UnknownRatingError as e:
        return Verdict(kid_name, title.name, "needs_review", [str(e)])

    kid_rank = rating_rank(kid["max_maturity_rating"])
    if title_rank > kid_rank:
        reasons.append(
            f"maturity rating {title.maturity_rating} exceeds ceiling {kid['max_maturity_rating']}"
        )

    banned = {_normalize(t) for t in kid.get("banned_themes", [])}
    matched_themes = sorted(t for t in title.themes if _normalize(t) in banned)
    if matched_themes:
        reasons.append(f"contains banned theme(s): {', '.join(matched_themes)}")

    if title.pacing_score is None:
        # We have a rating but not a pacing score yet -- can't clear it, don't block it either.
        return Verdict(kid_name, title.name, "needs_review", ["no pacing/stimulation score on file for this title yet"])

    max_pacing = kid["max_pacing_score"]
    if title.pacing_score > max_pacing:
        reasons.append(f"pacing score {title.pacing_score} exceeds ceiling {max_pacing}")

    if reasons:
        return Verdict(kid_name, title.name, "block", reasons)

    return Verdict(kid_name, title.name, "allow", ["within maturity, theme, and pacing limits"])


def evaluate_catalog(family_profile: dict, titles: list[Title]) -> dict[str, list[Verdict]]:
    """Evaluate every title for every kid in the family profile."""
    results: dict[str, list[Verdict]] = {}
    for kid in family_profile["kids"]:
        results[kid["name"]] = [evaluate_title_for_kid(kid, t) for t in titles]
    return results


REQUIRED_KID_FIELDS = ("name", "age", "max_maturity_rating", "max_pacing_score")


def reconcile_kids_sharing_profile(kids: list[dict]) -> dict:
    """
    Real households frequently put more than one kid on a single platform
    profile (e.g. a 3- and two 6-year-olds sharing one "Girls" Netflix
    profile) -- confirmed live: that shared profile's actual maturity
    ceiling was already set to the toddler's stricter TV-G, not the older
    kids' looser TV-Y7, because a shared profile can only have ONE setting.

    Combines N kids' individual rubrics into the single most-restrictive
    effective rubric for a shared profile:
      - max_maturity_rating: the strictest (lowest-rank) ceiling wins
      - max_pacing_score: the strictest (lowest) ceiling wins
      - banned_themes: union -- if any sharing kid bans a theme, it's banned
      - block_titles: union -- if any sharing kid blocks a title, it's blocked
      - allow_titles: intersection -- an override only applies if EVERY
        sharing kid's profile allows it, so one kid's convenience override
        can never quietly expose content to a sibling on the same profile
    """
    if len(kids) == 1:
        return kids[0]
    if not kids:
        raise ValueError("reconcile_kids_sharing_profile requires at least one kid")

    strictest = min(kids, key=lambda k: rating_rank(k["max_maturity_rating"]))

    def dedupe_preserve_case(titles: list[str]) -> list[str]:
        # Union/intersection logic works on normalized keys (matching evaluate_title_for_kid's
        # own comparisons), but the returned list keeps first-seen original casing so a
        # parent-facing report doesn't show an all-lowercased title name.
        seen: dict[str, str] = {}
        for t in titles:
            seen.setdefault(_normalize(t), t)
        return [seen[k] for k in sorted(seen)]

    block_titles_union = dedupe_preserve_case([t for k in kids for t in k.get("block_titles", [])])

    allow_key_sets = [{_normalize(t) for t in k.get("allow_titles", [])} for k in kids]
    allow_key_intersection = set.intersection(*allow_key_sets) if allow_key_sets else set()
    allow_titles_by_key = {_normalize(t): t for k in kids for t in k.get("allow_titles", [])}
    allow_titles = [allow_titles_by_key[key] for key in sorted(allow_key_intersection)]

    return {
        "name": " & ".join(k["name"] for k in kids),
        "max_maturity_rating": strictest["max_maturity_rating"],
        "max_pacing_score": min(k["max_pacing_score"] for k in kids),
        "banned_themes": sorted({t for k in kids for t in k.get("banned_themes", [])}),
        "block_titles": block_titles_union,
        "allow_titles": allow_titles,
    }


def load_family_profile(path: str | Path) -> dict:
    """Load and lightly validate a family-profile.json. Raises ValueError with
    a specific message on any structural problem -- never returns a partially
    valid profile."""
    data = json.loads(Path(path).read_text())

    kids = data.get("kids")
    if not isinstance(kids, list) or not kids:
        raise ValueError("family profile must have a non-empty 'kids' array")

    for i, kid in enumerate(kids):
        missing = [f for f in REQUIRED_KID_FIELDS if f not in kid]
        if missing:
            raise ValueError(f"kids[{i}] is missing required field(s): {', '.join(missing)}")
        # Validate the rating and any banned themes are recognized at load time, not first use.
        rating_rank(kid["max_maturity_rating"])
        validate_themes(kid.get("banned_themes", []))

    return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate a single title against a family profile (debug helper).")
    parser.add_argument("family_profile", help="Path to family-profile.json")
    parser.add_argument("title", help="Title name")
    parser.add_argument("--rating", help="Maturity rating, e.g. TV-Y7")
    parser.add_argument("--pacing", type=int, help="Pacing score 1-10")
    parser.add_argument("--themes", nargs="*", default=[])
    args = parser.parse_args()

    profile = load_family_profile(args.family_profile)
    title = Title(name=args.title, maturity_rating=args.rating, themes=args.themes, pacing_score=args.pacing)
    for kid_name, verdicts in evaluate_catalog(profile, [title]).items():
        v = verdicts[0]
        print(f"{kid_name}: {v.status} — {'; '.join(v.reasons)}")
