const CACHE_PREFIX = 'bist-hibrit-';
const CACHE_NAME = 'bist-hibrit-v4.8-kurumsal-pwa-cache';
const NETWORK_TIMEOUT_MS = 4500;
const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './dogrulanmis_piyasa_snapshot.json',
  './icon-192.png',
  './icon-512.png',
  './icon-192.svg',
  './icon-512.svg'
];

function getCanonicalCacheKey(requestOrUrl) {
  try {
    const rawUrl = typeof requestOrUrl === 'string' ? requestOrUrl : requestOrUrl.url;
    const parsed = new URL(rawUrl, self.location ? self.location.origin : 'https://axonturk.github.io');
    // Sorgu parametreli (?t=..., ?app=...) snapshot ve statik dosya isteklerini tek kanonik anahtara indirge (F18 düzeltmesi)
    if (
      parsed.pathname.endsWith('/') ||
      parsed.pathname.endsWith('dogrulanmis_piyasa_snapshot.json') ||
      parsed.pathname.endsWith('index.html') ||
      parsed.pathname.endsWith('manifest.json') ||
      parsed.pathname.endsWith('sw.js') ||
      parsed.pathname.endsWith('.svg') ||
      parsed.pathname.endsWith('.png')
    ) {
      return parsed.origin + parsed.pathname;
    }
    return parsed.href;
  } catch (_) {
    return typeof requestOrUrl === 'string' ? requestOrUrl.split('?')[0] : requestOrUrl;
  }
}

function fetchWithTimeout(req, timeoutMs) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        reject(new Error('SW_NETWORK_TIMEOUT'));
      }
    }, timeoutMs);

    fetch(req)
      .then((res) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(res);
        }
      })
      .catch((err) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(err);
        }
      });
  });
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.map((key) => {
            // Yalnızca bu uygulamaya ait (bist-hibrit-*) eski önbellekleri sil; aynı origin'deki diğer uygulamaları koru (F18)
            if (key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME) {
              return caches.delete(key);
            }
            return null;
          })
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (!req || req.method !== 'GET') return;

  const canonicalKey = getCanonicalCacheKey(req);

  event.respondWith(
    fetchWithTimeout(req, NETWORK_TIMEOUT_MS)
      .then((res) => {
        if (res && res.ok) {
          const clone = res.clone();
          const writePromise = caches.open(CACHE_NAME).then((cache) => cache.put(canonicalKey, clone));
          if (typeof event.waitUntil === 'function') {
            event.waitUntil(writePromise);
          }
        }
        return res;
      })
      .catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        const exactMatch = await cache.match(canonicalKey);
        if (exactMatch) return exactMatch;
        const reqMatch = await caches.match(req, { ignoreSearch: true });
        if (reqMatch) return reqMatch;
        const baseSnap = canonicalKey.endsWith('dogrulanmis_piyasa_snapshot.json')
          ? await cache.match('./dogrulanmis_piyasa_snapshot.json')
          : null;
        return baseSnap || cache.match('./index.html');
      })
  );
});
