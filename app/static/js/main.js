// main.js

// Highlight active nav link based on current path
(function () {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-page-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href && href !== '/' && path.startsWith(href.replace(/\/[^/]+$/, ''))) {
            link.classList.add('nav-page-link--active');
        }
    });
})();

// ── Shared setting-info tooltip (ⓘ buttons) ─────────────────────────────────
// Page-agnostic: any button with class .settings-info-btn carries its tooltip
// text in a data-tooltip attribute (rendered server-side — e.g. the League
// Settings page renders it from app/setting_help.py's SETTING_HELP dict) and
// an optional data-wiki-anchor (e.g. "setting-2.10") used here to append a
// "Learn more" link pointing at the in-app wiki. The link is appended by this
// JS on top of the tooltip text — it is never part of the shared text itself.
// Positioning/dismiss logic generalized from the settings page's original
// inline implementation.
(function () {
    const buttons = document.querySelectorAll('.settings-info-btn');
    if (!buttons.length) return;
    let tip = null;
    function ensureTip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.id = 'settings-info-tip';
        document.body.appendChild(tip);
        document.addEventListener('click', e => {
            if (!e.target.closest('.settings-info-btn') && !e.target.closest('#settings-info-tip')) {
                tip.style.display = 'none';
            }
        }, true);
        return tip;
    }
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            const t = ensureTip();
            if (t.style.display === 'block' && t._src === btn) { t.style.display = 'none'; return; }
            t._src = btn;
            t.innerHTML = '';
            t.appendChild(document.createTextNode(btn.dataset.tooltip || ''));
            const anchor = btn.dataset.wikiAnchor;
            if (anchor) {
                t.appendChild(document.createElement('br'));
                const a = document.createElement('a');
                a.href = '/wiki#' + anchor;
                a.target = '_blank';
                a.rel = 'noopener';
                a.textContent = 'Learn more';
                t.appendChild(a);
            }
            t.style.display = 'block';
            const rect = btn.getBoundingClientRect();
            const scrollX = window.scrollX, scrollY = window.scrollY;
            t.style.left = (rect.left + scrollX) + 'px';
            t.style.top  = (rect.top  + scrollY - t.offsetHeight - 8) + 'px';
            const tr = t.getBoundingClientRect();
            if (tr.left < 8) t.style.left = (scrollX + 8) + 'px';
            if (tr.right > window.innerWidth - 8) t.style.left = (scrollX + window.innerWidth - t.offsetWidth - 8) + 'px';
            if (tr.top < 8) t.style.top = (rect.bottom + scrollY + 4) + 'px';
        });
    });
})();

// ── Shared Expand All / Collapse All control for grouped <details> ─────────
// Page-agnostic: any button with data-details-toggle="expand-all" or
// "collapse-all" plus data-details-group="<class>" toggles every
// <details class="<class>"> on the page open/closed.
(function () {
    document.querySelectorAll('[data-details-toggle]').forEach(btn => {
        const groupClass = btn.dataset.detailsGroup;
        if (!groupClass) return;
        const open = btn.dataset.detailsToggle === 'expand-all';
        btn.addEventListener('click', () => {
            document.querySelectorAll('details.' + groupClass).forEach(d => { d.open = open; });
        });
    });
})();
