"""
Email / SMTP configuration and sending.

Routes (all admin-only):
  GET  /admin/email               — settings + test send + blast UI
  POST /admin/email/save          — save SMTP config
  POST /admin/email/test          — send a test email
  POST /admin/email/blast         — manual blast to all active players with emails

Public helpers (imported by other blueprints):
  send_league_email(league_id, to_emails, subject, html_body)
      — returns (sent_count, error_message_or_None)
  send_announcement_email(db, league_id, announcement_message, ann_type)
      — fires if email_on_announcement is set; no-op otherwise
  send_round_posted_email(db, league_id, season_id, week_label)
      — fires if email_on_round_posted is set; no-op otherwise
"""

import smtplib, ssl, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from routes.auth import admin_required
from database import get_db

log = logging.getLogger(__name__)

bp = Blueprint('email_config', __name__, url_prefix='/admin/email')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_email_config(db, league_id):
    """Return the email-related columns from leagues as a plain dict."""
    row = db.execute(
        """SELECT league_name,
                  email_enabled, smtp_host, smtp_port, smtp_user, smtp_password,
                  smtp_from_email, smtp_from_name, smtp_use_tls,
                  email_on_announcement, email_on_round_posted, email_on_sub_assigned
           FROM leagues WHERE league_id = %s""",
        (league_id,)
    ).fetchone()
    if not row:
        return {}
    return dict(row)


def _get_player_emails(db, league_id):
    """Return list of (first_name, last_name, email) for active players with a non-null email
    who have NOT opted out of emails (email_opt_out = 0 or column absent)."""
    # Use COALESCE so query works both before and after migrate_email_opt_out.py is run
    rows = db.execute(
        """SELECT first_name, last_name, email
           FROM players
           WHERE league_id = %s AND active = 1
             AND email IS NOT NULL AND trim(email) != ''
             AND COALESCE(email_opt_out, 0) = 0""",
        (league_id,)
    ).fetchall()
    return [(r['first_name'], r['last_name'], r['email']) for r in rows]


