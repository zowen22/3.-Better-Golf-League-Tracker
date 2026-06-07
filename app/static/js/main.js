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
