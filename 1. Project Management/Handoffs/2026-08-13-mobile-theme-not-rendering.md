# Handoff: Mobile dark theme tokens deployed correctly but not visually applying on real devices

*Status: `Blocked`*
*Created: 2026-08-13 — Planner: Sonnet 5 (this session, background job)*
*Priority: `Medium` — Effort: `Unknown` (could be a one-line fix or a real cross-browser investigation)*
*Depends on: None*
*Parallel-safe: `Yes`*

-----

## Goal

Get "Fairway Drench 1st Alternate" (a dark two-tone color scheme) actually rendering on mobile web (`@media (max-width: 768px)`), while desktop stays on Sage & Terracotta unchanged. The CSS is written, deployed, and verifiably correct by every remote check available — but does not visually apply on @user's real device in two different browsers. **This needs either real browser DevTools (remote-debug an actual iPhone) or Cloudflare dashboard access — neither of which this session has.**

## Context

@user asked to ship a theme built in an interactive theme-customizer artifact (`Artifacts/2026-07-29-theme-options.html`) to mobile web only. The mechanism: a `@media (max-width: 768px) { :root { --bg: ...; --card-bg: ...; etc. } }` block in `app/static/css/main.css`, positioned after the base `:root` block, redefining the shared design-token custom properties the rest of the site already uses.

Three real bugs were found and fixed over several iterations tonight (all already pushed to `main`, all confirmed live):
1. The mobile `:root` override itself — correct from the start, verified working via a temporary diagnostic probe (see below).
2. `home.html`'s `.lp-hero`/`.lp-btn-ghost` had **hardcoded literal colors** (`#ffffff`, `#fff`) bypassing the shared tokens entirely — fixed with a matching mobile override scoped to those two rules.
3. That fix was initially placed **before** the original rules in source order — CSS cascade tiebreaking (equal specificity, later-wins) meant the original always won regardless of the media query matching. Fixed by moving the override after the originals.

**After all three fixes, @user still sees the unchanged light "Sage & Terracotta" scheme** — confirmed independently in **two different browsers** (Chrome iOS incognito, Safari iOS private) on an iPhone 16 Pro Max, on both the logged-in admin panel (`/admin/season/<id>`) and the logged-out marketing homepage (`/`). A screenshot (not reproduced here, but described below) showed every overridden token still resolving to its light value — body background cream not near-black, cards white not dark, the "Admin Panel" badge pale gold not translucent dark gold, the active tab pill light sage not dark green — **while a separate, simpler CSS rule under the identical `@media (max-width: 768px)` condition, in the same stylesheet, was confirmed firing correctly** (see diagnostic probe below).

As a last-resort forcing move, `!important` was added to every declaration in the mobile `:root` override block (commit `8a8b1ab`) — confirmed deployed and byte-correct via direct `curl`. **Confirmed this did NOT fix it.** @user tested in Safari iOS private mode (a second, independent browser from the earlier Chrome test) on this exact build — the footer probe read "Build 8a8b1ab · up since 2026-08-13 01:08 UTC · viewport: mobile scheme active" (confirming both the correct build *and* the media query matching), while the hero/page colors were still reported as unchanged light Sage & Terracotta immediately before that probe check. **`!important` failing is the single strongest data point in this whole investigation** — it should be close to unbeatable in a normal CSS cascade, so this now looks less like a specificity edge case and more like something structurally different: a second stylesheet/cache layer this session hasn't found, a Service Worker intercepting the CSS response independent of HTTP caching, or a genuine, unusual WebKit rendering bug that needs real inspection tools to see.

## Findings / Evidence (everything already ruled out — do not re-derive)

