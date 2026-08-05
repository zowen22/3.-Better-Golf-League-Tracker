# Desktop UI/UX Audit — 2026-08-05

**Type:** Audit Finding
**Status:** Mostly resolved — F1, F2, F3, F5, F7 fixed; F4 turned out already-resolved by the upstream Admin Panel rebuild. Only F6 (nav-surface consolidation) still open.
**Priority:** ~~P1 (F1, F2)~~ done. F6 still open, P3, structural — needs @user's call before touching.
**Prepared by:** Sonnet, 2026-08-05 (fixes applied same day: F1/F2/F5/F7 after "fix the rest", F3 after @user picked sage as canonical)
**Linked WP:** none yet — log against WP3.1 (backlog) if F3/F6 get scoped
**Scope of this pass:** desktop viewport (1440×900) only. No mobile/tablet pass done here.

---

## ⚠️ Post-merge correction (read this first)

This audit was originally run against a **stale local checkout** — this session's `main` was ~70 commits behind `origin/main` at audit time (unrelated to this doc; a prior push in the same session hadn't pulled first). After writing the audit, a push attempt failed with a non-fast-forward rejection, which surfaced the divergence. The branches were merged (`git merge origin/main`, clean, no conflicts) before this doc was pushed.

**Practical effect on the findings below:** the missed upstream commits included a full Admin Panel rebuild (tabbed layout — `ap-tabs`/`ap-panel`/`ap-tile`, replacing the tile-grid + "More Tools" dropdown this audit screenshotted), a Stats nav restructure, print-scorecards rework, and ~100 other file changes. Concretely:

