/* Service worker del Stock Research Dashboard.
   Estrategia: network-first SIN caché HTTP para la página y para version.json
   (así cualquier dispositivo ve siempre la última publicación), con caché de
   respaldo solo para poder abrir la app sin conexión. */
const CACHE = "stocks-shell-v3";
const ASSETS = ["./", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (e) => {
  if (e.data === "skipWaiting") self.skipWaiting();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Solo gestionamos nuestro propio origen; las consultas en vivo a TradingView van directo a la red.
  if (url.origin !== self.location.origin) return;

  // El sello de versión nunca se cachea ni se guarda: es justamente lo que detecta la caché vieja.
  if (url.pathname.endsWith("version.json")) {
    e.respondWith(fetch(e.request, { cache: "no-store" }));
    return;
  }

  // La página siempre se pide fresca al servidor, saltando la caché HTTP del navegador.
  const esPagina = e.request.mode === "navigate" || url.pathname.endsWith("/") ||
                   url.pathname.endsWith("index.html");
  e.respondWith(
    fetch(esPagina ? new Request(e.request, { cache: "no-store" }) : e.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy)).catch(() => {});
        return resp;
      })
      .catch(() => caches.match(e.request, { ignoreSearch: true }))
  );
});
