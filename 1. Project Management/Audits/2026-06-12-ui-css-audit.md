# UI / CSS Quality Audit — 2026-06-12

**Type:** CSS & Template Audit
**Status:** In Progress
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

- [ ] **Only one breakpoint (768px)** — Nothing for 480px on most components. Coverage improved with new 480px block but not comprehensive.
- [ ] **Touch targets < 44px** — Various badges, small buttons, and nav links don't meet the 44×44px minimum. Worth a dedicated pass.
- [ ] **Inconsistent border-radius values** — 4px, 5px, 6px, 8px, 10px, 12px, 20px in use. Consolidate to a 3-value scale (4/8/12).
- [ ] **Four different greens, four different reds** — CSS variables used inconsistently. Audit and consolidate into `:root` variables.
- [ ] **`schedule-filter-bar` on very narrow phones** — still may wrap awkwardly below 360px.
- [ ] **`col-player-name` min-width 150px** — may still overflow on very narrow phones in scorecard view.

---

## P3 — Low (Future)

- [ ] **`ov-stat-grid` at 320px** — 2 columns at 480px may still be tight at 320px; consider single column.
- [ ] **Forum row metadata wraps awkwardly** — line-height and flex layout need refinement on narrow screens.
- [ ] **Admin overview "stat" label font-size 11px** — borderline small; consider 12px.
- [ ] **`.form-row .form-group min-width: 180px`** — can overflow at 360px before the 768px breakpoint kicks in; add `min-width: 0` on mobile.
- [ ] **Missing `text-overflow: ellipsis` on long player names in tables** — would prevent wrapping inside data cells.

---

## Files Modified

- `app/static/css/main.css` — stroke-dot, sc-pt-indicator, standings-subnav, sch-edit-save-bar, mob-save-bar, global responsive block appended
- `app/templates/base.html` — viewport-fit=cover
- `app/templates/courses/detail.html` — table-scroll wrapper on tee table
- `app/templates/scores/enter.html` — table-scroll wrapper on absence table
