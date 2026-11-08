const CACHE_NAME = 'locktrace-pwa-v34';

const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/integrity.json',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-192.png',
  '/icons/icon-maskable-512.png',
  '/icons/apple-touch-icon.png',
  '/icons/icon-32.png',
  '/icons/icon.svg'
];

// Install: Pre-cache critical decentralized core shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: Clean up previous version caches immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-First for HTML shell (respects 403 SHA-256 tamper lock, survives full server shutdown offline!)
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // 1. Never intercept or cache API or P2P RPC requests
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/p2p/')) {
    return;
  }

  // 2. Only handle same-origin static requests
  if (url.origin !== self.location.origin) {
    return;
  }

  // 3. Navigation / HTML shell: Network-First with Offline Fallback
  if (event.request.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkResponse;
      }).catch(() => {
        return caches.match('/index.html') || caches.match('/');
      })
    );
    return;
  }

  // 4. Stale-While-Revalidate for icons/manifest/integrity.json
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});

// 5. Native Push & Instant Notification Handlers (Mobile PWA & Browser)
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          if ('navigate' in client) {
            client.navigate(targetUrl);
          }
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

self.addEventListener('push', (event) => {
  let data = { title: 'LockTrace Mainnet', body: 'New blockchain event received.', url: '/' };
  if (event.data) {
    try {
      data = Object.assign(data, event.data.json());
    } catch (_e) {
      data.body = event.data.text() || data.body;
    }
  }

  const options = {
    body: data.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-32.png',
    tag: data.tag || 'locktrace-push-' + Date.now(),
    vibrate: [150, 80, 150],
    data: { url: data.url || '/' },
    renotify: true
  };

  const notifyPromise = self.registration.showNotification(data.title, options);
  const broadcastPromise = self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
    for (const client of windowClients) {
      client.postMessage({
        type: 'LOCKTRACE_PUSH_EVENT',
        payload: {
          id: data.tag || ('push-' + Date.now()),
          category: data.category || 'transfer',
          title: data.title,
          body: data.body,
          icon: (data.category === 'transfer' ? 'payments' : (data.category === 'space' ? 'forum' : (data.category === 'bns_offer' ? 'gavel' : 'notifications'))),
          time: Number(data.timestamp ? (data.timestamp * 1000) : Date.now()),
          read: false,
          actionUrl: data.url || '#cuzdanim'
        }
      });
    }
  }).catch(() => {});

  event.waitUntil(Promise.all([notifyPromise, broadcastPromise]));
});
