"""
Colour maths in CIELAB, and the colour rules built on top of it.

Why Lab: distances in RGB don't match what people see. Lab was designed so
that equal steps look roughly equally different, and CIEDE2000 (used here)
corrects the remaining unevenness in blues and neutrals.

Pure Python, no Flask, so the notebook can import it.
"""

import math
import re
from functools import lru_cache
from itertools import combinations

HEX_RE = re.compile(r"^#[0-9a-f]{6}$")

# Named swatches people pick from. The name doubles as the colour filter in
# the wardrobe, and custom colours snap to the nearest one.
NAMED_COLORS = {
    "black": "#1b1b1d",
    "charcoal": "#3a3d42",
    "grey": "#8a8d91",
    "light grey": "#c8cacc",
    "white": "#f5f5f2",
    "cream": "#efe6d2",
    "beige": "#d8c3a0",
    "khaki": "#b8a77a",
    "camel": "#b8864b",
    "brown": "#6b4428",
    "navy": "#1f2a4a",
    "denim": "#3c5a8a",
    "blue": "#2f6fd0",
    "light blue": "#a9c4e4",
    "teal": "#1f7a7a",
    "green": "#2f7d4f",
    "olive": "#6b7340",
    "mint": "#a8dcc0",
    "yellow": "#f0c419",
    "mustard": "#c99a2e",
    "orange": "#e2702f",
    "coral": "#f07a6a",
    "red": "#c42b2b",
    "burgundy": "#6e2238",
    "pink": "#e88aa8",
    "magenta": "#c2357a",
    "lavender": "#b9a7da",
    "purple": "#5e3a8a",
}


