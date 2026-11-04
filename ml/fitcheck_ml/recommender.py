"""
The hybrid recommendation engine.

    wardrobe items ──▶ shortlist per slot ──▶ build every valid outfit
                         (rules.item_prefit)      top+bottom+shoes, or dress+shoes,
                                                  ± outerwear, ± accessories
                   ──▶ rule scores (rules.py)
                   ──▶ ML scores   (ml.py: decision tree + KNN)
                   ──▶ personal feedback (ml.personal_similarity + item likes)
                   ──▶ weighted blend → 0..100, plus a written explanation

It only ever picks from the items passed in, which are the person's own
active wardrobe, so it can't recommend something they don't own.

No database or Flask in here: the route loads the data and saves the result.
"""

import hashlib
import math
import random
from itertools import product

from . import features, ml, rules

WEIGHTS = {
    "occasion": 0.22,
    "weather": 0.22,
    "color": 0.20,
    "style": 0.14,
    "ml": 0.14,
    "feedback": 0.08,
}

SHORTLIST = {"top": 7, "bottom": 7, "dress": 4, "footwear": 6, "outerwear": 3, "accessory": 4}
ML_POOL = 80          # how many rule-ranked outfits go through the ML models
RANDOM_POOL = 4       # "generate another" samples among this many of the best


