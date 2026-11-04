// Photos, in the browser.
// Swayam Shakya
//
//  processUpload  validate a file by actually decoding it, fix orientation,
//                 shrink to 900px and re-encode (which drops EXIF/GPS)
//  cutOut         lift the garment off its background with U²-Net-p
//                 (assets/models/u2netp.onnx) run by onnxruntime-web
//  dyedStock      a real photographed garment of the right type, dyed to
//                 the chosen colour in CIELAB (for pieces without a photo)
//  garmentColour  the garment's main colour, ignoring the background
//
// Ports of the old server's storage.py, cutout.py and stock.py.

import { hexToLab } from "../lib/color.js";

export const MAX_SIDE = 900;
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const ALLOWED = ["image/jpeg", "image/png", "image/webp"];

export class ImageProblem extends Error {
  constructor(message, code = "invalid_image") {
    super(message);
    this.code = code;
  }
}

function canvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

function toBlob(c, type, quality) {
  return new Promise((resolve) => c.toBlob(resolve, type, quality));
}

// WebP keeps transparency and is small; Safari can't encode it, so fall back.
async function encode(c, transparent) {
  const webp = await toBlob(c, "image/webp", 0.86);
  if (webp && webp.type === "image/webp") return webp;
  return transparent ? toBlob(c, "image/png") : toBlob(c, "image/jpeg", 0.88);
}

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = "async";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new ImageProblem("That image couldn't be loaded."));
    img.src = src;
  });
}

/** Validate and clean an uploaded file. Returns { blob, canvas, width, height }. */
export async function processUpload(file) {
  if (!file || !file.size) throw new ImageProblem("Choose an image file.");
  if (file.size > MAX_UPLOAD_BYTES) throw new ImageProblem("Images must be 15 MB or smaller.", "file_too_large");
  if (file.type && !ALLOWED.includes(file.type)) throw new ImageProblem("Use a JPG, PNG or WebP image.");
  // never trust the name or the type: the bytes have to decode as an image
  const head = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const isJpeg = head[0] === 0xff && head[1] === 0xd8;
  const isPng = head[0] === 0x89 && head[1] === 0x50 && head[2] === 0x4e && head[3] === 0x47;
  const isWebp = head[8] === 0x57 && head[9] === 0x45 && head[10] === 0x42 && head[11] === 0x50;
  if (!isJpeg && !isPng && !isWebp) throw new ImageProblem("That file isn't a JPG, PNG or WebP image.");
  let bmp;
  try {
    bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ImageProblem("That file isn't a readable image.");
  }
  if (Math.min(bmp.width, bmp.height) < 32) {
    bmp.close?.();
    throw new ImageProblem("Images must be at least 32px on each side.");
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
  const c = canvas(Math.round(bmp.width * scale), Math.round(bmp.height * scale));
  const g = c.getContext("2d");
  g.imageSmoothingQuality = "high";
  g.drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  const blob = await encode(c, false);
  return { blob, canvas: c, width: c.width, height: c.height };
}

// ---------------------------------------------------------------- cut-outs

const SIZE = 320;
const MEAN = [0.485, 0.456, 0.406];
const STD = [0.229, 0.224, 0.225];
let sessionPromise = null;

export function cutoutModel() {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const ort = await import("../../vendor/ort/ort.wasm.min.mjs");
      ort.env.wasm.numThreads = 1;              // one thread: pages aren't cross-origin isolated
      ort.env.wasm.wasmPaths = new URL("../../vendor/ort/", import.meta.url).href;
      const session = await ort.InferenceSession.create(new URL("../../models/u2netp.onnx", import.meta.url).href,
        { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
      return { ort, session };
    })();
    sessionPromise.catch(() => { sessionPromise = null; });
  }
  return sessionPromise;
}

