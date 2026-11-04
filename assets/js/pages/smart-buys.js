// Smart buys: a short list of cheap basics, each shown on the model with
// clothes the person already owns, and an "I've got it" button that adds it
// to the wardrobe.

import { api } from "../api.js";
import { label } from "../lib/catalog.js";
import { colourCaption } from "../outfit-view.js";
import { initShell } from "../shell.js";
import { demoWardrobeButton, esc, toast, toastError, watchApiStatus, withBusy } from "../ui.js";

const me = await initShell("shop");
if (me) start();

function cardHTML(s, i) {
  const others = s.outfit.items.filter((it) => !it.shop).map((it) => it.name);
  const caption = colourCaption(s.outfit.items);
  const reasons = s.reasons.filter((r) => !r.startsWith("Makes "));
  const unlock = s.unlocks
    ? `<span class="shop-card__unlock">makes <strong>${s.unlocks}</strong> outfit${s.unlocks === 1 ? "" : "s"} with your clothes</span>`
    : "";
  const shownWith = s.outfit.with_basics
    ? `Shown with other basics, since your wardrobe can't finish this outfit yet.`
    : `Shown with your ${others.map(esc).join(", ")}.`;
  return `<li class="shop-card" style="--tilt:${i % 2 ? 0.6 : -0.6}deg">
    <figure class="look look--card shop-card__picture">
      <div class="look__frame">${s.image_url
        ? `<img class="shop-card__product" src="${esc(s.image_url)}" alt="${esc(s.name)}">`
        : `<span class="shop-card__swatch" style="--sw:${esc(s.color.hex)}"></span>`}</div>
      <figcaption class="look__caption">${esc(caption)}</figcaption>
    </figure>
    <div class="shop-card__body">
      <div class="shop-card__head">
        <h2 class="shop-card__name"><span class="chip-dot" style="background:${esc(s.color.hex)}"></span>${esc(s.name)}</h2>
        <span class="price-tag">${esc(s.price)}</span>
      </div>
      ${unlock}
      <p class="shop-card__why">${esc(s.why)}</p>
      ${reasons.length ? `<ul class="shop-card__reasons">${reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      <p class="shop-card__with">${shownWith} Best for ${esc(label(s.outfit.occasion).toLowerCase())}, scoring ${s.outfit.score}.</p>
      <div class="shop-card__actions">
        <button class="btn btn--primary" type="button" data-add="${esc(s.key)}">I've got one, add it to my wardrobe</button>
        <button class="btn" type="button" data-photo="${esc(s.key)}">See it on a real person</button>
      </div>
    </div>
  </li>`;
}

async function start() {
  watchApiStatus();
  const root = document.querySelector("[data-shop]");

  async function load() {
    try {
      const res = await api.shop.suggest();
      if (!res.suggestions.length) {
        root.innerHTML = `<div class="empty-state"><h2 class="empty-state__title">Your basics are covered</h2>
          <p>You already own every basic on the list in a colour that works. Nice.</p></div>`;
        return;
      }
      const intro = res.wardrobe_size < 3
        ? `<div class="notice shop-intro"><div><strong>These are general picks for now.</strong>
            <p>Add a few of your own clothes (or the demo wardrobe) and the list will be worked out around them.</p></div></div>`
        : "";
      root.innerHTML = `${intro}<ul class="shop-grid">${res.suggestions.map(cardHTML).join("")}</ul>`;
      if (res.wardrobe_size < 3) root.querySelector(".shop-intro > div").append(demoWardrobeButton(load));
      root.querySelectorAll("[data-photo]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const card = btn.closest(".shop-card");
          try {
            const res = await withBusy(btn, () => api.photos.forSuggestion(btn.dataset.photo, {
              onWait: (sec) => { btn.textContent = `Busy, waiting ${sec} s…`; },
            }), "Photographing… (10–40 s)");
            const img = new Image();
            img.className = "shop-card__photo";
            img.alt = "AI photo of a person wearing this outfit";
            img.onload = () => { card.querySelector(".look__frame").replaceChildren(img); card.querySelector(".look").classList.add("look--photo"); };
            img.onerror = () => toastError(new Error("download"), "The photo didn't download. Try again.");
            img.src = res.photo_url;
            btn.textContent = "New photo";
          } catch (err) {
            toastError(err, "Couldn't make the photo.");
          }
        });
      });
      root.querySelectorAll("[data-add]").forEach((btn) => btn.addEventListener("click", async () => {
        try {
          const { item } = await withBusy(btn, () => api.shop.add(btn.dataset.add), "Adding…");
          toast(`${item.name} added to your wardrobe.`, "success");
          await load();
        } catch (err) {
          toastError(err);
        }
      }));
    } catch (err) {
      root.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
    }
  }
  load();
}
