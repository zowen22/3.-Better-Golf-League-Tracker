"""In-app site wiki — structural skeleton only.

Renders a single scrollable reference page, organized into categories
adapted from the GLT how-to article grouping (see
`1. Project Management/Audits/2026-07-04-site-wiki-skeleton-investigation.md`),
with one anchor section per League Settings entry.

All per-setting label/body text is read directly from `setting_help.SETTING_HELP`
— the same dict the League Settings page's tooltip (`admin/settings.html`) reads
from — so the two are guaranteed to never drift apart. This module must not
define or duplicate any per-setting explanatory copy; it only supplies the
category *structure* (which setting ids belong under which heading) and,
where a category has no settings mapped to it yet, a plain placeholder string.
"""

from flask import Blueprint, render_template
from .auth import login_required
from setting_help import SETTING_HELP

bp = Blueprint('wiki', __name__)

_PLACEHOLDER_SECTION = 'This section is being written — check back soon.'

# Category structure only (no explanatory content) — which League Settings
# ids (SETTING_HELP keys) fall under each category heading. Adapted from the
# GLT how-to article grouping: Setup/Account/Admin, League Structure &
# Roster, Courses/Tees, Scheduling, Handicaps, Scoring/Points, Subs/Absences,
# Skins/Contests, Reports, Communication — renamed to BGLT's own feature
# names and built from the settings page's own section groupings (Scoring,
# Handicap, Max Score Per Hole, Playoffs, Skins Defaults, Self-Reporting,
# Season Segments, Tiebreakers, Member Dashboard Widgets).
WIKI_CATEGORIES = [
    {
        'slug': 'setup-basics',
        'icon': '⚙️',
        'name': 'Setup & Season Basics',
        'settings': ['1.02'],
    },
    {
        'slug': 'league-structure',
        'icon': '🏆',
        'name': 'League Structure, Roster & Playoffs',
        'settings': ['4.01', '4.02'],
    },
    {
        'slug': 'courses-tees',
        'icon': '🗺️',
        'name': 'Courses & Tees',
        'settings': ['1.01'],
    },
    {
        'slug': 'scheduling-segments',
        'icon': '📅',
        'name': 'Scheduling & Season Segments',
        'settings': ['7.01', '7.02'],
    },
    {
        'slug': 'handicaps',
        'icon': '🧮',
        'name': 'Handicaps',
        'settings': [
            '2.01', '2.02', '2.03', '2.04', '2.05', '2.06',
            '2.07', '2.08', '2.09', '2.10', '2.11',
        ],
    },
    {
        'slug': 'scoring-points',
        'icon': '🏌️',
        'name': 'Scoring & Points',
        'settings': [
            '1.03', '1.04', '1.05', '1.06', '1.07',
            '3.01', '3.02', '3.03',
            '8.01', '8.02', '8.03', '8.04',
        ],
    },
    {
        'slug': 'subs-absences',
        'icon': '🔄',
        'name': 'Subs & Absences',
        'settings': ['1.08'],
    },
    {
        'slug': 'skins-contests',
        'icon': '💰',
        'name': 'Skins & Contests',
        'settings': ['5.01', '5.02', '5.03'],
    },
    {
        'slug': 'self-reporting',
        'icon': '📝',
        'name': 'Self-Reporting',
        'settings': ['6.01', '6.02'],
    },
    {
        'slug': 'reports-dashboard',
        'icon': '📊',
        'name': 'Reports & Dashboard',
        'settings': ['9.01', '9.02', '9.03', '9.04'],
    },
    {
        'slug': 'communication',
        'icon': '📢',
        'name': 'Communication',
        'settings': [],
    },
]


@bp.route('/wiki')
@login_required
def index():
    return render_template(
        'wiki/index.html',
        categories=WIKI_CATEGORIES,
        setting_help=SETTING_HELP,
        placeholder=_PLACEHOLDER_SECTION,
    )
