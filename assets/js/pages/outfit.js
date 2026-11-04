// One outfit with its full scoring breakdown (linked from history and saved).

import { api } from "../api.js";
import { label } from "../lib/catalog.js";
import { bindOutfitActions } from "../outfit-actions.js";
import { outfitFullHTML } from "../outfit-view.js";
import { mountPhoto } from "../photo-view.js";
import { initShell } from "../shell.js";
import { emptyStateHTML, esc, watchApiStatus } from "../ui.js";

const me = await initShell("history");
if (me) start();

async function start() {
  watchApiStatus();
  const root = document.querySelector("[data-outfit]");
  const id = Number(new URLSearchParams(location.search).get("id"));

  const from = new URLSearchParams(location.search).get("from");
  if (from === "saved") {
    const back = document.querySelector("[data-back]");
    back.href = "saved-outfits.html";
    back.textContent = "Back to saved outfits";
  }

  if (!Number.isInteger(id) || id < 1) {
    root.innerHTML = emptyStateHTML({ title: "No outfit chosen", body: "Open an outfit from your history or saved list.",
      actionLabel: "Go to history", actionHref: "history.html" });
    return;
  }

  try {
    const { outfit } = await api.recommendations.get(id);
    document.querySelector("[data-outfit-title]").textContent = outfit.saved_name || `${label(outfit.occasion)} outfit`;
    document.title = `${outfit.saved_name || `${label(outfit.occasion)} outfit`}, FitCheck.AI`;
    root.innerHTML = outfitFullHTML(outfit, { unit: me.preferences.temperature_unit });
    mountPhoto(root, outfit);
    bindOutfitActions(root, outfit, {
      onUpdate: (o) => {
        if (o.saved_name) document.querySelector("[data-outfit-title]").textContent = o.saved_name;
      },
    });
  } catch (err) {
    root.innerHTML = err.status === 404
      ? emptyStateHTML({ title: "That outfit isn't here", body: "It may belong to another account or the link is wrong.",
          actionLabel: "Go to history", actionHref: "history.html" })
      : `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
  }
}
