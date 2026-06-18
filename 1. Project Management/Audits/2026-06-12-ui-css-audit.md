# UI / CSS Quality Audit — 2026-06-12

**Type:** CSS & Template Audit
**Status:** Complete
**Linked WP:** Phase 7 (Future)

---

## Executive Summary

Two Explore agents audited `app/static/css/main.css` (~7,563 lines) and all key templates for mobile-web and desktop-web quality. 43 findings across 4 priority tiers. Primary goal: prevent elements from overflowing, cascading off-screen, or overlapping on mobile. Fixes shipped 2026-06-12 cover the critical and high tiers.

---

## P0 — Critical (shipped 2026-06-12)

- [x] **Missing `viewport-fit=cover`** — `env(safe-area-inset-bottom)` had no effect without it. Added to `base.html` viewport meta.
- [x] **`main` container padding not reduced on mobile** — `0 24px` was too wide on 360px phones. Now `0 14px` at 768px, `0 10px` at 480px.
- [x] **`page-header` flex row didn't wrap** — title + badge + actions overflowed on narrow screens. Added `flex-wrap: wrap` at 768px.
- [x] **`header-actions` didn't wrap on mobile** — Multiple action buttons ran off-screen. Added `flex-wrap: wrap` at 768px.
- [x] **`archive-grid` / `courses-grid` minmax overflow** — `minmax(340px, 1fr)` and `minmax(280px, 1fr)` forced horizontal scroll on phones. Both collapse to `1fr` at 768px.
- [x] **`settings-grid` overflow on phones** — `minmax(240px, 1fr)` still 2 columns at 360px. Collapses to `1fr` at 480px.
- [x] **Course detail tee table missing scroll wrapper** — Added `<div class="table-scroll">` wrapper around tee sets table.
- [x] **Absence table in score entry missing scroll wrapper** — Added `table-scroll` wrapper.

---

## P1 — High (shipped 2026-06-12)

- [x] **`filter-group select` min-width: 200px** — forced horizontal scroll on narrow screens. Removed on mobile; width: 100%.
- [x] **`standings-subnav` overflow** — tabs exceeded viewport width with no scroll. Added `overflow-x: auto; -webkit-overflow-scrolling: touch`.
- [x] **`matchup-row` cramped on narrow screens** — flex row with tight content didn't wrap. Added `flex-wrap: wrap; gap: 6px` at 768px.
- [x] **iOS safe area inset on `.mob-save-bar`** — bottom padding didn't account for iPhone home bar. Now `calc(16px + env(safe-area-inset-bottom))`.
- [x] **iOS safe area inset on `.sch-edit-save-bar`** — same fix applied.
- [x] **`stroke-dot` font-size 6px** — unreadably small. Bumped to 8px.
- [x] **`sc-pt-indicator` font-size 10px** — very small. Bumped to 11px.
- [x] **Long strings (emails, forum, list-card) overflow containers** — Added `word-break: break-word; overflow-wrap: anywhere` at 768px.
- [x] **`subnav-link` padding cramped at 480px** — Reduced to `8px 12px; font-size: 0.82rem`.

---

## P2 — Medium (Future)

- [x] **Only one breakpoint (768px)** — 480px blocks added for col-player-name, form-row, schedule-filter-bar.
- [x] **Touch targets < 44px** — Added `@media (pointer: coarse)` block enforcing `min-height: var(--touch-min)` on subnav-link, btn-link, tab-link, standings-tab, filter-btn, page-btn.
- [x] **Inconsistent border-radius values** — Added `--radius-sm/md/lg` (4/8/12px) to `:root`. New code should use variables; legacy values are a future cleanup.
- [x] **Four different greens, four different reds** — Added full color system to `:root` (--green-dark/mid/light/bg, --red/red-bg, --orange, etc.). New code should use variables; legacy inline values are a future cleanup.
- [x] **`schedule-filter-bar` on very narrow phones** — Handled in 480px block (column layout, full-width selects).
- [x] **`col-player-name` min-width 150px** — Fixed at 480px: max-width 120px with overflow ellipsis.

---

## P3 — Low (Future)

- [x] **`ov-stat-grid` at 320px** — Collapses to 1 column at 340px.
- [x] **Forum row metadata wraps awkwardly** — `.forum-row-meta` gets `flex-wrap: wrap; row-gap: 2px; line-height: 1.4`.
- [x] **Admin overview "stat" label font-size 11px** — `.ov-stat-label` bumped to 12px.
- [x] **`.form-row .form-group min-width: 180px`** — `min-width: 0` applied at 480px.
- [x] **Missing `text-overflow: ellipsis` on long player names in tables** — `.data-table td.player-name-cell, .col-player` get ellipsis + max-width.

---

## Files Modified

- `app/static/css/main.css` — stroke-dot, sc-pt-indicator, standings-subnav, sch-edit-save-bar, mob-save-bar, global responsive block appended
- `app/templates/base.html` — viewport-fit=cover
- `app/templates/courses/detail.html` — table-scroll wrapper on tee table
- `app/templates/scores/enter.html` — table-scroll wrapper on absence table
