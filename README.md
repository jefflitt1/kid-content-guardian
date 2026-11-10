# Kid Content Guardian

A Claude Code skill that reviews what's actually available to your kids' profiles on streaming
services against a rubric you set — age, maturity rating, banned themes, and a "how calm vs.
frenetic is this" pacing score — and applies the resulting blocks through a **supervised** browser
session you watch.

If this skill is useful to you, please give it a [⭐ on GitHub](https://github.com/jefflitt1/kid-content-guardian) — it helps others find it.

## Who this is for

**This is not a general consumer app.** It's a [Claude Code](https://claude.com/claude-code) skill,
which means it assumes you have Claude Code and browser computer-use
([claude-in-chrome](https://claude.com/claude-code)) available. If that's not you, this repo won't
be directly useful yet — the reference docs and rubric engine are plain Python and reusable, but
there's no standalone app here.

## What it actually does (and doesn't)

- Reads what's currently visible to a kid's profile on a platform, including its "New & Recently
  Added" row specifically — not just the maturity-rating setting (read-only).
- Scores each title against your rubric using age/theme ratings from
  [Common Sense Media](https://www.commonsensemedia.org) if you have a partnership API key — CSM's
  API isn't self-serve (see below) — or, by default, from a [Wikipedia](https://www.wikipedia.org)
  synopsis lookup (no key required) plus Claude's own judgment, clearly flagged as lower-confidence
  in every report. On top of either source, a pacing/stimulation score Claude derives itself, since
  no API exposes that today. **Not TMDB** — its API Terms of Use restrict using its data in
  connection with any AI/ML application, which is exactly this use; see "Data sources" below.
- Shows you a plain-language diff — what would be blocked, what needs more data — **before
  touching anything**.
- Only after you approve, drives your own already-logged-in browser session to apply exactly that
  change, then re-reads the settings to confirm it landed.
- **Never** runs unattended or on a schedule. **Never** stores or handles your account password or
  parental-control PIN — you type those yourself if a platform's flow requires them.

v1 covers **Netflix and Prime Video**. Adding another platform is a documentation task (one
`references/<platform>.md` file), not a rewrite — see `SKILL.md` → "Adding a new platform".

## ⚠️ A real risk to understand before using this

Most streaming services' Terms of Service prohibit automated/bot access to your account. This
project deliberately avoids the highest-risk pattern (headless, unattended scripts) in favor of a
supervised session — you're logged in on your own browser, watching, and can stop at any point —
which is a materially different posture than an unattended bot. It is **not** zero risk. Use your
own judgment about your accounts, and don't run this unattended even if you find a way to.

## Setup

1. Clone this repo, `cd` into it (or symlink it into `~/.claude/skills/kid-content-guardian` if
   you use Claude Code's skill library).
2. `pip install -r requirements.txt` (or just `pip install requests pytest` — the only two
   dependencies).
3. No key needed for the default rating path — it uses Wikipedia's public API. *Optional,
   higher-confidence upgrade:* Common Sense Media's API is gated behind a partnership agreement, not
   a self-serve key — see https://www.commonsensemedia.org/developers/api-overview and their
   [contact form](https://commonsense.force.com/membersupport/s/contactsupport) if you want to
   pursue it. If you get one, `export COMMONSENSE_API_KEY=...` and the skill prefers it
   automatically.
4. Copy `data/family-profile.example.json` to `data/family-profile.json` and fill in your kids —
   see `references/rubric-schema.md` for every field.
5. In Claude Code, with `claude-in-chrome` connected, ask it to run the Kid Content Guardian skill
   (e.g. "check what's available to my kids on Netflix"). It'll walk you through discover → score →
   review, and only apply changes you've explicitly approved.

## Data sources

An earlier version of this project used [TMDB](https://www.themoviedb.org) as the fallback
synopsis source. That was removed after reading TMDB's actual API Terms of Use: Section 1.C
restricts using TMDB data "in connection with... a machine learning (ML) or artificial intelligence
(AI) based Application" — regardless of personal vs. commercial use — and Section 2.A separately
lists LLM/chatbot use as a commercial use requiring a paid agreement. Feeding a title's TMDB data to
an LLM's reasoning (exactly what this project does) is the restricted combination.

The fallback path now uses Wikipedia (CC0 for structured data, CC BY-SA for article text — no
comparable AI-use restriction found, and Wikimedia explicitly frames their data as suitable for
LLM/AI use). `scripts/wikipedia_client.py` always returns a `source_url` for attribution.

**If you're evaluating a new data source for this project**, check its terms for an AI/ML-use
restriction *before* wiring it in, not after — that's the mistake that produced this section.

## Development

```
python3 -m pytest tests/ -v
```

`scripts/rubric_engine.py` is pure logic with no network/browser dependency — that's the part with
real test coverage today. `scripts/csm_client.py`'s exact request/response contract is written
against Common Sense Media's public docs but hasn't been verified against a live API key (see the
module docstring) — if you get a key and confirm the real response shape, a PR fixing
`_parse_response()` is very welcome. The platform reference docs (`references/netflix.md`,
`references/primevideo.md`) are similarly marked "unverified against a live account" until someone
walks them live and confirms the navigation still matches.

## License

MIT — see `LICENSE`.

If it helped, a [⭐](https://github.com/jefflitt1/kid-content-guardian) is a small way to help the next parent find it.
