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

## Real open decisions for Fable (not mine to resolve)

1. **How does a site admin authenticate and see multiple leagues, given every session is pinned to one `league_id`?** Two genuinely different shapes, each a real architectural commitment: (a) a wholly separate login surface/session type for site admins, with its own identity flag (new `users.is_site_admin` or similar) that bypasses the league-scoping decorators entirely; (b) a "super session" mechanism where a flagged user can switch which `league_id` their session is currently scoped to (an impersonation/switch-context pattern) — reuses more of the existing per-league code paths (admin panel, etc.) but is a bigger behavioral change to the session model and a larger security-surface question (impersonating into a league's admin view needs its own audit trail).
2. **Scope of the first version.** A read-only "list of leagues + basic health/usage" view (active leagues, season counts, API usage from `api_request_log`) is a much smaller lift than a dashboard that can also *edit* `platform_settings` ceilings or *act* inside a league on the site admin's behalf. Worth deciding a v1 scope explicitly rather than assuming "cross-league management" means full write access everywhere.
3. **Relationship to the deferred "multi-league user accounts" feature.** Project Overview's Scope explicitly lists "Multi-league user accounts (deferred)" as Out — that's the *user-facing* version of "one identity, many leagues." A site-admin dashboard is the *operator-facing* version of the same underlying problem (an identity that isn't pinned to one league_id). Building the site-admin session-switching mechanism narrowly (site-admin-only, not exposed to regular users) avoids reopening that deferred decision; building it more generally might inadvertently solve both at once, for better or worse. Worth Fable/user explicitly choosing which of these it is, rather than it falling out of implementation details by accident.

## Net for Fable

This is a genuinely foundational feature, not a small addition — the core work isn't UI, it's deciding how a cross-league identity fits into a session model that currently assumes there's no such thing. The `platform_settings` table is real, unused, and would make a strong, low-risk v1 feature (site admin can view/edit platform-wide config ceilings) that doesn't require solving the harder session/identity question first, since a v1 could plausibly live behind a simple, separately-gated route with its own hardcoded check rather than a whole new role system. Recommend that as the concrete starting point if Fable wants a bounded first slice rather than committing to the full cross-league session-switching design in one pass.