- **Deploy pipeline is fine.** Checked via the `render-api` MCP connector (needs a fresh session — this conversation's own connector was stale from before a key rotation; spin up `claude --bg` with `--allowedTools` pre-approving `mcp__render-api__*` read tools if you need to re-check). All recent deploys show `status=live`, matching commits, no stuck/failed deploys.
- **The live CSS is correct, byte-for-byte, at every point checked.** Direct `curl https://bettergolfleague.com/static/css/main.css?v=<current>` repeatedly confirmed the exact intended content — correct values, correct `@media` nesting, correct source order relative to the rules it overrides, no stray characters (`cat -A` checked for invisible/encoding issues — clean).
- **No competing rule anywhere in the ~8,850-line `main.css`.** Exhaustively grepped for every token touched (`--bg`, `--card-bg`, `--border`, `--border-dark`, `--text`, `--text-muted`, `--text-faint`, `--btn-primary` family, `--admin-accent-bg`, `--admin-accent-text`, `--shadow-sm`, `--shadow-md`) — each is defined in exactly two places: the base `:root` and this one mobile override. No third definition, no duplicate `.role-badge--league_admin` rule (the exact class of bug — a duplicate rule silently winning the cascade — that has bitten this codebase before, see Technical Reference's `.data-table` cascade note from 2026-08-08; checked for it specifically here and it isn't present).
- **Cloudflare is not the problem.** Response headers checked directly: the HTML page is `cf-cache-status: DYNAMIC` (never cached by Cloudflare, always passed to origin). The CSS file showed `cf-cache-status: REVALIDATED` with a `last-modified` timestamp matching the exact deploy time — i.e. Cloudflare's cache is confirmed fresh, not stale.
- **A diagnostic CSS-only probe confirms the media query itself matches on @user's device.** Added to the site footer (`app/templates/base.html`, `.viewport-probe--mobile`/`--desktop` classes in `main.css`'s `.site-footer-build` section) — two spans, one shown only under `@media (max-width: 768px)`, the other only outside it. On the Chrome iOS test (screenshot), it correctly showed "mobile scheme active" — **while every color token in the exact same stylesheet, under the exact same media condition, was still resolving to its light-theme value.** This is the core mystery: two rules under an identical `@media (max-width: 768px) { ... }` condition, in the same file, one applies and one doesn't.
- **`!important` was added as a forcing move** (commit `8a8b1ab`) on the theory that this is some kind of specificity/cascade resolution edge case (possibly WebKit-specific — all iOS browsers, including "Chrome iOS," use WebKit under the hood, so testing two different iOS browser *apps* does not test two different rendering engines and does not by itself rule out a WebKit-specific bug). This is unverified — see Immediate Next Step.

## Current Hypothesis (unconfirmed, ranked)

