// Light / dark switching. The first paint is handled by the tiny inline
// script in each page's <head> so there's no flash of the wrong theme;
// this module only wires up the toggle buttons afterwards.

import { config } from "./config.js";
import { registerOffline } from "./pwa.js";

registerOffline();

const KEY = config.storageKeys.theme;
const root = document.documentElement;
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

function stored() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export function currentTheme() {
  return root.dataset.theme || (systemDark.matches ? "dark" : "light");
}

export function setTheme(theme, { persist = true } = {}) {
  root.dataset.theme = theme;
  if (persist) {
    try { localStorage.setItem(KEY, theme); } catch { /* storage blocked: fine, it just won't stick */ }
  }
  syncButtons();
}

function syncButtons() {
  const dark = currentTheme() === "dark";
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(dark));
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    btn.title = dark ? "Light mode" : "Dark mode";
  });
}

export function initTheme() {
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => setTheme(currentTheme() === "dark" ? "light" : "dark"));
  });

  // Follow the OS while the user hasn't made their own choice
  systemDark.addEventListener("change", () => {
    if (!stored()) syncButtons();
  });

  // Keep other open tabs in step
  window.addEventListener("storage", (e) => {
    if (e.key === KEY && e.newValue) setTheme(e.newValue, { persist: false });
  });

  syncButtons();
}
