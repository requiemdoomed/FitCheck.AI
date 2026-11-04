// Smart buys: which cheap basic would do the most for this wardrobe?
// Swayam Shakya
//
// The list below is deliberately boring: plain, well-cut basics in quiet
// colours that every high-street and supermarket clothing range sells, with
// typical price ranges and no brands. For each one we ask the same rules
// engine that builds outfits: if you owned this, how many good outfits could
// you make with what's already on your rail? Pieces that open up the most
// outfits, suit your styles and colours, and fill a gap rank first. Anything
// you already own (same kind, near-identical colour) is skipped.

import { NAMED_COLORS } from "./data.js";
import { deltaE } from "./color.js";
import { scoreRules, itemPrefit } from "./rules.js";

const C = NAMED_COLORS;

// price: [budget range, mid range] in US dollars
export const BASICS = [
  { key: "white-tee", name: "White crew-neck tee", category: "top", subcategory: "t-shirt", hex: C.white, style: "minimalist", occasions: ["casual", "college", "travel", "date"], seasons: ["spring", "summer", "autumn"], price: ["$8–15", "$20–30"], why: "The most useful top there is: it goes under jackets, with every colour of trouser, all year." },
  { key: "black-tee", name: "Black crew-neck tee", category: "top", subcategory: "t-shirt", hex: C.black, style: "minimalist", occasions: ["casual", "college", "travel", "party", "date"], seasons: ["spring", "summer", "autumn"], price: ["$8–15", "$20–30"], why: "Slimming, hides wear, and makes light trousers look sharper." },
  { key: "grey-tee", name: "Grey marl tee", category: "top", subcategory: "t-shirt", hex: C["light grey"], style: "minimalist", occasions: ["casual", "college", "travel", "sports"], seasons: ["spring", "summer", "autumn"], price: ["$8–14", "$18–28"], why: "Softer than white, easier than black; it never clashes." },
  { key: "navy-tee", name: "Navy tee", category: "top", subcategory: "t-shirt", hex: C.navy, style: "classic", occasions: ["casual", "college", "travel", "date"], seasons: ["spring", "summer", "autumn"], price: ["$8–15", "$20–30"], why: "Navy reads smarter than black and flatters almost every skin tone." },
  { key: "oxford-blue", name: "Light blue oxford shirt", category: "top", subcategory: "shirt", hex: C["light blue"], style: "classic", occasions: ["work", "college", "date", "casual"], seasons: ["spring", "summer", "autumn", "winter"], price: ["$20–30", "$35–60"], why: "Dresses up jeans, dresses down chinos; the one shirt that does work and weekends." },
  { key: "white-shirt", name: "Plain white shirt", category: "top", subcategory: "shirt", hex: C.white, style: "classic", occasions: ["work", "formal", "date", "party"], seasons: ["spring", "summer", "autumn", "winter"], price: ["$18–30", "$35–60"], why: "For interviews, dinners and anything formal, at a basic price." },
  { key: "navy-polo", name: "Navy polo", category: "top", subcategory: "polo", hex: C.navy, style: "smart_casual", occasions: ["casual", "work", "date", "travel"], seasons: ["spring", "summer"], price: ["$15–22", "$28–45"], why: "A collar without the effort: smart enough for casual Fridays." },
  { key: "cream-knit", name: "Cream crew-neck jumper", category: "top", subcategory: "sweater", hex: C.cream, style: "classic", occasions: ["casual", "work", "date", "college"], seasons: ["autumn", "winter"], price: ["$20–35", "$40–70"], why: "Warm, soft-looking and lifts dark trousers in winter." },
  { key: "navy-knit", name: "Navy crew-neck jumper", category: "top", subcategory: "sweater", hex: C.navy, style: "classic", occasions: ["casual", "work", "date", "college"], seasons: ["autumn", "winter"], price: ["$20–35", "$40–70"], why: "Goes over a shirt for work or a tee at the weekend." },
  { key: "grey-hoodie", name: "Grey zip-free hoodie", category: "top", subcategory: "hoodie", hex: C.grey, style: "streetwear", occasions: ["casual", "college", "travel", "sports"], seasons: ["spring", "autumn", "winter"], price: ["$18–28", "$35–55"], why: "The comfortable layer for travel days and lectures." },
  { key: "black-turtleneck", name: "Black fine-knit turtleneck", category: "top", subcategory: "turtleneck", hex: C.black, style: "elegant", occasions: ["work", "date", "party", "formal"], seasons: ["autumn", "winter"], price: ["$15–25", "$35–60"], why: "Instantly polished under a coat or blazer, without a tie." },
  { key: "white-blouse", name: "Simple white blouse", category: "top", subcategory: "blouse", hex: C.white, style: "elegant", occasions: ["work", "date", "formal", "party"], seasons: ["spring", "summer", "autumn"], price: ["$18–28", "$35–55"], why: "Clean and light: tucks into skirts or trousers for work and dinners." },

  { key: "dark-jeans", name: "Dark straight-leg jeans", category: "bottom", subcategory: "jeans", hex: C.denim, style: "classic", occasions: ["casual", "college", "date", "travel", "party"], seasons: ["spring", "autumn", "winter"], price: ["$20–35", "$45–70"], why: "Dark denim counts as a neutral and looks smarter than light washes." },
  { key: "black-jeans", name: "Black slim jeans", category: "bottom", subcategory: "jeans", hex: C.black, style: "streetwear", occasions: ["casual", "college", "party", "date"], seasons: ["spring", "autumn", "winter"], price: ["$20–35", "$45–70"], why: "Works with every colour of top and with boots or trainers." },
  { key: "beige-chinos", name: "Beige chinos", category: "bottom", subcategory: "chinos", hex: C.beige, style: "smart_casual", occasions: ["work", "casual", "date", "travel"], seasons: ["spring", "summer", "autumn"], price: ["$20–30", "$40–60"], why: "Halfway between jeans and suit trousers: right for most offices." },
  { key: "navy-chinos", name: "Navy chinos", category: "bottom", subcategory: "chinos", hex: C.navy, style: "smart_casual", occasions: ["work", "casual", "date", "college"], seasons: ["spring", "autumn", "winter"], price: ["$20–30", "$40–60"], why: "Pairs with white, grey, light blue and every earthy colour." },
  { key: "grey-trousers", name: "Charcoal tailored trousers", category: "bottom", subcategory: "trousers", hex: C.charcoal, style: "classic", occasions: ["work", "formal", "date", "party"], seasons: ["autumn", "winter", "spring"], price: ["$22–35", "$45–75"], why: "Formal enough for interviews and weddings with a plain shirt." },
  { key: "black-trousers", name: "Black wide-leg trousers", category: "bottom", subcategory: "trousers", hex: C.black, style: "elegant", occasions: ["work", "formal", "party", "date"], seasons: ["spring", "autumn", "winter"], price: ["$22–35", "$45–75"], why: "Easy elegance: a tee and these already looks put together." },
  { key: "grey-joggers", name: "Grey tapered joggers", category: "bottom", subcategory: "joggers", hex: C.grey, style: "sporty", occasions: ["sports", "casual", "travel"], seasons: ["spring", "autumn", "winter"], price: ["$15–25", "$30–50"], why: "For the gym and long journeys; tapered so they still look tidy." },
  { key: "black-skirt", name: "Black midi skirt", category: "bottom", subcategory: "skirt", hex: C.black, style: "elegant", occasions: ["work", "date", "party", "formal"], seasons: ["spring", "summer", "autumn"], price: ["$18–28", "$35–55"], why: "Goes with every top you own and every shoe from trainers to heels." },
  { key: "stone-shorts", name: "Stone chino shorts", category: "bottom", subcategory: "shorts", hex: C.khaki, style: "smart_casual", occasions: ["casual", "travel", "date"], seasons: ["summer"], price: ["$15–22", "$30–45"], why: "Neater than denim shorts for warm days out." },

  { key: "black-dress", name: "Simple black dress", category: "dress", subcategory: "casual dress", hex: C.black, style: "elegant", occasions: ["date", "party", "work", "formal"], seasons: ["spring", "summer", "autumn"], price: ["$22–35", "$45–80"], why: "One piece, ready for almost anything with a change of shoes." },

  { key: "white-sneakers", name: "Plain white trainers", category: "footwear", subcategory: "sneakers", hex: C.white, style: "minimalist", occasions: ["casual", "college", "travel", "date"], seasons: ["spring", "summer", "autumn"], price: ["$25–40", "$50–80"], why: "Go with jeans, chinos, shorts and even a casual dress." },
  { key: "black-sneakers", name: "Black canvas trainers", category: "footwear", subcategory: "sneakers", hex: C.black, style: "streetwear", occasions: ["casual", "college", "travel", "party"], seasons: ["spring", "autumn", "winter"], price: ["$20–35", "$45–70"], why: "Hide dirt and rain better than white." },
  { key: "brown-boots", name: "Brown suede-look ankle boots", category: "footwear", subcategory: "ankle boots", hex: C.brown, style: "classic", occasions: ["casual", "work", "date", "college"], seasons: ["autumn", "winter", "spring"], price: ["$30–45", "$55–90"], why: "Smart-casual footwear that copes with rain." },
  { key: "black-loafers", name: "Black loafers", category: "footwear", subcategory: "loafers", hex: C.black, style: "classic", occasions: ["work", "date", "formal", "party"], seasons: ["spring", "summer", "autumn"], price: ["$28–40", "$50–85"], why: "Slip-on smart shoes that make chinos look like work trousers." },
  { key: "black-flats", name: "Black ballet flats", category: "footwear", subcategory: "flats", hex: C.black, style: "elegant", occasions: ["work", "date", "party", "casual"], seasons: ["spring", "summer", "autumn"], price: ["$18–30", "$40–65"], why: "Comfortable all day and smart enough for the office." },
  { key: "running-shoes", name: "Grey running shoes", category: "footwear", subcategory: "running shoes", hex: C["light grey"], style: "sporty", occasions: ["sports", "casual", "travel"], seasons: ["spring", "summer", "autumn", "winter"], price: ["$30–45", "$55–90"], why: "Proper trainers for the gym, which also suit travel days." },

  { key: "denim-jacket", name: "Mid-blue denim jacket", category: "outerwear", subcategory: "denim jacket", hex: C.denim, style: "streetwear", occasions: ["casual", "college", "travel", "date"], seasons: ["spring", "autumn"], price: ["$25–40", "$50–80"], why: "The spring and autumn layer that goes over everything except more denim." },
  { key: "navy-blazer", name: "Unstructured navy blazer", category: "outerwear", subcategory: "blazer", hex: C.navy, style: "smart_casual", occasions: ["work", "date", "formal", "party"], seasons: ["spring", "autumn", "winter"], price: ["$35–50", "$60–100"], why: "Turns a tee and jeans into a work outfit." },
  { key: "camel-coat", name: "Camel overcoat", category: "outerwear", subcategory: "wool coat", hex: C.camel, style: "classic", occasions: ["work", "date", "formal", "casual"], seasons: ["winter", "autumn"], price: ["$45–60", "$70–120"], why: "Warm, smart and lifts dark winter outfits." },
  { key: "black-puffer", name: "Black padded jacket", category: "outerwear", subcategory: "puffer jacket", hex: C.black, style: "streetwear", occasions: ["casual", "college", "travel"], seasons: ["winter"], price: ["$35–50", "$60–100"], why: "Real warmth for cold days at a low price." },
  { key: "khaki-trench", name: "Stone trench coat", category: "outerwear", subcategory: "trench coat", hex: C.beige, style: "classic", occasions: ["work", "casual", "date", "travel"], seasons: ["spring", "autumn"], price: ["$40–55", "$65–110"], why: "Rain-ready and smart over a shirt or a jumper." },
  { key: "grey-cardigan", name: "Grey cardigan", category: "outerwear", subcategory: "cardigan", hex: C.grey, style: "minimalist", occasions: ["work", "college", "casual", "date"], seasons: ["spring", "autumn", "winter"], price: ["$20–30", "$35–60"], why: "A light layer for offices and cool evenings." },
];

