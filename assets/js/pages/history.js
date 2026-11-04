// Outfit history with like/dislike filter and paging.

import { api } from "../api.js";
import { outfitCardHTML } from "../outfit-view.js";
import { initShell } from "../shell.js";
import { emptyStateHTML, esc, loaderHTML, toastError, watchApiStatus } from "../ui.js";

const me = await initShell("history");
if (me) start();

function start() {
  watchApiStatus();
  const root = document.querySelector("[data-history]");
  const tabs = document.querySelector("[data-history-filter]");
  const unit = me.preferences.temperature_unit;
  const state = { page: 1, verdict: "", data: null };

  const params = new URLSearchParams(location.search);
  if (["like", "dislike"].includes(params.get("verdict"))) state.verdict = params.get("verdict");
  if (Number(params.get("page")) > 1) state.page = Number(params.get("page"));

  function syncUrl() {
    const q = new URLSearchParams();
    if (state.verdict) q.set("verdict", state.verdict);
    if (state.page > 1) q.set("page", state.page);
    history.replaceState(null, "", `history.html${q.toString() ? `?${q}` : ""}`);
  }

  function syncTabs() {
    tabs.querySelectorAll("[data-verdict]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.verdict === state.verdict)));
  }

  const thumb = {
    like: '<path d="M6 20v-9h3l3-7c2 0 3 1.4 3 3.4l-.6 3.6H19c1.4 0 2.3 1.3 2 2.6l-1.3 5.2c-.3 1-1 1.6-2 1.6Z"/>',
    dislike: '<path d="M18 4v9h-3l-3 7c-2 0-3-1.4-3-3.4l.6-3.6H5c-1.4 0-2.3-1.3-2-2.6l1.3-5.2C4.6 4.6 5.3 4 6.3 4Z"/>',
  };
  const fbButton = (o, verdict) => `<button class="icon-btn feedback-btn" type="button" data-fb="${verdict}" data-id="${Number(o.id)}"
      aria-pressed="${o.feedback === verdict}" aria-label="${verdict === "like" ? "Like" : "Not for me"}">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${thumb[verdict]}</svg>
    </button>`;

  function render() {
    const d = state.data;
    if (!d.outfits.length) {
      root.innerHTML = state.verdict
        ? emptyStateHTML({ title: state.verdict === "like" ? "No liked outfits yet" : "Nothing marked 'not for me'",
            body: "Rate outfits on the generator or here in your history." })
        : emptyStateHTML({ title: "No outfits yet", body: "Your suggestions will be listed here.",
            actionLabel: "Get dressed", actionHref: "outfit-generator.html" });
      return;
    }
    const pager = d.pages > 1 ? `<nav class="pager" aria-label="Pages">
        <button class="btn btn--sm" type="button" data-page="${d.page - 1}" ${d.page <= 1 ? "disabled" : ""}>Newer</button>
        <span>Page ${d.page} of ${d.pages}</span>
        <button class="btn btn--sm" type="button" data-page="${d.page + 1}" ${d.page >= d.pages ? "disabled" : ""}>Older</button>
      </nav>` : "";
    root.innerHTML = `<p class="result-count">${d.total} ${d.total === 1 ? "outfit" : "outfits"}</p>
      <ul class="outfit-list">${d.outfits.map((o) => `<li>${outfitCardHTML(o, {
        unit,
        extraActions: `${fbButton(o, "like")}${fbButton(o, "dislike")}<a class="btn btn--sm" href="outfit.html?id=${Number(o.id)}">Details</a>`,
      })}</li>`).join("")}</ul>${pager}`;
  }

  async function load() {
    syncTabs();
    syncUrl();
    root.setAttribute("aria-busy", "true");
    if (!state.data) root.innerHTML = `<div class="loading-block">${loaderHTML("Loading your history")}</div>`;
    try {
      state.data = await api.recommendations.history(state.page, state.verdict);
      if (state.page > state.data.pages) {
        state.page = state.data.pages;
        return load();
      }
      render();
    } catch (err) {
      root.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
    } finally {
      root.removeAttribute("aria-busy");
    }
  }

  tabs.addEventListener("click", (e) => {
    const b = e.target.closest("[data-verdict]");
    if (!b) return;
    state.verdict = b.dataset.verdict;
    state.page = 1;
    load();
  });

  root.addEventListener("click", async (e) => {
    const pageBtn = e.target.closest("[data-page]");
    if (pageBtn) {
      state.page = Number(pageBtn.dataset.page);
      await load();
      root.scrollIntoView({ block: "start" });
      return;
    }
    const fb = e.target.closest("[data-fb]");
    if (!fb) return;
    const outfit = state.data.outfits.find((o) => o.id === Number(fb.dataset.id));
    const verdict = outfit.feedback === fb.dataset.fb ? null : fb.dataset.fb;
    fb.disabled = true;
    try {
      await api.recommendations.feedback(outfit.id, verdict);
      outfit.feedback = verdict;
      if (state.verdict && verdict !== state.verdict) await load(); else render();
    } catch (err) {
      toastError(err);
      fb.disabled = false;
    }
  });

  load();
}