1. **Most likely, given the evidence pattern:** some WebKit-specific bug or edge case with CSS custom properties redefined on `:root` inside a media query, when other rules in the same stylesheet already reference those properties via `var(--x, fallback)` with a literal fallback baked in (nearly every consumer of these tokens in `main.css` is written as `var(--bg, #f8f6f0)`-style with a hardcoded light-theme fallback — worth specifically testing whether removing the fallback values, or restructuring to avoid the redundant fallback, changes behavior). Not confirmed; no way to test without real device/simulator DevTools.
2. **Possible but weaker:** something about Private/Incognito browsing mode specifically alters viewport/media-query evaluation on iOS (would be unusual and undocumented, but hasn't been tested in a normal, non-private tab — worth asking @user to try one normal, non-private tab as a control, since every test so far has been in a private/incognito context on both browsers).
3. **Ruled out:** deploy staleness, Cloudflare caching, CSS syntax errors, cascade/source-order conflicts, duplicate rules, browser cache (multiple independent private-mode tests).

## Immediate Next Step (do this first, cheap, before anything else)

Ask @user directly: **on the most recent Safari private test, what did the footer probe say — "mobile scheme active" or "desktop scheme active"?** This single data point splits the investigation in two completely different directions:
- If **"mobile scheme active"**: the `!important` build (`8a8b1ab`) either fixed it (ask them to hard-check again, this exact build, since their report may predate it going live) or the mystery is even deeper than a specificity issue and needs real DevTools.
- If **"desktop scheme active"**: this is a completely different, more mundane problem (the media query genuinely isn't matching in Safari) — check for "Request Desktop Website" being toggled on, or an actual viewport-width discrepancy, not a cascade bug at all.

## What This Needs That This Session Doesn't Have

- **Real device or simulator DevTools** (Safari Web Inspector via a Mac connected to the iPhone, or iOS Simulator) — to actually inspect computed styles on the live page and see which declaration is "winning" for each custom property, rather than reasoning about it from source alone.
- **Cloudflare dashboard access** — to rule out any page rule, Transform Rule, or Configuration Rule that might restructure CSS delivery in a way that isn't visible from response headers alone (unlikely given the cache-status headers already checked, but not 100% ruled out without direct access).
- Alternatively: if a stronger/differently-tooled agent has access to a real browser automation tool (Playwright, etc. — this codebase's own Technical Reference notes "No SVG-to-PNG rasterizer or working headless browser by default" in this environment, so this session couldn't screenshot-test even a simulated mobile viewport locally) that could actually load the live site at a 430px viewport and inspect computed styles, that would resolve this quickly without needing @user's real device at all.

## Stop Conditions

- If the probe answer is "desktop scheme active" — do not keep pursuing the WebKit/cascade theory, pivot entirely to viewport-detection debugging instead.
- If a browser automation tool confirms the CSS resolves correctly in a simulated 430px viewport — the bug is device/browser-specific in a way that may need @user to test on a different physical device before concluding anything further about WebKit.

## Critical Files

| File | Why |
|------|-----|
| `app/static/css/main.css` | Lines ~73-118: the mobile `:root` override (with `!important` as of `8a8b1ab`). Lines ~1516-1518: `.role-badge--league_admin`, the element visibly wrong in @user's screenshot. `.site-footer-build`/`.viewport-probe--*`: the diagnostic probe. |
| `app/templates/base.html` | Footer build note + diagnostic probe markup (`GIT_COMMIT_SHORT`/`BOOT_TIME` Jinja globals, `.viewport-probe--mobile`/`--desktop` spans) |
| `app/templates/home.html` | `.lp-hero`/`.lp-btn-ghost` mobile override (lines ~75-96 as of `e4129c3`) — already fixed for source order, but same underlying "does :root override actually apply" mystery could affect it too |
| `app/config.py` | `GIT_COMMIT_SHORT`/`BOOT_TIME` (reads Render's auto-set `RENDER_GIT_COMMIT` env var) |
| `1. Project Management/4. Technical Reference.md` | "Visual Theme" section has the full narrative of this investigation already written up in detail, including the exact commit sequence — read it before re-deriving any of this from scratch |

## Relevant Recent Commits (chronological)

- `67df001` — mobile `:root` token override, initial version
- `d46c17c` — footer build note added (`GIT_COMMIT_SHORT`/`BOOT_TIME`)
- `56e581f` — diagnostic viewport probe added to footer
- `d3d0253` — first attempt at `home.html` hero/ghost-button fix (had the source-order bug)
- `e4129c3` — fixed the source-order bug
- `8a8b1ab` — added `!important` to the mobile `:root` override — **confirmed NOT to have fixed it** (probe read "mobile scheme active" on this exact build in Safari private, colors still unchanged)
- `e7a55cf` — bumped `sw.js`'s `CACHE_VERSION` ('v1' → 'v2') to force a full Service Worker cache wipe, on the theory that the SW's cache-first `/static/` handling has some browser-specific quirk in matching the versioned CSS URL, bypassing all HTTP-level cache-busting. **Not yet confirmed either way** — this is the last easy thing this session tried before handing off.

**If `e7a55cf` also doesn't fix it:** that would rule out Service Worker caching as cleanly as everything else has been ruled out, and would leave only the "needs real DevTools" and "needs Cloudflare dashboard access" paths open. In that case, also worth having @user manually clear Safari's site data for `bettergolfleague.com` (iOS Settings → Safari → Advanced → Website Data) as a completely independent, guaranteed-clean test — if that *still* doesn't fix it, every caching theory is dead and this is very likely a genuine rendering bug needing device inspection.

-----

## Execution Report

*(leave blank — fill in when this handoff is picked up and worked)*
