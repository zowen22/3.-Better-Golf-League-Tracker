# Handoff: Site Admin Dashboard v1 (read-only platform health)

*Status: `Done`*
*Created: 2026-07-06 — Planner: Opus (this session)*
*Priority: `Medium` — Effort: `M`*
*Depends on: None*
*Parallel-safe: `Yes` — Critical Files disjoint from the `max_score_over_handicap` handoff (that one touches only `handicap.py`).*

-----

## Goal

A logged-in **site admin** (platform operator, i.e. you) can open a single read-only page and see platform-wide health at a glance: how many leagues exist, how many are active, and Golf Course API usage/error status across all leagues. No editing, no cross-league impersonation, no session-model change — just aggregate counts over data that already exists.

## Context

BGLT is a single-app, multi-league system. Today every route, decorator, query, and template is implicitly scoped to `session['league_id']` — there is **no identity that spans leagues** and no page anywhere that lists all leagues unfiltered (confirmed in the investigation doc). @user scoped a v1 explicitly: a **read-only** platform-health overview, nothing that acts inside a specific league. That read-only constraint is what makes this small and safe — it sidesteps the hard "how does a cross-league admin session work" question entirely, because this page never becomes a league's admin, it just counts rows across all of them.

Full background: `1. Project Management/Audits/2026-07-04-site-admin-dashboard-investigation.md`. Read it — it explains why the dormant `platform_settings`/`permissions.scope` schema is deliberately **out** of scope for v1 (that's a v2 edit-surface decision).

## Findings / Evidence

- **No site-admin concept exists.** `users` table (`schema_postgres.sql:16-24`) has only `user_id, first_name, last_name, email, password_hash, created_date, active` — no superuser flag. The only role names anywhere are `'league_admin'`/`'member'`, always scoped through `user_league_roles.league_id`. Verified via grep.
- **Two login flows, only one carries a user identity** (`routes/auth.py`):
  - Individual-account login (lines 148-158) sets `session['user_id']`, `session['league_id']`, `session['role']`, `session['user_display_name']`.
  - Shared league-password login (lines 184-193) sets `session['league_id']` + `session['role']` but **no `session['user_id']`** (it's a shared password, no individual identity).
  - **Consequence the gate relies on:** a site admin must sign in with an individual account (email + password). The gate keys off `users.is_site_admin` for `session['user_id']`. Someone on the shared league password simply has no `user_id` and therefore can't be a site admin — correct and intended.
- **All data needed already exists, unfiltered:**
  - League counts: `SELECT COUNT(*) FROM leagues` and `... WHERE active = 1` (`leagues.active INTEGER DEFAULT 1`, `schema_postgres.sql`).
  - API usage/status: `api_request_log(log_id, endpoint, league_id, user_id, response_code, requested_at TIMESTAMPTZ)` (`schema_postgres.sql`). Existing index on `(league_id, requested_at DESC)`. The existing per-league query pattern is `courses.py`'s `_monthly_request_count(db, league_id)` (~lines 94-105) — the platform version is the same shape with the league filter dropped and/or a `GROUP BY league_id`.
- **`admin_required`** (`routes/auth.py`) checks `session.get('role') != 'league_admin'`. Do **not** reuse it — it's league-scoped and would let any league admin in. A new `site_admin_required` decorator is required.

## Scope

### In

1. One migration adding `users.is_site_admin INTEGER NOT NULL DEFAULT 0`.
2. A `site_admin_required` decorator (in `routes/auth.py`, next to `admin_required`).
3. A new blueprint `routes/site_admin.py` with one route, `GET /site-admin`, rendering read-only aggregates.
4. One template `templates/site_admin/dashboard.html`.
5. Blueprint registration in `app.py`.
6. A nav entry to reach the page, shown **only** to site admins.
7. The **metrics floor** (@user-specified, must appear): total leagues; active leagues; Golf Course API pull counts + status (at minimum: calls this calendar month platform-wide, and a 2xx-vs-4xx/5xx success/error breakdown from `response_code`).

### Out — deliberately left alone

- **`platform_settings` and `permissions.scope`** — the dormant feature-flag-ceiling schema. It's a v2 *edit* surface, explicitly deferred by @user. Do not wire it up, do not seed it.
- **Any cross-league *action*** — no editing a league, no viewing a league's member list, no impersonation/context-switch. Read-only aggregates only. If you find yourself adding a link that drills into a specific league's admin data, stop (see Stop Conditions).
- **Any change to the existing league-scoped `admin_required` decorator or the login flows.** Add alongside; don't modify.
- **A site-admin management UI** (creating other site admins, a users list). For v1 the flag is set manually in the DB by @user. Do not build a UI to toggle it.
- **iOS / API-v1 exposure.** Web only.

### Metrics beyond the floor — your judgment (from the investigation, offered not required)

@user said the 3 named metrics are the floor, not the ceiling, and gave latitude to add what a platform operator would actually want. Cheap-from-existing-data candidates: most-recently-created leagues (onboarding funnel, `leagues.created_date`); count of inactive leagues (`active = 0`, churn); total players/teams/seasons platform-wide; most-recent API error rows. Add a few if they're genuinely useful and cheap; don't gold-plate.

## Implementation Plan

1. **Migration.** Create `app/migrations/add_site_admin_flag.sql`:
   `ALTER TABLE users ADD COLUMN IF NOT EXISTS is_site_admin INTEGER NOT NULL DEFAULT 0;`
   Register it in the additive-migration list (`app/init_db.py` — follow the exact pattern the other `add_*.sql` files use; grep `init_db.py` for a recent one like `add_dashboard_widget_visibility.sql` and mirror it). Also add the column to the `users` `CREATE TABLE` in `schema_postgres.sql` so fresh deploys have it.
2. **Decorator.** In `routes/auth.py`, add `site_admin_required(view)` modeled on `admin_required` but: require `session.get('user_id')`; look up `SELECT is_site_admin FROM users WHERE user_id = %s`; allow only if truthy; otherwise flash + redirect to `main.dashboard` (or `auth.login` if not logged in at all). Keep it dependency-light and consistent with the existing decorator style (`functools.wraps`, `get_db()`).
3. **Blueprint.** Create `routes/site_admin.py`: `bp = Blueprint('site_admin', __name__, url_prefix='/site-admin')`, one `@bp.route('/')` `@site_admin_required` `def dashboard():` that runs the aggregate queries and renders the template. Keep queries simple and read-only. Model the API-usage query on `courses.py:_monthly_request_count` but without the `league_id` filter.
4. **Register** the blueprint in `app.py` (mirror how the other blueprints, e.g. `wiki`, are imported + registered — grep `app.py` for `register_blueprint`).
5. **Template** `templates/site_admin/dashboard.html`: extend `base.html`, a clean stat-tile grid for the headline counts + a small table for per-league API usage or recent errors. Match existing dashboard/stat styling already in the app (reuse existing CSS classes — grep templates for `stat` tiles used elsewhere; do not invent a new design system).
6. **Nav link**, site-admin-only. The session doesn't currently carry `is_site_admin`. Cleanest: set `session['is_site_admin'] = bool(user_row...)` at individual-account login time in `auth.py` (line ~156 area) so templates can gate on `session.get('is_site_admin')` without a per-request query. Add the nav link in `base.html` guarded by `{% if session.get('is_site_admin') %}`. (If you prefer not to touch login, expose it via a context processor — but the session key is simplest and matches how `role`/`league_name` are already handled.)
7. **Validate** (see Definition of Done) against the real dev Postgres DB.

## Stop Conditions

- **If v1 read-only starts requiring cross-league session/identity changes** (e.g. you conclude you need to switch `session['league_id']` or bypass league-scoping decorators to make a metric work) — stop, mark `Blocked`. The whole point of v1 is that it does NOT need that. Aggregates over `leagues`/`api_request_log` never need a league-scoped session.
- **If wiring a metric would require `platform_settings`/`permissions.scope`** — that's out of scope; either drop the metric or stop and ask.
- **If the dev DB has zero individual-account users** (so you can't set/exercise `is_site_admin`) — you may create a test user + set the flag in the dev DB to validate, but restore the dev DB to its prior state afterward (this project's convention: validate against real data, leave it as you found it). Do not hardcode an email/user_id gate as a shortcut.
- **If you're tempted to add a site-admin management UI or wire the flag into anything beyond this one page** — don't; log it as a follow-up.

## Definition of Done

- [ ] Migration file created + registered in `init_db.py` + column added to `schema_postgres.sql`; running the app against the dev DB applies it cleanly (idempotent — `ADD COLUMN IF NOT EXISTS`).
- [ ] `GET /site-admin` returns 200 for a user with `is_site_admin=1` and correctly redirects (not 200) for: a logged-out visitor, a shared-league-password admin (no `user_id`), and an individual-account user with `is_site_admin=0`. Verify all four via the Flask test client against the real dev Postgres DB.
- [ ] The three floor metrics render with correct values (cross-check counts against direct `psql` queries).
- [ ] Nav link appears only when `session.get('is_site_admin')` is set; absent for normal admins/members.
- [ ] `python -m py_compile` clean on all touched `.py`; the new template parses through the real `app.jinja_env`.
- [ ] Dev DB left in its pre-validation state (any test user/flag you added is removed).
- [ ] Execution Report below filled in.
- [ ] Status updated to `Done`.

## Build/verify conventions for this repo (a cold session won't know these)

- Dev DB: `postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev` (already running locally). Use the project venv: `/home/user/BetterGolfLeagueTracker/.venv/bin/python3`.
- App factory: `from app import create_app` with `DATABASE_URL` env var set to the dev DB; `create_app()`; use `app.test_client()` + `client.session_transaction()` to set session keys (`user_id`, `league_id`, `role`, `is_site_admin`) for auth'd requests.
- **Build directly on `main`** (the whole repo works on `main` per @user's standing preference and `.claude/settings.json`). **Commit locally but DO NOT push** — the Planner reviews before anything ships, and @user runs the migration on Supabase before the push. Leave the commit unpushed and note its SHA in the Execution Report.
- Match commit-author config already in the repo (`git config user.email noreply@anthropic.com` / `user.name Claude`) so the commit isn't flagged Unverified.

## Critical Files

| File | Why |
|------|-----|
| `app/migrations/add_site_admin_flag.sql` | New — the `is_site_admin` column |
| `app/init_db.py` | Register the new migration in the additive list |
| `app/schema_postgres.sql` | Add `is_site_admin` to `users` for fresh deploys |
| `app/routes/auth.py` | New `site_admin_required` decorator; set `session['is_site_admin']` at individual login |
| `app/routes/site_admin.py` | New — blueprint + `/site-admin` route + aggregate queries |
| `app/templates/site_admin/dashboard.html` | New — the read-only dashboard |
| `app/app.py` | Register the new blueprint |
| `app/templates/base.html` | Site-admin-only nav link |
| `app/routes/courses.py` | Reference only — `_monthly_request_count` query pattern to model the API-usage query on |

-----

## Execution Report

*Executed: 2026-07-08 — Executor: Sonnet 5 (cold executor session)*

**Commit:** `9fee9dc` on `main`, local only — not pushed (per instructions; Planner reviews and @user runs the Supabase migration first).

### What Was Done

- `app/migrations/add_site_admin_flag.sql` (new): `ALTER TABLE users ADD COLUMN IF NOT EXISTS is_site_admin INTEGER NOT NULL DEFAULT 0;`
- `app/init_db.py`: registered `add_site_admin_flag.sql` in the additive-migration list.
- `app/schema_postgres.sql`: added `is_site_admin INTEGER NOT NULL DEFAULT 0` to the `users` `CREATE TABLE` for fresh deploys.
- `app/routes/auth.py`: added `site_admin_required(view)` decorator next to `admin_required` (requires `session['user_id']`, looks up `users.is_site_admin`, redirects to `auth.login` if not logged in at all or `main.dashboard` if logged in but not a site admin). Also set `session['is_site_admin'] = bool(user['is_site_admin'])` at individual-account login (auth.py login route, `login_type == 'user'` branch), alongside the other session keys already set there. `admin_required` and the login flows themselves were not modified.
- `app/routes/site_admin.py` (new): blueprint `site_admin` at `/site-admin`, one route `GET /` (`dashboard`) gated by `site_admin_required`. Queries: total/active/inactive league counts; total players/teams/seasons platform-wide; this-month platform-wide Golf Course API call count (same query shape as `courses.py::_monthly_request_count`, league filter dropped); 2xx vs. error breakdown from `response_code`; per-league this-month API usage table; 10 most recent API errors (non-2xx); 5 most-recently-created leagues.
- `app/templates/site_admin/dashboard.html` (new): extends `base.html`; reuses existing `profile-stat-grid`/`profile-stat-card`, `card-section`, `data-table`, and `profile-badge--inactive` classes — no new CSS added.
- `app/app.py`: imported and registered the `site_admin` blueprint (mirrors the `wiki` blueprint pattern).
- `app/templates/base.html`: added a nav-drawer link to `/site-admin` guarded by `{% if session.get('is_site_admin') %}`, placed above the league-scoped groups.

### Validation Performed (against real dev Postgres DB, per Definition of Done)

- `python -m py_compile` clean on `routes/auth.py`, `routes/site_admin.py`, `app.py`, `init_db.py`.
- Ran `create_app()` against `DATABASE_URL=postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev` — migration applied cleanly; confirmed via `psql \d users` that `is_site_admin` column now exists. Re-running is idempotent (`ADD COLUMN IF NOT EXISTS`).
- Dev DB had **zero individual-account users** (Stop Condition case) — created two temporary test users (`is_site_admin=1` and `is_site_admin=0`) and 4 temporary `api_request_log` rows (2× 200, 1× 404, 1× 500) to exercise the metrics, per the Stop Condition's explicit allowance.
- Used Flask `test_client()` + `session_transaction()` to hit `GET /site-admin/` under all four required scenarios — all passed:
  - Logged-out visitor → 302 to `/login`
  - Shared-league-password admin (`role=league_admin`, no `user_id`) → 302 to `/login`
  - Individual-account user, `is_site_admin=0` → 302 to `/dashboard`
  - Individual-account user, `is_site_admin=1` → 200, page rendered (confirms template parses through the real `app.jinja_env`)
- Cross-checked all rendered metrics against direct `psql` queries — exact match: total leagues 1, active 1, inactive 0, players 21, teams 10, seasons 1, monthly API calls 4, success 2, error 2, per-league table and recent-errors table content matched the inserted rows, recently-created-leagues table showed the one seeded league.
- Confirmed the nav link is absent for a plain member session and for a `league_admin` (shared-password) session (grepped rendered HTML for "Site Admin" — not present in either).
- Cleaned up: deleted both temporary users and all 4 temporary `api_request_log` rows. `users` and `api_request_log` tables are back to 0 rows each, matching the pre-validation state.

### Deviations from Plan

- None. Implementation followed the plan as scoped; no cross-league session changes, no `platform_settings`/`permissions.scope` wiring, no site-admin management UI.
- Left `handicap.py` untouched throughout — confirmed at commit time that the concurrent executor's in-progress changes to that file were present in the working tree but not staged/committed by this session.

### Follow-ups Discovered

- None beyond what's already tracked in the investigation doc's "Real open decisions" section (cross-league session identity, `platform_settings` wiring, multi-league accounts) — all explicitly out of scope for v1.
