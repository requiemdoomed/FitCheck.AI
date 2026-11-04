// Bits shared by the sign-in and create-account pages.

import { ApiError } from "../api.js";
import { initTheme } from "../theme.js";
import { esc, showFieldErrors, watchApiStatus } from "../ui.js";

const APP_PAGES = new Set([
  "dashboard.html", "wardrobe.html", "outfit-generator.html", "outfit.html",
  "saved-outfits.html", "history.html", "profile.html",
]);

// Only ever send people to one of our own pages after signing in, never
// to whatever URL was put in ?next= (that would be an open redirect).
export function safeNext(fallback = "dashboard.html") {
  const next = new URLSearchParams(location.search).get("next") || "";
  const [page, query = ""] = next.split("?");
  if (!APP_PAGES.has(page)) return fallback;
  return /^[\w=&%.-]*$/.test(query) && query ? `${page}?${query}` : page;
}

export function setupAuthPage() {
  initTheme();
  watchApiStatus();
  document.querySelectorAll("[data-pw-toggle]").forEach((btn) => {
    const input = document.getElementById(btn.getAttribute("aria-controls"));
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
      btn.setAttribute("aria-pressed", String(show));
    });
  });
}

export function notice(message, kind = "error") {
  const box = document.querySelector("[data-auth-notice]");
  box.innerHTML = message ? `<div class="notice notice--${kind}" role="${kind === "error" ? "alert" : "status"}">${esc(message)}</div>` : "";
}

export function handleAuthError(form, err) {
  if (err instanceof ApiError) {
    const marked = showFieldErrors(form, err.details);
    notice(marked && err.code === "validation_error" ? "" : err.message);
  } else {
    console.error(err);
    notice("Something went wrong. Try again.");
  }
}
