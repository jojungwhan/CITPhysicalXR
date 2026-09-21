/* global caches, self */

const BASE_PATH = new URL(self.registration.scope).pathname.replace(/\/$/, "");
const CACHE_NAME = `cit-classroom-control-v3:${BASE_PATH}`;
const CONSOLE_PATH = `${BASE_PATH}/fabric`;
const APP_SHELL = [
  CONSOLE_PATH,
  `${BASE_PATH}/fabric.webmanifest`,
  `${BASE_PATH}/favicon.svg`,
  `${BASE_PATH}/icons/cit-control-192.png`,
  `${BASE_PATH}/icons/cit-control-512.png`,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter(
              (key) =>
                key.startsWith("cit-classroom-control-") && key !== CACHE_NAME,
            )
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith(`${BASE_PATH}/api/`)
  ) {
    return;
  }

  if (
    request.mode === "navigate" &&
    url.pathname.replace(/\/$/, "") === CONSOLE_PATH
  ) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            event.waitUntil(
              caches
                .open(CACHE_NAME)
                .then((cache) => cache.put(CONSOLE_PATH, copy)),
            );
          }
          return response;
        })
        .catch(() => caches.match(CONSOLE_PATH)),
    );
    return;
  }

  if (
    url.pathname.startsWith(`${BASE_PATH}/assets/`) ||
    url.pathname.startsWith(`${BASE_PATH}/icons/`) ||
    url.pathname === `${BASE_PATH}/favicon.svg` ||
    url.pathname === `${BASE_PATH}/fabric.webmanifest`
  ) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ??
          fetch(request).then((response) => {
            const copy = response.clone();
            void caches
              .open(CACHE_NAME)
              .then((cache) => cache.put(request, copy));
            return response;
          }),
      ),
    );
  }
});
