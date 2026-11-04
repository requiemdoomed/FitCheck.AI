// Registers the service worker (sw.js) so pages open without a connection and
// FitCheck.AI can be installed to a home screen. The worker never stores
// anything from /api, so no personal data is kept in the browser.
// Swayam Shakya

export function registerOffline() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => { /* offline support is optional */ });
  }, { once: true });
}
