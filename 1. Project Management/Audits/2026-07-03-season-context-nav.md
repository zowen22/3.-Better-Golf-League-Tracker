# Season Context Unification + Nav Year Prefix + Role-Pill Alignment — 2026-07-03

**Type:** Refactor + UX fix batch (WP-A of the "Start Another Season" feature pair)
**Status:** Open — execute now
**Priority:** P2 (foundation for WP-B, `2026-07-03-start-another-season.md`)
**Prepared by:** Fable, 2026-07-03
**Executor:** Sonnet agent
**Linked WP:** WP3.20

---

## Goal

Make "current season" mean **the season the user has switched to**, everywhere. Today a season-switcher already exists (nav drawer `<select>` → `/switch-season/<id>` → `session['current_season_id']`), but most page routes ignore the session key and independently recompute "newest season by id" — so switching seasons only changes the dropdown, not the pages. Finish the half-built mechanism, add a year prefix to the league-name headers, and fix the Admin/Member pill vertical alignment.

## Context

- `app/app.py:223` `inject_nav_context()` — context processor that loads `nav_seasons`, maintains `session['current_season_id']` (defaults it to newest if unset), and exposes `nav_season_id` to all templates.
- `app/app.py:300-305` `switch_season(season_id)` — writes the session key, redirects to referrer. Works today.
- `app/templates/base.html:41` — drawer header `<span class="nav-drawer-league">{{ session['league_name'] }}</span>`; `base.html:43` — the season `<select class="nav-drawer-season-select">` (rendered when >1 season).
- `app/templates/dashboard.html:5-10` — page header: `<h1>{{ session['league_name'] }}</h1>` + `<span class="role-badge role-badge--{{ session['role'] }}">`.
- CSS: `.page-header` is defined TWICE — `main.css:189-191` (margin only) and `main.css:1105-1110` (flex, `align-items:center`, gap). `.page-header h1` (`main.css:193-196`) carries `margin-bottom: 8px`, which inside the centered flex row shifts the h1 box up so the pill reads "too low". `.role-badge` family at `main.css:1112-1127`.

## Scope

### 1. Shared current-season helper + route conversion

Add **one** helper — put it in `app/app.py` next to `inject_nav_context()` is fine, but it must be importable by blueprints, so prefer a small function in `database.py` or a new `app/routes/season_context.py`:

```python
def get_current_season_id(db, league_id):
    """The season the user is 'in': session['current_season_id'] if it's a
    real season of THIS league (guards stale ids after league switch),
    else newest by season_id (and write it back to the session)."""
```

