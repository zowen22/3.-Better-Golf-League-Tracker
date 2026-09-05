from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import get_db, get_current_season_id
from routes.auth import login_required, admin_required
from routes.handicap import PRE_ELIGIBILITY_MARKER_PREFIX, get_week_handicap_standings_context
from routes.standings import get_standings_context
from routes.contests import get_week_contest_results_context
from routes.skins import get_week_skins_display
from datetime import datetime, timedelta
import random

bp = Blueprint('schedule', __name__, url_prefix='/schedule')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_single_course(db, season_id, league_id):
    """If multi_course=0, return (course_id, default_tee_id) for the league's
    one course, else return (None, None). Used to auto-populate matchups.

    A missing league_settings row (e.g. a brand-new season nobody has visited
    Settings for yet) is treated the same as multi_course=0 (its schema/UI
    default), NOT the same as multi_course=1 — otherwise a genuinely
    single-course league silently gets NULL course_id/tee_id on every
    matchup generated before the admin's first Settings save."""
    ls = db.execute(
        "SELECT multi_course FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if ls and ls['multi_course']:
        return None, None
    course = db.execute(
        "SELECT course_id, default_tee_id FROM courses WHERE league_id = %s ORDER BY course_id LIMIT 1",
        (league_id,)
    ).fetchone()
    if not course:
        return None, None
    return course['course_id'], course['default_tee_id']


# ---------------------------------------------------------------------------
# Shotgun-start tee time templates -- see
# Plans/2026-08-13-shotgun-tee-time-technical-spec.md. "Group 1" is a
# physical starting position, not a fixed team pairing -- which matchup
# lands in which slot each week is just schedule/creation order, assigned
# via matchups.slot_number. No stored "is this the default or a custom
# override" flag anywhere -- computed at display time by comparing a
# matchup's actual tee_time/starting_hole against what the template says
# for its slot + that week's nine.
# ---------------------------------------------------------------------------

def _shotgun_enabled(db, season_id, league_id):
    row = db.execute(
        "SELECT shotgun_start_enabled FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    return bool(row and row['shotgun_start_enabled'])


def _open_schedule_enabled(db, season_id, league_id):
    row = db.execute(
        "SELECT open_schedule_enabled FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    return bool(row and row['open_schedule_enabled'])


def _shotgun_slots_needed(db, season_id, league_id):
    """Number of physical starting slots a shotgun week needs -- derived
    from team count (ceil(team_count / 2), one slot per pairing including
    a lone bye), not a separate configurable setting."""
    team_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM teams WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()['cnt']
    return (team_count + 1) // 2 if team_count else 0


def _sync_shotgun_slot_count(db, season_id, league_id):
    """Additive only -- inserts any missing slot_number rows (1..N) with
    blank time/holes, never touches or deletes a row an admin already
    filled in. Called when Shotgun Start is turned on, and available as
    an explicit re-sync action if team count changes later."""
    needed = _shotgun_slots_needed(db, season_id, league_id)
    existing = {r['slot_number'] for r in db.execute(
        "SELECT DISTINCT slot_number FROM shotgun_slot_templates WHERE season_id = %s AND slot_label IS NULL",
        (season_id,)
    ).fetchall()}
    for slot in range(1, needed + 1):
        if slot not in existing:
            db.execute(
                "INSERT INTO shotgun_slot_templates (season_id, slot_number) VALUES (%s, %s)"
                " ON CONFLICT (season_id, slot_number, slot_label) DO NOTHING",
                (season_id, slot)
            )


def _tee_nine(db, tee_id):
    """'front'/'back'/'full'/None for a given tee_id -- which nine a week
    is playing is derived from its matchups' tee_id, not stored directly."""
    if not tee_id:
        return None
    row = db.execute("SELECT nine FROM tees WHERE tee_id = %s", (tee_id,)).fetchone()
    return row['nine'] if row else None


def _shotgun_template_by_slot(db, season_id):
    """{slot_number: row} for the season's primary (non-A/B-labeled) slots
    -- used for auto-population at schedule-generation time. Labeled (A/B
    shared-hole) variants are a manual setup refinement on the template
    management page, not part of automatic assignment."""
    rows = db.execute(
        "SELECT * FROM shotgun_slot_templates WHERE season_id = %s AND slot_label IS NULL"
        " ORDER BY slot_number",
        (season_id,)
    ).fetchall()
    return {r['slot_number']: r for r in rows}


def _shotgun_hole_for_nine(template_row, nine):
    if not template_row:
        return None
    if nine == 'back':
        return template_row['back_nine_hole']
    return template_row['front_nine_hole']  # front/full/unknown all default to the front-hole column


# ---------------------------------------------------------------------------
# Round-robin generator (circle method)
# ---------------------------------------------------------------------------

def generate_round_robin(teams):
    teams = list(teams)
    random.shuffle(teams)
    if len(teams) % 2 == 1:
        teams.append(None)
    n = len(teams)
    rounds = []
    for r in range(n - 1):
        round_pairs = []
        for i in range(n // 2):
            t1 = teams[i]
            t2 = teams[n - 1 - i]
            round_pairs.append((t1, t2))
        rounds.append(round_pairs)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_player_handicap(db, player_id):
    """Return (handicap_index, is_provisional). is_provisional=True means
    the latest handicap_history row is a pre-eligibility temp handicap."""
    if not player_id:
        return None, False
    row = db.execute(
        "SELECT handicap_index, override_reason FROM handicap_history WHERE player_id = %s ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1",
        (player_id,)
    ).fetchone()
    if row:
        is_provisional = bool(row['override_reason'] and
                               row['override_reason'].startswith(PRE_ELIGIBILITY_MARKER_PREFIX))
        return row['handicap_index'], is_provisional
    row = db.execute("SELECT starting_handicap FROM players WHERE player_id = %s", (player_id,)).fetchone()
    return (row['starting_handicap'] or 0) if row else 0, False


def _build_team_info(db, season_id, league_id):
    """
    Returns (team_info_dict, team_num_map, teams_list).
    team_num_map: team_id -> sequential number (1-N by team_id order).
    team_info_dict: team_id -> dict with player names, handicaps, etc.
    """
    rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.player_id AS p1_id, p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.player_id AS p2_id, p2.first_name AS p2_first, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_id""",
        (season_id, league_id)
    ).fetchall()

    team_num_map = {}
    team_info    = {}
    teams_list   = []

    for i, t in enumerate(rows, start=1):
        p1_hdcp, p1_hdcp_provisional = _get_player_handicap(db, t['p1_id'])
        p2_hdcp, p2_hdcp_provisional = _get_player_handicap(db, t['p2_id'])
        info = {
            'team_id':   t['team_id'],
            'team_num':  i,
            'nickname':  t['team_name'],
            'p1_id':     t['p1_id'],
            'p1_name':   f"{t['p1_first'] or ''} {t['p1_last'] or ''}".strip() or '—',
            'p1_hdcp':   p1_hdcp,
            'p1_hdcp_provisional': p1_hdcp_provisional,
            'p2_id':     t['p2_id'],
            'p2_name':   f"{t['p2_first'] or ''} {t['p2_last'] or ''}".strip() or '—',
            'p2_hdcp':   p2_hdcp,
            'p2_hdcp_provisional': p2_hdcp_provisional,
            'label':     f"#{i} — {t['p1_last'] or '?'} / {t['p2_last'] or '?'}"
                         + (f" ({t['team_name']})" if t['team_name'] else ''),
        }
        team_num_map[t['team_id']] = i
        team_info[t['team_id']]    = info
        teams_list.append(info)

    return team_info, team_num_map, teams_list


def _build_weekly_rows(week_matchups, team_info, team_num_map):
    rows = []
    non_byes = [m for m in week_matchups if not m['is_bye']]
    byes     = [m for m in week_matchups if m['is_bye']]
    ordered  = non_byes + byes

    for i, m in enumerate(ordered, start=1):
        t1 = team_info.get(m['team1_id']) if m['team1_id'] else None
        t2 = team_info.get(m['team2_id']) if m['team2_id'] else None
        bt = team_info.get(m['bye_team_id']) if m['bye_team_id'] else None

        rows.append({
            'group':      i,
            'hole':       m['starting_hole'] if m['starting_hole'] else 1,
            'course':     m['course_name'] or '—',
            'side':       (m['side'] or '').capitalize() or '—',
            'tee_time':   m['tee_time'] or '—',
            'matchup_id': m['matchup_id'],
            'status':     m['status'],
            'is_bye':     bool(m['is_bye']),
            'week_type':  m['week_type'] or 'Normal',
            'team1':      t1 or bt,
            'team2':      t2,
        })
    return rows


def _build_yearly_rows(all_matchups, team_info, team_num_map, weeks_dropdown):
    by_week = {}
    for m in all_matchups:
        by_week.setdefault(m['week_number'], []).append(m)

    max_groups = max((len(v) for v in by_week.values()), default=0)

    rows = []
    for week_num, date in weeks_dropdown:
        week_matchups = by_week.get(week_num, [])
        non_byes = [m for m in week_matchups if not m['is_bye']]
        byes     = [m for m in week_matchups if m['is_bye']]

        week_type      = week_matchups[0]['week_type']   if week_matchups else 'Normal'
        course_name    = next((m['course_name'] for m in week_matchups if m['course_name']), '—')
        raw_course_id  = next((m['course_id']     for m in week_matchups if m['course_id']),   None)
        raw_tee_id     = next((m['tee_id']         for m in week_matchups if m['tee_id']),         None)
        side           = next((m['side']           for m in week_matchups if m['side']),           '')
        week_label     = next((m['week_label']     for m in week_matchups if m['week_label']),     None)
        makeup_for     = next((m['makeup_for_week'] for m in week_matchups if m['makeup_for_week']), None)

        groups      = []
        edit_cells  = []  # parallel list for inline edit mode
        for m in non_byes:
            t1n = team_num_map.get(m['team1_id'], '?')
            t2n = team_num_map.get(m['team2_id'], '?')
            groups.append(f"{t1n} v {t2n}")
            edit_cells.append({
                'matchup_id':    m['matchup_id'],
                'is_bye':        False,
                'is_league_bye': False,
                'team1_id':      m['team1_id'],
                'team2_id':      m['team2_id'],
                'bye_team_id':   None,
                'editable':      m['status'] != 'completed',
            })
        for m in byes:
            if m['bye_team_id'] is None:
                groups.append('League Bye')
                edit_cells.append({
                    'matchup_id':    m['matchup_id'],
                    'is_bye':        True,
                    'is_league_bye': True,
                    'team1_id':      None,
                    'team2_id':      None,
                    'bye_team_id':   None,
                    'editable':      False,
                })
            else:
                tn = team_num_map.get(m['bye_team_id'], '?')
                groups.append(f"{tn} — BYE")
                edit_cells.append({
                    'matchup_id':    m['matchup_id'],
                    'is_bye':        True,
                    'is_league_bye': False,
                    'team1_id':      None,
                    'team2_id':      None,
                    'bye_team_id':   m['bye_team_id'],
                    'editable':      m['status'] != 'completed',
                })

        while len(groups) < max_groups:
            groups.append('')
            edit_cells.append(None)

        has_completed = any(m['status'] == 'completed' for m in week_matchups)

        rows.append({
            'week_num':       week_num,
            'week_type':      week_type,
            'week_label':     week_label,
            'makeup_for':     makeup_for,
            'date':           date or '—',
            'raw_date':       date or '',
            'course':         course_name,
            'raw_course_id':  raw_course_id,
            'raw_tee_id':     raw_tee_id,
            'side':           side.capitalize() if side else '—',
            'raw_side':       side.lower() if side else '',
            'groups':         groups,
            'edit_cells':     edit_cells,
            'has_completed':  has_completed,
        })

    return rows, max_groups


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route('/current')
@login_required
def current():
    """Redirect to the current season's schedule. Pass ?week=all to land on all-dates view."""
    db = get_db()
    season_id = get_current_season_id(db, session['league_id'])
    if season_id:
        week = request.args.get('week')
        kwargs = {'season_id': season_id}
        if week:
            kwargs['week'] = week
        return redirect(url_for('schedule.index', **kwargs))
    flash('No seasons found.', 'error')
    return redirect(url_for('seasons.index'))


@bp.route('/<int:season_id>')
@login_required
def index(season_id):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    team_info, team_num_map, teams_list = _build_team_info(db, season_id, session['league_id'])
    team_count = len(teams_list)

    if _open_schedule_enabled(db, season_id, session['league_id']):
        # Open Schedule: a flat, date-ordered list of individual matches
        # instead of the week-grouped views below, which key everything off
        # week_number grouping that doesn't mean "a shared week" here.
        open_matchups = db.execute(
            """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.status,
                      m.team1_id, m.team2_id, m.course_id, m.tee_id, m.notes,
                      c.course_name, te.nine AS side
               FROM matchups m
               LEFT JOIN courses c  ON m.course_id = c.course_id
               LEFT JOIN tees    te ON m.tee_id    = te.tee_id
               WHERE m.season_id = %s
               ORDER BY m.scheduled_date DESC, m.matchup_id DESC""",
            (season_id,)
        ).fetchall()
        return render_template('schedule/index.html',
                               season=season, has_schedule=bool(open_matchups), view='open',
                               matchups=open_matchups, team_info=team_info,
                               teams_list=teams_list, team_count=team_count)

    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.round_number, m.scheduled_date,
                  m.status, m.is_bye, m.bye_team_id, m.notes,
                  m.tee_time, m.starting_hole, m.week_type,
                  m.team1_id, m.team2_id, m.course_id, m.tee_id,
                  m.week_label, m.makeup_for_week,
                  c.course_name,
                  te.nine AS side
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.season_id = %s
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()

    has_schedule = bool(matchups)

    if not has_schedule:
        return render_template('schedule/index.html',
                               season=season, has_schedule=False,
                               weeks_dropdown=[], teams_list=teams_list,
                               selected_week='', selected_team='',
                               team_count=team_count,
                               commissioner_note='')

    # Build week dropdown: [(week_num, date_str), ...]
    seen_weeks = {}
    for m in matchups:
        w = m['week_number']
        if w not in seen_weeks:
            seen_weeks[w] = m['scheduled_date']
    weeks_dropdown = sorted(seen_weeks.items(), key=lambda x: (x[1] or '9999-99-99', x[0]))

    # Determine default week (closest upcoming date, else last week)
    # Subtract 6h from UTC so the current week stays selected until ~1am EST
    today         = (datetime.now() - timedelta(hours=6)).strftime('%Y-%m-%d')
    selected_week = request.args.get('week', '').strip()
    selected_team = request.args.get('team', '').strip()

    if not selected_week:
        future = [(w, d) for w, d in weeks_dropdown if d and d >= today]
        if future:
            selected_week = str(future[0][0])
        else:
            selected_week = str(weeks_dropdown[-1][0])

    # ---- Yearly view -------------------------------------------------------
    if selected_week == 'all':
        yearly_rows, max_groups = _build_yearly_rows(
            matchups, team_info, team_num_map, weeks_dropdown
        )
        ls = db.execute(
            "SELECT holes_per_round, multi_course FROM league_settings WHERE season_id = %s AND league_id = %s",
            (season_id, session['league_id'],)
        ).fetchone()
        holes_per_round = int(ls['holes_per_round']) if ls else 9
        multi_course    = bool(ls['multi_course'])   if ls else False
        courses_list = db.execute(
            "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
            (session['league_id'],)
        ).fetchall()
        return render_template('schedule/index.html',
                               season=season, has_schedule=True, view='yearly',
                               yearly_rows=yearly_rows, max_groups=max_groups,
                               weeks_dropdown=weeks_dropdown, teams_list=teams_list,
                               selected_week='all', selected_team=selected_team,
                               team_count=team_count, holes_per_round=holes_per_round,
                               courses_list=courses_list, multi_course=multi_course,
                               commissioner_note='')

    # ---- Weekly detail view ------------------------------------------------
    try:
        week_num = int(selected_week)
    except (ValueError, TypeError):
        week_num = weeks_dropdown[-1][0]
    week_matchups = [m for m in matchups if m['week_number'] == week_num]
    week_date = seen_weeks.get(week_num)

    if selected_team:
        try:
            tid = int(selected_team)
        except (ValueError, TypeError):
            tid = None
        if tid is not None:
            week_matchups = [
                m for m in week_matchups
                if m['team1_id'] == tid or m['team2_id'] == tid or m['bye_team_id'] == tid
            ]

    weekly_rows = _build_weekly_rows(week_matchups, team_info, team_num_map)

    ls_weekly = db.execute(
        "SELECT multi_course FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    multi_course = bool(ls_weekly['multi_course']) if ls_weekly else False

    # Load commissioner note for this week (graceful if table absent)
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

    return render_template('schedule/index.html',
                           season=season, has_schedule=True, view='weekly',
                           weekly_rows=weekly_rows, week_date=week_date,
                           week_num=week_num,
                           weeks_dropdown=weeks_dropdown, teams_list=teams_list,
                           selected_week=selected_week, selected_team=selected_team,
                           team_count=team_count, multi_course=multi_course,
                           commissioner_note=commissioner_note)


@bp.route('/<int:season_id>/generate', methods=['GET', 'POST'])
@admin_required
def generate(season_id):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    existing = db.execute(
        "SELECT COUNT(*) as cnt FROM matchups WHERE season_id = %s", (season_id,)
    ).fetchone()['cnt']
    if existing:
        flash('A schedule already exists. Clear it first to regenerate.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.last_name AS p1_last, p2.last_name AS p2_last
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s""",
        (season_id, session['league_id'])
    ).fetchall()

    if len(teams) < 2:
        flash('You need at least 2 teams to generate a schedule.', 'error')
        return redirect(url_for('seasons.detail', season_id=season_id))

    if request.method == 'POST':
        start_date_str = request.form.get('start_date', '').strip()
        last_week_date_str = request.form.get('last_week_date', '').strip()
        try:
            days_between = int(request.form.get('days_between', 7))
        except (ValueError, TypeError):
            days_between = 7
        start_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid start date.', 'error')
                return render_template('schedule/generate.html', season=season, teams=teams,
                                       start_date=start_date_str, days_between=days_between)

        auto_course_id, auto_tee_id = _get_single_course(db, season_id, session['league_id'])
        rounds = generate_round_robin([dict(t) for t in teams])

        # Default: one full round-robin (each team plays every other team once).
        # If a last-week date is given, extend (or shrink) the season to fit —
        # repeating the round-robin pairings cyclically once the unique
        # match-ups run out, so a longer season naturally becomes a double
        # (or more) round-robin instead of stopping short.
        weeks_needed = len(rounds)
        if last_week_date_str:
            if not start_date:
                flash('A season start date is required to schedule through a specific last-week date.', 'error')
                return render_template('schedule/generate.html', season=season, teams=teams,
                                       start_date=start_date_str, days_between=days_between,
                                       last_week_date=last_week_date_str)
            try:
                last_week_date = datetime.strptime(last_week_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Invalid last week date.', 'error')
                return render_template('schedule/generate.html', season=season, teams=teams,
                                       start_date=start_date_str, days_between=days_between,
                                       last_week_date=last_week_date_str)
            if last_week_date < start_date:
                flash('Last week date must be on or after the start date.', 'error')
                return render_template('schedule/generate.html', season=season, teams=teams,
                                       start_date=start_date_str, days_between=days_between,
                                       last_week_date=last_week_date_str)
            days_span = (last_week_date - start_date).days
            weeks_needed = max(1, days_span // days_between + 1)

        # Shotgun Start: assign a physical slot to each pairing and pull its
        # tee_time/starting_hole from the season's template, if one exists.
        # Only resolvable here for single-course leagues (auto_tee_id known
        # up front) -- multi-course leagues set course/tee per-week later,
        # so their slots get numbered but not time/hole-populated until a
        # "Reapply Defaults" pass after course/tee is set.
        shotgun_on = _shotgun_enabled(db, season_id, session['league_id'])
        shotgun_template = _shotgun_template_by_slot(db, season_id) if shotgun_on else {}
        shotgun_nine = _tee_nine(db, auto_tee_id) if shotgun_on else None

        for week_num in range(1, weeks_needed + 1):
            pairs = rounds[(week_num - 1) % len(rounds)]
            week_date = None
            if start_date:
                week_date = (start_date + timedelta(days=days_between * (week_num - 1))).strftime('%Y-%m-%d')
            slot_number = 0
            for t1, t2 in pairs:
                is_bye   = t1 is None or t2 is None
                bye_team = t2 if t1 is None else (t1 if t2 is None else None)
                slot_number += 1
                slot_tee_time = slot_starting_hole = None
                if shotgun_on:
                    tmpl_row = shotgun_template.get(slot_number)
                    slot_tee_time = tmpl_row['tee_time'] if tmpl_row else None
                    slot_starting_hole = _shotgun_hole_for_nine(tmpl_row, shotgun_nine)
                db.execute(
                    """INSERT INTO matchups
                       (season_id, round_number, week_number, scheduled_date,
                        team1_id, team2_id, is_bye, bye_team_id, status,
                        course_id, tee_id, slot_number, tee_time, starting_hole)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s)""",
                    (season_id, week_num, week_num, week_date,
                     t1['team_id'] if t1 else None,
                     t2['team_id'] if t2 else None,
                     1 if is_bye else 0,
                     bye_team['team_id'] if bye_team else None,
                     auto_course_id, auto_tee_id,
                     slot_number if shotgun_on else None,
                     slot_tee_time,
                     slot_starting_hole if slot_starting_hole else 1)
                )
        db.commit()
        flash('Schedule generated!', 'success')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('schedule/generate.html', season=season, teams=teams,
                           start_date=season['start_date'] or today, days_between=7)


@bp.route('/<int:season_id>/clear', methods=['POST'])
@admin_required
def clear(season_id):
    db = get_db()

    from routes.archive import block_if_locked
    blocked = block_if_locked(db, season_id, session['league_id'],
                               'schedule.index', season_id=season_id, week='all')
    if blocked:
        return blocked

    completed = db.execute(
        "SELECT COUNT(*) as cnt FROM matchups WHERE season_id = %s AND status = 'completed'",
        (season_id,)
    ).fetchone()['cnt']
    if completed:
        flash(f'Cannot clear — {completed} matchup(s) are already completed.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))
    db.execute("DELETE FROM matchups WHERE season_id = %s", (season_id,))
    db.commit()
    flash('Schedule cleared.', 'success')
    return redirect(url_for('schedule.index', season_id=season_id, week='all'))


@bp.route('/<int:season_id>/add-week', methods=['POST'])
@admin_required
def add_week(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    week_type  = request.form.get('week_type', 'play')
    date_str   = request.form.get('scheduled_date', '').strip() or None

    _nw_row = db.execute(
        "SELECT COALESCE(MAX(week_number), 0) + 1 AS nw FROM matchups WHERE season_id = %s",
        (season_id,)
    ).fetchone()
    next_week = (_nw_row['nw'] or 1) if _nw_row else 1

    auto_course_id, auto_tee_id = _get_single_course(db, season_id, league_id)

    if week_type == 'bye':
        db.execute(
            """INSERT INTO matchups
               (season_id, round_number, week_number, scheduled_date,
                team1_id, team2_id, is_bye, bye_team_id, status, week_type,
                course_id, tee_id)
               VALUES (%s, %s, %s, %s, NULL, NULL, 1, NULL, 'scheduled', 'League Bye', %s, %s)""",
            (season_id, next_week, next_week, date_str, auto_course_id, auto_tee_id)
        )
        db.commit()
        flash(f'League bye week {next_week} added.', 'success')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    # Play week — greedy min-played-together pairing
    teams = db.execute(
        "SELECT team_id FROM teams WHERE season_id = %s AND league_id = %s ORDER BY team_id",
        (season_id, league_id)
    ).fetchall()

    if len(teams) < 2:
        flash('Need at least 2 teams to add a play week.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    # Count how many times each pair has played
    history = db.execute(
        """SELECT team1_id, team2_id FROM matchups
           WHERE season_id = %s AND is_bye = 0 AND team1_id IS NOT NULL AND team2_id IS NOT NULL""",
        (season_id,)
    ).fetchall()
    pair_counts = {}
    for m in history:
        key = tuple(sorted([m['team1_id'], m['team2_id']]))
        pair_counts[key] = pair_counts.get(key, 0) + 1

    from itertools import combinations
    team_ids = [t['team_id'] for t in teams]
    random.shuffle(team_ids)
    all_pairs = sorted(combinations(team_ids, 2), key=lambda p: pair_counts.get(tuple(sorted(p)), 0))

    used = set()
    pairs = []
    for t1, t2 in all_pairs:
        if t1 not in used and t2 not in used:
            pairs.append((t1, t2))
            used.add(t1)
            used.add(t2)
    for t in team_ids:
        if t not in used:
            pairs.append((None, t))  # team bye

    shotgun_on = _shotgun_enabled(db, season_id, league_id)
    shotgun_template = _shotgun_template_by_slot(db, season_id) if shotgun_on else {}
    shotgun_nine = _tee_nine(db, auto_tee_id) if shotgun_on else None
    slot_number = 0
    for t1_id, t2_id in pairs:
        slot_number += 1
        slot_tee_time = slot_starting_hole = None
        if shotgun_on:
            tmpl_row = shotgun_template.get(slot_number)
            slot_tee_time = tmpl_row['tee_time'] if tmpl_row else None
            slot_starting_hole = _shotgun_hole_for_nine(tmpl_row, shotgun_nine)
        db.execute(
            """INSERT INTO matchups
               (season_id, round_number, week_number, scheduled_date,
                team1_id, team2_id, is_bye, bye_team_id, status,
                course_id, tee_id, slot_number, tee_time, starting_hole)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s)""",
            (season_id, next_week, next_week, date_str,
             t1_id, t2_id,
             1 if t1_id is None else 0,
             t2_id if t1_id is None else None,
             auto_course_id, auto_tee_id,
             slot_number if shotgun_on else None,
             slot_tee_time,
             slot_starting_hole if slot_starting_hole else 1)
        )
    db.commit()
    play_count = len([p for p in pairs if p[0] is not None])
    flash(f'Week {next_week} added with {play_count} matchup{"s" if play_count != 1 else ""}.', 'success')
    return redirect(url_for('schedule.index', season_id=season_id, week='all'))


# ---------------------------------------------------------------------------
# Open Schedule -- member-created matches (see 10.02 Open Schedule setting)
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/add-match', methods=['GET', 'POST'])
@login_required
def add_match(season_id):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # Server-side gate -- do not rely on the UI hiding the link (see
    # self_report.py's submit(), which only checks self_reporting_enabled in
    # the template, not the route -- a gap this feature must not repeat).
    if not _open_schedule_enabled(db, season_id, league_id):
        flash('Open Schedule is not turned on for this season.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id))

    player_id = session.get('player_id')
    if not player_id:
        flash('Your account is not linked to a player. Ask your admin to link your account.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id))

    my_team = db.execute(
        """SELECT team_id, player1_id, player2_id FROM teams
           WHERE season_id = %s AND league_id = %s AND (player1_id = %s OR player2_id = %s)""",
        (season_id, league_id, player_id, player_id)
    ).fetchone()
    if not my_team:
        flash("You're not on a team for this season.", 'error')
        return redirect(url_for('schedule.index', season_id=season_id))

    my_team_size = 2 if my_team['player2_id'] else 1

    team_info, team_num_map, teams_list = _build_team_info(db, season_id, league_id)
    # Opponent options: exclude own team, and exclude any team whose player
    # count doesn't match ours -- a solo (1-player) team playing a full
    # 2-player team hits a real pre-existing scoring bug in scores.py's
    # _recalc_single_round() (a dict-key collision silently drops one of the
    # solo player's two point pairings). Solo-vs-solo and pair-vs-pair both
    # compute correctly, so this is the guardrail, not a new limitation.
    opponents = [
        t for t in teams_list
        if t['team_id'] != my_team['team_id']
        and (2 if t['p2_id'] else 1) == my_team_size
    ]

    auto_course_id, auto_tee_id = _get_single_course(db, season_id, league_id)

    if request.method == 'POST':
        opponent_id_raw = request.form.get('opponent_team_id', '').strip()
        scheduled_date  = request.form.get('scheduled_date', '').strip() or None
        opponent_id     = int(opponent_id_raw) if opponent_id_raw.isdigit() else None
        valid_opponent_ids = {t['team_id'] for t in opponents}

        if opponent_id not in valid_opponent_ids:
            flash('Pick a valid opponent.', 'error')
            return redirect(url_for('schedule.add_match', season_id=season_id))
        if not scheduled_date:
            flash('Pick a date.', 'error')
            return redirect(url_for('schedule.add_match', season_id=season_id))

        if auto_course_id:
            course_id_val, tee_id_val = auto_course_id, auto_tee_id
        else:
            course_id_raw = request.form.get('course_id', '').strip()
            tee_id_raw    = request.form.get('tee_id', '').strip()
            course_id_val = int(course_id_raw) if course_id_raw else None
            tee_id_val    = int(tee_id_raw)    if tee_id_raw    else None

        _nw_row = db.execute(
            "SELECT COALESCE(MAX(week_number), 0) + 1 AS nw FROM matchups WHERE season_id = %s",
            (season_id,)
        ).fetchone()
        next_week = (_nw_row['nw'] or 1) if _nw_row else 1

        db.execute(
            """INSERT INTO matchups
               (season_id, round_number, week_number, scheduled_date,
                team1_id, team2_id, is_bye, status, course_id, tee_id)
               VALUES (%s, %s, %s, %s, %s, %s, 0, 'scheduled', %s, %s)""",
            (season_id, next_week, next_week, scheduled_date,
             my_team['team_id'], opponent_id, course_id_val, tee_id_val)
        )
        db.commit()
        flash('Match added.', 'success')
        return redirect(url_for('schedule.index', season_id=season_id))

    # GET -- render the form. Course/tee pickers only needed for multi-course leagues.
    courses = []
    tees = []
    preview_course_id = ''
    if not auto_course_id:
        courses = db.execute(
            "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
            (league_id,)
        ).fetchall()
        preview_course_id = request.args.get('course_id', '')
        if preview_course_id:
            tees = db.execute(
                """SELECT tee_id, tee_name, nine, gender
                   FROM tees WHERE course_id = %s ORDER BY gender, nine, tee_name""",
                (int(preview_course_id),)
            ).fetchall()

    return render_template('schedule/add_match.html',
                           season=season, opponents=opponents,
                           my_team_size=my_team_size,
                           courses=courses, tees=tees,
                           preview_course_id=preview_course_id,
                           single_course=bool(auto_course_id))


@bp.route('/<int:season_id>/bulk-edit', methods=['POST'])
@admin_required
def bulk_edit(season_id):
    """Save inline schedule edits from the yearly overview edit-mode form."""
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # For single-course leagues, backfill course/tee on any matchup that's missing them
    auto_course_id, auto_tee_id = _get_single_course(db, season_id, league_id)
    if auto_course_id:
        db.execute(
            "UPDATE matchups SET course_id = %s, tee_id = COALESCE(tee_id, %s)"
            " WHERE season_id = %s AND course_id IS NULL",
            (auto_course_id, auto_tee_id, season_id)
        )

    # Any Front/Back side swap below also needs to remap already-scored
    # rounds (see remap_week_to_tee's docstring) -- a plain matchups.tee_id
    # update alone silently has zero effect on in-progress/completed
    # scorecards, since scoring reads rounds.tee_id, not matchups.tee_id.
    from routes.scores import remap_week_to_tee
    from routes.archive import season_is_locked
    season_locked = season_is_locked(db, season_id, league_id)
    side_remap_total = 0
    side_remap_warnings = []

    # Process course_ keys first so side_ lookups can use the just-saved course_id
    ordered_keys = sorted(request.form.keys(), key=lambda k: (0 if k.startswith('course_') else 1))
    for key in ordered_keys:
        val = (request.form[key] or '').strip() or None
        if key.startswith('date_'):
            week_num = int(key[5:])
            # Date is week-level metadata — update all matchups in the week
            db.execute(
                "UPDATE matchups SET scheduled_date = %s"
                " WHERE season_id = %s AND week_number = %s",
                (val, season_id, week_num)
            )
        elif key.startswith('t1_'):
            matchup_id = int(key[3:])
            # Team changes only allowed for non-completed matchups
            db.execute(
                "UPDATE matchups SET team1_id = %s"
                " WHERE matchup_id = %s AND season_id = %s AND status != 'completed'",
                (int(val) if val else None, matchup_id, season_id)
            )
        elif key.startswith('t2_'):
            matchup_id = int(key[3:])
            db.execute(
                "UPDATE matchups SET team2_id = %s"
                " WHERE matchup_id = %s AND season_id = %s AND status != 'completed'",
                (int(val) if val else None, matchup_id, season_id)
            )
        elif key.startswith('bye_'):
            matchup_id = int(key[4:])
            db.execute(
                "UPDATE matchups SET bye_team_id = %s"
                " WHERE matchup_id = %s AND season_id = %s AND status != 'completed'",
                (int(val) if val else None, matchup_id, season_id)
            )
        elif key.startswith('side_'):
            week_num = int(key[5:])
            desired_nine = (val or '').lower()
            if desired_nine in ('front', 'back'):
                current = db.execute(
                    """SELECT te.tee_id, te.course_id, te.tee_name, te.tee_color
                       FROM matchups m
                       JOIN tees te ON m.tee_id = te.tee_id
                       WHERE m.season_id = %s AND m.week_number = %s
                         AND m.tee_id IS NOT NULL
                       LIMIT 1""",
                    (season_id, week_num)
                ).fetchone()
                if current:
                    # Week already has a tee — find same color/name on desired nine
                    new_tee = db.execute(
                        """SELECT tee_id FROM tees
                           WHERE course_id = %s AND nine = %s
                             AND (tee_color = %s OR tee_name = %s)
                           LIMIT 1""",
                        (current['course_id'], desired_nine,
                         current['tee_color'] or current['tee_name'],
                         current['tee_color'] or current['tee_name'])
                    ).fetchone()
                    if not new_tee:
                        # Fallback: any tee on that nine for the course
                        new_tee = db.execute(
                            "SELECT tee_id FROM tees WHERE course_id = %s AND nine = %s LIMIT 1",
                            (current['course_id'], desired_nine)
                        ).fetchone()
                    if new_tee:
                        db.execute(
                            "UPDATE matchups SET tee_id = %s"
                            " WHERE season_id = %s AND week_number = %s",
                            (new_tee['tee_id'], season_id, week_num)
                        )
                        if season_locked:
                            side_remap_warnings.append(
                                f'Week {week_num}: season is locked — already-scored groups were not remapped.')
                        else:
                            remapped, warns = remap_week_to_tee(db, season_id, week_num, league_id, new_tee['tee_id'])
                            side_remap_total += remapped
                            side_remap_warnings.extend(warns)
                else:
                    # Week has no tee yet — look up by course_id on the matchup
                    course_row = db.execute(
                        """SELECT m.course_id, c.default_tee_id
                           FROM matchups m
                           LEFT JOIN courses c ON c.course_id = m.course_id
                           WHERE m.season_id = %s AND m.week_number = %s
                             AND m.course_id IS NOT NULL
                           LIMIT 1""",
                        (season_id, week_num)
                    ).fetchone()
                    if course_row:
                        course_id = course_row['course_id']
                        # Prefer tee that matches course default's color on desired nine
                        new_tee = None
                        if course_row['default_tee_id']:
                            default_meta = db.execute(
                                "SELECT tee_color, tee_name FROM tees WHERE tee_id = %s",
                                (course_row['default_tee_id'],)
                            ).fetchone()
                            if default_meta:
                                color = default_meta['tee_color'] or default_meta['tee_name']
                                new_tee = db.execute(
                                    """SELECT tee_id FROM tees
                                       WHERE course_id = %s AND nine = %s
                                         AND (tee_color = %s OR tee_name = %s)
                                       LIMIT 1""",
                                    (course_id, desired_nine, color, color)
                                ).fetchone()
                        if not new_tee:
                            # Fallback: any tee on that nine for the course
                            new_tee = db.execute(
                                "SELECT tee_id FROM tees WHERE course_id = %s AND nine = %s LIMIT 1",
                                (course_id, desired_nine)
                            ).fetchone()
                        if new_tee:
                            db.execute(
                                "UPDATE matchups SET tee_id = %s"
                                " WHERE season_id = %s AND week_number = %s",
                                (new_tee['tee_id'], season_id, week_num)
                            )
                            if season_locked:
                                side_remap_warnings.append(
                                    f'Week {week_num}: season is locked — already-scored groups were not remapped.')
                            else:
                                remapped, warns = remap_week_to_tee(db, season_id, week_num, league_id, new_tee['tee_id'])
                                side_remap_total += remapped
                                side_remap_warnings.extend(warns)
        elif key.startswith('course_') and key[7:].isdigit():
            week_num = int(key[7:])
            course_id_val = int(val) if val else None
            db.execute(
                "UPDATE matchups SET course_id = %s"
                " WHERE season_id = %s AND week_number = %s",
                (course_id_val, season_id, week_num)
            )
        elif key.startswith('type_') and key[5:].isdigit():
            week_num = int(key[5:])
            db.execute(
                "UPDATE matchups SET week_type = %s"
                " WHERE season_id = %s AND week_number = %s",
                (val or 'Normal', season_id, week_num)
            )

    db.commit()
    for w in side_remap_warnings:
        flash(w, 'warning')
    if side_remap_total:
        flash(f'Schedule saved — {side_remap_total} already-scored group(s) remapped to the new side, results recalculated.', 'success')
    else:
        flash('Schedule saved.', 'success')
    return redirect(url_for('schedule.index', season_id=season_id, week='all'))


@bp.route('/<int:season_id>/week/<int:week_num>/mark-rain-out', methods=['POST'])
@admin_required
def mark_rain_out(season_id, week_num):
    """Mark all matchups in a week as Rain Out."""
    db = get_db()
    league_id = session['league_id']
    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    completed = db.execute(
        "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id=%s AND week_number=%s AND status='completed'",
        (season_id, week_num)
    ).fetchone()['cnt']
    if completed:
        flash(f'Week {week_num} has completed scores — cannot mark as Rain Out.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    db.execute(
        "UPDATE matchups SET week_type='Rain Out' WHERE season_id=%s AND week_number=%s",
        (season_id, week_num)
    )
    db.commit()
    from flask import jsonify
    return jsonify({'ok': True})


@bp.route('/<int:season_id>/week/<int:week_num>/undo-rain-out', methods=['POST'])
@admin_required
def undo_rain_out(season_id, week_num):
    """Revert a Rain Out week back to Normal."""
    db = get_db()
    league_id = session['league_id']
    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        from flask import jsonify
        return jsonify({'ok': False, 'error': 'Season not found.'})

    db.execute(
        "UPDATE matchups SET week_type='Normal' WHERE season_id=%s AND week_number=%s AND week_type='Rain Out'",
        (season_id, week_num)
    )
    db.commit()
    from flask import jsonify
    return jsonify({'ok': True})


@bp.route('/<int:season_id>/week/<int:week_num>/add-matchup', methods=['POST'])
@admin_required
def add_matchup_to_week(season_id, week_num):
    """Add one more blank matchup slot to an existing week (e.g. a manually-built
    playoff week that started with fewer matchup rows than teams need)."""
    db = get_db()
    league_id = session['league_id']
    from flask import jsonify

    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        return jsonify({'ok': False, 'error': 'Season not found.'})

    existing = db.execute(
        """SELECT scheduled_date, week_type, course_id, tee_id
           FROM matchups WHERE season_id = %s AND week_number = %s LIMIT 1""",
        (season_id, week_num)
    ).fetchone()
    if not existing:
        return jsonify({'ok': False, 'error': 'Week not found.'})

    # An odd team count means every full round has one team with a bye each
    # week. If this new slot will complete the week to that full count and
    # no bye slot exists yet, add it as the bye instead of a blank matchup --
    # otherwise a manually-populated week (e.g. a hand-built playoff bracket)
    # ends up with one too many "real" matchup slots for the team count to
    # ever fill, since one team can never be paired.
    team_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM teams WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()['cnt']

    week_rows = db.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(is_bye), 0) AS byes,"
        " ARRAY_REMOVE(ARRAY_AGG(team1_id), NULL) || ARRAY_REMOVE(ARRAY_AGG(team2_id), NULL) AS used_teams"
        " FROM matchups WHERE season_id = %s AND week_number = %s",
        (season_id, week_num)
    ).fetchone()

    is_bye_slot = False
    bye_team_id = None
    if team_count % 2 == 1:
        full_week_size = (team_count + 1) // 2
        if not week_rows['byes'] and week_rows['total'] + 1 == full_week_size:
            is_bye_slot = True
            used_teams = set(week_rows['used_teams'] or [])
            remaining = db.execute(
                "SELECT team_id FROM teams WHERE season_id = %s AND league_id = %s"
                " ORDER BY team_id",
                (season_id, league_id)
            ).fetchall()
            unused = [t['team_id'] for t in remaining if t['team_id'] not in used_teams]
            bye_team_id = unused[0] if unused else (remaining[0]['team_id'] if remaining else None)

    db.execute(
        """INSERT INTO matchups
           (season_id, round_number, week_number, scheduled_date,
            team1_id, team2_id, is_bye, bye_team_id, status, week_type,
            course_id, tee_id)
           VALUES (%s, %s, %s, %s, NULL, NULL, %s, %s, 'scheduled', %s, %s, %s)""",
        (season_id, week_num, week_num, existing['scheduled_date'],
         1 if is_bye_slot else 0, bye_team_id,
         existing['week_type'] or 'Normal', existing['course_id'], existing['tee_id'])
    )
    db.commit()
    return jsonify({'ok': True})


@bp.route('/<int:season_id>/rain-outs')
@admin_required
def rain_outs(season_id):
    """Manage Rain Outs page."""
    db = get_db()
    league_id = session['league_id']
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    from_week = request.args.get('from_week', type=int)

    # Rain out weeks with their pairings
    rain_out_matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.week_label,
                  m.team1_id, m.team2_id, m.is_bye, m.bye_team_id,
                  m.course_id, m.tee_id,
                  t1.team_name AS t1_name, t2.team_name AS t2_name
           FROM matchups m
           LEFT JOIN teams t1 ON t1.team_id = m.team1_id
           LEFT JOIN teams t2 ON t2.team_id = m.team2_id
           WHERE m.season_id=%s AND m.week_type='Rain Out'
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()

    # Group rain outs by week
    ro_by_week = {}
    for m in rain_out_matchups:
        w = m['week_number']
        if w not in ro_by_week:
            ro_by_week[w] = {'week_number': w, 'date': m['scheduled_date'],
                             'week_label': m['week_label'], 'matchups': []}
        ro_by_week[w]['matchups'].append(dict(m))
    rain_out_weeks = list(ro_by_week.values())

    # Future unplayed weeks (eligible to be overwritten)
    target_weeks_raw = db.execute(
        """SELECT m.week_number, m.scheduled_date, m.week_label,
                  COUNT(*) AS matchup_count
           FROM matchups m
           WHERE m.season_id=%s AND m.week_type NOT IN ('Rain Out','League Bye')
             AND m.status != 'completed'
           GROUP BY m.week_number, m.scheduled_date, m.week_label
           ORDER BY m.week_number""",
        (season_id,)
    ).fetchall()
    target_weeks = [dict(t) for t in target_weeks_raw]

    # Team info for display
    team_info, _, teams_list = _build_team_info(db, season_id, league_id)

    # All scheduled dates for week-label calculation
    week_dates = db.execute(
        """SELECT week_number, MIN(scheduled_date) AS d
           FROM matchups WHERE season_id=%s AND scheduled_date IS NOT NULL
           GROUP BY week_number ORDER BY week_number""",
        (season_id,)
    ).fetchall()
    week_date_map = {r['week_number']: r['d'] for r in week_dates}

    return render_template('schedule/rain_outs.html',
                           season=season,
                           rain_out_weeks=rain_out_weeks,
                           target_weeks=target_weeks,
                           team_info=team_info,
                           teams_list=teams_list,
                           from_week=from_week,
                           week_date_map=week_date_map)


@bp.route('/<int:season_id>/rain-outs/reschedule', methods=['POST'])
@admin_required
def reschedule_rain_out(season_id):
    """Create a makeup week from a rain out week."""
    db = get_db()
    league_id = session['league_id']
    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id=%s AND league_id=%s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    source_week   = request.form.get('source_week', type=int)
    action        = request.form.get('action')          # 'overwrite' or 'new_week'
    target_week   = request.form.get('target_week', type=int)
    makeup_date   = request.form.get('makeup_date', '').strip() or None

    if not source_week:
        flash('No source rain out week selected.', 'error')
        return redirect(url_for('schedule.rain_outs', season_id=season_id))

    # Fetch source matchups
    source_matchups = db.execute(
        """SELECT * FROM matchups WHERE season_id=%s AND week_number=%s""",
        (season_id, source_week)
    ).fetchall()
    if not source_matchups:
        flash('Rain out week not found.', 'error')
        return redirect(url_for('schedule.rain_outs', season_id=season_id))

    auto_course_id, auto_tee_id = _get_single_course(db, season_id, league_id)
    course_id = source_matchups[0]['course_id'] or auto_course_id
    tee_id    = source_matchups[0]['tee_id']    or auto_tee_id

    if action == 'overwrite':
        if not target_week:
            flash('No target week selected.', 'error')
            return redirect(url_for('schedule.rain_outs', season_id=season_id))

        # Safety check — no completed scores in target
        completed = db.execute(
            "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id=%s AND week_number=%s AND status='completed'",
            (season_id, target_week)
        ).fetchone()['cnt']
        if completed:
            flash(f'Week {target_week} has completed scores — cannot overwrite.', 'error')
            return redirect(url_for('schedule.rain_outs', season_id=season_id))

        # Get target date before deleting
        target_date_row = db.execute(
            "SELECT MIN(scheduled_date) AS d FROM matchups WHERE season_id=%s AND week_number=%s",
            (season_id, target_week)
        ).fetchone()
        target_date = makeup_date or (target_date_row['d'] if target_date_row else None)

        db.execute("DELETE FROM matchups WHERE season_id=%s AND week_number=%s", (season_id, target_week))

        for m in source_matchups:
            db.execute(
                """INSERT INTO matchups
                   (season_id, round_number, week_number, scheduled_date,
                    team1_id, team2_id, is_bye, bye_team_id, status,
                    course_id, tee_id, week_type, makeup_for_week)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',%s,%s,'Makeup',%s)""",
                (season_id, target_week, target_week, target_date,
                 m['team1_id'], m['team2_id'], m['is_bye'], m['bye_team_id'],
                 course_id, tee_id, source_week)
            )
        db.commit()
        flash(f'Week {source_week} rescheduled into Week {target_week} as a Makeup.', 'success')

    elif action == 'new_week':
        if not makeup_date:
            flash('A date is required to add a new makeup week.', 'error')
            return redirect(url_for('schedule.rain_outs', season_id=season_id))

        # Calculate week_label: find the last week whose date <= makeup_date
        week_dates = db.execute(
            """SELECT week_number, MIN(scheduled_date) AS d
               FROM matchups WHERE season_id=%s AND scheduled_date IS NOT NULL
               GROUP BY week_number ORDER BY week_number""",
            (season_id,)
        ).fetchall()

        prev_week = None
        for wd in week_dates:
            if wd['d'] and wd['d'] <= makeup_date:
                prev_week = wd['week_number']

        if prev_week is None:
            # Before all weeks — label as 0.1
            base_label = '0'
        else:
            # Check if a label like "4.1" already exists
            existing_label = db.execute(
                "SELECT week_label FROM matchups WHERE season_id=%s AND week_label LIKE %s LIMIT 1",
                (season_id, f'{prev_week}.%')
            ).fetchone()
            if existing_label and existing_label['week_label']:
                try:
                    sub = int(existing_label['week_label'].split('.')[1]) + 1
                except (IndexError, ValueError):
                    sub = 1
            else:
                sub = 1
            base_label = str(prev_week)

        week_label = f'{base_label}.{sub if prev_week is not None else 1}'

        # New week_number = MAX + 1 (internal ordering; display uses week_label)
        max_week = db.execute(
            "SELECT COALESCE(MAX(week_number),0) AS m FROM matchups WHERE season_id=%s",
            (season_id,)
        ).fetchone()['m']
        new_week_num = max_week + 1

        for m in source_matchups:
            db.execute(
                """INSERT INTO matchups
                   (season_id, round_number, week_number, scheduled_date,
                    team1_id, team2_id, is_bye, bye_team_id, status,
                    course_id, tee_id, week_type, makeup_for_week, week_label)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',%s,%s,'Makeup',%s,%s)""",
                (season_id, new_week_num, new_week_num, makeup_date,
                 m['team1_id'], m['team2_id'], m['is_bye'], m['bye_team_id'],
                 course_id, tee_id, source_week, week_label)
            )
        db.commit()
        flash(f'Makeup week {week_label} added for Week {source_week}.', 'success')

    else:
        flash('Invalid action.', 'error')

    return redirect(url_for('schedule.index', season_id=season_id, week='all'))


@bp.route('/<int:season_id>/week/<int:week_num>/remove', methods=['POST'])
@admin_required
def remove_week(season_id, week_num):
    db = get_db()
    league_id = session['league_id']

    # Verify season belongs to this league
    season = db.execute(
        "SELECT season_id FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    completed = db.execute(
        "SELECT COUNT(*) AS cnt FROM matchups WHERE season_id = %s AND week_number = %s AND status = 'completed'",
        (season_id, week_num)
    ).fetchone()['cnt']
    if completed:
        flash(f'Cannot remove — {completed} matchup(s) in Week {week_num} are already completed.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    db.execute(
        "DELETE FROM matchups WHERE season_id = %s AND week_number = %s",
        (season_id, week_num)
    )

    # Renumber remaining weeks so they stay consecutive (1, 2, 3, …)
    remaining = db.execute(
        """SELECT DISTINCT week_number FROM matchups
           WHERE season_id = %s ORDER BY week_number ASC""",
        (season_id,)
    ).fetchall()
    for new_num, row in enumerate(remaining, start=1):
        old_num = row['week_number']
        if old_num != new_num:
            db.execute(
                "UPDATE matchups SET week_number = %s WHERE season_id = %s AND week_number = %s",
                (new_num, season_id, old_num)
            )
            # Keep week_notes in sync if that table exists
            try:
                db.execute(
                    "UPDATE week_notes SET week_number = %s WHERE season_id = %s AND week_number = %s",
                    (new_num, season_id, old_num)
                )
            except Exception:
                pass

    db.commit()
    flash(f'Week {week_num} removed and weeks renumbered.', 'success')
    return redirect(url_for('schedule.index', season_id=season_id, week='all'))


@bp.route('/<int:season_id>/tee-time-template', methods=['GET', 'POST'])
@admin_required
def tee_time_template(season_id):
    """Manage the season's shotgun-start slot template -- see
    Plans/2026-08-13-shotgun-tee-time-technical-spec.md."""
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    if not _shotgun_enabled(db, season_id, league_id):
        flash('Turn on Shotgun Start in League Settings first.', 'error')
        return redirect(url_for('admin.settings', season_id=season_id))

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'sync':
            _sync_shotgun_slot_count(db, season_id, league_id)
            db.commit()
            flash('Slot count synced to current team count.', 'success')
            return redirect(url_for('schedule.tee_time_template', season_id=season_id))

        if action == 'add_shared':
            base_slot = request.form.get('shared_base_slot', '').strip()
            label = request.form.get('shared_label', '').strip().upper()
            if base_slot.isdigit() and label:
                db.execute(
                    "INSERT INTO shotgun_slot_templates (season_id, slot_number, slot_label) VALUES (%s, %s, %s)"
                    " ON CONFLICT (season_id, slot_number, slot_label) DO NOTHING",
                    (season_id, int(base_slot), label)
                )
                db.commit()
                flash(f'Added shared-hole group {base_slot}{label}.', 'success')
            else:
                flash('Pick a slot number and a label for the shared-hole group.', 'error')
            return redirect(url_for('schedule.tee_time_template', season_id=season_id))

        if action == 'reapply':
            template = _shotgun_template_by_slot(db, season_id)
            weeks = db.execute(
                """SELECT DISTINCT m.week_number, m.tee_id FROM matchups m
                   WHERE m.season_id = %s AND m.is_bye = 0
                     AND m.status != 'completed' AND m.slot_number IS NOT NULL""",
                (season_id,)
            ).fetchall()
            updated = 0
            for w in weeks:
                nine = _tee_nine(db, w['tee_id'])
                matchups = db.execute(
                    "SELECT matchup_id, slot_number FROM matchups"
                    " WHERE season_id = %s AND week_number = %s AND is_bye = 0 AND status != 'completed'",
                    (season_id, w['week_number'])
                ).fetchall()
                for m in matchups:
                    tmpl_row = template.get(m['slot_number'])
                    if not tmpl_row:
                        continue
                    hole = _shotgun_hole_for_nine(tmpl_row, nine)
                    db.execute(
                        "UPDATE matchups SET tee_time = %s, starting_hole = %s WHERE matchup_id = %s",
                        (tmpl_row['tee_time'], hole if hole else 1, m['matchup_id'])
                    )
                    updated += 1
            db.commit()
            flash(f'Reapplied defaults to {updated} not-yet-completed matchup(s).', 'success')
            return redirect(url_for('schedule.tee_time_template', season_id=season_id))

        # action == 'save' -- update every existing row's time/holes from the form
        rows = db.execute(
            "SELECT template_id FROM shotgun_slot_templates WHERE season_id = %s", (season_id,)
        ).fetchall()
        for r in rows:
            tid = r['template_id']
            tt = request.form.get(f'time_{tid}', '').strip() or None
            fh_raw = request.form.get(f'front_{tid}', '').strip()
            bh_raw = request.form.get(f'back_{tid}', '').strip()
            fh = int(fh_raw) if fh_raw.isdigit() else None
            bh = int(bh_raw) if bh_raw.isdigit() else None
            db.execute(
                "UPDATE shotgun_slot_templates SET tee_time = %s, front_nine_hole = %s, back_nine_hole = %s"
                " WHERE template_id = %s",
                (tt, fh, bh, tid)
            )
        db.commit()
        flash('Tee time template saved.', 'success')
        return redirect(url_for('schedule.tee_time_template', season_id=season_id))

    # Self-heal: ensure rows exist even if the settings-page auto-seed was
    # somehow skipped (e.g. shotgun turned on before this route existed).
    _sync_shotgun_slot_count(db, season_id, league_id)
    db.commit()

    slots = db.execute(
        "SELECT * FROM shotgun_slot_templates WHERE season_id = %s ORDER BY slot_number, slot_label NULLS FIRST",
        (season_id,)
    ).fetchall()
    base_slot_count = _shotgun_slots_needed(db, season_id, league_id)

    return render_template('schedule/tee_time_template.html', season=season, slots=slots,
                           base_slot_count=base_slot_count)


@bp.route('/matchup/<int:matchup_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_matchup(matchup_id):
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

    if matchup['status'] == 'completed':
        flash('Completed matchups cannot be edited.', 'error')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    if request.method == 'POST':
        scheduled_date = request.form.get('scheduled_date', '').strip() or None
        tee_time       = request.form.get('tee_time',       '').strip() or None
        try:
            starting_hole = int(request.form.get('starting_hole', 1))
        except (ValueError, TypeError):
            starting_hole = 1
        week_type      = request.form.get('week_type',      'Normal').strip() or 'Normal'
        notes          = request.form.get('notes',          '').strip() or None

        course_id_raw  = request.form.get('course_id', '').strip()
        tee_id_raw     = request.form.get('tee_id',    '').strip()
        course_id_val  = int(course_id_raw) if course_id_raw else None
        tee_id_val     = int(tee_id_raw)    if tee_id_raw    else None

        db.execute(
            """UPDATE matchups
               SET scheduled_date = %s, tee_time = %s, starting_hole = %s, notes = %s,
                   course_id = %s, tee_id = %s
               WHERE matchup_id = %s""",
            (scheduled_date, tee_time, starting_hole, notes, course_id_val, tee_id_val, matchup_id)
        )
        # week_type applies to all matchups in this week
        db.execute(
            "UPDATE matchups SET week_type = %s WHERE season_id = %s AND week_number = %s",
            (week_type, matchup['season_id'], matchup['week_number'])
        )
        db.commit()
        flash('Matchup updated.', 'success')
        return redirect(url_for('schedule.index', season_id=matchup['season_id']))

    # Load courses for the Course/Tee pickers
    courses = db.execute(
        "SELECT course_id, course_name FROM courses WHERE league_id = %s OR league_id IS NULL ORDER BY course_name",
        (session['league_id'],)
    ).fetchall()

    # Use ?course_id= query param (from onchange reload) or fall back to matchup's stored course
    preview_course_id = request.args.get('course_id') or matchup['course_id']
    tees = []
    if preview_course_id:
        tees = db.execute(
            """SELECT tee_id, tee_name, nine, gender
               FROM tees WHERE course_id = %s ORDER BY gender, nine, tee_name""",
            (int(preview_course_id),)
        ).fetchall()

    return render_template('schedule/edit_matchup.html',
                           matchup=matchup, courses=courses, tees=tees,
                           preview_course_id=str(preview_course_id or ''))


# ---------------------------------------------------------------------------
# Tee Sheet — printable starting times view
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/week/<int:week_num>/tee-sheet')
@login_required
def tee_sheet(season_id, week_num):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  m.status, m.is_bye, m.bye_team_id, m.week_type,
                  m.tee_time, m.starting_hole,
                  m.team1_id, m.team2_id,
                  c.course_name,
                  te.nine AS side,
                  te.tee_name
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY
               CASE WHEN m.tee_time IS NULL OR m.tee_time = '' THEN 1 ELSE 0 END,
               m.tee_time,
               m.starting_hole,
               m.matchup_id""",
        (season_id, week_num)
    ).fetchall()

    if not matchups:
        flash(f'No matchups found for Week {week_num}.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    team_info, team_num_map, teams_list = _build_team_info(db, season_id, session['league_id'])

    # Build league info for header
    league = db.execute(
        "SELECT league_name FROM leagues WHERE league_id = %s",
        (session['league_id'],)
    ).fetchone()

    week_date     = matchups[0]['scheduled_date'] if matchups else None
    week_type     = matchups[0]['week_type']      if matchups else 'Normal'
    course_name   = next((m['course_name'] for m in matchups if m['course_name']), None)
    side          = next((m['side']        for m in matchups if m['side']),        None)
    tee_name      = next((m['tee_name']    for m in matchups if m['tee_name']),    None)

    # Separate byes from regular matchups
    regular = [m for m in matchups if not m['is_bye']]
    byes    = [m for m in matchups if m['is_bye']]

    has_tee_times  = any(m['tee_time']    for m in regular)
    has_start_hole = any(m['starting_hole'] and m['starting_hole'] != 1 for m in regular)

    rows = []
    for i, m in enumerate(regular, start=1):
        t1 = team_info.get(m['team1_id']) if m['team1_id'] else None
        t2 = team_info.get(m['team2_id']) if m['team2_id'] else None
        rows.append({
            'group':      i,
            'tee_time':   m['tee_time'] or '',
            'hole':       m['starting_hole'] if m['starting_hole'] else 1,
            'team1':      t1,
            'team2':      t2,
            'matchup_id': m['matchup_id'],
            'status':     m['status'],
        })

    bye_teams = []
    for m in byes:
        bt = team_info.get(m['bye_team_id']) if m['bye_team_id'] else None
        if bt:
            bye_teams.append(bt)

    print_date = datetime.now().strftime('%b %d, %Y')
    return render_template(
        'schedule/tee_sheet.html',
        season=season,
        league=league,
        week_num=week_num,
        week_date=week_date,
        week_type=week_type,
        course_name=course_name,
        side=side,
        tee_name=tee_name,
        rows=rows,
        bye_teams=bye_teams,
        has_tee_times=has_tee_times,
        has_start_hole=has_start_hole,
        season_id=season_id,
        print_date=print_date,
    )


# ---------------------------------------------------------------------------
# iCal export — /schedule/<season_id>/ical
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/ical')
@login_required
def ical_export(season_id):
    """Return an .ics file with one VEVENT per scheduled week."""
    from flask import Response
    import uuid

    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    league = db.execute(
        "SELECT league_name FROM leagues WHERE league_id = %s", (league_id,)
    ).fetchone()
    league_name = league['league_name'] if league else 'Golf League'

    matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date,
                  m.tee_time, m.week_type,
                  m.team1_id, m.team2_id, m.bye_team_id,
                  CASE WHEN m.team2_id IS NULL THEN 1 ELSE 0 END AS is_bye,
                  c.course_name,
                  te.nine AS side, te.tee_name
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.season_id = %s
           ORDER BY m.week_number, m.matchup_id""",
        (season_id,)
    ).fetchall()

    team_info, _, _ = _build_team_info(db, season_id, league_id)

    # Group matchups by week
    by_week = {}
    for m in matchups:
        by_week.setdefault(m['week_number'], []).append(m)

    def _ical_dt(date_str, time_str=None, duration_hours=4):
        """Return DTSTART, DTEND strings. If time_str given, use it; else all-day."""
        if not date_str:
            return None, None
        if time_str:
            # time_str may be "7:00 PM", "19:00", "7:30 AM", etc.
            for fmt in ('%I:%M %p', '%H:%M', '%I %p', '%I:%M%p', '%I%p'):
                try:
                    t = datetime.strptime(time_str.strip(), fmt)
                    d = datetime.strptime(date_str.strip(), '%Y-%m-%d')
                    start = d.replace(hour=t.hour, minute=t.minute)
                    end   = start + timedelta(hours=duration_hours)
                    return start.strftime('%Y%m%dT%H%M%S'), end.strftime('%Y%m%dT%H%M%S')
                except ValueError:
                    continue
        # All-day event
        d = datetime.strptime(date_str.strip(), '%Y-%m-%d')
        next_d = d + timedelta(days=1)
        return d.strftime('%Y%m%d'), next_d.strftime('%Y%m%d')

    def _fold(line):
        """RFC 5545 line folding: max 75 octets, continuation lines start with space."""
        result = []
        while len(line.encode('utf-8')) > 75:
            result.append(line[:75])
            line = ' ' + line[75:]
        result.append(line)
        return '\r\n'.join(result)

    # Build calendar lines
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//BetterGolfLeagueTracker//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        f'X-WR-CALNAME:{league_name} — {season["season_name"]}',
        'X-WR-TIMEZONE:America/New_York',
    ]

    for week_num, week_matchups in sorted(by_week.items()):
        non_byes = [m for m in week_matchups if not m['is_bye']]
        if not non_byes:
            continue

        first = non_byes[0]
        date_str  = first['scheduled_date']
        time_str  = next((m['tee_time'] for m in non_byes if m['tee_time']), None)
        course    = next((m['course_name'] for m in non_byes if m['course_name']), None)
        week_type = first['week_type'] or 'Normal'

        if not date_str:
            continue

        dtstart, dtend = _ical_dt(date_str, time_str)
        if not dtstart:
            continue

        all_day = len(dtstart) == 8  # YYYYMMDD = all-day

        summary = f'{league_name} — Week {week_num}'
        if week_type and week_type != 'Normal':
            summary += f' ({week_type})'

        # Build description: list matchups
        desc_parts = []
        if course:
            desc_parts.append(f'Course: {course}')
        if time_str:
            desc_parts.append(f'Tee time: {time_str}')
        for m in non_byes:
            t1 = team_info.get(m['team1_id'])
            t2 = team_info.get(m['team2_id'])
            t1_label = t1['label'] if t1 else '?'
            t2_label = t2['label'] if t2 else '?'
            desc_parts.append(f'{t1_label} vs {t2_label}')
        description = '\\n'.join(desc_parts)

        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f'{league_id}-{season_id}-week{week_num}'))

        now_str = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')

        lines.append('BEGIN:VEVENT')
        lines.append(f'UID:{uid}@betterglf')
        lines.append(f'DTSTAMP:{now_str}')
        if all_day:
            lines.append(f'DTSTART;VALUE=DATE:{dtstart}')
            lines.append(f'DTEND;VALUE=DATE:{dtend}')
        else:
            lines.append(f'DTSTART:{dtstart}')
            lines.append(f'DTEND:{dtend}')
        lines.append(_fold(f'SUMMARY:{summary}'))
        lines.append(_fold(f'DESCRIPTION:{description}'))
        if course:
            lines.append(_fold(f'LOCATION:{course}'))
        lines.append('END:VEVENT')

    lines.append('END:VCALENDAR')

    ics_content = '\r\n'.join(lines) + '\r\n'
    filename = f'golf-league-season{season_id}.ics'

    return Response(
        ics_content,
        mimetype='text/calendar',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'text/calendar; charset=utf-8',
        }
    )


