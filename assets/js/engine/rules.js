// Rule-based scoring: the parts of "does this outfit work?" that are true
// for everyone. A line-for-line port of ml/fitcheck_ml/rules.py, kept
// separate from the learned models (taste.js). tests/engine checks the two
// implementations agree.

import { outfitHarmony, paletteFit } from "./color.js";
import { pyRound, pySum } from "./num.js";
import { CATEGORY_DEFAULTS, OCCASION_RULES, STYLE_AFFINITY, SUBCATEGORIES } from "./data.js";

export const CORE_ROLES = ["top", "bottom", "dress", "footwear"];
const ROLE_WEIGHT = { top: 1.0, bottom: 1.0, dress: 2.0, footwear: 1.0, outerwear: 0.7, accessory: 0.3 };

const AFFINITY = new Map();
for (const [a, b, v] of STYLE_AFFINITY) {
  AFFINITY.set(`${a}|${b}`, v);
  AFFINITY.set(`${b}|${a}`, v);
}

export function styleAffinity(a, b) {
  if (a === b) return 1;
  return AFFINITY.get(`${a}|${b}`) || 0.3;
}

export function attributes(category, subcategory) {
  const sub = (subcategory || "").trim().toLowerCase();
  return SUBCATEGORIES[category]?.[sub] || CATEGORY_DEFAULTS[category] || CATEGORY_DEFAULTS.top;
}

export const attrs = (item) => attributes(item.category, item.subcategory);
export const isSporty = (item) => item.style === "sporty" || attrs(item).tags.includes("sporty");

// Python's round() on the values that get stored and fed to the models
export { pyRound, pySum };
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const has = (item, key, value) => (item[key] || []).includes(value);

export function seasonForTemperature(t) {
  if (t >= 24) return "summer";
  if (t >= 14) return "spring";
  if (t >= 6) return "autumn";
  return "winter";
}

// ---------------------------------------------------------------- occasion

export function itemOccasionFit(item, occasion) {
  const rule = OCCASION_RULES[occasion];
  const f = attrs(item).formality;
  const [lo, hi] = rule.formality;
  const gap = lo <= f && f <= hi ? 0 : Math.min(Math.abs(f - lo), Math.abs(f - hi));
  const formalityFit = Math.max(0, 1 - 0.35 * gap);
  const tagged = has(item, "occasions", occasion);
  let score = 0.55 * (tagged ? 1 : 0.4) + 0.45 * formalityFit;
  if (item.category !== "accessory") {
    if (rule.sporty === true && !isSporty(item)) {
      score *= ["top", "bottom", "footwear"].includes(item.category) ? 0.6 : 0.85;
    } else if (rule.sporty === false && isSporty(item)) {
      score *= 0.55;
    }
  }
  return clamp01(score);
}

export function scoreOccasion(items, ctx) {
  const occasion = ctx.occasion;
  let total = 0;
  let weight = 0;
  for (const it of items) {
    const w = ROLE_WEIGHT[it.category];
    total += w * itemOccasionFit(it, occasion);
    weight += w;
  }
  let score = weight ? total / weight : 0;
  const core = items.filter((it) => CORE_ROLES.includes(it.category)).map((it) => attrs(it).formality);
  const spread = core.length ? Math.max(...core) - Math.min(...core) : 0;
  const notes = [];
  if (spread >= 3) {
    score -= 0.12;
    notes.push("mixed_formality");
  }
  const wearable = items.filter((it) => it.category !== "accessory");
  const tagged = wearable.filter((it) => has(it, "occasions", occasion));
  if (tagged.length === wearable.length) notes.push("all_tagged");
  else if (!tagged.length) notes.push("none_tagged");
  return [clamp01(score), notes, { formality_spread: spread, tagged: tagged.length }];
}

// ---------------------------------------------------------------- weather

export function targetWarmth(t) {
  if (t >= 28) return 1;
  if (t >= 22) return 2;
  if (t >= 16) return 3;
  if (t >= 10) return 4;
  if (t >= 3) return 5;
  return 6;
}

const WARM_ACCESSORY_MAX_TEMP = 12;

