# family-profile.json field reference

Full JSON Schema: `assets/family-profile.schema.json`. This is the plain-English version.

Your real file is `data/family-profile.json` (gitignored — it's PII: kids' names and ages). Copy
`data/family-profile.example.json` to get started.

## Top level

- `kids` (required, array): one entry per child.
- `platform_profiles` (optional, object): maps `{platform: {kid_name: platform_profile_name}}` so
  a discovered catalog (keyed by the platform's own profile name, e.g. "Big Kids") can be matched
  back to the right kid in your rubric. Without an entry here for a given platform, that kid is
  skipped when diffing that platform — no profile name to look up means nothing to compare against.

## Per-kid fields

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Local display name only. Never sent to Common Sense Media or any external API — only title names leave your machine. |
| `age` | yes | Informational; not used directly in scoring (the ratings/pacing ceilings below are what actually gate content — set them deliberately rather than relying on age alone). |
| `max_maturity_rating` | yes | Ceiling on the unified rating scale (`scripts/rubric_engine.py::RATING_RANK`). One of `TV-Y, TV-Y7, TV-G, G, TV-PG, PG, TV-14, PG-13`. |
| `banned_themes` | no | Theme tags that block a title outright regardless of rating. Must be drawn from the canonical vocabulary in `scripts/rubric_engine.py::THEME_TAGS` — currently `violence`, `scary_imagery`, `sexual_content`, `romance`, `language`, `substance_use`, `consumerism`, `mature_themes`, `gambling`, `disrespectful_behavior`. This is the *same* fixed list the scorer (CSM mapping or Claude's own inference) must draw from when recording a title's themes — matching is exact-string, so a theme tag outside this list can never match anything and `load_family_profile()` rejects it at load time rather than silently no-op'ing. |
| `max_pacing_score` | yes | 1 (calmest) to 10 (most frenetic) ceiling. Titles scored above this are blocked even if rating and themes are fine. |
| `allow_titles` | no | Exact-match title names that are always allowed, overriding every other check. Use for a show you've personally vetted that the rubric would otherwise flag (e.g. an unusual rating). |
| `block_titles` | no | Exact-match title names that are always blocked, overriding every other check. |

## Shared platform profiles

More than one kid can map to the same real platform profile name under `platform_profiles` — e.g.
`{"Milo": "Girls", "Nora": "Girls", "Ivy": "Girls"}`. A real platform profile has exactly
one maturity ceiling and one block list, so `rubric_engine.reconcile_kids_sharing_profile()` combines
the sharing kids' individual rubrics into one effective rubric, most-restrictive-wins:

| Field | Combination rule |
|---|---|
| `max_maturity_rating` | strictest (lowest-rank) ceiling among the group |
| `max_pacing_score` | strictest (lowest) ceiling among the group |
| `banned_themes` | union — any sharing kid's ban applies to the whole profile |
| `block_titles` | union — any sharing kid's explicit block applies to the whole profile |
| `allow_titles` | **intersection** — an override only takes effect if every kid sharing the profile explicitly allows it, so one kid's convenience override can never quietly expose content a sibling on the same profile would otherwise be blocked from |

This was live-verified against a real account (2026-08-05): a profile shared by a 3-year-old and
two 6-year-olds was already set to the 3-year-old's stricter ceiling, matching what this logic
reproduces.

## Verdict precedence (see `rubric_engine.evaluate_title_for_kid`)

1. `block_titles` match → block, always.
2. `allow_titles` match → allow, always.
3. Missing maturity rating, or missing pacing score, or an unrecognized rating string → `needs_review`
   (never silently allowed or silently blocked — a title with a data gap should be surfaced, not
   guessed on).
4. Maturity rating over ceiling → block.
5. Any banned theme present → block.
6. Pacing score over ceiling → block.
7. Otherwise → allow.
