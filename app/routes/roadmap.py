"""Public Roadmap page — what's planned for BGLT next.

Renders roadmap_content.ROADMAP_LANES, a hand-curated content list (see
that module's docstring). No per-league data, no auth required — same
"safe and useful as a pre-signup reference too" reasoning as wiki.py.
"""

from flask import Blueprint, render_template
from roadmap_content import ROADMAP_LANES

bp = Blueprint('roadmap', __name__)


@bp.route('/roadmap')
def index():
    return render_template('roadmap/index.html', lanes=ROADMAP_LANES)
