# Plan: Weekly Recap Page Redesign (Email/Text Mode + Reorderable Sections)

*Status: `Decision: Approach A (backend plain-text renderer) + Approach B (touch-safe pointer-based drag) + Decision 3 as read (Text mode live, Email mode manual-preview unchanged)` — @user approved 2026-07-09, "go on your weekly recap design"*
*Opened: 2026-07-09 — @user request, captured before building per explicit instruction*

-----

## Ask (verbatim, 4 parts)

1. Remove the "← Email Settings" button from the top of the Send Weekly Recap page.
2. Remove the "Email is not enabled" warning banner; only show it if a send is actually attempted and fails because email isn't enabled.
3. In the "Sections to Include" box, add a toggle that swaps the page between **Email** mode and **Text** mode. In Text mode, a box below is populated with a **live preview** of the selected sections as plain text, with a **Copy** button.
4. Make the "Sections to Include" options **drag-to-reorder**, and have that order drive the order sections appear in the preview.

## Current state (`app/routes/email_config.py` + `app/templates/admin/weekly_recap.html`)

- **Header button** (item 1): `templates/admin/weekly_recap.html` lines 10-12, a static link to `email_config.settings`. Trivial to remove.
- **Always-visible banner** (item 2): lines 15-21, rendered unconditionally whenever `not email_enabled`. **The reactive behavior already exists and works today** — `weekly_recap_send()` (`email_config.py:1173-1176`) already checks `cfg.get('email_enabled')` at send time and `flash()`s an error if it's off, redirecting back to this same page. So item 2 is almost free: delete the static banner block, and the existing flash mechanism (rendered by `base.html` for every page already) covers the "only show if tried and not enabled" behavior with zero backend change.
- **Sections are unordered today, and the render order is hardcoded regardless of anything the admin does.** `sections = set(request.form.getlist('sections'))` (three call sites: `weekly_recap_preview`, `weekly_recap_send`, and the identical pattern would apply to a new text-preview endpoint) is a Python `set` — no order. `_build_recap_html()` (`email_config.py:831+`) doesn't consult any order at all; it's a hardcoded sequential `if 'x' in sections:` chain: custom_message → match_results → scorecards → low_gross → standings → upcoming → absences, always in that order no matter what. **This is the load-bearing finding for item 4** — drag-reordering the checkboxes in the UI would currently have zero effect on output, because the backend never asks what order they came in. This has to become a real ordered pipeline, not just a frontend cosmetic change.
- **No plain-text rendering exists anywhere in this flow.** `_build_recap_html()` produces HTML only; `send_league_email(league_id, recipients, subject, html)` is called without a `text_body` (its signature supports one — `text_body=None` — but weekly recap never populates it). Item 3's Text mode needs genuinely new rendering logic, not a rewire of something that already exists.
- **Bug found, not requested, flagging separately:** `weekly_recap_weeks()` (`email_config.py:1100-1124`, the AJAX endpoint that repopulates the Week dropdown when Season changes) binds its `WHERE season_id = %s` to `session['league_id']` instead of the actual `season_id` request argument — the real season-ownership check happens in a *separate* query below that never gets used to filter the main one. Looks like a botched security fix (variable swapped). **Not fixing as part of this plan** unless you want it bundled in — flagging because I'll already be in this exact function for the reorder work.

## Decision 1 — How does Text mode actually render plain text?

**Approach A: Real backend plain-text renderer (Recommended).** Add `_build_recap_text(league_name, season_name, data, sections, custom_message)` mirroring `_build_recap_html`'s structure and dispatch, but each section gets its own hand-designed plain-text format (e.g. standings as an aligned fixed-width list, match results as simple `Team A def. Team B, 5.5–2.5` lines, scorecards condensed to gross/net per player rather than full hole-by-hole, absences as a short list). A new `mode` param on `/weekly-recap/preview` (`'html'`/`'text'`) branches to one builder or the other and returns `{content, error}`.
- *Tradeoffs:* real design work per section (7 sections, each needs its own plain-text shape decided) — this is genuinely the biggest chunk of new work in the whole request. But it produces something actually meant to be pasted into a text message or GroupMe, which is clearly the intent ("Copy the box contents").
- *Effort:* M.

**Approach B: Strip the existing HTML client-side.** Reuse the HTML preview response, extract `.innerText` from a hidden container in JS, dump that into the Text-mode box.
- *Tradeoffs:* almost free to build, but several sections are HTML tables (scorecards, standings) — `innerText` on a table produces ugly, inconsistently-spaced output that won't paste cleanly into a text message. Doesn't match "populated with a live preview" well if the result looks broken.
- *Effort:* S, but likely needs rework later once someone actually tries to paste the output somewhere.

**My recommendation: A.** The whole point of Text mode is producing something clean enough to paste into a group text — B's output quality risk defeats that purpose for exactly the sections (scorecards, standings) most likely to be included. Confirm before I start, since A is real work, not a quick toggle.

## Decision 2 — Drag-and-drop implementation

**Approach A: Native HTML5 Drag and Drop API (`dragstart`/`dragover`/`drop`).**
- *Tradeoffs:* smallest amount of new JS, no dependency. **But HTML5 DnD has no real touch/mobile support** — this project has put real effort into mobile parity all session (compact mobile tables, touch-target sizing audits, etc.), and an admin reordering recap sections is a very plausible thing to do from a phone. Native DnD would silently not work on mobile at all.
- *Effort:* S.

