"""
Admin blueprint — season-scoped admin panel.
/admin/                              redirect to latest season panel
/admin/season/<id>                   admin panel + schedule management widget
/admin/season/<id>/week/<num>/edit   edit week date & type
/admin/season/<id>/settings          league settings for the season (GET/POST)
/admin/scores/<matchup_id>/unlock    info page, redirects to edit
/admin/scores/<matchup_id>/edit      pre-filled score editing, updates in place
"""
from flask import Blueprint, current_app, render_template, request, redirect, url_for, session, flash
import database
from database import get_db, table_exists
from routes.auth import admin_required
from routes.schedule import _build_team_info, _build_yearly_rows
from routes.scores import (get_league_settings, strokes_on_hole, calc_match_play,
                            get_player_handicap)
from routes.handicap import recalc_handicap_for_player

bp = Blueprint('admin', __name__, url_prefix='/admin')


# ---------------------------------------------------------------------------
# Landing — redirect to latest season
# ---------------------------------------------------------------------------

@bp.route('/')
@admin_required
def landing():
    db = get_db()
    season = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (session['league_id'],)
    ).fetchone()
    if season:
        return redirect(url_for('admin.panel', season_id=season['season_id']))
    flash('Create a season first.', 'error')
    return redirect(url_for('seasons.index'))


# ---------------------------------------------------------------------------
# Admin panel for a season
# ---------------------------------------------------------------------------

