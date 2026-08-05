# Desktop UI/UX Audit — 2026-08-05

**Type:** Audit Finding
**Status:** Open
**Priority:** P1 (F1, F2 — live 500s), P3 (F3, F4, F6), P4 (F5, F7)
**Prepared by:** Sonnet, 2026-08-05
**Linked WP:** none yet — log against WP3.1 (backlog) if/when scoped for a fix pass
**Scope of this pass:** desktop viewport (1440×900) only. No mobile/tablet pass done here. No code changes made — audit only, per explicit request.

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

| ID | Finding | Location | Severity |
|----|---------|----------|----------|
| F1 | **`/archive/` 500s unconditionally.** `_season_stats()`'s `top_team` query selects `t.team_name` + two player-name columns while only grouping by `mr.team_id` — Postgres rejects this at plan time (`GroupingError: column "t.team_name" must appear in the GROUP BY clause`). Fails on every call, every league, regardless of data. Linked from the Dashboard tile, Admin Panel → More Tools, and the nav drawer's League group. | `routes/archive.py:104-115` (`_season_stats`) | **P1 — live bug** |
| F2 | **`/admin/email/` (Email Settings) 500s outright.** The template's "← Admin Panel" back-link calls `url_for('admin.panel')` with no `season_id`, but that endpoint requires one (`werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'admin.panel'. Did you forget to specify values ['season_id']?`). Page is currently unreachable via its own "More Tools" link. | `templates/admin/email_settings.html:6` → `routes/email_config.py:295` (`settings()`) | **P1 — live bug** |
| F3 | **Three competing "primary action" colors, no single canonical one.** Terracotta (`--accent-bright`, homepage hero CTAs only) vs. light sage (`#bcd6ab`, `.btn-primary` — the actual default on Sign In, Create League, Add Contest, New Topic, Save Settings, etc.) vs. dark green (`--green-dark` — nav bg + a few "hero" CTA components like Score Entry/Print Scorecards cards, dashboard admin CTA banner). No page-type rule for which one applies where. | `static/css/main.css` — `.btn-primary` (~L1341), `--accent-bright` (`:root`), `--green-dark` usages | P3 — theme unity |
| F4 | **False urgency on admin buttons.** `.admin-action-btn--submissions` (used by Submissions / Sub Requests / Registrations) always renders in the amber "needs attention" style regardless of whether the pending count is actually >0 — only the numeric badge is conditional, the alarming color isn't. | `templates/admin/season.html:58,62,93`; `static/css/main.css:4044` (`.admin-action-btn--submissions`) | P3 — user friction |
| F5 | **Narrow auth/marketing pages strand content on the left of wide viewports.** `/login`, `/create-league`, `/compare`, `/formats` all cap content at ~480–680px without horizontal centering (`/login` has a `.form-page--centered` modifier available and correctly uses it; the other three don't apply it or an equivalent). On a 1440px display this leaves ~700–950px of dead space to the right — reads as unfinished rather than intentionally minimal. | `templates/create_league.html`, `templates/compare.html` (or equivalent), `templates/formats.html` — missing `.form-page--centered` or equivalent | P3 — user friction |
| F6 | **Three overlapping navigation surfaces covering mostly the same ground.** Dashboard grid (~17 tiles), Admin Panel quick-actions + "More Tools" (~25 links), and the hamburger drawer (~30 links, nested) all route to largely the same destinations with no single one being canonical. Not a bug, but the single largest structural navigation cost found. | `templates/dashboard.html`, `templates/admin/season.html`, `templates/base.html` (drawer) | P3 — navigation (structural, no quick fix) |
| F7 | **Minor / low-priority:**<br>• Some list pages show an inline admin "⚙ Manage" shortcut next to the title (Announcements); others with an equivalent admin route don't (Hall of Fame has `hall_of_fame.admin_list` but no inline link to it).<br>• `<link rel="stylesheet" href="https://fonts.googleapis.com/...">` in `<head>` is render-blocking by nature of being a stylesheet link (mitigated already with `display=swap` + `rel="preconnect"`, so not a strong finding — just worth remembering if Google domains are ever slow/blocked for a real user, page paint stalls behind it). | `templates/announcements/*.html` vs `templates/hall_of_fame/*.html`; `templates/base.html:19-21` | P4 |

### Ruled out (do not re-chase)

- **Nav drawer appearing "cut off" partway down in a full-page screenshot** — `.nav-drawer`/`.nav-drawer-overlay` are correctly `position: fixed`; a full-page Playwright capture only renders fixed elements within one viewport-height window at the top by design, so the rest of the capture shows normal page content underneath. Confirmed correct in a real (non-full-page) screenshot with the drawer open at a scrolled position — it covers the entire visible viewport as expected. Not a bug.
- **Standings sub-nav "🏆 Podium" tab appearing color-highlighted vs. its siblings** — it's the trophy *emoji* rendering in its native color (browsers always render emoji in color regardless of surrounding text color); the tab uses the exact same `.subnav-link` class as every other tab, no special CSS. Not a bug.

---

## Navigation State Check — "flattened Stats" nav (@user's specific question)

@user recalled a possible recent change by another agent/session that removed the nested "Stats & Records" hamburger group in favor of a single flat "Stats" link pointing at a directory-style stats page, and asked this be documented so that change (if it exists somewhere) can be diffed against this baseline.

**As of `main` @ `1d06b83` (this session's HEAD, 2026-08-05): that change does not exist.** The nav drawer still renders a nested, collapsible **"Stats & Records"** group with two sub-groups inside it — confirmed both from live source and from this audit's own screenshot (`40_nav_drawer_open.png`):

```html
<!-- templates/base.html, current -->
<button class="nav-drawer-group-btn" onclick="navToggleGroup(this)">
    <span>Stats &amp; Records</span><span class="nav-drawer-chevron">›</span>
</button>
<div class="nav-drawer-group-items">
    <button class="nav-drawer-subgroup-btn">Leaderboards &amp; Records</button>
    <div class="nav-drawer-subgroup-items">
        <a href="...">🏆 Leaderboard</a>
        <a href="...">📈 Records</a>
        <a href="...">🏛️ Hall of Fame</a>
        <a href="...">💰 Skins</a>
    </div>
    <button class="nav-drawer-subgroup-btn">Player Analysis</button>
    <div class="nav-drawer-subgroup-items">
        <a href="...">🧮 Handicaps</a>
        <a href="...">📊 Season Stats</a>
        <a href="...">🕳️ Hole Averages</a>
        <a href="...">⚖️ Season Comparison</a>
        <a href="...">📅 Participation</a>
        <a href="...">⚔️ Compare Players</a>
        <a href="...">👤 My Stats</a> <!-- only if session.player_id -->
    </div>
</div>
```

Checked for any trace of a flattening change and found none:
- **Git history (`git log --all --oneline -i --grep=stats`)**: the only stats-nav-structural commit on record is `62a3c4e` — *"Nest Stats & Records nav into subgroups (Leaderboards & Records / Player Analysis)"* — which is the **opposite** of what's being recalled (it's what *created* today's nested structure). No later commit reverses or flattens it.
- **Branches (`git branch -a`)**: only `main` and `claude/supabase-db-connector-tk0xc4` exist locally/remotely; neither has divergent nav code.
- **PM docs** (`Plans/`, `Handoffs/`, `Audits/`): no plan or handoff proposing a flat stats directory page found in a title/content grep across all three folders.

**Most likely explanations, in order of likelihood:** (a) @user is recalling commit `62a3c4e` itself and inverted the direction in memory (nested ≠ flattened), (b) the remembered change happened in a different session/branch/environment that never got merged to this repo, or (c) it was discussed/planned but never actually implemented. Whichever it is — **this document is the baseline to diff against.** If another agent has (or produces) a version with a flat "Stats" link + directory page, compare its `templates/base.html` nav-drawer markup against the block quoted above to confirm it's a real, intentional divergence and not a partial/broken edit.

---

## Scope (if a fix pass is ever run against this doc)

**Not in scope for this document — audit only, no changes made.** If picked up later:
- F1/F2 are one-line fixes each (add missing `GROUP BY` columns or aggregate; pass `season_id` into the `url_for` call) — lowest-risk, highest-value first pass.
- F3 (color unification) and F6 (nav consolidation) are judgment calls requiring a decision from @user on which convention wins — do not unilaterally pick one.
- F4, F5, F7 are small, independent, low-risk template/CSS edits — safe to batch together.
