"""
Rule-based scoring: the parts of "does this outfit work?" that are true for
everyone. Each scorer returns a value in 0..1 and a list of short notes the
explanation writer can use.

Kept strictly separate from the ML layer (services/ml.py), as the brief asks.

An *item* here is a dict with: id, name, category, subcategory, style,
main_color_hex, secondary_color_hex, occasions (list), seasons (list).
A *context* is a dict with: occasion, weather, temperature_c, style (or None),
palette, favorite_colors (list), avoided_colors (list), preferred_styles (list).
"""

from functools import lru_cache
from itertools import combinations

from . import catalog
from .color import outfit_harmony, palette_fit, pair_harmony  # noqa: F401  (pair_harmony re-exported for tests)

CORE_ROLES = ("top", "bottom", "dress", "footwear")
ROLE_WEIGHT = {"top": 1.0, "bottom": 1.0, "dress": 2.0, "footwear": 1.0, "outerwear": 0.7, "accessory": 0.3}


def attrs(item):
    return catalog.attributes(item["category"], item.get("subcategory"))


def is_sporty(item):
    return item.get("style") == "sporty" or "sporty" in attrs(item)["tags"]


# ---------------------------------------------------------------------------
# occasion
# ---------------------------------------------------------------------------

def item_occasion_fit(item, occasion):
    rule = catalog.OCCASION_RULES[occasion]
    f = attrs(item)["formality"]
    lo, hi = rule["formality"]
    gap = 0 if lo <= f <= hi else min(abs(f - lo), abs(f - hi))
    formality_fit = max(0.0, 1 - 0.35 * gap)

    tagged = occasion in (item.get("occasions") or [])
    score = 0.55 * (1.0 if tagged else 0.4) + 0.45 * formality_fit

    if item["category"] != "accessory":
        if rule["sporty"] is True and not is_sporty(item):
            score *= 0.6 if item["category"] in ("top", "bottom", "footwear") else 0.85
        elif rule["sporty"] is False and is_sporty(item):
            score *= 0.55
    return max(0.0, min(1.0, score))


def score_occasion(items, ctx):
    occasion = ctx["occasion"]
    total = weight = 0.0
    for it in items:
        w = ROLE_WEIGHT[it["category"]]
        total += w * item_occasion_fit(it, occasion)
        weight += w
    score = total / weight if weight else 0.0

    core = [attrs(it)["formality"] for it in items if it["category"] in CORE_ROLES]
    spread = (max(core) - min(core)) if core else 0
    notes = []
    if spread >= 3:
        score -= 0.12
        notes.append("mixed_formality")

    tagged = [it for it in items if it["category"] != "accessory" and occasion in (it.get("occasions") or [])]
    if len(tagged) == len([it for it in items if it["category"] != "accessory"]):
        notes.append("all_tagged")
    elif not tagged:
        notes.append("none_tagged")
    return max(0.0, min(1.0, score)), notes, {"formality_spread": spread, "tagged": len(tagged)}


# ---------------------------------------------------------------------------
# weather
# ---------------------------------------------------------------------------

def target_warmth(temp_c):
    """Total warmth points an outfit should add up to at this temperature."""
    if temp_c >= 28:
        return 1
    if temp_c >= 22:
        return 2
    if temp_c >= 16:
        return 3
    if temp_c >= 10:
        return 4
    if temp_c >= 3:
        return 5
    return 6


WARM_ACCESSORY_MAX_TEMP = 12   # above this a scarf or beanie is styling, not insulation


def outfit_warmth(items, temp_c):
    total = 0
    for it in items:
        if it["category"] == "footwear":
            continue
        a = attrs(it)
        if it["category"] == "accessory":
            # scarves and beanies only count as warmth when it's actually cold,
            # so a scarf can't "fix" a too-light outfit on a warm day
            if a["warmth"] == 0 or temp_c >= WARM_ACCESSORY_MAX_TEMP:
                continue
        total += a["warmth"]
    return total


