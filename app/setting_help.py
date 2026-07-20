"""Shared tooltip / wiki-content source of truth for League Settings.

SETTING_HELP is a plain data dict (no Flask/route dependencies) keyed by the
same setting-number scheme already used on the League Settings page
(``'2.10'``, ``'2.11'``, etc. — matching the ⓘ tooltip button and the
``/wiki#setting-N.NN`` anchor scheme). Each entry is ``{'label': ..., 'text': ...}``.

This module is read from two places, both of which must treat ``text`` as
byte-identical, never as a starting point to copy-and-diverge from:
  - ``admin/settings.html`` (via the ``SETTING_HELP`` Jinja global registered
    in ``app.py``) renders it as each setting's tooltip / desktop help text.
  - The future in-app wiki skeleton (tracked in
    ``1. Project Management/Audits/2026-07-04-site-wiki-skeleton-investigation.md``)
    will render the same ``text`` value as that setting's wiki section body.

Do not duplicate this content anywhere else. The "Learn more -> /wiki#setting-N.NN"
link shown next to a tooltip is appended by the rendering/JS layer on top of
``text`` — it is not, and must never become, part of ``text`` itself (the wiki
page reading the same ``text`` must not show a "Learn more" link pointing at
itself).

Real explanatory copy exists for every setting that already had a one-line
``<p class="form-hint">`` on the pre-scalability version of this page —
migrated here unchanged (including 2.10/2.11, from the old inline
``infoText`` JS dict). Settings that never had hint text before (mostly
self-explanatory ones — course count, holes per round, playoff team count,
etc.) hold the placeholder below. Writing NEW copy beyond what already
existed is separate, future work paired with the wiki skeleton — this
module only carries forward content that was already written and reviewed,
it does not add anything new.

Voice (per @user, 2026-07-15): when writing NEW wiki/tooltip copy, it's
written from @user's own first-person point of view as the person who
built this. An occasional first-person aside is welcome where the human
perspective actually helps explain the "why" behind a setting or a design
choice — don't overdo it, most entries should stay plain third-person
explanation like the existing content above.
"""

_PLACEHOLDER = 'Full explanation coming soon.'

