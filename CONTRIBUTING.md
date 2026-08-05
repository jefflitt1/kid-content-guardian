# Contributing

Pull requests and issues are welcome — this project is genuinely more useful with more eyes on it,
especially the parts marked "unverified" or "known fragility points" in `references/*.md`.

## Good first contributions

- **Live-verify a reference doc.** `references/netflix.md` and `references/primevideo.md` are
  marked with a verification date and a "Known fragility points" section. If a platform's UI has
  drifted since, a PR correcting the doc against what you actually see live is exactly the kind of
  contribution this project needs most — these docs are load-bearing for the `apply` step.
- **Add a new platform adapter.** See `SKILL.md` → "Adding a new platform" for the shape: one
  `references/<platform>.md` file following the existing docs' structure (what the platform
  natively supports, discover-step navigation, apply-step navigation, known fragility points). No
  script changes needed — `rubric_engine.py`, `content_cache.py`, `csm_client.py`,
  `wikipedia_client.py`, `llm_rating_scorer.py`, `pacing_scorer.py`, and `diff_report.py` are all
  platform-agnostic.
- **Expand the theme vocabulary.** `scripts/rubric_engine.py::THEME_TAGS` is deliberately a small,
  curated list. If you add a tag, update it in that one place — it's validated at load time
  (`validate_themes`), so a typo'd or one-off tag is rejected rather than silently matching nothing.
- **Fix `csm_client.py`'s response parsing.** It's written from Common Sense Media's public docs but
  hasn't been verified against a live partnership key (see the module docstring). If you have one,
  confirming/fixing `_parse_response()` closes a real gap.

## Ground rules that aren't up for debate in a PR

These came from real incidents during development — see the module docstrings and `SKILL.md`'s
"Hard rules" section for the full reasoning, not just the rule:

- **No headless/unattended execution.** Every `apply` happens in a session a parent is watching.
  A PR that adds scheduling, cron, or any unattended-write path will be declined regardless of how
  it's implemented.
- **No credential handling.** The skill never stores, requests, or reads a password or PIN. If a
  platform's flow needs one, the parent types it themselves.
- **No new data source without checking its terms for an AI/ML-use restriction first.** This
  project already removed TMDB after shipping it once (see README's "Data sources" section) because
  its API Terms of Use prohibit feeding its data to an AI application — exactly what this project
  does. Read a candidate source's actual terms, not just its marketing page, before proposing it.
- **A title with missing rating or pacing data is `needs_review`, never guessed into `allow` or
  `block`.** Don't add a fallback that silently assumes safety (or unsafety) from partial data.
- **`llm_inferred` ratings always carry a rationale a parent can read**, and are always visibly
  flagged as lower-confidence than an independent review in `diff_report.py`'s output. Don't remove
  that distinction to simplify a report.

## Development

```
pip install -r requirements.txt
python3 -m pytest tests/ -v
```

`scripts/rubric_engine.py` has the most complete test coverage and no network/browser dependency —
a good place to start reading the code. Tests for a bug fix or new behavior are expected, not
optional; several of the existing tests were written specifically to catch a real regression found
during development (see the mutation-testing note in commit history for `rubric_engine.py`'s theme
check, if you want the precedent).

## Reporting a platform-behavior bug

If a `references/<platform>.md` doc turns out to be wrong (a UI moved, a control doesn't do what's
documented), please open an issue with what you found even if you don't have time to fix the doc
yourself — these docs only stay useful if drift gets reported.
