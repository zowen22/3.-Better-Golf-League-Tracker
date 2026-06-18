from flask import Blueprint, jsonify, render_template, request, redirect, url_for, session, flash
import database
from database import get_db
from routes.auth import login_required, admin_required
from datetime import datetime
import config
import urllib.request
import urllib.error
import urllib.parse
import json as _json

bp = Blueprint('courses', __name__, url_prefix='/courses')


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_course_or_404(course_id):
    """Return course row if it belongs to this league (or is a master record), else None."""
    db = get_db()
    course = db.execute(
        """SELECT * FROM courses
           WHERE course_id = %s
             AND (league_id = %s OR league_id IS NULL OR is_master_record = 1)""",
        (course_id, session['league_id'])
    ).fetchone()
    return course


def _get_tees_grouped(db, course_id):
    """Return tees grouped by (tee_name, tee_color, gender).
    Each group dict: {tee_name, tee_color, gender, front: row|None, back: row|None, full: row|None}
    'full' = 18-hole single-tee (nine='full').
    """
    rows = db.execute(
        "SELECT * FROM tees WHERE course_id = %s ORDER BY tee_name, gender, nine",
        (course_id,)
    ).fetchall()
    groups = {}
    for row in rows:
        key = (row['tee_name'], row['tee_color'] or '', row['gender'])
        if key not in groups:
            groups[key] = {'tee_name': row['tee_name'],
                           'tee_color': row['tee_color'],
                           'gender': row['gender'],
                           'front': None, 'back': None, 'full': None}
        nine_val = row['nine']
        if nine_val in ('front', 'back', 'full'):
            groups[key][nine_val] = dict(row)
        else:
            # Fallback: store under 'front' for unknown values
            groups[key]['front'] = dict(row)
    return list(groups.values())


# ── Course list ────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
def index():
    db = get_db()
    courses = db.execute(
        """SELECT c.*,
                  COUNT(DISTINCT t.tee_id) as tee_count
           FROM courses c
           LEFT JOIN tees t ON t.course_id = c.course_id
           WHERE c.league_id = %s OR c.league_id IS NULL OR c.is_master_record = 1
           GROUP BY c.course_id
           ORDER BY c.course_name""",
        (session['league_id'],)
    ).fetchall()
    return render_template('courses/list.html', courses=courses)


# ── Golf Course API proxy + import ─────────────────────────────────────────

_GC_API_BASE  = 'https://api.golfcourseapi.com/v1'
_CACHE_TTL_DAYS    = 90
_MONTHLY_LIMIT     = 45   # per-league hard cap; leaves 5-req buffer on free tier
_THROTTLE_SECONDS  = 30   # minimum gap between API calls per league


def _log_api_request(db, endpoint, response_code):
    """Write one row to api_request_log. Silently swallows errors."""
    try:
        db.execute(
            "INSERT INTO api_request_log (endpoint, league_id, user_id, response_code) "
            "VALUES (%s, %s, %s, %s)",
            (endpoint, session.get('league_id'), session.get('user_id'), response_code)
        )
    except Exception:
        pass


def _monthly_request_count(db, league_id):
    """Count API calls this calendar month for the given league."""
    try:
        row = db.execute(
            "SELECT COUNT(*) AS n FROM api_request_log "
            "WHERE league_id = %s "
            "  AND DATE_TRUNC('month', requested_at) = DATE_TRUNC('month', NOW())",
            (league_id,)
        ).fetchone()
        return row['n'] if row else 0
    except Exception:
        return 0


def _seconds_since_last_request(db, league_id):
    """Seconds since the most recent API call for this league. Returns None if no prior calls."""
    try:
        row = db.execute(
            "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(requested_at)))::int AS secs "
            "FROM api_request_log WHERE league_id = %s",
            (league_id,)
        ).fetchone()
        return row['secs'] if row and row['secs'] is not None else None
    except Exception:
        return None


