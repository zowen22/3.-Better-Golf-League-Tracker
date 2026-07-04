# Site Admin Dashboard (Cross-League Management) — Investigation for Fable

**Type:** Feature Scoping (pre-design investigation, not an implementation plan)
**Status:** Open — findings ready for Fable to plan from
**Prepared by:** Sonnet, 2026-07-04
**Linked WP:** Backlog item "Site admin dashboard (cross-league management)" (`3. Work Packages.md`, Phase 4: SaaS Pivot)

-----

## Ask

The backlog item was a single unscoped line. This is audit-only groundwork before Fable plans it: what exists today, what's genuinely reusable, and where the real architectural decision points are. No design decisions made here.

## The core architectural fact Fable needs first

**BGLT's session model pins one `session['league_id']` for the life of a login, set once at `auth.py:153/184/191` and never changed.** Every single query, every decorator (`login_required`, `admin_required`), every template, is written against "the current league" implicitly. There is currently **no concept of an identity that spans leagues** — not a role, not a session state, nothing. This is the one fact that shapes every other decision below: a site admin dashboard isn't an additive feature bolted onto the existing admin panel, it's a second, structurally different kind of session.

## What exists today — confirmed by direct code/schema inspection

**Zero cross-league visibility anywhere.** Grepped every `SELECT ... FROM leagues` across the codebase (`auth.py`, `admin.py`, `api.py`, `display.py`, `email_prefs.py`, `player_reg.py`, `public_view.py`) — every single one filters by a specific `league_id`, `login_code`, `api_key`, or `public_slug`. No route anywhere lists all leagues unfiltered. There's no existing "leagues index" page to extend, even an internal/undocumented one.

**No site-admin/platform-admin role concept exists.** `users` table (`schema_postgres.sql:16-24`) has no `is_site_admin`/superuser flag — just name, email, password hash. The only two role names ever inserted or checked anywhere in the codebase are `'league_admin'` and `'member'` (confirmed via grep across `auth.py`/`users.py`), and both are scoped through `user_league_roles.league_id` — i.e., "admin" today always means "admin of one specific league," there's no broader tier.

## Dormant infrastructure that looks purpose-built for this — but is 100% dead code today

Three pieces of schema exist that read like an earlier design pass anticipated exactly this feature, then never finished wiring it up:

1. **`permissions.scope` column** (`schema_postgres.sql:66`, default `'own_league'`) — a `permissions` table exists with `can_read`/`can_write`/`can_delete`/`scope` columns per role, but **none of these columns are ever read anywhere in the app** (confirmed via grep — zero hits outside the `CREATE TABLE` statements in `schema_postgres.sql` and `init_db.py`). The `scope` column defaulting to `'own_league'` implies the schema was designed to support a different scope value (e.g. a future `'all_leagues'` or `'platform'`) — but the enforcement code was never built, and no other scope value has ever been used.
2. **`platform_settings` table** (`schema_postgres.sql:83-93`) — a single global table, **no `league_id` FK at all**, holding feature-flag ceilings that read exactly like a site-admin governance panel's natural first screen: `allow_gross_net_toggle`, `allow_holes_setting`, `allow_handicap_percent_change`, `allow_negative_handicaps`, `max_handicap_index_ceiling`, `allow_playoff_config`, `max_playoff_teams_allowed`, `allow_skins_config`, `allow_absent_player_config`, `allow_custom_points`. **This table is never read anywhere in the app** — no route selects from it, and there's no evidence a row has ever been seeded into it. It's the single most promising reusable piece here: the schema for "site admin sets platform-wide limits on what any league can configure" already exists, just needs a UI and enforcement wired to it.
3. **`user_league_roles`/`roles`** — this one is real and working (used for the individual-accounts dual-auth system), but every read/write is scoped to a specific `(user_id, league_id)` pair. Extending it to a cross-league "site admin" would need either a new role_name that's specially recognized as league_id-independent (a convention, fragile) or a proper new column/table for a platform-level flag on `users` directly (cleaner, but new schema).

