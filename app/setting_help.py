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

Real explanatory copy has only been written for 2.10 / 2.11 so far (migrated
here unchanged from the old inline ``infoText`` JS dict that used to live in
``settings.html``). Every other setting currently holds placeholder text —
writing real copy for those is separate, future work paired with the wiki
skeleton, not part of the settings-page-scalability handoff this module was
introduced for.
"""

_PLACEHOLDER = 'Full explanation coming soon.'

SETTING_HELP = {
    # ── 1. Scoring ───────────────────────────────────────────────────────
    '1.01': {'label': 'How many courses does this league use?', 'text': _PLACEHOLDER},
    '1.02': {'label': 'Holes Per Round', 'text': _PLACEHOLDER},
    '1.03': {'label': 'Scoring Format', 'text': _PLACEHOLDER},
    '1.04': {'label': 'Does this league use handicaps?', 'text': _PLACEHOLDER},
    '1.05': {'label': 'Match Play Pts Per Hole (Win)', 'text': _PLACEHOLDER},
    '1.06': {'label': 'Match Play Pts Overall (Win)', 'text': _PLACEHOLDER},
    '1.07': {'label': 'A/B Designation Method', 'text': _PLACEHOLDER},
    '1.08': {'label': 'Absence Overall Point Policy', 'text': _PLACEHOLDER},

    # ── 2. Handicap ──────────────────────────────────────────────────────
    '2.01': {'label': 'Differential Method', 'text': _PLACEHOLDER},
    '2.02': {'label': 'Rounds to Average', 'text': _PLACEHOLDER},
    '2.03': {'label': 'High Scores to Drop', 'text': _PLACEHOLDER},
    '2.04': {'label': 'Min Rounds Required', 'text': _PLACEHOLDER},
    '2.05': {'label': 'Handicap Percent (%)', 'text': _PLACEHOLDER},
    '2.06': {'label': 'Max Handicap Index', 'text': _PLACEHOLDER},
    '2.07': {'label': 'Max Score Over Handicap', 'text': _PLACEHOLDER},
    '2.08': {'label': 'Allow Negative Handicap', 'text': _PLACEHOLDER},
    '2.09': {'label': 'Carry Scores Across Seasons', 'text': _PLACEHOLDER},
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
    '3.01': {'label': 'Max Score Per Hole (optional)', 'text': _PLACEHOLDER},
    '3.02': {'label': 'Action When Exceeded', 'text': _PLACEHOLDER},
    '3.03': {'label': 'Custom Warning Message (optional)', 'text': _PLACEHOLDER},

    # ── 4. Playoffs ──────────────────────────────────────────────────────
    '4.01': {'label': 'Playoff Teams', 'text': _PLACEHOLDER},
    '4.02': {'label': 'Finals Duration (weeks)', 'text': _PLACEHOLDER},

    # ── 5. Skins Defaults ────────────────────────────────────────────────
    '5.01': {'label': 'Default Scoring', 'text': _PLACEHOLDER},
    '5.02': {'label': 'Default Buy-In Amount ($) (optional)', 'text': _PLACEHOLDER},
    '5.03': {'label': 'Allow Players to Self Opt-In', 'text': _PLACEHOLDER},

    # ── 6. Self-Reporting ────────────────────────────────────────────────
    '6.01': {'label': 'Allow Members to Submit Scores', 'text': _PLACEHOLDER},
    '6.02': {'label': 'Require Admin Approval', 'text': _PLACEHOLDER},

    # ── 7. Season Segments ───────────────────────────────────────────────
    '7.01': {'label': 'Segment Start Week', 'text': _PLACEHOLDER},
    '7.02': {'label': 'Segment End Week', 'text': _PLACEHOLDER},

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
}
