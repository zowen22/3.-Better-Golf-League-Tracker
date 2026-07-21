import re
from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import database
from database import get_db, get_current_season_id
from routes.auth import login_required, admin_required
from routes.admin import _seed_starting_handicaps

bp = Blueprint('seasons', __name__, url_prefix='/seasons')

# Explicit clone column list for league_settings: every column in
# schema_postgres.sql:104-147 EXCEPT setting_id (own PK) and season_id (set
# explicitly to the new season). Keep this list in sync with the schema —
# see the "Start Another Season" audit doc for the cross-check against
# init_db.py's additive migrations (none currently add league_settings
# columns beyond what's already in the base schema).
_LEAGUE_SETTINGS_CLONE_COLUMNS = [
    'league_id', 'holes_per_round', 'scoring_type',
    'match_play_points_per_hole', 'match_play_tie_points', 'match_play_overall_point',
    # Best Ball / Team Totals / Classical Stroke Play columns (added 2026-07-10,
    # after this clone list was originally written) -- were missing entirely,
    # meaning "Start Another Season" silently dropped a league's configured
    # format/point values back to schema defaults instead of carrying them
    # forward. Found and fixed 2026-07-10 while touching this list for the
    # match_play_tie_points addition above. scoring_mode itself was already
    # present further down this list (with multi_course/absence_overall_point_policy).
    'best_ball_points_per_hole', 'best_ball_tie_points', 'best_ball_overall_point',
    'team_totals_points_per_hole', 'team_totals_tie_points', 'team_totals_overall_point',
    'classical_stroke_play_points_per_stroke',
    'absent_player_policy_id',
    'playoff_teams', 'finals_weeks', 'min_rounds_for_handicap',
    'rounds_to_average', 'high_scores_to_drop', 'handicap_percent',
    'max_handicap_index', 'max_score_over_handicap',
    'negative_handicap_allowed', 'carry_scores_across_seasons',
    'skins_default_gross_net', 'skins_default_amount',
    'self_reporting_enabled', 'self_reporting_requires_approval',
    'skins_self_optin_enabled', 'diff_calculation_type',
    'max_score_per_hole', 'max_score_action', 'max_score_message',
    'padding_score_count', 'low_scores_to_drop',
    'segment_start_week', 'segment_end_week',
    'dues_amount',  # dues_due_date deliberately excluded — forced NULL below (stale date)
    'show_dues_shame_widget',
    'scoring_mode', 'multi_course', 'absence_overall_point_policy',
    'temp_handicap_percent_member', 'temp_handicap_percent_sub',
    'show_announcements_widget', 'show_round_recap_widget',
    'show_activity_feed_widget', 'show_league_activity_widget',
]


def season_is_over(db, season_id):
    """True when the season has concluded: its latest scheduled matchup
    date is in the past, or — if it has no matchups yet — its end_date is
    in the past. Dates are TEXT (ISO 'YYYY-MM-DD'), compared as strings
    against today's ISO date, matching main.py's scheduled_date convention.
    """
    today_str = date.today().isoformat()

    row = db.execute(
        "SELECT MAX(scheduled_date) AS last_date FROM matchups WHERE season_id = %s AND scheduled_date IS NOT NULL",
        (season_id,)
    ).fetchone()
    last_date = row['last_date'] if row else None
    if last_date:
        return last_date < today_str

    season = db.execute(
        "SELECT end_date FROM seasons WHERE season_id = %s", (season_id,)
    ).fetchone()
    if season and season['end_date']:
        return season['end_date'] < today_str
    return False


def _next_season_name(latest_name):
    """Increment the first 4-digit year token in a season name
    ("2026 Summer Season" -> "2027 Summer Season"); '' if no year token."""
    if not latest_name:
        return ''
    m = re.search(r'(?<!\d)(\d{4})(?!\d)', latest_name)
    if not m:
        return ''
    year = int(m.group(1)) + 1
    return latest_name[:m.start(1)] + str(year) + latest_name[m.end(1):]


@bp.route('/')
@login_required
def index():
    db = get_db()
    seasons = db.execute(
        """SELECT s.season_id, s.season_name, s.start_date, s.end_date,
                  COUNT(DISTINCT t.team_id) as team_count
           FROM seasons s
           LEFT JOIN teams t ON t.season_id = s.season_id
           WHERE s.league_id = %s
           GROUP BY s.season_id
           ORDER BY s.start_date DESC, s.season_id DESC""",
        (session['league_id'],)
    ).fetchall()
    return render_template('seasons/index.html', seasons=seasons)


@bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create():
    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        start_date  = request.form.get('start_date', '').strip() or None
        end_date    = request.form.get('end_date', '').strip() or None

        if not season_name:
            flash('Season name is required.', 'error')
            return render_template('seasons/create.html',
                                   season_name=season_name, start_date=start_date or '', end_date=end_date or '')

        db = get_db()
        league_id = session['league_id']
        existing = db.execute(
            "SELECT season_id FROM seasons WHERE league_id = %s AND LOWER(season_name) = LOWER(%s)",
            (league_id, season_name)
        ).fetchone()
        if existing:
            flash('A season with that name already exists.', 'error')
            return render_template('seasons/create.html',
                                   season_name=season_name, start_date=start_date or '', end_date=end_date or '')

        # Is this the league's very first season? Drives whether we hand
        # off into the Season Setup wizard below (a brand-new league needs
        # that onboarding; an admin adding another season to an
        # already-running league doesn't need to be walked through it again).
        is_first_season = db.execute(
            "SELECT COUNT(*) AS n FROM seasons WHERE league_id = %s", (league_id,)
        ).fetchone()['n'] == 0

        if database.is_postgres():
            season_id = db.execute(
                "INSERT INTO seasons (league_id, season_name, start_date, end_date) VALUES (%s, %s, %s, %s) RETURNING season_id",
                (league_id, season_name, start_date, end_date)
            ).fetchone()[0]
            db.commit()
        else:
            db.execute(
                "INSERT INTO seasons (league_id, season_name, start_date, end_date) VALUES (%s, %s, %s, %s)",
                (league_id, season_name, start_date, end_date)
            )
            db.commit()
            season_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        session['current_season_id'] = season_id
        flash(f'Season "{season_name}" created.', 'success')
        if is_first_season:
            return redirect(url_for('seasons.setup', season_id=season_id))
        return redirect(url_for('seasons.index'))

    return render_template('seasons/create.html', season_name='', start_date='', end_date='')