- **F1 and F2 were re-checked against the merged/current code and are still present** — both are real, current bugs, not stale findings. Confirmed by re-reading the live source below.
- **F3, F4, F5, F6, F7 were screenshotted against the old Admin Panel and old nav** and have **not** been re-verified against current `main`. F4 in particular referenced an `.admin-action-btn--submissions` class/button that no longer appears anywhere in the current `admin/season.html` — the whole quick-actions/tile-grid it lived on was replaced by the tabbed rebuild. F3/F5/F6/F7 may still hold (they weren't specific to the old Admin Panel), but treat them as **unverified against current `main`**, not confirmed.
- **The "Navigation State Check" section below was flat-out wrong in its original form** — it concluded the Stats-nav flattening @user recalled didn't exist anywhere in history. It does: see the corrected section below.

If re-auditing, re-shoot F3–F7 against current `main` before trusting them; don't just re-read this doc's original prose for those.

---

## Goal

User asked for a desktop-perspective audit across five lenses: **user friction, site function, UI/CSS function, theme unity, site navigation.** Swept ~30 pages (logged-out marketing + logged-in admin/member app) via Playwright against local dev (`DATABASE_URL` pointed at `golf_dev` Postgres, league `Shankapotamus`, `league_id=1`), full-page screenshots at 1440×900, cross-checked every visual anomaly against source and the Flask dev server's error log before reporting — nothing below is screenshot-guesswork.

This doc exists specifically so a later session (human or agent) checking a *different* version of the app can diff their findings against a known-good baseline, per @user's request — see "Navigation State Check" below for the specific question that prompted that.

## Method / Caveats

- Local dev DB was mostly empty (no generated schedule, no completed rounds) at audit time — this is *why* most pages show empty states in the screenshots. Do not read "0 rounds played" as a bug; it's test-data starvation, not app breakage. Where a finding depends on real data existing, that's called out.
- Two things that *looked* like bugs in initial screenshots were run down and ruled out as false alarms (documented at the bottom so nobody re-chases them): a full-page-screenshot artifact on the nav drawer's height, and emoji-native-color being misread as a CSS inconsistency on the Standings "🏆 Podium" tab.
- One flaky Playwright timeout on `/league/info` was traced to the sandbox's outbound-HTTPS proxy occasionally hanging on `fonts.googleapis.com`/`googletagmanager.com` — confirmed via direct `curl` (4ms response) that the Flask app itself is fine. Noted as a real-world resilience consideration anyway (see F7), but not logged as an app bug.

---

## Findings

| ID | Finding | Location | Severity | Status |
|----|---------|----------|----------|--------|
| F1 | **`/archive/` 500s unconditionally.** `_season_stats()`'s `top_team` query selects `t.team_name` + two player-name columns while only grouping by `mr.team_id` — Postgres rejects this at plan time (`GroupingError: column "t.team_name" must appear in the GROUP BY clause`). Fails on every call, every league, regardless of data. Linked from the Dashboard tile, Admin Panel → More Tools, and the nav drawer's League group. | `routes/archive.py:104-115` (`_season_stats`) | **P1 — live bug** | ✅ **Fixed** `090ba1b` — added the missing columns to `GROUP BY` |
| F2 | **`/admin/email/` (Email Settings) 500s outright.** The template's "← Admin Panel" back-link calls `url_for('admin.panel')` with no `season_id`, but that endpoint requires one (`werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'admin.panel'. Did you forget to specify values ['season_id']?`). Page is currently unreachable via its own "More Tools" link. | `templates/admin/email_settings.html:6` → `routes/email_config.py:295` (`settings()`) | **P1 — live bug** | ✅ **Fixed** `090ba1b` — back-link now points at `admin.landing` (season-agnostic entry point) |
| F3 | **Three competing "primary action" colors, no single canonical one.** Terracotta (`--accent-bright`, homepage hero CTAs only) vs. light sage (`#bcd6ab`, `.btn-primary` — the actual default on Sign In, Create League, Add Contest, New Topic, Save Settings, etc.) vs. dark green (`--green-dark` — nav bg + a few "hero" CTA components like Score Entry/Print Scorecards cards, dashboard admin CTA banner). No page-type rule for which one applies where. | `static/css/main.css` — `.btn-primary` (~L1378), `--accent-bright` (`:root`), `--green-dark` usages | P3 — theme unity | ✅ **Fixed** — @user decided: sage. Added master `--btn-primary`/`--btn-primary-hover`/`--btn-primary-text` variables to `:root`; repointed `.btn-primary`, `.score-entry-cta`, `.dash-card--cta`, `.ap-checklist-banner .btn-primary`, and the landing page's `.lp-btn-primary` at them. See Technical Reference "Visual Theme" section for the full writeup. `.start-next-banner .btn-primary` (white-on-dark-banner) intentionally left as a contrast-only override, not a competing brand color. |
| F4 | **False urgency on admin buttons.** `.admin-action-btn--submissions` (used by Submissions / Sub Requests / Registrations) always renders in the amber "needs attention" style regardless of whether the pending count is actually >0 — only the numeric badge is conditional, the alarming color isn't. | `templates/admin/season.html:58,62,93`; `static/css/main.css:4044` (`.admin-action-btn--submissions`) | P3 — user friction | ✅ **Already resolved** — the class no longer exists anywhere in templates or CSS; the old tile-grid/More-Tools Admin Panel it lived on was replaced by the tabbed rebuild in the commits this session had missed. No action needed. |
| F5 | **Narrow auth/marketing pages strand content on the left of wide viewports.** `/login`, `/create-league`, `/compare`, `/formats` all cap content at ~480–680px without horizontal centering (`/login` has a `.form-page--centered` modifier available and correctly uses it; the other three don't apply it or an equivalent). On a 1440px display this leaves ~700–950px of dead space to the right — reads as unfinished rather than intentionally minimal. | `templates/create_league.html`, `templates/compare.html`, `templates/formats.html` | P3 — user friction | ✅ **Fixed** `090ba1b` — `compare.html`/`formats.html` already had `.form-page--centered` from the upstream work this session had missed; `create_league.html` was the one holdout, added it. |
| F6 | **Three overlapping navigation surfaces covering mostly the same ground.** Dashboard grid (~17 tiles), Admin Panel quick-actions + "More Tools" (~25 links), and the hamburger drawer (~30 links, nested) all route to largely the same destinations with no single one being canonical. Not a bug, but the single largest structural navigation cost found. | `templates/dashboard.html`, `templates/admin/season.html`, `templates/base.html` (drawer) | P3 — navigation (structural) | **Open** — the Admin Panel side of this changed shape (now tabbed, not tile-grid) in the upstream rebuild, so the specific overlap has shifted, but the 3-surfaces-covering-the-same-ground structure is still real. Needs @user's call on which surface is canonical before restructuring anything. |
| F7 | **Minor / low-priority:**<br>• Some list pages show an inline admin "⚙ Manage" shortcut next to the title (Announcements); others with an equivalent admin route don't (Hall of Fame had `hall_of_fame.admin_list` but no inline link to it).<br>• `<link rel="stylesheet" href="https://fonts.googleapis.com/...">` in `<head>` is render-blocking by nature of being a stylesheet link (mitigated already with `display=swap` + `rel="preconnect"`, so not a strong finding — just worth remembering if Google domains are ever slow/blocked for a real user, page paint stalls behind it). | `templates/announcements/*.html` vs `templates/hall_of_fame/*.html`; `templates/base.html:19-21` | P4 | ✅ **Hall of Fame bullet fixed** `090ba1b` — added the same "⚙ Manage" pattern (`hall_of_fame.py`'s `index()` now passes `current_season_id`). Font-loading bullet left as-is — already mitigated, not worth churning for.|

### Ruled out (do not re-chase)

- **Nav drawer appearing "cut off" partway down in a full-page screenshot** — `.nav-drawer`/`.nav-drawer-overlay` are correctly `position: fixed`; a full-page Playwright capture only renders fixed elements within one viewport-height window at the top by design, so the rest of the capture shows normal page content underneath. Confirmed correct in a real (non-full-page) screenshot with the drawer open at a scrolled position — it covers the entire visible viewport as expected. Not a bug.
- **Standings sub-nav "🏆 Podium" tab appearing color-highlighted vs. its siblings** — it's the trophy *emoji* rendering in its native color (browsers always render emoji in color regardless of surrounding text color); the tab uses the exact same `.subnav-link` class as every other tab, no special CSS. Not a bug.

---

## Navigation State Check — "flattened Stats" nav (@user's specific question)

@user recalled a possible recent change by another agent/session that removed the nested "Stats & Records" hamburger group in favor of a single flat "Stats" link pointing at a directory-style stats page, and asked this be documented so that change (if it exists somewhere) can be diffed against this baseline.

**Correction from the original version of this doc:** the first pass of this check was run against a stale local checkout (~70 commits behind `origin/main` — see the post-merge correction at the top of this doc) and concluded, wrongly, that the flattening didn't exist anywhere. It does — @user's memory was correct. After merging `origin/main` (clean, no conflicts), the current `templates/base.html` nav drawer looks like this:

```html
<!-- templates/base.html, current (post-merge, main) -->
{# Stats — direct link to the flat, categorized stats/reports directory
   instead of a nested dropdown; category subnavs live on the landing
   pages themselves. Styled like the group buttons below (League,
   Community, Admin) rather than a nested .nav-drawer-item, since it
   sits at that same top level — just without a chevron, since it's
   a single link rather than an expandable group. #}
<a href="{{ url_for('stats.index') }}" class="nav-drawer-group-btn nav-drawer-group-btn--link">Stats &amp; Records</a>
```

That's a single flat link (no chevron, no expand/collapse, no subgroups) straight to `stats.index` — a directory-style landing page (`templates/stats/index.html`, added in the same commit) that itself hosts sub-navs (`_league_subnav.html`, `_individual_subnav.html`) for the individual stats pages, matching GLT's flat statistics-directory pattern. This replaced the nested "Stats & Records" → "Leaderboards & Records"/"Player Analysis" two-level dropdown that the original (stale) version of this doc found and mistook for current.

**The actual relevant commits** (both on `main`, both were missing from this session's stale checkout, both present after the merge):
- `596b617` — *"Nav bar: hamburger to the right, de-nest Stats & Records drawer group"*
- `4e45a5d` — *"Restructure Stats nav to mirror GLT's flat statistics directory"*

For the record, `62a3c4e` (*"Nest Stats & Records nav into subgroups"*) — the commit the original version of this doc pointed to as "the only stats-nav commit, and it's the opposite direction" — is real and did happen, earlier, but was superseded by the two commits above. So both directions happened, in sequence: flat → nested (`62a3c4e`) → flat again (`596b617`/`4e45a5d`). The original doc only had visibility into the first transition because its checkout predated the second one.

**No further action needed on this specific question** — the state is now confirmed directly from current `main`, not inferred from a stale checkout or git-log archaeology. If a *different* environment/session/branch still shows the nested version, that one is what's behind, not this repo.

---

## Fix pass — 2026-08-05, same day, commit `090ba1b`

@user confirmed the stale-checkout finding above matched their memory and said to fix the rest. Applied:
- **F1**: `routes/archive.py` — added `t.team_name, p1.first_name, p1.last_name, p2.first_name, p2.last_name` to the `GROUP BY` clause.
- **F2**: `templates/admin/email_settings.html` — back-link now uses `url_for('admin.landing')` instead of `url_for('admin.panel')`.
- **F5**: `templates/create_league.html` — added the `.form-page--centered` modifier (matching `compare.html`/`formats.html`, which already had it from upstream work).
- **F7** (Hall of Fame bullet only): `routes/hall_of_fame.py`'s `index()` now passes `current_season_id`; `templates/hall_of_fame/index.html` gained the same admin-only "⚙ Manage" link pattern `announcements/index.html` uses.

All four verified against a locally running dev server (real HTTP 200s, not just code review) — `/archive/` and `/admin/email/` render without error, `/create-league` is horizontally centered at 1440px, and Hall of Fame's Manage link resolves to `/admin/season/<id>/hall-of-fame`.

**F4 needed no fix** — already resolved by the upstream Admin Panel rebuild this session had missed; the class it referenced doesn't exist anymore.

**F3 and F6 intentionally left open** — both are sitewide design/product decisions (which button color is canonical; which nav surface is canonical), not something to unilaterally resolve while fixing bugs. Flag to @user separately if/when worth scoping.