**Also adjacent, not dead but not directly reusable:** `api_request_log` (WP6.2's Golf Course API rate-limit tracking) already logs per-league API usage — a natural data source for a "league health/usage" view on a future site-admin dashboard, without needing new schema for that specific piece.

## v1 scope, as directed by @user (2026-07-04)

@user has scoped v1 explicitly: **a read-only dashboard showing API pull counts/status, number of leagues, and number of active leagues** ("stuff like that" — a platform-health overview, not a management/editing surface).

**This significantly de-risks the feature — it does NOT require resolving Open Decision 1 below.** Every piece of data this needs already exists, unfiltered by any single league:

- **Number of leagues / active leagues**: `SELECT COUNT(*) FROM leagues` / `SELECT COUNT(*) FROM leagues WHERE active = 1` — trivial, no new schema.
- **API pull counts/status**: `api_request_log` (`schema_postgres.sql:755-762`: `log_id`, `endpoint`, `league_id`, `user_id`, `response_code`, `requested_at`) already logs every Golf Course API call, per league, with an existing index on `(league_id, requested_at DESC)`. `courses.py`'s `_monthly_request_count(db, league_id)` (`courses.py:94-105`) already implements the exact query shape needed — it currently filters `WHERE league_id = %s` for one league's usage meter (per WP6.2, already shown in the Add Course UI); a platform-wide version is the same query with the league filter dropped and a `GROUP BY league_id` (or `JOIN leagues` for a per-league breakdown table, or omitted entirely for one platform-wide total) — not a rewrite, just a different `WHERE`/`GROUP BY`.

Because this v1 is **read-only and purely aggregate** — it never needs to "become" a specific league's admin or act inside any single league's data — it sidesteps the hard part of Open Decision 1 below entirely. It still needs *some* gate to decide who's allowed to view it (even a minimal one: a new `users.is_site_admin` boolean checked by a single new route-level decorator, no session-switching or identity-model change required). This is a genuinely small, bounded v1: no new schema beyond one boolean flag (or even a hardcoded email/user_id check if a real flag feels like overkill for a single-operator tool), two or three read-only aggregate queries against tables that already exist, and one new template.

## Real open decisions for Fable (still open — v1 above doesn't require resolving these, but future growth of this dashboard will)

1. **How does a site admin authenticate and see multiple leagues for anything beyond read-only aggregates?** The moment this dashboard needs to *act* inside a specific league (edit its settings, view its member list, impersonate its admin) rather than just count rows across all of them, this becomes a real decision: (a) a wholly separate login surface/session type for site admins, with its own identity flag that bypasses league-scoping decorators entirely; (b) a "super session" mechanism where a flagged user can switch which `league_id` their session is currently scoped to (impersonation/switch-context pattern) — reuses more existing per-league code (the admin panel, etc.) but is a bigger behavioral change to the session model and needs its own audit trail. Not needed for the v1 scope above — only relevant once "see status" grows into "manage."
2. **Whether `platform_settings` (the dormant feature-flag-ceiling table) gets wired up as a v2.** Separate from the v1 counts/status ask — a natural next step, but a distinct, larger decision (it's an edit surface, not read-only) than what @user scoped for v1.
3. **Relationship to the deferred "multi-league user accounts" feature.** Project Overview's Scope explicitly lists "Multi-league user accounts (deferred)" as Out — that's the *user-facing* version of "one identity, many leagues." Only becomes relevant if/when this dashboard grows past read-only aggregates into Decision 1 above; irrelevant to the scoped v1.

## Net for Fable

@user has scoped v1 concretely: a read-only platform-health view (league counts, active-league count, API pull counts/status). That version is small and low-risk — no session/identity redesign needed, no new tables beyond possibly one boolean flag, built entirely on existing `leagues`/`api_request_log` data and an existing query pattern (`_monthly_request_count`) that just needs its league filter dropped. The bigger architectural questions (cross-league session identity, wiring up `platform_settings`, the multi-league-accounts relationship) are real and worth Fable tracking for whenever this dashboard is asked to do more than show status — but they're not blocking work for the v1 that's been asked for now.
