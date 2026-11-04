// The realistic photo on an outfit: shows the stored photo, or makes one
// with the photo engine the person chose (the free open-source one by
// default, so it works with no setup). Used by the generator and the
// single-outfit page.

import { api, ApiError } from "./api.js";
import { esc } from "./ui.js";

let statusCache = null;
export async function photoStatus({ refresh = false } = {}) {
  if (!statusCache || refresh) statusCache = api.photos.status().catch(() => ({ configured: true, engine: "free" }));
  return statusCache;
}
export function forgetPhotoStatus() { statusCache = null; }

function setOverlay(frame, html) {
  frame.querySelector(".outfit-photo__overlay")?.remove();
  if (!html) return;
  const div = document.createElement("div");
  div.className = "outfit-photo__overlay";
  div.innerHTML = html;
  frame.append(div);
}

/**
 * root:   element holding outfitFullHTML
 * outfit: the outfit object (gets photo_url set when a photo arrives)
 */
export async function mountPhoto(root, outfit) {
  const frame = root.querySelector("[data-photo-frame]");
  if (!frame) return;
  const again = root.querySelector("[data-new-photo]");
  const strip = root.querySelector("[data-photo-strip]");

  // earlier takes of this outfit: tap one to make it the outfit's photo
  function renderStrip(photos = []) {
    if (!strip) return;
    strip.hidden = photos.length < 2;
    strip.innerHTML = photos.map((p) => `<li><button type="button" class="photo-strip__pick" data-pick="${p.index}"
        aria-pressed="${p.cover}" aria-label="Photo ${p.index + 1}${p.cover ? " (shown)" : ""}">
        <img src="${esc(p.url)}" alt="" loading="lazy"></button></li>`).join("");
    strip.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", async () => {
      try {
        const res = await api.photos.choose(outfit.id, Number(b.dataset.pick));
        outfit.photo_url = res.photo_url;
        outfit.photos = res.photos;
        await showPhoto(res.photo_url, res.model);
        renderStrip(res.photos);
      } catch { /* the strip stays as it was */ }
    }));
  }
  const label = frame.querySelector(".outfit-photo__label");
  const names = outfit.items.map((i) => i.name).join(", ");

  const showPhoto = (url, model) => new Promise((resolve) => {
    const img = new Image();
    img.className = "outfit-photo__img";
    img.alt = `AI photo of a person wearing ${names}`;
    img.decoding = "async";
    img.onload = () => {
      frame.classList.add("has-photo");
      frame.querySelector(".outfit-photo__media").replaceChildren(img);
      label.textContent = `AI photo${model ? ` · ${model}` : ""}`;
      setOverlay(frame, "");
      if (again) again.hidden = false;
      resolve(true);
    };
    img.onerror = () => resolve(false);
    img.src = url;
  });

  async function make(force = false) {
    frame.setAttribute("aria-busy", "true");
    if (again) again.disabled = true;
    const status = await photoStatus();
    const engine = status.engine === "gemini" ? "Gemini" : "the free image model";
    const waitHTML = (extra = "") => `<div class="photo-wait" role="status">
        <span class="photo-wait__flash" aria-hidden="true"></span>
        <strong>Photographing your outfit…</strong>
        <span>${extra || `Usually 10 to 40 seconds with ${esc(engine)}.`}</span>
      </div>`;
    setOverlay(frame, waitHTML());
    label.textContent = "Developing the photo…";
    try {
      const res = await api.photos.forOutfit(outfit.id, {
        force,
        onWait: (s) => setOverlay(frame, waitHTML(`The free service is busy; waiting ${s} s for a slot…`)),
      });
      // a URL-only answer still has to download; wait for it before showing
      if (!(await showPhoto(res.photo_url, res.model))) throw new ApiError("The photo didn't download. Try again.", { code: "photo_failed" });
      outfit.photo_url = res.photo_url;
      outfit.photos = res.photos;
      renderStrip(res.photos);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Couldn't make the photo.";
      const keyProblem = err?.code === "photo_bad_key" || err?.code === "photo_key_missing";
      label.textContent = "No photo yet";
      setOverlay(frame, `<div class="photo-wait photo-wait--error" role="alert">
          <strong>No photo this time</strong><span>${esc(msg)}</span>
          <span class="photo-wait__row">
            <button class="btn btn--sm btn--primary" type="button" data-photo-retry>Try again</button>
            ${keyProblem ? `<a class="btn btn--sm" href="profile.html#photos">Photo settings</a>` : ""}
          </span>
        </div>`);
      frame.querySelector("[data-photo-retry]").addEventListener("click", () => make(force));
      if (keyProblem) forgetPhotoStatus();
    } finally {
      frame.removeAttribute("aria-busy");
      if (again) again.disabled = false;
    }
  }

  again?.addEventListener("click", () => make(true));

  if (outfit.photo_url && (await showPhoto(outfit.photo_url, outfit.photo_model))) {
    renderStrip(outfit.photos || []);
    return;
  }
  make(false);
}