def _season_ok(item, temp_c):
    seasons = item.get("seasons") or []
    want = catalog.season_for_temperature(temp_c)
    if want in seasons:
        return True
    # spring and autumn are interchangeable in-between weather
    return want in ("spring", "autumn") and ({"spring", "autumn"} & set(seasons))


def item_weather_fit(item, ctx):
    """Single-item check used to shortlist pieces before building outfits."""
    temp, weather = ctx["temperature_c"], ctx["weather"]
    a = attrs(item)
    score = 0.65 if _season_ok(item, temp) else 0.35
    if item["category"] == "footwear":
        if weather in ("rainy", "snowy") and "open" in a["tags"]:
            score -= 0.3
        if weather == "snowy":
            score += 0.25 if "snow" in a["tags"] else (0.1 if "rain" in a["tags"] else -0.1)
        elif weather == "rainy" and "rain" in a["tags"]:
            score += 0.2
        if temp >= 26 and a["warmth"] >= 2:
            score -= 0.25
    elif item["category"] == "outerwear":
        if temp >= 24:
            score -= 0.3
        if weather in ("rainy", "snowy") and ({"rain", "snow"} & set(a["tags"])):
            score += 0.25
        if temp < 5 and a["warmth"] >= 3:
            score += 0.2
    else:
        if temp >= 26 and a["warmth"] >= 2:
            score -= 0.3
        if temp < 8 and a["warmth"] == 0 and item["category"] != "accessory":
            score -= 0.2
    if item["category"] == "accessory":
        if "sun" in a["tags"] and weather == "sunny":
            score += 0.25
        if "rain" in a["tags"] and weather == "rainy":
            score += 0.3
        if a["warmth"] >= 2:
            score += 0.2 if temp < 8 else (-0.45 if temp >= 16 else 0)
    return max(0.0, min(1.0, score + 0.2))


def score_weather(items, ctx):
    temp, weather = ctx["temperature_c"], ctx["weather"]
    warmth = outfit_warmth(items, temp)
    target = target_warmth(temp)
    warmth_fit = max(0.0, 1 - 0.22 * abs(warmth - target))

    wearable = [it for it in items if it["category"] != "accessory"]
    season_fit = sum(1 for it in wearable if _season_ok(it, temp)) / max(1, len(wearable))

    score = 0.55 * warmth_fit + 0.3 * season_fit + 0.15
    notes = []
    shoes = next((it for it in items if it["category"] == "footwear"), None)
    outer = next((it for it in items if it["category"] == "outerwear"), None)
    shoe_tags = attrs(shoes)["tags"] if shoes else []
    outer_tags = attrs(outer)["tags"] if outer else []

    if weather == "rainy":
        if "open" in shoe_tags:
            score -= 0.3
            notes.append("open_shoes_in_rain")
        if "rain" in outer_tags or "rain" in shoe_tags:
            score += 0.08
            notes.append("rain_ready")
        if not outer and temp < 20:
            score -= 0.08
    if weather == "snowy":
        if not ({"snow", "rain"} & set(shoe_tags)):
            score -= 0.25
            notes.append("shoes_not_for_snow")
        if not outer:
            score -= 0.3
            notes.append("no_coat_in_snow")
    if temp < 8 and not outer:
        score -= 0.2
        notes.append("cold_without_layer")
    if temp >= 24 and outer and attrs(outer)["warmth"] >= 2:
        score -= 0.2
        notes.append("too_warm_layer")
    if weather == "windy" and outer:
        score += 0.04
    warm_extras = [it for it in items if it["category"] == "accessory" and attrs(it)["warmth"] >= 2]
    if warm_extras and temp >= 16:
        score -= 0.15
        notes.append("warm_accessory_on_warm_day")

    if warmth < target - 1:
        notes.append("too_cold")
    elif warmth > target + 1:
        notes.append("too_warm")
    else:
        notes.append("warmth_right")
    return max(0.0, min(1.0, score)), notes, {"warmth": warmth, "target_warmth": target,
                                              "season_fit": round(season_fit, 3)}


