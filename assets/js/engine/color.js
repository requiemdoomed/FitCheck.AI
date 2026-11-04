// Colour behaviour for the recommendation engine.
// Mirrors ml/fitcheck_ml/color.py; the low-level CIELAB maths lives in
// ../lib/color.js and is shared with the landing-page demo.

import { chroma, deltaE2000, hexToLab, hueAngle, isNeutral as isNeutralLab, pairHarmony } from "../lib/color.js";
import { NAMED_COLORS } from "./data.js";
import { pySum } from "./num.js";

export { chroma, hexToLab, pairHarmony };

const HEX_RE = /^#[0-9a-f]{6}$/;

export function normalizeHex(value) {
  if (typeof value !== "string") return null;
  let v = value.trim().toLowerCase();
  if (!v.startsWith("#")) v = "#" + v;
  if (/^#[0-9a-f]{3}$/.test(v)) v = "#" + [...v.slice(1)].map((c) => c + c).join("");
  return HEX_RE.test(v) ? v : null;
}

export const isNeutral = (hex) => isNeutralLab(hexToLab(hex));
export const isBold = (hex) => chroma(hexToLab(hex)) > 45;

export function isPastel(hex) {
  const lab = hexToLab(hex);
  const c = chroma(lab);
  return lab[0] > 70 && c > 12 && c < 45;
}

export function isEarthy(hex) {
  const lab = hexToLab(hex);
  const c = chroma(lab);
  const h = hueAngle(lab);
  return c > 8 && c < 50 && h >= 25 && h <= 115 && lab[0] < 80;
}

export const deltaE = (a, b) => deltaE2000(hexToLab(a), hexToLab(b));

const nameCache = new Map();
export function nearestName(hex) {
  if (nameCache.has(hex)) return nameCache.get(hex);
  const lab = hexToLab(hex);
  let best = null;
  let bestD = Infinity;
  for (const [name, value] of Object.entries(NAMED_COLORS)) {
    const d = deltaE2000(lab, hexToLab(value));
    if (d < bestD) { bestD = d; best = name; }
  }
  nameCache.set(hex, best);
  return best;
}

function pairs(list) {
  const out = [];
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) out.push([i, j]);
  return out;
}

/** Harmony for a whole outfit: [score 0..1, detail]. The weakest pair matters most. */
export function outfitHarmony(hexes) {
  hexes = hexes.filter(Boolean);
  if (hexes.length < 2) return [0.75, { pairs: [], weakest: null, loud: 0 }];
  const ps = pairs(hexes).map(([i, j]) => {
    const r = pairHarmony(hexes[i], hexes[j]);
    return { a: i, b: j, score: r.score, kind: r.kind, delta_e: Math.round(r.dE * 10) / 10 };
  });
  const mean = pySum(ps.map((p) => p.score)) / ps.length;
  let weakest = ps[0];
  for (const p of ps) if (p.score < weakest.score) weakest = p;
  const loud = hexes.filter((h) => !isNeutral(h)).length;
  let score = 0.6 * mean + 0.4 * weakest.score;
  if (loud >= 3) score -= 0.06 * (loud - 2);
  score = Math.max(0, Math.min(1, score));
  return [score, { pairs: ps, weakest, loud, mean: Math.round(mean * 1000) / 1000 }];
}

/** How well colours match a requested palette, 0..1. */
export function paletteFit(hexes, palette) {
  hexes = hexes.filter(Boolean);
  if (!hexes.length || !palette || palette === "any") return 1;
  const n = hexes.length;
  const count = (f) => hexes.filter(f).length;
  if (palette === "neutral") return count(isNeutral) / n;
  if (palette === "earthy") {
    return (count((h) => isEarthy(h) || isNeutral(h)) / n) * 0.8 + (hexes.some(isEarthy) ? 0.2 : 0);
  }
  if (palette === "pastel") {
    const hits = count(isPastel);
    const soft = count((h) => isNeutral(h) && hexToLab(h)[0] > 60);
    return Math.min(1, (hits + 0.5 * soft) / n + (hits ? 0.2 : 0));
  }
  if (palette === "bold") {
    const bold = count(isBold);
    if (bold === 0) return 0.2;
    return bold <= 2 ? 1 : 0.75;
  }
  if (palette === "monochrome") {
    if (n === 1) return 1;
    const coloured = hexes.filter((h) => !isNeutral(h));
    if (coloured.length <= 1) return 0.85;
    const ds = pairs(coloured).map(([i, j]) => deltaE(coloured[i], coloured[j]));
    return Math.max(0, 1 - pySum(ds) / ds.length / 40);
  }
  return 1;
}
