# Mobile Nav Redesign & Visual Theme Options

**Status:** Nav — **Archived** (Decision: Large Nested Hamburger, shipped `b562b58`) · Themes — **Evaluating**

## Why

The first mobile nav shipped this session (`88cb5f7` — a sticky two-tier subheader replacing the hamburger for content nav on mobile) worked, but @user wanted to see it against genuinely different structural alternatives before treating it as final, and separately wanted to compare full palette/type options against the current Sage & Terracotta theme. Two live, interactive review artifacts were built for this rather than static mockups, so options could be tapped/switched through directly instead of described. Both artifacts are kept live and up to date as a running record of every option considered — not just the one picked.

## Artifact 1 — Six Ways to Wayfind (mobile nav patterns) — DECIDED

**https://claude.ai/code/artifact/3961108d-b14c-4edb-a7d7-5bf92e712a96**

Six structurally distinct mobile nav patterns, each a working interactive phone mockup built from the site's real content (all ~40 nav items across League / Stats & Records [with its two subgroups] / Community / Admin / Account). Kept live with all six intact — this is the full record of what was considered, not just the winner:

1. **Scorecard Tabs** — the first thing shipped. Sticky tier-1 tabs, tier-2 reveal row per group. Later refined in the same artifact (before being superseded) so "Stats & Records" routed to a dedicated Stats home instead of a tier-2 reveal.
2. **Bottom Dock** — 4 thumb-zone icons (Schedule/Standings/Score Entry/Stats) + a "More" bottom sheet for everything else.
3. **Mega Grid** — full-screen section cards that expand in place, no second screen.
4. **Mini Dock + Accordion** — icon-only strip, expands inline in the page (no overlay).
5. **Command Palette** — search-first, all 40 items filterable by typing; built for admins who already know where they're going.
6. **Large Nested Hamburger** — modeled on a real competitor (GLT). **Chosen.**

### Decision (2026-07-28)

@user named two front-runners — Scorecard Tabs and Large Nested Hamburger (marked ★ in the artifact) — then chose **Large Nested Hamburger** and asked to ship it for real, replacing Scorecard Tabs outright rather than running both.

**Implemented as `b562b58`.** Turned out to be almost entirely *removal*, not new code: the real hamburger drawer already had the exact nested structure the mockup called for (League/Community/Admin/My Account as flat groups, Stats & Records already split into its two real subgroups — Leaderboards & Records, Player Analysis). So shipping it meant deleting the `.mobile-subnav` tier-1/tier-2 markup, CSS, and JS entirely; un-hiding `.nav-drawer-content-groups` on mobile; reverting the header's mobile `position: static` (sticky again, matching desktop); and reverting the drawer's mobile `top:0/height:100vh` override back to the shared `top: var(--nav-height)` rule, which makes it flow down under the sticky header instead of covering it. Net result: mobile and desktop now share identical nav chrome — no mobile-specific nav code left at all.

Per @user's explicit answer during scoping: Stats & Records content stayed as BGLT's own real 11 categories, **not** GLT's ~28-report structure — the GLT-modeled structure lives only in the archived mockup (see below), as the comparison reference it was built for.

### GLT statistics-page research (fed pattern #6, now historical reference)

@user asked for a comparison against Golf League Tracker's real statistics page (`golfleaguetracker.com/glthome/statistics/`). `WebFetch` can't reach authenticated pages (confirmed directly — it fails the site's login wall by design). Found and used the documented access method already recorded in `7. GLT Feature Parity.md` (lines 26-54, confirmed working 2026-07-09): plain `curl` with a realistic `User-Agent` (GLT's bot detection blocks `WebFetch`'s fingerprint specifically, not a sandbox network issue) + cookie jar, GET the target page to land on the login form and capture the anti-forgery cookie, scrape `__RequestVerificationToken` out of the HTML, POST to `/glthome/security/loginaction` with that token + `UserId=Buckeye`/`Password=skypilot` (credentials already `@user`-authorized to store in that doc, 2026-07-04 — low-risk test/demo league account), reuse the cookie jar for the actual target page.

**GLT's real structure, fetched live 2026-07-28:** one long index page, six labeled categories, ~28 total reports, two categories (Standings; Stroke Play and Point Reports) nesting a further nine sub-groups, the other four flat. Verbatim category/report names captured in the artifact's `GLT_NESTED` data object (`mobile-nav-options.html`), used purely as a comparison reference inside the archived Large Nested Hamburger mockup — the real, shipped drawer uses BGLT's own Stats & Records content, not GLT's report list. Full page-by-page parity assessment (built/matched/declined/open, all 36 GLT stats pages) lives in `7. GLT Feature Parity.md` Part 4 → Stats, also rendered as a standalone reference table: **https://claude.ai/code/artifact/cee98de1-6140-4e51-be4f-6e49d0dccf67**.

## Artifact 2 — Palettes on the Same Page (visual theme options) — STILL EVALUATING

**https://claude.ai/code/artifact/2ed29ce2-e552-4d24-add3-3fad5083c2d8**

One shared realistic app mockup (nav bar, primary + secondary CTA, standings card, filter pills, search input), live-re-themed via a switcher — same interaction shape as swapping `main.css`'s `:root` block, which is the actual mechanism this would take to ship. Five presets now (grown from the original four):

1. **Sage & Terracotta** — current shipped palette (`--green-dark`/`--accent`/`--accent-bright`), included as the baseline.
2. **Fairway Drench** — added per @user's follow-up ask for a "color drench" variant: same hue family and typography as the shipped theme, but the whole surface (background, cards, everything) saturated in sage instead of neutral cream with green accents — terracotta reads as one hot pop against an immersive backdrop instead of the only color in the room.
3. **Studio Amber** — the exact palette the review artifacts' own chrome is built in (graphite ground, warm amber accent, serif display face), corrected to render genuinely dark (not a lightened interpretation, per @user's direct feedback) — dropped into the real app as a genuine candidate, not left as just the documents' own styling.
4. **Fescue & Ink** — a deliberate departure from green: sun-bleached fescue gold against scorecard-ink navy.
5. **Clubhouse Brass** — forest-shadow near-black + aged brass, slab serif — a heritage-clubhouse feel distinct from the current softer sage-and-cream take.

Not yet reviewed/decided by @user.

## Next session

- Get @user's read on the theme options artifact; when a preset is chosen (or none), update this doc's status to Archived with the decision, same as the nav side.
- If a new theme preset is chosen, the actual swap is a single `:root` edit in `main.css` (already the site's existing convention — see "Visual Theme" section, `4. Technical Reference.md`) — update that Technical Reference section's palette values and its "History" line (it already documents prior scheme changes — Coastal Slate & Teal, Fairway Gold — this would be the same pattern again).