# ---------------------------------------------------------------------------
# style
# ---------------------------------------------------------------------------

def item_style_fit(item, ctx):
    wanted = ctx.get("style")
    if wanted:
        return catalog.style_affinity(item["style"], wanted)
    preferred = ctx.get("preferred_styles") or []
    if preferred:
        return max(catalog.style_affinity(item["style"], s) for s in preferred)
    return 0.75


def score_style(items, ctx):
    styles = [it["style"] for it in items if it["category"] != "accessory"]
    pairs = list(combinations(styles, 2))
    coherence = sum(catalog.style_affinity(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0

    notes = []
    wanted = ctx.get("style")
    if wanted or ctx.get("preferred_styles"):
        match = sum(item_style_fit(it, ctx) for it in items if it["category"] != "accessory") / max(1, len(styles))
        score = 0.6 * match + 0.4 * coherence
        exact = sum(1 for s in styles if s == wanted) if wanted else 0
        if wanted and exact == len(styles):
            notes.append("all_match_style")
        elif wanted and exact == 0:
            notes.append("no_style_match")
    else:
        match = None
        score = coherence
    if coherence >= 0.85:
        notes.append("coherent")
    elif coherence < 0.5:
        notes.append("mixed_styles")
    return max(0.0, min(1.0, score)), notes, {"coherence": round(coherence, 3),
                                              "match": None if match is None else round(match, 3)}


# ---------------------------------------------------------------------------
# colour
# ---------------------------------------------------------------------------

@lru_cache(maxsize=20000)
def _harmony_cached(hexes):
    return outfit_harmony(list(hexes))


def score_color(items, ctx):
    # accessories count, but only the first one, so a belt can't sink a look
    ordered = [it for it in items if it["category"] != "accessory"]
    accessories = [it for it in items if it["category"] == "accessory"][:1]
    hexes = tuple(it["main_color_hex"] for it in ordered + accessories)

    harmony, detail = _harmony_cached(hexes)
    palette = ctx.get("palette") or "any"
    pal = palette_fit(list(hexes), palette)
    score = harmony if palette == "any" else 0.72 * harmony + 0.28 * pal

    names = [it.get("main_color_name") for it in items]
    fav = set(ctx.get("favorite_colors") or [])
    avoid = set(ctx.get("avoided_colors") or [])
    fav_hits = sum(1 for n in names if n in fav)
    avoid_hits = sum(1 for n in names if n in avoid)
    score += min(0.1, 0.05 * fav_hits) - 0.15 * avoid_hits

    notes = [detail["weakest"]["kind"]] if detail["weakest"] else []
    if avoid_hits:
        notes.append("has_avoided_colour")
    if fav_hits:
        notes.append("has_favourite_colour")
    if palette != "any":
        notes.append("palette_match" if pal >= 0.7 else "palette_miss")
    detail = {
        "harmony": round(harmony, 3),
        "palette_fit": round(pal, 3),
        "weakest_pair": detail["weakest"],
        "loud": detail["loud"],
        "mean_pair": detail.get("mean"),
    }
    return max(0.0, min(1.0, score)), notes, detail


# ---------------------------------------------------------------------------

def score_rules(items, ctx):
    """All four rule components for one outfit."""
    out = {}
    for name, fn in (("occasion", score_occasion), ("weather", score_weather),
                     ("style", score_style), ("color", score_color)):
        score, notes, detail = fn(items, ctx)
        out[name] = {"score": round(score, 4), "notes": notes, "detail": detail}
    return out


def item_prefit(item, ctx):
    """Quick single-item suitability used to shortlist candidates."""
    return (0.45 * item_occasion_fit(item, ctx["occasion"])
            + 0.35 * item_weather_fit(item, ctx)
            + 0.20 * item_style_fit(item, ctx))
