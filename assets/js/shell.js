// The frame around every signed-in page: header, desktop nav, phone tab
// bar, account menu, sign-out, and the "you need to be signed in" guard.

import { api, apiEvents, ApiError, session } from "./api.js";
import { initTheme } from "./theme.js";
import { esc, toast } from "./ui.js";

const NAV = [
  { page: "dashboard", href: "dashboard.html", label: "Dashboard", icon: '<path d="M4 11 12 4l8 7v9h-5v-6H9v6H4Z"/>' },
  { page: "wardrobe", href: "wardrobe.html", label: "Wardrobe", icon: '<path d="M12 6.5a2 2 0 1 1 2 2c-1 0-2 .7-2 1.6V11"/><path d="M12 11 3 18h18Z"/>' },
  { page: "generator", href: "outfit-generator.html", label: "Get dressed", icon: '<path d="m12 3 2.2 5.6L20 9.5l-4.4 3.9 1.3 5.8L12 16.3 7.1 19.2l1.3-5.8L4 9.5l5.8-.9Z"/>' },
  { page: "saved", href: "saved-outfits.html", label: "Saved", icon: '<path d="M6 3h12v18l-6-4-6 4Z"/>' },
  { page: "shop", href: "smart-buys.html", label: "Smart buys", icon: '<path d="M5 8h14l-1.2 11.2a1 1 0 0 1-1 .8H7.2a1 1 0 0 1-1-.8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>' },
  { page: "history", href: "history.html", label: "History", icon: '<path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 4v4.5h4.5M12 8v4l3 2"/>' },
];

const svg = (paths) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
  stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;

// Real, useful styling tips for the shop-window ticker
const TIPS = [
  "Neutrals let one bright piece be the star",
  "Rain on the forecast? Boots beat sandals",
  "Denim counts as a neutral",
  "Three loud colours is one too many",
  "Under 12°C, bring a layer",
  "Tonal outfits look expensive",
  "Rate outfits and the suggestions learn your taste",
];

function tickerHTML() {
  const items = TIPS.map((t) => `<span>${t}</span>`).join("");
  return `<div class="ticker__track">${items}${items}</div>`;
}

function initials(name) {
  return (name || "?").trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
}

function headerHTML(page) {
  const links = NAV.map((n) =>
    `<a class="app-nav__link" href="${n.href}" ${n.page === page ? 'aria-current="page"' : ""}>${n.label}</a>`
  ).join("");
  return `
    <div class="container site-header__inner">
      <a class="wordmark" href="dashboard.html" aria-label="FitCheck.AI dashboard"><img class="wordmark__logo" src="assets/images/logo/fitcheck-mark.png" alt="" width="36" height="36">FitCheck<span class="wordmark__ai">.ai</span></a>
      <nav class="app-nav" aria-label="Main">${links}</nav>
      <div class="site-header__actions">
        <button class="icon-btn theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="Switch to dark mode">
          <span class="swatch" aria-hidden="true"></span>
        </button>
        <details class="account-menu">
          <summary class="account-menu__button" aria-label="Account menu">
            <span class="avatar" data-avatar>·</span>
          </summary>
          <div class="account-menu__panel" role="menu">
            <p class="account-menu__who"><strong data-user-name>Signed in</strong><span data-user-email></span></p>
            <a role="menuitem" href="profile.html" ${page === "profile" ? 'aria-current="page"' : ""}>Profile and preferences</a>
            <button role="menuitem" type="button" data-sign-out>Sign out</button>
          </div>
        </details>
      </div>
    </div>`;
}

function tabbarHTML(page) {
  return NAV.map((n) =>
    `<a class="tabbar__item ${n.page === "generator" ? "tabbar__item--main" : ""}" href="${n.href}"
        ${n.page === page ? 'aria-current="page"' : ""}>
       ${svg(n.icon)}<span>${n.label}</span>
     </a>`
  ).join("");
}

function goToLogin(reason) {
  const here = location.pathname.split("/").pop() || "dashboard.html";
  const next = encodeURIComponent(here + location.search);
  location.replace(`login.html?next=${next}${reason ? `&reason=${reason}` : ""}`);
}

export async function signOut() {
  try {
    if (session.isSignedIn) await api.auth.logout();
  } catch {
    // the token is cleared locally regardless; a dead server can't keep you signed in
  }
  session.clear();
  location.href = "login.html?reason=signed_out";
}

function showOffline(err) {
  const main = document.querySelector("main");
  const box = document.createElement("div");
  box.className = "notice notice--error offline-notice";
  box.setAttribute("role", "alert");
  box.innerHTML = `<div><strong>${esc(err.message)}</strong>
    <p>FitCheck.AI couldn't reach its server. Check your connection; if it persists, the server may be starting up or down for maintenance.</p></div>
    <button class="btn" type="button">Try again</button>`;
  box.querySelector("button").addEventListener("click", () => location.reload());
  main.prepend(box);
}

/**
 * Call first on every signed-in page.
 * Resolves to { user, preferences } or null if the page shouldn't continue.
 */
export async function initShell(page) {
  if (!session.isSignedIn) {
    goToLogin();
    return null;
  }

  document.body.dataset.page = page;
  const header = document.querySelector("[data-shell-header]");
  if (!document.querySelector(".ticker")) {
    const ticker = document.createElement("div");
    ticker.className = "ticker";
    ticker.setAttribute("aria-hidden", "true");
    ticker.innerHTML = tickerHTML();
    header.before(ticker);
  }
  header.className = "site-header app-header";
  header.innerHTML = headerHTML(page);
  initTheme();

  const tabbar = document.querySelector("[data-shell-tabbar]");
  tabbar.className = "tabbar";
  tabbar.setAttribute("aria-label", "Main");
  tabbar.innerHTML = tabbarHTML(page);

  header.querySelector("[data-sign-out]").addEventListener("click", signOut);
  const menu = header.querySelector(".account-menu");
  document.addEventListener("click", (e) => {
    if (menu.open && !menu.contains(e.target)) menu.open = false;
  });
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { menu.open = false; menu.querySelector("summary").focus(); }
  });

  apiEvents.addEventListener("unauthorized", () => goToLogin("expired"));

  try {
    const me = await api.auth.me();
    header.querySelector("[data-user-name]").textContent = me.user.display_name;
    header.querySelector("[data-user-email]").textContent = me.user.email;
    header.querySelector("[data-avatar]").textContent = initials(me.user.display_name);
    return me;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null; // redirecting
    if (err instanceof ApiError) {
      showOffline(err);
    } else {
      console.error(err);
      toast("Something went wrong loading your account.", "error");
    }
    return null;
  }
}