def _gc_api_get(path, db=None):
    """Make a GET request to golfcourseapi.com. Returns parsed JSON or raises.
    If db is provided, enforces per-league monthly cap and 30-second throttle.
    """
    key = config.GOLFCOURSE_API_KEY
    if not key:
        raise ValueError('GOLFCOURSE_API_KEY not configured.')

    if db is not None:
        league_id = session.get('league_id')

        count = _monthly_request_count(db, league_id)
        if count >= _MONTHLY_LIMIT:
            raise RuntimeError(
                f'Monthly API limit reached ({count}/{_MONTHLY_LIMIT} for your league). '
                'Try again next month or contact support.'
            )

        secs = _seconds_since_last_request(db, league_id)
        if secs is not None and secs < _THROTTLE_SECONDS:
            wait = _THROTTLE_SECONDS - secs
            raise RuntimeError(
                f'Please wait {wait} more second{"s" if wait != 1 else ""} before searching again.'
            )

    req = urllib.request.Request(
        f'{_GC_API_BASE}{path}',
        headers={'Authorization': f'Key {key}'}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode())
        if db is not None:
            _log_api_request(db, path, 200)
        return data
    except urllib.error.HTTPError as e:
        if db is not None:
            _log_api_request(db, path, e.code)
        raise


@bp.route('/api-search')
@admin_required
def api_search():
    """Proxy: search golfcourseapi.com by name and return results as JSON."""
    if not config.GOLFCOURSE_API_KEY:
        return jsonify({'error': 'GOLFCOURSE_API_KEY not set on server.'}), 503
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'courses': []})
    db = get_db()
    try:
        encoded = urllib.parse.quote(query)
        data = _gc_api_get(f'/search?search_query={encoded}', db=db)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 429
    except urllib.error.HTTPError as e:
        return jsonify({'error': f'API error {e.code}'}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    courses = data.get('courses', [])
    for c in courses:
        tees = c.get('tees', {})
        c['tee_count'] = sum(len(v) for v in tees.values() if isinstance(v, list))

    # Surface per-league monthly usage so the UI can warn when nearing the limit
    usage = _monthly_request_count(db, session.get('league_id'))
    return jsonify({'courses': courses, 'monthly_usage': usage, 'monthly_limit': _MONTHLY_LIMIT})


@bp.route('/api-import', methods=['POST'])
@admin_required
def api_import():
    """Fetch a course by API ID and create it (+ tees + holes) in one shot."""
    if not config.GOLFCOURSE_API_KEY:
        flash('GOLFCOURSE_API_KEY not configured.', 'error')
        return redirect(url_for('courses.add'))

    api_id = request.form.get('api_id', type=int)
    if not api_id:
        flash('No course selected.', 'error')
        return redirect(url_for('courses.add'))

    db = get_db()

    # Check cache first (TTL: 90 days)
    data = None
    try:
        cached = db.execute(
            "SELECT response_json, fetched_at FROM course_api_cache WHERE api_course_id = %s",
            (api_id,)
        ).fetchone()
        if cached:
            from datetime import timedelta
            age = datetime.now() - cached['fetched_at'].replace(tzinfo=None)
            if age.days < _CACHE_TTL_DAYS:
                data = _json.loads(cached['response_json'])
    except Exception:
        pass  # Cache miss — fall through to API

    if data is None:
        try:
            data = _gc_api_get(f'/courses/{api_id}', db=db)
            # Store in cache
            try:
                db.execute(
                    "INSERT INTO course_api_cache (api_course_id, response_json, fetched_at) "
                    "VALUES (%s, %s, NOW()) "
                    "ON CONFLICT (api_course_id) DO UPDATE "
                    "SET response_json = EXCLUDED.response_json, fetched_at = NOW()",
                    (api_id, _json.dumps(data))
                )
            except Exception:
                pass  # Cache write failure is non-fatal
        except RuntimeError as e:
            flash(str(e), 'error')
            return redirect(url_for('courses.add'))
        except Exception as e:
            flash(f'API error: {e}', 'error')
            return redirect(url_for('courses.add'))

    c = data.get('course', {})
    loc = c.get('location', {})
    course_name = c.get('club_name') or c.get('course_name') or 'Unknown Course'
    city  = loc.get('city') or None
    state = loc.get('state') or None

    # Detect total holes from tee data
    all_tees = []
    for gender_key, tee_list in (c.get('tees') or {}).items():
        gender = 'F' if gender_key == 'female' else 'M'
        for t in (tee_list or []):
            all_tees.append((gender, t))

    num_holes = 18
    if all_tees:
        sample_holes = all_tees[0][1].get('number_of_holes', 18)
        num_holes = sample_holes if sample_holes in (9, 18) else 18

    # Avoid duplicate import
    existing = db.execute(
        "SELECT course_id FROM courses WHERE course_name = %s AND league_id = %s",
        (course_name, session['league_id'])
    ).fetchone()
    if existing:
        flash(f'"{course_name}" already exists in your courses.', 'error')
        return redirect(url_for('courses.detail', course_id=existing['course_id']))

    # Insert course
    sql = """INSERT INTO courses (league_id, course_name, city, state, num_holes,
                                  is_master_record, created_date)
             VALUES (%s, %s, %s, %s, %s, 0, %s)"""
    params = (session['league_id'], course_name, city, state, num_holes,
              datetime.now().strftime('%Y-%m-%d'))
    if database.is_postgres():
        course_id = db.execute(sql + " RETURNING course_id", params).fetchone()[0]
    else:
        course_id = db.execute(sql, params).lastrowid

    def _insert_tee(course_id, tee_name, nine, slope, rating, par_total, gender, holes_subset):
        """Insert one tee + its holes. holes_subset is a list of hole dicts."""
        tee_sql = """INSERT INTO tees (course_id, tee_name, nine, slope, rating, par_total, gender)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        tee_params = (course_id, tee_name, nine, slope, rating, par_total, gender)
        if database.is_postgres():
            tee_id = db.execute(tee_sql + " RETURNING tee_id", tee_params).fetchone()[0]
        else:
            tee_id = db.execute(tee_sql, tee_params).lastrowid
        for h in holes_subset:
            db.execute(
                """INSERT INTO holes (tee_id, hole_number, par, handicap_index, distance_yards)
                   VALUES (%s, %s, %s, %s, %s)""",
                (tee_id, h['hole_number'], h.get('par', 4), h.get('handicap_index'), h.get('yardage'))
            )
        return tee_id

    def _api_holes_to_dicts(holes_data, start_hole=1):
        """Normalise API hole list → [{hole_number, par, handicap_index, yardage}, ...]."""
        result = []
        for i, h in enumerate(holes_data, start=start_hole):
            result.append({
                'hole_number':   i,
                'par':           h.get('par', 4),
                'handicap_index': h.get('handicap'),
                'yardage':       h.get('yardage'),
            })
        return result

    def _blank_holes(hole_numbers):
        return [{'hole_number': n, 'par': 4, 'handicap_index': None, 'yardage': None}
                for n in hole_numbers]

    # Insert tees + holes
    tees_added = 0
    for gender, t in all_tees:
        tee_name  = t.get('tee_name') or 'Standard'
        slope     = t.get('slope_rating') or None
        rating    = t.get('course_rating') or None
        par_total = t.get('par_total') or None
        n_holes   = t.get('number_of_holes', 18)
        holes_raw = t.get('holes') or []

        if n_holes >= 18:
            # 18-hole tee → create full + front split + back split
            all_holes = _api_holes_to_dicts(holes_raw) if holes_raw else _blank_holes(range(1, 19))
            front_holes = [h for h in all_holes if h['hole_number'] <= 9]
            back_holes  = [h for h in all_holes if h['hole_number'] >= 10]
            front_par = sum(h['par'] for h in front_holes)
            back_par  = sum(h['par'] for h in back_holes)
            # Full 18
            _insert_tee(course_id, tee_name, 'full', slope, rating, par_total, gender, all_holes)
            # Front 9 and Back 9 — slope/rating not derivable from API, left null
            _insert_tee(course_id, tee_name, 'front', None, None, front_par or None, gender, front_holes)
            _insert_tee(course_id, tee_name, 'back',  None, None, back_par  or None, gender, back_holes)
            tees_added += 3
        else:
            # 9-hole tee from API — detect which nine from name, default to front
            name_lower = tee_name.lower()
            if any(w in name_lower for w in ('back', ' in', 'second', 'b9')):
                nine = 'back'
            elif any(w in name_lower for w in ('front', 'out', 'first', 'f9')):
                nine = 'front'
            else:
                nine = 'front'
            holes = _api_holes_to_dicts(holes_raw) if holes_raw else _blank_holes(range(1, 10))
            _insert_tee(course_id, tee_name, nine, slope, rating, par_total, gender, holes)
            tees_added += 1

    db.commit()
    flash(f'Imported "{course_name}" with {tees_added} tee set(s) '
          f'(18-hole courses include Full, Front, and Back entries).', 'success')
    return redirect(url_for('courses.detail', course_id=course_id))


# ── Add course ─────────────────────────────────────────────────────────────

@bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    if request.method == 'POST':
        course_name = request.form.get('course_name', '').strip()
        city        = request.form.get('city', '').strip() or None
        state       = request.form.get('state', '').strip() or None
        num_holes   = request.form.get('num_holes', '18').strip()
        website     = request.form.get('website', '').strip() or None
        notes       = request.form.get('notes', '').strip() or None

        errors = []
        if not course_name:
            errors.append('Course name is required.')
        try:
            num_holes = int(num_holes)
            if num_holes not in (9, 18, 27, 36):
                errors.append('Number of holes must be 9, 18, 27, or 36.')
        except ValueError:
            errors.append('Number of holes must be a number.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('courses/add_edit.html',
                                   course=None,
                                   f=request.form)

        db = get_db()
        sql = """INSERT INTO courses (league_id, course_name, city, state, num_holes, website, notes,
                                is_master_record, created_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s)"""
        params = (session['league_id'], course_name, city, state, num_holes,
                  website, notes, datetime.now().strftime('%Y-%m-%d'))
        if database.is_postgres():
            new_course_id = db.execute(sql + " RETURNING course_id", params).fetchone()[0]
        else:
            cur = db.execute(sql, params)
            new_course_id = cur.lastrowid
        db.commit()
        flash(f'{course_name} added.', 'success')
        return redirect(url_for('courses.detail', course_id=new_course_id))

    return render_template('courses/add_edit.html', course=None, f={})


# ── Course detail (tee management) ─────────────────────────────────────────

@bp.route('/<int:course_id>')
@login_required
def detail(course_id):
    course = _get_course_or_404(course_id)
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('courses.index'))

    db = get_db()
    tee_groups = _get_tees_grouped(db, course_id)
    can_edit = (course['league_id'] == session['league_id'])
    return render_template('courses/detail.html',
                           course=course,
                           tee_groups=tee_groups,
                           can_edit=can_edit)


# ── Edit course ────────────────────────────────────────────────────────────

@bp.route('/<int:course_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(course_id):
    course = _get_course_or_404(course_id)
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('courses.index'))
    if course['league_id'] != session['league_id']:
        flash('You can only edit courses added by your league.', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))

    db = get_db()

    if request.method == 'POST':
        course_name = request.form.get('course_name', '').strip()
        city        = request.form.get('city', '').strip() or None
        state       = request.form.get('state', '').strip() or None
        num_holes   = request.form.get('num_holes', '18').strip()
        website     = request.form.get('website', '').strip() or None
        notes       = request.form.get('notes', '').strip() or None

        errors = []
        if not course_name:
            errors.append('Course name is required.')
        try:
            num_holes = int(num_holes)
        except ValueError:
            errors.append('Number of holes must be a number.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('courses/add_edit.html', course=course, f=request.form)

        db.execute(
            """UPDATE courses SET course_name=%s, city=%s, state=%s, num_holes=%s,
               website=%s, notes=%s WHERE course_id=%s""",
            (course_name, city, state, num_holes, website, notes, course_id)
        )
        db.commit()
        flash('Course updated.', 'success')
        return redirect(url_for('courses.detail', course_id=course_id))

    return render_template('courses/add_edit.html', course=course, f=course)


# ── Add tee set ────────────────────────────────────────────────────────────

@bp.route('/<int:course_id>/tees/add', methods=['GET', 'POST'])
@admin_required
def add_tee(course_id):
    course = _get_course_or_404(course_id)
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('courses.index'))
    if course['league_id'] != session['league_id']:
        flash('You can only edit courses added by your league.', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))

    db = get_db()

    if request.method == 'POST':
        tee_name   = request.form.get('tee_name', '').strip()
        tee_color  = request.form.get('tee_color', '').strip() or tee_name
        gender     = request.form.get('gender', 'M').strip()
        slope_str  = request.form.get('slope', '').strip()
        rating_str = request.form.get('rating', '').strip()
        # nine_type: 'nine' (front/back checkboxes) or 'full18'
        nine_type  = request.form.get('nine_type', 'nine')
        nines      = request.form.getlist('nines') if nine_type != 'full18' else ['full']

        errors = []
        if not tee_name:
            errors.append('Tee name is required.')
        if not nines:
            errors.append('Select at least one nine (or Full 18).')
        slope = None
        rating = None
        if slope_str:
            try:
                slope = float(slope_str)
            except ValueError:
                errors.append('Slope must be a number.')
        if rating_str:
            try:
                rating = float(rating_str)
            except ValueError:
                errors.append('Rating must be a number.')

        # Check for duplicate
        existing = db.execute(
            "SELECT 1 FROM tees WHERE course_id=%s AND tee_name=%s AND gender=%s",
            (course_id, tee_name, gender)
        ).fetchone()
        if existing and not errors:
            errors.append(f'A "{tee_name}" ({gender}) tee set already exists for this course.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('courses/add_tee.html', course=course,
                                   f=request.form,
                                   nines_selected=request.form.getlist('nines'),
                                   nine_type_selected=nine_type)

        for nine in nines:
            if nine == 'full':
                # Full 18-hole tee: one record, holes 1-18, default par_total=72
                sql = """INSERT INTO tees (course_id, tee_name, tee_color, nine, slope, rating, par_total, gender)
                       VALUES (%s, %s, %s, 'full', %s, %s, 72, %s)"""
                params = (course_id, tee_name, tee_color, slope, rating, gender)
                if database.is_postgres():
                    tee_id = db.execute(sql + " RETURNING tee_id", params).fetchone()[0]
                else:
                    tee_id = db.execute(sql, params).lastrowid
                for h in range(1, 19):
                    db.execute(
                        "INSERT INTO holes (tee_id, hole_number, par) VALUES (%s, %s, 4)",
                        (tee_id, h)
                    )
            else:
                # Front or back nine: one record, 9 holes
                sql = """INSERT INTO tees (course_id, tee_name, tee_color, nine, slope, rating, par_total, gender)
                       VALUES (%s, %s, %s, %s, %s, %s, 36, %s)"""
                params = (course_id, tee_name, tee_color, nine, slope, rating, gender)
                if database.is_postgres():
                    tee_id = db.execute(sql + " RETURNING tee_id", params).fetchone()[0]
                else:
                    tee_id = db.execute(sql, params).lastrowid
                start_hole = 1 if nine == 'front' else 10
                for h in range(start_hole, start_hole + 9):
                    db.execute(
                        "INSERT INTO holes (tee_id, hole_number, par) VALUES (%s, %s, 4)",
                        (tee_id, h)
                    )

        db.commit()
        flash(f'Tee set "{tee_name}" added. Edit hole details below.', 'success')
        return redirect(url_for('courses.detail', course_id=course_id))

    return render_template('courses/add_tee.html', course=course, f={},
                           nines_selected=['front', 'back'], nine_type_selected='nine')


# ── Edit holes for a tee ───────────────────────────────────────────────────

@bp.route('/<int:course_id>/tees/<int:tee_id>/holes', methods=['GET', 'POST'])
@admin_required
def edit_holes(course_id, tee_id):
    course = _get_course_or_404(course_id)
    if not course:
        flash('Course not found.', 'error')
        return redirect(url_for('courses.index'))

    db = get_db()
    tee = db.execute("SELECT * FROM tees WHERE tee_id=%s AND course_id=%s",
                     (tee_id, course_id)).fetchone()
    if not tee:
        flash('Tee not found.', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))

    holes = db.execute(
        "SELECT * FROM holes WHERE tee_id=%s ORDER BY hole_number",
        (tee_id,)
    ).fetchall()

    if request.method == 'POST':
        slope_str  = request.form.get('slope', '').strip()
        rating_str = request.form.get('rating', '').strip()
        try:
            slope = float(slope_str) if slope_str else None
        except ValueError:
            slope = None
        try:
            rating = float(rating_str) if rating_str else None
        except ValueError:
            rating = None

        par_total = 0
        for hole in holes:
            h_num = hole['hole_number']
            par_val   = request.form.get(f'par_{h_num}', '4')
            hdcp_val  = request.form.get(f'hdcp_{h_num}', '')
            yards_val = request.form.get(f'yards_{h_num}', '')
            try:
                par_val = int(par_val)
            except (ValueError, TypeError):
                par_val = 4
            try:
                hdcp_val = int(hdcp_val) if hdcp_val else None
            except (ValueError, TypeError):
                hdcp_val = None
            try:
                yards_val = int(yards_val) if yards_val else None
            except (ValueError, TypeError):
                yards_val = None

            par_total += par_val
            db.execute(
                """UPDATE holes SET par=%s, handicap_index=%s, distance_yards=%s
                   WHERE hole_id=%s""",
                (par_val, hdcp_val, yards_val, hole['hole_id'])
            )

        db.execute(
            "UPDATE tees SET par_total=%s, slope=%s, rating=%s WHERE tee_id=%s",
            (par_total, slope, rating, tee_id)
        )
        db.commit()
        flash('Hole details saved.', 'success')
        return redirect(url_for('courses.detail', course_id=course_id))

    is_full18 = (tee['nine'] == 'full')
    return render_template('courses/holes.html',
                           course=course, tee=tee, holes=holes,
                           is_full18=is_full18)


# ── Delete tee ─────────────────────────────────────────────────────────────

@bp.route('/<int:course_id>/tees/<int:tee_id>/delete', methods=['POST'])
@admin_required
def delete_tee(course_id, tee_id):
    course = _get_course_or_404(course_id)
    if not course or course['league_id'] != session['league_id']:
        flash('Not allowed.', 'error')
        return redirect(url_for('courses.index'))

    db = get_db()
    db.execute("DELETE FROM holes WHERE tee_id=%s", (tee_id,))
    db.execute("DELETE FROM tees WHERE tee_id=%s AND course_id=%s", (tee_id, course_id))
    db.commit()
    flash('Tee deleted.', 'success')
    return redirect(url_for('courses.detail', course_id=course_id))


# ── Delete course ─────────────────────────────────────────────────────────────

@bp.route('/<int:course_id>/delete', methods=['POST'])
@admin_required
def delete_course(course_id):
    course = _get_course_or_404(course_id)
    if not course or course['league_id'] != session['league_id']:
        flash('Not allowed.', 'error')
        return redirect(url_for('courses.index'))

    db = get_db()
    used = db.execute(
        "SELECT 1 FROM rounds WHERE course_id = %s LIMIT 1", (course_id,)
    ).fetchone()
    if used:
        flash('Cannot delete — this course has recorded rounds.', 'error')
        return redirect(url_for('courses.detail', course_id=course_id))

    # Clear course/tee refs on scheduled matchups before deleting tees
    db.execute(
        "UPDATE matchups SET course_id = NULL, tee_id = NULL WHERE course_id = %s",
        (course_id,)
    )
    tee_ids = [r['tee_id'] for r in db.execute(
        "SELECT tee_id FROM tees WHERE course_id = %s", (course_id,)
    ).fetchall()]
    for tid in tee_ids:
        db.execute("DELETE FROM holes WHERE tee_id = %s", (tid,))
    db.execute("DELETE FROM tees WHERE course_id = %s", (course_id,))
    db.execute("DELETE FROM courses WHERE course_id = %s AND league_id = %s",
               (course_id, session['league_id']))
    db.commit()
    flash('Course deleted.', 'success')
    return redirect(url_for('courses.index'))


# ── Tees JSON (for import wizard dropdowns) ──────────────────────────────────

@bp.route('/<int:course_id>/tees-json')
@login_required
def tees_json(course_id):
    db = get_db()
    tees = db.execute(
        "SELECT tee_id, tee_name, nine FROM tees WHERE course_id=%s ORDER BY tee_name, nine",
        (course_id,)
    ).fetchall()
    result = []
    for t in tees:
        label = t['tee_name']
        if t['nine'] == 'full':
            label += ' (Full 18)'
        elif t['nine'] in ('front', 'back'):
            label += f" ({t['nine'].title()})"
        result.append({'tee_id': t['tee_id'], 'tee_name': label})
    return jsonify(result)
