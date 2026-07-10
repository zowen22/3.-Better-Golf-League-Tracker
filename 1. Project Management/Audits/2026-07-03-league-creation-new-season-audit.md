# League Creation & New-Season ("New Year") Experience Audit — 2026-07-03

**Type:** Audit (bugs fixed same-session; feature recommendations pending priority call)
**Status:** Complete. Bugs fixed same-session. Recommendations #1–#3 (copy-from-previous-season, setup checklist, default-settings-on-create question) resolved via WP3.20 "Season Rollover & Pre-Season Setup" (2026-07-03). Recommendation #4 (minor validation gaps) fixed 2026-07-10 — see below.
**Priority:** P1 (bugs, silent wrong data), P2/P3 (feature recommendations)
**Prepared by:** Sonnet, 2026-07-03
**Linked WP:** WP3.1 (backlog item "Audit league creation process," added 2026-07-03)

---

## Goal

Audit the two flows that make up "creating and running a league": (1) the one-time initial league signup, and (2) the recurring annual "start a new season" workflow an existing admin repeats every year. The user's ask was specifically about making the **annual "new year" rollover** good, easy, and simple — this audit treats that as the primary lens, with the one-time signup flow covered for completeness since it feeds directly into the same setup burden.

## Context

Traced both flows end-to-end via direct code reading (two Explore agents, cross-verified against the actual source afterward — every finding below was independently confirmed by reading the exact file:line, not just agent-reported).

This extends an already-documented gap (Technical Reference: `seasons.create()` never inserts a `league_settings` row, previously only known to break the handicap-rebuild engine) and found **two further, previously-unknown downstream bugs** caused by that same root gap, plus a clear picture of why the annual rollover is currently tedious.

### Bugs found and fixed this session