const W = { occasion: 0.22 / 0.78, weather: 0.22 / 0.78, color: 0.2 / 0.78, style: 0.14 / 0.78 };
const GOOD = 0.74;

/** The outfit-building roles a piece pairs with. */
function partnersNeeded(category) {
  switch (category) {
    case "top": return [["bottom"], ["footwear"]];
    case "bottom": return [["top"], ["footwear"]];
    case "dress": return [["footwear"]];
    case "footwear": return [["top", "dress"], ["bottom"]];
    case "outerwear": return [["top", "dress"], ["bottom"], ["footwear"]];
    default: return [];
  }
}

function contextsFor(prefs) {
  const base = { palette: prefs.preferred_palette || "any", favorite_colors: prefs.favorite_colors || [], avoided_colors: prefs.avoided_colors || [], preferred_styles: prefs.preferred_styles || [], style: null };
  const occs = [prefs.default_occasion || "casual", "work", "date"].filter((o, i, a) => a.indexOf(o) === i);
  // a mild day and a cold day, so coats and knits get a fair chance
  return occs.flatMap((o) => [
    { ...base, occasion: o, weather: "cloudy", temperature_c: 17 },
    { ...base, occasion: o, weather: "windy", temperature_c: 6 },
  ]);
}

function total(rules) {
  return Object.entries(W).reduce((s, [k, w]) => s + rules[k].score * w, 0);
}

