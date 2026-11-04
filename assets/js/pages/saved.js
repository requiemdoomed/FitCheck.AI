// Saved outfits.

import { api } from "../api.js";
import { outfitCardHTML } from "../outfit-view.js";
import { initShell } from "../shell.js";
import { confirmDialog, emptyStateHTML, esc, toast, toastError, watchApiStatus } from "../ui.js";

const me = await initShell("saved");
if (me) start();

async function start() {
  watchApiStatus();
  const root = document.querySelector("[data-saved]");
  const unit = me.preferences.temperature_unit;
  let outfits = [];

  function render() {
    if (!outfits.length) {
      root.innerHTML = emptyStateHTML({
        title: "Nothing saved yet",
        body: "When an outfit's a keeper, press Save outfit and it'll wait for you here.",
        actionLabel: "Get dressed",
        actionHref: "outfit-generator.html",
      });
      return;
    }
    root.innerHTML = `<ul class="outfit-list outfit-list--grid">${outfits.map((o) => `<li>${outfitCardHTML(o, {
      unit, look: true,
      extraActions: `<a class="btn btn--sm" href="outfit.html?id=${Number(o.id)}&from=saved">View</a>
        <button class="btn btn--sm btn--quiet" type="button" data-unsave="${Number(o.saved_id)}">Remove</button>`,
    })}</li>`).join("")}</ul>`;
  }

  root.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-unsave]");
    if (!btn) return;
    const outfit = outfits.find((o) => o.saved_id === Number(btn.dataset.unsave));
    const ok = await confirmDialog({
      title: `Remove "${outfit?.saved_name}" from saved?`,
      body: "It stays in your outfit history.",
      confirmLabel: "Remove",
    });
    if (!ok) return;
    try {
      await api.outfits.unsave(btn.dataset.unsave);
      outfits = outfits.filter((o) => o.saved_id !== Number(btn.dataset.unsave));
      render();
      toast("Removed from saved outfits.", "success");
    } catch (err) {
      toastError(err);
    }
  });

  try {
    outfits = (await api.outfits.saved()).outfits;
    render();
  } catch (err) {
    root.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
  }
}