@bp.route('/start-next', methods=['GET', 'POST'])
@admin_required
def start_next():
    """'Start Another Season' wizard: create a new season, optionally
    bringing over teams/divisions, league settings, and seeded starting
    handicaps from the season the admin is currently in. Players and
    courses always carry over automatically — they're league-scoped, not
    season-scoped, so there's nothing to copy for them.
    """
    db = get_db()
    league_id = session['league_id']

    prior_season_id = get_current_season_id(db, league_id)
    prior_season = None
    if prior_season_id:
        prior_season = db.execute(
            "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
            (prior_season_id, league_id)
        ).fetchone()

    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        start_date  = request.form.get('start_date', '').strip() or None
        end_date    = request.form.get('end_date', '').strip() or None
        bring_teams    = bool(request.form.get('bring_teams'))
        bring_settings = bool(request.form.get('bring_settings'))
        # Hard precondition: seeding handicaps requires teams to exist in
        # the new season first (admin.seed_handicaps reads the player set
        # via a teams join) — re-check server-side regardless of what the
        # (JS-disabled) checkbox submitted.
        seed_hcp = bool(request.form.get('seed_handicaps')) and bring_teams

        form_state = dict(season_name=season_name, start_date=start_date or '',
                           end_date=end_date or '', bring_teams=bring_teams,
                           bring_settings=bring_settings, seed_handicaps=seed_hcp)

        errors = []
        if not season_name:
            errors.append('Season name is required.')
        if not start_date:
            errors.append('Start date is required.')
        if not errors:
            existing = db.execute(
                "SELECT season_id FROM seasons WHERE league_id = %s AND LOWER(season_name) = LOWER(%s)",
                (league_id, season_name)
            ).fetchone()
            if existing:
                errors.append('A season with that name already exists.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('seasons/start_next.html', **form_state)

        try:
            new_row = db.execute(
                "INSERT INTO seasons (league_id, season_name, start_date, end_date) VALUES (%s, %s, %s, %s) RETURNING season_id",
                (league_id, season_name, start_date, end_date)
            ).fetchone()
            new_season_id = new_row['season_id']

            if bring_settings and prior_season_id:
                prior_settings = db.execute(
                    "SELECT * FROM league_settings WHERE season_id = %s AND league_id = %s",
                    (prior_season_id, league_id)
                ).fetchone()
                if prior_settings:
                    cols = _LEAGUE_SETTINGS_CLONE_COLUMNS
                    placeholders = ', '.join(['%s'] * len(cols))
                    values = tuple(prior_settings[c] for c in cols)
                    db.execute(
                        f"""INSERT INTO league_settings (season_id, dues_due_date, {', '.join(cols)})
                            VALUES (%s, %s, {placeholders})""",
                        (new_season_id, None) + values
                    )
                # If the prior season has no settings row, skip silently —
                # the hub's Settings card shows "pending" either way.

            teams_copied = 0
            if bring_teams and prior_season_id:
                result = db.execute(
                    """INSERT INTO teams (season_id, league_id, team_name, player1_id, player2_id, division_name)
                       SELECT %s, league_id, team_name, player1_id, player2_id, division_name
                       FROM teams WHERE season_id = %s AND league_id = %s""",
                    (new_season_id, prior_season_id, league_id)
                )
                teams_copied = result.rowcount

            if seed_hcp and teams_copied:
                _seed_starting_handicaps(db, league_id, new_season_id)

            db.commit()
        except Exception:
            db.rollback()
            flash('Something went wrong creating the season — no changes were made. Please try again.', 'error')
            return render_template('seasons/start_next.html', **form_state)

        session['current_season_id'] = new_season_id
        flash(f'Season "{season_name}" created.', 'success')
        return redirect(url_for('seasons.setup', season_id=new_season_id))

    prefill_name = _next_season_name(prior_season['season_name']) if prior_season else ''
    return render_template('seasons/start_next.html',
                           season_name=prefill_name, start_date='', end_date='',
                           bring_teams=True, bring_settings=True, seed_handicaps=True)


@bp.route('/<int:season_id>/setup')
@admin_required
def setup(season_id):
    """Season Setup hub: status widgets for the pre-season chores a new
    season needs before it's fully usable (roster, activation, settings,
    schedule, buy-ins, starting handicaps)."""
    db = get_db()
    league_id = session['league_id']

    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    # ── Roster / Teams ──────────────────────────────────────────────────
    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.first_name AS p1_first, p1.last_name AS p1_last, p1.active AS p1_active,
                  p2.first_name AS p2_first, p2.last_name AS p2_last, p2.active AS p2_active
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY t.team_name""",
        (season_id, league_id)
    ).fetchall()
    team_count = len(teams)
    inactive_teams = []
    for t in teams:
        flagged = []
        if t['p1_active'] == 0:
            flagged.append(f"{t['p1_first']} {t['p1_last']}")
        if t['p2_active'] == 0:
            flagged.append(f"{t['p2_first']} {t['p2_last']}")
        if flagged:
            inactive_teams.append({'team_name': t['team_name'] or '(unnamed team)', 'players': flagged})

    # ── Players (league-wide, not season-scoped) ────────────────────────
    active_count = db.execute(
        "SELECT COUNT(*) AS c FROM players WHERE league_id = %s AND active = 1", (league_id,)
    ).fetchone()['c']
    inactive_count = db.execute(
        "SELECT COUNT(*) AS c FROM players WHERE league_id = %s AND active = 0", (league_id,)
    ).fetchone()['c']

    # ── League Settings ──────────────────────────────────────────────────
    settings_row = db.execute(
        "SELECT setting_id, dues_amount, dues_due_date FROM league_settings WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    settings_done = settings_row is not None

    # ── Schedule ─────────────────────────────────────────────────────────
    matchup_count = db.execute(
        "SELECT COUNT(*) AS c FROM matchups WHERE season_id = %s", (season_id,)
    ).fetchone()['c']

    # ── Buy-ins / Dues — reuse dues.py's eligibility+paid derivation
    # (same queries as dues.py's _get_dues_settings/admin_dues; not forked
    # math, just replicated here to avoid a heavier cross-blueprint import
    # for two simple COUNT queries) ──────────────────────────────────────
    dues_configured = bool(settings_row and (settings_row['dues_amount'] or settings_row['dues_due_date']))
    dues_paid_count = 0
    dues_total_count = 0
    if dues_configured:
        dues_total_count = db.execute(
            """SELECT COUNT(DISTINCT p.player_id) AS c
               FROM players p
               JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
               WHERE t.season_id = %s AND t.league_id = %s AND p.active = 1""",
            (season_id, league_id)
        ).fetchone()['c']
        dues_paid_count = db.execute(
            "SELECT COUNT(DISTINCT player_id) AS c FROM dues_payments WHERE season_id = %s AND league_id = %s",
            (season_id, league_id)
        ).fetchone()['c']

    # ── Starting Handicaps ───────────────────────────────────────────────
    hcp_rows = db.execute(
        """SELECT DISTINCT p.player_id, p.starting_handicap
           FROM players p
           JOIN teams t ON (t.player1_id = p.player_id OR t.player2_id = p.player_id)
           WHERE t.season_id = %s AND t.league_id = %s""",
        (season_id, league_id)
    ).fetchall()
    hcp_total = len(hcp_rows)
    hcp_seeded = sum(1 for r in hcp_rows if r['starting_handicap'] is not None)

    return render_template('seasons/setup.html',
                           season=season,
                           team_count=team_count,
                           inactive_teams=inactive_teams,
                           active_count=active_count,
                           inactive_count=inactive_count,
                           settings_done=settings_done,
                           matchup_count=matchup_count,
                           dues_configured=dues_configured,
                           dues_paid_count=dues_paid_count,
                           dues_total_count=dues_total_count,
                           hcp_total=hcp_total,
                           hcp_seeded=hcp_seeded)


@bp.route('/<int:season_id>')
@login_required
def detail(season_id):
    db = get_db()
    season = db.execute(
        "SELECT * FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, session['league_id'])
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('seasons.index'))

    teams = db.execute(
        """SELECT t.team_id, t.team_name,
                  p1.last_name AS player1_last, p2.last_name AS player2_last,
                  p1.first_name AS player1_first, p2.first_name AS player2_first
           FROM teams t
           LEFT JOIN players p1 ON t.player1_id = p1.player_id
           LEFT JOIN players p2 ON t.player2_id = p2.player_id
           WHERE t.season_id = %s AND t.league_id = %s
           ORDER BY p1.last_name, p2.last_name""",
        (season_id, session['league_id'])
    ).fetchall()

    return render_template('seasons/detail.html', season=season, teams=teams)
