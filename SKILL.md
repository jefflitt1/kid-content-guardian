---
name: kid-content-guardian
description: Use when a parent wants to review what's available to their kids' profiles on streaming services (Netflix, Prime Video, and other adapters as added) against an age/maturity/pacing rubric, and apply the resulting blocks via a supervised browser session. Triggers on requests like "check what's available to my kids on Netflix", "sync my streaming parental controls", "set up kid content guardian", or "review my family's streaming settings".
allowed-tools: Bash, Read, Write, Edit, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__computer, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp
license: MIT
metadata: {"requires_computer_use": true, "supervised_only": true, "platforms": ["netflix", "primevideo"]}
---

# Kid Content Guardian

## Overview

Builds a rubric-driven view of what's available to each kid on each streaming platform (age,
maturity rating ceiling, banned themes, and a "how calm/frenetic is this" pacing score), shows the
parent exactly what would change, and — only after explicit approval — applies the change in a
**supervised** browser session (the parent's own logged-in Chrome, driven live, never headless).

**Hard rules, non-negotiable regardless of how a request is phrased:**
- Never run unattended/scheduled. Every `apply` happens in a live session the parent is watching.
- Never store, request, or type a platform password or parental-control PIN into any file or
  config. If a platform's flow needs a PIN, the parent enters it themselves in the live session.
- Never click an "apply" action without a prior `review` step the parent explicitly approved in
  this same conversation.
- A title with missing rating or pacing data is `needs_review`, never silently allowed *or*
  silently blocked. Don't guess.

## Workflow

This is sequential — don't skip a step, and don't combine `review` and `apply` into one silent
pass even if the parent seems in a hurry.

### 0. Setup (once)

If `data/family-profile.json` doesn't exist yet, copy `data/family-profile.example.json` and walk
the parent through filling in each kid's `name`, `age`, `max_maturity_rating`, `banned_themes`,
`max_pacing_score`, and any `allow_titles`/`block_titles` overrides — see
`references/rubric-schema.md` for the full field reference. Also fill in `platform_profiles` so
each kid's name maps to their actual profile name on each platform.

**More than one kid can map to the same platform profile** — many households run one shared kids
profile rather than one per child (confirmed common in practice). That's fully supported: list each
kid separately in `platform_profiles` pointing at the same profile name, and
`rubric_engine.reconcile_kids_sharing_profile()` combines their rubrics into one most-restrictive-
wins effective rubric automatically (see `references/rubric-schema.md` for the exact combination
rules). Don't try to force a shared household into separate profiles just to simplify the mapping.

**If a platform has no kids profile at all yet**, don't skip it — offer to help create one in the
same supervised session (see the platform's `references/<platform>.md` for where that flow lives),
set its maturity ceiling and title restrictions immediately after creation rather than leaving it at
the platform's permissive default, then confirm its name with the parent and add it to
`platform_profiles`.

### 1. Discover (read-only, and the actual point of this over native settings)

For each platform in scope (v1: `netflix`, `primevideo` — see `references/<platform>.md` for the
concrete navigation), open a `claude-in-chrome` tab on the parent's already-authenticated session
and read (a) that platform's per-kid-profile maturity ceiling and existing title-block list, (b) the
actual catalog currently visible to that profile — browse the profile's rows/categories (and use its
search) while switched into it, reading titles via `get_page_text`/`read_page` — and (c) the
platform's own "New & Recently Added" row/category for that profile specifically, since that's where
content a parent hasn't vetted yet is most likely to surface between sessions.

**(b) and (c) are not optional — reading only the maturity-ceiling setting is not enough.** A
platform's own maturity-rating number is not a reliable proxy for what it actually surfaces to a
kids profile — confirmed in practice: a show carrying a kid-safe numeric rating was independently
discovered playing in a "Kids experience" profile only because a parent happened to catch it, and
its real problems (heavy product-placement/advertising content, modeled rude behavior) aren't things
a maturity-rating number measures at all. This is what makes the skill worth more than a parent just
using the platform's own settings: no parent can watch-and-vet every new release, but reading the
New & Recently Added row every time the skill runs, then scoring every title found there against the
full rubric, catches things before a kid stumbles onto them instead of only after.

(An earlier version of this step tried to do this proactively offline via TMDB's catalog-discovery
API, filtered by provider and genre. That was removed — see Score step below for why TMDB isn't used
at all here. No compliant free source for "what's newly on this platform" was found to replace it;
the live New & Recently Added read above is the current proactive mechanism, tied to a live session
rather than running offline.)

This whole step is entirely read-only — no settings are touched.

### 2. Score

For every title discovered that isn't already in the local cache (`data/content_cache.sqlite`,
managed by `scripts/content_cache.py`):