class NotEnoughItems(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__("not enough items")


def signature(items):
    ids = sorted(str(it["id"]) for it in items)
    return hashlib.sha1(",".join(ids).encode(), usedforsecurity=False).hexdigest()  # an id, not a security hash


def _need_outer(ctx):
    return ctx["temperature_c"] < 12 or ctx["weather"] == "snowy"


def _want_outer(ctx):
    return ctx["temperature_c"] < 21 or ctx["weather"] in ("rainy", "windy")


def _shortlist(items, ctx):
    by_role = {role: [] for role in SHORTLIST}
    for it in items:
        by_role[it["category"]].append(it)
    for role, pool in by_role.items():
        pool.sort(key=lambda it: rules.item_prefit(it, ctx), reverse=True)
        by_role[role] = pool[: SHORTLIST[role]]
    return by_role


def missing_roles(items):
    cats = {it["category"] for it in items}
    missing = []
    if "footwear" not in cats:
        missing.append("footwear")
    if "dress" not in cats and not ({"top", "bottom"} <= cats):
        if "top" not in cats:
            missing.append("top")
        if "bottom" not in cats:
            missing.append("bottom")
    return missing


def _rule_total(components, weights):
    w = sum(weights[k] for k in ("occasion", "weather", "color", "style"))
    return sum(weights[k] * components[k]["score"] for k in ("occasion", "weather", "color", "style")) / w


def build_candidates(items, ctx):
    """Every reasonable outfit from the shortlist, rule-scored."""
    slots = _shortlist(items, ctx)
    bases = [list(c) for c in product(slots["top"], slots["bottom"], slots["footwear"])]
    bases += [list(c) for c in product(slots["dress"], slots["footwear"])]

    outer_options = [None]
    if slots["outerwear"] and (_need_outer(ctx) or _want_outer(ctx)):
        outer_options = slots["outerwear"] if _need_outer(ctx) else [None] + slots["outerwear"]

    candidates = []
    for base in bases:
        for outer in outer_options:
            outfit = base + ([outer] if outer else [])
            comp = rules.score_rules(outfit, ctx)
            candidates.append({"items": outfit, "rules": comp, "rule_total": _rule_total(comp, WEIGHTS)})

    candidates.sort(key=lambda c: c["rule_total"], reverse=True)

    # accessories: greedily add up to two to the strongest outfits if they help
    for cand in candidates[:40]:
        for acc in slots["accessory"]:
            if sum(1 for it in cand["items"] if it["category"] == "accessory") >= 2:
                break
            trial = cand["items"] + [acc]
            comp = rules.score_rules(trial, ctx)
            total = _rule_total(comp, WEIGHTS)
            if total > cand["rule_total"] + 0.004:
                cand.update(items=trial, rules=comp, rule_total=total)

    candidates.sort(key=lambda c: c["rule_total"], reverse=True)
    return candidates


def item_affinity(cand_items, liked_counts, disliked_counts):
    """+ for pieces that keep showing up in liked outfits, - for disliked ones."""
    vals = []
    for it in cand_items:
        l, d = liked_counts.get(it["id"], 0), disliked_counts.get(it["id"], 0)
        if l or d:
            vals.append((l - d) / (l + d + 1))
    if not vals:
        return 0.5
    return 0.5 + 0.5 * (sum(vals) / len(vals))


def recommend(items, ctx, bundle=None, history=None, liked_counts=None, disliked_counts=None,
              exclude=(), recent=None, rng=None):
    """
    items:   the person's active wardrobe (list of item dicts)
    ctx:     occasion/weather/temperature/style/palette + stored preferences
    bundle:  ml.ModelBundle or None
    history: [(raw_feature_dict, verdict), ...] from past feedback
    exclude: signatures already shown this session ("generate another")
    recent:  items of the outfit shown just before, to nudge towards variety
    Returns a dict with items, score, breakdown, explanation, signature, engine.
    """
    missing = missing_roles(items)
    if missing:
        raise NotEnoughItems(missing)

    rng = rng or random.Random()  # nosec B311: only picks which good outfit to show, not security
    history = history or []
    liked_counts = liked_counts or {}
    disliked_counts = disliked_counts or {}
    exclude = set(exclude)

    candidates = [c for c in build_candidates(items, ctx) if signature(c["items"]) not in exclude]
    if not candidates:
        raise NotEnoughItems([])  # every combination has been shown already

    pool = candidates[:ML_POOL]
    rows = [features.build_features(c["items"], ctx, c["rules"]) for c in pool]

    ml_out = bundle.predict(rows) if bundle is not None and bundle.available else None
    personal = ml.personal_similarity(rows, history, bundle)
    use_feedback = personal is not None

    weights = dict(WEIGHTS)
    if ml_out is None:
        weights.pop("ml")
    if not use_feedback:
        weights.pop("feedback")
    wsum = sum(weights.values())

    recent_ids = {it["id"] for it in (recent or [])}
    for i, cand in enumerate(pool):
        comp = {k: cand["rules"][k]["score"] for k in ("occasion", "weather", "color", "style")}
        if ml_out is not None:
            comp["ml"] = float(ml_out[0][i])
        if use_feedback:
            comp["feedback"] = float(0.6 * personal[i] + 0.4 * item_affinity(cand["items"], liked_counts,
                                                                              disliked_counts))
        total = sum(weights[k] * comp[k] for k in weights) / wsum
        if recent_ids:
            shared = sum(1 for it in cand["items"] if it["id"] in recent_ids and it["category"] in rules.CORE_ROLES)
            total -= 0.02 * shared
        cand["components"] = comp
        cand["total"] = total
        cand["features"] = rows[i]
        if ml_out is not None:
            cand["ml_detail"] = {"decision_tree": float(ml_out[1][i]), "knn": float(ml_out[2][i])}

    pool.sort(key=lambda c: c["total"], reverse=True)

    if exclude:
        # asked for another: pick among the next best so repeats feel fresh
        top = pool[:RANDOM_POOL]
        best = top[0]["total"]
        weights_r = [math.exp((c["total"] - best) * 25) for c in top]
        chosen = rng.choices(top, weights=weights_r, k=1)[0]
    else:
        chosen = pool[0]

    score = int(round(100 * max(0.0, min(1.0, chosen["total"]))))
    engine = "hybrid" if ml_out is not None else "rules"

    breakdown = {
        "weights": {k: round(v / wsum, 3) for k, v in weights.items()},
        "components": {k: round(v, 4) for k, v in chosen["components"].items()},
        "rules": chosen["rules"],
        "ml": chosen.get("ml_detail"),
        "feedback_used": use_feedback,
        "feedback_count": len(history),
        "features": chosen["features"],
        "candidates_considered": len(candidates),
    }
    return {
        "items": order_items(chosen["items"]),
        "score": score,
        "breakdown": breakdown,
        "explanation": explain(chosen, ctx, engine, use_feedback),
        "signature": signature(chosen["items"]),
        "engine": engine,
    }


ROLE_ORDER = {"outerwear": 0, "top": 1, "dress": 1, "bottom": 2, "footwear": 3, "accessory": 4}


def order_items(items):
    return sorted(items, key=lambda it: ROLE_ORDER[it["category"]])


# ---------------------------------------------------------------------------
# explanation
# ---------------------------------------------------------------------------

OCCASION_WORDS = {
    "casual": "a casual day", "college": "college", "work": "work", "formal": "a formal event",
    "party": "a party", "sports": "sport", "date": "a date", "travel": "travelling",
}

COLOUR_SENTENCES = {
    "neutral-contrast": "The colours are neutrals with clear light-dark contrast, which always reads deliberate.",
    "neutral-flat": "It's all quiet neutrals: easy to wear, if a little low-key.",
    "anchored": "Neutral pieces anchor the outfit so the colour has room to stand out.",
    "tonal": "The colours sit close together, so the look reads as one tonal idea.",
    "analogous": "The colours are neighbours on the colour wheel, which keeps things harmonious.",
    "complementary": "It pairs near-opposite colours for contrast; the rest is kept calm so it doesn't shout.",
    "clash": "Two of the colours compete a little. Swap one for a neutral if that bothers you.",
}


def _names(items, roles):
    picked = [it["name"] for it in items if it["category"] in roles]
    return " and ".join(picked) if picked else ""


def explain(cand, ctx, engine, used_feedback):
    items = cand["items"]
    r = cand["rules"]
    comp = cand["components"]
    parts = []

    # occasion
    occ = OCCASION_WORDS[ctx["occasion"]]
    if "all_tagged" in r["occasion"]["notes"]:
        parts.append(f"Every piece is one you've marked as right for {occ}.")
    elif r["occasion"]["score"] >= 0.7:
        parts.append(f"The formality level suits {occ}.")
    else:
        parts.append(f"This is the closest match for {occ} your wardrobe has right now; "
                     f"tagging more pieces for it will improve suggestions.")

    # weather
    temp = ctx["temperature_c"]
    wnotes = r["weather"]["notes"]
    outer = _names(items, ("outerwear",))
    if "rain_ready" in wnotes:
        parts.append(f"At {temp:g}°C and {ctx['weather']}, it's set up for the wet.")
    elif outer and _need_outer(ctx):
        parts.append(f"At {temp:g}°C the {outer} adds the warmth you'll need.")
    elif "warmth_right" in wnotes:
        parts.append(f"The layers suit {temp:g}°C.")
    elif "too_warm" in wnotes:
        parts.append(f"It may run warm for {temp:g}°C; your wardrobe has few lighter options here.")
    elif "too_cold" in wnotes:
        parts.append(f"It may feel cool at {temp:g}°C. Adding a warmer layer would help.")

    # colour
    kind = r["color"]["detail"]["weakest_pair"]["kind"] if r["color"]["detail"]["weakest_pair"] else None
    if kind in COLOUR_SENTENCES:
        parts.append(COLOUR_SENTENCES[kind])
    if "palette_match" in r["color"]["notes"]:
        parts.append(f"It fits the {ctx.get('palette')} palette you asked for.")

    # style
    if ctx.get("style") and "all_match_style" in r["style"]["notes"]:
        parts.append(f"Every piece is {ctx['style'].replace('_', ' ')}.")
    elif "coherent" in r["style"]["notes"]:
        parts.append("The pieces share a consistent style.")
    elif "mixed_styles" in r["style"]["notes"]:
        parts.append("It mixes styles more than usual.")

    # learned parts
    if engine == "hybrid" and "ml" in comp:
        pct = int(round(comp["ml"] * 100))
        parts.append(f"The taste models give it a {pct}% chance of being an outfit you'd like.")
    if used_feedback and "feedback" in comp:
        if comp["feedback"] >= 0.6:
            parts.append("It's close to outfits you've liked before.")
        elif comp["feedback"] <= 0.4:
            parts.append("It's a step away from what you usually like, which is worth a try.")
    if engine == "rules":
        parts.append("Scored on rules only, because the learned models aren't loaded.")
    return " ".join(parts)
