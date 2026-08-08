# UI/UX Overhaul — Clean, Modern Redesign

*Status: `In Progress` — Phase 1 shipped 2026-07-16 (`27965b4`), UI fix batch shipped 2026-07-16 (`6a92e51`), Phase 2 (landing hero) shipped 2026-07-16, Phase 3 (dashboard hierarchy) shipped 2026-07-16, Phase 4 (data-table cascade fix) shipped 2026-08-08 — see Phase 4 below for why the broader table-polish scope was closed out rather than built*
*Owner: @claude, on Opus (Planner). Requested by @user 2026-07-16.*

-----

## Goal

Make the site cleaner and more modern — UI + content organization — on both
desktop and mobile. Cleaner font site-wide. Special attention to the landing
page (the dark-hero-box-on-light-background was the specific eyesore @user
called out).

## Direction decided (@user, 2026-07-16)

Chosen via a 3-question review after seeing a landing draft:

- **Font: Inter** (site-wide). Chosen over Figtree (drafted) and keeping Nunito
  Sans. Cleaner/crisper, excellent on the app's data-dense tables.
- **Background: soften off the saturated lime tint** (`#f4fee5`) to a clean
  near-white (`#f7f8f4`). Lime becomes an accent, not the whole page.
- **Landing skeleton: NOT yet.** @user explicitly said don't ship a new landing
  skeleton yet — do the font + de-tint + polish first, land the new landing
  separately. So `home.html` is untouched and still shows its current dark hero
  box; it just inherits the new font + background.

## Hard constraint

**Do NOT touch scorecard column spacing** (@user worked hard on it). Off-limits
CSS in `app/static/css/main.css`: `.scorecard-table`, `.sc-col-*`, `.sc-name-*`,
`.sc-summary-cell`, `--sc-summary-w`, `.col-player-name`, and their mobile media
queries (roughly lines 1921–2216, 3867–3884, 4633–4715, 8489–8491). These
columns are fixed-width (`table-layout: fixed`) so the font change can't reflow
them.

-----

## Phased roadmap

### Phase 1 — Foundation *(SHIPPED 2026-07-16, `27965b4`)*
- Inter font site-wide (base.html link + `body` font-family + antialiasing).
- App background `#f4fee5` → `#f7f8f4` (clean near-white); softened border
  tokens; added `--shadow-sm` / `--shadow-md`.
- Primitive polish, **visual-only, no layout/size changes**: `.card-section`
  and `.dash-card` get soft shadows + hover lift; `.btn` gets transition +
  active press; `.form-group input/select` get cleaner borders, matching
  8px radius, and a green focus ring.
- Verified across landing, login, dashboard, standings, schedule via real
  screenshots. Zero scorecard rules in the diff (checked).

### Phase 2 — Landing page redesign *(SHIPPED 2026-07-16)*
The drafted light-hero landing shipped as `home.html`. Key moves:
- Kills the dark hero box. Light, airy hero on a soft lime→white gradient that
  is *part of the page*, not a floating dark card.
- Dark green reserved for the nav + a closing "strip" (bookends the page).
- A product-preview visual (styled mini-standings card) as the hero anchor.
- Feature cards grid (4→2→1 responsive), bright lime reserved for the primary CTA.
- Full-bleed hero on mobile (edge to edge, not a floating card) via a
  `max-width:640px` breakpoint that cancels the page's side margins.
- Kept @user's approved headline/subhead copy verbatim. Swapped the closing
  strip's tagline from the draft's reused "Less work. More golf." (removed
  as a subtitle earlier in the project) to "Ready when your league is."
  instead of relitigating that removal.
- Mapped the draft's standalone color tokens onto the site's real CSS custom
  properties (`--green-dark`, `--accent-bright`, etc.) instead of hardcoded
  duplicate hex, so it stays in sync with future palette tweaks.
- Deleted the now-obsolete `.landing-hero*` / `.home-cta-row` / `.home-feature-list`
  rules from `main.css` (confirmed dead — no other template referenced them).
- Verified via real Playwright screenshots at desktop (1400px) and mobile
  (390px). Zero scorecard-column-spacing rules touched.

