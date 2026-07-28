# Mobile Nav Redesign & Visual Theme Options

**Status:** Evaluating

## Why

The shipped mobile nav (`88cb5f7`, this session — a sticky two-tier subheader replacing the hamburger for content nav on mobile) works, but @user wants to see it against genuinely different structural alternatives before treating it as final, and separately wants to compare full palette/type options against the current Sage & Terracotta theme. Two live, interactive review artifacts were built for this rather than static mockups, so options can be tapped/switched through directly instead of described.

## Artifact 1 — Six Ways to Wayfind (mobile nav patterns)

**https://claude.ai/code/artifact/3961108d-b14c-4edb-a7d7-5bf92e712a96**

Six structurally distinct mobile nav patterns, each a working interactive phone mockup built from the site's real content (all ~40 nav items across League / Stats & Records [with its two subgroups] / Community / Admin / Account):

1. **Scorecard Tabs** — what's shipped. Sticky tier-1 tabs, tier-2 reveal row per group.
2. **Bottom Dock** — 4 thumb-zone icons (Schedule/Standings/Score Entry/Stats) + a "More" bottom sheet for everything else.
3. **Mega Grid** — full-screen section cards that expand in place, no second screen.
4. **Mini Dock + Accordion** — icon-only strip, expands inline in the page (no overlay).
5. **Command Palette** — search-first, all 40 items filterable by typing; built for admins who already know where they're going.
6. **Large Nested Hamburger** — modeled on a real competitor. See below.

**Front-runner, per @user (2026-07-28): Scorecard Tabs (#1).** It's already shipped, and its one real gap — Stats & Records needing a flattened 11-item row instead of a clean destination — has since been refined directly in the same artifact: tapping "Stats & Records" now routes to a dedicated Stats home instead of a tier-2 reveal, picked up by a small header badge, with a three-tier filter stack underneath the subheader (category dropdown → dependent sub-category scroller → time range), all in-page with no reload.

### GLT statistics-page research (feeds pattern #6)

@user asked for a comparison against Golf League Tracker's real statistics page (`golfleaguetracker.com/glthome/statistics/`). `WebFetch` can't reach authenticated pages (confirmed directly — it fails site's login wall by design). Found and used the documented access method already recorded in `7. GLT Feature Parity.md` (lines 26-54, confirmed working 2026-07-09): plain `curl` with a realistic `User-Agent` (GLT's bot detection blocks `WebFetch`'s fingerprint specifically, not a sandbox network issue) + cookie jar, GET the target page to land on the login form and capture the anti-forgery cookie, scrape `__RequestVerificationToken` out of the HTML, POST to `/glthome/security/loginaction` with that token + `UserId=Buckeye`/`Password=skypilot` (credentials already `@user`-authorized to store in that doc, 2026-07-04 — low-risk test/demo league account), reuse the cookie jar for the actual target page.

**GLT's real structure, fetched live 2026-07-28:** one long index page, six labeled categories, ~28 total reports, two categories (Standings; Stroke Play and Point Reports) nesting a further nine sub-groups, the other four flat. Verbatim category/report names captured in the artifact's `GLT_NESTED` data object (`mobile-nav-options.html`) for exact reuse if this direction is pursued further. Pattern #6 (Large Nested Hamburger) brings this structure into the hamburger drawer itself — League/Community/Admin/Account stay flat single-tap links, "Stats" is the one item with real depth, expanding through GLT's actual category → sub-group → report hierarchy without leaving the drawer.

**Open note on #6:** most of GLT's 28 reports don't have a direct BGLT equivalent yet — the mockup uses GLT's real names verbatim (not invented BGLT report names), so treat it as "what adopting GLT's index shape would look like," not a claim that BGLT already has all 28 reports built.

## Artifact 2 — Four Palettes on the Same Page (visual theme options)

**https://claude.ai/code/artifact/2ed29ce2-e552-4d24-add3-3fad5083c2d8**

One shared realistic app mockup (nav bar, primary + secondary CTA, standings card, filter pills, search input), live-re-themed via a switcher — same interaction shape as swapping `main.css`'s `:root` block, which is the actual mechanism this would take to ship. Four presets:

1. **Sage & Terracotta** — current shipped palette (`--green-dark`/`--accent`/`--accent-bright`), included as the baseline.
2. **Studio Amber** — the exact palette the review artifacts' own chrome is built in (graphite ground, warm amber accent, serif display face), dropped into the real app as a genuine candidate, not left as just the documents' own styling — built "for kicks" per @user, who liked the review artifacts' own look enough to ask for it as an option.
3. **Fescue & Ink** — a deliberate departure from green: sun-bleached fescue gold against scorecard-ink navy.
4. **Clubhouse Brass** — forest-shadow near-black + aged brass, slab serif — a heritage-clubhouse feel distinct from the current softer sage-and-cream take.

Not yet reviewed live by @user — built alongside the nav-pattern work, no decision made.

## Next session

- Get @user's read on the theme options artifact.
- If Scorecard Tabs + the Stats-home refinement is confirmed as final (not just front-runner), implement the Stats-home page for real (`app/routes/stats.py` or wherever the actual Stats & Records routes live — not yet located/scoped this session) and remove the tier-2 reveal special-case for that one tab in `base.html`/`main.css`.
- If a new theme preset is chosen, the actual swap is a single `:root` edit in `main.css` (already the site's existing convention — see "Visual Theme" section, `4. Technical Reference.md`) — should update that Technical Reference section's palette values and note the "History" line (it already documents prior scheme changes — Coastal Slate & Teal, Fairway Gold — this would be the same pattern again).