export function outfitWarmth(items, temp) {
  let total = 0;
  for (const it of items) {
    if (it.category === "footwear") continue;
    const a = attrs(it);
    if (it.category === "accessory" && (a.warmth === 0 || temp >= WARM_ACCESSORY_MAX_TEMP)) continue;
    total += a.warmth;
  }
  return total;
}

function seasonOk(item, temp) {
  const seasons = item.seasons || [];
  const want = seasonForTemperature(temp);
  if (seasons.includes(want)) return true;
  return (want === "spring" || want === "autumn") && (seasons.includes("spring") || seasons.includes("autumn"));
}

export function itemWeatherFit(item, ctx) {
  const temp = ctx.temperature_c;
  const weather = ctx.weather;
  const a = attrs(item);
  const tags = a.tags;
  let score = seasonOk(item, temp) ? 0.65 : 0.35;
  if (item.category === "footwear") {
    if ((weather === "rainy" || weather === "snowy") && tags.includes("open")) score -= 0.3;
    if (weather === "snowy") score += tags.includes("snow") ? 0.25 : tags.includes("rain") ? 0.1 : -0.1;
    else if (weather === "rainy" && tags.includes("rain")) score += 0.2;
    if (temp >= 26 && a.warmth >= 2) score -= 0.25;
  } else if (item.category === "outerwear") {
    if (temp >= 24) score -= 0.3;
    if ((weather === "rainy" || weather === "snowy") && (tags.includes("rain") || tags.includes("snow"))) score += 0.25;
    if (temp < 5 && a.warmth >= 3) score += 0.2;
  } else {
    if (temp >= 26 && a.warmth >= 2) score -= 0.3;
    if (temp < 8 && a.warmth === 0 && item.category !== "accessory") score -= 0.2;
  }
  if (item.category === "accessory") {
    if (tags.includes("sun") && weather === "sunny") score += 0.25;
    if (tags.includes("rain") && weather === "rainy") score += 0.3;
    if (a.warmth >= 2) score += temp < 8 ? 0.2 : temp >= 16 ? -0.45 : 0;
  }
  return clamp01(score + 0.2);
}

export function scoreWeather(items, ctx) {
  const temp = ctx.temperature_c;
  const weather = ctx.weather;
  const warmth = outfitWarmth(items, temp);
  const target = targetWarmth(temp);
  const warmthFit = Math.max(0, 1 - 0.22 * Math.abs(warmth - target));
  const wearable = items.filter((it) => it.category !== "accessory");
  const seasonFit = wearable.filter((it) => seasonOk(it, temp)).length / Math.max(1, wearable.length);

  let score = 0.55 * warmthFit + 0.3 * seasonFit + 0.15;
  const notes = [];
  const shoes = items.find((it) => it.category === "footwear");
  const outer = items.find((it) => it.category === "outerwear");
  const shoeTags = shoes ? attrs(shoes).tags : [];
  const outerTags = outer ? attrs(outer).tags : [];

  if (weather === "rainy") {
    if (shoeTags.includes("open")) { score -= 0.3; notes.push("open_shoes_in_rain"); }
    if (outerTags.includes("rain") || shoeTags.includes("rain")) { score += 0.08; notes.push("rain_ready"); }
    if (!outer && temp < 20) score -= 0.08;
  }
  if (weather === "snowy") {
    if (!(shoeTags.includes("snow") || shoeTags.includes("rain"))) { score -= 0.25; notes.push("shoes_not_for_snow"); }
    if (!outer) { score -= 0.3; notes.push("no_coat_in_snow"); }
  }
  if (temp < 8 && !outer) { score -= 0.2; notes.push("cold_without_layer"); }
  if (temp >= 24 && outer && attrs(outer).warmth >= 2) { score -= 0.2; notes.push("too_warm_layer"); }
  if (weather === "windy" && outer) score += 0.04;
  const warmExtras = items.filter((it) => it.category === "accessory" && attrs(it).warmth >= 2);
  if (warmExtras.length && temp >= 16) { score -= 0.15; notes.push("warm_accessory_on_warm_day"); }

  if (warmth < target - 1) notes.push("too_cold");
  else if (warmth > target + 1) notes.push("too_warm");
  else notes.push("warmth_right");
  return [clamp01(score), notes, { warmth, target_warmth: target, season_fit: pyRound(seasonFit, 3) }];
}

