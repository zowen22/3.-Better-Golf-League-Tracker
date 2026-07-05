# Handoff: Settings Page Scalability (compact rows, collapsible categories, tooltip icons)

*Status: `Open`*
*Created: 2026-07-04 — Planner: Sonnet (site session)*
*Priority: `Medium` — Effort: `M`*
*Depends on: `None`*
*Parallel-safe: `Yes` — touches `admin/settings.html`, `main.css`, `main.js`, a new `app/setting_help.py` data module, and (only if the executor discovers a real need) `admin.py`'s render path. No schema, no migration, no other feature's files. Note for whoever later builds the wiki skeleton (`Audits/2026-07-04-site-wiki-skeleton-investigation.md`): that work depends on `app/setting_help.py` existing — read the note in this handoff's Context section before starting that one.*

-----

> This handoff is pure front-end restructuring, not a new feature and not a gap-closure pass. The GLT settings-parity audit (`7. GLT Feature Parity.md`) found ~209 GLT settings across 24 categories; BGLT's own settings page currently holds 36 settings in 9 categories using a roomy card-grid layout with always-visible hint paragraphs. That layout does not scale — this handoff reshapes the page's presentation layer so future gap-closure settings (whatever they turn out to be) have somewhere sane to land. **Do not add any new settings, categories, or gap-closure logic here** — that's separate, future work.

## Goal

The League Settings page (`app/routes/admin.py`'s `settings()` route, `app/templates/admin/settings.html`) should read as **compact, uncluttered, and navigable** even once it holds 100+ settings: one concise row per setting (not today's tall card), categories collapsed by default and expandable on demand, and every setting has a tooltip affordance — even though the actual explanatory text isn't ready yet (placeholder for now, real copy is separate future work tied to the in-app wiki). Desktop and mobile can present the tooltip differently (desktop: always-visible adjacent column; mobile: tap-to-reveal icon), but should share one underlying markup structure, not two maintained in parallel.

## Context

@user asked for this specifically because of the completed GLT-parity settings audit — before starting to close those gaps, the settings page itself needs to be able to absorb a much larger number of settings without becoming an unusable wall of cards. @user's explicit direction: "compact and concise setting rows, with collapsible categories for easy nav," a tooltip icon on every setting with a placeholder popup on mobile for now, and a possible different (adjacent-column) treatment on desktop where there's more room. Emphasis on clean/crisp/uncluttered, especially on mobile.

This is explicitly scoped as **infrastructure prep**, not gap-closure — no new settings are being added, no GLT gaps are being closed, and no product decisions from the parity audit (WHS math, absence point-clamps, etc.) are being resolved here.