/** Soft mask (Float32Array SIZE*SIZE, 0..1) for the main subject, or null. */
async function saliency(source) {
  let model;
  try {
    model = await cutoutModel();
  } catch (err) {
    console.warn("Background removal unavailable:", err);
    return null;
  }
  const c = canvas(SIZE, SIZE);
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(source, 0, 0, SIZE, SIZE);
  const px = g.getImageData(0, 0, SIZE, SIZE).data;
  let max = 1e-6;
  for (let i = 0; i < px.length; i += 4) max = Math.max(max, px[i] / 255, px[i + 1] / 255, px[i + 2] / 255);
  const input = new Float32Array(3 * SIZE * SIZE);
  for (let i = 0, p = 0; i < px.length; i += 4, p++) {
    for (let ch = 0; ch < 3; ch++) input[ch * SIZE * SIZE + p] = (px[i + ch] / 255 / max - MEAN[ch]) / STD[ch];
  }
  const { ort, session } = model;
  const feeds = { [session.inputNames[0]]: new ort.Tensor("float32", input, [1, 3, SIZE, SIZE]) };
  const out = await session.run(feeds);
  const d = out[session.outputNames[0]].data;
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of d) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const m = new Float32Array(SIZE * SIZE);
  const span = Math.max(hi - lo, 1e-6);
  for (let i = 0; i < m.length; i++) {
    const v = (d[i] - lo) / span;
    m[i] = Math.min(1, Math.max(0, (v - 0.25) / 0.5));   // firm up the edge, like the server did
  }
  return m;
}

/**
 * Background-removed garment as a canvas (transparent, cropped), or null
 * when the model isn't available or isn't confident.
 */
export async function cutOut(source, maxSide = MAX_SIDE) {
  const m = await saliency(source);
  if (!m) return null;
  let solid = 0, soft = 0, half = 0;
  for (const v of m) {
    if (v > 40 / 255) soft++;
    if (v > 200 / 255) solid++;
    if (v > 0.5) half++;
  }
  const coverage = half / m.length;
  if (coverage < 0.04 || coverage > 0.97 || !soft || solid / soft < 0.7) return null;

  const w = source.width;
  const h = source.height;
  const maskC = canvas(SIZE, SIZE);
  const mg = maskC.getContext("2d");
  const id = mg.createImageData(SIZE, SIZE);
  for (let i = 0; i < m.length; i++) id.data[i * 4 + 3] = Math.round(m[i] * 255);
  mg.putImageData(id, 0, 0);

  const out = canvas(w, h);
  const og = out.getContext("2d", { willReadFrequently: true });
  og.drawImage(source, 0, 0, w, h);
  og.globalCompositeOperation = "destination-in";
  og.filter = "blur(0.6px)";
  og.drawImage(maskC, 0, 0, w, h);
  og.filter = "none";
  og.globalCompositeOperation = "source-over";

  // crop to the garment, plus a little room
  let minX = SIZE, minY = SIZE, maxX = -1, maxY = -1;
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      if (m[y * SIZE + x] > 40 / 255) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    }
  }
  const sx = w / SIZE, sy = h / SIZE;
  const bx = Math.max(0, Math.floor(minX * sx) - 6), by = Math.max(0, Math.floor(minY * sy) - 6);
  const bw = Math.min(w, Math.ceil((maxX + 1) * sx) + 6) - bx, bh = Math.min(h, Math.ceil((maxY + 1) * sy) + 6) - by;
  const scale = Math.min(1, maxSide / Math.max(bw, bh));
  const crop = canvas(Math.round(bw * scale), Math.round(bh * scale));
  crop.getContext("2d").drawImage(out, bx, by, bw, bh, 0, 0, crop.width, crop.height);
  return crop;
}

export const canvasToBlob = (c, transparent = true) => encode(c, transparent);

// ---------------------------------------------------------------- garment colour