// ---------------------------------------------------------------- style

export function itemStyleFit(item, ctx) {
  if (ctx.style) return styleAffinity(item.style, ctx.style);
  const preferred = ctx.preferred_styles || [];
  if (preferred.length) return Math.max(...preferred.map((s) => styleAffinity(item.style, s)));
  return 0.75;
}

export function scoreStyle(items, ctx) {
  const wearable = items.filter((it) => it.category !== "accessory");
  const styles = wearable.map((it) => it.style);
  const pairVals = [];
  for (let i = 0; i < styles.length; i++) {
    for (let j = i + 1; j < styles.length; j++) pairVals.push(styleAffinity(styles[i], styles[j]));
  }
  const coherence = pairVals.length ? pySum(pairVals) / pairVals.length : 1;
  const notes = [];
  const wanted = ctx.style;
  let match = null;
  let score;
  if (wanted || (ctx.preferred_styles || []).length) {
    match = pySum(wearable.map((it) => itemStyleFit(it, ctx))) / Math.max(1, styles.length);
    score = 0.6 * match + 0.4 * coherence;
    const exact = wanted ? styles.filter((s) => s === wanted).length : 0;
    if (wanted && exact === styles.length) notes.push("all_match_style");
    else if (wanted && exact === 0) notes.push("no_style_match");
  } else {
    score = coherence;
  }
  if (coherence >= 0.85) notes.push("coherent");
  else if (coherence < 0.5) notes.push("mixed_styles");
  return [clamp01(score), notes, { coherence: pyRound(coherence, 3), match: match === null ? null : pyRound(match, 3) }];
}

// ---------------------------------------------------------------- colour

const harmonyCache = new Map();

export function scoreColor(items, ctx) {
  const ordered = items.filter((it) => it.category !== "accessory");
  const accessories = items.filter((it) => it.category === "accessory").slice(0, 1);
  const hexes = [...ordered, ...accessories].map((it) => it.main_color_hex);
  const key = hexes.join(",");
  if (!harmonyCache.has(key)) {
    if (harmonyCache.size > 20000) harmonyCache.clear();
    harmonyCache.set(key, outfitHarmony(hexes));
  }
  const [harmony, d] = harmonyCache.get(key);
  const palette = ctx.palette || "any";
  const pal = paletteFit(hexes, palette);
  let score = palette === "any" ? harmony : 0.72 * harmony + 0.28 * pal;

  const names = items.map((it) => it.main_color_name);
  const fav = new Set(ctx.favorite_colors || []);
  const avoid = new Set(ctx.avoided_colors || []);
  const favHits = names.filter((n) => fav.has(n)).length;
  const avoidHits = names.filter((n) => avoid.has(n)).length;
  score += Math.min(0.1, 0.05 * favHits) - 0.15 * avoidHits;

  const notes = d.weakest ? [d.weakest.kind] : [];
  if (avoidHits) notes.push("has_avoided_colour");
  if (favHits) notes.push("has_favourite_colour");
  if (palette !== "any") notes.push(pal >= 0.7 ? "palette_match" : "palette_miss");
  return [clamp01(score), notes, {
    harmony: pyRound(harmony, 3),
    palette_fit: pyRound(pal, 3),
    weakest_pair: d.weakest,
    loud: d.loud,
    mean_pair: d.mean ?? null,
  }];
}

// ---------------------------------------------------------------- all four

export function scoreRules(items, ctx) {
  const out = {};
  for (const [name, fn] of [["occasion", scoreOccasion], ["weather", scoreWeather],
    ["style", scoreStyle], ["color", scoreColor]]) {
    const [score, notes, detail] = fn(items, ctx);
    out[name] = { score: pyRound(score, 4), notes, detail };
  }
  return out;
}

export function itemPrefit(item, ctx) {
  return 0.45 * itemOccasionFit(item, ctx.occasion) + 0.35 * itemWeatherFit(item, ctx) + 0.2 * itemStyleFit(item, ctx);
}
