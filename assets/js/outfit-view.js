// Rendering for outfits: the full "on the rail" view with score and care
// label, and the compact card used in history and saved lists.

import { imageSrc } from "./api.js";
import { categoryLabel, formatTemp, icon, label, WEATHER_ICONS, WEATHER_LABELS } from "./lib/catalog.js";
import { esc, formatDate } from "./ui.js";

/**
 * The picture for one garment:
 *  - a clean cut-out (lifted from the photo, or a dyed real garment when no
 *    photo was given): shown as a catalogue packshot on a studio sweep
 *  - otherwise the photo itself (the cut-out was unsure, or asked for)
 *  - neither (e.g. a watch with no photo): a swatch of its colour
 */
export function itemPicture(item, { size = "md", preferCutout = true } = {}) {
  const cut = imageSrc(item.cutout_url);
  const photo = imageSrc(item.image_url);
  if (cut && (item.image_source === "stock" || preferCutout || !photo)) {
    return `<span class="pic pic--${size} pic--cut"><img src="${esc(cut)}" alt="" loading="lazy" decoding="async"></span>`;
  }
  if (photo) {
    return `<img class="pic pic--${size}" src="${esc(photo)}" alt="" loading="lazy" decoding="async">`;
  }
  const hex = item.main_color?.hex;
  // no photo (a watch, say): its colour, honestly, rather than a drawing
  return `<span class="pic pic--${size} pic--swatch" style="--chip:${esc(hex)}" title="${esc(item.main_color?.name)}"></span>`;
}

const HOOK = `<svg class="hanger-hook" viewBox="0 0 40 26" aria-hidden="true" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 9a4 4 0 1 1 4 4c-2.2 0-4 1.4-4 3.4V18"/>
  <path d="M20 18 4 25h32Z"/></svg>`;

function railItem(item) {
  const archived = item.archived ? `<span class="rail-item__flag">No longer in wardrobe</span>` : "";
  return `<li class="rail-item">
    ${HOOK}
    <div class="swing-tag rail-item__tag">
      ${itemPicture(item, { size: "lg" })}
      <span class="rail-item__role">${esc(categoryLabel(item.role || item.category))}</span>
      <span class="swing-tag__name">${esc(item.name)}</span>
      <span class="swing-tag__meta"><span class="chip-dot" style="background:${esc(item.main_color?.hex)}"></span>${esc(item.main_color?.name)} ${esc(item.subcategory)}</span>
      ${archived}
    </div>
  </li>`;
}

export function tapeHTML(score) {
  const n = Math.max(0, Math.min(100, Number(score)));
  return `<div class="tape-readout">
    <div class="tape-readout__score">
      <span class="tape-readout__label">Score</span>
      <output class="tape-readout__number">${n}</output>
    </div>
    <div class="tape" style="--fill:${n}" role="img" aria-label="Outfit score ${n} out of 100">
      <div class="tape__ticks"></div>
    </div>
  </div>`;
}

const COMPONENT_INFO = {
  occasion: { title: "Occasion", desc: "Formality and the occasions you tagged", kind: "Rule",
    icon: '<rect x="4" y="6" width="16" height="14" rx="1.5"/><path d="M4 10.5h16M8.5 4v4m7-4v4"/>' },
  weather: { title: "Weather", desc: "Warmth, seasons, rain and snow readiness", kind: "Rule",
    icon: WEATHER_ICONS.sunny },
  color: { title: "Colour", desc: "CIELAB harmony between every pair", kind: "Rule",
    icon: '<circle cx="9.5" cy="10" r="5"/><circle cx="14.5" cy="10" r="5"/><circle cx="12" cy="14.5" r="5"/>' },
  style: { title: "Style", desc: "How well the pieces' styles agree", kind: "Rule",
    icon: '<path d="M12 4 20 20H4Z"/>' },
  ml: { title: "Taste models", desc: "Decision tree and KNN prediction", kind: "Learned",
    icon: '<circle cx="6" cy="7" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="12" cy="18" r="2"/><path d="m7.5 8.5 3.5 8m1.5 0 4-8"/>' },
  feedback: { title: "Your feedback", desc: "Similarity to outfits you rated", kind: "Learned",
    icon: '<path d="M6 20v-9h3l3-7c2 0 3 1.4 3 3.4l-.6 3.6H19c1.4 0 2.3 1.3 2 2.6l-1.3 5.2c-.3 1-1 1.6-2 1.6Z"/>' },
};

