# UI/UX Overhaul — Clean, Modern Redesign

*Status: `In Progress` — Phase 1 shipped 2026-07-16 (`27965b4`), UI fix batch shipped 2026-07-16 (`6a92e51`), Phase 2 (landing hero) shipped 2026-07-16*
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

### Phase 3 — App shell + dashboard *(planned)*
- Dashboard: currently a wall of equal-weight emoji tiles. Introduce hierarchy
  (primary actions emphasized, secondary grouped), cleaner cards, consistent
  icon treatment. Consider a real icon set vs. the current emoji.
- Nav drawer: modernize styling; keep the grouping (it works).
- Standardize the page-header pattern (title / subtitle / actions).

### Phase 4 — Data-dense pages *(planned)*
- Standings, records, stats, players, schedule tables: cleaner table styling
  (zebra, sticky headers, tabular figures, spacing), consistent form/settings
  styling. **Excludes scorecard column spacing.**
- There are many scattered per-page input/focus/button overrides in `main.css`
  (dozens of context-specific rules) — Phase 4 is where those get consolidated
  toward the Phase-1 primitives, page by page, with screenshots each time.

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