@bp.route('/season/<int:season_id>')
@admin_required
def panel(season_id):
    db = get_db()
    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (session['league_id'],)
    ).fetchall()
    season = next((s for s in all_seasons if s['season_id'] == season_id), None)
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    team_info, team_num_map, teams_list = _build_team_info(db, season_id, session['league_id'])

    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.round_number, m.scheduled_date,
                  m.status, m.is_bye, m.bye_team_id, m.notes,
                  m.tee_time, m.starting_hole, m.week_type,
                  m.team1_id, m.team2_id, m.course_id, m.tee_id,
                  m.week_label, m.makeup_for_week,
                  c.course_name, te.nine AS side
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.season_id = %s
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()

    has_schedule = bool(matchups)
    yearly_rows, max_groups, weeks_dropdown = [], 0, []

    if has_schedule:
        seen = {}
        for m in matchups:
            seen.setdefault(m['week_number'], m['scheduled_date'])
        weeks_dropdown = sorted(seen.items(), key=lambda x: (x[1] or '9999-99-99', x[0]))
        yearly_rows, max_groups = _build_yearly_rows(
            matchups, team_info, team_num_map, weeks_dropdown
        )
        by_week = {}
        for m in matchups:
            by_week.setdefault(m['week_number'], []).append(m)
        for row in yearly_rows:
            row['matchups'] = by_week.get(row['week_num'], [])

    # Build per-week score entry status for the Score Entry widget
    score_weeks = []
    if has_schedule:
        from datetime import date as _date
        today = _date.today()
        for row in yearly_rows:
            wtype = row.get('week_type', 'Normal')
            if wtype in ('League Bye',):
                continue
            week_matchups = [m for m in row['matchups'] if not m['is_bye']]
            if wtype == 'Rain Out':
                status_label = 'rain-out'
            elif not week_matchups:
                status_label = 'bye'
            else:
                n_done = sum(1 for m in week_matchups if m['status'] == 'completed')
                if n_done == len(week_matchups):
                    status_label = 'complete'
                elif n_done > 0:
                    status_label = 'in-progress'
                else:
                    status_label = 'not-entered'

            # Only show weeks that haven't fully passed:
            # - no date set (unknown), or date is today/future, or not yet complete
            week_date = None
            if row['date']:
                try:
                    from datetime import datetime as _dt
                    week_date = _dt.strptime(row['date'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            is_past = week_date is not None and week_date < today
            is_future = week_date is not None and week_date > today
            if is_future:
                continue

            score_weeks.append({
                'week_num':  row['week_num'],
                'date':      row['date'],
                'week_type': wtype,
                'status':    status_label,
                'matchup_id': row['matchups'][0]['matchup_id'] if row['matchups'] else None,
            })

    # Fetch archive settings for this season (for the Archive Settings widget)
    arc_settings = db.execute(
        'SELECT * FROM archive_settings WHERE season_id = %s AND league_id = %s',
        (season_id, session['league_id'])
    ).fetchone()

    # Open sub request count for badge
    try:
        sub_req_row = db.execute(
            "SELECT COUNT(*) AS cnt FROM sub_requests WHERE league_id=%s AND status='open'",
            (session['league_id'],)
        ).fetchone()
        open_sub_request_count = sub_req_row['cnt'] if sub_req_row else 0
    except Exception:
        open_sub_request_count = 0

    # self_reporting_enabled — controls Submissions button visibility
    try:
        ls_row = db.execute(
            "SELECT self_reporting_enabled FROM league_settings WHERE league_id=%s",
            (session['league_id'],)
        ).fetchone()
        self_reporting_enabled = bool(ls_row['self_reporting_enabled']) if ls_row else False
    except Exception:
        self_reporting_enabled = False

    return render_template('admin/season.html',
                           season=season, all_seasons=all_seasons,
                           teams_list=teams_list, team_count=len(teams_list),
                           has_schedule=has_schedule,
                           yearly_rows=yearly_rows, max_groups=max_groups,
                           open_sub_request_count=open_sub_request_count,
                           arc_settings=arc_settings,
                           score_weeks=score_weeks,
                           self_reporting_enabled=self_reporting_enabled)


# ---------------------------------------------------------------------------
# Edit week date + type
# ---------------------------------------------------------------------------

@bp.route('/season/<int:season_id>/week/<int:week_num>/edit', methods=['GET', 'POST'])
@admin_required
def edit_week(season_id, week_num):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    rep = db.execute(
        "SELECT * FROM matchups WHERE season_id = %s AND week_number = %s ORDER BY matchup_id LIMIT 1",
        (season_id, week_num)
    ).fetchone()
    if not rep:
        flash('Week not found.', 'error')
        return redirect(url_for('admin.panel', season_id=season_id))

    courses = db.execute(
        "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
        (session['league_id'],)
    ).fetchall()
    tees = db.execute(
        "SELECT t.tee_id, t.course_id, t.tee_name, t.nine FROM tees t "
        "JOIN courses c ON t.course_id = c.course_id "
        "WHERE c.league_id = %s OR c.league_id IS NULL ORDER BY t.course_id, t.tee_name",
        (session['league_id'],)
    ).fetchall()

    if request.method == 'POST':
        scheduled_date = request.form.get('scheduled_date', '').strip() or None
        week_type      = request.form.get('week_type', 'Normal').strip() or 'Normal'
        course_id_raw  = request.form.get('course_id', '').strip()
        tee_id_raw     = request.form.get('tee_id', '').strip()
        course_id      = int(course_id_raw) if course_id_raw else None
        tee_id         = int(tee_id_raw)    if tee_id_raw    else None
        commissioner_note = request.form.get('commissioner_note', '').strip()
        db.execute(
            "UPDATE matchups SET scheduled_date = %s, week_type = %s, course_id = %s, tee_id = %s "
            "WHERE season_id = %s AND week_number = %s",
            (scheduled_date, week_type, course_id, tee_id, season_id, week_num)
        )
        # Save per-matchup tee times + starting holes
        week_matchup_ids = db.execute(
            "SELECT matchup_id FROM matchups WHERE season_id=%s AND week_number=%s AND is_bye=0",
            (season_id, week_num)
        ).fetchall()
        for wm in week_matchup_ids:
            mid = wm['matchup_id']
            tt  = request.form.get(f'tee_time_{mid}', '').strip() or None
            sh_raw = request.form.get(f'hole_{mid}', '').strip()
            sh  = int(sh_raw) if sh_raw and sh_raw.isdigit() else 1
            db.execute(
                "UPDATE matchups SET tee_time=%s, starting_hole=%s WHERE matchup_id=%s",
                (tt, sh, mid)
            )
        # Save commissioner note (upsert into week_notes; graceful if table absent)
        try:
            if commissioner_note:
                db.execute(
                    """INSERT INTO week_notes (league_id, season_id, week_number, notes, updated_at)
                       VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                       ON CONFLICT(league_id, season_id, week_number)
                       DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at""",
                    (session['league_id'], season_id, week_num, commissioner_note)
                )
            else:
                db.execute(
                    "DELETE FROM week_notes WHERE league_id=%s AND season_id=%s AND week_number=%s",
                    (session['league_id'], season_id, week_num)
                )
        except Exception:
            pass  # week_notes table not yet created — run migrate_week_notes.py
        db.commit()
        flash(f'Week {week_num} updated.', 'success')
        return redirect(url_for('admin.panel', season_id=season_id))

    tees_by_course = {}
    for t in tees:
        tees_by_course.setdefault(t['course_id'], []).append({
            'tee_id': t['tee_id'], 'tee_name': t['tee_name'], 'nine': t['nine']
        })

    # Load matchups for this week (for bulk tee-time editor)
    week_matchups = db.execute(
        """SELECT m.matchup_id, m.tee_time, m.starting_hole,
                  COALESCE(t1.team_name,
                    COALESCE(p1a.last_name,'') || ' / ' || COALESCE(p1b.last_name,'')
                  ) AS t1_label,
                  COALESCE(t2.team_name,
                    COALESCE(p2a.last_name,'') || ' / ' || COALESCE(p2b.last_name,'')
                  ) AS t2_label
           FROM matchups m
           LEFT JOIN teams   t1  ON m.team1_id  = t1.team_id
           LEFT JOIN teams   t2  ON m.team2_id  = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.tee_time ASC NULLS LAST, m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    # Load existing commissioner note (graceful if table absent)
    commissioner_note = ''
    try:
        note_row = db.execute(
            "SELECT notes FROM week_notes WHERE league_id=%s AND season_id=%s AND week_number=%s",
            (session['league_id'], season_id, week_num)
        ).fetchone()
        if note_row:
            commissioner_note = note_row['notes']
    except Exception:
        pass

    return render_template('admin/edit_week.html', season=season, week_num=week_num, rep=rep,
                           courses=courses, tees_by_course=tees_by_course,
                           commissioner_note=commissioner_note,
                           week_matchups=week_matchups)


_TB_DEFAULTS = {
    'priority_1': 'head_to_head',
    'priority_2': 'points_percentage',
    'priority_3': 'all_play_record',
    'priority_4': 'scoring_average',
}


def _get_tiebreaker_cfg(db, season_id, league_id):
    row = db.execute(
        "SELECT * FROM tiebreaker_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if row:
        return {k: row[k] or v for k, v in _TB_DEFAULTS.items()}
    return dict(_TB_DEFAULTS)


def _save_tiebreaker_cfg(db, season_id, league_id, data):
    existing = db.execute(
        "SELECT setting_id FROM tiebreaker_settings WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if existing:
        db.execute(
            """UPDATE tiebreaker_settings
               SET priority_1=:priority_1, priority_2=:priority_2,
                   priority_3=:priority_3, priority_4=:priority_4
               WHERE season_id=:season_id AND league_id=:league_id""",
            {**data, 'season_id': season_id, 'league_id': league_id}
        )
    else:
        db.execute(
            """INSERT INTO tiebreaker_settings
               (league_id, season_id, priority_1, priority_2, priority_3, priority_4)
               VALUES (:league_id, :season_id, :priority_1, :priority_2, :priority_3, :priority_4)""",
            {**data, 'league_id': league_id, 'season_id': season_id}
        )


# ---------------------------------------------------------------------------
# League settings — read/write all league_settings columns
# ---------------------------------------------------------------------------

# Default values matching the schema
_SETTINGS_DEFAULTS = {
    'holes_per_round': 9,
    'scoring_type': 'net',
    'match_play_points_per_hole': 2,
    'match_play_overall_point': 2,
    'ab_designation_method': 'weekly',
    'absent_player_policy_id': None,
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
    'self_reporting_enabled': 0,
    'self_reporting_requires_approval': 1,
    'skins_self_optin_enabled': 0,
    'diff_calculation_type': 'par',
    'max_score_per_hole': None,
    'max_score_action': 'warn',
    'max_score_message': None,
    # Season segments (requires migrate_add_segments.py)
    'segment_start_week': None,
    'segment_end_week': None,
    # Scoring format
    'scoring_mode': 'match_play',
    # Course configuration
    'multi_course': 0,
}


@bp.route('/season/<int:season_id>/settings', methods=['GET', 'POST'])
@admin_required
def settings(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    # Existing row or None
    existing = get_league_settings(db, season_id, league_id)

    if request.method == 'POST':
        def _int(key, default=None):
            v = request.form.get(key, '').strip()
            try:
                return int(v) if v != '' else default
            except (ValueError, TypeError):
                return default

        def _float(key, default=None):
            v = request.form.get(key, '').strip()
            try:
                return float(v) if v != '' else default
            except (ValueError, TypeError):
                return default

        def _bool(key):
            return 1 if request.form.get(key) == '1' else 0

        def _str(key, default=''):
            return request.form.get(key, '').strip() or default

        data = {
            'holes_per_round':               _int('holes_per_round', 9),
            'scoring_type':                  _str('scoring_type', 'net'),
            'match_play_points_per_hole':    _int('match_play_points_per_hole', 2),
            'match_play_overall_point':      _int('match_play_overall_point', 2),
            'ab_designation_method':         _str('ab_designation_method', 'weekly'),
            'playoff_teams':                 _int('playoff_teams', 4),
            'finals_weeks':                  _int('finals_weeks', 2),
            'min_rounds_for_handicap':       _int('min_rounds_for_handicap', 2),
            'rounds_to_average':             _int('rounds_to_average', 4),
            'high_scores_to_drop':           _int('high_scores_to_drop', 1),
            'handicap_percent':              _float('handicap_percent', 90.0),
            'max_handicap_index':            _float('max_handicap_index', 18.0),
            'max_score_over_handicap':       _int('max_score_over_handicap', 18),
            'negative_handicap_allowed':     _bool('negative_handicap_allowed'),
            'carry_scores_across_seasons':   _bool('carry_scores_across_seasons'),
            'diff_calculation_type':         _str('diff_calculation_type', 'par'),
            'skins_default_gross_net':       _str('skins_default_gross_net', 'gross'),
            'skins_default_amount':          _float('skins_default_amount'),
            'self_reporting_enabled':        _bool('self_reporting_enabled'),
            'self_reporting_requires_approval': _bool('self_reporting_requires_approval'),
            'skins_self_optin_enabled':      _bool('skins_self_optin_enabled'),
            'max_score_per_hole':            _int('max_score_per_hole'),
            'max_score_action':              _str('max_score_action', 'warn'),
            'max_score_message':             request.form.get('max_score_message', '').strip() or None,
            'segment_start_week':            _int('segment_start_week'),
            'segment_end_week':              _int('segment_end_week'),
            'scoring_mode':                  _str('scoring_mode', 'match_play'),
            'multi_course':                  _bool('multi_course'),
        }

        if existing:
            db.execute(
                """UPDATE league_settings SET
                   holes_per_round=%(holes_per_round)s,
                   scoring_type=%(scoring_type)s,
                   match_play_points_per_hole=%(match_play_points_per_hole)s,
                   match_play_overall_point=%(match_play_overall_point)s,
                   ab_designation_method=%(ab_designation_method)s,
                   playoff_teams=%(playoff_teams)s,
                   finals_weeks=%(finals_weeks)s,
                   min_rounds_for_handicap=%(min_rounds_for_handicap)s,
                   rounds_to_average=%(rounds_to_average)s,
                   high_scores_to_drop=%(high_scores_to_drop)s,
                   handicap_percent=%(handicap_percent)s,
                   max_handicap_index=%(max_handicap_index)s,
                   max_score_over_handicap=%(max_score_over_handicap)s,
                   negative_handicap_allowed=%(negative_handicap_allowed)s,
                   carry_scores_across_seasons=%(carry_scores_across_seasons)s,
                   diff_calculation_type=%(diff_calculation_type)s,
                   skins_default_gross_net=%(skins_default_gross_net)s,
                   skins_default_amount=%(skins_default_amount)s,
                   self_reporting_enabled=%(self_reporting_enabled)s,
                   self_reporting_requires_approval=%(self_reporting_requires_approval)s,
                   skins_self_optin_enabled=%(skins_self_optin_enabled)s,
                   max_score_per_hole=%(max_score_per_hole)s,
                   max_score_action=%(max_score_action)s,
                   max_score_message=%(max_score_message)s,
                   segment_start_week=%(segment_start_week)s,
                   segment_end_week=%(segment_end_week)s,
                   scoring_mode=%(scoring_mode)s,
                   multi_course=%(multi_course)s
                   WHERE season_id=%(season_id)s AND league_id=%(league_id)s""",
                {**data, 'season_id': season_id, 'league_id': league_id}
            )
        else:
            db.execute(
                """INSERT INTO league_settings
                   (league_id, season_id,
                    holes_per_round, scoring_type,
                    match_play_points_per_hole, match_play_overall_point,
                    ab_designation_method,
                    playoff_teams, finals_weeks,
                    min_rounds_for_handicap, rounds_to_average, high_scores_to_drop,
                    handicap_percent, max_handicap_index, max_score_over_handicap,
                    negative_handicap_allowed, carry_scores_across_seasons,
                    diff_calculation_type,
                    skins_default_gross_net, skins_default_amount,
                    self_reporting_enabled, self_reporting_requires_approval,
                    skins_self_optin_enabled,
                    max_score_per_hole, max_score_action, max_score_message,
                    segment_start_week, segment_end_week,
                    scoring_mode, multi_course)
                   VALUES
                   (%(league_id)s, %(season_id)s,
                    %(holes_per_round)s, %(scoring_type)s,
                    %(match_play_points_per_hole)s, %(match_play_overall_point)s,
                    %(ab_designation_method)s,
                    %(playoff_teams)s, %(finals_weeks)s,
                    %(min_rounds_for_handicap)s, %(rounds_to_average)s, %(high_scores_to_drop)s,
                    %(handicap_percent)s, %(max_handicap_index)s, %(max_score_over_handicap)s,
                    %(negative_handicap_allowed)s, %(carry_scores_across_seasons)s,
                    %(diff_calculation_type)s,
                    %(skins_default_gross_net)s, %(skins_default_amount)s,
                    %(self_reporting_enabled)s, %(self_reporting_requires_approval)s,
                    %(skins_self_optin_enabled)s,
                    %(max_score_per_hole)s, %(max_score_action)s, %(max_score_message)s,
                    %(segment_start_week)s, %(segment_end_week)s,
                    %(scoring_mode)s, %(multi_course)s)""",
                {**data, 'league_id': league_id, 'season_id': season_id}
            )

        # Save tiebreaker settings
        tb_data = {
            'priority_1': request.form.get('priority_1', 'head_to_head'),
            'priority_2': request.form.get('priority_2', 'points_percentage'),
            'priority_3': request.form.get('priority_3', 'all_play_record'),
            'priority_4': request.form.get('priority_4', 'scoring_average'),
        }
        _save_tiebreaker_cfg(db, season_id, league_id, tb_data)

        db.commit()
        flash('Settings saved successfully.', 'success')
        return redirect(url_for('admin.settings', season_id=season_id))

    # Build a plain dict for the template (existing row or defaults)
    cfg = dict(_SETTINGS_DEFAULTS)
    if existing:
        for k in _SETTINGS_DEFAULTS.keys():
            try:
                cfg[k] = existing[k]
            except (IndexError, KeyError):
                pass  # column not yet in this row — keep default

    tb_cfg = _get_tiebreaker_cfg(db, season_id, league_id)
    return render_template('admin/settings.html',
                           season=season, all_seasons=all_seasons,
                           cfg=cfg, tb_cfg=tb_cfg)


# ---------------------------------------------------------------------------
# Unlock page — informational, redirects to edit
# ---------------------------------------------------------------------------

@bp.route('/scores/<int:matchup_id>/unlock')
@admin_required
def unlock_scores(matchup_id):
    """Just redirect straight to the edit page — no deletion needed."""
    return redirect(url_for('admin.edit_scores', matchup_id=matchup_id))


# ---------------------------------------------------------------------------
# Edit scores — pre-filled grid, updates in place
# ---------------------------------------------------------------------------

@bp.route('/scores/<int:matchup_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_scores(matchup_id):
    db = get_db()

    matchup = db.execute(
        """SELECT m.*, s.season_name, s.league_id, s.season_id
           FROM matchups m JOIN seasons s ON m.season_id = s.season_id
           WHERE m.matchup_id = %s""",
        (matchup_id,)
    ).fetchone()
    if not matchup or matchup['league_id'] != session['league_id']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('seasons.index'))
    if matchup['status'] != 'completed':
        flash('No scores to edit — enter scores normally.', 'error')
        return redirect(url_for('scores.enter', matchup_id=matchup_id))

    round_row = db.execute("SELECT * FROM rounds WHERE matchup_id = %s", (matchup_id,)).fetchone()
    if not round_row:
        flash('Round data not found.', 'error')
        return redirect(url_for('admin.panel', season_id=matchup['season_id']))

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
        (round_row['tee_id'],)
    ).fetchall()
    tee    = db.execute("SELECT * FROM tees    WHERE tee_id    = %s", (round_row['tee_id'],)).fetchone()
    course = db.execute("SELECT * FROM courses WHERE course_id = %s", (round_row['course_id'],)).fetchone()

    # Scorecards with player + existing hole scores
    scorecards = db.execute(
        """SELECT sc.scorecard_id, sc.player_id, sc.team_id, sc.handicap_at_time_of_play,
                  p.first_name, p.last_name
           FROM scorecards sc JOIN players p ON sc.player_id = p.player_id
           WHERE sc.round_id = %s""",
        (round_row['round_id'],)
    ).fetchall()

    # Map scorecard_id -> existing gross scores per hole
    existing_scores = {}   # player_id -> {hole_number: gross_score}
    for sc in scorecards:
        hs = db.execute(
            "SELECT hole_number, gross_score FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
            (sc['scorecard_id'],)
        ).fetchall()
        existing_scores[sc['player_id']] = {h['hole_number']: h['gross_score'] for h in hs}

    # Existing A/B roles from match_results
    mr_rows = db.execute(
        "SELECT player_id, role, team_id FROM match_results WHERE matchup_id = %s",
        (matchup_id,)
    ).fetchall()
    role_map = {r['player_id']: r['role']    for r in mr_rows}
    team_map = {r['player_id']: r['team_id'] for r in mr_rows}

    if request.method == 'POST':
        return _save_edited_scores(
            db, matchup, round_row, scorecards, holes,
            role_map, team_map, request.form
        )

    return render_template('admin/edit_scores.html',
                           matchup=matchup, round_row=round_row,
                           scorecards=scorecards, holes=holes,
                           existing_scores=existing_scores,
                           tee=tee, course=course,
                           role_map=role_map)


def _save_edited_scores(db, matchup, round_row, scorecards, holes,
                         role_map, team_map, form):
    """Parse new gross scores, update hole_scores, rebuild match_results."""
    season_id = matchup['season_id']
    league_id = session['league_id']

    # Parse gross scores
    gross = {}
    for sc in scorecards:
        pid = sc['player_id']
        scores = []
        for h in holes:
            val = form.get(f"score_{pid}_{h['hole_number']}", '').strip()
            if not val:
                flash(f"Missing score for {sc['first_name']} {sc['last_name']}, hole {h['hole_number']}.", 'error')
                return redirect(url_for('admin.edit_scores', matchup_id=matchup['matchup_id']))
            try:
                scores.append(int(val))
            except ValueError:
                flash(f"Invalid score for {sc['first_name']} {sc['last_name']}.", 'error')
                return redirect(url_for('admin.edit_scores', matchup_id=matchup['matchup_id']))
        gross[pid] = scores

    # Use stored playing handicaps (don't change them for past rounds)
    playing_hcps = {sc['player_id']: sc['handicap_at_time_of_play'] for sc in scorecards}

    # Net scores per hole
    net = {}
    for sc in scorecards:
        pid = sc['player_id']
        net[pid] = []
        for i, h in enumerate(holes):
            strk = strokes_on_hole(playing_hcps[pid], h['handicap_index'], total_holes=len(holes))
            net[pid].append(gross[pid][i] - strk)

    # Keep original A/B roles; find opponents
    t1_id = matchup['team1_id']
    t2_id = matchup['team2_id']

    t1_a = next((p for p, r in role_map.items() if r == 'A' and team_map.get(p) == t1_id), None)
    t1_b = next((p for p, r in role_map.items() if r == 'B' and team_map.get(p) == t1_id), None)
    t2_a = next((p for p, r in role_map.items() if r == 'A' and team_map.get(p) == t2_id), None)
    t2_b = next((p for p, r in role_map.items() if r == 'B' and team_map.get(p) == t2_id), None)

    def match_result(pid_x, pid_y):
        h_x, h_y = 0.0, 0.0
        for i in range(len(holes)):
            px, py = calc_match_play(net[pid_x][i], net[pid_y][i])
            h_x += px; h_y += py
        ov_x, ov_y = calc_match_play(sum(net[pid_x]), sum(net[pid_y]))
        return h_x, h_y, ov_x, ov_y

    aa = match_result(t1_a, t2_a)
    bb = match_result(t1_b, t2_b)

    # Update hole_scores in place
    sc_id_map = {sc['player_id']: sc['scorecard_id'] for sc in scorecards}
    for sc in scorecards:
        pid  = sc['player_id']
        scid = sc_id_map[pid]
        for i, h in enumerate(holes):
            db.execute(
                """UPDATE hole_scores
                   SET gross_score = %s, net_score = %s, score_differential = %s
                   WHERE scorecard_id = %s AND hole_number = %s""",
                (gross[pid][i], net[pid][i], gross[pid][i] - h['par'], scid, h['hole_number'])
            )

    # Rebuild match_results
    db.execute("DELETE FROM match_results WHERE matchup_id = %s", (matchup['matchup_id'],))
    roles = {
        t1_a: ('A', t1_id, t2_a, aa[0], aa[2]),
        t2_a: ('A', t2_id, t1_a, aa[1], aa[3]),
        t1_b: ('B', t1_id, t2_b, bb[0], bb[2]),
        t2_b: ('B', t2_id, t1_b, bb[1], bb[3]),
    }
    for pid, (role, tid, opp, hole_pts, ov_pt) in roles.items():
        db.execute(
            """INSERT INTO match_results
               (matchup_id, team_id, player_id, role,
                hole_points_won, overall_point_won, total_points, opponent_player_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (matchup['matchup_id'], tid, pid, role,
             hole_pts, ov_pt, hole_pts + ov_pt, opp)
        )

    # Update scorecard totals
    for sc in scorecards:
        pid  = sc['player_id']
        scid = sc_id_map[pid]
        total_gross = sum(gross[pid])
        total_net   = sum(net[pid])
        hole_pts_tot = roles[pid][3] if pid in roles else 0
        ov_pt_tot    = roles[pid][4] if pid in roles else 0
        total_pts    = hole_pts_tot + ov_pt_tot
        db.execute(
            """UPDATE scorecards
               SET total_gross = %s, total_net = %s, total_points = %s
               WHERE scorecard_id = %s""",
            (total_gross, total_net, total_pts, scid)
        )

    db.commit()
    flash('Scores updated successfully.', 'success')
    return redirect(url_for('admin.edit_scores', matchup_id=matchup['matchup_id']))


# ---------------------------------------------------------------------------
# Absence log for a season
# ---------------------------------------------------------------------------

@bp.route('/season/<int:season_id>/absences')
@admin_required
def absence_log(season_id):
    db = get_db()
    season = db.execute(
        'SELECT * FROM seasons WHERE season_id = %s AND league_id = %s',
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    absence_rows = db.execute(
        """SELECT pa.*,
                  p.first_name  AS absent_first,  p.last_name  AS absent_last,
                  sub.first_name AS sub_first,    sub.last_name AS sub_last,
                  m.week_number,
                  r.round_number, r.round_date,
                  m.matchup_id
           FROM player_absences pa
           JOIN players p ON pa.player_id = p.player_id
           LEFT JOIN players sub ON pa.sub_player_id = sub.player_id
           LEFT JOIN matchups m ON pa.matchup_id = m.matchup_id
           LEFT JOIN rounds r   ON pa.round_id   = r.round_id
           WHERE p.league_id = %s
             AND (m.season_id = %s OR pa.round_id IN (
                 SELECT round_id FROM rounds r2
                 JOIN matchups m2 ON r2.matchup_id = m2.matchup_id
                 WHERE m2.season_id = %s
             ))
           ORDER BY m.week_number DESC NULLS LAST, pa.absence_id DESC""",
        (session['league_id'], season_id, season_id)
    ).fetchall()

    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (session['league_id'],)
    ).fetchall()

    return render_template('admin/absences.html',
                           season=season, absence_rows=absence_rows,
                           all_seasons=all_seasons)


# ---------------------------------------------------------------------------
# Alias: admin.season → same as admin.landing (used by nav and templates)
# ---------------------------------------------------------------------------

@bp.route('/season')
@admin_required
def season():
    return landing()


# ---------------------------------------------------------------------------
# API Key management
# ---------------------------------------------------------------------------

@bp.route('/api-settings', methods=['GET', 'POST'])
@admin_required
def api_settings():
    import secrets as _secrets
    db = get_db()
    league_id = session['league_id']

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            new_key = 'bglk_' + _secrets.token_urlsafe(32)
            try:
                db.execute("UPDATE leagues SET api_key = %s WHERE league_id = %s",
                           (new_key, league_id))
                db.commit()
                flash('New API key generated. Copy it now — it will not be shown again in full.', 'success')
            except Exception:
                # api_key column may not exist yet if migration hasn't been run
                flash('Run migrate_api_key.py first to add the api_key column.', 'error')
        elif action == 'revoke':
            try:
                db.execute("UPDATE leagues SET api_key = NULL WHERE league_id = %s", (league_id,))
                db.commit()
                flash('API key revoked. All API access for this league is now disabled.', 'warning')
            except Exception:
                flash('Error revoking key.', 'error')
        return redirect(url_for('admin.api_settings'))

    # GET — load current key
    try:
        row = db.execute("SELECT api_key FROM leagues WHERE league_id = %s", (league_id,)).fetchone()
        api_key = row['api_key'] if row else None
    except Exception:
        api_key = None

    season = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    return render_template('admin/api_settings.html', season=season, api_key=api_key)


# ---------------------------------------------------------------------------
# Season Carry-Over Handicap Seeding
# ---------------------------------------------------------------------------

@bp.route('/season/<int:season_id>/seed-handicaps', methods=['GET', 'POST'])
@admin_required
def seed_handicaps(season_id):
    """
    Preview and apply handicap seeding: set each player's starting_handicap
    to their most-recently computed handicap_index (from any season).
    """
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    # Fetch all players in this season's teams
    players = db.execute(
        """SELECT DISTINCT
               p.player_id, p.first_name, p.last_name, p.starting_handicap
          FROM players p
          JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
         WHERE t.season_id = %s AND t.league_id = %s
         ORDER BY p.last_name, p.first_name""",
        (season_id, league_id)
    ).fetchall()

    # For each player, find their latest computed handicap across all seasons
    seed_rows = []
    for p in players:
        pid = p['player_id']
        hcp_row = db.execute(
            """SELECT handicap_index, calculated_date
                 FROM handicap_history
                WHERE player_id = %s
                ORDER BY calculated_date DESC, handicap_id DESC
                LIMIT 1""",
            (pid,)
        ).fetchone()

        current_start = p['starting_handicap']
        if hcp_row:
            proposed = round(float(hcp_row['handicap_index']), 1)
            source = f"Computed {hcp_row['calculated_date']}"
            has_computed = True
        else:
            proposed = current_start  # nothing to seed
            source = "No history — no change"
            has_computed = False

        changed = has_computed and (
            current_start is None or
            abs(float(current_start) - proposed) >= 0.05
        )

        seed_rows.append({
            'player_id':     pid,
            'name':          f"{p['first_name']} {p['last_name']}",
            'current_start': current_start,
            'proposed':      proposed,
            'source':        source,
            'has_computed':  has_computed,
            'changed':       changed,
        })

    if request.method == 'POST':
        updated = 0
        for row in seed_rows:
            if row['has_computed']:
                db.execute(
                    "UPDATE players SET starting_handicap = %s WHERE player_id = %s AND league_id = %s",
                    (row['proposed'], row['player_id'], league_id)
                )
                updated += 1
        db.commit()
        flash(
            f"Handicap seeding complete: {updated} player(s) updated.",
            'success'
        )
        return redirect(url_for('seasons.detail', season_id=season_id))

    changes_count = sum(1 for r in seed_rows if r['changed'])
    return render_template(
        'admin/seed_handicaps.html',
        season=season,
        seed_rows=seed_rows,
        changes_count=changes_count,
    )


@bp.route('/season/<int:season_id>/week/<int:week_num>/send-reminders', methods=['POST'])
@admin_required
def send_week_reminders(season_id, week_num):
    """Send personalized pre-round reminder emails to all players for a week."""
    from routes.email_config import send_round_reminder_emails
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT season_name FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('admin.landing'))

    sent, err = send_round_reminder_emails(db, league_id, season_id, week_num)

    if err and sent == 0:
        flash(f'Could not send reminders: {err}', 'error')
    elif sent == 0:
        flash('No emails sent — no players have email addresses on file for this week.', 'warning')
    elif err:
        flash(f'Sent {sent} reminder(s), but some failed: {err}', 'warning')
    else:
        flash(f'✅ {sent} reminder email(s) sent for Week {week_num}.', 'success')

    return redirect(url_for('admin.panel', season_id=season_id))


# ---------------------------------------------------------------------------
# Commissioner Overview Dashboard  /admin/overview
# ---------------------------------------------------------------------------

@bp.route('/overview')
@admin_required
def overview():
    db = get_db()
    league_id = session['league_id']

    # -- Latest season --
    season = db.execute(
        "SELECT * FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (league_id,)
    ).fetchone()
    season_id = season['season_id'] if season else None

    all_seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()

    # -- Pending actions --
    pending_self_reports = 0
    try:
        r = db.execute(
            """SELECT COUNT(*) AS cnt FROM score_submissions ss
               JOIN matchups m ON ss.matchup_id = m.matchup_id
               JOIN seasons  s ON m.season_id   = s.season_id
               WHERE s.league_id = %s AND ss.status = 'pending'""",
            (league_id,)
        ).fetchone()
        pending_self_reports = r['cnt'] if r else 0
    except Exception:
        pass

    open_sub_requests = 0
    try:
        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM sub_requests WHERE league_id=%s AND status='open'",
            (league_id,)
        ).fetchone()
        open_sub_requests = r['cnt'] if r else 0
    except Exception:
        pass

    pending_registrations = 0
    try:
        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM player_registrations WHERE league_id=%s AND status='pending'",
            (league_id,)
        ).fetchone()
        pending_registrations = r['cnt'] if r else 0
    except Exception:
        pass

    total_pending = pending_self_reports + open_sub_requests + pending_registrations

    # -- Season stats --
    rounds_completed = 0
    rounds_total = 0
    standings_leader = None
    next_round = None
    unlocked_scores = 0

    if season_id:
        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id=%s AND status='completed' AND is_bye=0",
            (season_id,)
        ).fetchone()
        rounds_completed = r['cnt'] if r else 0

        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id=%s AND is_bye=0",
            (season_id,)
        ).fetchone()
        rounds_total = r['cnt'] if r else 0

        # standings leader — team with most total_points
        leader_row = db.execute(
            """SELECT t.team_id, t.team_name,
                      p1.last_name AS p1_last, p2.last_name AS p2_last,
                      COALESCE(SUM(mr.total_points), 0) AS total_pts
               FROM teams t
               LEFT JOIN players p1 ON t.player1_id = p1.player_id
               LEFT JOIN players p2 ON t.player2_id = p2.player_id
               LEFT JOIN match_results mr ON mr.team_id = t.team_id
                   AND mr.matchup_id IN (
                       SELECT matchup_id FROM matchups WHERE season_id=%s
                   )
               WHERE t.season_id=%s AND t.league_id=%s
               GROUP BY t.team_id, t.team_name, p1.last_name, p2.last_name
               ORDER BY total_pts DESC
               LIMIT 1""",
            (season_id, season_id, league_id)
        ).fetchone()
        if leader_row:
            label = leader_row['team_name'] or f"{leader_row['p1_last'] or '?'} / {leader_row['p2_last'] or '?'}"
            standings_leader = {'label': label, 'pts': int(leader_row['total_pts'])}

        # next upcoming round
        next_round = db.execute(
            """SELECT m.week_number, m.scheduled_date, m.tee_time,
                      c.course_name, te.tee_name
               FROM matchups m
               LEFT JOIN courses c ON m.course_id = c.course_id
               LEFT JOIN tees   te ON m.tee_id    = te.tee_id
               WHERE m.season_id=%s AND m.status != 'completed' AND m.is_bye=0
               ORDER BY m.week_number ASC
               LIMIT 1""",
            (season_id,)
        ).fetchone()

        # unlocked scores (completed matchups that an admin unlocked for editing)
        try:
            r = db.execute(
                """SELECT COUNT(DISTINCT r.matchup_id) AS cnt
                   FROM rounds r
                   JOIN matchups m ON r.matchup_id = m.matchup_id
                   WHERE m.season_id=%s AND r.is_locked=0 AND m.status='completed'""",
                (season_id,)
            ).fetchone()
            unlocked_scores = r['cnt'] if r else 0
        except Exception:
            unlocked_scores = 0

    # -- Dues status --
    dues_paid = 0
    dues_total = 0
    dues_amount = None
    if season_id:
        try:
            ls = db.execute(
                "SELECT dues_amount FROM league_settings WHERE season_id=%s AND league_id=%s",
                (season_id, league_id)
            ).fetchone()
            if ls:
                dues_amount = ls['dues_amount']
            r = db.execute(
                """SELECT COUNT(DISTINCT tp.player_id) AS total
                   FROM teams t
                   JOIN players tp ON (tp.player_id = t.player1_id OR tp.player_id = t.player2_id)
                   WHERE t.season_id=%s AND t.league_id=%s AND tp.active=1""",
                (season_id, league_id)
            ).fetchone()
            dues_total = r['total'] if r else 0
            r = db.execute(
                """SELECT COUNT(DISTINCT dp.player_id) AS paid
                   FROM dues_payments dp
                   WHERE dp.season_id=%s AND dp.league_id=%s""",
                (season_id, league_id)
            ).fetchone()
            dues_paid = r['paid'] if r else 0
        except Exception:
            pass

    # -- Recent completed rounds (last 8) --
    recent_rounds = []
    if season_id:
        rows = db.execute(
            """SELECT m.week_number, m.scheduled_date, m.matchup_id,
                      t1.team_name AS t1_name, p1a.last_name AS t1_p1, p1b.last_name AS t1_p2,
                      t2.team_name AS t2_name, p2a.last_name AS t2_p1, p2b.last_name AS t2_p2,
                      COALESCE(SUM(CASE WHEN mr.team_id = m.team1_id THEN mr.total_points END), 0) AS pts1,
                      COALESCE(SUM(CASE WHEN mr.team_id = m.team2_id THEN mr.total_points END), 0) AS pts2
               FROM matchups m
               JOIN teams t1 ON t1.team_id = m.team1_id
               JOIN teams t2 ON t2.team_id = m.team2_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
               LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               LEFT JOIN match_results mr ON mr.matchup_id = m.matchup_id
               WHERE m.season_id=%s AND m.status='completed' AND m.is_bye=0
               GROUP BY m.matchup_id, m.week_number, m.scheduled_date,
                        t1.team_name, p1a.last_name, p1b.last_name,
                        t2.team_name, p2a.last_name, p2b.last_name
               ORDER BY m.week_number DESC, m.matchup_id DESC
               LIMIT 8""",
            (season_id,)
        ).fetchall()
        for row in rows:
            label1 = row['t1_name'] or f"{row['t1_p1'] or '?'}/{row['t1_p2'] or '?'}"
            label2 = row['t2_name'] or f"{row['t2_p1'] or '?'}/{row['t2_p2'] or '?'}"
            pts1 = int(row['pts1'] or 0)
            pts2 = int(row['pts2'] or 0)
            recent_rounds.append({
                'week': row['week_number'],
                'date': row['scheduled_date'],
                'matchup_id': row['matchup_id'],
                'label1': label1, 'pts1': pts1,
                'label2': label2, 'pts2': pts2,
                'winner': 1 if pts1 > pts2 else (2 if pts2 > pts1 else 0),
            })

    # -- Player count + active users --
    player_count = 0
    try:
        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM players WHERE league_id=%s AND active=1",
            (league_id,)
        ).fetchone()
        player_count = r['cnt'] if r else 0
    except Exception:
        pass

    user_count = 0
    try:
        r = db.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE league_id=%s",
            (league_id,)
        ).fetchone()
        user_count = r['cnt'] if r else 0
    except Exception:
        pass

    # -- Active announcements --
    active_ann = 0
    try:
        from datetime import date
        today = date.today().isoformat()
        r = db.execute(
            """SELECT COUNT(*) AS cnt FROM announcements
               WHERE league_id=%s AND (expires_at IS NULL OR expires_at >= %s)""",
            (league_id, today)
        ).fetchone()
        active_ann = r['cnt'] if r else 0
    except Exception:
        pass

    # -- Recent forum activity --
    recent_forum = []
    try:
        rows = db.execute(
            """SELECT topic_id, title, reply_count, updated_at
               FROM forum_topics WHERE league_id=%s
               ORDER BY updated_at DESC LIMIT 3""",
            (league_id,)
        ).fetchall()
        recent_forum = [dict(r) for r in rows]
    except Exception:
        pass

    return render_template('admin/overview.html',
        season=season, all_seasons=all_seasons,
        total_pending=total_pending,
        pending_self_reports=pending_self_reports,
        open_sub_requests=open_sub_requests,
        pending_registrations=pending_registrations,
        rounds_completed=rounds_completed,
        rounds_total=rounds_total,
        standings_leader=standings_leader,
        next_round=next_round,
        unlocked_scores=unlocked_scores,
        dues_paid=dues_paid, dues_total=dues_total, dues_amount=dues_amount,
        recent_rounds=recent_rounds,
        player_count=player_count,
        user_count=user_count,
        active_ann=active_ann,
        recent_forum=recent_forum,
    )