export function careLabelHTML(breakdown) {
  if (!breakdown?.components) return "";
  // MySQL's JSON type re-sorts object keys, so put them back in reading order
  const rows = Object.keys(COMPONENT_INFO).filter((k) => k in breakdown.components).map((key) => {
    const value = breakdown.components[key];
    const info = COMPONENT_INFO[key];
    const pct = Math.round(value * 100);
    const weight = Math.round((breakdown.weights?.[key] || 0) * 100);
    return `<div class="care-label__row" role="listitem">
      <span class="care-label__icon">${icon(info.icon, 30)}</span>
      <div>
        <div class="care-label__title">${info.title} <span class="care-label__kind" data-kind="${info.kind}">${info.kind}</span></div>
        <div class="care-label__desc">${info.desc}</div>
        <div class="meter" aria-hidden="true"><span style="width:${pct}%"></span></div>
      </div>
      <span class="care-label__weight"><strong>${pct}</strong><small>weight ${weight}%</small></span>
    </div>`;
  }).join("");
  const engineNote = breakdown.components.ml === undefined
    ? `<p class="care-label__foot">Scored on rules only: the learned models aren't loaded on the server.</p>`
    : breakdown.feedback_used ? "" :
      `<p class="care-label__foot">Rate a few outfits and your own likes start counting too.</p>`;
  return `<div class="care-label" role="list" aria-label="How this outfit was scored">${rows}${engineNote}</div>`;
}

export function contextLine(outfit, unit = "C") {
  const bits = [
    `<span>${esc(label(outfit.occasion))}</span>`,
    `<span class="ctx-weather">${icon(WEATHER_ICONS[outfit.weather], 16)}${esc(WEATHER_LABELS[outfit.weather])}, ${esc(formatTemp(outfit.temperature_c, unit))}</span>`,
  ];
  if (outfit.style) bits.push(`<span>${esc(label(outfit.style))}</span>`);
  if (outfit.palette && outfit.palette !== "any") bits.push(`<span>${esc(label(outfit.palette))} palette</span>`);
  return `<p class="ctx-line">${bits.join("")}</p>`;
}

function isToday(iso) {
  const d = new Date(iso);
  const n = new Date();
  return d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate();
}