**Added requirement (@user, 2026-07-04, before this was dispatched):** the tooltip text and the corresponding section on the future wiki page must be **one shared source of truth**, not two independently-maintained copies. @user's reasoning: seeing byte-identical text in both places is deliberate positive reinforcement that the wiki page a setting's "Learn more" link lands on is actually the right section — if the two ever drifted apart, that reinforcement becomes confusion instead. This changes "placeholder text" from something typed directly into `settings.html`'s markup into something read from a small shared data module — see the new `app/setting_help.py` requirement below. The wiki page itself isn't being built in this handoff (that's the separate, still-open wiki-skeleton work), but this handoff must lay the data foundation that work will read from, or the two will duplicate content the moment both exist.

## Findings / Evidence (current state — verified against code)

- **Current layout**: `admin/settings.html` — 9 sections (`Scoring`, `Handicap`, `Max Score Per Hole`, `Playoffs`, `Skins Defaults`, `Self-Reporting`, `Season Segments`, `Tiebreakers`, `Member Dashboard Widgets`), each a static `<div class="settings-section">` with an `<h2 class="settings-section__title">`, never collapsible, always fully rendered (`settings.html:34-462`). Each setting is a `.form-group` in a `.settings-grid` (CSS grid, `auto-fill, minmax(240px, 1fr)`, `main.css:2304-2311`) — label, input, and an always-visible `<p class="form-hint">` paragraph. 36 settings today (`grep -c "form-group" settings.html`), in 502 lines — this is the shape that won't scale to 100+.
- **Existing (unfinished) tooltip mechanism**: only 2 of 36 settings (2.10, 2.11 — the temp-handicap-percent pair) have a `<button class="settings-info-btn" data-info-target="info-2-10">ⓘ</button>` (`settings.html:189,199`). The popup content lives in a **hand-maintained JS object literal inline in this one template** (`settings.html:468-471`, `const infoText = {'info-2-10': '...', 'info-2-11': '...'}`), with click-to-show/position/dismiss logic in an inline `<script>` block (`settings.html:466-500`). **This does not scale** — it would require this dict to grow to 100+ hand-written entries inside one template file. CSS for it already exists and is reusable as-is: `.settings-info-btn`, `#settings-info-tip` (`main.css:2299-2302`).
- **Collapsible-section precedent already exists in this codebase** — native `<details>/<summary>`, no JS framework needed: `templates/players/roster.html:78-79,113-114` (`.inactive-section`), `templates/schedule/index.html:279-280` (`.team-ref-card`), `templates/playoffs/index.html:140-141` (`.bracket-edit-details`). Reuse this pattern rather than building a new JS-driven accordion.
- **Existing responsive breakpoint**: `main.css:8011` already collapses `.settings-grid` to a single column at `@media (max-width: 768px)`. Use this same breakpoint for the mobile/desktop tooltip-behavior split, for consistency with the rest of the page.
- **Both existing tooltip entries link to `/wiki#setting-2.10` / `#setting-2.11`** — `/wiki` doesn't exist yet (confirmed dead route; see `Audits/2026-07-04-site-wiki-skeleton-investigation.md`). This is a pre-existing, already-known gap, not something this handoff introduces or needs to fix — see Scope below.
- **Backend is untouched by this work**: `admin.py`'s `settings()` route reads/writes via `_SETTINGS_DEFAULTS` + a `data` dict + parallel UPDATE/INSERT SQL, all keyed by exact form field names. **No schema change, no migration.** This is a presentation-layer reshape only.
- **Wiki skeleton investigation** (`Audits/2026-07-04-site-wiki-skeleton-investigation.md`) already decided the future wiki page will be a **static Jinja template, not a DB-backed CMS** — content lives in code, not a database, and isn't admin-editable. A shared Python data structure (not a DB table) is consistent with that decision and is the natural place for the tooltip/wiki shared source of truth to live — no new schema needed for this either.

## Scope

### In
- Convert **all 9 existing sections** to the new pattern (not a partial demo — the page must be internally consistent when this is done).
- Compact row layout: one row per setting (number + label + tooltip icon, input control, and — desktop only — the tooltip text itself), replacing the current tall card + always-visible hint paragraph.
- Collapsible categories via native `<details>/<summary>` (matching the existing site pattern), collapsed by default, with a shared "Expand All / Collapse All" control at the top of the form.
- A tooltip icon (ⓘ) on **every** setting (all ~36, not just 2), with **placeholder text** for now — writing real per-setting explanations is explicitly NOT part of this handoff. The placeholder text (and, later, the real text) must live in **one shared data source**, not be typed directly into `settings.html`'s markup — see the new `app/setting_help.py` module below. This is what lets the future wiki page render the identical text without a second copy ever being created.
- **New shared data module: `app/setting_help.py`** — a plain Python dict keyed by the same setting-number scheme already in use (`'2.10'`, `'2.11'`, etc., matching `data-info-target="info-2-10"` and `/wiki#setting-2.10`), e.g. `SETTING_HELP = {'2.10': {'label': 'Pre-Eligibility Temp Handicap % (Member)', 'text': 'Full explanation coming soon.'}, ...}`. One entry per setting, all 36 for now (placeholder `text` for the 34 that don't already have real-ish copy; keep 2.10/2.11's existing text as their `text` value, migrated into this module rather than left in the old inline dict). This module is the single source both `settings.html`'s tooltip rendering and the future wiki page will read from — do not duplicate its content anywhere.
- Refactor the tooltip mechanism out of the one-off inline `<script>`/hardcoded dict into a **shared, scalable component**: put the JS in `main.js` (not inline per-template), and have the Jinja template render each button's `data-tooltip` attribute **from `setting_help.SETTING_HELP[id]['text']`** (looked up server-side at render time), not from a hand-typed string in the template and not from a client-side JS dict. This is the part that actually makes 100+ tooltips maintainable — and the part that makes the wiki page's future content genuinely the same string, not a copy of it.
- Desktop-vs-mobile tooltip behavior, same underlying markup, CSS/JS-driven by the existing 768px breakpoint: mobile = tap icon → popup (matching today's existing popup style/positioning logic, generalized); desktop = tooltip text always visible in an adjacent column, no click needed (executor's call whether the ⓘ icon still shows on desktop given the text is already visible — probably hide it there, since showing an icon next to already-visible text is clutter, but use judgment).
- Keep the `#setting-N.NN` numbering scheme and the "Learn more → `/wiki#setting-N.NN`" link pattern for forward-compatibility with the wiki skeleton work (that route is dead today; these links will start working automatically once the wiki skeleton ships — do not remove or "fix" them, they're intentionally forward-compatible). **Important:** the "Learn more" link is appended by the tooltip-rendering code *on top of* the shared `SETTING_HELP[id]['text']` value — it is not part of the shared text itself. The future wiki page reads the same `text` value directly and does not need (and must not show) a "Learn more" link pointing to itself.

### Out — do not touch
- **Writing real tooltip content** for any setting — placeholder text only. Real copy is separate, future work (paired with the in-app wiki skeleton).
- **Adding any new settings, categories, or GLT gap-closure logic.** This is layout/infrastructure only. If you find yourself wanting to add a "Standings" or "E-mails" category shell in anticipation of future gap-closure work — don't. Empty categories with zero settings are confusing, not helpful.
- **`admin.py`'s settings read/save logic** (the `_SETTINGS_DEFAULTS` dict, the `data` dict, the UPDATE/INSERT SQL) — do not change any of it. Every existing `name=`/`id=` attribute must survive unchanged (see Stop Conditions).
- **The other settings pages** (`admin/api_settings.html`, `admin/email_settings.html`, `registration/admin_settings.html`, `public/admin_settings.html`, the Dues/Skins settings sections) — this handoff is scoped to the main League Settings page (`admin/settings.html`) only. The shared tooltip JS component being built here is a reasonable candidate to extend to those pages later, but that's a future decision, not this handoff's job.
- **The dead `/wiki` route itself** — not this handoff's problem (tracked separately in `Handoffs`-adjacent wiki-skeleton work).

## Implementation Plan

1. **Create `app/setting_help.py`** first — the shared source of truth. A plain module-level dict, `SETTING_HELP`, keyed by setting-number string (`'1.01'`, `'2.10'`, etc. — cover all 36 current settings), each value `{'label': '...', 'text': '...'}`. Migrate the 2 existing real tooltip texts (2.10, 2.11) out of `settings.html`'s inline `infoText` dict into this module unchanged; give the other 34 a placeholder `text` (exact wording is the executor's call, but keep it consistent, e.g. "Full explanation coming soon."). This module has no Flask/route dependencies — it's just data — so it can be imported by both `admin.py` (for this handoff) and, later, whatever route the wiki skeleton work adds, with zero coupling between them.
2. **Wire `admin.py`'s `settings()` route to pass `SETTING_HELP` into the template context** (or import it directly in the template via a Jinja global — executor's call on which is cleaner in this codebase's existing conventions), so `settings.html` looks up each setting's tooltip text by its number rather than having text hand-typed into the markup.
3. **Design the compact row markup once**, then apply it uniformly across all 9 sections. Suggested shape (adjust as needed, but keep every setting looking the same): a row containing (a) `<span class="setting-num">N.NN</span>` + label + `<button class="settings-info-btn" data-tooltip="{{ SETTING_HELP['N.NN'].text }}">ⓘ</button>`, (b) the existing input/select/checkbox control unchanged (same `name=`/`id=`/`value=` — see Stop Conditions), (c) a tooltip-text element (also rendered from `SETTING_HELP`) that's hidden on mobile (shown only via the JS popup) and shown inline in a third column on desktop (≥768px). Consider whether a Jinja macro (e.g. a `_setting_row` macro taking number/label/input-HTML, looking up its own tooltip text from `SETTING_HELP` by number) is worth introducing to cut repetition across 36+ rows — recommended given the scale this needs to reach eventually, but not mandatory if it doesn't cleanly fit Jinja's macro model for varying input types.
4. **Refactor the tooltip JS into `main.js`**: a single, page-agnostic initializer that finds all `.settings-info-btn` elements (on any page, not just this one), reads tooltip text from `data-tooltip` on the button itself (already rendered server-side from `SETTING_HELP` per step 3 — the JS itself doesn't need to know about the Python module, it just reads the attribute), appends the "Learn more → `/wiki#setting-N.NN`" link in the popup (JS-appended, not part of the shared text — see Scope), and reuses the existing popup positioning/dismiss logic from `settings.html:472-498` (generalized, not settings-page-specific). Delete the inline `<script>` block and the hardcoded `infoText` dict from `settings.html` once this lands. Reuse the existing `.settings-info-btn` / `#settings-info-tip` CSS as-is; extend if the desktop adjacent-column layout needs new classes.
5. **Wrap each of the 9 `.settings-section` blocks in `<details>`**, replacing `<h2 class="settings-section__title">` with `<summary>` (keep the `.setting-num` + title text inside it). Collapsed by default. Add a small shared "Expand All / Collapse All" control (a couple of buttons or one toggle) — this needs a few lines of JS (can live in `main.js` alongside the tooltip init) that finds all `<details class="settings-section">` on the page and toggles their `open` attribute.
6. **Add the CSS**: compact row styles (replacing/extending `.settings-grid`/`.form-group`), the desktop-only tooltip column (media query gated at the existing 768px breakpoint — `min-width: 769px` block, or an `@media (max-width: 768px)` block hiding the desktop column and showing the icon+popup instead — whichever reads more cleanly against the existing stylesheet's convention), and styling for the `<details>/<summary>` wrapper consistent with the existing `.inactive-section`/`.team-ref-card` look elsewhere in the app.
7. **Validate** (see Definition of Done) — this is a pure presentation change with a hard correctness constraint (form field names must be byte-identical), so validation must include an actual settings-page load + save round-trip, not just a template parse.

## Stop Conditions

- Any change would require altering an existing `name=`, `id=`, or the value logic of an input/select/checkbox in a way that could change what gets submitted to `admin.py`'s `settings()` route. The row-layout change must be purely visual/structural around the existing controls, never a change to the controls themselves.
- The desktop/mobile split turns out to need two genuinely separate DOM structures (not just CSS-driven visibility of the same markup) — if so, stop and flag it; the intent is one shared structure, and two parallel structures would recreate the exact maintenance problem this handoff is trying to fix.
- Any temptation arises to add a new setting, a new category, or resolve a GLT-parity gap while working through this — that's explicitly out of scope; note it as a Follow-up instead.
- Any temptation arises to hand-type tooltip text directly into `settings.html` "just for now" instead of adding it to `SETTING_HELP` — don't; that would immediately recreate the exact duplication problem @user asked to avoid, and would need to be un-done the moment the wiki page is built.

## Definition of Done

- [ ] `app/setting_help.py` exists with a `SETTING_HELP` dict covering all 36 current settings (label + text each); this is the single source both the tooltip and the future wiki page will read from.
- [ ] All 9 existing sections converted to collapsible `<details>` categories, collapsed by default, with a working Expand All / Collapse All control.
- [ ] All 36 existing settings converted to the new compact row layout; every setting has a tooltip icon whose text is rendered from `SETTING_HELP` (not hand-typed in the template).
- [ ] Tooltip JS lives in `main.js` (not inline in `settings.html`), driven by `data-tooltip` attributes (populated server-side from `SETTING_HELP`), not a hardcoded ID-keyed JS dict. The "Learn more" link is appended by the JS/rendering layer on top of the shared text, not baked into `SETTING_HELP`'s `text` value.
- [ ] Mobile (≤768px): tooltip is tap-to-reveal via the icon, matching today's popup positioning behavior. Desktop (>768px): tooltip text is visible inline in an adjacent column without needing a click.
- [ ] Every existing setting's `name=`/`id=`/`value=` is unchanged — verified by an actual settings-page **load AND save round-trip** (not just a template parse): load the settings page as admin, submit the form with a couple of values changed, confirm they persisted correctly (mirrors the validation rigor used for the dashboard-widget-visibility handoff — see `5. Session Log.md`, 2026-07-04 entry, for the exact pattern: real Flask test client, real local Postgres dev DB, not a live production DB).
- [ ] Validated: `py_compile` on any touched `.py` (likely none, but check); real-app-context Jinja parse (`app.jinja_env`, not a bare `jinja2.Environment`) on `settings.html`.
- [ ] No schema/migration involved — confirm this remains true; if it turns out not to be, that's a Stop Condition, not something to quietly work around.
- [ ] Execution Report below filled in; Status updated to `Done` (or `Blocked`).
- [ ] Given zero schema/backend risk, this can be built directly on `main` (per @user's stated preference and consistent with the dashboard-widget-visibility precedent) — no feature branch needed, but still validate thoroughly before considering it done, since the correctness bar (byte-identical field names) is unforgiving.

## Critical Files

| File | Why |
|------|-----|
| `app/setting_help.py` | **New.** Shared `SETTING_HELP` dict — the single source of truth for tooltip text, also the future wiki page's source. Central to this handoff's most important constraint. |
| `app/templates/admin/settings.html` | The page being restructured — layout, `<details>` wrapping, tooltip markup, reads from `SETTING_HELP` |
| `app/static/css/main.css` | Compact row styles, desktop tooltip column, `<details>` styling (reuse `.settings-info-btn`, `#settings-info-tip`, `.inactive-section` as starting points) |
| `app/static/js/main.js` | New shared tooltip + expand/collapse-all JS, replacing the inline script in `settings.html` |
| `app/routes/admin.py` | Passes `SETTING_HELP` into the template context (or template imports it directly); confirms exact `name=`/`id=` values that must not change — do not edit the settings save/read logic itself unless a Stop Condition requires it |

-----

## Execution Report

*Executed: [date] — Executor: [model/session]*

### What Was Done

-

### Deviations from Plan

-

### Follow-ups Discovered

-
