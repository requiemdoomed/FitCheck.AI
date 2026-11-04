// Landing page: mix real pieces and see them on a person, the dye demo,
// and a lookbook of cheap pairings as realistic AI photos.
//
// The pieces are real CC0 garment photos (assets/images/garments). Photos of
// people are made on the FitCheck.AI server by free open-source models
// (Pollinations), cached so a repeat costs nothing, and limited per visitor.

import { api, session } from "../api.js";
import { nearestName } from "../engine/color.js";
import { pairHarmony, hexToLab, isNeutral } from "../lib/color.js";
import { initTheme } from "../theme.js";
import { esc, watchApiStatus } from "../ui.js";

const MIX = {
  top: ["tropical-print-shirt", "breton-stripe-tee", "hot-pink-tee", "sunshine-tee", "pale-blue-oxford", "red-check-shirt"],
  bottom: ["light-wash-jeans", "mustard-trousers", "white-shorts", "red-mini-skirt", "black-wide-trousers", "dark-denim"],
  shoes: ["white-sneakers", "brown-derbies", "blue-runners", "white-flats", "brown-boots"],
};
const LABELS = { top: "Top", bottom: "Bottom", shoes: "Shoes" };

const picked = { top: 0, bottom: 0, shoes: 0 };
let catalog = {};
let backdrop = 0;

const stage = document.querySelector("[data-stage]");
const scoreEl = document.querySelector("[data-score]");
const verdictEl = document.querySelector("[data-verdict]");

function piece(slot) {
  return catalog[MIX[slot][picked[slot]]];
}

function colourWord(g) {
  return g.main_color_name;
}

function buildStrip(strip) {
  const slot = strip.dataset.slot;
  strip.innerHTML = `
    <button class="icon-btn" type="button" data-step="-1" aria-label="Previous ${slot === "shoes" ? "shoes" : LABELS[slot].toLowerCase()}">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 4-6 6 6 6"/></svg>
    </button>
    <div class="strip__stage" aria-live="polite">
      <span class="strip__slot" id="slot-${slot}">${LABELS[slot]}</span>
      <span class="strip__name" aria-labelledby="slot-${slot}"></span>
    </div>
    <button class="icon-btn" type="button" data-step="1" aria-label="Next ${slot === "shoes" ? "shoes" : LABELS[slot].toLowerCase()}">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m8 4 6 6-6 6"/></svg>
    </button>`;
  strip.querySelectorAll("[data-step]").forEach((btn) =>
    btn.addEventListener("click", () => step(slot, Number(btn.dataset.step))));
}

function renderNames() {
  for (const slot of Object.keys(MIX)) {
    const g = piece(slot);
    document.querySelector(`[data-slot="${slot}"] .strip__name`).innerHTML =
      `<span class="strip__chip" style="background:${esc(g.main_color)}"></span>${esc(g.name)}`;
  }
}

function stagePieces() {
  return ["top", "bottom", "shoes"].map((slot) => piece(slot));
}

// the chosen pieces as a flat lay of their real photos, plus a button to see them worn
function renderStage() {
  const pieces = stagePieces();
  stage.innerHTML = `<div class="stage-photo">
      <ul class="flatlay flatlay--stage" aria-label="${esc(pieces.map((g) => g.name).join(", "))}">
        ${pieces.map((g) => `<li><img src="${esc(g.cutout || g.image)}" alt=""></li>`).join("")}
      </ul>
      <button class="btn btn--primary stage-photo__go" type="button" data-wear>See it on a person</button>
    </div>`;
  stage.querySelector("[data-wear]").addEventListener("click", wearIt);
}

let wearToken = 0;
async function wearIt() {
  const token = ++wearToken;
  const pieces = stagePieces();
  const btn = stage.querySelector("[data-wear]");
  btn.disabled = true;
  btn.textContent = "Photographing… (10–40 s)";
  try {
    const described = pieces.map((g) => ({
      role: g.category, subcategory: g.subcategory, colour: g.main_color_name,
      pattern: g.pattern || "", secondary: g.pattern ? nameOfHex(g.secondary_color) : "",
    }));
    const fem = pieces.some((g) => /skirt|dress/.test(g.subcategory) || g.subcategory === "flats");
    const res = await api.photos.sample({ pieces: described, person: { build: fem ? "fem" : "masc", skin: "medium" },
      occasion: "casual", backdrop: backdrop % 6 });
    if (token !== wearToken) return;
    const img = new Image();
    img.className = "stage-photo__img";
    img.alt = `AI photo of a person wearing ${pieces.map((g) => g.name).join(", ")}`;
    img.onload = () => {
      if (token !== wearToken) return;
      stage.innerHTML = "";
      const wrap = document.createElement("div");
      wrap.className = "stage-photo stage-photo--done";
      wrap.append(img);
      stage.append(wrap);
    };
    img.onerror = () => { btn.disabled = false; btn.textContent = "Couldn't load. Try again"; };
    img.src = res.photo_url;
  } catch (err) {
    if (token === wearToken) { btn.disabled = false; btn.textContent = err?.code === "photo_quota" ? "Sample limit reached. Sign up to see yours" : "The photo service is busy. Try again"; }
  }
}