**Approach B: Pointer-events-based custom reorder (Recommended)** — hand-rolled long-press-and-drag using `pointerdown`/`pointermove`/`pointerup` (unified mouse+touch handling, no library). Reorders the actual `.wr-toggle` DOM nodes on drop.
- *Tradeoffs:* more JS to write and test than A, but works on both desktop and mobile, consistent with the rest of this app's established mobile-first conventions this session.
- *Effort:* M.

**My recommendation: B.** Given this codebase's demonstrated priority on mobile parity everywhere else, shipping a reorder feature that silently doesn't work on a phone would be a real regression in spirit even if it "works" on desktop. No new dependency either way — this is vanilla JS regardless of approach.

**One clean design consequence of choosing DOM-order-as-source-of-truth:** `FormData.getAll('sections')` already returns *checked* checkbox values **in DOM order**. So dragging a `.wr-toggle` row to a new position in the list is *sufficient* — no separate hidden "order" field is needed; the existing `sections` form field naturally submits in the new order once the DOM is reordered. Backend just needs `sections = request.form.getlist('sections')` (a **list**, not `set(...)`) at all three call sites, and `_build_recap_html`/`_build_recap_text` need to iterate that list (via a `{key: renderer}` lookup dict) instead of the current hardcoded if-chain — same ordered list drives both Email and Text mode, so the two views can never drift out of sync with each other.

## Decision 3 — Is Text mode's "live preview" actually live (auto-updating), while Email mode keeps its current manual "Preview Email" button?

Your phrasing says "a live preview" specifically for the Text-mode box, and doesn't say anything about changing Email mode's existing manual-button behavior. **My reading: yes, this is an intentional asymmetry** — Text mode auto-refreshes (debounced) on every section toggle, reorder, season/week change, or custom-message edit; Email mode keeps requiring the explicit "Preview Email" click it has today. This also naturally means the **Send button only makes sense in Email mode** — Text mode replaces it with the Copy button (nothing to "send" from a text mode built for copy/paste). Flagging this reading explicitly since it's an assumption, not something you spelled out — correct me if Email mode should also go live.

## Scope

### In
1. Remove header "Email Settings" button.
2. Remove static "email not enabled" banner; verified the existing flash-on-send-attempt already covers the desired behavior with no backend change.
3. Email/Text mode toggle (segmented control, near the Sections box or preview panel). Text mode: readonly box + live (debounced auto-refresh) plain-text preview + Copy button (Clipboard API). Email mode: unchanged manual-preview/Send behavior.
4. New `_build_recap_text()` covering all 7 current sections, each with its own plain-text format.
5. `/weekly-recap/preview` gains a `mode` param, branches to HTML or text builder.
6. Sections list becomes drag-reorderable (pointer-events based, touch-safe), reordering the actual DOM nodes so form submission order updates for free.
7. `sections` becomes an ordered list end-to-end (three call sites); `_build_recap_html` refactored from its hardcoded if-chain to an ordered `{key: renderer}` dispatch so Email and Text modes can never disagree on section order.

### Out — explicitly not doing
- **Not fixing** the `weekly_recap_weeks()` league_id/season_id bug found during this investigation — flagged above, separate decision.
- **Not** adding a persisted "default section order" per league (order lives only in the current page session/DOM state, resets to the current hardcoded default on page reload) — no ask for persistence, not assuming one.
- **Not** changing what `weekly_recap_send()` actually emails (still HTML + no text_body) — Text mode is a standalone copy/paste utility, not wired into the actual sent email's multipart body. If you want the plain-text renderer also used as the real email's text-alternative body (good practice, `send_league_email` already supports it), that's a very small additional step once `_build_recap_text` exists — flag if you want it bundled in.

## Definition of Done (once approved)
- [x] All 4 requested items implemented per the decisions above.
- [x] Validated against real dev Postgres: preview (both modes) for a real completed week, all 7 sections individually toggled on/off (subset tests), drag-reorder actually changes output order in both modes, Copy button copies exactly what's shown (confirmation state verified), flash-based "email not enabled" error fires only on an actual send attempt (unchanged existing mechanism, not re-tested this pass).
- [x] Drag-reorder tested via genuine `pointerdown`/`pointermove`/`pointerup` events in a real Playwright Chromium session (mouse-path simulation) — the implementation itself is pointer-events-based so the same code path handles touch; a physical mobile device was not used for this pass.
- [x] No regression to existing Email-mode preview/send behavior — confirmed via Playwright (mode-toggle back to Email restores Preview/Send controls, manual "Preview Email" still works).

**Build complete 2026-07-09.** See Session Log for full validation details (backend script `test_recap_backend.py` + end-to-end Playwright `test_recap_ui.py`, both against real dev Postgres data, all assertions passed). Also fixed a 6th GROUP BY instance found inside `_build_recap_data()` during this work (same bug class as the production error that opened this session — see Work Packages WP3.1).

-----

## Next step
Confirm Decisions 1–3 above (or redirect them), and say go — this is real, multi-part work (new text-rendering logic per section, ordered-dispatch refactor, touch-safe drag reorder), not a quick pass.
