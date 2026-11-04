// The app's fixed vocabulary, mirrored from ml/fitcheck_ml/catalog.py and
// ml/fitcheck_ml/color.py. tests/static/test_pages.py fails if
// the two copies drift apart, so edit both together.

export const CATALOG = /* catalog-json-start */ {
  "categories": ["top", "bottom", "dress", "outerwear", "footwear", "accessory"],
  "subcategories": {
    "top": ["athletic top", "blouse", "dress shirt", "hoodie", "polo", "shirt", "sweater", "sweatshirt", "t-shirt", "tank top", "turtleneck"],
    "bottom": ["athletic shorts", "cargo pants", "chinos", "jeans", "joggers", "leggings", "shorts", "skirt", "trousers"],
    "dress": ["casual dress", "cocktail dress", "evening gown", "jumpsuit", "sundress"],
    "outerwear": ["blazer", "bomber jacket", "cardigan", "denim jacket", "leather jacket", "parka", "puffer jacket", "raincoat", "suit jacket", "trench coat", "windbreaker", "wool coat"],
    "footwear": ["ankle boots", "dress shoes", "flats", "heels", "loafers", "rain boots", "running shoes", "sandals", "sneakers", "snow boots"],
    "accessory": ["bag", "beanie", "belt", "cap", "jewellery", "scarf", "sunglasses", "tie", "umbrella", "watch"]
  },
  "styles": ["minimalist", "streetwear", "classic", "smart_casual", "sporty", "elegant"],
  "occasions": ["casual", "college", "work", "formal", "party", "sports", "date", "travel"],
  "seasons": ["spring", "summer", "autumn", "winter"],
  "weather": ["sunny", "cloudy", "rainy", "snowy", "windy"],
  "palettes": ["any", "neutral", "monochrome", "earthy", "bold", "pastel"],
  "colors": {
    "black": "#1b1b1d", "charcoal": "#3a3d42", "grey": "#8a8d91", "light grey": "#c8cacc",
    "white": "#f5f5f2", "cream": "#efe6d2", "beige": "#d8c3a0", "khaki": "#b8a77a",
    "camel": "#b8864b", "brown": "#6b4428", "navy": "#1f2a4a", "denim": "#3c5a8a",
    "blue": "#2f6fd0", "light blue": "#a9c4e4", "teal": "#1f7a7a", "green": "#2f7d4f",
    "olive": "#6b7340", "mint": "#a8dcc0", "yellow": "#f0c419", "mustard": "#c99a2e",
    "orange": "#e2702f", "coral": "#f07a6a", "red": "#c42b2b", "burgundy": "#6e2238",
    "pink": "#e88aa8", "magenta": "#c2357a", "lavender": "#b9a7da", "purple": "#5e3a8a"
  }
} /* catalog-json-end */;

const LABELS = {
  smart_casual: "Smart casual",
  top: "Tops",
  bottom: "Bottoms",
  dress: "Dresses",
  outerwear: "Outerwear",
  footwear: "Shoes",
  accessory: "Accessories",
};

const SINGULAR = {
  top: "Top", bottom: "Bottom", dress: "Dress", outerwear: "Outerwear",
  footwear: "Shoes", accessory: "Accessory",
};

export function label(value) {
  if (!value) return "";
  if (LABELS[value]) return LABELS[value];
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
}

export function categoryLabel(value, plural = false) {
  return plural ? LABELS[value] || label(value) : SINGULAR[value] || label(value);
}

export const PALETTE_SWATCHES = {
  any: [],
  neutral: ["#1b1b1d", "#8a8d91", "#f5f5f2", "#1f2a4a"],
  monochrome: ["#1f2a4a", "#3c5a8a", "#a9c4e4", "#2f6fd0"],
  earthy: ["#6b4428", "#b8864b", "#6b7340", "#d8c3a0"],
  bold: ["#c42b2b", "#2f6fd0", "#f0c419", "#c2357a"],
  pastel: ["#a8dcc0", "#b9a7da", "#e88aa8", "#a9c4e4"],
};

export const WEATHER_LABELS = {
  sunny: "Sunny", cloudy: "Cloudy", rainy: "Rain", snowy: "Snow", windy: "Windy",
};

// Line icons, drawn on a 24px grid
export const WEATHER_ICONS = {
  sunny: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8"/>',
  cloudy: '<path d="M7 18h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 18Z"/>',
  rainy: '<path d="M7 14h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 14Z"/><path d="m9 17-1 3m5-3-1 3m5-3-1 3"/>',
  snowy: '<path d="M7 14h10a4 4 0 0 0 .5-8 6 6 0 0 0-11.4 1.5A3.3 3.3 0 0 0 7 14Z"/><path d="M8 18h.01M12 18h.01M16 18h.01M10 21h.01M14 21h.01" stroke-width="2.6"/>',
  windy: '<path d="M3 9h11a3 3 0 1 0-3-3M3 13h15a3 3 0 1 1-3 3M3 17h7"/>',
};

export function icon(paths, size = 22) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor"
    stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
}

export const toF = (c) => Math.round((c * 9) / 5 + 32);
export const toC = (f) => Math.round((((f - 32) * 5) / 9) * 10) / 10;

export function formatTemp(celsius, unit = "C") {
  return unit === "F" ? `${toF(celsius)}°F` : `${Math.round(celsius)}°C`;
}
