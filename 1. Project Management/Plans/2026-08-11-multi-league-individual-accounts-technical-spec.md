# Technical Spec: Multi-League Individual Accounts ("My Leagues" + "Add League")

*Status: `Built & validated` — 2026-08-11. Built as specced, validated end-to-end against a real local Postgres instance (27/28 automated checks passed; the 1 "failure" was a wording mismatch in the test script itself, not an app bug — confirmed by reading the actual template). Not yet pushed. Owner: @claude. Requested by @user 2026-08-11, following up on the target UX @user described while writing the Wiki How-To "Two Ways to Sign In" article: an individual account should be able to hold roles across more than one league, via a "My Leagues" page with an "Add League" button. That article already documents this as the target state, flagged inline as not-yet-built. See Work Packages backlog and Technical Reference's "Multi-league individual accounts, target UX now scoped" note.*

## Goal

Let one individual account (email + password) hold a role in more than one league at once, and let the account holder see which leagues they're linked to, add a new one, and switch which league is active in their session. Today an individual account can only ever be tied to one league: `auth.py`'s `login()` resolves it with `... WHERE ulr.user_id = %s ... LIMIT 1`, so even a user with multiple `user_league_roles` rows only ever reaches one of them.

## Current state: this is mostly a session/UI gap, not a data model gap

Checked the actual schema before assuming anything needed to change:

- **`user_league_roles(user_id, league_id, role_id)`** already allows multiple rows per `user_id` across different `league_id` values. No unique constraint blocks it. This table was built for exactly this, it just isn't used that way yet.
- **`players(user_id, league_id, ...)`** already allows one player row per league per user. No unique constraint on `user_id` alone. A user can already be linked to a different player row in each league they belong to.

So the real gaps are narrower than "redesign the data model":

1. `login()`'s `LIMIT 1` never offers a choice when more than one role row exists.
2. No page shows an account which leagues it's linked to.
3. No flow lets an account link a *new* league after registration (today, linking to a league only happens once, at `register()` time).
4. No way to switch the active league in-session once linked to more than one.

## Design

### Session model: mirror the existing season-switcher, don't invent a new mechanism

Nearly every route in the app scopes its queries off `session['league_id']` (set once at login). This app already has a working precedent for "swap out a session-scoped value and redirect back," used for switching seasons within a league:

```python
# app.py:391-396, existing
@app.route('/switch-season/<int:season_id>')
@login_required
def switch_season(season_id):
    session['current_season_id'] = season_id
    referrer = request.referrer or '/'
    return redirect(referrer)
```

A league switch needs to do more than swap one session key, since `role`, `player_id`, `league_name`, and `is_site_admin` are all also derived per-league at login time, but the shape is the same:

```python
@app.route('/switch-league/<int:league_id>')
@login_required
def switch_league(league_id):
    user_id = session.get('user_id')
    if not user_id:
        abort(403)  # shared-password sessions have no account to switch leagues on

    db = get_db()
    ulr = db.execute(
        """SELECT ulr.league_id, ulr.role_id, r.role_name, l.league_name
           FROM user_league_roles ulr
           JOIN roles r ON r.role_id = ulr.role_id
           JOIN leagues l ON l.league_id = ulr.league_id
           WHERE ulr.user_id = %s AND ulr.league_id = %s AND l.active = 1""",
        (user_id, league_id)
    ).fetchone()
    if not ulr:
        abort(403)  # not actually linked to this league — don't trust the URL blindly

    player = db.execute(
        "SELECT player_id FROM players WHERE user_id = %s AND league_id = %s",
        (user_id, league_id)
    ).fetchone()

    session['league_id']         = ulr['league_id']
    session['league_name']       = ulr['league_name']
    session['role']              = ulr['role_name']
    session['player_id']         = player['player_id'] if player else None
    session.pop('current_season_id', None)  # season selection doesn't carry across leagues

    return redirect(url_for('main.dashboard'))
```

This is the same shape as `login()`'s existing user-account branch (`auth.py:283-334`), just re-run against a different `league_id` instead of the first row found. Because the rest of the app already scopes everything off `session['league_id']`, **no other route needs to change** — this is a low-blast-radius feature precisely because of that existing convention, not despite it.

### "My Leagues" page

New page, individual-account only (`session.get('user_id')` must be set — a shared-password session has no account to attach multiple leagues to). Lists every league the account is linked to, each row showing: league name, role in that league, and a "Switch to this league" action (hits `switch-league/<id>` above). The currently-active league is marked distinctly, not just listed alongside the others. Each row also carries a "Remove" action, see below.

### Leaving a league (resolved, 2026-08-11: self-removal allowed)

An account can remove itself from a league it's linked to. This deletes only its `user_league_roles` row for that league; nothing else changes. Specifically, it does **not**: delete the account, delete or deactivate the linked `players` row, remove the person's name/history/scores from the league, or touch the shared League ID/password for that league at all.

The confirmation step has to say this plainly, since "remove" reads as more destructive than it is. Confirmation copy (exact wording to refine at build time, but the content must cover all three points):

> Remove your individual account's access to **[League Name]**?
>
> This only removes the connection between this account and that league. It does not delete you from the league, remove your name or history, or affect anyone else's access. You'll still be able to get into **[League Name]** anytime using its shared League ID and password. You can also link this account back to it later from Add League.

