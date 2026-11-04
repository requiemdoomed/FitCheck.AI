// Outfit generator: pick the situation, get an outfit from your own wardrobe.

import { api, ApiError } from "../api.js";
import { CATALOG, icon, label, PALETTE_SWATCHES, toC, WEATHER_ICONS, WEATHER_LABELS } from "../lib/catalog.js";
import { bindOutfitActions } from "../outfit-actions.js";
import { mountPhoto } from "../photo-view.js";
import { outfitFullHTML } from "../outfit-view.js";
import { initShell } from "../shell.js";
import { localWeather } from "../local/weather.js";
import { esc, loaderHTML, toast, watchApiStatus } from "../ui.js";

const me = await initShell("generator");
if (me) start();

const LAST_KEY = "fitcheck.generator.last";

function start() {
  watchApiStatus();
  const prefs = me.preferences;
  const unit = prefs.temperature_unit || "C";
  const form = document.querySelector("[data-gen-form]");
  const result = document.querySelector("[data-result]");
  const temp = form.querySelector("[data-temp]");
  const readout = form.querySelector("[data-temp-readout]");
  const button = form.querySelector("[data-generate]");

  // the last choices this tab made, so "back" from another page keeps them
  let last = {};
  try { last = JSON.parse(sessionStorage.getItem(LAST_KEY) || "{}"); } catch { last = {}; }

  const radio = (name, value, text, checked, extra = "") =>
    `<label class="chip"><input type="radio" name="${name}" value="${value}" ${checked ? "checked" : ""}><span>${extra}${text}</span></label>`;

  form.querySelector("[data-occasions]").innerHTML = CATALOG.occasions.map((o) =>
    radio("occasion", o, label(o), o === (last.occasion || prefs.default_occasion || "casual"))).join("");
  form.querySelector("[data-weather]").innerHTML = CATALOG.weather.map((w) =>
    radio("weather", w, WEATHER_LABELS[w], w === (last.weather || "sunny"), icon(WEATHER_ICONS[w], 18))).join("");
  form.querySelector("[data-styles]").innerHTML = radio("style", "", "Any", !last.style) +
    CATALOG.styles.map((s) => radio("style", s, label(s), s === last.style)).join("");
  form.querySelector("[data-palettes]").innerHTML = CATALOG.palettes.map((p) => {
    const sw = PALETTE_SWATCHES[p].map((h) => `<i style="background:${h}"></i>`).join("");
    return radio("palette", p, p === "any" ? "Any" : label(p), p === (last.palette || prefs.preferred_palette || "any"),
      sw ? `<span class="mini-swatches" aria-hidden="true">${sw}</span>` : "");
  }).join("");
  if (last.style || (last.palette && last.palette !== "any")) form.querySelector(".gen-more").open = true;

  // slider works in the person's own unit
  if (unit === "F") {
    temp.min = -4; temp.max = 104; temp.value = last.tempF ?? 64;
  } else if (last.tempC !== undefined) {
    temp.value = last.tempC;
  }
  const showTemp = () => { readout.textContent = `${temp.value}°${unit}`; };

  // fill weather and temperature from Open-Meteo, only when asked
  const auto = form.querySelector("[data-local-weather]");
  auto.addEventListener("click", async () => {
    auto.disabled = true;
    auto.textContent = "Checking the sky…";
    try {
      const w = await localWeather();
      const r = form.querySelector(`[name="weather"][value="${w.weather}"]`);
      if (r) r.checked = true;
      temp.value = unit === "F" ? Math.round(w.temperature_c * 9 / 5 + 32) : w.temperature_c;
      showTemp();
      toast(`Right now: ${WEATHER_LABELS[w.weather].toLowerCase()}, ${temp.value}°${unit}.`, "success", { duration: 3500 });
    } catch (err) {
      toast(err.message || "Couldn't get the weather.", "error");
    } finally {
      auto.disabled = false;
      auto.textContent = "Use my local weather";
    }
  });
  temp.addEventListener("input", showTemp);
  showTemp();

  const state = { seen: [], current: null, contextKey: "" };

  function criteria() {
    const value = (name) => form.querySelector(`[name="${name}"]:checked`)?.value || "";
    const t = Number(temp.value);
    return {
      occasion: value("occasion"),
      weather: value("weather"),
      temperature_c: unit === "F" ? toC(t) : t,
      style: value("style") || null,
      palette: value("palette") || "any",
    };
  }

  function remember(c) {
    const saved = { occasion: c.occasion, weather: c.weather, style: c.style, palette: c.palette };
    if (unit === "F") saved.tempF = Number(temp.value); else saved.tempC = Number(temp.value);
    try { sessionStorage.setItem(LAST_KEY, JSON.stringify(saved)); } catch { /* fine */ }
  }

  function emptyView() {
    result.innerHTML = `<div class="gen-empty">
      <div>
        <ul class="flatlay" aria-label="A white tee, light jeans and white trainers, waiting to be worn">
          <li><img src="assets/images/garments/cutouts/plain-white-tee.webp" alt=""></li>
          <li><img src="assets/images/garments/cutouts/light-wash-jeans.webp" alt=""></li>
          <li><img src="assets/images/garments/cutouts/white-sneakers.webp" alt=""></li>
        </ul>
        <p>Choose where you're going and what the weather's like,<br>then press <strong>Find my outfit</strong>. You'll see it as a photo on a real-looking person.</p>
      </div>
    </div>`;
  }

  async function generate({ another = false } = {}) {
    const c = criteria();
    const key = JSON.stringify(c);
    if (key !== state.contextKey) {
      state.seen = [];
      state.contextKey = key;
    }
    remember(c);

    const body = { ...c };
    if (another && state.current) {
      body.exclude = state.seen.slice(-200);
      body.previous_id = state.current.id;
    }

    button.disabled = true;
    result.setAttribute("aria-busy", "true");
    if (!another) result.innerHTML = `<div class="loading-block">${loaderHTML("Looking through your wardrobe")}</div>`;
    const anotherBtn = result.querySelector("[data-another]");
    if (anotherBtn) { anotherBtn.disabled = true; anotherBtn.textContent = "Finding another…"; }

    try {
      const res = await api.recommendations.generate(body);
      const outfit = res.outfit;
      state.current = outfit;
      if (outfit.signature) state.seen.push(outfit.signature);
      result.innerHTML = outfitFullHTML(outfit, { unit, another: true });
      mountPhoto(result, outfit);
      bindOutfitActions(result, outfit, { onAnother: () => generate({ another: true }) });
      if (window.matchMedia("(max-width: 1000px)").matches) {
        result.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      showError(err, another);
    } finally {
      button.disabled = false;
      result.removeAttribute("aria-busy");
    }
  }

  function showError(err, another = false) {
    if (err instanceof ApiError && err.code === "wardrobe_incomplete") {
      result.innerHTML = `<div class="gen-empty"><div>
        <h2>Your wardrobe needs a few more pieces</h2>
        <p style="margin:var(--s3) auto var(--s4)">${esc(err.message)}</p>
        <a class="btn btn--primary" href="wardrobe.html#add">Add clothes</a></div></div>`;
      return;
    }
    if (err instanceof ApiError && err.code === "no_more_combinations") {
      const notice = `<div class="notice notice--warn" role="status" style="margin-bottom:var(--s4)">${esc(err.message)}</div>`;
      if (state.current) {
        result.insertAdjacentHTML("afterbegin", notice);
        const btn = result.querySelector("[data-another]");
        if (btn) { btn.disabled = true; btn.textContent = "No more combinations"; }
      } else {
        result.innerHTML = notice;
      }
      return;
    }
    const message = err instanceof ApiError ? err.message : "Something went wrong. Try again.";
    if (!(err instanceof ApiError)) console.error(err);
    if (another && state.current) {
      // keep the outfit on screen; just say what happened
      toast(message, "error");
      const btn = result.querySelector("[data-another]");
      if (btn) { btn.disabled = false; btn.textContent = "Show me another"; }
      return;
    }
    result.innerHTML = `<div class="notice notice--error" role="alert">${esc(message)}</div>`;
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    generate();
  });

  emptyView();
}
