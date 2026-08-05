# Prime Video — supervised settings adapter

**Status: verified live 2026-08-05** against a real account (4 profiles, one flagged as a Kids
profile with its own PIN). Corrected from an earlier version written off Amazon's public docs
alone — the real architecture is meaningfully different from Netflix's, in ways that limit what
"apply" can actually guarantee. Read the limitation below before trusting this in apply mode.

## What Prime Video actually supports — and a real limitation to be upfront about

Prime Video's parental-control surface is split across three places, not one combined form like
Netflix:

1. **Account & Settings → Permissions** (`primevideo.com/settings/profile`, Permissions tab; real
   URL lands at `/region/na/settings/parental-controls`). This is an **account+device-wide** age-band
   restriction (`all` / `7+` / `13+` / `16+` / `18+`) — the page states outright: "Viewing
   restrictions apply across all profiles on the devices selected below." **This is not a per-kid
   setting.** Turning it down affects every profile on the selected device(s), including adult
   profiles. Do not adjust this as a substitute for per-kid control — it's a household/device gate,
   analogous to setting a maturity ceiling on a shared TV, not on a specific kid's profile. Requires
   a full Amazon re-authentication (sign-in, not just a code) to reach.
2. **Manage Profiles → [Kids profile] → PIN gate**. The Kids profile itself is PIN-locked
   separately from the account-wide PIN (a "Kids Profile PIN", distinct from the "Prime Video
   Account PIN" which bypasses everything). Entering it lands in a genuinely simplified storefront
   (`/region/na/storefront/kids` — nav reduced to Home/Movies/TV shows only, no Sports/News/Live
   TV) that shows a built-in per-title age badge (e.g. "Age 8+ PG", "Age 6+ TV-Y7") on every title.
3. **Account & Settings → Hidden videos** (`primevideo.com/settings/hidden-history`). This **is**
   genuinely per-profile — the page states "Each profile has its own list" — and is the closest
   analog to Netflix's Title Restrictions. **But it is materially weaker**: the page says outright
   "We'll keep these videos out of future recommendations, but they'll still appear in search
   results." A hidden title is suppressed from browse/recommendation rows only — a kid who searches
   for it by name will still find and can still watch it. This is not a real block, and `diff_report`
   output applied here should never be represented to a parent as equivalent to a Netflix-style
   block. Say so explicitly when reporting an applied Prime Video diff.

**Bottom line for this skill:** Prime Video's `to_block` mechanism (Hidden videos) reduces
*passive discovery* risk, not *deliberate search* risk. Netflix's Title Restrictions genuinely block
regardless of how the title is found; Prime Video's does not. This is a real capability gap between
platforms, not a bug in this skill — report it as such rather than presenting both platforms'
"blocked" state with equal confidence.

## Discover step (read-only)

1. Switch to the Kids profile (PIN entered by the parent themselves, same rule as every other
   platform-lock/PIN in this repo).
2. Read the built-in per-title age badge shown on each title in the Kids storefront's rows — this
   is a useful extra ground-truth signal Netflix doesn't surface as directly.
3. Browse the Kids storefront's rows/categories and use search, same as the Netflix adapter — the
   built-in age badge is not a substitute for reading themes/pacing against the family rubric, for
   the same reason established on Netflix (a kid-safe badge doesn't mean pacing/theme-appropriate).
4. Read the existing Hidden videos list (`primevideo.com/settings/hidden-history`, while the Kids
   profile is active) as the "before" state.
5. Do **not** read or rely on the account-wide Permissions age-band as a per-kid signal — it's not
   scoped to this profile.

## Apply step (writes — supervised only)

Only after the parent has reviewed `diff_report.py`'s output and approved it — **and has been told
about the search-bypass limitation above for this platform specifically**:

1. **The hide control**: hover a title's tile until it expands into a preview card (takes ~1-2
   seconds — a quick hover isn't enough, the icon row renders after the card fully expands). A
   circle-slash icon appears next to the Play/Resume and "+" (watchlist) icons. Click it, then
   confirm the toast that appears: *"Hiding this movie/season, but you can still search for it."*
   That toast text is the platform's own confirmation the hide actually applied — treat its absence
   as a failed action, not just the click event.
2. **This icon is only available on personalized recommendation rows (e.g. "Watch next — Kids"),
   confirmed NOT to appear on**: the title's own detail page, editorial/chart rows (e.g. "Top 10 for
   Kids"), or search results — checked all three live and none exposed a hide control. **If a title
   in `to_block` only appears in a chart/search context and not in a "Watch next"-style row, there
   may currently be no way to hide it via this UI at all.** Tell the parent this explicitly rather
   than silently skipping it — it's a real platform gap, not a step you failed to find.
3. There is no centralized "add a title to the hidden list by name" search field — hiding is only
   ever a per-tile action from wherever the title happens to be surfaced.
4. Verify no account-wide setting (Permissions tab) is being touched — that's out of scope for a
   per-kid apply and affects other profiles.
5. After hiding, reload `primevideo.com/settings/hidden-history` while still on the Kids profile and
   re-read the list to confirm the title actually landed — don't trust a successful-looking toast
   alone (confirmed reliable in practice, but re-check anyway, same discipline as every other
   platform in this repo).

## If the platform has no Kids profile yet

Same principle as Netflix: offer to help create one via "Manage Profiles → Add new", mark it as a
Kids profile, set its PIN, and confirm its name with the parent before adding it to
`family-profile.json`'s `platform_profiles`. Given only one "Kids" profile existed on the account
this was verified against — not one per child — check with the parent whether multiple kids of
different ages will share it (if so, `rubric_engine.reconcile_kids_sharing_profile()` applies here
exactly as it does for a shared Netflix profile) or whether separate Kids profiles should be created
per child instead.

## Known fragility points to re-check on drift
- Whether a centralized "add a title to the hidden list by name" form exists (it didn't at
  verification time — hiding is only a per-tile hover action on specific row types).
- **Which rows expose the hide icon.** Confirmed live: "Watch next — Kids" does, "Top 10 for Kids"
  and search results don't, the detail page doesn't. This split isn't documented by Amazon anywhere
  found — it was reverse-engineered by checking each surface directly, and could change without
  notice. Re-verify row-by-row before assuming any specific row supports hiding.
- Whether "Hidden videos" ever becomes a true block (search-inclusive) rather than
  recommendations-only — re-read its own description text on the settings page before assuming
  either way.
- The exact Permissions-tab re-authentication trigger (full sign-in was required once this
  session; may not repeat identically every time).