- **`POST /my-leagues/<int:league_id>/remove`** — deletes the `user_league_roles` row for `(session['user_id'], league_id)`. If the league being removed is the currently-active one in session, fall back to another linked league if one exists, or to the My Leagues page itself (with `league_id`/`role`/`player_id` cleared from session) if that was the last one.

### "Add League" flow

A button on My Leagues, reusing the exact role-by-password convention `register()` already established rather than inventing a second one:

- Form asks for League ID + that league's password (admin or member).
- Validates the same way `register()` does today (`auth.py:419-437`): look up the league by `login_code`, check the password against `admin_password_hash` then `member_password_hash` to determine role.
- On success: insert a new `user_league_roles` row for `(session['user_id'], league.league_id, role_id)`. If a `user_league_roles` row for that `(user_id, league_id)` pair already exists (re-adding a league already linked), update its role instead of inserting a duplicate — this is also the reason a unique constraint is worth adding, see Data model below.
- Does **not** auto-link a player row. Matches today's convention exactly: `register()` doesn't auto-link a player either, `users.py`'s `link_player()` (admin-only) is the actual linking step. An admin still connects the new account to a roster player from Manage Users after the fact, same as today.

### Register() interaction (resolved, 2026-08-11: leave register() unchanged for now)

`register()` (`auth.py:381-476`) keeps creating the account **and** its first league link in one step, exactly as it works today. "Add League" is purely additive, for every league after the first — no changes to the registration form or flow. This does mean the League ID + League Password validation logic exists in two places (`register()`'s own inline version, and Add League's) rather than one shared one; acceptable duplication for now, worth revisiting if the two ever drift out of sync.

## Data model

**No new tables.** One recommended addition:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_user_league_roles_user_league
    ON user_league_roles(user_id, league_id);
```

`user_league_roles` has no constraint today preventing two rows for the same `(user_id, league_id)` pair. That's harmless while every account only ever links once, but "Add League" makes it possible to hit the same league twice (re-entering a league you're already linked to) — the app-level "update instead of insert" logic above should make this unreachable in practice, but the constraint is worth having as a real guarantee rather than trusting the application layer alone. Register in `init_db.py`'s additive migration list, per this project's own repeatedly-learned lesson about migrations that get written but never actually registered (see Technical Reference's "New columns need THREE things" note).

## Routes

- **`GET /my-leagues`** — the page above. `login_required`, and further gated on `session.get('user_id')` being set (redirect shared-password sessions elsewhere with an explanatory flash, same pattern `users.account()` already uses for this exact case).
- **`GET/POST /my-leagues/add`** — the Add League form + its POST handler.
- **`GET /switch-league/<int:league_id>`** — shown above.
- **`POST /my-leagues/<int:league_id>/remove`** — shown above, under "Leaving a league."

## UI

- Nav: a "My Leagues" link in the existing "My Account" drawer group (`base.html`, next to Email Preferences / My Sub Requests), shown only when `session_user_id` is set — same conditional those already use.
- Once an account is linked to more than one league, worth a compact switcher next to the season switcher in the nav drawer footer (same `<select>`-and-redirect pattern as `nav-drawer-season-select`) so switching doesn't require a trip to My Leagues every time. **Recommend deferring this to a fast-follow** rather than building it in the first pass — start with My Leagues as the one place to switch, matching exactly what @user's own how-to copy described, and only add the nav shortcut if switching turns out to happen often enough to be worth the extra UI.

## Open questions for @user

1. ~~Leaving/unlinking a league from My Leagues~~ — **Resolved 2026-08-11**: self-removal allowed, with confirmation copy that explicitly states nothing is deleted, only the individual account's link to that league; the shared League ID/password still works. See "Leaving a league" above.
2. ~~`register()` unchanged vs. unified through "Add League"~~ — **Resolved 2026-08-11**: leave `register()` unchanged for now. See "Register() interaction" above.
3. ~~Can an account link to a league it has no player row in yet~~ — **Resolved 2026-08-11**: yes, no issue. Linking to an "empty" league (no admin has connected a player yet) is a normal, supported state — matches how a freshly-registered account already behaves today.

All open questions resolved. Ready to build once prioritized.

## Effort

**S.** No new tables, one small unique index. One new route mirroring an existing one almost line-for-line (`switch_league` off `switch_season`), one new form flow reusing `register()`'s existing password-role-lookup logic, one new template (My Leagues) plus one small addition to an existing one (Add League can share `register()`'s form partial rather than being built from scratch). No changes required to any of the app's other ~40 route files, since none of them need to know an account *could* belong to multiple leagues — they only ever read `session['league_id']`, which is exactly what `switch_league()` sets.

## Testing plan

Validate against real dev Postgres per this project's standing convention: register two leagues, link one account to both via Add League (correct role picked per password on each), confirm My Leagues lists both with correct roles, switch between them and confirm every session key updates (`league_id`/`league_name`/`role`/`player_id`) and a season selected in league A doesn't leak into league B, confirm the new unique index actually rejects/updates-in-place a duplicate `(user_id, league_id)` insert, confirm a shared-password session is blocked from `/my-leagues` with a clear message; confirm removing the active league falls back correctly (to another linked league, or to a cleared session if it was the last one) and that removing a league never touches its `players` row, its shared password hashes, or any other account's link to it.

## Next step

Built and validated (2026-08-11). See Technical Reference's new "Multi-League Individual Accounts" section for the shipped shape. Not yet pushed to `main`.
