# Netflix — supervised settings adapter

**Status: verified live 2026-08-05** against a real account (5 profiles, including one profile
shared by 3 kids at different ages). Corrected from an earlier version written off Netflix's public
Help Center docs alone — several details differed from what's documented there.

## What Netflix actually supports

Netflix does **not** have a fully separate "kids account" the way Disney+ does. Per-profile controls
live on one combined form and are saved together, not as separate flows:

- **Path**: Account (`netflix.com/account`) → **Profiles** in the left nav → **"Adjust parental
  controls"** (labeled "Set maturity ratings, block titles") under "Parental Controls and
  Permissions" at the top of that page → pick a profile from the list shown.
- This triggers a **re-authentication gate** (`netflix.com/mfa?guid=...`) — email a code, text a
  code, or confirm password — **before** showing that profile's settings. This is exactly the kind
  of identity check the skill must never touch; the parent completes it themselves in the live
  session, every time, not just once.
- After verification, lands on `netflix.com/settings/restrictions/<guid>` — **"Adjust Parental
  Controls"** — with three sections on one form:
  1. **"Profile Maturity Rating for {profile}"** — a discrete slider/stepper, not a dropdown, with
     stops in this order (confirmed live): `TV-Y → TV-Y7 → TV-G/G → TV-PG/PG → PG-13 → TV-14 → R →
     TV-MA → NC-17`. Matches this repo's unified `RATING_RANK` scale
     (`scripts/rubric_engine.py`) — TV-G/G share a step, TV-PG/PG share a step, R/TV-MA are
     adjacent tiers, NC-17 is the top. The current selection is visibly highlighted (blue dot).
  2. **"Kids Profile"** — a checkbox: "Display the Netflix Kids experience with titles just for
     kids." Independent of the maturity slider.
  3. **"Title Restrictions for {profile}"** — labeled "Don't show specific titles for this profile
     regardless of Maturity Rating." A text input ("Enter show or movie name") to add a title, and
     a list of currently-blocked titles below it, each with an `×` to remove. **This** is the
     mechanism `diff_report.py`'s `to_block` list maps onto.
  4. A single **Save** / **Cancel** pair at the bottom saves the maturity rating, kids-profile
     checkbox, and title restrictions together in one action — there's no separate save per section.

Source: live walkthrough 2026-08-05, cross-checked against
[Netflix Help Center — parental controls](https://help.netflix.com/en/node/264).

## If the platform has no dedicated kids profile yet

Real households often run one shared profile across several kids of different ages rather than one
profile per kid (confirmed with the parent who commissioned this: 3 kids, ages 3/6/6, share one
"Girls" Netflix profile). Two implications:

1. **Don't assume a 1:1 kid-to-profile mapping.** `family-profile.json`'s `platform_profiles` maps
   each kid's name to whatever real profile they're actually on — multiple kids can point at the
   same profile name. `rubric_engine.reconcile_kids_sharing_profile()` combines their individual
   rubrics into one most-restrictive-wins effective rubric for that shared profile (strictest
   maturity ceiling, strictest pacing ceiling, union of banned themes and blocked titles,
   intersection of allow-overrides). This was live-verified: a shared profile with a 3- and two
   6-year-olds was already set to TV-G — the toddler's ceiling, not the older kids' looser TV-Y7 —
   which is exactly what the reconciliation logic reproduces.
2. **If a parent has no kids profile at all yet**, offer to help create one in the same supervised
   session, via "Manage Profiles" → **Add Profile** (visible on the main Profiles page, not the
   parental-controls sub-page). Set its maturity ceiling and Title Restrictions immediately after
   creation, in the same flow described above, rather than leaving a freshly-created profile at
   Netflix's permissive default. Confirm the new profile's name with the parent before writing it
   into `family-profile.json`'s `platform_profiles`.

## Apply step (writes — supervised only)

Only after the parent has reviewed `diff_report.py`'s output and approved it:

1. Account → Profiles → Adjust parental controls → select the profile. Complete the
   re-authentication gate (parent does this themselves).
2. If the diff calls for a maturity ceiling change, click the corresponding stop on the slider.
3. For each title in `to_block`, type it into the Title Restrictions search field and select it.
   Netflix's search returns real matches as you type — if a title from the diff report doesn't
   resolve to a single unambiguous result, stop and flag it back to the parent rather than guessing.
4. Click **Save** (not Cancel) once every change for this profile is made — it's one combined save,
   not per-section.
5. After saving, reload the same settings page and re-read the maturity rating and Title
   Restrictions list to confirm every change actually landed — don't trust the save click alone.

## Known fragility points to re-check on drift
- The slider's stop order and labels (`TV-Y → TV-Y7 → TV-G/G → ...`).
- Whether "Title Restrictions" is still the exact section name and still lives on the same combined
  form as the maturity slider.
- The re-authentication gate's exact trigger conditions (it may not fire identically for every
  account/session state).