const PLURAL = { top: "tops", bottom: "trousers or skirts", dress: "dresses", footwear: "shoes", outerwear: "jackets or coats" };

/** When the wardrobe can't complete an outfit yet, show the piece with other basics. */
function withBasics(piece, groups, ctx) {
  let outfit = [piece];
  for (const cats of groups) {
    let pick = null;
    for (const b of BASICS) {
      if (!cats.includes(b.category) || b.category === "dress") continue;
      const trial = [...outfit, asItem(b)];
      const t = total(scoreRules(trial, ctx));
      if (!pick || t > pick.t) pick = { t, item: asItem(b) };
    }
    if (pick) outfit = [...outfit, pick.item];
  }
  return { items: outfit, score: total(scoreRules(outfit, ctx)), occasion: ctx.occasion };
}

const alreadyOwned = (b, items) => items.some((it) => it.category === b.category
  && it.subcategory === b.subcategory && deltaE(it.main_color_hex, b.hex) < 12);

function asItem(b) {
  return {
    id: `shop:${b.key}`, name: b.name, category: b.category, subcategory: b.subcategory,
    main_color_hex: b.hex, style: b.style, occasions: b.occasions, seasons: b.seasons,
  };
}

function prefScore(b, prefs) {
  let s = 0.5;
  if ((prefs.preferred_styles || []).includes(b.style)) s += 0.3;
  const fav = (prefs.favorite_colors || []).map((n) => C[n]).filter(Boolean);
  if (fav.some((h) => deltaE(h, b.hex) < 15)) s += 0.2;
  return Math.min(1, s);
}