function nameOfHex(hex) {
  return hex ? nearestName(hex) : "";
}

function step(slot, dir) {
  const n = MIX[slot].length;
  picked[slot] = (picked[slot] + dir + n) % n;
  update();
}

function shuffle() {
  for (const slot of Object.keys(MIX)) {
    let next;
    do { next = Math.floor(Math.random() * MIX[slot].length); } while (next === picked[slot]);
    picked[slot] = next;
  }
  backdrop += 1;
  update();
}

// Top/bottom is the pairing people notice most, so it carries half the weight.
function scoreOutfit(top, bottom, shoes) {
  const tb = pairHarmony(top.main_color, bottom.main_color);
  const bs = pairHarmony(bottom.main_color, shoes.main_color);
  const ts = pairHarmony(top.main_color, shoes.main_color);
  let score = tb.score * 0.5 + bs.score * 0.25 + ts.score * 0.25;
  const loud = [top, bottom, shoes].filter((g) => !isNeutral(hexToLab(g.main_color))).length;
  if (loud === 3) score -= 0.08;
  return { score: Math.round(Math.max(0, Math.min(1, score)) * 100), tb, loud };
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function verdict(top, bottom, shoes, { score, tb, loud }) {
  const t = colourWord(top), b = colourWord(bottom);
  const topNeutral = isNeutral(hexToLab(top.main_color));
  const lines = {
    "neutral-contrast": `${cap(t)} and ${b} are both neutrals with clear contrast: clean and deliberate.`,
    "neutral-flat": `${cap(t)} and ${b} are quiet neutrals. Safe, if a little flat; a bright piece would give it a focus.`,
    anchored: `The ${topNeutral ? t + " top" : b + " bottom"} anchors the look, so the ${topNeutral ? b : t} can carry the colour.`,
    tonal: `${cap(t)} and ${b} sit close on the colour wheel, so they read as one tonal idea.`,
    analogous: `${cap(t)} and ${b} are colour-wheel neighbours. Harmonious, especially with a lightness change.`,
    complementary: `${cap(t)} and ${b} are near-opposites: bold contrast that works when the rest stays calm.`,
    clash: `${cap(t)} and ${b} compete without being true opposites. That's where clashes live.`,
  };
  let text = lines[tb.kind];
  if (loud === 3) text += ` Three saturated colours is busy; neutral shoes would calm it.`;
  else if (score >= 85) text += " Easy to wear.";
  return text;
}

function update() {
  renderNames();
  renderStage();
  const top = piece("top"), bottom = piece("bottom"), shoes = piece("shoes");
  const result = scoreOutfit(top, bottom, shoes);
  scoreEl.textContent = result.score;
  verdictEl.textContent = verdict(top, bottom, shoes, result);
}

function buildRailShow(items) {
  const track = document.querySelector("[data-rail-show]");
  const figs = items.map((g, i) => `<figure style="--tilt:${(i % 2 ? 2 : -2) + (i % 3) - 1}deg">
      <img src="${esc(g.image)}" alt="${esc(g.name)}" loading="lazy" width="170" height="212">
      <figcaption>${esc(g.name)}</figcaption></figure>`).join("");
  // two copies so the loop is seamless; the second is hidden from screen readers
  track.innerHTML = figs + `<div aria-hidden="true" style="display:contents">${figs}</div>`;
}

// ---- dye demo ----
const DYES = { black: "#1b1b1d", red: "#c42b2b", navy: "#1f2a4a", mint: "#a8dcc0", mustard: "#c99a2e", pink: "#e88aa8" };

function buildDyes() {
  const box = document.querySelector("[data-dye]");
  box.innerHTML = Object.entries(DYES).map(([name, hex], i) =>
    `<button class="dye" type="button" style="--sw:${hex}" data-colour="${name}" aria-pressed="${i === 0}"
       aria-label="${cap(name)}" title="${cap(name)}"></button>`).join("");
  box.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-colour]");
    if (!btn) return;
    const c = btn.dataset.colour;
    box.querySelectorAll("[data-colour]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
    for (const kind of ["hoodie", "jeans"]) {
      const img = document.querySelector(`[data-dye-img="${kind}"]`);
      img.src = `assets/images/stock-demo/${kind}-${c}.webp`;
      img.alt = `A real ${kind === "hoodie" ? "hoodie" : "pair of jeans"} photo dyed ${c}`;
      document.querySelector(`[data-dye-caption="${kind}"]`).textContent = `${cap(c)} ${kind}`;
    }
  });
}