### Phase 3 — App shell + dashboard *(SHIPPED 2026-07-16)*
- Dashboard admin view restructured from one flat wall of ~24 equal-weight
  tiles into three tiers: a **Primary** grid (Score Entry, Schedule,
  Standings, Players — larger cards, bigger icon/label, the pages an admin
  opens every week), an **Admin Tools** section (Submissions, Print
  Scorecards, Manage Users, Admin Panel, Skins, Dues — still tinted green,
  denser cards), and a **More** section (everything else — Courses,
  Playoffs, Archive, Records, stats pages, Reports, Contests, League Info,
  Announcements, Forum, Compare Players, My Account/Sub Requests/Stats),
  each under a small uppercase section label. New CSS: `.dash-section-label`,
  `.dash-primary-grid`, `.dash-more-grid`, `.dash-cta-banner` — additive
  modifiers layered on the existing `.dash-card`/`.dashboard-grid` base, so
  `seasons/setup.html` (the only other consumer of those base classes) is
  unaffected. Member (non-admin) dashboard view untouched — it already
  showed widgets only, no tile wall, per Phase-1-era design.
- Nav drawer styling and page-header pattern (title/subtitle/actions) were
  already modernized/standardized by the earlier UI fix batch and the
  pre-existing `.page-header` convention (used across 115 templates already)
  respectively — nothing further needed here.
- Kept emoji icons rather than introducing an icon-font/SVG-set dependency —
  lowest-risk choice; revisit only if a real icon set becomes a priority.
- Verified via real Playwright screenshots at desktop (1400px) and mobile
  (390px, session-cookie transplant). Zero scorecard rules touched.

### Phase 4 — Data-dense pages *(SHIPPED 2026-08-08, scope closed rather than fully built)*
- **`.data-table` cascade bug fixed.** `main.css` had two conflicting rule
  blocks for `.data-table th`/`td` — the original at ~line 544 (light gray
  header, off-palette hex left over from before the 2026-07-19 Sage &
  Terracotta swap: `#ddd`/`#f9f9f9`/`#666`/`#f0f0f0`) and an unscoped override
  later in the file (~line 5277, inside a Manage Users CSS section) that
  silently won the cascade and repainted every `.data-table th` site-wide dark
  green. Not a bug introduced this session — a pre-existing quirk, first
  flagged when this phase was originally planned. Merged into one canonical
  block at the original location; the rendered result is unchanged (still the
  dark-green header everyone's used to seeing), but the hardcoded off-palette
  grays now reference the established tokens (`--card-bg`, `--border`,
  `--green-dark`) instead of literal hex, per the site's existing
  scheme-portability convention (see "Visual Theme" in Technical Reference).
- **Broader table-polish scope (zebra striping, sticky headers, tabular
  figures, consolidating scattered per-page input/focus/button overrides)
  evaluated and deliberately not built.** Per @user (2026-08-08): no clear
  issue was found to justify it — "let sleeping dogs lie." The zebra-striping
  risk flagged when this phase was first planned still applies if it's
  revisited later: a blanket `tbody tr:nth-child(even)` rule would fight
  existing row-state classes like `.row-completed` (schedule detail table sets
  its own row background) across the 50 templates using `.data-table`, so it'd
  need a page-by-page pass with screenshots, not a global rule — treat as a
  fresh scoping exercise if a real need shows up, not a resumption of this
  plan.

### Phase 5 — Polish *(planned)*
- Empty states, focus/hover states everywhere, consistent iconography, optional
  dark-mode consideration.

-----

## Notes / decisions log
- "Polish" in Phase 1 was deliberately scoped to color/shadow/border/transition/
  typography — i.e. visual-only, non-layout-shifting — because `main.css` is
  ~8,700 lines with many page-specific rules; broad padding/size changes would
  be regression-prone. Deeper per-component unification is Phase 3/4 work, done
  incrementally with screenshots.
- The landing draft's font is Inter in the preserved file? No — it was drafted
  under Figtree, but Phase 1 standardized on Inter. When Phase 2 ships, the
  landing will inherit Inter automatically (the draft's scoped styles don't pin
  a font family except via inheritance).
