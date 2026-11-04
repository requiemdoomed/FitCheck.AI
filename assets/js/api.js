// FitCheck.AI — API client
// Swayam Shakya
//
// Pages talk to the server through this one object. The session lives in an
// HttpOnly cookie the page can't read; every request that changes something
// also sends the CSRF token from the readable fc_csrf cookie. Photo
// processing that needs a canvas (resizing, cutting the garment out, reading
// its colour and pattern) happens here, before upload; the server checks and
// re-encodes everything it receives.

import { NAMED_COLORS } from "./engine/data.js";
import { nearestName } from "./engine/color.js";
import { suggestBuys, BASICS } from "./engine/shop.js";
import { canvasToBlob, cutOut, dyedStock, garmentColour, ImageProblem, patternOf, processUpload } from "./local/images.js";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "unknown", details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function cookie(name) {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : "";
}

// The session cookie is HttpOnly; fc_csrf is set alongside it, so its presence
// means "probably signed in" (the server always has the final word).
export const session = {
  get isSignedIn() { return Boolean(cookie("fc_csrf")); },
  save() { /* the server sets the cookies */ },
  clear() { document.cookie = "fc_csrf=; Max-Age=0; Path=/; SameSite=Strict"; },
};

export const apiEvents = new EventTarget();

async function request(method, path, { json, form, query } = {}) {
  const url = new URL(path, document.baseURI);
  if (query) for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = cookie("fc_csrf");
  let body;
  if (json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  if (form) body = form;
  let res;
  try {
    res = await fetch(url, { method, headers, body, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError("Can't reach FitCheck.AI. Check your connection and try again.", { code: "offline" });
  }
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const e = data?.error || {};
    if (res.status === 401) {
      session.clear();
      apiEvents.dispatchEvent(new CustomEvent("unauthorized"));
    }
    throw new ApiError(e.message || `Request failed (${res.status}).`, { status: res.status, code: e.code || "http_error", details: e.details || null });
  }
  return data;
}

const get = (p, query) => request("GET", p, { query });
const post = (p, json) => request("POST", p, { json: json ?? {} });
const put = (p, json) => request("PUT", p, { json: json ?? {} });
const del = (p, json) => request("DELETE", p, json === undefined ? {} : { json });

// Images come from the app's own server (or blob:/data: made in this tab).
export function imageSrc(url) {
  if (!url) return "";
  if (/^(blob:|data:image\/)/i.test(url)) return url;
  if (/^(api\/images\/[0-9a-f]{32}|assets\/)/.test(url)) return url;
  return "";
}

// ---- pictures, prepared in the browser before upload

function imageProblem(err) {
  if (err instanceof ImageProblem) {
    return new ApiError(err.message, { status: err.code === "file_too_large" ? 413 : 400, code: err.code || "invalid_image", details: { image: err.message } });
  }
  return err;
}

/**
 * FormData (or a plain object) from the add/edit form -> multipart for the
 * server, with the processed photo, its cut-out and its pattern; or, with no
 * photo, a real garment photo dyed to the chosen colour.
 */
async function itemForm(input, { creating }) {
  const out = new FormData();
  let file = null;
  const entries = input instanceof FormData ? [...input.entries()] : Object.entries(input || {}).flatMap(([k, v]) => (Array.isArray(v) ? v.map((x) => [k, x]) : [[k, v]]));
  for (const [k, v] of entries) {
    if (k === "image") { if (v instanceof Blob && v.size) file = v; continue; }
    if (v !== undefined && v !== null) out.append(k, v);
  }
  const look = Object.fromEntries(entries.filter(([k]) => ["category", "subcategory", "main_color"].includes(k)));
  const removing = ["1", "true", "yes"].includes(String(look.remove_image || out.get("remove_image") || "").toLowerCase());
  if (file) {
    let processed;
    try { processed = await processUpload(file); } catch (err) { throw imageProblem(err); }
    out.append("image", processed.blob, "photo");
    out.append("image_source", "upload");
    let cut = await cutOut(processed.canvas).catch(() => null);
    if (!cut && look.category) cut = await dyedStock(look.category, look.subcategory, look.main_color).catch(() => null);
    if (cut) out.append("cutout", await canvasToBlob(cut, true), "cutout");
    const role = look.category;
    if (["top", "bottom", "outerwear", "dress"].includes(role)) {
      out.set("pattern", await patternOf(processed.blob, role));
    }
  } else if ((creating || removing) && look.category) {
    const c = await dyedStock(look.category, look.subcategory, look.main_color).catch(() => null);
    if (c) {
      out.append("image", await canvasToBlob(c, true), "stock");
      out.append("image_source", "stock");
    }
    if (removing) out.delete("remove_image");
  }
  return out;
}

// ---- Smart buys: worked out here from the wardrobe, with the same rules

let lastSuggestions = new Map();
const basicPics = new Map();
async function basicPicture(b) {
  if (!basicPics.has(b.key)) {
    basicPics.set(b.key, dyedStock(b.category, b.subcategory, b.hex)
      .then((c) => (c ? canvasToBlob(c, true).then((bl) => URL.createObjectURL(bl)) : null)).catch(() => null));
  }
  return basicPics.get(b.key);
}

function engineRow(it) {
  return {
    id: it.id, name: it.name, category: it.category, subcategory: it.subcategory, main_color_hex: it.main_color.hex,
    main_color_name: it.main_color.name, style: it.style, seasons: it.seasons, occasions: it.occasions,
  };
}

async function suggest() {
  const [{ items }, me] = await Promise.all([get("api/wardrobe"), get("api/auth/me")]);
  const p = me.preferences;
  const byId = new Map(items.map((it) => [it.id, it]));
  const list = suggestBuys(items.map(engineRow), p, { limit: 8 });
  lastSuggestions = new Map();
  const out = [];
  for (const s of list) {
    const outfit = s.best.items.map((it) => (byId.has(it.id) ? byId.get(it.id)
      : { id: it.id, name: it.name, category: it.category, subcategory: it.subcategory,
          main_color: { hex: it.main_color_hex, name: nearestName(it.main_color_hex) }, image_source: "stock", shop: true }));
    lastSuggestions.set(s.basic.key, { basic: { name: s.basic.name, category: s.basic.category, subcategory: s.basic.subcategory, hex: s.basic.hex },
      item_ids: s.best.items.filter((it) => byId.has(it.id)).map((it) => it.id), occasion: s.best.occasion });
    out.push({
      image_url: await basicPicture(s.basic),
      key: s.basic.key, name: s.basic.name, category: s.basic.category, subcategory: s.basic.subcategory,
      color: { hex: s.basic.hex, name: nearestName(s.basic.hex) }, style: s.basic.style,
      price: s.price, why: s.basic.why, reasons: s.reasons, unlocks: s.unlocks,
      outfit: { items: outfit, score: Math.round(s.best.score * 100), occasion: s.best.occasion, with_basics: Boolean(s.best.filler) },
    });
  }
  return { budget: p.budget || "budget", suggestions: out, wardrobe_size: items.length };
}

// ---- the API, same shape as before

export const api = {
  health: async () => {
    const h = await get("api/health");
    return h;
  },
  auth: {
    register: (data) => post("api/auth/register", data),
    login: (data) => post("api/auth/login", data),
    logout: () => post("api/auth/logout"),
    logoutEverywhere: () => post("api/auth/logout-all"),
    me: () => get("api/auth/me"),
    forgot: (email) => post("api/auth/forgot", { email }),
    reset: (token, password) => post("api/auth/reset", { token, password }),
    sessions: () => get("api/auth/sessions"),
    endSession: (id) => del(`api/auth/sessions/${Number(id)}`),
  },
  wardrobe: {
    list: (filters) => get("api/wardrobe", filters || {}),
    get: (id) => get(`api/wardrobe/${Number(id)}`),
    create: async (data) => request("POST", "api/wardrobe", { form: await itemForm(data, { creating: true }) }),
    update: async (id, data) => request("PUT", `api/wardrobe/${Number(id)}`, { form: await itemForm(data, { creating: false }) }),
    remove: (id) => del(`api/wardrobe/${Number(id)}`),
    // colour of a photo, read in the browser (nothing is uploaded until the piece is saved)
    analyze: async (fd) => {
      const file = fd instanceof FormData ? fd.get("image") : null;
      let processed;
      try { processed = await processUpload(file); } catch (err) { throw imageProblem(err); }
      const measured = await garmentColour(processed.canvas);
      if (!measured) return { color: null };
      const name = nearestName(measured);
      return { color: { hex: NAMED_COLORS[name], name, measured } };
    },
  },
  recommendations: {
    generate: (criteria) => post("api/recommendations/generate", criteria),
    history: (page = 1, verdict = "", perPage = 12) => get("api/recommendations/history", { page, verdict, per_page: perPage }),
    get: (id) => get(`api/recommendations/${Number(id)}`),
    feedback: (id, verdict) => post(`api/recommendations/${Number(id)}/feedback`, { verdict }),
    save: (id, name) => post(`api/recommendations/${Number(id)}/save`, { name }),
    wear: (id, worn) => post(`api/recommendations/${Number(id)}/wear`, { worn }),
  },
  outfits: {
    saved: () => get("api/outfits/saved"),
    unsave: (id) => del(`api/outfits/saved/${Number(id)}`),
  },
  dashboard: {
    summary: () => get("api/dashboard/summary"),
    statistics: () => get("api/dashboard/statistics"),
  },
  profile: {
    get: () => get("api/profile"),
    update: (data) => put("api/profile", data),
    remove: (password) => del("api/profile", { password }),
    exportData: (password) => post("api/profile/export", { password }),
    importData: (backup) => post("api/profile/import", backup),
  },
  photos: {
    status: () => get("api/photos/status"),
    useFree: (opts) => put("api/photos/free", opts || {}),
    useGemini: () => post("api/photos/gemini/use"),
    connect: (key) => post("api/photos/gemini", { key }),
    disconnect: () => del("api/photos/gemini"),
    forOutfit: (id, opts = {}) => post(`api/photos/outfit/${Number(id)}`, { force: Boolean(opts.force) }),
    choose: (id, index) => post(`api/photos/outfit/${Number(id)}/choose`, { index }),
    forSuggestion: async (key) => {
      const s = lastSuggestions.get(key);
      if (!s) throw new ApiError("That suggestion has changed. Reload the page.", { code: "not_found", status: 404 });
      return post("api/photos/suggestion", s);
    },
    sample: (body) => post("api/public/photo", body),
  },
  shop: {
    suggest,
    add: async (key) => {
      const b = BASICS.find((x) => x.key === key);
      if (!b) throw new ApiError("That suggestion couldn't be found.", { status: 404, code: "not_found" });
      return api.wardrobe.create({ name: b.name, category: b.category, subcategory: b.subcategory, main_color: b.hex,
        style: b.style, seasons: b.seasons, occasions: b.occasions, description: "Added from Smart buys." });
    },
  },
  demo: {
    load: () => post("api/demo/load"),
  },
  meta: {
    options: () => get("api/meta/options"),
  },
};
