# Handoff: In-App Site Wiki Skeleton

*Status: `Done`*
*Created: 2026-07-05 — Planner: Sonnet (site session)*
*Priority: `Medium` — Effort: `S`*
*Depends on: `app/setting_help.py` (already built and shipped — see `Handoffs/2026-07-04-settings-page-scalability.md`, merged to main `3fc588c`)*
*Parallel-safe: `Yes` — new blueprint/route/template + one nav link + `base.html`. Touches no existing feature's files except `base.html` (additive) and `app.py` (one new blueprint registration).*

-----

> Structure only — do not write new explanatory content. This skeleton renders existing content from `app/setting_help.py`'s `SETTING_HELP` dict (already populated with real text for ~24 settings, placeholder text for the rest) and falls back to a plain "being written" placeholder for anything not in there. Per-setting text must never be typed directly into this wiki's template — see Scope.

## Goal

A working `/wiki` page that: (a) immediately fixes two already-broken links in production (`admin/settings.html`'s "Learn more" links for settings 2.10/2.11 currently 404), (b) gives every other setting's future "Learn more" link somewhere real to land the moment it's added, and (c) is organized into clear categories so it reads as a real reference, not a wall of anchors — all without requiring anyone to write new content right now.

## Context

This is the second of two related, already-scoped pieces of prep work from the GLT-parity-driven settings push: first the settings page itself was rebuilt for scale (shipped `3fc588c`), and this is its natural companion — the wiki page those tooltips already link to. @user asked for this skeleton specifically, with an explicit, standing instruction from when it was first investigated: build the structure now, defer writing real content until the product is more mature (features/settings are still changing, so content written today would go stale). @user separately required that this page and the settings-page tooltip share one source of truth (`SETTING_HELP`) rather than risk drifting apart — that dependency is now satisfied.

Full investigation: `Audits/2026-07-04-site-wiki-skeleton-investigation.md` — read it in full before starting. This handoff operationalizes its "Recommended v1 skeleton shape" section directly; nothing here contradicts it.

## Findings / Evidence (current state — verified against code)

- **`/wiki` is referenced twice today and 404s both times.** `app/templates/admin/settings.html`'s tooltip JS (`app/static/js/main.js`, the shared tooltip component built in the settings-scalability work) appends a "Learn more → /wiki#setting-N.NN" link using each button's `data-wiki-anchor` attribute. No `wiki` blueprint is registered in `app.py` (confirmed: 40 `register_blueprint` calls, none for `wiki`) — so every one of these links currently 404s.
- **`app/setting_help.py` exists and is the required content source** (built in the settings-scalability handoff, shipped to main). `SETTING_HELP` is a plain dict keyed by setting number (`'2.10'`, `'1.05'`, etc.), each entry `{'label': ..., 'text': ...}`. ~24 settings have real, already-reviewed one-line text (backfilled from the page's pre-existing hint copy during Planner review); the rest hold a placeholder (`"Full explanation coming soon."`). This wiki skeleton must render its per-setting sections from this exact dict — see Scope.
- **Anchor convention already established**: `data-wiki-anchor="setting-N.NN"` on every tooltip button, matching the `#setting-N.NN` scheme the dead links already use. The wiki template's per-setting sections must use `id="setting-N.NN"` to match.
- **No nav entry point exists.** `base.html`'s nav drawer (~25 links across admin/member/misc sections) has nothing for wiki/help. Natural placement: immediately after "League Info" (`base.html` — `url_for('league_info.info')`, followed by Archive, Reports), same section, same audience (all logged-in users, not admin-only).
- **Category structure already proven**: the GLT how-to article grouping built during the parity audit (`7. GLT Feature Parity.md`'s "How-To Articles" table) groups by Setup/Account/Admin, League Structure & Roster, Courses/Tees, Scheduling, Handicaps, Scoring/Points, Subs/Absences, Skins/Contests, Reports, Communication. Adapt these names to BGLT's actual features (not GLT's), don't invent a new taxonomy.
- **Storage model is settled**: static Jinja template, no database, no admin-editing UI (matches the settings-scalability precedent of `SETTING_HELP` being a plain Python module, not a DB table).

## Scope

### In
- New blueprint `app/routes/wiki.py`, one route `GET /wiki`, `login_required` (not `admin_required` — members and admins both).
- One template, one long scrollable page, organized into the category headings above (adapted to BGLT's own features).
- Per-setting anchor sections (`id="setting-N.NN"`) rendered from `SETTING_HELP[id]['label']` / `SETTING_HELP[id]['text']` — iterate over `SETTING_HELP` (imported directly, same module the settings page already uses) and place each entry under its matching category heading. Settings not yet in `SETTING_HELP`, or category-level content with no per-setting granularity, get a plain "This section is being written — check back soon" placeholder.
- One new nav-drawer link in `base.html`, placed next to "League Info".
- Confirm the two existing dead links (`/wiki#setting-2.10`, `/wiki#setting-2.11`) now resolve to real, matching content (they should — 2.10/2.11 already have real text in `SETTING_HELP`).

### Out — do not touch
- **Writing any new explanatory content.** Every setting's text comes from `SETTING_HELP` as it exists today — do not add prose beyond what's already there, even where the placeholder feels thin. Writing real copy is separate, future work, explicitly deferred by @user.
- **Editing `app/setting_help.py`'s content.** If a category has no settings in it yet (e.g. broader "how the schedule works" explainer content beyond individual settings), use a placeholder section, don't invent new dict entries to fill the gap.
- **A DB-backed CMS, admin-editing UI, or versioning.** Explicitly out of scope per the investigation — static template only.
- **Splitting into multiple pages.** Single page with anchors, per the investigation's recommendation — don't introduce per-category sub-routes.
- **The tooltip-retrofit backlog item** ("retrofit ⓘ tooltip pattern onto the other ~36 existing settings fields") — that's about the settings page's own tooltip UI coverage, already handled by the settings-scalability work (all 39 settings now have the ⓘ icon). Not this handoff's concern.

## Implementation Plan

1. Create `app/routes/wiki.py`: a blueprint, one `GET /wiki` route (`login_required`), importing `SETTING_HELP` from `app/setting_help.py` directly (same pattern the settings page uses — no new Jinja global needed unless it turns out cleaner to register one, executor's call).
2. Register the blueprint in `app.py` alongside the other ~40.
3. Build the template: category headings (adapted GLT-derived list), with each category's known settings rendered as `<section id="setting-N.NN">` blocks (heading = `SETTING_HELP[id]['label']`, body = `SETTING_HELP[id]['text']`). Map each of BGLT's 39 settings to the category it conceptually belongs in (this mapping is presentation-only judgment, not a new design decision — use the settings page's own existing section groupings — Scoring/Handicap/Max Score/Playoffs/Skins/Self-Reporting/Segments/Tiebreakers/Dashboard Widgets — as a starting point, merging/renaming into the broader GLT-derived categories where it makes sense).
4. Add the nav-drawer link in `base.html` next to League Info.
5. Validate: `py_compile` on `wiki.py`/`app.py`; real-app-context Jinja parse on the new template; a real route hit via Flask's test client confirming `/wiki` returns 200 for a logged-in user and 302/redirect for a logged-out one (mirrors `login_required`'s existing behavior elsewhere); confirm `#setting-2.10` and `#setting-2.11` anchors exist in the rendered HTML with the same text currently shown in the settings-page tooltip for those two (byte-identical, since both read `SETTING_HELP` — this is the one correctness check that actually matters here).

## Stop Conditions

- Any temptation to write new explanatory content beyond what's already in `SETTING_HELP` — don't; flag as a Follow-up instead.
- Any temptation to add a second, wiki-specific content dict "just for the category intros" instead of a plain placeholder string — don't; keep the one-source-of-truth property intact for anything that touches per-setting content specifically (category-level framing text that isn't about one specific setting is fine to write directly in the template, since it has no settings-page counterpart to drift from).
- If achieving one-page-with-anchors turns out to require restructuring `SETTING_HELP` itself (rather than just reading from it) — stop; that would touch the settings-scalability feature's shipped code, out of scope here.

## Definition of Done

- [x] `GET /wiki` works for a logged-in user (member or admin), 200.
- [x] Logged-out access redirects to login (`login_required` behavior, consistent with the rest of the app).
- [x] Page organized into adapted-GLT categories; every one of the 39 current settings appears somewhere, under `id="setting-N.NN"`, with `SETTING_HELP`-sourced label/text (real text where it exists, placeholder otherwise).
- [x] `/wiki#setting-2.10` and `/wiki#setting-2.11` resolve to real content, identical to what the settings-page tooltip shows for those two settings today (spot-check both).
- [x] Nav-drawer link added, placed near "League Info".
- [x] Validated: `py_compile`, real-app-context Jinja parse, and a real test-client hit confirming 200/redirect behavior.
- [x] Execution Report filled in; Status updated to `Done` (or `Blocked`).
- [x] Zero schema/migration involved (confirm this remains true) — build directly on `main`, commit locally, but **do not push**; Planner reviews before it ships, same as the settings-scalability handoff.

## Critical Files

| File | Why |
|------|-----|
| `app/routes/wiki.py` | New. The blueprint/route. |
| `app/templates/wiki/index.html` (or similar — executor's call on exact path) | New. The page itself. |
| `app/setting_help.py` | Read-only — the content source. Do not edit its content, only import from it. |
| `app/app.py` | One new `register_blueprint` line. |
| `app/templates/base.html` | One new nav-drawer link. |

-----

## Execution Report

*Executed: 2026-07-06 — Executor: Sonnet 5 (executor session, on `main`)*

### What Was Done

- **New blueprint** `app/routes/wiki.py` — `GET /wiki`, `login_required` (not `admin_required`). No `url_prefix`; route registered directly as `/wiki` so the path is exact (no trailing slash), matching the existing dead-link convention (`/wiki#setting-N.NN`).
- Blueprint imports `SETTING_HELP` directly from `setting_help` (same pattern `app.py` already uses for the Jinja global) — no new content dict introduced. The module defines `WIKI_CATEGORIES`, a plain structural list mapping each of the 39 `SETTING_HELP` ids to one of 11 adapted-GLT category headings (structure/ids only, zero explanatory prose): Setup & Season Basics, League Structure/Roster & Playoffs, Courses & Tees, Scheduling & Season Segments, Handicaps, Scoring & Points, Subs & Absences, Skins & Contests, Self-Reporting, Reports & Dashboard, Communication (this last one has no settings mapped — placeholder-only, per scope).
- Registered in `app.py`: one import line + one `register_blueprint` call, alongside the other ~40.
- **New template** `app/templates/wiki/index.html` — single scrollable page, extends `base.html`. A jump-to-category TOC at top, then one `<section id="{cat.slug}">` per category with an `<h2>` heading, then per-setting `<section class="wiki-setting" id="setting-N.NN">` blocks (`<h3>` = `SETTING_HELP[id]['label']`, `<p>` = `SETTING_HELP[id]['text']`). Categories with no mapped settings (Communication) render the generic `"This section is being written — check back soon."` placeholder string (defined once in `wiki.py`, passed to the template — not duplicated in the template itself). No new explanatory copy was typed anywhere; the only hand-written strings are category names/icons (structure) and the one generic placeholder sentence.
- **Nav-drawer link** added in `base.html`, directly after "League Info" (`📖 Site Wiki` → `url_for('wiki.index')`), same Community group/audience.
- Confirmed the two previously-dead links now resolve: `/wiki#setting-2.10` and `/wiki#setting-2.11` render real content, byte-identical to `SETTING_HELP['2.10']['text']` / `['2.11']['text']` (see Validation below).

### Validation Performed

- `py_compile` on `app/routes/wiki.py` and `app/app.py` — clean. Also ran `python -m compileall -q .` across the whole `app/` tree — clean (nothing else broken by the two edits).
- Real-app-context Jinja parse: built the actual app via `create_app()`, then `app.jinja_env.get_source`/`from_string` on `wiki/index.html` inside `app.app_context()` (not a bare `jinja2.Environment()`) — parsed without error, confirming it resolves the app's registered globals/filters (`url_for`, etc.) correctly.
- Flask test client, real route hit:
  - Logged out: `GET /wiki` → `302`, `Location: /login` (matches `login_required`'s behavior elsewhere in the app).
  - Logged in (session seeded with `league_id`/`league_name`/`role` via `session_transaction`, no real DB round-trip needed since the route does no querying): `GET /wiki` → `200`.
- **Byte-identical anchor-text check (the one that matters):** extracted the rendered `<p class="wiki-setting__body">` contents for `id="setting-2.10"` and `id="setting-2.11"` from the actual response HTML and compared via Python string equality (`==`) against `SETTING_HELP['2.10']['text']` / `['2.11']['text']` read directly from `setting_help.py` — **both `True`** (not eyeballed). Since `admin/settings.html`'s tooltip reads the exact same dict values, the tooltip and wiki section are guaranteed byte-identical by construction, not just by this one spot-check.
- Coverage check: programmatically diffed `WIKI_CATEGORIES`' mapped ids against `SETTING_HELP.keys()` — 39 mapped, 0 missing, 0 extra (every current setting appears exactly once, under some category).
- **Incident during validation (self-corrected):** the local-dev SQLite smoke test's `create_app()` call ran `init_db()` against the repo's tracked `Database/golf_league.db` file (an existing committed dev-DB artifact, unrelated to this handoff) and modified it; it was then accidentally `rm`'d while cleaning up. Caught via `git status` showing it as deleted before committing, restored with `git checkout -- Database/golf_league.db`. Final `git status` before commit shows only the intended 4 files changed.

### Deviations from Plan

- Blueprint has no `url_prefix` (route is `@bp.route('/wiki')` directly) rather than following the `url_prefix='/xxx'` + `@bp.route('/')` pattern most other blueprints use (e.g. `archive.py`) — that pattern produces `/archive/` (trailing slash), which would not exactly match the already-dead `/wiki#setting-N.NN` links' path. Same net behavior, just avoids an unnecessary redirect/mismatch on the exact `/wiki` path the tooltip JS already hardcodes.
- Category set is 11, not exactly the 10 GLT-derived names verbatim — split "Self-Reporting" out as its own category (distinct workflow, matches the settings page's own section 6 grouping) and merged Tiebreakers (settings-page section 8) into "Scoring & Points" (they govern standings order, a scoring concern) rather than forcing them into "Reports." This is the presentation-only judgment call the handoff explicitly delegated to the executor.

### Follow-ups Discovered

- None beyond what the handoff already tracks as separate/deferred (writing real `SETTING_HELP` content; the tooltip-retrofit backlog item). No new gaps found.