// ---- go ----

if (session.isSignedIn) {
  document.querySelectorAll('a[href="register.html"]').forEach((a) => {
    a.href = "dashboard.html";
    a.textContent = "Open my wardrobe";
  });
  document.querySelectorAll('a[href="login.html"]').forEach((a) => {
    if (a.closest(".hero__ctas")) a.remove();
    else a.hidden = true;
  });
}

initTheme();
watchApiStatus();
buildDyes();
document.querySelectorAll(".mixer .strip").forEach(buildStrip);
document.querySelector("[data-shuffle]").addEventListener("click", shuffle);

fetch("assets/images/garments/catalog.json")
  .then((r) => r.json())
  .then((list) => {
    catalog = Object.fromEntries(list.map((g) => [g.slug, g]));
    buildRailShow(list.filter((g) => g.category !== "accessory").slice(0, 24));
    update();
  })
  .catch((err) => {
    console.error(err);
    stage.textContent = "The demo wardrobe couldn't load.";
  });


// ---- the lookbook: cheap pairings as realistic photos ----
// Loaded one after another, only once the section scrolls into view. The
// server keeps each photo once made, so later visitors see them at once.

const PAIRINGS = [
  { top: ["shirt", "light blue"], bottom: ["chinos", "navy"], shoes: ["loafers", "brown"], build: "masc", skin: "light" },
  { top: ["shirt", "burgundy"], bottom: ["chinos", "cream"], shoes: ["loafers", "brown"], build: "masc", skin: "tan" },
  { top: ["blouse", "white"], bottom: ["skirt", "black"], shoes: ["flats", "black"], build: "fem", skin: "deep" },
  { top: ["t-shirt", "navy"], bottom: ["jeans", "light blue"], shoes: ["sneakers", "white"], build: "masc", skin: "medium" },
];

function renderPairings() {
  const grid = document.querySelector("[data-pairings]");
  if (!grid) return;
  grid.innerHTML = PAIRINGS.map((p) => `<li><figure class="look look--card">
      <div class="look__frame"><div class="darkroom" aria-hidden="true"></div></div>
      <figcaption class="look__caption">${esc(p.top[1])} / ${esc(p.bottom[1])}</figcaption></figure></li>`).join("");
  const start = async () => {
    for (const [i, p] of PAIRINGS.entries()) {
      const pieces = [
        { role: "top", subcategory: p.top[0], colour: p.top[1] },
        { role: "bottom", subcategory: p.bottom[0], colour: p.bottom[1] },
        { role: "footwear", subcategory: p.shoes[0], colour: p.shoes[1] },
      ];
      const frame = grid.children[i].querySelector(".look__frame");
      let url;
      try {
        url = (await api.photos.sample({ pieces, person: { build: p.build, skin: p.skin }, occasion: "work", backdrop: i })).photo_url;
      } catch {
        frame.querySelector(".darkroom")?.classList.add("darkroom--failed");
        continue;
      }
      await new Promise((resolve) => {
        const img = new Image();
        img.alt = `AI photo: ${p.top[1]} ${p.top[0]} with ${p.bottom[1]} ${p.bottom[0]} and ${p.shoes[1]} ${p.shoes[0]}`;
        img.loading = "eager";
        img.onload = () => { frame.replaceChildren(img); frame.parentElement.classList.add("look--photo"); resolve(); };
        img.onerror = () => { frame.querySelector(".darkroom")?.classList.add("darkroom--failed"); resolve(); };
        img.src = url;
      });
    }
  };
  if (!("IntersectionObserver" in window)) return start();
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); start(); }
  }, { rootMargin: "200px" });
  io.observe(grid);
}

renderPairings();
