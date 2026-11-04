// Colour maths in CIELAB.
//
// RGB distances don't match how people see colour (two greens can be far
// apart in RGB and look identical). Lab is built so that equal distances
// look roughly equally different, and CIEDE2000 refines that further.
// The backend uses the same formulas in Python; this copy powers the
// little demo on the landing page.

export function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? [...h].map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

// sRGB (D65) -> XYZ -> Lab
export function rgbToLab([r, g, b]) {
  const lin = (c) => {
    c /= 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const R = lin(r), G = lin(g), B = lin(b);

  const x = (R * 0.4124564 + G * 0.3575761 + B * 0.1804375) / 0.95047;
  const y = (R * 0.2126729 + G * 0.7151522 + B * 0.072175) / 1.0;
  const z = (R * 0.0193339 + G * 0.119192 + B * 0.9503041) / 1.08883;

  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (t * 24389) / 27 / 116 + 16 / 116);
  const fx = f(x), fy = f(y), fz = f(z);

  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

export const hexToLab = (hex) => rgbToLab(hexToRgb(hex));

export function chroma([, a, b]) {
  return Math.hypot(a, b);
}

export function hueAngle([, a, b]) {
  const h = (Math.atan2(b, a) * 180) / Math.PI;
  return h < 0 ? h + 360 : h;
}

// CIEDE2000, following Sharma, Wu & Dalal (2005).
export function deltaE2000(lab1, lab2) {
  const [L1, a1, b1] = lab1;
  const [L2, a2, b2] = lab2;
  const rad = Math.PI / 180;

  const C1 = Math.hypot(a1, b1);
  const C2 = Math.hypot(a2, b2);
  const Cbar = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)));

  const a1p = (1 + G) * a1;
  const a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1);
  const C2p = Math.hypot(a2p, b2);

  const hp = (a, b) => {
    if (a === 0 && b === 0) return 0;
    const h = Math.atan2(b, a) / rad;
    return h < 0 ? h + 360 : h;
  };
  const h1p = hp(a1p, b1);
  const h2p = hp(a2p, b2);

  const dLp = L2 - L1;
  const dCp = C2p - C1p;

  let dhp = 0;
  if (C1p * C2p !== 0) {
    dhp = h2p - h1p;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp / 2) * rad);

  const Lbarp = (L1 + L2) / 2;
  const Cbarp = (C1p + C2p) / 2;

  let hbarp = h1p + h2p;
  if (C1p * C2p !== 0) {
    if (Math.abs(h1p - h2p) > 180) hbarp += h1p + h2p < 360 ? 360 : -360;
    hbarp /= 2;
  }

  const T = 1
    - 0.17 * Math.cos((hbarp - 30) * rad)
    + 0.24 * Math.cos(2 * hbarp * rad)
    + 0.32 * Math.cos((3 * hbarp + 6) * rad)
    - 0.2 * Math.cos((4 * hbarp - 63) * rad);

  const dTheta = 30 * Math.exp(-(((hbarp - 275) / 25) ** 2));
  const Rc = 2 * Math.sqrt(Cbarp ** 7 / (Cbarp ** 7 + 25 ** 7));
  const Sl = 1 + (0.015 * (Lbarp - 50) ** 2) / Math.sqrt(20 + (Lbarp - 50) ** 2);
  const Sc = 1 + 0.045 * Cbarp;
  const Sh = 1 + 0.015 * Cbarp * T;
  const Rt = -Math.sin(2 * dTheta * rad) * Rc;

  return Math.sqrt(
    (dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh)
  );
}

// Below this chroma a colour reads as a neutral (white, grey, black, navy-ish
// darks, beige). Neutrals go with nearly everything, which is the whole
// reason capsule wardrobes work.
export const NEUTRAL_CHROMA = 14;

export function isNeutral(lab) {
  const [L] = lab;
  const C = chroma(lab);
  if (C < NEUTRAL_CHROMA || L < 18) return true;
  // "Fashion neutrals": navy, denim, chocolate brown (dark and muted) and
  // khaki, stone, cream (light and muted). They behave like neutrals.
  return (C < 34 && L < 42) || (C < 28 && L > 62);
}

/**
 * How well two colours sit together, 0..1, plus a short reason.
 * This is a heuristic, not a law — taste lives in the ML layer.
 */
export function pairHarmony(hexA, hexB) {
  const A = hexToLab(hexA);
  const B = hexToLab(hexB);
  const dE = deltaE2000(A, B);
  const nA = isNeutral(A);
  const nB = isNeutral(B);
  const dL = Math.abs(A[0] - B[0]);

  if (nA && nB) {
    return dL > 25
      ? { score: 0.92, kind: "neutral-contrast", dE }
      : { score: 0.78, kind: "neutral-flat", dE };
  }
  if (nA || nB) {
    return { score: dL > 15 ? 0.9 : 0.8, kind: "anchored", dE };
  }

  if (dE < 9) return { score: 0.84, kind: "tonal", dE };

  let dh = Math.abs(hueAngle(A) - hueAngle(B));
  if (dh > 180) dh = 360 - dh;

  if (dh < 35) return { score: dL > 12 ? 0.8 : 0.62, kind: "analogous", dE };
  if (dh > 150) return { score: 0.7, kind: "complementary", dE };
  return { score: 0.42, kind: "clash", dE };
}