# ---------------------------------------------------------------------------
# League Profile (name + login code)
# ---------------------------------------------------------------------------

@bp.route('/league-profile', methods=['GET', 'POST'])
@admin_required
def league_profile():
    import re
    db = get_db()
    league_id = session['league_id']

    league = db.execute(
        "SELECT league_name, login_code FROM leagues WHERE league_id = %s",
        (league_id,)
    ).fetchone()

    if request.method == 'POST':
        new_name = request.form.get('league_name', '').strip()
        new_code = request.form.get('login_code', '').strip().lower()

        errors = []
        if not new_name:
            errors.append('League name is required.')
        if not new_code:
            errors.append('Login code is required.')
        elif not re.match(r'^[a-z0-9_-]+$', new_code):
            errors.append('Login code may only contain letters, numbers, hyphens, and underscores.')
        elif len(new_code) < 3 or len(new_code) > 50:
            errors.append('Login code must be between 3 and 50 characters.')

        if not errors:
            # Check name uniqueness (excluding current league)
            if db.execute(
                "SELECT league_id FROM leagues WHERE LOWER(league_name) = LOWER(%s) AND league_id != %s",
                (new_name, league_id)
            ).fetchone():
                errors.append('A league with that name already exists.')

            # Check login_code uniqueness (excluding current league)
            if db.execute(
                "SELECT league_id FROM leagues WHERE login_code = %s AND league_id != %s",
                (new_code, league_id)
            ).fetchone():
                errors.append('That login code is already taken.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('admin/league_profile.html',
                                   league_name=new_name, login_code=new_code)

        db.execute(
            "UPDATE leagues SET league_name = %s, login_code = %s WHERE league_id = %s",
            (new_name, new_code, league_id)
        )
        db.commit()
        session['league_name'] = new_name
        flash('League profile updated.', 'success')
        return redirect(url_for('admin.league_profile'))

    return render_template('admin/league_profile.html',
                           league_name=league['league_name'] if league else '',
                           login_code=league['login_code'] if league else '')


