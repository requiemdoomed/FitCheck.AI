"""
The fixed vocabulary of FitCheck.AI: categories, styles, occasions, and what
each kind of garment implies about warmth and formality.

The frontend keeps a copy of these lists in assets/js/lib/catalog.js. A test
(tests/static/test_pages.py) fails if the two ever drift apart.

This module is plain Python on purpose: the notebook imports it too.
"""

CATEGORIES = ["top", "bottom", "dress", "outerwear", "footwear", "accessory"]

STYLES = ["minimalist", "streetwear", "classic", "smart_casual", "sporty", "elegant"]

OCCASIONS = ["casual", "college", "work", "formal", "party", "sports", "date", "travel"]

SEASONS = ["spring", "summer", "autumn", "winter"]

WEATHER = ["sunny", "cloudy", "rainy", "snowy", "windy"]

PALETTES = ["any", "neutral", "monochrome", "earthy", "bold", "pastel"]

# Garment attributes:
#   warmth    0 = barely there .. 3 = built for cold
#   formality 1 = gym/lounge .. 5 = black tie
#   tags      sporty, rain (fine in the wet), snow, sun, open (exposed feet)
SUBCATEGORIES = {
    "top": {
        "t-shirt":        {"warmth": 1, "formality": 1, "tags": []},
        "tank top":       {"warmth": 0, "formality": 1, "tags": []},
        "polo":           {"warmth": 1, "formality": 2, "tags": []},
        "shirt":          {"warmth": 1, "formality": 3, "tags": []},
        "dress shirt":    {"warmth": 1, "formality": 4, "tags": []},
        "blouse":         {"warmth": 1, "formality": 3, "tags": []},
        "sweater":        {"warmth": 2, "formality": 3, "tags": []},
        "turtleneck":     {"warmth": 2, "formality": 3, "tags": []},
        "hoodie":         {"warmth": 2, "formality": 1, "tags": []},
        "sweatshirt":     {"warmth": 2, "formality": 1, "tags": []},
        "athletic top":   {"warmth": 0, "formality": 1, "tags": ["sporty"]},
    },
    "bottom": {
        "jeans":          {"warmth": 1, "formality": 2, "tags": []},
        "chinos":         {"warmth": 1, "formality": 3, "tags": []},
        "trousers":       {"warmth": 1, "formality": 4, "tags": []},
        "cargo pants":    {"warmth": 1, "formality": 1, "tags": []},
        "shorts":         {"warmth": 0, "formality": 1, "tags": []},
        "skirt":          {"warmth": 0, "formality": 3, "tags": []},
        "joggers":        {"warmth": 1, "formality": 1, "tags": ["sporty"]},
        "leggings":       {"warmth": 1, "formality": 1, "tags": ["sporty"]},
        "athletic shorts": {"warmth": 0, "formality": 1, "tags": ["sporty"]},
    },
    "dress": {
        "casual dress":   {"warmth": 1, "formality": 2, "tags": []},
        "sundress":       {"warmth": 0, "formality": 2, "tags": []},
        "cocktail dress": {"warmth": 1, "formality": 4, "tags": []},
        "evening gown":   {"warmth": 1, "formality": 5, "tags": []},
        "jumpsuit":       {"warmth": 1, "formality": 3, "tags": []},
    },
    "outerwear": {
        "cardigan":       {"warmth": 1, "formality": 2, "tags": []},
        "denim jacket":   {"warmth": 1, "formality": 2, "tags": []},
        "bomber jacket":  {"warmth": 2, "formality": 2, "tags": []},
        "leather jacket": {"warmth": 2, "formality": 2, "tags": ["rain"]},
        "blazer":         {"warmth": 1, "formality": 4, "tags": []},
        "suit jacket":    {"warmth": 1, "formality": 5, "tags": []},
        "wool coat":      {"warmth": 3, "formality": 4, "tags": []},
        "trench coat":    {"warmth": 2, "formality": 4, "tags": ["rain"]},
        "raincoat":       {"warmth": 1, "formality": 2, "tags": ["rain"]},
        "windbreaker":    {"warmth": 1, "formality": 1, "tags": ["rain", "sporty"]},
        "puffer jacket":  {"warmth": 3, "formality": 1, "tags": ["snow"]},
        "parka":          {"warmth": 3, "formality": 2, "tags": ["rain", "snow"]},
    },
    "footwear": {
        "sneakers":       {"warmth": 1, "formality": 1, "tags": []},
        "running shoes":  {"warmth": 1, "formality": 1, "tags": ["sporty"]},
        "loafers":        {"warmth": 1, "formality": 4, "tags": []},
        "dress shoes":    {"warmth": 1, "formality": 5, "tags": []},
        "ankle boots":    {"warmth": 2, "formality": 3, "tags": ["rain"]},
        "heels":          {"warmth": 0, "formality": 5, "tags": []},
        "flats":          {"warmth": 1, "formality": 3, "tags": []},
        "sandals":        {"warmth": 0, "formality": 1, "tags": ["open", "sun"]},
        "rain boots":     {"warmth": 2, "formality": 1, "tags": ["rain"]},
        "snow boots":     {"warmth": 3, "formality": 1, "tags": ["rain", "snow"]},
    },
    "accessory": {
        "watch":          {"warmth": 0, "formality": 3, "tags": []},
        "belt":           {"warmth": 0, "formality": 3, "tags": []},
        "tie":            {"warmth": 0, "formality": 5, "tags": []},
        "jewellery":      {"warmth": 0, "formality": 3, "tags": []},
        "bag":            {"warmth": 0, "formality": 2, "tags": []},
        "cap":            {"warmth": 0, "formality": 1, "tags": ["sun", "sporty"]},
        "sunglasses":     {"warmth": 0, "formality": 2, "tags": ["sun"]},
        "scarf":          {"warmth": 2, "formality": 3, "tags": []},
        "beanie":         {"warmth": 2, "formality": 1, "tags": ["snow"]},
        "umbrella":       {"warmth": 0, "formality": 2, "tags": ["rain"]},
    },
}

