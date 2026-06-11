from flask import Blueprint, jsonify, render_template, request, redirect, url_for, session, flash
import database
from database import get_db
from routes.auth import login_required, admin_required
from datetime import datetime

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
        tee_color  = request.form.get('tee_color', '').strip() or None
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
