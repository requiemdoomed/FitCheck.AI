"""
Turns an outfit + its context into the feature vector the ML models use.

This file is shared by the training notebook and the live API, so training
and prediction can never disagree about what a feature means. If you change
the feature list, retrain (re-run the notebook); the API checks the list
against model_metadata.json and falls back to rules-only if they differ.
"""

from itertools import combinations

import numpy as np

from . import catalog, rules
from .color import chroma, delta_e, hex_to_lab, is_bold, is_earthy, is_neutral, is_pastel

NUMERIC_FEATURES = [
    "temperature_c",
    "total_warmth",
    "warmth_gap",
    "mean_formality",
    "formality_spread",
    "n_items",
    "has_outerwear",
    "n_accessories",
    "is_dress",
    "n_neutral",
    "n_bold",
    "n_pastel",
    "n_earthy",
    "mean_lightness",
    "lightness_range",
    "mean_chroma",
    "max_delta_e",
    "occasion_tag_frac",
    "style_coherence",
    "style_match",
    "sporty_frac",
    "season_fit",
    "rain_ready",
    "rule_occasion",
    "rule_weather",
    "rule_style",
    "rule_color",
]

CATEGORICAL_FEATURES = {
    "occasion": catalog.OCCASIONS,
    "weather": catalog.WEATHER,
    "style_pref": ["none"] + catalog.STYLES,
    "palette": catalog.PALETTES,
}


def feature_names():
    names = list(NUMERIC_FEATURES)
    for field, cats in CATEGORICAL_FEATURES.items():
        names += [f"{field}={c}" for c in cats]
    return names


def build_features(items, ctx, rule_result=None):
    """Raw feature dict for one outfit. `rule_result` avoids rescoring if given."""
    if rule_result is None:
        rule_result = rules.score_rules(items, ctx)

    wearable = [it for it in items if it["category"] != "accessory"]
    core = [it for it in items if it["category"] in rules.CORE_ROLES]
    hexes = [it["main_color_hex"] for it in wearable]
    labs = [hex_to_lab(h) for h in hexes]
    formality = [rules.attrs(it)["formality"] for it in core] or [0]

    warmth = rules.outfit_warmth(items, ctx["temperature_c"])
    pairs = list(combinations(hexes, 2))
    occasion = ctx["occasion"]

    shoes = [it for it in items if it["category"] == "footwear"]
    outer = [it for it in items if it["category"] == "outerwear"]
    rain_tags = set()
    for it in shoes + outer:
        rain_tags |= set(rules.attrs(it)["tags"])

    style_detail = rule_result["style"]["detail"]
    match = style_detail.get("match")

    return {
        "temperature_c": float(ctx["temperature_c"]),
        "total_warmth": warmth,
        "warmth_gap": warmth - rules.target_warmth(ctx["temperature_c"]),
        "mean_formality": float(np.mean(formality)),
        "formality_spread": max(formality) - min(formality),
        "n_items": len(items),
        "has_outerwear": int(bool(outer)),
        "n_accessories": sum(1 for it in items if it["category"] == "accessory"),
        "is_dress": int(any(it["category"] == "dress" for it in items)),
        "n_neutral": sum(is_neutral(h) for h in hexes),
        "n_bold": sum(is_bold(h) for h in hexes),
        "n_pastel": sum(is_pastel(h) for h in hexes),
        "n_earthy": sum(is_earthy(h) for h in hexes),
        "mean_lightness": float(np.mean([lab[0] for lab in labs])) if labs else 50.0,
        "lightness_range": (max(l[0] for l in labs) - min(l[0] for l in labs)) if labs else 0.0,
        "mean_chroma": float(np.mean([chroma(l) for l in labs])) if labs else 0.0,
        "max_delta_e": max((delta_e(a, b) for a, b in pairs), default=0.0),
        "occasion_tag_frac": sum(occasion in (it.get("occasions") or []) for it in wearable) / max(1, len(wearable)),
        "style_coherence": style_detail["coherence"],
        "style_match": match if match is not None else 0.75,
        "sporty_frac": sum(rules.is_sporty(it) for it in wearable) / max(1, len(wearable)),
        "season_fit": rule_result["weather"]["detail"]["season_fit"],
        "rain_ready": int(bool({"rain", "snow"} & rain_tags)),
        "rule_occasion": rule_result["occasion"]["score"],
        "rule_weather": rule_result["weather"]["score"],
        "rule_style": rule_result["style"]["score"],
        "rule_color": rule_result["color"]["score"],
        # categorical
        "occasion": occasion,
        "weather": ctx["weather"],
        "style_pref": ctx.get("style") or "none",
        "palette": ctx.get("palette") or "any",
    }


def to_matrix(rows, encoders):
    """
    rows: list of raw feature dicts. encoders: {field: fitted OneHotEncoder}.
    Returns a float matrix with columns in feature_names() order.
    """
    numeric = np.array([[float(r[f]) for f in NUMERIC_FEATURES] for r in rows], dtype=float)
    parts = [numeric]
    for field in CATEGORICAL_FEATURES:
        col = np.array([[r[field]] for r in rows], dtype=object)
        enc = encoders[field].transform(col)
        parts.append(enc.toarray() if hasattr(enc, "toarray") else np.asarray(enc))
    return np.hstack(parts)


def make_encoders():
    """Fit one-hot encoders on the fixed vocabularies (not on data)."""
    from sklearn.preprocessing import OneHotEncoder
    encoders = {}
    for field, cats in CATEGORICAL_FEATURES.items():
        enc = OneHotEncoder(categories=[cats], handle_unknown="ignore", sparse_output=False)
        enc.fit(np.array([[c] for c in cats], dtype=object))
        encoders[field] = enc
    return encoders
