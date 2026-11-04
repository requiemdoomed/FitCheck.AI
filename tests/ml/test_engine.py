"""
The Python reference engine (ml/fitcheck_ml): colour maths, rules, features
and the trained models. The browser engine is checked against this one in
tests/engine/test_parity.py, so these tests pin down both.
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

from fitcheck_ml import catalog, color, features, ml, recommender, rules  # noqa: E402


class Config:
    MODEL_DIR = ROOT / "ml" / "models"

# ---------------------------------------------------------------- colour

SHARMA = [
    ((50, 2.6772, -79.7751), (50, 0, -82.7485), 2.0425),
    ((50, 3.1571, -77.2803), (50, 0, -82.7485), 2.8615),
    ((50, -1.3802, -84.2814), (50, 0, -82.7485), 1.0000),
    ((50, 0, 0), (50, -1, 2), 2.3669),
    ((50, 2.49, -0.001), (50, -2.49, 0.0009), 7.1792),
    ((50, 2.5, 0), (73, 25, -18), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.694), (23.0331, 14.973, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.441), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.135), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_ciede2000_matches_reference(lab1, lab2, expected):
    assert color.delta_e_2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)
    assert color.delta_e_2000(lab2, lab1) == pytest.approx(expected, abs=1e-4)  # symmetric


def test_rgb_to_lab_known_values():
    assert color.hex_to_lab("#ffffff") == pytest.approx((100, 0, 0), abs=0.01)
    assert color.hex_to_lab("#000000") == pytest.approx((0, 0, 0), abs=0.01)
    assert color.hex_to_lab("#ff0000") == pytest.approx((53.24, 80.09, 67.20), abs=0.05)


def test_normalize_hex():
    assert color.normalize_hex("#ABC") == "#aabbcc"
    assert color.normalize_hex("1f2a4a") == "#1f2a4a"
    for bad in ("#12345", "blue", "", None, "#ggg000", "javascript:alert(1)"):
        assert color.normalize_hex(bad) is None


def test_nearest_name():
    assert color.nearest_name("#000000") == "black"
    assert color.nearest_name("#203060") == "navy"
    assert color.nearest_name("#c22a2a") == "red"


def test_pair_harmony_kinds():
    assert color.pair_harmony("#f5f5f2", "#1b1b1d")[1] == "neutral-contrast"
    assert color.pair_harmony("#f5f5f2", "#c42b2b")[1] == "anchored"
    assert color.pair_harmony("#c42b2b", "#2f7d4f")[1] in ("complementary", "clash")
    good = color.outfit_harmony(["#f5f5f2", "#1f2a4a", "#6b4428"])[0]
    loud = color.outfit_harmony(["#e2702f", "#c2357a", "#2f6fd0"])[0]
    assert good > loud


def test_palette_fit():
    neutral = ["#f5f5f2", "#1b1b1d", "#8a8d91"]
    bold = ["#c42b2b", "#f5f5f2", "#1b1b1d"]
    assert color.palette_fit(neutral, "neutral") == 1.0
    assert color.palette_fit(neutral, "bold") < color.palette_fit(bold, "bold")
    assert color.palette_fit(neutral, "any") == 1.0


# ---------------------------------------------------------------- rules

def item(i, category, sub, hex_, style="classic", occasions=("work",), seasons=("spring", "autumn", "winter")):
    return {"id": i, "name": f"{sub} {i}", "category": category, "subcategory": sub, "style": style,
            "main_color_hex": hex_, "main_color_name": color.nearest_name(hex_),
            "occasions": list(occasions), "seasons": list(seasons)}


CTX = {"occasion": "work", "weather": "cloudy", "temperature_c": 15, "style": None, "palette": "any",
       "favorite_colors": [], "avoided_colors": [], "preferred_styles": []}


def test_sandals_lose_in_the_rain():
    base = [item(1, "top", "shirt", "#f5f5f2"), item(2, "bottom", "chinos", "#1f2a4a")]
    ctx = dict(CTX, weather="rainy", temperature_c=14)
    sandals = rules.score_weather(base + [item(3, "footwear", "sandals", "#6b4428", seasons=("summer",))], ctx)[0]
    boots = rules.score_weather(base + [item(4, "footwear", "ankle boots", "#6b4428")], ctx)[0]
    assert boots > sandals


def test_cold_needs_a_layer():
    base = [item(1, "top", "shirt", "#f5f5f2"), item(2, "bottom", "chinos", "#1f2a4a"),
            item(3, "footwear", "ankle boots", "#1b1b1d")]
    ctx = dict(CTX, temperature_c=0, weather="snowy")
    without = rules.score_weather(base, ctx)
    with_coat = rules.score_weather(base + [item(4, "outerwear", "parka", "#1f2a4a")], ctx)
    assert with_coat[0] > without[0]
    assert "no_coat_in_snow" in without[1]


def test_occasion_formality():
    formal = [item(1, "top", "dress shirt", "#f5f5f2", occasions=("formal",)),
              item(2, "bottom", "trousers", "#1b1b1d", occasions=("formal",)),
              item(3, "footwear", "dress shoes", "#1b1b1d", occasions=("formal",))]
    gym = [item(4, "top", "athletic top", "#2f6fd0", style="sporty", occasions=("sports",)),
           item(5, "bottom", "joggers", "#1b1b1d", style="sporty", occasions=("sports",)),
           item(6, "footwear", "running shoes", "#2f6fd0", style="sporty", occasions=("sports",))]
    f_ctx = dict(CTX, occasion="formal")
    s_ctx = dict(CTX, occasion="sports")
    assert rules.score_occasion(formal, f_ctx)[0] > rules.score_occasion(gym, f_ctx)[0]
    assert rules.score_occasion(gym, s_ctx)[0] > rules.score_occasion(formal, s_ctx)[0]


def test_avoided_colour_penalised():
    outfit = [item(1, "top", "shirt", "#c42b2b"), item(2, "bottom", "chinos", "#1f2a4a"),
              item(3, "footwear", "loafers", "#6b4428")]
    plain = rules.score_color(outfit, CTX)[0]
    avoid = rules.score_color(outfit, dict(CTX, avoided_colors=["red"]))[0]
    assert avoid < plain


def test_unknown_subcategory_uses_category_defaults():
    assert catalog.attributes("top", "kimono") == catalog.CATEGORY_DEFAULTS["top"]


def test_recommender_never_invents_items():
    wardrobe = [item(1, "top", "shirt", "#f5f5f2"), item(2, "top", "t-shirt", "#8a8d91", occasions=("casual",)),
                item(3, "bottom", "chinos", "#1f2a4a"), item(4, "bottom", "jeans", "#3c5a8a", occasions=("casual",)),
                item(5, "footwear", "loafers", "#6b4428"), item(6, "dress", "casual dress", "#6e2238"),
                item(7, "outerwear", "trench coat", "#b8a77a"), item(8, "accessory", "watch", "#6b4428")]
    ids = {i["id"] for i in wardrobe}
    for occ in catalog.OCCASIONS:
        for w in catalog.WEATHER:
            res = recommender.recommend(wardrobe, dict(CTX, occasion=occ, weather=w, temperature_c=10))
            assert {i["id"] for i in res["items"]} <= ids
            assert 0 <= res["score"] <= 100
            cats = [i["category"] for i in res["items"]]
            assert cats.count("footwear") == 1
            assert ("dress" in cats) != ({"top", "bottom"} <= set(cats))


def test_missing_roles():
    assert recommender.missing_roles([]) == ["footwear", "top", "bottom"]
    assert recommender.missing_roles([item(1, "dress", "sundress", "#e88aa8"),
                                      item(2, "footwear", "flats", "#1b1b1d")]) == []


# ---------------------------------------------------------------- ML

def test_models_load_and_match_feature_list():
    ml.reset_bundle()
    bundle = ml.get_bundle(Config.MODEL_DIR)
    assert bundle.available, bundle.reason
    meta = json.loads((Config.MODEL_DIR / "model_metadata.json").read_text())
    assert meta["feature_names"] == features.feature_names()
    for name in ("decision_tree_model.joblib", "knn_model.joblib", "scaler.joblib", "encoders.joblib"):
        assert (Config.MODEL_DIR / name).exists()


def test_model_predictions_are_probabilities():
    bundle = ml.get_bundle(Config.MODEL_DIR)
    outfit = [item(1, "top", "shirt", "#f5f5f2"), item(2, "bottom", "chinos", "#1f2a4a"),
              item(3, "footwear", "loafers", "#6b4428")]
    rows = [features.build_features(outfit, dict(CTX, occasion=o)) for o in catalog.OCCASIONS]
    blended, dt, knn = bundle.predict(rows)
    for arr in (blended, dt, knn):
        assert arr.shape == (len(rows),)
        assert np.all((arr >= 0) & (arr <= 1))


def test_bundle_unavailable_when_files_missing(tmp_path):
    shutil.copy(Config.MODEL_DIR / "model_metadata.json", tmp_path)
    bundle = ml.ModelBundle(tmp_path).load()
    assert bundle.available is False
    assert "not found" in bundle.reason


def test_bundle_unavailable_when_features_changed(tmp_path):
    for f in Config.MODEL_DIR.iterdir():
        if f.is_file():
            shutil.copy(f, tmp_path)
    meta = json.loads((tmp_path / "model_metadata.json").read_text())
    meta["feature_names"] = meta["feature_names"][:-1]
    (tmp_path / "model_metadata.json").write_text(json.dumps(meta))
    bundle = ml.ModelBundle(tmp_path).load()
    assert bundle.available is False
    assert "feature list" in bundle.reason


def test_personal_similarity():
    base = [item(1, "top", "shirt", "#f5f5f2"), item(2, "bottom", "chinos", "#1f2a4a"),
            item(3, "footwear", "loafers", "#6b4428")]
    loud = [item(4, "top", "t-shirt", "#e2702f", style="streetwear"),
            item(5, "bottom", "shorts", "#c2357a", style="streetwear"),
            item(6, "footwear", "sandals", "#2f6fd0", style="streetwear")]
    liked = features.build_features(base, CTX)
    disliked = features.build_features(loud, CTX)
    history = [(liked, "like")] * 3 + [(disliked, "dislike")] * 3
    bundle = ml.get_bundle(Config.MODEL_DIR)
    sims = ml.personal_similarity([liked, disliked], history, bundle)
    assert sims[0] > 0.5 > sims[1]
    assert ml.personal_similarity([liked], history[:2], bundle) is None   # too little feedback
    # also works without exported models
    sims_plain = ml.personal_similarity([liked, disliked], history, None)
    assert sims_plain[0] > sims_plain[1]



def test_scarf_is_not_used_to_warm_up_a_light_outfit_on_a_warm_day():
    """Regression: a scarf used to count as warmth at 20°C and got added to sports outfits."""
    wardrobe = [item(1, "top", "athletic top", "#2f6fd0", style="sporty", occasions=("sports",)),
                item(2, "bottom", "joggers", "#1b1b1d", style="sporty", occasions=("sports",)),
                item(3, "footwear", "running shoes", "#2f6fd0", style="sporty", occasions=("sports",)),
                item(4, "accessory", "scarf", "#8a8d91", style="minimalist", occasions=("casual",),
                     seasons=("autumn", "winter"))]
    warm = recommender.recommend(wardrobe, dict(CTX, occasion="sports", weather="sunny", temperature_c=20))
    assert "scarf" not in [i["subcategory"] for i in warm["items"]]
    assert rules.outfit_warmth(wardrobe, 20) == rules.outfit_warmth(wardrobe[:3], 20)
    assert rules.outfit_warmth(wardrobe, 2) == rules.outfit_warmth(wardrobe[:3], 2) + 2



# ---------------------------------------------------------------- stock pictures and cut-outs