# ---------------------------------------------------------------------------
# Week Summary / Recap
# ---------------------------------------------------------------------------

@bp.route('/week-summary/latest')
@login_required
def week_summary_latest():
    """Redirect to the read-only week-summary page for the most recently
    fully-completed week (every non-bye matchup in it is 'completed') --
    mirrors enter_week_current's self-resolving-redirect pattern so admin
    CTAs can link here without the caller having to know season/week."""
    db = get_db()
    season = db.execute(
        "SELECT season_id FROM seasons WHERE league_id = %s ORDER BY season_id DESC LIMIT 1",
        (session['league_id'],)
    ).fetchone()
    if not season:
        flash('No seasons found.', 'error')
        return redirect(url_for('seasons.index'))
    season_id = season['season_id']

    row = db.execute(
        """SELECT week_number FROM matchups
           WHERE season_id = %s AND is_bye = 0
           GROUP BY week_number
           HAVING COUNT(*) > 0
              AND COUNT(*) = SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
           ORDER BY week_number DESC LIMIT 1""",
        (season_id,)
    ).fetchone()
    if not row:
        flash('No completed weeks yet — nothing to summarize.', 'error')
        return redirect(url_for('admin.season'))

    return redirect(url_for('schedule.week_summary', season_id=season_id, week_num=row['week_number']))