/** Main colour of the garment as #rrggbb, ignoring the background, or null. */
export async function garmentColour(source) {
  const W = 96, H = 120;
  const c = canvas(W, H);
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(source, 0, 0, W, H);
  const px = g.getImageData(0, 0, W, H).data;
  const m = await saliency(source);
  const pts = [];
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4;
      const inMask = m ? m[Math.floor((y / H) * SIZE) * SIZE + Math.floor((x / W) * SIZE)] > 160 / 255 : true;
      if (px[i + 3] > 128 && inMask) pts.push([px[i], px[i + 1], px[i + 2]]);
    }
  }
  if (pts.length < 30) return null;
  // k-means with k = 4, deterministic start
  let centres = [0, 0.33, 0.66, 0.99].map((f) => pts[Math.floor(f * (pts.length - 1))].slice());
  const labels = new Uint8Array(pts.length);
  for (let it = 0; it < 15; it++) {
    for (let i = 0; i < pts.length; i++) {
      let best = 0, bd = Infinity;
      for (let k = 0; k < 4; k++) {
        const d = (pts[i][0] - centres[k][0]) ** 2 + (pts[i][1] - centres[k][1]) ** 2 + (pts[i][2] - centres[k][2]) ** 2;
        if (d < bd) { bd = d; best = k; }
      }
      labels[i] = best;
    }
    centres = centres.map((cen, k) => {
      let n = 0, r = 0, gg = 0, b = 0;
      for (let i = 0; i < pts.length; i++) if (labels[i] === k) { n++; r += pts[i][0]; gg += pts[i][1]; b += pts[i][2]; }
      return n ? [r / n, gg / n, b / n] : cen;
    });
  }
  const counts = [0, 0, 0, 0];
  for (const l of labels) counts[l]++;
  const big = centres[counts.indexOf(Math.max(...counts))];
  return "#" + big.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
}

// ---------------------------------------------------------------- dyed stock photos

export const TEMPLATE_FOR = {
  "t-shirt": "tee", "tank top": "tee", "polo": "tee", "athletic top": "tee",
  "shirt": "shirt", "dress shirt": "shirt", "blouse": "shirt",
  "sweater": "sweater", "sweatshirt": "sweater", "turtleneck": "turtleneck", "hoodie": "hoodie",
  "jeans": "jeans", "chinos": "trousers", "trousers": "trousers", "cargo pants": "trousers",
  "joggers": "joggers", "leggings": "joggers", "shorts": "shorts", "athletic shorts": "shorts",
  "skirt": "skirt",
  "casual dress": "dress", "sundress": "dress", "cocktail dress": "dress", "evening gown": "dress", "jumpsuit": "dress",
  "cardigan": "cardigan", "denim jacket": "jacket", "windbreaker": "jacket", "raincoat": "coat",
  "bomber jacket": "bomber", "leather jacket": "leather-jacket", "blazer": "blazer",
  "suit jacket": "blazer", "wool coat": "coat", "trench coat": "coat", "parka": "coat", "puffer jacket": "puffer",
  "sneakers": "sneakers", "running shoes": "sneakers", "loafers": "loafers", "dress shoes": "loafers",
  "flats": "loafers", "heels": "loafers", "ankle boots": "boots", "rain boots": "boots", "snow boots": "boots",
  "sandals": "sandals", "cap": "cap", "beanie": "beanie",
};
const CATEGORY_FALLBACK = { top: "tee", bottom: "trousers", dress: "dress", outerwear: "jacket", footwear: "sneakers" };

export function templateName(category, subcategory) {
  return TEMPLATE_FOR[(subcategory || "").trim().toLowerCase()] || CATEGORY_FALLBACK[category] || null;
}

const templateCache = new Map();

async function template(name) {
  if (!templateCache.has(name)) {
    templateCache.set(name, (async () => {
      const img = await loadImage(new URL(`../../images/stock-templates/${name}.png`, import.meta.url).href);
      const c = canvas(img.naturalWidth, img.naturalHeight);
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(img, 0, 0);
      const px = g.getImageData(0, 0, c.width, c.height).data;
      const n = c.width * c.height;
      const L = new Float32Array(n);
      const A = new Uint8ClampedArray(n);
      let sum = 0, cnt = 0;
      for (let i = 0; i < n; i++) {
        const grey = px[i * 4] / 255;
        const lin = grey <= 0.04045 ? grey / 12.92 : ((grey + 0.055) / 1.055) ** 2.4;
        const f = lin > 216 / 24389 ? Math.cbrt(lin) : (lin * 24389 / 27 + 16) / 116;
        L[i] = 116 * f - 16;
        A[i] = px[i * 4 + 3];
        if (A[i] > 128) { sum += L[i]; cnt++; }
      }
      return { w: c.width, h: c.height, L, A, mean: cnt ? sum / cnt : 50 };
    })());
  }
  return templateCache.get(name);
}