# ---------------------------------------------------------------------------
# In-app DB migration runner
# ---------------------------------------------------------------------------

@bp.route('/run-migrations', methods=['GET', 'POST'])
@admin_required
def run_migrations():
    if database.is_postgres():
        flash('Running on Postgres — tables are created from schema_postgres.sql at startup; '
              'no in-app migration needed.', 'info')
        return render_template('admin/run_migrations.html', results=[], done=True, missing=0)

    import sqlite3 as _sq
    db_path = current_app.config['DATABASE']
    results = []

    def _ht(cur, name):
        return table_exists(cur, name)

    MIGRATIONS = [
        ('week_notes', "CREATE TABLE week_notes (note_id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER NOT NULL, season_id INTEGER NOT NULL, week_number INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(league_id, season_id, week_number))"),
        ('contests', "CREATE TABLE contests (contest_id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER NOT NULL, season_id INTEGER NOT NULL, week_number INTEGER, title TEXT NOT NULL, contest_type TEXT NOT NULL DEFAULT 'custom', description TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')))"),
        ('contest_results', "CREATE TABLE contest_results (result_id INTEGER PRIMARY KEY AUTOINCREMENT, contest_id INTEGER NOT NULL, player_id INTEGER NOT NULL, value_text TEXT, notes TEXT, rank INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')))"),
        ('dues_payments', "CREATE TABLE dues_payments (payment_id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER NOT NULL, season_id INTEGER NOT NULL, player_id INTEGER NOT NULL, amount REAL NOT NULL DEFAULT 0, paid_date TEXT NOT NULL DEFAULT (date('now')), notes TEXT, recorded_by INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(league_id, season_id, player_id))"),
        ('player_registrations', "CREATE TABLE player_registrations (reg_id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL, email TEXT, starting_handicap REAL DEFAULT 18.0, message TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT (datetime('now')), reviewed_at TEXT, reviewed_by_user_id INTEGER, player_id INTEGER)"),
        ('player_availability', "CREATE TABLE player_availability (avail_id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, league_id INTEGER NOT NULL, season_id INTEGER NOT NULL, week_number INTEGER NOT NULL, available INTEGER NOT NULL DEFAULT 1, note TEXT, updated_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(player_id, league_id, season_id, week_number))"),
        ('player_nicknames', "CREATE TABLE player_nicknames (nickname_id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, league_id INTEGER NOT NULL, nickname TEXT NOT NULL, is_primary INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE(player_id, league_id, nickname))"),
        ('handicap_adjustments', "CREATE TABLE handicap_adjustments (adj_id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, league_id INTEGER NOT NULL, adjustment REAL NOT NULL DEFAULT 0, reason TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), created_by_user_id INTEGER, UNIQUE(player_id, league_id))"),
    ]

    if request.method == 'POST':
        try:
            conn = _sq.connect(db_path)
            cur  = conn.cursor()
            for tname, ddl in MIGRATIONS:
                if not _ht(cur, tname):
                    cur.execute(ddl)
                    results.append((tname, 'created'))
                else:
                    results.append((tname, 'already exists'))
            conn.commit()
            conn.close()
            created = sum(1 for _, s in results if s == 'created')
            flash('Migrations complete — {} table(s) created.'.format(created), 'success')
        except Exception as e:
            flash('Migration error: {}'.format(e), 'error')
            results.append(('ERROR', str(e)))
        return render_template('admin/run_migrations.html', results=results, done=True)

    try:
        conn = _sq.connect(db_path)
        cur  = conn.cursor()
        for tname, _ in MIGRATIONS:
            results.append((tname, 'exists' if _ht(cur, tname) else 'MISSING'))
        conn.close()
    except Exception as e:
        results = [('ERROR', str(e))]
    missing = sum(1 for _, s in results if s == 'MISSING')
    return render_template('admin/run_migrations.html', results=results, done=False, missing=missing)
