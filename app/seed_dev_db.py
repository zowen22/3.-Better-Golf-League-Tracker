"""
Dev-only seed script: adds a handful of played rounds — covering the edge
cases this project's scoring/handicap engine keeps needing debugged — on
top of the built-in "Shankapotamus Golf League" demo league that init_db.py
already creates on a fresh DB.

Targets the local Postgres dev database provisioned by
.claude/hooks/session-start.sh (postgresql://golf_dev:...@localhost/
golf_league_dev) — not SQLite. database.py's SQLite fallback only ever
worked for schema creation; every route uses %s placeholders, which raw
sqlite3 rejects, so the app cannot actually run against SQLite as-is.

Deliberately drives the real /scores/enter route via Flask's test client
(not raw SQL inserts for scorecards/hole_scores) so every round is scored
through the actual _process_scores → _process_absences → chronological
handicap rebuild pipeline — the same code path a real admin's browser
would hit. This also means it doubles as a smoke test: if this script
fails, something in that pipeline is broken.

Usage (from repo root, with the app's deps installed and DATABASE_URL set
to the local dev DB — see .claude/hooks/session-start.sh):
    python3 app/seed_dev_db.py

Idempotent: skips scenarios whose round already exists (matched by
matchup_id) so re-running after the DB has already been seeded is a no-op,
not a duplicate-data generator. Refuses to run unless DATABASE_URL clearly
points at the local dev DB (host is localhost/127.0.0.1 and the db name
is golf_league_dev) — a safety rail against ever seeding fake data into a
real Supabase database if DATABASE_URL were pointed there by mistake.

Scenarios seeded (Team "The Duffers" [players Wrist Flipper(15) + Hosel
Rocket(10)] vs Team "Fairway Felons" [Chip Yippsalot(1) + Sandy
Trapper(3)]), all in Season 1 as new matchups (IDs 9001-9005, week 19-23,
well past the base seed's 90 scheduled matchups so nothing collides):

  9001 (wk19): normal complete round, no edge cases — baseline sanity.
  9002 (wk20): Wrist Flipper (15) absent, no sub — ghost-score synthesis.
  9003 (wk21): Wrist Flipper (15) absent again, "+ New Sub" free-text
               creates a brand-new sub player with no starting_handicap —
               that sub's ROUND 1 (pre-eligibility temp handicap).
  9004 (wk22): same sub plays again (selected from the dropdown this
               time, not free-text) — their ROUND 2, the eligibility-
               crossing round the d8da205 fix addresses (self-only temp
               handicap, not the stale pre-round-1 entering value).
  9005 (wk23): Hosel Rocket (10) gets a manual playing-handicap override
               that differs from their computed default — exercises the
               Matrix/History override-dot display and the override-vs-
               provisional marker precedence in score entry.
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

_db_url = os.environ.get('DATABASE_URL', '').strip()
_looks_like_local_dev_db = _db_url and (
    ('localhost' in _db_url or '127.0.0.1' in _db_url) and _db_url.rstrip('/').endswith('golf_league_dev')
)
if not _looks_like_local_dev_db:
    print("Refusing to run: DATABASE_URL is not set to the local dev DB "
          "(expected host localhost/127.0.0.1, db name golf_league_dev). "
          "This is a safety rail against ever seeding fake data into a real "
          "database. Run .claude/hooks/session-start.sh first, or set "
          "DATABASE_URL to postgresql://golf_dev:golf_dev_local@localhost:5432/golf_league_dev",
          file=sys.stderr)
    sys.exit(1)

from app import app as flask_app  # noqa: E402  (triggers init_db() — base seed)
from database import get_db  # noqa: E402

flask_app.config['WTF_CSRF_ENABLED'] = False

LEAGUE_ID = 1
SEASON_ID = 1
COURSE_ID = 1
TEE_ID    = 1

# team1 = "The Duffers" (players 15, 10); team2 = "Fairway Felons" (players 1, 12)
TEAM1_ID, TEAM1_P1, TEAM1_P2 = 1, 15, 10
TEAM2_ID, TEAM2_P1, TEAM2_P2 = 2, 1, 12

# 9-hole layout matching the seeded tee's par_total=36. handicap_index is a
# 1-9 stroke-index permutation (arbitrary but each value used once).
HOLE_PARS    = [4, 4, 3, 5, 4, 4, 3, 5, 4]
HOLE_HCP_IDX = [5, 1, 9, 3, 7, 2, 8, 4, 6]


def ensure_holes(db):
    """Insert the 9 holes for TEE_ID if they aren't there yet (base seed
    creates the tee itself but never any holes for it)."""
    existing = db.execute("SELECT COUNT(*) AS c FROM holes WHERE tee_id = %s", (TEE_ID,)).fetchone()
    if existing['c'] > 0:
        return
    for i, (par, hcp) in enumerate(zip(HOLE_PARS, HOLE_HCP_IDX), start=1):
        db.execute(
            "INSERT INTO holes (tee_id, hole_number, par, handicap_index) VALUES (%s, %s, %s, %s)",
            (TEE_ID, i, par, hcp)
        )
    db.commit()
    print(f"  seeded {len(HOLE_PARS)} holes for tee_id={TEE_ID}")


def ensure_matchup(db, matchup_id, week_num, round_date):
    existing = db.execute("SELECT matchup_id FROM matchups WHERE matchup_id = %s", (matchup_id,)).fetchone()
    if existing:
        return False
    db.execute(
        """INSERT INTO matchups
               (matchup_id, season_id, round_number, week_number, scheduled_date,
                team1_id, team2_id, status, starting_hole, week_type, course_id, tee_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'scheduled', 1, 'Normal', %s, %s)""",
        (matchup_id, SEASON_ID, week_num, week_num, round_date, TEAM1_ID, TEAM2_ID, COURSE_ID, TEE_ID)
    )
    db.commit()
    return True


def scores_for(base_gross_per_hole):
    """{hole_number: gross} for a player who shoots `par + base` every hole."""
    return {i + 1: HOLE_PARS[i] + base_gross_per_hole for i in range(len(HOLE_PARS))}


def submit(client, matchup_id, per_player_scores, absent_pid=None, sub_pid=None,
           sub_new_name=None, hcp_override_pid=None, hcp_override_value=None,
           round_date='2026-07-10'):
    """POST a full score-entry submission for one matchup.

    per_player_scores: {pid: {hole_number: gross}} for every player who has
    a real score this round (an absent player is simply omitted).
    """
    form = {
        'action': 'submit_scores',
        'course_id': str(COURSE_ID),
        'tee_id': str(TEE_ID),
        'loaded_tee_id': str(TEE_ID),
        'round_date': round_date,
    }
    for pid in (TEAM1_P1, TEAM1_P2, TEAM2_P1, TEAM2_P2):
        form[f'absent_{pid}'] = '1' if pid == absent_pid else ''
        form[f'sub_{pid}'] = str(sub_pid) if (pid == absent_pid and sub_pid) else ''
        form[f'sub_new_name_{pid}'] = sub_new_name if (pid == absent_pid and sub_new_name) else ''
        form[f'reason_{pid}'] = ''
        form[f'excused_{pid}'] = ''
        if pid == hcp_override_pid:
            form[f'hcp_override_{pid}'] = str(hcp_override_value)

    score_pid = sub_pid if sub_pid else None  # scores for a NEW sub keyed by orig pid still (form contract)
    for pid, holes in per_player_scores.items():
        for hole_num, gross in holes.items():
            form[f'score_{pid}_{hole_num}'] = str(gross)

    resp = client.post(f'/scores/enter/{matchup_id}', data=form, follow_redirects=False)
    if resp.status_code not in (302, 200):
        raise RuntimeError(f"matchup {matchup_id}: unexpected status {resp.status_code}")
    return resp


def main():
    with flask_app.app_context():
        db = get_db()
        ensure_holes(db)

        with flask_app.test_client() as client:
            with client.session_transaction() as sess:
                sess['league_id']          = LEAGUE_ID
                sess['league_name']        = 'Shankapotamus Golf League'
                sess['role']               = 'league_admin'
                sess['current_season_id']  = SEASON_ID

            # ---- 9001: baseline normal round ----
            if ensure_matchup(db, 9001, 19, '2026-07-05'):
                submit(client, 9001, {
                    TEAM1_P1: scores_for(1),  # bogey golf
                    TEAM1_P2: scores_for(0),  # par golf
                    TEAM2_P1: scores_for(2),
                    TEAM2_P2: scores_for(1),
                }, round_date='2026-07-05')
                print("  9001 (wk19): baseline normal round — done")
            else:
                print("  9001 (wk19): already exists — skipped")

            # ---- 9002: absent, no sub (ghost score) ----
            if ensure_matchup(db, 9002, 20, '2026-07-12'):
                submit(client, 9002, {
                    TEAM1_P2: scores_for(0),
                    TEAM2_P1: scores_for(2),
                    TEAM2_P2: scores_for(1),
                }, absent_pid=TEAM1_P1, round_date='2026-07-12')
                print("  9002 (wk20): absent/no-sub (ghost score) — done")
            else:
                print("  9002 (wk20): already exists — skipped")

            # ---- 9003: absent, "+ New Sub" free-text (sub's round 1, pre-eligibility) ----
            if ensure_matchup(db, 9003, 21, '2026-07-19'):
                # First: save the absence + free-text sub (mirrors the popover's
                # "+ New Sub" flow), so the sub player gets created and the
                # scorecard row for the ORIGINAL player is what carries the sub's
                # scores (per _process_scores's orig_pid fallback contract).
                resp = client.post(f'/scores/enter/{9003}', data={
                    'action': 'save_absences',
                    f'absent_{TEAM1_P1}': '1',
                    f'sub_{TEAM1_P1}': '',
                    f'sub_new_name_{TEAM1_P1}': 'Fillin McSubberson',
                    f'reason_{TEAM1_P1}': '',
                    f'excused_{TEAM1_P1}': '',
                }, follow_redirects=False)
                if resp.status_code not in (302, 200):
                    raise RuntimeError(f"matchup 9003 save_absences: status {resp.status_code}")
                sub_row = db.execute(
                    "SELECT player_id FROM players WHERE first_name='Fillin' AND last_name='McSubberson' AND league_id=%s",
                    (LEAGUE_ID,)
                ).fetchone()
                if not sub_row:
                    raise RuntimeError("matchup 9003: sub player was not created")
                sub_pid = sub_row['player_id']
                submit(client, 9003, {
                    TEAM1_P1: scores_for(3),   # sub's own (rough) round — keyed by orig pid, per form contract
                    TEAM1_P2: scores_for(0),
                    TEAM2_P1: scores_for(2),
                    TEAM2_P2: scores_for(1),
                }, absent_pid=TEAM1_P1, sub_pid=sub_pid, round_date='2026-07-19')
                print(f"  9003 (wk21): new sub 'Fillin McSubberson' (player_id={sub_pid}) round 1 — done")
            else:
                sub_row = db.execute(
                    "SELECT player_id FROM players WHERE first_name='Fillin' AND last_name='McSubberson' AND league_id=%s",
                    (LEAGUE_ID,)
                ).fetchone()
                sub_pid = sub_row['player_id'] if sub_row else None
                print("  9003 (wk21): already exists — skipped")

            # ---- 9004: same sub's round 2 (the eligibility-crossing round) ----
            if sub_pid and ensure_matchup(db, 9004, 22, '2026-07-26'):
                submit(client, 9004, {
                    TEAM1_P1: scores_for(2),
                    TEAM1_P2: scores_for(0),
                    TEAM2_P1: scores_for(2),
                    TEAM2_P2: scores_for(1),
                }, absent_pid=TEAM1_P1, sub_pid=sub_pid, round_date='2026-07-26')
                print(f"  9004 (wk22): sub round 2 (crossing round) — done")
            elif not sub_pid:
                print("  9004 (wk22): skipped — scenario 9003 didn't run this time (sub_pid unknown)")
            else:
                print("  9004 (wk22): already exists — skipped")

            # ---- 9005: manual playing-handicap override ----
            if ensure_matchup(db, 9005, 23, '2026-08-02'):
                from routes.scores import get_player_handicap, calc_playing_handicap
                idx = get_player_handicap(db, TEAM1_P2, league_id=LEAGUE_ID)
                default_ph = calc_playing_handicap(idx, 90.0, 18.0)
                override_val = default_ph + 7
                submit(client, 9005, {
                    TEAM1_P1: scores_for(1),
                    TEAM1_P2: scores_for(0),
                    TEAM2_P1: scores_for(2),
                    TEAM2_P2: scores_for(1),
                }, hcp_override_pid=TEAM1_P2, hcp_override_value=override_val, round_date='2026-08-02')
                print(f"  9005 (wk23): manual hcp override on player {TEAM1_P2} "
                      f"({default_ph} -> {override_val}) — done")
            else:
                print("  9005 (wk23): already exists — skipped")

    print("\nSeed complete. Log in with league_id='1' / admin password from the "
          "seeded league (or use the same session-bypass technique this script "
          "uses if you're driving the app programmatically).")


if __name__ == '__main__':
    main()
