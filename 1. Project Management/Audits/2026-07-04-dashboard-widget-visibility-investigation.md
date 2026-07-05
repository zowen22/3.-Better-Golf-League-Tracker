# Admin Control Over Member Dashboard Widgets — Investigation for Fable

**Type:** Feature Scoping (pre-design investigation, not an implementation plan)
**Status:** Open — findings ready for Fable to plan from
**Prepared by:** Sonnet, 2026-07-04
**Linked WP:** Backlog item "Admin control over what shows on members' dashboards" (`3. Work Packages.md`, added 2026-07-03)

-----

## Ask

Backlog item (from an earlier session's investigation) established this doesn't exist today, but was never written up as a proper scoping doc — just a one-line confirmation. This does that: full widget inventory, the existing (single-purpose) precedent, and what a real per-widget system would need. Scope is member-facing dashboard only, per the backlog wording ("what shows on members' dashboards") — the admin-view dashboard (nav tiles, admin-only CTAs) is not part of this ask.

## Current state: exactly one real precedent, and it's single-purpose

`app/templates/dashboard.html` is one monolithic template with a hardcoded top-level branch (`{% if session['role'] == 'league_admin' %}` at line 12) between an admin view (nav tiles + widgets) and a member view (widgets only, nav tiles moved to the hamburger menu). Within the member view, there are **exactly 5 distinct widgets**, identified by the template's own section-comment labels (`dashboard.html:144,162,181,251,400`):

1. **Dues Shame Widget** (`dashboard.html:144-160`) — who's paid dues, member-only display.
2. **Announcements Banner** (`162-179`) — active announcements.
3. **Round Recap Widgets** (`181-`) — medalists / net lows / odds-and-ends, weekly.
4. **Activity Feed** (`251-`) — season progress bar + recent rounds / upcoming / standings snippet / handicap updates, one combined block.
5. **League Activity Feed** (`400-`) — a separate chronological notification-style feed, links to `/notifications`.

**Only widget #1 has any admin-configurable visibility today**, and it's the exact single-purpose mechanism the backlog item already flagged: `league_settings.show_dues_shame_widget` (`schema_postgres.sql:139`, a plain `INTEGER` boolean), read once in `main.py:230-237`, gating exactly that one widget. Widgets #2-5 are **purely data-driven** (shown whenever there's data to show — an announcement exists, a recap week exists, etc.) with no admin on/off control at all; an admin cannot hide them even if they wanted to.

## What a real per-widget system needs (facts, not a design)

1. **Registry of widget IDs.** The 5 sections above are the natural starting set, keyed by something stable (e.g. `dues_shame`, `announcements`, `round_recap`, `activity_feed`, `league_activity_feed`) — the template's own existing section-comment names are a ready-made naming convention.
2. **Storage shape — a real open decision.** Two real options, with a real scaling tradeoff: (a) one boolean column per widget on `league_settings` (mirrors the existing `show_dues_shame_widget` precedent exactly — simple, consistent with what's already there, but needs a schema migration every time a new widget is added or an existing one is split/renamed); (b) a single JSON/text column or a new child table (e.g. `dashboard_widget_visibility(league_id, season_id, widget_id, visible)`) — more normalized, no migration needed to add future widgets, but a bigger structural change from the existing single-column precedent. Given there are only 5 widgets today and the precedent already exists as columns, option (a) is the lower-friction extension; option (b) is the more future-proof one if more widgets are expected. Fable's call, not mine.
3. **Season-scoping matches the existing precedent, but is worth confirming as intentional.** `show_dues_shame_widget` lives on `league_settings`, which is **season-scoped** (has both `league_id` and `season_id`) — meaning visibility could in principle differ season to season. That may be more granularity than actually wanted (a league admin probably thinks of this as a league-level preference, not a per-season one) — worth Fable/@user explicitly deciding whether new widget-visibility settings should follow the same season-scoped precedent or be genuinely league-level (a different table, not `league_settings`).
4. **Season-rollover wizard interaction — an easy detail to miss.** `league_settings` columns are explicitly cloned by the "Start Another Season" wizard via a maintained column list (`seasons.py`'s `_LEAGUE_SETTINGS_CLONE_COLUMNS`, which already includes `show_dues_shame_widget`). **Any new widget-visibility column added to `league_settings` must be added to that clone list**, or it'll silently reset to its default every new season — exactly the kind of easy-to-miss step that produced several of the "dead setting" bugs found during this session's GLT parity audit. If a new child table is used instead (option (b) above), this concern doesn't apply the same way, but the season-rollover wizard would still need to know to carry forward whatever the new storage shape is.
5. **Admin-view is explicitly out of scope**, per the backlog wording — the existing hardcoded admin/member branch at `dashboard.html:12` stays as-is; this feature only ever needs to affect what renders inside the member branch.

## Net for Fable

Small, well-bounded feature once the storage-shape decision (item 2) is made — the widget inventory and naming are already given by the existing template structure, and the season-rollover clone-list gotcha (item 4) is a concrete, checkable detail rather than an open question. The one real design fork is storage shape (columns vs. a proper table) and, secondarily, whether visibility should be season-scoped like the existing precedent or promoted to a league-level setting. Recommend Fable pick one of the two storage shapes explicitly in the handoff's Implementation Plan rather than leaving it as a Stop Condition — this is a good-judgment call with no ambiguous requirement behind it, not a genuine open question needing @user's input.