Semantics: read `session.get('current_season_id')`; validate via `SELECT season_id FROM seasons WHERE season_id=%s AND league_id=%s`; on miss, fall back to `ORDER BY season_id DESC LIMIT 1`, write the result to `session['current_season_id']`, return it (or `None` if the league has no seasons — callers already handle their own no-season redirects; preserve each site's existing no-season behavior exactly).

Convert these **LIMIT 1 "default season" sites** to call the helper (verified list — line numbers as of this doc):

- `app/routes/main.py:25` (dashboard)
- `app/routes/standings.py:352` (`/current` redirect) and `standings.py:1289`
- `app/routes/schedule.py:253` (`/current` redirect)
- `app/routes/admin.py:30` (`landing()`)
- `app/routes/records.py:33`
- `app/routes/playoffs.py:280`
- `app/routes/skins.py:111`
- `app/routes/my_stats.py:65`
- `app/routes/league_info.py:60`
- `app/routes/display.py:239` — **check first**: if this is an unauthenticated/public display-board route (no login session), it must KEEP newest-by-id; convert only if it runs under a normal logged-in session.
- `app/routes/admin.py:933` and `admin.py:1153` — **check context first**: convert only if they mean "the season the admin is currently working in"; if they genuinely mean "most recent season" (e.g. a default for a season-picker), leave and note.
- `app/routes/courses.py:784` — same check-first rule.

Do **NOT** touch queries without `LIMIT 1` (`ORDER BY season_id DESC` lists at e.g. `standings.py:23`, `admin.py:48`, `stats.py:208`) — those enumerate all seasons for dropdowns and are correct as-is. Do not touch `api.py`'s `_current_season()` (mobile JWT flow, no browser session) or `public_view.py` (public, no session).

Also update `inject_nav_context()` itself to use the same helper (single source of truth) rather than keeping its own inline copy of the default-to-newest logic.

### 2. Year prefix on league-name headers

In `inject_nav_context()`, compute `nav_season_year` for the current season: first 4 chars of `start_date` if they match `^\d{4}`, else the first standalone 4-digit token (19xx/20xx) in `season_name`, else `None`. Expose it alongside the existing nav context vars.

Render as a prefix wherever the league name is a header:
- Drawer header (`base.html:41`): `2026 · Shankapotamus Golf League` (skip prefix cleanly when `nav_season_year` is None).
- Dashboard page header (`dashboard.html:6`): same treatment.
- Relabel the drawer season control: give the `<select>` an adjacent/visible label reading **"Switch Season"** (today it's an unlabeled dropdown). Keep it a select — do not rebuild the control.

### 3. Role-pill vertical alignment

- Merge the duplicate `.page-header` blocks (`main.css:189-191` + `main.css:1105-1110`) into one definition (keep the flex version's behavior + the margin-bottom from the first).
- Fix the misalignment: `.page-header h1`'s `margin-bottom: 8px` inside the `align-items:center` flex row is the cause. Zero it in the page-header context (keep any standalone-h1 spacing intact if used elsewhere — grep `.page-header` across templates first to see every page that uses it and confirm none rely on that margin for stacked layouts; `.page-header p` at `main.css:198` suggests some pages stack a subtitle under the h1 — if so, scope the fix so subtitle layouts don't collapse, e.g. keep vertical rhythm via the flex gap or `row-gap` instead of h1 margin).

## Stop Conditions

- [ ] A LIMIT-1 site turns out to mean "most recent season" rather than "the season the user is in" (candidates flagged above: `admin.py:933`, `admin.py:1153`, `courses.py:784`, `display.py:239`) — leave that site unchanged and note it in your report; do not force-fit.
- [ ] `display.py` (or any converted route) runs without a login session — do not convert it.
- [ ] The `.page-header` margin fix visibly breaks any page that stacks content under the h1 — stop CSS-guessing, report the conflicting page(s) instead of shipping a regression.
- [ ] `get_current_season_id()` can't be placed anywhere importable without a circular import — report rather than duplicating the logic per-blueprint.

## Definition of Done

- [ ] One shared helper; all converted sites call it; `inject_nav_context()` uses it too.
- [ ] Live test-client proof: with two seasons present, `GET /switch-season/1` then dashboard + standings/current + schedule/current + records all render **season 1** content while season 2 exists and is newer. (Create a temp second season for the test; delete it after — same pattern as `Audits/2026-07-03-league-creation-new-season-audit.md`'s verification. Dev DB: `postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev`, CSRF off via `app.config['WTF_CSRF_ENABLED']=False`, session-bypass login per `app/seed_dev_db.py:165-169`.)
- [ ] Year prefix renders in drawer + dashboard header; absent cleanly when no year derivable.
- [ ] "Switch Season" label present.
- [ ] Pill fix: one Playwright screenshot pair (desktop + ~390px mobile) of the dashboard header confirming h1/pill vertical centering — this is the ONLY screenshot allowed (user's standing instruction: no screenshots unless genuinely needed for visual confirmation; this is a visual fix). Chromium at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`; set a known admin password hash in the dev DB first if logging in via UI (see Session Log 2026-07-03 local-dev entry).
- [ ] `python3 -m py_compile` clean on every touched route file; Jinja2 parse clean on touched templates; CSS brace balance check on `main.css`.
- [ ] Report: files touched, sites converted vs. left (with reasons), test evidence summary.

## Out of scope — do not touch

- The "Start Another Season" wizard/hub (WP-B, separate doc).
- `api.py` / `public_view.py` season resolution.
- Rebuilding the season switcher UI beyond the label.
- Any scoring/handicap logic.

## Critical Files

- `app/app.py` (`inject_nav_context`, `switch_season`), helper home (`database.py` or new `app/routes/season_context.py`)
- Route files listed in Scope §1
- `app/templates/base.html`, `app/templates/dashboard.html`
- `app/static/css/main.css` (`.page-header` ~189/1105, `.role-badge` ~1112)
