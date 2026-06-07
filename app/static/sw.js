// Golf League Tracker — Service Worker
// Version bump here to force cache refresh on deploy
const CACHE_VERSION = 'v1';
const STATIC_CACHE = `glt-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `glt-dynamic-${CACHE_VERSION}`;
const OFFLINE_URL = '/offline';

// Static assets to pre-cache on install
const PRECACHE_URLS = [
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  OFFLINE_URL,
];

// Pages to cache dynamically (network-first with cache fallback)
const CACHE_PAGES = [
  '/schedule',
  '/standings',
  '/players',
];

// ── Install: pre-cache static assets ──────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

// ── Activate: clean up old caches ─────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
          .map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// ── Fetch: network-first for pages, cache-first for static assets ─────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip admin, score entry, and API-like routes (always need fresh data)
  const skipPaths = ['/admin', '/scores/enter', '/skins/calculate', '/forum/new', '/auth', '/switch-season'];
  if (skipPaths.some((p) => url.pathname.startsWith(p))) return;

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Navigation / page requests: network-first, fall back to cache, then offline page
  if (request.mode === 'navigate' || request.headers.get('Accept').includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful navigation responses for the key pages
          if (response && response.status === 200) {
            const shouldCache = CACHE_PAGES.some((p) => url.pathname.startsWith(p));
            if (shouldCache) {
              const clone = response.clone();
              caches.open(DYNAMIC_CACHE).then((cache) => cache.put(request, clone));
            }
          }
          return response;
        })
        .catch(() => {
          // Network failed — try cache, then offline fallback
          return caches.match(request).then((cached) => {
            return cached || caches.match(OFFLINE_URL);
          });
        })
    );
    return;
  }
});