SETTING_HELP = {
    # ── 1. Scoring ───────────────────────────────────────────────────────
    '1.01': {'label': 'How many courses does this league use?', 'text': 'Controls whether the Course column appears on schedule views.'},
    '1.02': {'label': 'Holes Per Round', 'text': 'Typically 9 for a league night.'},
    '1.03': {'label': 'Scoring Format', 'text': ('Match Play: per-hole W/T/L pts, individual A-vs-A/B-vs-B. Stableford: accumulate pts per hole vs par, '
                  'compare totals. Best Ball: each team’s hole score is the lower of its two players’ net scores, teams compared head-to-head. '
                  'Team Totals: each team’s hole score is both players’ net scores added together, teams compared head-to-head. Only one format is active at a time.')},
    '1.04': {'label': 'Does this league use handicaps?', 'text': _PLACEHOLDER},
    '1.05': {'label': 'Match Play Pts Per Hole (Win)', 'text': 'Points awarded for winning a hole. Loss = 0.'},
    '1.06': {'label': 'Match Play Pts Overall (Win)', 'text': 'Bonus points awarded for winning the overall 9-hole total.'},
    '1.07': {'label': 'Match Play Pts Per Hole (Tie)', 'text': 'Points awarded to each player when a hole is tied. Also used for the overall-total tie.'},
    '1.09': {'label': 'Best Ball Pts Per Hole (Win)', 'text': 'Only used when Scoring Format is Best Ball. Points awarded to the team with the lower combined hole score.'},
    '1.10': {'label': 'Best Ball Pts Per Hole (Tie)', 'text': 'Only used when Scoring Format is Best Ball. Points awarded to each team when the hole is tied.'},
    '1.11': {'label': 'Best Ball Pts Overall (Win)', 'text': 'Only used when Scoring Format is Best Ball. Bonus points awarded for the better overall combined net total.'},
    '1.12': {'label': 'Team Totals Pts Per Hole (Win)', 'text': 'Only used when Scoring Format is Team Totals. Points awarded to the team with the lower combined hole score.'},
    '1.13': {'label': 'Team Totals Pts Per Hole (Tie)', 'text': 'Only used when Scoring Format is Team Totals. Points awarded to each team when the hole is tied.'},
    '1.14': {'label': 'Team Totals Pts Overall (Win)', 'text': 'Only used when Scoring Format is Team Totals. Bonus points awarded for the better overall combined net total.'},
    '1.15': {'label': 'Classical Stroke Play Pts Per Stroke', 'text': ('Only used when Scoring Format is Classical Stroke Play. Points per stroke relative to '
                  'par, field-wide (not team-vs-team) -- a round 1 stroke under net par earns this many points, 1 over costs this many. Default is a reasonable '
                  'starting point, not a fixed convention -- adjust to taste.')},
    '1.08': {'label': 'Absence Overall Point Policy', 'text': ('Controls whether an absent player’s ghost score can win the overall (match) point '
                  'against their opponent. "Excused" is set per-absence in the sub/absence popover. Default matches current behavior.')},

    # ── 2. Handicap ──────────────────────────────────────────────────────
    '2.01': {'label': 'Differential Method', 'text': 'Par-based is the default for casual leagues.'},
    '2.02': {'label': 'Rounds to Average', 'text': 'Number of most recent rounds used in the calculation window.'},
    '2.03': {'label': 'High Scores to Drop', 'text': 'Worst rounds dropped before averaging (within the window).'},
    '2.04': {'label': 'Min Rounds Required', 'text': 'Minimum rounds before a handicap is calculated.'},
    '2.05': {'label': 'Handicap Percent (%)', 'text': 'Playing handicap = index × this ÷ 100. Typically 90%.'},
    '2.06': {'label': 'Max Handicap Index', 'text': 'Cap applied after percent reduction. Typically 18.'},
    '2.07': {'label': 'Max Score Over Handicap', 'text': 'Used for Equitable Stroke Control in differential calc.'},
    '2.08': {'label': 'Allow Negative Handicap', 'text': 'If unchecked, handicap index is floored at 0.'},
    '2.09': {'label': 'Carry Scores Across Seasons', 'text': 'Include rounds from prior seasons in handicap window.'},
    '2.10': {
        'label': 'Pre-Eligibility Temp Handicap % (Member)',
        'text': ('Applied to a regular member’s own round differential (gross − par) '
                  'for any round played before they reach Min Rounds Required. Computed '
                  'independently for each pre-eligibility round — not averaged or carried forward.'),
    },
    '2.11': {
        'label': 'Pre-Eligibility Temp Handicap % (Sub)',
        'text': ('Same calculation as 2.10, but used when the scorecard for that specific '
                  'round is flagged as a substitute, regardless of the player’s normal roster status.'),
    },

    # ── 3. Max Score Per Hole ────────────────────────────────────────────
    '3.01': {'label': 'Max Score Per Hole (optional)', 'text': 'Leave blank for no per-hole cap. Example: triple bogey max.'},
    '3.02': {'label': 'Action When Exceeded', 'text': _PLACEHOLDER},
    '3.03': {'label': 'Custom Warning Message (optional)', 'text': _PLACEHOLDER},

    # ── 4. Playoffs ──────────────────────────────────────────────────────
    '4.01': {'label': 'Playoff Teams', 'text': _PLACEHOLDER},
    '4.02': {'label': 'Finals Duration (weeks)', 'text': _PLACEHOLDER},

    # ── 5. Skins Defaults ────────────────────────────────────────────────
    '5.01': {'label': 'Default Scoring', 'text': _PLACEHOLDER},
    '5.02': {'label': 'Default Buy-In Amount ($) (optional)', 'text': _PLACEHOLDER},
    '5.03': {'label': 'Allow Players to Self Opt-In', 'text': 'Members can opt themselves in/out of skins for a round.'},

    # ── 6. Self-Reporting ────────────────────────────────────────────────
    '6.01': {'label': 'Allow Members to Submit Scores', 'text': 'Members can enter their own scores instead of waiting for an admin.'},
    '6.02': {'label': 'Require Admin Approval', 'text': 'Self-reported scores are held for admin review before counting.'},

    # ── 7. Season Segments ───────────────────────────────────────────────
    '7.01': {'label': 'Segment Start Week', 'text': 'First week included in the segment.'},
    '7.02': {'label': 'Segment End Week', 'text': 'Last week included in the segment.'},

    # ── 8. Tiebreakers ───────────────────────────────────────────────────
    '8.01': {'label': 'Priority 1', 'text': _PLACEHOLDER},
    '8.02': {'label': 'Priority 2', 'text': _PLACEHOLDER},
    '8.03': {'label': 'Priority 3', 'text': _PLACEHOLDER},
    '8.04': {'label': 'Priority 4', 'text': _PLACEHOLDER},

    # ── 9. Member Dashboard Widgets ──────────────────────────────────────
    '9.01': {'label': 'Announcements banner', 'text': _PLACEHOLDER},
    '9.02': {'label': 'Weekly round recap (medalists / net lows / odds & ends)', 'text': _PLACEHOLDER},
    '9.03': {'label': 'Activity feed (recent results, upcoming, standings snapshot)', 'text': _PLACEHOLDER},
    '9.04': {'label': 'League activity feed (notification-style timeline)', 'text': _PLACEHOLDER},
    '9.05': {'label': 'Standings snapshot name style', 'text': "Controls how teams are labeled in the dashboard's standings snapshot: Team Name (the team's configured name, falling back to last names if none is set), First Names, or Last Names. Only affects this one dashboard widget."},
}