@bp.route('/<int:season_id>/week/<int:week_num>/summary')
@login_required
def week_summary(season_id, week_num):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # ── Week meta (course/date from first non-bye matchup) ───────────────────
    week_matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.status,
                  m.is_bye, m.week_type, m.tee_time, m.starting_hole,
                  m.team1_id, m.team2_id,
                  t1.team_name AS team1_name, t2.team_name AS team2_name,
                  c.course_name
           FROM matchups m
           LEFT JOIN teams   t1 ON m.team1_id  = t1.team_id
           LEFT JOIN teams   t2 ON m.team2_id  = t2.team_id
           LEFT JOIN courses c  ON m.course_id = c.course_id
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY m.is_bye ASC, m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    if not week_matchups:
        flash('No matchups found for that week.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    non_byes = [m for m in week_matchups if not m['is_bye']]
    first    = week_matchups[0]
    week_date = first['scheduled_date']
    week_type = first['week_type'] or 'Normal'
    course_name = next((m['course_name'] for m in week_matchups if m['course_name']), None)

    any_completed = any(m['status'] == 'completed' for m in non_byes)

    # ── Matchup results ──────────────────────────────────────────────────────
    matchup_results = []
    for m in non_byes:
        pts_rows = db.execute(
            "SELECT team_id, SUM(total_points) AS pts FROM match_results WHERE matchup_id = %s GROUP BY team_id",
            (m['matchup_id'],)
        ).fetchall()
        team_pts = {r['team_id']: (r['pts'] or 0) for r in pts_rows}
        t1_pts = team_pts.get(m['team1_id'], 0)
        t2_pts = team_pts.get(m['team2_id'], 0)

        # Per-player breakdown
        players_rows = db.execute(
            """SELECT mr.player_id, mr.team_id, mr.role,
                      mr.hole_points_won, mr.overall_point_won, mr.total_points,
                      p.first_name, p.last_name
               FROM match_results mr
               JOIN players p ON mr.player_id = p.player_id
               WHERE mr.matchup_id = %s
               ORDER BY mr.team_id, mr.role""",
            (m['matchup_id'],)
        ).fetchall()

        if t1_pts > t2_pts:
            winner_team = m['team1_name']
        elif t2_pts > t1_pts:
            winner_team = m['team2_name']
        else:
            winner_team = None

        matchup_results.append({
            'matchup_id':  m['matchup_id'],
            'team1_id':    m['team1_id'],
            'team1_name':  m['team1_name'],
            'team2_id':    m['team2_id'],
            'team2_name':  m['team2_name'],
            't1_pts':      t1_pts,
            't2_pts':      t2_pts,
            'winner_team': winner_team,
            'status':      m['status'],
            'players':     [dict(p) for p in players_rows],
        })

    # ── Weekly leaders (low gross, most match pts) ────────────────────────────
    # Get all scorecards + hole scores for this week
    gross_rows = db.execute(
        """SELECT sc.player_id, p.first_name, p.last_name,
                  SUM(hs.gross_score) AS total_gross,
                  COUNT(hs.hole_score_id) AS holes_played
           FROM rounds r
           JOIN matchups m  ON r.matchup_id  = m.matchup_id
           JOIN scorecards sc ON sc.round_id = r.round_id
           JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
           JOIN players p ON sc.player_id = p.player_id
           WHERE m.season_id = %s AND m.week_number = %s AND sc.is_sub = 0 AND sc.is_absent = 0
           GROUP BY sc.player_id, p.first_name, p.last_name
           HAVING COUNT(hs.hole_score_id) >= 9
           ORDER BY total_gross ASC
           LIMIT 5""",
        (season_id, week_num)
    ).fetchall()

    pts_leaders = db.execute(
        """SELECT mr.player_id, p.first_name, p.last_name,
                  SUM(mr.total_points) AS total_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           JOIN players p ON mr.player_id = p.player_id
           WHERE m.season_id = %s AND m.week_number = %s
           GROUP BY mr.player_id, p.first_name, p.last_name
           ORDER BY total_pts DESC
           LIMIT 5""",
        (season_id, week_num)
    ).fetchall()

    # Birdie leaders for the week
    birdie_rows = db.execute(
        """SELECT sc.player_id, p.first_name, p.last_name,
                  COUNT(*) AS birdies
           FROM rounds r
           JOIN matchups m  ON r.matchup_id  = m.matchup_id
           JOIN scorecards sc ON sc.round_id = r.round_id
           JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
           JOIN players p ON sc.player_id = p.player_id
           WHERE m.season_id = %s AND m.week_number = %s AND sc.is_absent = 0
             AND hs.score_differential = -1
           GROUP BY sc.player_id, p.first_name, p.last_name
           ORDER BY birdies DESC
           LIMIT 3""",
        (season_id, week_num)
    ).fetchall()

    eagle_rows = db.execute(
        """SELECT sc.player_id, p.first_name, p.last_name,
                  COUNT(*) AS eagles
           FROM rounds r
           JOIN matchups m  ON r.matchup_id  = m.matchup_id
           JOIN scorecards sc ON sc.round_id = r.round_id
           JOIN hole_scores hs ON hs.scorecard_id = sc.scorecard_id
           JOIN players p ON sc.player_id = p.player_id
           WHERE m.season_id = %s AND m.week_number = %s AND sc.is_absent = 0
             AND hs.score_differential <= -2
           GROUP BY sc.player_id, p.first_name, p.last_name
           ORDER BY eagles DESC
           LIMIT 3""",
        (season_id, week_num)
    ).fetchall()

    # ── League Standings, through this week ────────────────────────────────
    # get_standings_context(sel_round=week_num) is the exact same call
    # standings.index() makes for its own "Choose Round" filter — literally
    # the Standings page's own table, cumulative through this week, not a
    # second implementation (see get_standings_context()'s docstring).
    standings_context = get_standings_context(db, season_id, league_id, sel_round=week_num)

    # ── Contest Results, this week only ────────────────────────────────────
    contest_results_context = get_week_contest_results_context(db, season_id, league_id, week_num)

    # ── Skins, this week ────────────────────────────────────────────────────
    # get_week_skins_display() is the read-only half of get_week_page_context()
    # (see its own docstring) — just the Winners of the Week tile's data, none
    # of the setup-form/full-scorecard machinery standings.index()'s
    # admin-only embed needs. Round Summary renders it via the same
    # render_winners() macro that tile always uses, so it can't drift.
    skins_display = get_week_skins_display(db, season_id, week_num)

    # ── Handicap Standings, through this week ──────────────────────────────
    handicap_standings_context = get_week_handicap_standings_context(db, season_id, league_id, week_num)

    # Navigation: every week of the season, for the top-of-page week picker
    # (replaces the old prev/next-week buttons — one screen-wide dropdown
    # instead, so it also works as a jump-to-any-week selector on mobile).
    from routes.email_config import _fmt_mmdd
    season_weeks = db.execute(
        """SELECT DISTINCT week_number, MIN(scheduled_date) AS scheduled_date
           FROM matchups
           WHERE season_id = %s AND is_bye = 0
           GROUP BY week_number ORDER BY week_number""",
        (season_id,)
    ).fetchall()
    # MM/DD only, no year -- a full date wraps the week picker's option text
    # on narrow screens (this dropdown is meant to be usable one-handed).
    season_weeks = [dict(w, scheduled_date=_fmt_mmdd(str(w['scheduled_date']) if w['scheduled_date'] else None))
                     for w in season_weeks]

    # Commissioner note for this week (graceful if table absent)
    commissioner_note = ''
    try:
        note_row = db.execute(
            "SELECT notes FROM week_notes WHERE league_id=%s AND season_id=%s AND week_number=%s",
            (league_id, season_id, week_num)
        ).fetchone()
        if note_row:
            commissioner_note = note_row['notes']
    except Exception:
        pass

    # ── Flag an earlier, still-uncompleted week (this recap isn't the true
    # most-recent league night if one is sitting incomplete in between) ──────
    gap_week = db.execute(
        """SELECT week_number, MIN(scheduled_date) AS scheduled_date
           FROM matchups
           WHERE season_id = %s AND is_bye = 0 AND week_number < %s
           GROUP BY week_number
           HAVING COUNT(*) > SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
           ORDER BY week_number DESC LIMIT 1""",
        (season_id, week_num)
    ).fetchone()

    # ── Which stat sections members see (admin-configurable, admins see all) ──
    is_admin = session.get('role') == 'league_admin'
    ALL_RECAP_SECTIONS = ['standings', 'contest_results', 'skins', 'handicap_standings',
                          'eagles', 'birdies', 'low_gross', 'match_points']
    ls_row = db.execute(
        "SELECT recap_visible_sections, recap_email_sections FROM league_settings WHERE league_id = %s AND season_id = %s",
        (league_id, season_id)
    ).fetchone()
    recap_sections_enabled = set(ls_row['recap_visible_sections'].split(',')) if ls_row and ls_row['recap_visible_sections'] else set(ALL_RECAP_SECTIONS)
    # Admins always see every section themselves; the toggle only governs what members see.
    recap_sections = set(ALL_RECAP_SECTIONS) if is_admin else recap_sections_enabled

    # ── Admin-only: compose/send recap email panel context ────────────────────
    compose_ctx = {}
    if is_admin:
        from routes.email_config import (_get_email_config, _get_player_emails,
                                          RECAP_EMAIL_SECTIONS_META, RECAP_EMAIL_DEFAULT_CHECKED)
        cfg = _get_email_config(db, league_id)

        # Ordered "key:0"/"key:1" prefs the admin last saved (see
        # weekly_recap_save_prefs) -- a synthetic __std_rounds entry rides
        # along for the Standings tile's Rounds sub-toggle. Falls back to the
        # built-in default order (RECAP_EMAIL_SECTIONS_META) the first time,
        # and any section added to the catalog later that isn't in an old
        # saved string yet gets appended at the end.
        meta_by_key = {k: (icon, title, desc) for k, icon, title, desc in RECAP_EMAIL_SECTIONS_META}
        default_keys = [k for k, *_ in RECAP_EMAIL_SECTIONS_META]
        saved = ls_row['recap_email_sections'] if ls_row and ls_row['recap_email_sections'] else ''
        saved_flags = {}
        saved_order = []
        for part in saved.split(','):
            if ':' not in part:
                continue
            key, flag = part.rsplit(':', 1)
            saved_flags[key] = (flag == '1')
            if key in meta_by_key:
                saved_order.append(key)
        if saved_order:
            order_keys = saved_order + [k for k in default_keys if k not in saved_flags]
        else:
            order_keys = default_keys
        recap_email_toggles = [
            dict(key=k, checked=saved_flags.get(k, k in RECAP_EMAIL_DEFAULT_CHECKED),
                 icon=meta_by_key[k][0], title=meta_by_key[k][1], desc=meta_by_key[k][2])
            for k in order_keys
        ]
        standings_show_rounds = saved_flags.get('__std_rounds', True)

        compose_ctx = dict(
            cfg=cfg,
            recap_email_toggles=recap_email_toggles,
            standings_show_rounds=standings_show_rounds,
            recipient_count=len(_get_player_emails(db, league_id)),
            email_enabled=bool(cfg.get('email_enabled')),
        )

    return render_template(
        'schedule/week_summary.html',
        season=season,
        week_num=week_num,
        week_date=week_date,
        week_type=week_type,
        course_name=course_name,
        matchup_results=matchup_results,
        any_completed=any_completed,
        gross_rows=[dict(g) for g in gross_rows],
        pts_leaders=[dict(p) for p in pts_leaders],
        birdie_rows=[dict(b) for b in birdie_rows],
        eagle_rows=[dict(e) for e in eagle_rows],
        standings_ctx=standings_context,
        contest_results_ctx=contest_results_context,
        skins_display=skins_display,
        handicap_ctx=handicap_standings_context,
        season_weeks=season_weeks,
        season_id=season_id,
        commissioner_note=commissioner_note,
        gap_week=gap_week,
        is_admin=is_admin,
        recap_sections=recap_sections,
        recap_sections_enabled=recap_sections_enabled,
        all_recap_sections=ALL_RECAP_SECTIONS,
        **compose_ctx,
    )


@bp.route('/<int:season_id>/week/<int:week_num>/summary/recap-sections', methods=['POST'])
@admin_required
def update_recap_sections(season_id, week_num):
    """Save which stat sections members see on the Week Recap page."""
    db = get_db()
    league_id = session['league_id']
    sections = request.form.getlist('sections')
    db.execute(
        "UPDATE league_settings SET recap_visible_sections = %s WHERE league_id = %s AND season_id = %s",
        (','.join(sections), league_id, season_id)
    )
    db.commit()
    flash('Recap sections updated for members.', 'success')
    return redirect(url_for('schedule.week_summary', season_id=season_id, week_num=week_num))


# ---------------------------------------------------------------------------
# Live Leaderboard
# ---------------------------------------------------------------------------

def _build_live_matchup_data(db, season_id, week_num, league_id):
    """Return a serializable list of matchup dicts for the live leaderboard."""
    week_matchups = db.execute(
        """SELECT m.matchup_id, m.week_number, m.scheduled_date, m.status,
                  m.is_bye, m.week_type, m.tee_time, m.starting_hole,
                  m.team1_id, m.team2_id,
                  t1.team_name AS team1_name,
                  t2.team_name AS team2_name,
                  p1a.last_name AS t1_p1_last, p1b.last_name AS t1_p2_last,
                  p2a.last_name AS t2_p1_last, p2b.last_name AS t2_p2_last,
                  c.course_name
           FROM matchups m
           LEFT JOIN teams   t1  ON m.team1_id  = t1.team_id
           LEFT JOIN teams   t2  ON m.team2_id  = t2.team_id
           LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
           LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
           LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
           LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
           LEFT JOIN courses c   ON m.course_id  = c.course_id
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY m.is_bye ASC, m.tee_time ASC NULLS LAST, m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    non_byes = [m for m in week_matchups if not m['is_bye']]
    meta = week_matchups[0] if week_matchups else None

    results = []
    for m in non_byes:
        entry = {
            'matchup_id': m['matchup_id'],
            'status':     m['status'],
            'tee_time':   m['tee_time'],
            'starting_hole': m['starting_hole'],
            'team1_id':   m['team1_id'],
            'team2_id':   m['team2_id'],
        }

        # Team labels
        def tlabel(name, la, lb):
            if name:
                return name
            parts = [x for x in [la, lb] if x]
            return ' / '.join(parts) if parts else '—'

        entry['team1_label'] = tlabel(m['team1_name'], m['t1_p1_last'], m['t1_p2_last'])
        entry['team2_label'] = tlabel(m['team2_name'], m['t2_p1_last'], m['t2_p2_last'])

        if m['status'] == 'completed':
            # Pull final match_results
            pts_rows = db.execute(
                "SELECT team_id, SUM(total_points) AS pts FROM match_results WHERE matchup_id = %s GROUP BY team_id",
                (m['matchup_id'],)
            ).fetchall()
            team_pts = {r['team_id']: (r['pts'] or 0) for r in pts_rows}
            t1p = team_pts.get(m['team1_id'], 0)
            t2p = team_pts.get(m['team2_id'], 0)
            entry['t1_pts'] = t1p
            entry['t2_pts'] = t2p
            if t1p > t2p:
                entry['winner'] = 'team1'
            elif t2p > t1p:
                entry['winner'] = 'team2'
            else:
                entry['winner'] = 'tie'

            # Player breakdown
            player_rows = db.execute(
                """SELECT mr.player_id, mr.team_id, mr.role,
                          mr.hole_points_won, mr.overall_point_won, mr.total_points,
                          p.first_name, p.last_name
                   FROM match_results mr
                   JOIN players p ON mr.player_id = p.player_id
                   WHERE mr.matchup_id = %s
                   ORDER BY mr.team_id, mr.role""",
                (m['matchup_id'],)
            ).fetchall()
            entry['players'] = [dict(r) for r in player_rows]

            # Hole scores for completed matchup (for per-hole display)
            round_row = db.execute(
                "SELECT * FROM rounds WHERE matchup_id = %s", (m['matchup_id'],)
            ).fetchone()
            entry['round_id'] = round_row['round_id'] if round_row else None

            # Gross scores per player
            gross_by_player = {}
            if round_row:
                sc_rows = db.execute(
                    "SELECT player_id, SUM(gross_score) AS total FROM hole_scores hs JOIN scorecards sc ON hs.scorecard_id = sc.scorecard_id WHERE sc.round_id = %s GROUP BY sc.player_id",
                    (round_row['round_id'],)
                ).fetchall()
                for sc in sc_rows:
                    gross_by_player[sc['player_id']] = sc['total']
            entry['gross_by_player'] = gross_by_player

        else:
            entry['t1_pts'] = None
            entry['t2_pts'] = None
            entry['winner'] = None
            entry['players'] = []
            entry['gross_by_player'] = {}

        results.append(entry)

    # Summary stats
    completed_count = sum(1 for r in results if r['status'] == 'completed')
    total_count = len(results)

    # Running standings for this week
    week_pts_rows = db.execute(
        """SELECT mr.team_id, SUM(mr.total_points) AS week_pts
           FROM match_results mr
           JOIN matchups m ON mr.matchup_id = m.matchup_id
           WHERE m.season_id = %s AND m.week_number = %s
           GROUP BY mr.team_id""",
        (season_id, week_num)
    ).fetchall()
    week_pts_map = {r['team_id']: (r['week_pts'] or 0) for r in week_pts_rows}

    # Season standings through last week (before this week)
    prior_week = week_num - 1
    prior_rows = db.execute(
        """SELECT t.team_id, t.team_name,
                  COALESCE(SUM(mr.total_points), 0) AS prior_pts,
                  p1.last_name AS p1_last, p2.last_name AS p2_last,
                  t.team_name AS team_nickname
           FROM teams t
           LEFT JOIN matchups m2 ON (m2.team1_id = t.team_id OR m2.team2_id = t.team_id)
               AND m2.season_id = %s AND m2.status = 'completed' AND m2.is_bye = 0
               AND m2.week_number <= %s
           LEFT JOIN match_results mr ON mr.matchup_id = m2.matchup_id AND mr.team_id = t.team_id
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s
           GROUP BY t.team_id, t.team_name, p1.last_name, p2.last_name
           ORDER BY prior_pts DESC, t.team_id""",
        (season_id, prior_week, season_id)
    ).fetchall()

    standings = []
    for t in prior_rows:
        label = t['team_nickname'] or ' / '.join(x for x in [t['p1_last'], t['p2_last']] if x) or '—'
        wpts = week_pts_map.get(t['team_id'], 0)
        standings.append({
            'team_id':    t['team_id'],
            'label':      label,
            'prior_pts':  t['prior_pts'],
            'week_pts':   wpts,
            'total_pts':  t['prior_pts'] + wpts,
        })
    standings.sort(key=lambda x: -x['total_pts'])

    return {
        'matchups':         results,
        'standings':        standings,
        'completed_count':  completed_count,
        'total_count':      total_count,
        'week_date':        meta['scheduled_date'] if meta else None,
        'week_type':        (meta['week_type'] or 'Normal') if meta else 'Normal',
        'course_name':      next((m['course_name'] for m in week_matchups if m['course_name']), None),
    }


@bp.route('/<int:season_id>/week/<int:week_num>/live')
@login_required
def live_leaderboard(season_id, week_num):
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    data = _build_live_matchup_data(db, season_id, week_num, league_id)

    all_done = data['completed_count'] == data['total_count'] and data['total_count'] > 0
    refresh_secs = 0 if all_done else 60

    # Commissioner note (graceful if table absent)
    commissioner_note = ''
    try:
        note_row = db.execute(
            "SELECT notes FROM week_notes WHERE league_id=%s AND season_id=%s AND week_number=%s",
            (league_id, season_id, week_num)
        ).fetchone()
        if note_row:
            commissioner_note = note_row['notes']
    except Exception:
        pass

    return render_template(
        'schedule/live_leaderboard.html',
        season=season,
        season_id=season_id,
        week_num=week_num,
        data=data,
        refresh_secs=refresh_secs,
        commissioner_note=commissioner_note,
    )


@bp.route('/<int:season_id>/week/<int:week_num>/live-data')
@login_required
def live_leaderboard_data(season_id, week_num):
    """JSON endpoint for AJAX refresh of live leaderboard."""
    from flask import jsonify
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        return jsonify({'error': 'not found'}), 404

    data = _build_live_matchup_data(db, season_id, week_num, league_id)
    return jsonify(data)


# ---------------------------------------------------------------------------
# Blank Pre-Round Scorecard
# ---------------------------------------------------------------------------

def _calc_strokes(hdcp, holes):
    """Return {hole_number: stroke_count} given a handicap index and hole list."""
    from routes.scores import strokes_on_hole
    if hdcp is None or not holes:
        return {}
    ph = int(hdcp)
    n = len(holes)
    hcp_idxs = [h['handicap_index'] for h in holes]
    return {h['hole_number']: strokes_on_hole(ph, h['handicap_index'], total_holes=n,
                                               hcp_indices=hcp_idxs) for h in holes}


@bp.route('/<int:season_id>/week/<int:week_num>/matchup/<int:matchup_id>/blank-scorecard')
@login_required
def blank_scorecard(season_id, week_num, matchup_id):
    db        = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    matchup = db.execute(
        """SELECT m.*,
                  c.course_name,
                  te.tee_name, te.nine AS side, te.gender, te.slope, te.rating
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.matchup_id = %s AND m.season_id = %s""",
        (matchup_id, season_id)
    ).fetchone()

    if not matchup or matchup['is_bye']:
        flash('Matchup not found.', 'error')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    # Holes for the assigned tee (empty list if no tee assigned)
    holes = []
    if matchup['tee_id']:
        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (matchup['tee_id'],)
        ).fetchall()

    # Team / player info (name + handicap)
    team_info, _, _ = _build_team_info(db, season_id, league_id)
    t1 = team_info.get(matchup['team1_id'])
    t2 = team_info.get(matchup['team2_id'])

    # Stroke allocation per player per hole
    t1_p1_strokes = _calc_strokes(t1['p1_hdcp'] if t1 else None, holes)
    t1_p2_strokes = _calc_strokes(t1['p2_hdcp'] if t1 else None, holes)
    t2_p1_strokes = _calc_strokes(t2['p1_hdcp'] if t2 else None, holes)
    t2_p2_strokes = _calc_strokes(t2['p2_hdcp'] if t2 else None, holes)

    league = db.execute(
        "SELECT league_name FROM leagues WHERE league_id = %s", (league_id,)
    ).fetchone()

    # Par total and yardage total for summary row
    par_total = sum(h['par'] for h in holes) if holes else 0

    return render_template(
        'schedule/blank_scorecard.html',
        season=season,
        matchup=matchup,
        league=league,
        holes=holes,
        par_total=par_total,
        t1=t1, t2=t2,
        t1_p1_strokes=t1_p1_strokes,
        t1_p2_strokes=t1_p2_strokes,
        t2_p1_strokes=t2_p1_strokes,
        t2_p2_strokes=t2_p2_strokes,
        week_num=week_num,
        print_date=datetime.now().strftime('%b %d, %Y'),
    )


# ---------------------------------------------------------------------------
# Latest Scorecards redirect — used by nav link
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/scorecards/latest')
@login_required
def latest_scorecards(season_id):
    db = get_db()
    row = db.execute(
        """SELECT week_number FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number DESC LIMIT 1""",
        (season_id,)
    ).fetchone()
    if not row:
        flash('No completed weeks yet.', 'info')
        return redirect(url_for('schedule.current', week='all'))
    return redirect(url_for('schedule.week_scorecards', season_id=season_id, week_num=row['week_number']))


# ---------------------------------------------------------------------------
# Week Scorecards — all completed scorecards for a given week
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/week/<int:week_num>/scorecards')
@login_required
def week_scorecards(season_id, week_num):
    from routes.scores import _load_completed_scorecard, _settings_scoring_mode, get_league_settings
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    week_matchups = db.execute(
        """SELECT m.matchup_id, m.status, m.is_bye
           FROM matchups m
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    settings = get_league_settings(db, season_id, league_id)
    scoring_mode = _settings_scoring_mode(settings)

    scorecards = []
    for m in week_matchups:
        if m['is_bye'] or m['status'] != 'completed':
            continue
        sc = _load_completed_scorecard(db, m['matchup_id'], scoring_mode)
        if sc:
            scorecards.append(sc)

    week_date = db.execute(
        "SELECT scheduled_date FROM matchups WHERE season_id=%s AND week_number=%s AND is_bye=0 LIMIT 1",
        (season_id, week_num)
    ).fetchone()

    # All weeks that have at least one completed matchup (for the dropdown)
    completed_weeks = db.execute(
        """SELECT DISTINCT m.week_number, MIN(m.scheduled_date) AS week_date
             FROM matchups m
            WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
            GROUP BY m.week_number
            ORDER BY m.week_number ASC""",
        (season_id,)
    ).fetchall()

    return render_template(
        'schedule/week_scorecards.html',
        season=season,
        season_id=season_id,
        week_num=week_num,
        week_date=week_date['scheduled_date'] if week_date else None,
        scorecards=scorecards,
        scoring_mode=scoring_mode,
        completed_weeks=completed_weeks,
    )


# ---------------------------------------------------------------------------
# Detailed Score Sheet — flat player list with hcp before/after and standings
# ---------------------------------------------------------------------------

def _fmt_tee_color(tee):
    if not tee:
        return '—'
    return (tee['tee_color'] or tee['tee_name'] or '—').strip()


@bp.route('/<int:season_id>/week/<int:week_num>/detailed-score-sheet')
@login_required
def detailed_score_sheet(season_id, week_num):
    from routes.scores import _settings_scoring_mode, get_league_settings
    db        = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    week_matchups = db.execute(
        """SELECT m.matchup_id, m.status, m.is_bye, m.team1_id, m.team2_id
           FROM matchups m
           WHERE m.season_id = %s AND m.week_number = %s
           ORDER BY m.matchup_id ASC""",
        (season_id, week_num)
    ).fetchall()

    # Per-player cumulative points (for current and prior week rank columns)
    def _player_season_pts(through_week):
        rows = db.execute(
            """SELECT mr.player_id, COALESCE(SUM(mr.total_points), 0) AS pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.week_number <= %s AND m.is_bye = 0
                 AND mr.player_id IS NOT NULL
               GROUP BY mr.player_id""",
            (season_id, through_week)
        ).fetchall()
        return {r['player_id']: float(r['pts']) for r in rows}

    def _team_season_pts(through_week):
        rows = db.execute(
            """SELECT mr.team_id, COALESCE(SUM(mr.total_points), 0) AS pts
               FROM match_results mr
               JOIN matchups m ON mr.matchup_id = m.matchup_id
               WHERE m.season_id = %s AND m.week_number <= %s AND m.is_bye = 0
                 AND mr.team_id IS NOT NULL
               GROUP BY mr.team_id""",
            (season_id, through_week)
        ).fetchall()
        return {r['team_id']: float(r['pts']) for r in rows}

    cur_pts_map       = _player_season_pts(week_num)
    prior_pts_map     = _player_season_pts(week_num - 1)
    cur_team_pts_map  = _team_season_pts(week_num)
    prior_team_pts_map = _team_season_pts(week_num - 1)

    def _rank_by_pts(pts_map):
        sorted_pids = sorted(pts_map.keys(), key=lambda p: -pts_map[p])
        return {pid: i + 1 for i, pid in enumerate(sorted_pids)}

    cur_rank        = _rank_by_pts(cur_pts_map)
    prior_rank      = _rank_by_pts(prior_pts_map)
    cur_team_rank   = _rank_by_pts(cur_team_pts_map)
    prior_team_rank = _rank_by_pts(prior_team_pts_map)

    header_holes = []
    header_tee   = None
    sheet_rows   = []

    for m in week_matchups:
        if m['is_bye'] or m['status'] != 'completed':
            continue

        round_row = db.execute(
            "SELECT * FROM rounds WHERE matchup_id = %s", (m['matchup_id'],)
        ).fetchone()
        if not round_row:
            continue
        round_id = round_row['round_id']

        holes = db.execute(
            "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
            (round_row['tee_id'],)
        ).fetchall()
        if not header_holes:
            header_holes = holes
            header_tee = db.execute(
                "SELECT * FROM tees WHERE tee_id = %s", (round_row['tee_id'],)
            ).fetchone()

        default_tee = db.execute(
            "SELECT * FROM tees WHERE tee_id = %s", (round_row['tee_id'],)
        ).fetchone()

        scorecards = db.execute(
            """SELECT sc.*, p.first_name, p.last_name, p.player_id,
                      t.team_id, t.team_name AS team_nickname,
                      tp1.last_name AS t_p1_last, tp2.last_name AS t_p2_last
               FROM scorecards sc
               JOIN players p ON sc.player_id = p.player_id
               JOIN teams t ON sc.team_id = t.team_id
               LEFT JOIN players tp1 ON t.player1_id = tp1.player_id
               LEFT JOIN players tp2 ON t.player2_id = tp2.player_id
               WHERE sc.round_id = %s
               ORDER BY sc.team_id, sc.player_id""",
            (round_id,)
        ).fetchall()

        results = db.execute(
            "SELECT player_id, total_points, role FROM match_results WHERE matchup_id = %s",
            (m['matchup_id'],)
        ).fetchall()
        role_map   = {r['player_id']: r['role']                for r in results}
        wk_pts_map = {r['player_id']: float(r['total_points']) for r in results}

        for sc in scorecards:
            pid = sc['player_id']

            hs = db.execute(
                "SELECT * FROM hole_scores WHERE scorecard_id = %s ORDER BY hole_number",
                (sc['scorecard_id'],)
            ).fetchall()
            gross     = [h['gross_score'] for h in hs]
            out_score = sum(gross) if gross else None

            if sc['tee_id'] and sc['tee_id'] != round_row['tee_id']:
                p_tee = db.execute(
                    "SELECT * FROM tees WHERE tee_id = %s", (sc['tee_id'],)
                ).fetchone()
            else:
                p_tee = default_tee

            before_row = db.execute(
                """SELECT handicap_index FROM handicap_history
                   WHERE player_id = %s
                     AND (trigger_round_id IS NULL OR trigger_round_id < %s)
                   ORDER BY calculated_date DESC, handicap_id DESC LIMIT 1""",
                (pid, round_id)
            ).fetchone()
            after_row = db.execute(
                """SELECT handicap_index FROM handicap_history
                   WHERE player_id = %s AND trigger_round_id = %s
                   ORDER BY handicap_id DESC LIMIT 1""",
                (pid, round_id)
            ).fetchone()

            role       = role_map.get(pid, '?')
            team_order = 0 if sc['team_id'] == m['team1_id'] else 1
            team_id    = sc['team_id']
            playing_hcp = sc['handicap_at_time_of_play']

            sheet_rows.append({
                'pid':               pid,
                'matchup_id':        m['matchup_id'],
                '_sort':             (m['matchup_id'], team_order, role or '?'),
                'team_num':          team_order + 1,
                'pos':               cur_team_rank.get(team_id, None),
                'last_pos':          prior_team_rank.get(team_id, None),
                'name':              f"{sc['last_name'].upper()}, {sc['first_name'].upper()}",
                'first_name_upper':  sc['first_name'].upper(),
                'last_name_upper':   sc['last_name'].upper(),
                'tee_color':         _fmt_tee_color(p_tee),
                'gross':             gross,
                'out_score':         out_score,
                'playing_hcp':       round(playing_hcp) if playing_hcp is not None else None,
                'hcp_before':        before_row['handicap_index'] if before_row else None,
                'hcp_after':         after_row['handicap_index']  if after_row  else None,
                'wk_pts':            wk_pts_map.get(pid, 0.0),
                'indiv_pts_before':  prior_pts_map.get(pid, 0.0),
                'indiv_pts_after':   cur_pts_map.get(pid, 0.0),
                'team_pts_before':   prior_team_pts_map.get(team_id, 0.0),
                'team_pts_after':    cur_team_pts_map.get(team_id, 0.0),
                'is_absent':         bool(sc['is_absent'] if 'is_absent' in sc.keys() else False),
            })

    sheet_rows.sort(key=lambda r: r['_sort'])
    for i, r in enumerate(sheet_rows):
        r['row_num'] = i + 1

    # Mark first row of each new matchup group so the template can draw a separator
    seen = set()
    for r in sheet_rows:
        r['new_group'] = r['matchup_id'] not in seen
        seen.add(r['matchup_id'])

    # Per-hole score counts for footer summary
    # holes list from header_holes; collect diffs vs par across all non-absent players
    score_counts = {'eagle': 0, 'birdie': 0, 'par': 0, 'bogey': 0, 'double': 0, 'other': 0}
    if header_holes:
        for r in sheet_rows:
            if r['is_absent']:
                continue
            for i, h in enumerate(header_holes):
                if i >= len(r['gross']) or r['gross'][i] is None:
                    continue
                par = h['par']
                if not par:
                    continue
                diff = r['gross'][i] - par
                if diff <= -2:
                    score_counts['eagle'] += 1
                elif diff == -1:
                    score_counts['birdie'] += 1
                elif diff == 0:
                    score_counts['par'] += 1
                elif diff == 1:
                    score_counts['bogey'] += 1
                elif diff == 2:
                    score_counts['double'] += 1
                else:
                    score_counts['other'] += 1

    week_date = db.execute(
        "SELECT scheduled_date FROM matchups WHERE season_id=%s AND week_number=%s AND is_bye=0 LIMIT 1",
        (season_id, week_num)
    ).fetchone()

    completed_weeks = db.execute(
        """SELECT DISTINCT m.week_number, MIN(m.scheduled_date) AS week_date
             FROM matchups m
            WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
            GROUP BY m.week_number
            ORDER BY m.week_number ASC""",
        (season_id,)
    ).fetchall()

    return render_template(
        'schedule/detailed_score_sheet.html',
        season=season,
        season_id=season_id,
        week_num=week_num,
        week_date=week_date['scheduled_date'] if week_date else None,
        sheet_rows=sheet_rows,
        header_holes=header_holes,
        header_tee=header_tee,
        completed_weeks=completed_weeks,
        score_counts=score_counts,
    )


# ---------------------------------------------------------------------------
# Week Preview Page — pre-round information for upcoming weeks
# ---------------------------------------------------------------------------

@bp.route('/<int:season_id>/week/<int:week_num>/preview')
@login_required
def week_preview(season_id, week_num):
    db        = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    league = db.execute(
        "SELECT league_name FROM leagues WHERE league_id = %s", (league_id,)
    ).fetchone()

    # All non-bye matchups for this week
    matchups = db.execute(
        """SELECT m.*,
                  c.course_name, c.city,
                  te.tee_name, te.nine AS side, te.slope, te.rating, te.color AS tee_color
           FROM matchups m
           LEFT JOIN courses c  ON m.course_id = c.course_id
           LEFT JOIN tees    te ON m.tee_id    = te.tee_id
           WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
           ORDER BY m.tee_time ASC NULLS LAST, m.matchup_id""",
        (season_id, week_num)
    ).fetchall()

    if not matchups:
        flash('No matchups found for this week.', 'info')
        return redirect(url_for('schedule.index', season_id=season_id, week='all'))

    team_info, team_num_map, _ = _build_team_info(db, season_id, league_id)

    # Get holes for the tee used in first matchup (usually all same tee)
    holes = []
    for m in matchups:
        if m['tee_id']:
            holes = db.execute(
                "SELECT * FROM holes WHERE tee_id = %s ORDER BY hole_number",
                (m['tee_id'],)
            ).fetchall()
            break

    # Build per-player recent form (last 5 results across all rounds this season)
    # Returns list of 'W'/'T'/'L' most recent first
    def _recent_form(player_id, n=5):
        rows = db.execute(
            """SELECT mr.overall_point_won
               FROM match_results mr
               JOIN scorecards sc ON mr.scorecard_id = sc.scorecard_id
               JOIN matchups m    ON sc.matchup_id   = m.matchup_id
               WHERE mr.player_id = %s AND m.season_id = %s
               ORDER BY m.week_number DESC, mr.result_id DESC
               LIMIT %s""",
            (player_id, season_id, n)
        ).fetchall()
        result = []
        for r in rows:
            v = r['overall_point_won']
            if v is None:
                result.append('?')
            elif v >= 1.5:
                result.append('W')
            elif v >= 0.9:
                result.append('T')
            else:
                result.append('L')
        return result

    # H2H record between two teams this season (from match_results summed per matchup)
    def _h2h_record(team1_id, team2_id):
        rows = db.execute(
            """SELECT sc.team_id, SUM(mr.total_points) AS team_pts
               FROM match_results mr
               JOIN scorecards sc ON mr.scorecard_id = sc.scorecard_id
               JOIN matchups m    ON sc.matchup_id   = m.matchup_id
               WHERE m.season_id = %s
                 AND m.is_bye = 0
                 AND (
                   (m.team1_id = %s AND m.team2_id = %s) OR
                   (m.team1_id = %s AND m.team2_id = %s)
                 )
               GROUP BY sc.matchup_id, sc.team_id""",
            (season_id, team1_id, team2_id, team2_id, team1_id)
        ).fetchall()

        t1_wins = t1_ties = t2_wins = 0
        # Group by matchup: compare total pts per team per matchup
        matchup_pts = {}
        for r in rows:
            # Can't group by matchup_id easily here; use a simpler approach
            pass

        # Simpler: query matchup-level results
        m_rows = db.execute(
            """SELECT m.matchup_id,
                      SUM(CASE WHEN sc.team_id = %s THEN mr.total_points ELSE 0 END) AS t1_pts,
                      SUM(CASE WHEN sc.team_id = %s THEN mr.total_points ELSE 0 END) AS t2_pts
               FROM matchups m
               JOIN scorecards sc ON sc.matchup_id = m.matchup_id
               JOIN match_results mr ON mr.scorecard_id = sc.scorecard_id
               WHERE m.season_id = %s AND m.status = 'completed' AND m.is_bye = 0
                 AND ((m.team1_id = %s AND m.team2_id = %s) OR (m.team1_id = %s AND m.team2_id = %s))
               GROUP BY m.matchup_id""",
            (team1_id, team2_id, season_id, team1_id, team2_id, team2_id, team1_id)
        ).fetchall()

        for r in m_rows:
            t1p = r['t1_pts'] or 0
            t2p = r['t2_pts'] or 0
            if t1p > t2p:
                t1_wins += 1
            elif t2p > t1p:
                t2_wins += 1
            else:
                t1_ties += 1

        return {'t1_wins': t1_wins, 't1_ties': t1_ties, 't2_wins': t2_wins,
                'played': t1_wins + t1_ties + t2_wins}

    # Build stroke net differential for A/B flight
    def _stroke_diff(hdcp_a, hdcp_b):
        """Returns (giver, receiver, strokes) or None if even."""
        if hdcp_a is None or hdcp_b is None:
            return None
        diff = int(hdcp_a or 0) - int(hdcp_b or 0)
        if diff == 0:
            return None
        if diff > 0:
            return {'giver': 'b', 'strokes': diff}   # b gives strokes to a
        else:
            return {'giver': 'a', 'strokes': -diff}   # a gives strokes to b

    preview_matchups = []
    for m in matchups:
        t1 = team_info.get(m['team1_id']) or {}
        t2 = team_info.get(m['team2_id']) or {}

        # A-flight: p1 vs p1, B-flight: p2 vs p2
        t1_p1_strokes = _calc_strokes(t1.get('p1_hdcp'), holes)
        t1_p2_strokes = _calc_strokes(t1.get('p2_hdcp'), holes)
        t2_p1_strokes = _calc_strokes(t2.get('p1_hdcp'), holes)
        t2_p2_strokes = _calc_strokes(t2.get('p2_hdcp'), holes)

        a_diff = _stroke_diff(t1.get('p1_hdcp'), t2.get('p1_hdcp'))
        b_diff = _stroke_diff(t1.get('p2_hdcp'), t2.get('p2_hdcp'))

        h2h = _h2h_record(m['team1_id'], m['team2_id'])

        t1_p1_form = _recent_form(t1.get('p1_id')) if t1.get('p1_id') else []
        t1_p2_form = _recent_form(t1.get('p2_id')) if t1.get('p2_id') else []
        t2_p1_form = _recent_form(t2.get('p1_id')) if t2.get('p1_id') else []
        t2_p2_form = _recent_form(t2.get('p2_id')) if t2.get('p2_id') else []

        preview_matchups.append({
            'matchup': m,
            't1': t1,
            't2': t2,
            't1_p1_strokes': t1_p1_strokes,
            't1_p2_strokes': t1_p2_strokes,
            't2_p1_strokes': t2_p1_strokes,
            't2_p2_strokes': t2_p2_strokes,
            'a_diff': a_diff,
            'b_diff': b_diff,
            'h2h': h2h,
            't1_p1_form': t1_p1_form,
            't1_p2_form': t1_p2_form,
            't2_p1_form': t2_p1_form,
            't2_p2_form': t2_p2_form,
        })

    # Par row from holes
    par_total = sum(h['par'] for h in holes) if holes else 0
    # Scheduled date from first matchup
    week_date = matchups[0]['scheduled_date'] if matchups else None

    return render_template(
        'schedule/week_preview.html',
        season=season,
        league=league,
        week_num=week_num,
        week_date=week_date,
        preview_matchups=preview_matchups,
        holes=holes,
        par_total=par_total,
    )