export function outfitFullHTML(outfit, { unit = "C", actions = true, another = false } = {}) {
  const liked = outfit.feedback === "like";
  const disliked = outfit.feedback === "dislike";
  return `
    <article class="outfit" data-outfit-id="${Number(outfit.id)}">
      <div class="outfit__head">
        ${contextLine(outfit, unit)}
        <p class="outfit__when">${esc(formatDate(outfit.created_at))}</p>
      </div>
      <div class="outfit__main">
        <div class="outfit__model">
          <figure class="outfit-photo" data-photo-frame>
            <div class="outfit-photo__media">${outfit.photo_url
              ? `<img class="outfit-photo__img" src="${esc(outfit.photo_url)}" alt="AI photo of a person wearing ${esc(outfit.items.map((i) => i.name).join(", "))}">`
              : `<div class="darkroom" aria-hidden="true"></div>`}</div>
            <figcaption class="outfit-photo__label">${outfit.photo_url ? "AI photo" : "Developing the photo…"}</figcaption>
          </figure>
          <p class="outfit-photo__about">AI-generated photo of a person wearing these pieces. <a href="privacy.html#photos">How photos are made</a></p>
          <ul class="photo-strip" data-photo-strip aria-label="Photos of this outfit"></ul>
          <div class="outfit-photo__actions">
            <button class="btn btn--sm" type="button" data-new-photo hidden>New photo</button>
            <button class="btn btn--sm" type="button" data-download-look>Download</button>
            <button class="btn btn--sm" type="button" data-share hidden>Share</button>
          </div>
        </div>
        <div class="outfit__score">
          ${tapeHTML(outfit.score)}
          <p class="outfit__why">${esc(outfit.explanation)}</p>
          ${actions ? `<div class="outfit__actions">
            <button class="btn feedback-btn" type="button" data-feedback="like" aria-pressed="${liked}">
              ${icon('<path d="M6 20v-9h3l3-7c2 0 3 1.4 3 3.4l-.6 3.6H19c1.4 0 2.3 1.3 2 2.6l-1.3 5.2c-.3 1-1 1.6-2 1.6Z"/>', 18)}
              ${liked ? "Liked" : "Like"}
            </button>
            <button class="btn feedback-btn" type="button" data-feedback="dislike" aria-pressed="${disliked}">
              ${icon('<path d="M18 4v9h-3l-3 7c-2 0-3-1.4-3-3.4l.6-3.6H5c-1.4 0-2.3-1.3-2-2.6l1.3-5.2C4.6 4.6 5.3 4 6.3 4Z"/>', 18)}
              Not for me
            </button>
            <button class="btn ${outfit.saved ? "" : "btn--primary"}" type="button" data-save ${outfit.saved ? 'aria-pressed="true"' : ""}>
              ${outfit.saved ? "Saved" : "Save outfit"}
            </button>
            ${another ? `<button class="btn btn--tape" type="button" data-another>Show me another</button>` : ""}
            <button class="btn" type="button" data-wear aria-pressed="${Boolean(outfit.worn_at && isToday(outfit.worn_at))}">
              ${outfit.worn_at && isToday(outfit.worn_at) ? "Wearing it today" : "I'm wearing this today"}
            </button>
          </div>` : ""}
          ${careLabelHTML(outfit.breakdown)}
        </div>
      </div>
      <h2 class="outfit__sub">The pieces</h2>
      <ul class="rail" aria-label="Outfit pieces" tabindex="0">${outfit.items.map(railItem).join("")}</ul>
    </article>`;
}

// "LIGHT BLUE / NAVY": the colour pairing, the way lookbooks caption outfits
export function colourCaption(items) {
  const name = (cat) => items.find((i) => (i.role || i.category) === cat)?.main_color?.name;
  return [name("dress") || name("top"), name("bottom")].filter(Boolean).join(" / ");
}

export function outfitCardHTML(outfit, { unit = "C", title, extraActions = "", level = 2, look = false } = {}) {
  const thumbs = outfit.items.slice(0, 5).map((it) => `<li>${itemPicture(it, { size: "sm", preferCutout: true })}</li>`).join("");
  const heading = title || outfit.saved_name || `${label(outfit.occasion)} outfit`;
  const verdict = outfit.feedback === "like" ? `<span class="verdict verdict--like">Liked</span>`
    : outfit.feedback === "dislike" ? `<span class="verdict verdict--dislike">Not for me</span>` : "";
  const picture = look && outfit.photo_url
    ? `<figure class="look look--card look--photo"><div class="look__frame"><img src="${esc(outfit.photo_url)}" alt="AI photo of this outfit" loading="lazy"></div>
        <figcaption class="look__caption">${esc(colourCaption(outfit.items))}</figcaption></figure>`
    : `<ul class="outfit-card__thumbs" aria-label="${esc(outfit.items.map((i) => i.name).join(", "))}">${thumbs}</ul>`;
  return `<article class="outfit-card${look ? " outfit-card--look" : ""}" data-outfit-id="${Number(outfit.id)}">
    ${picture}
    <div class="outfit-card__body">
      <h${level} class="outfit-card__title"><a href="outfit.html?id=${Number(outfit.id)}">${esc(heading)}</a></h${level}>
      ${contextLine(outfit, unit)}
      <p class="outfit-card__meta"><span class="score-pill">${Number(outfit.score)}</span>${verdict}<span>${esc(formatDate(outfit.created_at))}</span></p>
    </div>
    ${extraActions ? `<div class="outfit-card__actions">${extraActions}</div>` : ""}
  </article>`;
}
