#!/usr/bin/env python3
"""
Builds the human-reviewed diff between "what's currently visible to a kid on
a platform" and "what the family rubric says should be visible" -- the
output the parent reviews and approves *before* anything gets clicked in a
supervised browser session. Nothing in this module touches a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rubric_engine import Title, evaluate_title_for_kid, reconcile_kids_sharing_profile


@dataclass
class PlatformDiff:
    platform: str
    kid_name: str
    platform_profile_name: str
    to_block: list[dict] = field(default_factory=list)  # {"title": ..., "rating_source": ...}
    needs_review: list[dict] = field(default_factory=list)  # {"title": ..., "reasons": [...]}
    allowed_count: int = 0
    llm_inferred_count: int = 0  # of allowed_count + to_block, how many relied on Claude's own rating rather than CSM


def build_diff(family_profile: dict, platform: str, catalog: dict[str, list[str]],
                titles_metadata: dict[str, Title]) -> list[PlatformDiff]:
    """
    catalog: {platform_profile_name: [title names currently visible to that profile]}
    titles_metadata: {title name: Title} -- ratings/themes/pacing already resolved
      by the caller (via csm_client + pacing_scorer) before calling this.

    More than one kid can be mapped to the same real platform_profile_name
    (a shared "Girls" profile, say) -- those get grouped and evaluated
    against ONE reconciled, most-restrictive-wins rubric
    (rubric_engine.reconcile_kids_sharing_profile), because a real platform
    profile can only have one maturity ceiling and one block list, not a
    different one per kid sharing it.
    """
    platform_profiles = family_profile.get("platform_profiles", {}).get(platform, {})
    kids_by_name = {k["name"]: k for k in family_profile["kids"]}

    profile_to_kids: dict[str, list[dict]] = {}
    for kid_name, profile_name in platform_profiles.items():
        kid = kids_by_name.get(kid_name)
        if kid is None:
            continue  # profile mapping references a kid not in this family profile -- ignore, don't guess
        profile_to_kids.setdefault(profile_name, []).append(kid)

    diffs: list[PlatformDiff] = []
    for profile_name, kids in profile_to_kids.items():
        if profile_name not in catalog:
            continue  # mapped, but this platform's discover step didn't return this profile

        effective_kid = reconcile_kids_sharing_profile(kids)
        diff = PlatformDiff(platform=platform, kid_name=effective_kid["name"], platform_profile_name=profile_name)
        for title_name in catalog[profile_name]:
            title = titles_metadata.get(title_name, Title(name=title_name))
            verdict = evaluate_title_for_kid(effective_kid, title)
            if verdict.status == "block":
                diff.to_block.append({"title": title_name, "rating_source": title.rating_source})
                if title.rating_source == "llm_inferred":
                    diff.llm_inferred_count += 1
            elif verdict.status == "needs_review":
                diff.needs_review.append({"title": title_name, "reasons": verdict.reasons})
            else:
                diff.allowed_count += 1
                if title.rating_source == "llm_inferred":
                    diff.llm_inferred_count += 1
        diffs.append(diff)

    return diffs


def render_text(diffs: list[PlatformDiff]) -> str:
    if not diffs:
        return "No mapped kid profiles found for this platform in family-profile.json."

    lines: list[str] = []
    for d in diffs:
        lines.append(f"## {d.platform} — {d.platform_profile_name} ({d.kid_name})")
        lines.append(f"  {d.allowed_count} titles already within limits, no action needed.")
        if d.llm_inferred_count:
            lines.append(
                f"  ⚠ {d.llm_inferred_count} of the ratings below are Claude's own inference "
                "(no Common Sense Media key configured) -- lower confidence than an independent "
                "review, spot-check before approving."
            )
        if d.to_block:
            lines.append(f"  {len(d.to_block)} title(s) to BLOCK:")
            for item in d.to_block:
                flag = " [LLM-inferred rating]" if item["rating_source"] == "llm_inferred" else ""
                lines.append(f"    - {item['title']}{flag}")
        if d.needs_review:
            lines.append(f"  {len(d.needs_review)} title(s) NEED REVIEW (no verdict yet -- not blocked, not cleared):")
            for item in d.needs_review:
                lines.append(f"    - {item['title']}: {'; '.join(item['reasons'])}")
        if not d.to_block and not d.needs_review:
            lines.append("  Nothing to change.")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Render a diff report from a family profile + a discovered catalog JSON file (debug helper).")
    parser.add_argument("family_profile")
    parser.add_argument("platform")
    parser.add_argument("catalog_json", help='{"profile_name": ["Title A", "Title B"]}')
    args = parser.parse_args()

    from rubric_engine import load_family_profile

    profile = load_family_profile(args.family_profile)
    catalog = json.loads(open(args.catalog_json).read())
    # No metadata source wired up in this standalone invocation -- everything
    # will come back needs_review, which is correct: this CLI is for
    # exercising the diff shape, not a real sync.
    diffs = build_diff(profile, args.platform, catalog, titles_metadata={})
    print(render_text(diffs))
