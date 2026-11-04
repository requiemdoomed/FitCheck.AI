"""
Shared data helpers: images, preferences, and the JSON shapes the pages use.
Swayam Shakya
"""

import io
import secrets
import sys

from flask import current_app
from PIL import Image, ImageOps

import db
from config import ROOT
from errors import ApiError, bad, not_found
from security import iso, now

sys.path.insert(0, str(ROOT / "ml"))
from fitcheck_ml import catalog, color  # noqa: E402

PREF_DEFAULTS = {
    "preferred_styles": [], "preferred_palette": "any", "favorite_colors": [], "avoided_colors": [],
    "default_occasion": None, "temperature_unit": "C", "budget": "budget",
    "model_build": "masc", "model_skin": "medium", "model_body": "average", "photo_setting": "studio",
}
MAX_SHOTS = 4

# ---------------------------------------------------------------- images

Image.MAX_IMAGE_PIXELS = 40_000_000           # refuse decompression bombs


def _open(data):
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError
        img.load()
        return img
    except Exception:
        raise ApiError(400, "invalid_image", "That file isn't a JPG, PNG or WebP image we can read.", {"image": "Use a JPG, PNG or WebP photo."})


def clean_photo(data, keep_alpha=False, max_side=900):
    """Decode, fix rotation, shrink, and re-encode (which drops EXIF/GPS and anything appended)."""
    if len(data) > current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024:
        raise ApiError(413, "file_too_large", "Images must be 15 MB or smaller.", {"image": "Images must be 15 MB or smaller."})
    img = ImageOps.exif_transpose(_open(data))
    if min(img.size) < 32:
        raise bad("That image is too small.", {"image": "Use a photo at least 32 pixels on each side."})
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    if keep_alpha and img.mode in ("RGBA", "LA", "P"):
        img.convert("RGBA").save(buf, "WEBP", quality=85, method=4)
    else:
        img.convert("RGB").save(buf, "WEBP", quality=85, method=4)
    return buf.getvalue(), "image/webp"


def save_image(user_id, data, mime, cache_key=None):
    key = secrets.token_hex(16)
    db.run("INSERT INTO images (ikey, user_id, mime, data, cache_key, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
           (key, user_id, mime, data, cache_key, now()))
    return key


def delete_images(keys):
    keys = [k for k in set(keys) if k]
    for k in keys:
        db.run("DELETE FROM images WHERE ikey = %s", (k,))


def image_url(key):
    return f"api/images/{key}" if key else None


# ---------------------------------------------------------------- preferences

def prefs(user_id):
    row = db.one("SELECT data FROM preferences WHERE user_id = %s", (user_id,))
    return {**PREF_DEFAULTS, **((row or {}).get("data") or {})}


# ---------------------------------------------------------------- JSON shapes

def public_user(u):
    return {"id": u["id"], "email": u["email"], "display_name": u["display_name"], "created_at": iso(u["created_at"])}


def item_json(it, role=None):
    out = {
        "id": it["id"], "name": it["name"], "category": it["category"], "subcategory": it["subcategory"],
        "main_color": {"hex": it["main_color_hex"], "name": it["main_color_name"]},
        "secondary_color": {"hex": it["secondary_color_hex"], "name": it["secondary_color_name"]} if it["secondary_color_hex"] else None,
        "pattern": it.get("pattern") or "",
        "seasons": it["seasons"], "style": it["style"], "occasions": it["occasions"],
        "image_url": image_url(it["image_key"]), "image_source": it["image_source"],
        "cutout_url": image_url(it["cutout_key"]), "description": it["description"] or "",
        "archived": bool(it["deleted_at"]), "created_at": iso(it["created_at"]), "updated_at": iso(it["updated_at"]),
    }
    if role:
        out["role"] = role
    return out


def active_items(user_id):
    return db.all_("SELECT * FROM items WHERE user_id = %s AND deleted_at IS NULL", (user_id,))


def own_outfit(user_id, outfit_id):
    try:
        oid = int(outfit_id)
    except (TypeError, ValueError):
        raise not_found("That outfit")
    o = db.one("SELECT * FROM outfits WHERE id = %s AND user_id = %s", (oid, user_id))
    if not o:
        raise not_found("That outfit")
    return o


def outfit_items(outfit_id):
    return db.all_("SELECT i.*, oi.role AS role FROM outfit_items oi JOIN items i ON i.id = oi.item_id "
                   "WHERE oi.outfit_id = %s ORDER BY oi.position", (outfit_id,))


def photos_of(outfit_id):
    return db.all_("SELECT id, image_key, model FROM outfit_photos WHERE outfit_id = %s ORDER BY created_at, id", (outfit_id,))


def photos_json(o, shots=None):
    shots = shots if shots is not None else photos_of(o["id"])
    cover = o["photo_cover"] if o["photo_cover"] is not None and o["photo_cover"] < len(shots) else len(shots) - 1
    return {
        "photo_url": image_url(shots[cover]["image_key"]) if shots else None,
        "photo_model": shots[cover]["model"] if shots else None,
        "photos": [{"index": i, "url": image_url(s["image_key"]), "model": s["model"], "cover": i == cover} for i, s in enumerate(shots)],
    }


def outfit_json(o, breakdown=True):
    fb = db.one("SELECT verdict FROM feedback WHERE outfit_id = %s", (o["id"],))
    saved = db.one("SELECT id, name FROM saved_outfits WHERE outfit_id = %s", (o["id"],))
    out = {
        "id": o["id"], "occasion": o["occasion"], "weather": o["weather"], "temperature_c": float(o["temperature_c"]),
        "style": o["style_pref"], "palette": o["palette_pref"], "score": o["score"], "explanation": o["explanation"],
        "engine": o["engine"], "created_at": iso(o["created_at"]), "signature": o["signature"],
        "items": [item_json(it, it["role"]) for it in outfit_items(o["id"])],
        "feedback": fb["verdict"] if fb else None, "saved": bool(saved),
        "saved_id": saved["id"] if saved else None, "saved_name": saved["name"] if saved else None,
        "worn_at": iso(o["worn_at"]), **photos_json(o),
    }
    if breakdown:
        b = o["breakdown"] or {}
        out["breakdown"] = {"weights": b.get("weights"), "components": b.get("components"), "ml": b.get("ml"),
                            "feedback_used": b.get("feedback_used"),
                            "warmth": ((b.get("rules") or {}).get("weather") or {}).get("detail"),
                            "colour": ((b.get("rules") or {}).get("color") or {}).get("detail")}
    return out


def nearest_name(hex_):
    return color.nearest_name(hex_)


CATALOG = catalog
