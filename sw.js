self.addEventListener('install', (event) => {
    console.log('Service Worker Installing...');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('Service Worker Activated');
});

self.addEventListener('fetch', (event) => {
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