function labToRgb(L, a, b) {
  const fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200;
  const inv = (t) => (t ** 3 > 216 / 24389 ? t ** 3 : (116 * t - 16) / (24389 / 27));
  const x = inv(fx) * 0.95047, y = inv(fy), z = inv(fz) * 1.08883;
  const lin = [
    3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
    -0.969266 * x + 1.8760108 * y + 0.041556 * z,
    0.0556434 * x - 0.2040259 * y + 1.0572252 * z,
  ];
  return lin.map((v) => {
    v = Math.min(1, Math.max(0, v));
    v = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
    return Math.round(Math.min(1, Math.max(0, v)) * 255);
  });
}

/** A real garment photo of this type, dyed to hex. Canvas, or null if no template (e.g. watches). */
export async function dyedStock(category, subcategory, hex) {
  const name = templateName(category, subcategory);
  if (!name) return null;
  let t;
  try { t = await template(name); } catch { return null; }
  const [Lt, at, bt] = hexToLab(hex);
  const headroom = Math.min(Lt, 100 - Lt);
  const gain = 0.95 * Math.min(1, (headroom + 14) / 42);
  const c = canvas(t.w, t.h);
  const g = c.getContext("2d");
  const out = g.createImageData(t.w, t.h);
  for (let i = 0; i < t.L.length; i++) {
    if (!t.A[i]) continue;
    const L = Math.min(99, Math.max(2, Lt + (t.L[i] - t.mean) * gain));
    const cs = Math.min(1.1, Math.max(0.6, 0.75 + 0.25 * (L / Math.max(Lt, 1))));
    const [r, gg, b] = labToRgb(L, at * cs, bt * cs);
    out.data[i * 4] = r; out.data[i * 4 + 1] = gg; out.data[i * 4 + 2] = b; out.data[i * 4 + 3] = t.A[i];
  }
  g.putImageData(out, 0, 0);
  return c;
}

// ---------------------------------------------------------------- patterns

/**
 * Is the fabric patterned? Looks at the middle of the garment photo and counts
 * sharp light/dark changes in both directions. Returns "striped",
 * "patterned" or "".
 */
export async function patternOf(blob, category) {
  try {
    const bmp = await createImageBitmap(blob);
    const box = category === "bottom" ? [0.22, 0.18, 0.26, 0.3] : [0.34, 0.3, 0.32, 0.3];
    const c = document.createElement("canvas");
    c.width = 96; c.height = 96;
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, bmp.width * box[0], bmp.height * box[1], bmp.width * box[2], bmp.height * box[3], 0, 0, 96, 96);
    bmp.close?.();
    const { data } = ctx.getImageData(0, 0, 96, 96);
    const L = new Float32Array(96 * 96);
    for (let i = 0, p = 0; i < data.length; i += 4, p++) L[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    let h = 0, v = 0, n = 0;
    for (let y = 1; y < 96; y++) {
      for (let x = 1; x < 96; x++) {
        const p = y * 96 + x;
        if (Math.abs(L[p] - L[p - 1]) > 20) h++;
        if (Math.abs(L[p] - L[p - 96]) > 20) v++;
        n++;
      }
    }
    const edges = (h + v) / n;
    if (edges < 0.1) return "";
    // edges mostly one way round = stripes
    return Math.max(h, v) > 2.2 * Math.min(h, v) ? "striped" : "patterned";
  } catch {
    return "";
  }
}