# Reasonable defaults when someone types a subcategory we don't know.
CATEGORY_DEFAULTS = {
    "top":       {"warmth": 1, "formality": 2, "tags": []},
    "bottom":    {"warmth": 1, "formality": 2, "tags": []},
    "dress":     {"warmth": 1, "formality": 3, "tags": []},
    "outerwear": {"warmth": 2, "formality": 2, "tags": []},
    "footwear":  {"warmth": 1, "formality": 2, "tags": []},
    "accessory": {"warmth": 0, "formality": 2, "tags": []},
}

# What each occasion expects: an acceptable formality range, and whether
# sporty pieces are wanted (True), fine (None), or out of place (False).
OCCASION_RULES = {
    "casual":  {"formality": (1, 3), "sporty": None},
    "college": {"formality": (1, 3), "sporty": None},
    "work":    {"formality": (3, 4), "sporty": False},
    "formal":  {"formality": (4, 5), "sporty": False},
    "party":   {"formality": (2, 4), "sporty": False},
    "sports":  {"formality": (1, 1), "sporty": True},
    "date":    {"formality": (2, 4), "sporty": False},
    "travel":  {"formality": (1, 2), "sporty": None},
}

# How comfortably two styles sit in one outfit (symmetric, 0..1).
_STYLE_AFFINITY = {
    ("minimalist", "classic"): 0.85,
    ("minimalist", "smart_casual"): 0.8,
    ("minimalist", "elegant"): 0.75,
    ("minimalist", "streetwear"): 0.6,
    ("minimalist", "sporty"): 0.45,
    ("classic", "smart_casual"): 0.9,
    ("classic", "elegant"): 0.8,
    ("classic", "streetwear"): 0.35,
    ("classic", "sporty"): 0.25,
    ("smart_casual", "elegant"): 0.6,
    ("smart_casual", "streetwear"): 0.55,
    ("smart_casual", "sporty"): 0.35,
    ("streetwear", "sporty"): 0.8,
    ("streetwear", "elegant"): 0.2,
    ("sporty", "elegant"): 0.1,
}


def style_affinity(a, b):
    if a == b:
        return 1.0
    return _STYLE_AFFINITY.get((a, b)) or _STYLE_AFFINITY.get((b, a)) or 0.3


def attributes(category, subcategory):
    """Warmth/formality/tags for a garment, falling back to category defaults."""
    sub = (subcategory or "").strip().lower()
    return SUBCATEGORIES.get(category, {}).get(sub) or CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS["top"])


def season_for_temperature(temp_c):
    if temp_c >= 24:
        return "summer"
    if temp_c >= 14:
        return "spring"   # spring and autumn behave the same; both are accepted
    if temp_c >= 6:
        return "autumn"
    return "winter"


def options():
    """Everything the frontend needs to build its forms."""
    return {
        "categories": CATEGORIES,
        "subcategories": {cat: sorted(subs) for cat, subs in SUBCATEGORIES.items()},
        "styles": STYLES,
        "occasions": OCCASIONS,
        "seasons": SEASONS,
        "weather": WEATHER,
        "palettes": PALETTES,
    }