def send_league_email(league_id, to_emails, subject, html_body, text_body=None):
    """
    Send an email to a list of addresses using the league's SMTP config.

    Parameters
    ----------
    league_id : int
    to_emails : list[str]   — recipient addresses
    subject   : str
    html_body : str         — HTML email body
    text_body : str | None  — plain-text fallback (auto-generated from html if None)

    Returns
    -------
    (sent_count: int, error: str | None)
    """
    if not to_emails:
        return 0, None

    db = get_db()
    cfg = _get_email_config(db, league_id)

    if not cfg.get('email_enabled'):
        return 0, 'Email is disabled for this league.'
    if not cfg.get('smtp_host') or not cfg.get('smtp_from_email'):
        return 0, 'SMTP is not configured (missing host or from-address).'

    smtp_host     = cfg['smtp_host'].strip()
    smtp_port     = int(cfg['smtp_port'] or 587)
    smtp_user     = (cfg['smtp_user'] or '').strip()
    smtp_password = (cfg['smtp_password'] or '').strip()
    from_email    = cfg['smtp_from_email'].strip()
    from_name     = (cfg['smtp_from_name'] or cfg['league_name'] or 'Golf League').strip()
    use_tls       = bool(cfg.get('smtp_use_tls', 1))

    from_header = f'"{from_name}" <{from_email}>'

    if text_body is None:
        import re
        text_body = re.sub(r'<[^>]+>', '', html_body)

    sent = 0
    errors = []

    try:
        if use_tls and smtp_port == 465:
            ctx = ssl.create_default_context()
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            if use_tls:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()

        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)

        for addr in to_emails:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From']    = from_header
                msg['To']      = addr
                msg.attach(MIMEText(text_body, 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
                server.sendmail(from_email, [addr], msg.as_string())
                sent += 1
            except Exception as e:
                errors.append(f'{addr}: {e}')
                log.warning('Failed to send email to %s: %s', addr, e)

        server.quit()

    except Exception as e:
        log.error('SMTP connection error: %s', e)
        return sent, str(e)

    if errors:
        return sent, f'Sent {sent}, failed: ' + '; '.join(errors[:5])
    return sent, None


def _build_html_email(league_name, heading, body_html, footer_note=''):
    """Wrap content in a minimal branded HTML email template."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 20px; }}
  .wrapper {{ max-width: 600px; margin: 0 auto; background: #fff;
              border-radius: 8px; overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,.1); }}
  .header  {{ background: #2d6a4f; color: #fff; padding: 20px 24px; }}
  .header h2 {{ margin: 0; font-size: 20px; }}
  .header p  {{ margin: 4px 0 0; font-size: 13px; opacity: .8; }}
  .body    {{ padding: 24px; color: #333; line-height: 1.6; }}
  .footer  {{ background: #f0f0f0; padding: 12px 24px; font-size: 11px; color: #888; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h2>{league_name}</h2>
    <p>{heading}</p>
  </div>
  <div class="body">
    {body_html}
  </div>
  <div class="footer">
    {footer_note or f'You are receiving this because you are a member of {league_name}.'}
  </div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public trigger helpers (called from other blueprints)
# ---------------------------------------------------------------------------

def send_announcement_email(db, league_id, announcement_message, ann_type='general'):
    """Fire an email to all players when a new announcement is posted."""
    try:
        cfg = _get_email_config(db, league_id)
        if not cfg.get('email_enabled') or not cfg.get('email_on_announcement'):
            return
        recipients = [e for _, _, e in _get_player_emails(db, league_id)]
        if not recipients:
            return
        league_name = cfg.get('league_name', 'Golf League')
        type_label  = ann_type.replace('_', ' ').title()
        subject     = f"[{league_name}] New Announcement: {type_label}"
        body_html   = f"<p><strong>New league announcement ({type_label}):</strong></p><p>{announcement_message}</p>"
        html        = _build_html_email(league_name, f'New Announcement — {type_label}', body_html)
        send_league_email(league_id, recipients, subject, html)
    except Exception as e:
        log.warning('send_announcement_email failed: %s', e)


def send_round_posted_email(db, league_id, season_id, week_label):
    """Fire an email to all players when scores for a round are posted."""
    try:
        cfg = _get_email_config(db, league_id)
        if not cfg.get('email_enabled') or not cfg.get('email_on_round_posted'):
            return
        recipients = [e for _, _, e in _get_player_emails(db, league_id)]
        if not recipients:
            return
        league_name = cfg.get('league_name', 'Golf League')
        subject     = f"[{league_name}] Scores Posted — {week_label}"
        body_html   = f"<p>Scores for <strong>{week_label}</strong> have been posted.</p><p>Log in to view the full standings and scorecards.</p>"
        html        = _build_html_email(league_name, f'Scores Posted — {week_label}', body_html)
        send_league_email(league_id, recipients, subject, html)
    except Exception as e:
        log.warning('send_round_posted_email failed: %s', e)


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

@bp.route('/')
@admin_required
def settings():
    db = get_db()
    league_id = session['league_id']
    cfg = _get_email_config(db, league_id)
    player_emails = _get_player_emails(db, league_id)
    players_with_email    = len(player_emails)
    players_without_email = db.execute(
        "SELECT COUNT(*) FROM players WHERE league_id = %s AND active = 1 AND (email IS NULL OR trim(email) = '')",
        (league_id,)
    ).fetchone()[0]
    seasons = db.execute(
        "SELECT season_id, season_name FROM seasons WHERE league_id = %s ORDER BY season_id DESC",
        (league_id,)
    ).fetchall()
    current_season_id = session.get('current_season_id')
    return render_template('admin/email_settings.html',
                           cfg=cfg,
                           players_with_email=players_with_email,
                           players_without_email=players_without_email,
                           seasons=seasons,
                           current_season_id=current_season_id)


@bp.route('/save', methods=['POST'])
@admin_required
def save():
    db = get_db()
    league_id = session['league_id']

    email_enabled        = 1 if request.form.get('email_enabled') else 0
    smtp_host            = request.form.get('smtp_host', '').strip()
    try:
        smtp_port = int(request.form.get('smtp_port') or 587)
    except (ValueError, TypeError):
        smtp_port = 587
    smtp_user            = request.form.get('smtp_user', '').strip()
    smtp_password_raw    = request.form.get('smtp_password', '')
    smtp_from_email      = request.form.get('smtp_from_email', '').strip()
    smtp_from_name       = request.form.get('smtp_from_name', '').strip()
    smtp_use_tls         = 1 if request.form.get('smtp_use_tls') else 0
    email_on_ann         = 1 if request.form.get('email_on_announcement') else 0
    email_on_round       = 1 if request.form.get('email_on_round_posted') else 0
    email_on_sub         = 1 if request.form.get('email_on_sub_assigned') else 0

    # Only update password if a new one was typed (non-empty)
    if smtp_password_raw.strip():
        db.execute(
            """UPDATE leagues SET
               email_enabled=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s, smtp_password=%s,
               smtp_from_email=%s, smtp_from_name=%s, smtp_use_tls=%s,
               email_on_announcement=%s, email_on_round_posted=%s, email_on_sub_assigned=%s
               WHERE league_id=%s""",
            (email_enabled, smtp_host, smtp_port, smtp_user, smtp_password_raw,
             smtp_from_email, smtp_from_name, smtp_use_tls,
             email_on_ann, email_on_round, email_on_sub, league_id)
        )
    else:
        db.execute(
            """UPDATE leagues SET
               email_enabled=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s,
               smtp_from_email=%s, smtp_from_name=%s, smtp_use_tls=%s,
               email_on_announcement=%s, email_on_round_posted=%s, email_on_sub_assigned=%s
               WHERE league_id=%s""",
            (email_enabled, smtp_host, smtp_port, smtp_user,
             smtp_from_email, smtp_from_name, smtp_use_tls,
             email_on_ann, email_on_round, email_on_sub, league_id)
        )
    db.commit()
    flash('Email settings saved.', 'success')
    return redirect(url_for('email_config.settings'))


@bp.route('/test', methods=['POST'])
@admin_required
def test_send():
    league_id = session['league_id']
    to_addr   = request.form.get('test_to', '').strip()
    if not to_addr:
        flash('Please enter a recipient address.', 'error')
        return redirect(url_for('email_config.settings'))

    db = get_db()
    cfg = _get_email_config(db, league_id)
    league_name = cfg.get('league_name', 'Golf League')
    subject   = f"[{league_name}] Test Email"
    body_html = "<p>This is a test email from your BetterGolfLeagueTracker app.</p><p>If you received this, your SMTP settings are working correctly! ✅</p>"
    html      = _build_html_email(league_name, 'SMTP Test', body_html, footer_note='This is a test message sent by a league administrator.')

    sent, err = send_league_email(league_id, [to_addr], subject, html)
    if err and sent == 0:
        flash(f'Send failed: {err}', 'error')
    elif err:
        flash(f'Sent with warnings: {err}', 'warning')
    else:
        flash(f'Test email sent to {to_addr}.', 'success')
    return redirect(url_for('email_config.settings'))


@bp.route('/blast', methods=['POST'])
@admin_required
def blast():
    league_id = session['league_id']
    subject   = request.form.get('blast_subject', '').strip()
    body_text = request.form.get('blast_body', '').strip()

    if not subject or not body_text:
        flash('Subject and message body are required.', 'error')
        return redirect(url_for('email_config.settings'))

    db = get_db()
    cfg = _get_email_config(db, league_id)
    league_name = cfg.get('league_name', 'Golf League')
    recipients  = [e for _, _, e in _get_player_emails(db, league_id)]

    if not recipients:
        flash('No players have email addresses on file.', 'warning')
        return redirect(url_for('email_config.settings'))

    # Convert newlines to <br> for HTML
    import html as _html
    body_html_content = '<p>' + _html.escape(body_text).replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'
    full_html = _build_html_email(league_name, subject, body_html_content)

    sent, err = send_league_email(league_id, recipients, subject, full_html, text_body=body_text)
    if err and sent == 0:
        flash(f'Blast failed: {err}', 'error')
    elif err:
        flash(f'Sent {sent} email(s) with warnings: {err}', 'warning')
    else:
        flash(f'Blast sent to {sent} player(s).', 'success')
    return redirect(url_for('email_config.settings'))


# ---------------------------------------------------------------------------
# Weekly digest helpers
# ---------------------------------------------------------------------------

def _build_digest_data(db, league_id, season_id):
    """
    Return a dict with standings, recent_results, and upcoming_schedule
    for use in the digest email.
    """
    # -- Standings: all teams sorted by total points desc --
    standings_rows = db.execute(
        """SELECT t.team_id,
                  p1.first_name AS p1_first, p1.last_name AS p1_last,
                  p2.first_name AS p2_first, p2.last_name AS p2_last,
                  t.team_name AS nickname,
                  COALESCE(SUM(mr.total_points), 0) AS total_pts,
                  COUNT(DISTINCT CASE WHEN m.status='completed' THEN m.matchup_id END) AS rounds
           FROM teams t
           LEFT JOIN players p1       ON t.player1_id  = p1.player_id
           LEFT JOIN players p2       ON t.player2_id  = p2.player_id
           LEFT JOIN match_results mr ON mr.team_id    = t.team_id
           LEFT JOIN matchups m       ON mr.matchup_id = m.matchup_id
                                     AND m.season_id   = %s
           WHERE t.season_id = %s AND t.league_id = %s
           GROUP BY t.team_id
           ORDER BY total_pts DESC""",
        (season_id, season_id, league_id)
    ).fetchall()

    standings = []
    for i, row in enumerate(standings_rows):
        name = row['nickname'] if row['nickname'] else f"{row['p1_last']} / {row['p2_last']}"
        standings.append({
            'rank': i + 1,
            'name': name,
            'pts': row['total_pts'],
            'rounds': row['rounds'],
        })

    # -- Most recent completed week --
    last_week = db.execute(
        """SELECT week_number, scheduled_date
           FROM matchups
           WHERE season_id = %s AND status = 'completed' AND is_bye = 0
           ORDER BY week_number DESC
           LIMIT 1""",
        (season_id,)
    ).fetchone()

    recent_results = []
    recent_week_label = None
    if last_week:
        wn = last_week['week_number']
        recent_week_label = f"Week {wn}"
        if last_week['scheduled_date']:
            recent_week_label += f" ({last_week['scheduled_date']})"
        matchups = db.execute(
            """SELECT m.matchup_id, m.is_bye,
                      t1.team_name AS t1_nick,
                      p1a.last_name AS p1a_last, p1b.last_name AS p1b_last,
                      t2.team_name AS t2_nick,
                      p2a.last_name AS p2a_last, p2b.last_name AS p2b_last
               FROM matchups m
               LEFT JOIN teams   t1  ON m.team1_id    = t1.team_id
               LEFT JOIN teams   t2  ON m.team2_id    = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
               LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
               ORDER BY m.matchup_id""",
            (season_id, wn)
        ).fetchall()
        for m in matchups:
            t1_name = m['t1_nick'] if m['t1_nick'] else f"{m['p1a_last'] or ''} / {m['p1b_last'] or ''}"
            t2_name = m['t2_nick'] if m['t2_nick'] else f"{m['p2a_last'] or ''} / {m['p2b_last'] or ''}"
            # Get match result totals
            results = db.execute(
                """SELECT mr.team_id, SUM(mr.total_points) AS pts
                   FROM match_results mr
                   WHERE mr.matchup_id = %s
                   GROUP BY mr.team_id""",
                (m['matchup_id'],)
            ).fetchall()
            pts_map = {r['team_id']: r['pts'] for r in results}
            # Find team ids
            t1_row = db.execute("SELECT team_id FROM teams WHERE team_name=%s AND season_id=%s", (m['t1_nick'], season_id)).fetchone() if m['t1_nick'] else None
            # Use match results directly from matchup
            mr_rows = db.execute(
                """SELECT mr.team_id, mr.total_points,
                          t.team_name, p1.last_name AS p1l, p2.last_name AS p2l
                   FROM match_results mr
                   JOIN teams t ON mr.team_id = t.team_id
                   LEFT JOIN players p1 ON t.player1_id = p1.player_id
                   LEFT JOIN players p2 ON t.player2_id = p2.player_id
                   WHERE mr.matchup_id = %s""",
                (m['matchup_id'],)
            ).fetchall()
            if len(mr_rows) == 2:
                a, b = mr_rows[0], mr_rows[1]
                a_name = a['team_name'] if a['team_name'] else f"{a['p1l']} / {a['p2l']}"
                b_name = b['team_name'] if b['team_name'] else f"{b['p1l']} / {b['p2l']}"
                recent_results.append({
                    'matchup': f"{a_name} vs {b_name}",
                    'score': f"{a['total_points']} – {b['total_points']}",
                })
            else:
                recent_results.append({
                    'matchup': f"{t1_name} vs {t2_name}",
                    'score': '—',
                })

    # -- Next upcoming (non-completed) week --
    next_week = db.execute(
        """SELECT week_number, scheduled_date
           FROM matchups
           WHERE season_id = %s AND status != 'completed'
             AND is_bye = 0
           ORDER BY week_number ASC
           LIMIT 1""",
        (season_id,)
    ).fetchone()

    upcoming = []
    upcoming_label = None
    if next_week:
        nwn = next_week['week_number']
        upcoming_label = f"Week {nwn}"
        if next_week['scheduled_date']:
            upcoming_label += f" — {next_week['scheduled_date']}"
        nxt_matchups = db.execute(
            """SELECT m.matchup_id, m.is_bye, m.tee_time,
                      t1.team_name AS t1_nick,
                      p1a.last_name AS p1a_last, p1b.last_name AS p1b_last,
                      t2.team_name AS t2_nick,
                      p2a.last_name AS p2a_last, p2b.last_name AS p2b_last
               FROM matchups m
               LEFT JOIN teams   t1  ON m.team1_id    = t1.team_id
               LEFT JOIN teams   t2  ON m.team2_id    = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
               LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
               ORDER BY m.matchup_id""",
            (season_id, nwn)
        ).fetchall()
        for m in nxt_matchups:
            t1_name = m['t1_nick'] if m['t1_nick'] else f"{m['p1a_last'] or ''} / {m['p1b_last'] or ''}"
            t2_name = m['t2_nick'] if m['t2_nick'] else f"{m['p2a_last'] or ''} / {m['p2b_last'] or ''}"
            entry = {'matchup': f"{t1_name} vs {t2_name}"}
            if m['tee_time']:
                entry['matchup'] += f"  ({m['tee_time']})"
            upcoming.append(entry)

    return {
        'standings': standings,
        'recent_results': recent_results,
        'recent_week_label': recent_week_label,
        'upcoming': upcoming,
        'upcoming_label': upcoming_label,
    }


def _build_digest_html(league_name, season_name, digest, app_url=''):
    """Build the full HTML body for a weekly digest email."""
    # Standings table
    stnd_rows = ''
    for row in digest['standings'][:10]:
        stnd_rows += (
            f'<tr>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;font-weight:bold">{row["rank"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee">{row["name"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right">{row["pts"]}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:#666">{row["rounds"]}</td>'
            f'</tr>'
        )

    standings_section = ''
    if stnd_rows:
        standings_section = f'''
<h3 style="color:#2d6a4f;margin:20px 0 8px">📊 Current Standings — {season_name}</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px">
  <thead>
    <tr style="background:#f4f4f4">
      <th style="padding:6px 10px;text-align:left">#</th>
      <th style="padding:6px 10px;text-align:left">Team</th>
      <th style="padding:6px 10px;text-align:right">Pts</th>
      <th style="padding:6px 10px;text-align:right">Rounds</th>
    </tr>
  </thead>
  <tbody>{stnd_rows}</tbody>
</table>'''

    # Recent results
    results_section = ''
    if digest['recent_results']:
        result_rows = ''.join(
            f'<tr>'
            f'<td style="padding:5px 10px;border-bottom:1px solid #eee">{r["matchup"]}</td>'
            f'<td style="padding:5px 10px;border-bottom:1px solid #eee;text-align:right;font-weight:bold">{r["score"]}</td>'
            f'</tr>'
            for r in digest['recent_results']
        )
        results_section = f'''
<h3 style="color:#2d6a4f;margin:20px 0 8px">🏌️ Recent Results — {digest["recent_week_label"]}</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px">
  <tbody>{result_rows}</tbody>
</table>'''

    # Upcoming schedule
    upcoming_section = ''
    if digest['upcoming']:
        upcoming_rows = ''.join(
            f'<tr><td style="padding:5px 10px;border-bottom:1px solid #eee">{u["matchup"]}</td></tr>'
            for u in digest['upcoming']
        )
        upcoming_section = f'''
<h3 style="color:#2d6a4f;margin:20px 0 8px">📅 Upcoming — {digest["upcoming_label"]}</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px">
  <tbody>{upcoming_rows}</tbody>
</table>'''

    body = f'''
<p style="margin:0 0 12px">Here is your weekly league digest for <strong>{season_name}</strong>.</p>
{standings_section}
{results_section}
{upcoming_section}
'''
    if app_url:
        body += f'<p style="margin-top:20px"><a href="{app_url}" style="color:#2d6a4f">View full league →</a></p>'

    return _build_html_email(league_name, f'Weekly Digest — {season_name}', body)


# ---------------------------------------------------------------------------
# Digest route
# ---------------------------------------------------------------------------

@bp.route('/digest', methods=['POST'])
@admin_required
def send_digest():
    league_id  = session['league_id']
    season_id  = request.form.get('digest_season_id', type=int)
    app_url    = request.form.get('app_url', '').strip()

    if not season_id:
        flash('Please select a season for the digest.', 'error')
        return redirect(url_for('email_config.settings'))

    db = get_db()
    cfg = _get_email_config(db, league_id)

    if not cfg.get('email_enabled'):
        flash('Email is disabled. Enable it in SMTP settings first.', 'error')
        return redirect(url_for('email_config.settings'))

    season = db.execute(
        "SELECT season_name FROM seasons WHERE season_id = %s AND league_id = %s",
        (season_id, league_id)
    ).fetchone()
    if not season:
        flash('Season not found.', 'error')
        return redirect(url_for('email_config.settings'))

    recipients = [e for _, _, e in _get_player_emails(db, league_id)]
    if not recipients:
        flash('No players have email addresses on file.', 'warning')
        return redirect(url_for('email_config.settings'))

    digest    = _build_digest_data(db, league_id, season_id)
    league_name = cfg.get('league_name', 'Golf League')
    season_name = season['season_name']
    html      = _build_digest_html(league_name, season_name, digest, app_url)
    subject   = f"[{league_name}] Weekly Digest — {season_name}"

    sent, err = send_league_email(league_id, recipients, subject, html)
    if err and sent == 0:
        flash(f'Digest failed: {err}', 'error')
    elif err:
        flash(f'Digest sent to {sent} player(s) with warnings: {err}', 'warning')
    else:
        flash(f'Weekly digest sent to {sent} player(s).', 'success')
    return redirect(url_for('email_config.settings'))


def send_player_scorecard_emails(db, league_id, week_label, player_summaries, scorecard_url=None):
    """
    Send personalized round-result emails to each player in a matchup.

    player_summaries: list of dicts, one per player:
        {player_id, name, gross_total, net_total, total_pts,
         opp_name, opp_gross, opp_pts, role}
    scorecard_url: absolute URL to the scorecard page (optional).
    Only fires when email_on_round_posted is enabled.
    """
    try:
        cfg = _get_email_config(db, league_id)
        if not cfg.get('email_enabled') or not cfg.get('email_on_round_posted'):
            return
        league_name = cfg.get('league_name', 'Golf League')

        # Build player_id -> email lookup from the DB (skip global + round-result opt-outs)
        email_rows = db.execute(
            """SELECT player_id, email FROM players
               WHERE league_id = %s AND active = 1
                 AND email IS NOT NULL AND trim(email) != ''
                 AND COALESCE(email_opt_out, 0) = 0
                 AND COALESCE(email_opt_out_round_results, 0) = 0""",
            (league_id,)
        ).fetchall()
        email_map = {r['player_id']: r['email'] for r in email_rows}

        for p in player_summaries:
            addr = email_map.get(p['player_id'])
            if not addr:
                continue

            pts_str   = f"{p['total_pts']:.1f}".rstrip('0').rstrip('.')
            opp_pts   = f"{p['opp_pts']:.1f}".rstrip('0').rstrip('.')
            result    = 'WIN' if p['total_pts'] > p['opp_pts'] else ('TIE' if p['total_pts'] == p['opp_pts'] else 'LOSS')
            result_color = {'WIN': '#2d6a4f', 'TIE': '#888', 'LOSS': '#c0392b'}[result]

            scorecard_link = (
                f'<p><a href="{scorecard_url}" '
                f'style="color:#2d6a4f;">View full scorecard →</a></p>'
            ) if scorecard_url else ''

            body_html = f"""
<p>Hi <strong>{p['name']}</strong>,</p>
<p>Here are your results for <strong>{week_label}</strong>:</p>

<table style="border-collapse:collapse;margin:16px 0;font-size:14px;">
  <tr>
    <th style="text-align:left;padding:6px 12px 6px 0;border-bottom:2px solid #2d6a4f;color:#2d6a4f;">Player</th>
    <th style="text-align:center;padding:6px 12px;border-bottom:2px solid #2d6a4f;color:#2d6a4f;">Gross</th>
    <th style="text-align:center;padding:6px 12px;border-bottom:2px solid #2d6a4f;color:#2d6a4f;">Net</th>
    <th style="text-align:center;padding:6px 12px;border-bottom:2px solid #2d6a4f;color:#2d6a4f;">Pts</th>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:8px 12px 8px 0;font-weight:700;">{p['name']} <em style="font-weight:400;color:#888;">(you)</em></td>
    <td style="text-align:center;padding:8px 12px;">{p['gross_total']}</td>
    <td style="text-align:center;padding:8px 12px;">{p['net_total']}</td>
    <td style="text-align:center;padding:8px 12px;font-weight:700;color:{result_color};">{pts_str}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px 8px 0;">{p['opp_name']}</td>
    <td style="text-align:center;padding:8px 12px;">{p['opp_gross']}</td>
    <td style="text-align:center;padding:8px 12px;color:#888;">{p['opp_net']}</td>
    <td style="text-align:center;padding:8px 12px;color:#888;">{opp_pts}</td>
  </tr>
</table>

<p style="font-size:16px;font-weight:700;color:{result_color};">
  Result: {result} &nbsp; ({pts_str} pts)
</p>
<p style="color:#888;font-size:12px;">Flight {p['role']} &nbsp;·&nbsp; {week_label}</p>
{scorecard_link}
"""
            subject = f"[{league_name}] Your {week_label} Results — {result} ({pts_str} pts)"
            html    = _build_html_email(league_name, f'Round Results — {week_label}', body_html)
            try:
                send_league_email(league_id, [addr], subject, html)
            except Exception:
                pass
    except Exception:
        pass


def send_round_reminder_emails(db, league_id, season_id, week_number):
    """
    Send personalized pre-round reminder emails to every player in every
    non-bye matchup for the given week.

    Returns (sent_count, error_str_or_None).
    Silently skips players with no email on file.
    Fires regardless of email_on_round_posted setting — this is admin-triggered.
    """
    try:
        cfg = _get_email_config(db, league_id)
        if not cfg.get('email_enabled'):
            return 0, 'Email is not enabled. Configure SMTP in Email Settings first.'
        league_name = cfg.get('league_name', 'Golf League')

        # Pull all non-bye matchups for the week with full details
        matchups = db.execute(
            """SELECT m.matchup_id, m.scheduled_date, m.tee_time, m.starting_hole,
                      m.week_number,
                      c.course_name, te.tee_name, te.tee_color,
                      -- Team 1
                      t1.team_name AS t1_name,
                      p1a.player_id AS p1a_id, p1a.first_name AS p1a_first, p1a.last_name AS p1a_last, p1a.email AS p1a_email,
                      p1b.player_id AS p1b_id, p1b.first_name AS p1b_first, p1b.last_name AS p1b_last, p1b.email AS p1b_email,
                      -- Team 2
                      t2.team_name AS t2_name,
                      p2a.player_id AS p2a_id, p2a.first_name AS p2a_first, p2a.last_name AS p2a_last, p2a.email AS p2a_email,
                      p2b.player_id AS p2b_id, p2b.first_name AS p2b_first, p2b.last_name AS p2b_last, p2b.email AS p2b_email
               FROM matchups m
               LEFT JOIN courses c  ON m.course_id = c.course_id
               LEFT JOIN tees   te  ON m.tee_id    = te.tee_id
               LEFT JOIN teams  t1  ON m.team1_id  = t1.team_id
               LEFT JOIN teams  t2  ON m.team2_id  = t2.team_id
               LEFT JOIN players p1a ON t1.player1_id = p1a.player_id
               LEFT JOIN players p1b ON t1.player2_id = p1b.player_id
               LEFT JOIN players p2a ON t2.player1_id = p2a.player_id
               LEFT JOIN players p2b ON t2.player2_id = p2b.player_id
               WHERE m.season_id = %s AND m.week_number = %s AND m.is_bye = 0
               ORDER BY m.tee_time ASC NULLS LAST, m.matchup_id ASC""",
            (season_id, week_number)
        ).fetchall()

        if not matchups:
            return 0, 'No matchups found for this week.'

        week_label = f'Week {week_number}'

        total_sent = 0
        total_errors = []

        for m in matchups:
            # Build team labels
            t1_label = m['t1_name'] or f"{m['p1a_last'] or ''} / {m['p1b_last'] or ''}".strip(' /')
            t2_label = m['t2_name'] or f"{m['p2a_last'] or ''} / {m['p2b_last'] or ''}".strip(' /')

            # Course / tee info line
            course_line = m['course_name'] or 'Course TBD'
            if m['tee_name']:
                course_line += f" — {m['tee_name']} Tees"

            # Tee time + hole
            tee_time_str = m['tee_time'] or 'TBD'
            hole_str = f"Hole {m['starting_hole']}" if m['starting_hole'] and m['starting_hole'] != 1 else 'Hole 1'

            # Date
            date_str = m['scheduled_date'] or 'Date TBD'

            # Build list of (player, their_team_label, opp_team_label, role, email)
            players_to_notify = [
                (m['p1a_first'], m['p1a_last'], m['p1a_email'], t1_label, t2_label, 'A'),
                (m['p1b_first'], m['p1b_last'], m['p1b_email'], t1_label, t2_label, 'B'),
                (m['p2a_first'], m['p2a_last'], m['p2a_email'], t2_label, t1_label, 'A'),
                (m['p2b_first'], m['p2b_last'], m['p2b_email'], t2_label, t1_label, 'B'),
            ]

            # Build set of opted-out player emails for this matchup
            optout_ids = set()
            try:
                oo_rows = db.execute(
                    """SELECT player_id FROM players
                       WHERE league_id = %s AND player_id IN (%s,%s,%s,%s)
                         AND (COALESCE(email_opt_out, 0) = 1
                              OR COALESCE(email_opt_out_reminders, 0) = 1)""",
                    (league_id, m['p1a_id'] or 0, m['p1b_id'] or 0,
                     m['p2a_id'] or 0, m['p2b_id'] or 0)
                ).fetchall()
                optout_ids = {r['player_id'] for r in oo_rows}
            except Exception:
                pass

            # Rebuild with player_id included
            players_to_notify = [
                (m['p1a_id'], m['p1a_first'], m['p1a_last'], m['p1a_email'], t1_label, t2_label, 'A'),
                (m['p1b_id'], m['p1b_first'], m['p1b_last'], m['p1b_email'], t1_label, t2_label, 'B'),
                (m['p2a_id'], m['p2a_first'], m['p2a_last'], m['p2a_email'], t2_label, t1_label, 'A'),
                (m['p2b_id'], m['p2b_first'], m['p2b_last'], m['p2b_email'], t2_label, t1_label, 'B'),
            ]

            for (pid, first, last, email, my_team, opp_team, role) in players_to_notify:
                if not email or not first:
                    continue
                if pid and pid in optout_ids:
                    continue

                body_html = f"""
<p>Hi <strong>{first}</strong>,</p>
<p>This is a reminder for your upcoming league round:</p>

<table style="border-collapse:collapse;margin:16px 0;font-size:15px;width:100%;max-width:480px;">
  <tr>
    <td style="padding:8px 12px 8px 0;color:#666;width:130px;">📅 Date</td>
    <td style="padding:8px 0;font-weight:600;">{date_str}</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:8px 12px 8px 0;color:#666;">⏰ Tee Time</td>
    <td style="padding:8px 0;font-weight:600;">{tee_time_str}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px 8px 0;color:#666;">🚩 Starting Hole</td>
    <td style="padding:8px 0;font-weight:600;">{hole_str}</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:8px 12px 8px 0;color:#666;">⛳ Course</td>
    <td style="padding:8px 0;font-weight:600;">{course_line}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px 8px 0;color:#666;">🏌️ Your Team</td>
    <td style="padding:8px 0;font-weight:600;">{my_team}</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:8px 12px 8px 0;color:#666;">🆚 Opponent</td>
    <td style="padding:8px 0;font-weight:600;">{opp_team}</td>
  </tr>
  <tr>
    <td style="padding:8px 12px 8px 0;color:#666;">✈️ Flight</td>
    <td style="padding:8px 0;font-weight:600;">Flight {role}</td>
  </tr>
</table>

<p style="color:#888;font-size:12px;">Good luck out there! 🏆</p>
"""
                subject = f"[{league_name}] Reminder: {week_label} — {date_str} at {tee_time_str}"
                html = _build_html_email(league_name, f'{week_label} Round Reminder', body_html)
                sent, err = send_league_email(league_id, [email], subject, html)
                total_sent += sent
                if err:
                    total_errors.append(err)

        err_str = '; '.join(total_errors[:3]) if total_errors else None
        return total_sent, err_str

    except Exception as e:
        log.error('send_round_reminder_emails failed: %s', e)
        return 0, str(e)