def normalize_hex(value):
    """'#ABC' / 'abc123' / '#AbC123' -> '#aabbcc' or None if it isn't a colour."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v.startswith("#"):
        v = "#" + v
    if re.fullmatch(r"#[0-9a-f]{3}", v):
        v = "#" + "".join(c * 2 for c in v[1:])
    return v if HEX_RE.match(v) else None


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_lab(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (t * 24389 / 27 + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


@lru_cache(maxsize=4096)
def hex_to_lab(hex_color):
    return rgb_to_lab(hex_to_rgb(hex_color))


def chroma(lab):
    return math.hypot(lab[1], lab[2])


def hue_angle(lab):
    h = math.degrees(math.atan2(lab[2], lab[1]))
    return h + 360 if h < 0 else h


def delta_e_2000(lab1, lab2):
    """CIEDE2000 colour difference (Sharma, Wu & Dalal, 2005)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hp(a, b):
        if a == 0 and b == 0:
            return 0.0
        h = math.degrees(math.atan2(b, a))
        return h + 360 if h < 0 else h

    h1p, h2p = hp(a1p, b1), hp(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = 0.0
    if C1p * C2p != 0:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    Lbarp = (L1 + L2) / 2
    Cbarp = (C1p + C2p) / 2
    hbarp = h1p + h2p
    if C1p * C2p != 0:
        if abs(h1p - h2p) > 180:
            hbarp += 360 if hbarp < 360 else -360
        hbarp /= 2

    T = (1 - 0.17 * math.cos(math.radians(hbarp - 30))
         + 0.24 * math.cos(math.radians(2 * hbarp))
         + 0.32 * math.cos(math.radians(3 * hbarp + 6))
         - 0.20 * math.cos(math.radians(4 * hbarp - 63)))
    d_theta = 30 * math.exp(-(((hbarp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbarp ** 7 / (Cbarp ** 7 + 25 ** 7))
    Sl = 1 + (0.015 * (Lbarp - 50) ** 2) / math.sqrt(20 + (Lbarp - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -math.sin(math.radians(2 * d_theta)) * Rc

    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(hex_a, hex_b):
    return delta_e_2000(hex_to_lab(hex_a), hex_to_lab(hex_b))


@lru_cache(maxsize=2048)
def nearest_name(hex_color):
    """Snap any colour to the closest named swatch."""
    lab = hex_to_lab(hex_color)
    return min(NAMED_COLORS, key=lambda n: delta_e_2000(lab, hex_to_lab(NAMED_COLORS[n])))


# ---------------------------------------------------------------------------
# colour behaviour
# ---------------------------------------------------------------------------

NEUTRAL_CHROMA = 14


def is_neutral(hex_color):
    L, _, _ = lab = hex_to_lab(hex_color)
    C = chroma(lab)
    if C < NEUTRAL_CHROMA or L < 18:
        return True
    # "fashion neutrals": navy, denim, chocolate brown (dark and muted) and
    # khaki, stone, cream (light and muted)
    return (C < 34 and L < 42) or (C < 28 and L > 62)


def is_bold(hex_color):
    return chroma(hex_to_lab(hex_color)) > 45


def is_pastel(hex_color):
    lab = hex_to_lab(hex_color)
    return lab[0] > 70 and 12 < chroma(lab) < 45


def is_earthy(hex_color):
    lab = hex_to_lab(hex_color)
    C = chroma(lab)
    h = hue_angle(lab)
    # browns, olives, rusts, khakis: warm-ish hues, muted to medium chroma
    return 8 < C < 50 and 25 <= h <= 115 and lab[0] < 80


def pair_harmony(hex_a, hex_b):
    """
    How well two colours sit together, 0..1, with the kind of relationship.
    Same rules as the landing-page demo (assets/js/lib/color.js).
    """
    A, B = hex_to_lab(hex_a), hex_to_lab(hex_b)
    dE = delta_e_2000(A, B)
    nA, nB = is_neutral(hex_a), is_neutral(hex_b)
    dL = abs(A[0] - B[0])

    if nA and nB:
        return (0.92, "neutral-contrast", dE) if dL > 25 else (0.78, "neutral-flat", dE)
    if nA or nB:
        return (0.9 if dL > 15 else 0.8), "anchored", dE
    if dE < 9:
        return 0.84, "tonal", dE

    dh = abs(hue_angle(A) - hue_angle(B))
    if dh > 180:
        dh = 360 - dh
    if dh < 35:
        return (0.8 if dL > 12 else 0.62), "analogous", dE
    if dh > 150:
        return 0.7, "complementary", dE
    return 0.42, "clash", dE


def outfit_harmony(hexes):
    """
    Harmony for a whole outfit. Returns (score 0..1, details dict).
    Uses each piece's main colour; the weakest pair matters most, because
    one clash ruins an otherwise good outfit.
    """
    hexes = [h for h in hexes if h]
    if len(hexes) < 2:
        return 0.75, {"pairs": [], "weakest": None, "loud": 0}

    pairs = []
    for (i, a), (j, b) in combinations(enumerate(hexes), 2):
        score, kind, dE = pair_harmony(a, b)
        pairs.append({"a": i, "b": j, "score": score, "kind": kind, "delta_e": round(dE, 1)})

    mean = sum(p["score"] for p in pairs) / len(pairs)
    weakest = min(pairs, key=lambda p: p["score"])
    loud = sum(1 for h in hexes if not is_neutral(h))

    score = 0.6 * mean + 0.4 * weakest["score"]
    if loud >= 3:
        score -= 0.06 * (loud - 2)   # three or more saturated colours gets busy
    score = max(0.0, min(1.0, score))
    return score, {"pairs": pairs, "weakest": weakest, "loud": loud, "mean": round(mean, 3)}


def palette_fit(hexes, palette):
    """How well the outfit's colours match a requested palette, 0..1."""
    hexes = [h for h in hexes if h]
    if not hexes or palette in (None, "", "any"):
        return 1.0
    n = len(hexes)
    if palette == "neutral":
        return sum(is_neutral(h) for h in hexes) / n
    if palette == "earthy":
        return sum(is_earthy(h) or is_neutral(h) for h in hexes) / n * 0.8 + \
            (0.2 if any(is_earthy(h) for h in hexes) else 0)
    if palette == "pastel":
        hits = sum(is_pastel(h) for h in hexes)
        soft = sum(is_neutral(h) and hex_to_lab(h)[0] > 60 for h in hexes)
        return min(1.0, (hits + 0.5 * soft) / n + (0.2 if hits else 0))
    if palette == "bold":
        bold = sum(is_bold(h) for h in hexes)
        if bold == 0:
            return 0.2
        return 1.0 if bold <= 2 else 0.75
    if palette == "monochrome":
        if len(hexes) == 1:
            return 1.0
        coloured = [h for h in hexes if not is_neutral(h)]
        if len(coloured) <= 1:
            return 0.85
        diffs = [delta_e(a, b) for a, b in combinations(coloured, 2)]
        return max(0.0, 1 - (sum(diffs) / len(diffs)) / 40)
    return 1.0
