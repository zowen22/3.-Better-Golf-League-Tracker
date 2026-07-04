# "Start Another Season" Wizard + Pre-Season Setup Hub — 2026-07-03

**Type:** Feature (WP-B of the "Start Another Season" pair; requires WP-A `2026-07-03-season-context-nav.md` merged first)
**Status:** Complete — executed as `e0fae00` (2026-07-03), part of WP3.20. Status corrected 2026-07-04 (was left stale as "Open" after execution).
**Priority:** P1 (the user's core "easy new years" ask)
**Prepared by:** Fable, 2026-07-03
**Executor:** Sonnet agent
**Linked WP:** WP3.20

---

## Goal

An admin whose season has ended clicks one prominent **"Start Another Season"** button, fills a short wizard (name prefilled, start date, three carry-over checkboxes), and lands on a **Season Setup hub** of status widgets covering the pre-season chores: roster/teams, player activation, settings, schedule, buy-ins, starting handicaps. Client-facing verbiage is always **"Start Another Season"** — never "copy/clone previous season" (code comments may say clone).

## Context (verified file:line, as of this doc)

- `seasons.create()` `app/routes/seasons.py:27-56` — bare insert (league_id, season_name, start_date, end_date) + app-level dup-name check. Stays as the "start blank" path.
- `league_settings` schema `app/schema_postgres.sql:104-147` — 40 columns. Clone all EXCEPT `setting_id`, `season_id`. Keep `dues_amount` (buy-in usually repeats), set `dues_due_date` to NULL (stale date), keep `show_dues_shame_widget`.
- Teams: season-scoped, `teams.py:62-107` (`add`), form fields `team_name, player1_id, player2_id, division_name`. No delete/bulk routes (and don't add any).
- Players: league-scoped, `players.active` flag (schema `:225`), `deactivate`/`reactivate` routes (`players.py:500,518`). **Known bug to fix here**: `players.py` `delete()` (`:536-597`) guards team membership via `SELECT 1 FROM team_members ...` (`~:566-578`) — that table does not exist (teams store members as `player1_id`/`player2_id`), so on Postgres the guard raises `UndefinedTable` instead of blocking. Replace with a check against `teams` (`WHERE player1_id=%s OR player2_id=%s`, any season, this league) preserving the intended "block delete if ever on a team" behavior and its flash message.
- `admin.seed_handicaps` `app/routes/admin.py:943-1032` — GET preview / POST apply; sets `players.starting_handicap` from each player's most-recent `handicap_history.handicap_index`; reads the player set via `JOIN teams ... WHERE t.season_id=%s`, so **teams must exist in the target season first**.
- `schedule.generate` `app/routes/schedule.py:401-477` — needs ≥2 teams; refuses when matchups exist. Do not modify it; the hub only links to it.
- Dues system is fully built: `app/routes/dues.py` (admin view `:108`, settings upsert `:170`, record `:205` / batch `:248` / delete `:287` payments), `dues_payments` table (schema `:611-621`), paid = ≥1 payment row (`dues.py:73`), eligibility = on a team this season (`dues.py:54-61`). Hub widget links to `dues.admin_dues`; no new dues plumbing.
- "Season over" signal: `matchups.scheduled_date` exists and is used in `main.py:116,127`. No status column on `seasons`.
- Dashboard: admin cards grid `app/templates/dashboard.html:15-132` (`.dash-card` / `.dash-card--admin`, CSS `main.css:1129+`); route `app/routes/main.py:17-442`. Admin post-login landing = `admin.landing` (`admin.py:25-36`) → `admin.panel` (`admin.py:43+`).
- Seasons index `app/routes/seasons.py:8-22` + `app/templates/seasons/index.html` ("+ New Season" link ~line 11).
- After WP-A: `get_current_season_id(db, league_id)` helper exists and pages honor `session['current_season_id']` — the wizard must SET that key to the new season on success so the whole app "moves into" it.

## Scope

### 1. Fix the player-delete guard bug (`players.py:~566-578`)
As described in Context. Small, isolated, do it first.

### 2. `season_is_over(db, season_id)` helper (in `seasons.py`, importable)
True when the season's `MAX(matchups.scheduled_date)` is non-null and `< today`; when the season has no matchups, fall back to `end_date` set and `< today`; else False. Dates are TEXT — compare as ISO strings against `date.today().isoformat()` (consistent with existing code, e.g. `main.py`'s scheduled_date handling; verify format used there and match it).

### 3. Wizard — `GET/POST /seasons/start-next` (admin_required, `seasons.py`)
GET form (`app/templates/seasons/start_next.html`, match existing form styling e.g. `seasons/create.html`):
- `season_name` — prefilled by incrementing the first 4-digit year token in the latest season's name ("2026 Summer Season" → "2027 Summer Season"); blank if no year token.
- `start_date` (required — drives the nav year prefix), `end_date` (optional).
- Checkboxes, all default ON: **Bring over teams & divisions**; **Bring over league settings**; **Seed starting handicaps from current handicaps** (disable via JS + re-check server-side unless teams checkbox is on — hard precondition).
- Brief inline hint per checkbox (one line each) saying what it does; note that players and courses always carry over automatically (league-wide).

POST (single transaction — one `db.commit()` at the end, any exception → `db.rollback()` + error flash + re-render form; the psycopg2 wrapper in `database.py` supports this, same pattern as `_process_scores`):
1. Validate: name non-empty + case-insensitive dup check (reuse `seasons.py:39-42` pattern); start_date non-empty.
2. `INSERT INTO seasons ... RETURNING season_id` (Postgres RETURNING is used elsewhere; if the SQLite dev path matters, mirror how other inserts fetch new ids — check `database.py`'s wrapper for lastrowid handling and copy the established idiom).
3. If settings checked: clone the prior season's `league_settings` row (prior = the season the admin is currently in per `session['current_season_id']`, falling back to newest-before-new). **Explicit column list** — enumerate the 40 schema columns minus `setting_id`/`season_id`, with `dues_due_date` forced NULL. Cross-check the list against `schema_postgres.sql:104-147` AND registered migrations in `init_db.py`'s additive list for any `league_settings` columns added post-schema (as of this doc there are none for league_settings, but verify). If the prior season has NO settings row, skip silently (nothing to clone) and let the hub's Settings card show "pending".
4. If teams checked: `INSERT INTO teams (season_id, league_id, team_name, player1_id, player2_id, division_name) SELECT <new_id>, league_id, team_name, player1_id, player2_id, division_name FROM teams WHERE season_id=<prior> AND league_id=%s`. Copy ALL teams including those with inactive players — the hub Roster card flags those rather than silently dropping them.
5. If seed-handicaps checked (and teams were copied): call the refactored `_seed_starting_handicaps` (see §4).
6. `session['current_season_id'] = new_id`; flash success; redirect to the Setup hub.

### 4. Refactor `admin.seed_handicaps` POST core → `_seed_starting_handicaps(db, league_id, season_id)`
Extract the apply logic (`admin.py:~1000-1032`, the POST branch: latest `handicap_history` per player on a team in `season_id`, `UPDATE players SET starting_handicap=...` only for players with computed history) into a module-level function in `admin.py`; the existing route calls it; the wizard imports and calls it. **Behavior of the existing route must be bit-identical** — pure extraction, no semantic change. Returns a count for the flash/report.

### 5. Season Setup hub — `GET /seasons/<int:season_id>/setup` (admin_required, `seasons.py`; template `app/templates/seasons/setup.html`)
Status widget cards (reuse `.dash-card` / `dashboard-grid` classes from `main.css:1129+` — no new CSS framework; small page-local styles ok):
- **Roster / Teams** — n teams; ⚠ list of copied teams containing a player with `active=0` (name them); links: "+ Add Team" (`teams.add`), season detail (edit links live there).
- **Players** — active count / inactive count; link to `players.roster` (deactivate/reactivate lives there).
- **League Settings** — done if a `league_settings` row exists for this season (link: `admin.settings`); else pending + same link.
- **Schedule** — done if matchups exist (count); else pending + link to `schedule.generate` (mention needs ≥2 teams if teams < 2).
- **Buy-ins / Dues** — pending if `dues_amount`/`dues_due_date` unset; else "n of m paid" (reuse `dues.py:54-73`'s eligibility+paid derivation — import/replicate minimally, do NOT fork the dues math: if reuse requires more than a trivial refactor, link-only with settings-set status and note it); link `dues.admin_dues`.
- **Starting Handicaps** — n of m rostered players with `starting_handicap IS NOT NULL`; link to `admin.seed_handicaps`.
Each card: ✓ done / ○ pending state visual (text badge is fine). Header: "Season Setup — {season_name}".

### 6. CTA placements ("Start Another Season")
- **Dashboard** (`main.py` + `dashboard.html`): when `session['role']=='league_admin'` AND `season_is_over(current season)` → a prominent first admin card linking the wizard. Compute the flag in the dashboard route (one extra query), not in the template.
- **Admin panel** (`admin.py` `panel()` + its template): same condition → banner/button at top. Panel already loads matchups (`admin.py:58+`) — derive from data already in hand if possible.
- **Seasons index** (`seasons/index.html`): "Start Another Season" as the primary button; demote the existing "+ New Season" to a secondary "start a blank season" link (route unchanged).
- **Admin panel, always**: if the current season is NOT over but a newer season exists with incomplete setup (hub has pending cards), show a low-key "Continue season setup" link. Keep this cheap: a single "does the newest season lack matchups or settings" check; skip if it needs >1 extra query beyond what the panel already loads — note it instead.

## Stop Conditions

- [ ] WP-A (`get_current_season_id`, session-honoring pages) is not actually on main — stop, report.
- [ ] The wizard transaction cannot be made atomic with the existing db wrapper (RETURNING/lastrowid or rollback semantics fight you) — stop and report rather than shipping a partial-create path.
- [ ] `league_settings` has live columns beyond the 40 in `schema_postgres.sql:104-147` (check registered migrations) that the explicit clone list would drop — enumerate them in the list too; if a column's meaning makes carrying it over ambiguous, keep the row-clone without it and NOTE it, don't guess.
- [ ] `_seed_starting_handicaps` extraction would change the existing route's behavior in any observable way — stop the refactor, report.
- [ ] The dues paid/eligible derivation can't be reused without forking logic — ship the Buy-ins card as link + settings-set status only, note it.
- [ ] Do NOT build: team delete, team bulk-edit, schedule.generate changes, dues plumbing changes, member-facing hub.

## Definition of Done

- [ ] Player-delete guard fixed (test: deleting a seeded player who's on a team flashes the block message, no 500).
- [ ] Full wizard loop proven via live test-client against the dev DB (`postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev`, CSRF off, session-bypass per `app/seed_dev_db.py:165-169`): run wizard with all boxes checked → assert new season row; settings row cloned (spot-check `handicap_percent`, `scoring_mode` match season 1's row — note: seed a settings row for season 1 first if none exists; `dues_amount` kept, `dues_due_date` NULL); teams copied (same count/pairings, new season_id); `starting_handicap` seeded for players with history; `session['current_season_id']` now the new season; hub renders with Roster ✓ / Settings ✓ / Schedule pending / Handicaps n/m.
- [ ] CTA proof: set all season-1 matchup `scheduled_date`s to the past (or use the new test season with a past-dated matchup) → dashboard + admin panel show the CTA; restore data after. **Clean up ALL test artifacts** (test season + its settings/teams rows) so the dev DB returns to seeded state.
- [ ] `py_compile` clean on all touched .py; Jinja2 parse clean on new/touched templates; no Playwright screenshots (nothing here is a visual-only change; the user's standing no-screenshots instruction applies).
- [ ] Report: what shipped, stop conditions hit (if any), test evidence, anything noted-not-done.

## Critical Files

- `app/routes/seasons.py` (wizard, hub, `season_is_over`), `app/routes/players.py` (delete guard), `app/routes/admin.py` (seed refactor, panel CTA), `app/routes/main.py` (dashboard CTA)
- New: `app/templates/seasons/start_next.html`, `app/templates/seasons/setup.html`
- Touched: `app/templates/seasons/index.html`, `app/templates/dashboard.html`, admin panel template
- Reference-only (no edits): `app/routes/dues.py`, `app/routes/schedule.py`, `app/schema_postgres.sql`