1. **`get_league_settings(db, season_id, league_id)`** (`app/routes/scores.py:146`) was called with **arguments swapped** at two sites — `app/routes/admin.py:163` (inside `panel()`, the admin panel's playing-handicap display) and `app/routes/schedule.py:2022` (inside `week_scorecards()`). Since the query is `WHERE season_id = %s AND league_id = %s`, both call sites passed the IDs in the wrong slots. This only "worked" by coincidence for a league's very first season (where `league_id == season_id`) — for any second+ season, both call sites silently got `None` back and fell through to hardcoded defaults (100% handicap, max 36, match_play) instead of the league's actual configured settings, with no error surfaced anywhere. **Fixed**: both call sites now pass `(db, season_id, league_id)` in the correct order. Confirmed no other call site in the codebase has this bug (all other ~15 call sites already pass the args correctly).

2. **`schedule.py:_get_single_course()`** (`schedule.py:15-30`) treated a **missing** `league_settings` row identically to `multi_course=1` (`if not ls or ls['multi_course']: return None, None`). Since a brand-new season has no `league_settings` row until the admin's first Settings save (see gap #3), generating a schedule before that first save gave every matchup `course_id=NULL, tee_id=NULL` — silently, even for a genuinely single-course league — and nothing retroactively fixed already-generated matchups once Settings was later saved. **Fixed**: a missing row is now treated the same as `multi_course=0` (its actual schema/UI default), matching the precedent already set by this session's earlier handicap-rebuild fix (fall back to sane defaults, don't silently null out).

3. **Root gap (already known, confirmed still present)**: `seasons.create()` (`seasons.py:48-51`) inserts only into `seasons` — no `league_settings` row. Bugs 1 and 2 are direct downstream consequences of this same gap, in addition to the already-fixed handicap-rebuild instance from earlier this session. **Deliberately left unfixed in this pass** — see Recommendations below for why.

Both fixes verified: `py_compile` clean, and a live Flask test-client reproduction against the local seeded dev DB — created a second season (`season_id=2, league_id=1`, so the two IDs differ), confirmed `get_league_settings(db, 2, 1)` now correctly reads a season-specific settings row instead of returning `None`, and confirmed `_get_single_course(db, 2, 1)` with no settings row present correctly resolves the league's real course instead of `(None, None)`.

### Why the annual "new year" rollover is tedious

- **Already good**: `players`, `courses`, `tees` are league-scoped (not season-scoped) — these already persist automatically year to year with zero extra admin work.
- **The actual pain point**: `teams` and `league_settings` are season-scoped and start **completely blank** every year, with **no copy/clone tooling anywhere in the codebase** (confirmed — no clone/copy/carryover code exists). Every year, an admin must manually re-pair every team from scratch (`teams.add()`, one at a time) and manually re-enter every league setting (handicap %, scoring mode, playoff format, absence policy, etc.) — the Settings page's GET pre-fills from hardcoded schema defaults (`admin.py`'s `_SETTINGS_DEFAULTS`), never from the prior season's actual saved values.
- `admin.seed_handicaps()` exists as a "new season" helper but only works *after* teams are already re-added (it joins through `teams` to find the current season's players) — it doesn't reduce the roster-recreation tedium itself, just handles handicap carryover once rosters exist.
- Neither `create_league.html` nor `seasons/create.html` gives any indication of what will/won't carry over, or what comes next. A brand-new admin who just signed up is bounced straight to a bare "Create a season first" flash with zero guidance on the ~6 setup steps required (season → course/tees → players → teams → settings → schedule) before any match week can run.
- Minor, lower-priority validation gaps noted in passing: `league_name` has no DB-level uniqueness constraint (app-level check only, TOCTOU race possible); no password-strength requirement on league admin/member passwords (contrast: the separate personal-account `register()` flow requires ≥6 chars); `season_name` duplicate check is also app-level only.

## Recommendations (not built this session — need a priority/scope call)

These are real product decisions, not bug fixes, so they weren't built silently:

1. **"Copy from previous season" action** — the highest-leverage single feature for this ask. On season-create (or as a follow-up action from the new season's detail page), offer to clone the most recent prior season's `teams` rows (pairings + division names, re-pointed at the new `season_id`) and its `league_settings` row into the new season — both fully editable afterward, nothing locked in. This alone would take the annual rollover from "rebuild everything by hand" to "review and adjust what carried over," which is the core of what "easy, simple new years" means in practice.
2. **Post-signup / empty-season setup checklist** — a short, in-app checklist shown on the create-league success page and/or the empty dashboard, listing the concrete next steps (add a course, add players, add teams, configure settings, build a schedule) with direct links, instead of the current bare "Create a season first" flash.
3. **Should `seasons.create()` write a default `league_settings` row automatically?** This is the actual root-gap question, and it's a real tradeoff, not a bug: writing defaults automatically closes gaps like #1/#2 above at the source, but means every new season silently gets specific numeric defaults (100%/36/match_play-equivalent) baked into the DB before an admin has looked at Settings, which could itself surprise someone who assumed "unconfigured" meant "will prompt me." Recommend deciding this alongside recommendation #1 — if "copy from previous season" ships, it makes this question largely moot (the new season would get the *prior* season's real settings, not hardcoded defaults, either way).
4. ~~Minor: add a DB-level `UNIQUE` constraint on `league_name` (or an app-level lock/transaction) and a password-strength requirement matching `register()`'s ≥6-char rule, applied to league admin/member passwords too.~~ **Fixed 2026-07-10**: case-insensitive `UNIQUE` index (`ux_leagues_league_name_ci`, matches the app's existing `LOWER()` comparison) added to `schema_postgres.sql` + standalone `migrations/add_league_name_unique.sql` for already-existing DBs (applied to dev Postgres, needs a production Supabase run — same as the other outstanding migrations). Admin/member passwords in `create_league()` now require ≥6 characters, matching `register()`'s existing rule exactly. Validated via Flask test client against real dev Postgres: case-insensitive duplicate rejected, both short-password cases rejected with the correct message, valid creation still succeeds.

## Critical Files

- `app/routes/admin.py:163` (fixed), `app/routes/schedule.py:15-30, 2022` (fixed)
- `app/routes/seasons.py:25-56` (`create()` — root gap, not touched this pass)
- `app/routes/auth.py:37-102` (`create_league()` — signup flow)
- `app/routes/teams.py:62-107` (`teams.add()` — no bulk/clone path)
- `app/routes/admin.py:386-424, 429` (`_SETTINGS_DEFAULTS`, `settings()` — GET pre-fills from hardcoded defaults, not prior season)
- `app/templates/create_league.html`, `app/templates/seasons/create.html`, `app/templates/seasons/detail.html`
- `1. Project Management/4. Technical Reference.md` (existing gap note, extended)
