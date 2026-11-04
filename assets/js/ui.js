// Small UI helpers shared by every page: toasts, busy buttons,
// loaders, empty states, and the backend status indicator.

import { api, ApiError } from "./api.js";

// ---- escaping ----
// Anything that came from the server or a form goes through this before
// it touches innerHTML.
export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// ---- toasts ----

let rack;

function getRack() {
  if (!rack) {
    rack = document.createElement("div");
    rack.className = "toast-rack";
    rack.setAttribute("role", "region");
    rack.setAttribute("aria-label", "Notifications");
    document.body.append(rack);
  }
  return rack;
}

/**
 * toast("Saved to your wardrobe", "success")
 * kinds: success | error | info
 */
export function toast(message, kind = "info", { duration = 4500 } = {}) {
  const el = document.createElement("div");
  el.className = "toast";
  el.dataset.kind = kind;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.innerHTML = `<span>${esc(message)}</span>
    <button class="toast__close" type="button" aria-label="Dismiss">&times;</button>`;

  const dismiss = () => {
    el.classList.add("is-leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 400); // in case animations are off
  };

  el.querySelector("button").addEventListener("click", dismiss);
  getRack().append(el);
  if (duration) setTimeout(dismiss, duration);
  return dismiss;
}

// Turns any thrown error into something a person can read.
export function toastError(err, fallback = "Something went wrong.") {
  const msg = err instanceof ApiError ? err.message : fallback;
  if (!(err instanceof ApiError)) console.error(err);
  return toast(msg, "error", { duration: 7000 });
}

// ---- busy state ----

export async function withBusy(button, task, busyLabel = "Working…") {
  const original = button.innerHTML;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = busyLabel;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.innerHTML = original;
  }
}

// ---- markup snippets ----

export function loaderHTML(label = "Loading") {
  return `<span class="stitch-loader" role="status">
    <svg viewBox="0 0 64 10" aria-hidden="true"><line x1="2" y1="5" x2="62" y2="5"/></svg>
    <span>${esc(label)}…</span>
  </span>`;
}

const hangerSVG = `<svg viewBox="0 0 88 64" fill="none" stroke="currentColor" stroke-width="2.5"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M44 14a6 6 0 1 1 6 6c-3 0-6 2-6 5v3"/>
  <path d="M44 28 6 52h76L44 28Z"/>
</svg>`;

export function emptyStateHTML({ title, body, actionLabel, actionHref }) {
  const action = actionLabel
    ? `<a class="btn btn--primary" href="${esc(actionHref)}">${esc(actionLabel)}</a>`
    : "";
  return `<div class="empty-state">
    ${hangerSVG}
    <h2 class="empty-state__title">${esc(title)}</h2>
    <p>${esc(body)}</p>
    ${action}
  </div>`;
}

// ---- demo wardrobe ----
// A button that fills an empty wardrobe with 20-odd real photographed pieces,
// so someone can try the whole app before photographing their own clothes.

export function demoWardrobeButton(onDone) {
  const btn = document.createElement("button");
  btn.className = "btn btn--tape";
  btn.type = "button";
  btn.textContent = "Try it with a demo wardrobe";
  btn.dataset.demo = "";
  btn.addEventListener("click", async () => {
    try {
      const res = await withBusy(btn, () => api.demo.load(), "Hanging up the demo pieces…");
      toast(`Added ${res.added} demo pieces to your wardrobe.`, "success");
      onDone?.(res);
    } catch (err) {
      toastError(err, "Couldn't load the demo wardrobe.");
    }
  });
  return btn;
}

// ---- storage status pill ----
// Any element with [data-api-status] says where the data lives and whether
// the on-device engine is ready.

export async function watchApiStatus() {
  const pills = document.querySelectorAll("[data-api-status]");
  if (!pills.length) return;
  const set = (state, text) => pills.forEach((p) => { p.dataset.state = state; p.textContent = text; });
  set("checking", "Starting up…");
  try {
    const h = await api.health();
    set("up", h.models.available ? "Connected · AI ready" : "Connected · rules mode");
  } catch {
    set("down", "Server unreachable");
  }
}

// ---- form errors ----
// The API returns { details: { field: "message" } }. Each input gets
// aria-invalid and a message underneath, linked with aria-describedby.

export function clearFieldErrors(form) {
  form.querySelectorAll("[data-error-for]").forEach((el) => el.remove());
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
}

export function showFieldErrors(form, details) {
  clearFieldErrors(form);
  if (!details) return false;
  let first = null;
  for (const [field, message] of Object.entries(details)) {
    const name = field.replace(/^preferences\./, "");
    const group = form.querySelector(`[data-field="${CSS.escape(name)}"]`);
    const input = form.querySelector(`[name="${CSS.escape(name)}"]`) || group;
    if (!input) continue;
    // grouped controls (chips, swatches) show one message under the group
    const holder = group || input.closest(".field") || input.parentElement;
    const msg = document.createElement("p");
    msg.className = "field__error";
    msg.dataset.errorFor = name;
    msg.id = `err-${name.replace(/[^a-z0-9_-]/gi, "")}`;
    msg.textContent = message;
    holder.append(msg);
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", msg.id);
    first ??= input;
  }
  if (first) first.focus({ preventScroll: false });
  return Boolean(first);
}

// ---- confirm dialog ----

export function confirmDialog({ title, body = "", confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "dialog dialog--small";
    dlg.innerHTML = `
      <form method="dialog" class="dialog__body">
        <h2 class="dialog__title">${esc(title)}</h2>
        ${body ? `<p class="muted">${esc(body)}</p>` : ""}
        <div class="dialog__actions">
          <button class="btn" value="cancel" type="submit">Cancel</button>
          <button class="btn ${danger ? "btn--danger" : "btn--primary"}" value="ok" type="submit">${esc(confirmLabel)}</button>
        </div>
      </form>`;
    document.body.append(dlg);
    dlg.addEventListener("close", () => {
      resolve(dlg.returnValue === "ok");
      dlg.remove();
    });
    dlg.showModal();
    dlg.querySelector('[value="cancel"]').focus();
  });
}

// ---- password check for sensitive actions ----
// Resolves to the typed password, or null if cancelled.

export function passwordDialog({ title, body = "", confirmLabel = "Continue" }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "dialog dialog--small";
    dlg.innerHTML = `
      <form method="dialog" class="dialog__body">
        <h2 class="dialog__title">${esc(title)}</h2>
        ${body ? `<p class="muted">${esc(body)}</p>` : ""}
        <div class="field">
          <label class="field__label" for="reauth-pw">Your password</label>
          <input class="input" id="reauth-pw" type="password" autocomplete="current-password" required>
        </div>
        <div class="dialog__actions">
          <button class="btn" value="cancel" type="submit" formnovalidate>Cancel</button>
          <button class="btn btn--primary" value="ok" type="submit">${esc(confirmLabel)}</button>
        </div>
      </form>`;
    document.body.append(dlg);
    const input = dlg.querySelector("input");
    dlg.addEventListener("close", () => {
      resolve(dlg.returnValue === "ok" && input.value ? input.value : null);
      dlg.remove();
    });
    dlg.showModal();
    input.focus();
  });
}

// ---- small formatting helpers ----

export function formatDate(iso) {
  // the API sends naive UTC timestamps
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400 && d.getDate() === now.getDate()) {
    return `today, ${d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  }
  return d.toLocaleDateString([], { day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
