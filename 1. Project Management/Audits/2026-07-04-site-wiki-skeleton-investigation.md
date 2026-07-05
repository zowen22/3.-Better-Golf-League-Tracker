# In-App Site Wiki — Skeleton Investigation for Fable

**Type:** Feature Scoping (structure only — @user has explicitly deferred content population until the product is more mature)
**Status:** Open — findings ready for Fable to plan from
**Prepared by:** Sonnet, 2026-07-04
**Linked WP:** Backlog item "In-app site wiki for members/admins" (`3. Work Packages.md`)

-----

## Scope, as directed by @user

Build the **skeleton only** — route, blueprint, page structure, navigation entry point, category scaffolding. **Do not write the actual explanatory content yet** ("probably smart to wait to populate the wiki until the site is more mature" — features and settings are still changing, so real wiki copy would go stale fast). This doc is evidence + a recommended structure for Fable to plan the skeleton from; it is not asking anyone to write help-article prose.

## Key finding: `/wiki` is already referenced twice, and it's a dead link today

`app/templates/admin/settings.html` (lines 189, 199, 432-433) already has "Learn more" links pointing to `/wiki#setting-2.10` and `/wiki#setting-2.11` (the two temp-handicap-percent settings' ⓘ tooltips). **There is no `wiki` blueprint registered anywhere** — confirmed via `app.py`'s full blueprint-registration list (23 blueprints registered, no `wiki_bp`) — so these two links 404 today. This isn't a green-field feature; it's completing something the UI already half-built and is currently silently broken.

This also hands the skeleton its anchor convention for free: `#setting-N.NN` matching the admin settings numbering already used in the ⓘ tooltip system (`data-info-target="info-2-10"` etc., `settings.html:189,199`). Only 2 of the ~38 total settings currently have this tooltip+link pattern — a separate, already-tracked backlog item ("retrofit ⓘ tooltip pattern onto the other ~36 existing settings fields," `3. Work Packages.md`) covers extending the tooltip UI itself. **This wiki skeleton and that tooltip-retrofit item are related but separate** — the skeleton just needs to be structurally ready to receive `#setting-N.NN` anchors whenever content and tooltips both land; it doesn't need to solve the tooltip retrofit itself.

## What the skeleton needs to decide (structural, not content)

1. **Single long page with anchors, vs. multiple category pages.** The existing dead links (`/wiki#setting-2.10`) imply a **single-page-with-anchors** model was the original intent — same pattern as most in-app help pages (one scrollable reference, deep-linkable by `#id`, browser-searchable with Ctrl+F). This is simpler to build and matches what's already half-wired; recommend as the default unless Fable sees a reason to split into multiple pages (e.g. if content volume later gets large enough that one page becomes unwieldy — a future problem, not a v1 one).
2. **Category structure.** BGLT already has a proven category grouping for exactly this kind of "explain how the product works" content — the GLT how-to article site map built earlier this session (`7. GLT Feature Parity.md`'s "How-To Articles" table) groups by: Setup/Account/Admin, League Structure & Roster, Courses/Tees, Scheduling, Handicaps, Scoring/Points, Subs/Absences, Skins/Contests, Reports, Communication. Recommend reusing this grouping (renamed/adapted to BGLT's own actual feature set, not GLT's) as the wiki's section skeleton — it's already a battle-tested breakdown of the questions a golf league admin/member actually asks, no need to invent a new taxonomy from scratch.
3. **Storage: static Jinja template vs. DB-backed/CMS.** A static template (hardcoded HTML sections, edited via code changes/deploys) is almost certainly the right call for a skeleton meant to sit empty for a while — it needs zero new schema, zero admin-editing UI, and is trivial to fill in later a section at a time as content gets written. A DB-backed CMS (admin-editable wiki content, versioning, etc.) is a meaningfully bigger feature and isn't implied by anything in the backlog ask ("plain-language explanations," not "admin-authorable content") — flag as explicitly out of scope unless @user says otherwise.
4. **Nav entry point.** No "Wiki"/"Help" link exists anywhere in `base.html`'s nav drawer today (confirmed via grep — the drawer has ~25 links across admin/member/misc sections, none for help/wiki). A skeleton needs at least one visible entry point, not just the tooltip deep-links — natural placement is near "League Info" (`league_info.index`) in the misc/info section of the nav, or a footer link, Fable's call.
5. **Audience gating.** Backlog says "members/admins" — i.e. this should be visible to all logged-in users, not admin-only (distinct from `4. Technical Reference.md`, which is dev-only and lives outside the app entirely). A plain `login_required` route (no `admin_required`) matches this.

## Recommended v1 skeleton shape (structure, zero real content)

Based on the above: one new blueprint (`wiki.py`), one route (`GET /wiki`, `login_required`), one template with the category sections above present as empty/placeholder headers (e.g. "Handicaps — content coming soon" under each category, or a single "This section is being written — check back soon" placeholder per category), and the two existing dead anchor IDs (`setting-2.10`, `setting-2.11`) present in the template even if their content is a placeholder, so the two currently-broken links at least resolve to a real page section instead of a 404. One new nav-drawer link. No new schema, no admin-editing surface, no real help copy — purely load-bearing structure that content can be dropped into later without touching the skeleton again.

## Net for Fable

This is a small, mechanical skeleton — the interesting decision (categories, one-page-vs-many, storage model) has a fairly clear recommended answer above based on what already exists in the codebase (the dead `/wiki#` links, the proven GLT-derived category list), so there isn't much open design debate here, unlike the skins-flights or site-admin-dashboard items. The main value of doing this now rather than waiting: it fixes two already-broken links in production and gives future content work a real place to land, without committing to writing any content before the product settles down, per @user's explicit instruction.