/**
 * items: the person's active wardrobe rows (engine shape)
 * prefs: their preferences
 * Returns up to `limit` suggestions, best first:
 *   { basic, price, unlocks, best: { items, score }, score, reasons[] }
 */
export function suggestBuys(items, prefs = {}, { limit = 8 } = {}) {
  const tier = prefs.budget === "mid" ? 1 : 0;
  const ctxs = contextsFor(prefs);
  const avoided = (prefs.avoided_colors || []).map((n) => C[n]).filter(Boolean);
  const have = (cat) => items.filter((it) => it.category === cat);
  const out = [];

  for (const b of BASICS) {
    if (alreadyOwned(b, items)) continue;
    if (avoided.some((h) => deltaE(h, b.hex) < 12)) continue;
    const piece = asItem(b);
    const groups = partnersNeeded(b.category);
    const seen = new Set();
    let best = null;
    let good = 0;

    for (const ctx of ctxs) {
      // the few best-fitting partners of each kind, so this stays quick on big wardrobes
      const pools = groups.map((cats) => cats.flatMap(have)
        .map((it) => [itemPrefit(it, ctx), it]).sort((x, y) => y[0] - x[0]).slice(0, 6).map(([, it]) => it));
      if (pools.some((p) => !p.length)) continue;
      const combos = pools.reduce((acc, pool) => acc.flatMap((c) => pool.map((it) => [...c, it])), [[]]);
      for (const combo of combos) {
        // a dress replaces both top and bottom
        if (combo.some((x) => x.category === "dress") && combo.some((x) => x.category === "bottom")) continue;
        const outfit = [piece, ...combo];
        const t = total(scoreRules(outfit, ctx));
        const sig = combo.map((x) => x.id).sort().join(",");
        if (t >= GOOD && !seen.has(sig)) { seen.add(sig); good++; }
        if (!best || t > best.score) best = { items: outfit, score: t, occasion: ctx.occasion };
      }
    }

    const gap = groups.length && have(b.category).length === 0 ? 1 : have(b.category).length < 2 ? 0.5 : 0;
    const unlockPart = Math.min(good / 10, 1);
    const score = 0.5 * unlockPart + 0.2 * prefScore(b, prefs) + 0.15 * gap + 0.15 * (best ? best.score : 0);
    const reasons = [];
    if (good) reasons.push(`Makes ${good} good outfit${good === 1 ? "" : "s"} with clothes you already have.`);
    if (gap === 1) reasons.push(`You don't have any ${PLURAL[b.category]} yet.`);
    if ((prefs.preferred_styles || []).includes(b.style)) reasons.push("Matches a style you said you like.");
    if (!best) best = { ...withBasics(piece, groups, ctxs[0]), filler: true };
    out.push({ basic: b, price: b.price[tier], unlocks: good, best, score, reasons });
  }

  out.sort((a, b) => b.score - a.score || a.basic.key.localeCompare(b.basic.key));
  // don't fill the list with five t-shirts: at most two of each category
  const picked = [];
  const perCat = {};
  for (const s of out) {
    if ((perCat[s.basic.category] || 0) >= 2) continue;
    perCat[s.basic.category] = (perCat[s.basic.category] || 0) + 1;
    picked.push(s);
    if (picked.length >= limit) break;
  }
  return picked;
}
