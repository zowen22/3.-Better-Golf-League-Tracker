from flask import Blueprint, render_template, session, redirect, url_for, flash
from .auth import login_required
from database import get_db, get_current_season_id

bp = Blueprint('league_info', __name__, url_prefix='/league')

_SETTINGS_DEFAULTS = {
    'holes_per_round': 9,
    'scoring_type': 'net',
    'match_play_points_per_hole': 2,
    'match_play_tie_points': 1.0,
    'match_play_overall_point': 2,
    'playoff_teams': 4,
    'finals_weeks': 2,
    'min_rounds_for_handicap': 2,
    'rounds_to_average': 4,
    'high_scores_to_drop': 1,
    'handicap_percent': 90.0,
    'max_handicap_index': 18.0,
    'max_score_over_handicap': 18,
    'negative_handicap_allowed': 1,
    'carry_scores_across_seasons': 1,
    'skins_default_gross_net': 'gross',
    'skins_default_amount': None,
    'skins_self_optin_enabled': 0,
    'self_reporting_enabled': 0,
    'self_reporting_requires_approval': 1,
    'diff_calculation_type': 'par',
    'max_score_per_hole': None,
    'max_score_action': 'warn',
    'segment_start_week': None,
    'segment_end_week': None,
    'scoring_mode': 'match_play',
}

_TB_DEFAULTS = {
    'priority1': 'h2h',
    'priority2': 'pts_pct',
    'priority3': 'allplay_pct',
    'priority4': 'scoring_avg',
}

_TB_LABELS = {
    'h2h':          'Head-to-Head record',
    'pts_pct':      'Points percentage (season)',
    'allplay_pct':  'All-play winning percentage',
    'scoring_avg':  'Scoring average (lower is better)',
    'none':         '(not used)',
}


@bp.route('/info')
@login_required
def info():
    db = get_db()
    league_id  = session['league_id']

    # Current season
    season_id = get_current_season_id(db, league_id)
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone() if season_id else None
    if not season:
        flash('No season found.', 'error')
        return redirect(url_for('main.dashboard'))

    # League settings
    cfg = dict(_SETTINGS_DEFAULTS)
    row = db.execute(
        "SELECT * FROM league_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if row:
        for k in _SETTINGS_DEFAULTS:
            try:
                v = row[k]
                if v is not None:
                    cfg[k] = v
            except (IndexError, KeyError):
                pass

    # Tiebreaker settings
    tb = dict(_TB_DEFAULTS)
    try:
        tbrow = db.execute(
            "SELECT * FROM tiebreaker_settings WHERE season_id=%s AND league_id=%s",
            (season_id, league_id)
        ).fetchone()
        if tbrow:
            for k in _TB_DEFAULTS:
                col = k.replace('priority', 'priority_')
                v = tbrow[col]
                if v:
                    tb[k] = v
    except Exception:
        pass

    # Schedule summary
    total_rounds = db.execute(
        "SELECT COUNT(*) FROM matchups WHERE season_id=%s AND is_bye=0",
        (season_id,)
    ).fetchone()[0] or 0

    completed_rounds = db.execute(
        "SELECT COUNT(DISTINCT week_number) FROM matchups WHERE season_id=%s AND status='completed' AND is_bye=0",
        (season_id,)
    ).fetchone()[0] or 0

    total_weeks = db.execute(
        "SELECT COUNT(DISTINCT week_number) FROM matchups WHERE season_id=%s",
        (season_id,)
    ).fetchone()[0] or 0

    # Dates
    first_date = db.execute(
        "SELECT MIN(scheduled_date) FROM matchups WHERE season_id=%s AND is_bye=0",
        (season_id,)
    ).fetchone()[0]
    last_date = db.execute(
        "SELECT MAX(scheduled_date) FROM matchups WHERE season_id=%s AND is_bye=0",
        (season_id,)
    ).fetchone()[0]

    # Courses used this season
    courses_used = db.execute(
        """SELECT DISTINCT c.course_name, t.tee_name, t.tee_color AS color
           FROM matchups m
           JOIN tees t ON m.tee_id = t.tee_id
           JOIN courses c ON m.course_id = c.course_id
           WHERE m.season_id=%s""",
        (season_id,)
    ).fetchall()

    # Team count
    team_count = db.execute(
        "SELECT COUNT(*) FROM teams WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()[0] or 0

    # Divisions
    divisions = []
    try:
        divisions = db.execute(
            "SELECT DISTINCT division_name AS division FROM teams WHERE season_id=%s AND league_id=%s AND division_name IS NOT NULL AND division_name != ''",
            (season_id, league_id)
        ).fetchall()
    except Exception:
        pass

    # Skins rounds this season
    skins_count = 0
    try:
        skins_count = db.execute(
            """SELECT COUNT(DISTINCT m.matchup_id)
               FROM skins_rounds sr
               JOIN matchups m ON sr.matchup_id = m.matchup_id
               WHERE m.season_id=%s""",
            (season_id,)
        ).fetchone()[0] or 0
    except Exception:
        pass

    return render_template('league_info/index.html',
        season=season,
        cfg=cfg,
        tb=tb,
        tb_labels=_TB_LABELS,
        total_weeks=total_weeks,
        completed_rounds=completed_rounds,
        first_date=first_date,
        last_date=last_date,
        courses_used=courses_used,
        team_count=team_count,
        divisions=divisions,
        skins_count=skins_count,
    )