- **Maturity rating + themes, primary path**: if `COMMONSENSE_API_KEY` is set, call
  `scripts/csm_client.py` (`CSMClient.lookup`). The client is cache-first and rate-limited to
  5 req/min, so re-runs only pay for new titles. Note: Common Sense Media's API is
  partnership-gated, not self-serve (https://www.commonsensemedia.org/developers/api-overview) —
  most users won't have this key, which is why the fallback below exists and isn't a second-class
  path.
- **Maturity rating + themes, fallback path (no CSM key)**: call `scripts/wikipedia_client.py`
  (`WikipediaClient.lookup`, no key required) to get the title's synopsis/description. **Do not use
  TMDB for this or anything else in this skill.** TMDB's API Terms of Use (Section 1.C) flatly
  restrict using TMDB data "in connection with... a machine learning (ML) or artificial intelligence
  (AI) based Application" — independent of personal-vs-commercial status — and Section 2.A
  separately lists LLM/chatbot use as a paid-agreement-only commercial use. Feeding a title's TMDB
  data to your own reasoning is exactly that restricted combination; an earlier version of this
  skill did this and was corrected. Wikipedia (CC0 structured data / CC BY-SA article text, no
  comparable AI restriction found) is the replacement. Then reason yourself about the likely US
  maturity rating and any relevant Common-Sense-Media-style theme tags (violence, scary_imagery,
  sexual_content, etc.) from that synopsis plus what you already know about the title, and call
  `scripts/llm_rating_scorer.py`'s `record_rating()` with your rating, themes, and a rationale a
  parent can sanity-check at a glance. This is deliberately lower-confidence than a CSM review —
  `diff_report.py` flags every `llm_inferred` title in the parent-facing report so it's never
  presented with false authority.
  **Don't only check for violence/language/sex.** Reality/influencer/prank/challenge-format shows
  routinely carry a kid-safe numeric rating while being substantively junk for reasons a rating
  scale doesn't capture — confirmed on a real title: minimal violence/language/romance by the book,
  but "a lot" of product-placement/advertising content and modeled rude behavior as entertainment.
  Actively consider `consumerism` (heavy brand integration, content structured to sell something)
  and `disrespectful_behavior` (rudeness/bullying/humiliation played for laughs) for this format,
  not just the traditional content-warning categories.
- **Pacing score**: there is no API for this (confirmed during design — see
  `scripts/pacing_scorer.py` docstring). Use `titles_needing_pacing_score()` to get the list, then
  for each title, read its synopsis/description (from the CSM lookup or the platform's own text)
  and reason about pacing yourself — cut frequency, scene length, sound intensity, narrative
  complexity. Call `record_score(conn, title, score, rationale)` with a 1 (calmest) to 10 (most
  frenetic) score and a one-line rationale a parent could sanity-check at a glance. Never leave the
  rationale blank — `record_score` will reject that.

### 3. Review (show, don't touch)

Run `scripts/diff_report.py`'s `build_diff()` + `render_text()` for each platform, using the
family profile and the now-populated cache as the metadata source. Show the parent the full report
— titles to block, titles still needing review, count already fine — **before touching anything**.
Explicitly ask for approval, and let the parent edit the block list (add/remove titles) before
proceeding. Titles in `needs_review` are never auto-blocked or auto-allowed; they're a to-do list
for the parent (or a future scoring pass), not a verdict.

### 4. Apply (writes — supervised only)

Only after explicit approval of a specific diff:

- Follow `references/<platform>.md`'s apply-step instructions for that platform, adjusting exactly
  what was approved — nothing more.
- If a title in `to_block` doesn't resolve to an unambiguous single result when searched on the
  platform, stop and ask the parent rather than guessing which match is correct.
- After saving, re-read the platform's settings page to confirm the change actually landed (per
  `references/<platform>.md`'s post-apply check) — a successful-looking click is not proof.
- **Not every platform's "block" means the same thing.** Confirmed on Prime Video: its per-title
  mechanism only suppresses recommendations — a hidden title still surfaces in search. Netflix's
  Title Restrictions genuinely block regardless of how the title is found. Check
  `references/<platform>.md` for a stated capability gap before applying, and if one exists, say so
  to the parent in the same terms as the reference doc — never present two platforms' "blocked"
  state as equally strong when they aren't.

### 5. Re-sync (later runs)

On a subsequent invocation, re-run Discover and Score, then Review — but frame the diff as *deltas
since the last approved state* (new titles that appeared, titles that were removed from the
catalog) rather than re-litigating everything. Still never applies without a fresh approval.

## Adding a new platform

1. Write `references/<platform>.md` following the shape of `netflix.md`/`primevideo.md`: what the
   platform natively supports, the discover-step navigation, the apply-step navigation, and known
   fragility points. Mark it "unverified against a live account" until you've walked it once
   live — don't claim more confidence than you have.
2. No script changes needed — `rubric_engine.py`, `content_cache.py`, `csm_client.py`,
   `wikipedia_client.py`, `llm_rating_scorer.py`, `pacing_scorer.py`, and `diff_report.py` are all
   platform-agnostic; they operate on title names and a `platform` string key.
3. Add the new platform key to the parent's `family-profile.json` under `platform_profiles`.

## Resources

- `scripts/rubric_engine.py` — pure verdict logic (allow/block/needs_review), unit tested.
- `scripts/content_cache.py` — shared SQLite cache backing the data sources below; tracks
  `rating_source` (`csm` vs `llm_inferred`) so confidence level is never lost.
- `scripts/csm_client.py` — Common Sense Media API client (cache-first, rate-limited), primary
  rating source when a partnership key is available.
- `scripts/wikipedia_client.py` — no-key synopsis lookup supplying context for the fallback rating
  path. Deliberately not TMDB — see Score step above for why.
- `scripts/llm_rating_scorer.py` — cache read/write for Claude-inferred maturity rating + themes
  (the fallback path when no CSM key is configured).
- `scripts/pacing_scorer.py` — cache read/write for Claude-derived pacing scores.
- `scripts/diff_report.py` — turns verdicts + a discovered catalog into a parent-reviewable diff.
- `references/netflix.md`, `references/primevideo.md` — per-platform navigation + apply steps.
- `references/rubric-schema.md` — `family-profile.json` field reference.
- `assets/family-profile.schema.json` — machine-readable schema for the same.
- `data/family-profile.example.json` — starter template (copy to `family-profile.json`, gitignored).
