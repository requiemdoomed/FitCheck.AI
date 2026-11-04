"""Profile, preferences, password, backup, account deletion, demo wardrobe."""

import base64
import json
from datetime import datetime

from flask import Blueprint, current_app, g, request

import db
import security as sec
import store
from config import ROOT
from errors import ApiError, bad
from validation import V

bp = Blueprint("profile", __name__)
C = store.CATALOG
COLOURS = list(store.color.NAMED_COLORS)


def _profile(uid):
    user = db.one("SELECT * FROM users WHERE id = %s", (uid,))
    return {"user": store.public_user(user), "preferences": store.prefs(uid),
            "stats": {"items": db.one("SELECT COUNT(*) AS n FROM items WHERE user_id = %s AND deleted_at IS NULL", (uid,))["n"],
                      "outfits": db.one("SELECT COUNT(*) AS n FROM outfits WHERE user_id = %s", (uid,))["n"]}}


def _clean_prefs(uid, incoming):
    merged = {**store.prefs(uid), **(incoming if isinstance(incoming, dict) else {})}
    pv = (V(merged).multi("preferred_styles", C.STYLES, required=False)
          .choice("preferred_palette", C.PALETTES, required=False, default="any")
          .multi("favorite_colors", COLOURS, required=False, max=8, label="Favourite colours")
          .multi("avoided_colors", COLOURS, required=False, max=8, label="Avoided colours")
          .choice("default_occasion", C.OCCASIONS, required=False)
          .choice("temperature_unit", ["C", "F"], required=False, default="C")
          .choice("budget", ["budget", "mid"], required=False, default="budget")
          .choice("model_build", ["masc", "fem"], required=False, default="masc")
          .choice("model_skin", ["light", "medium", "tan", "deep"], required=False, default="medium")
          .choice("model_body", ["slim", "average", "athletic", "curvy", "plus"], required=False, default="average")
          .choice("photo_setting", ["studio", "occasion"], required=False, default="studio"))
    if set(pv.clean.get("favorite_colors") or []) & set(pv.clean.get("avoided_colors") or []) and "avoided_colors" not in pv.errors:
        pv.errors["avoided_colors"] = "A colour can't be both a favourite and avoided."
    return pv


@bp.get("/api/profile")
@sec.login_required
def get_profile():
    return _profile(g.user["id"])


@bp.put("/api/profile")
@sec.login_required
def update_profile():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise bad("Send the profile as an object.")
    uid = g.user["id"]
    v = V(data)
    if "display_name" in data:
        v.text("display_name", max=60, label="Name")
    new_prefs = None
    if data.get("preferences") is not None:
        pv = _clean_prefs(uid, data["preferences"])
        for k, msg in pv.errors.items():
            v.errors[f"preferences.{k}"] = msg
        new_prefs = pv.clean
    wants_pw = bool(data.get("new_password"))
    if wants_pw:
        problem = sec.password_problem(data["new_password"], g.user["email"])
        if problem:
            v.errors["new_password"] = problem
        if not sec.check_password(data.get("current_password"), g.user["password_hash"]):
            v.errors["current_password"] = "Your current password isn't right."
    clean = v.done()
    if "display_name" in clean:
        db.run("UPDATE users SET display_name = %s WHERE id = %s", (clean["display_name"], uid))
    if wants_pw:
        db.run("UPDATE users SET password_hash = %s WHERE id = %s", (sec.hash_password(data["new_password"]), uid))
        sec.end_all_sessions(uid, except_id=g.session_row["id"])
    if new_prefs is not None:
        db.run("INSERT INTO preferences (user_id, data) VALUES (%s, %s) ON DUPLICATE KEY UPDATE data = VALUES(data)",
               (uid, db.as_json(new_prefs)))
    return _profile(uid)


def _need_password(what):
    pw = (request.get_json(silent=True) or {}).get("password")
    if not sec.check_password(pw, g.user["password_hash"]):
        raise bad(f"Enter your password to {what}.", {"password": "Password isn't right."})


@bp.delete("/api/profile")
@sec.login_required
def delete_account():
    _need_password("delete your account")
    db.run("DELETE FROM users WHERE id = %s", (g.user["id"],))     # cascades to everything
    g.clear_cookies = True
    return "", 204


# ---------------------------------------------------------------- backup

def _b64(data, mime):
    return f"data:{mime};base64,{base64.b64encode(bytes(data)).decode()}"


@bp.post("/api/profile/export")
@sec.login_required
def export_data():
    _need_password("download a backup")
    uid = g.user["id"]
    items = db.all_("SELECT * FROM items WHERE user_id = %s", (uid,))
    outfits = db.all_("SELECT * FROM outfits WHERE user_id = %s", (uid,))
    keys = {k for it in items for k in (it["image_key"], it["cutout_key"]) if k}
    out_outfits = []
    for o in outfits:
        shots = store.photos_of(o["id"])
        keys |= {s["image_key"] for s in shots}
        out_outfits.append({
            "id": o["id"], "occasion": o["occasion"], "weather": o["weather"], "temperature_c": float(o["temperature_c"]),
            "style_pref": o["style_pref"], "palette_pref": o["palette_pref"], "score": o["score"],
            "breakdown": o["breakdown"], "explanation": o["explanation"], "engine": o["engine"],
            "created_at": sec.iso(o["created_at"]), "worn_at": sec.iso(o["worn_at"]), "photo_cover": o["photo_cover"],
            "items": [{"id": r["item_id"], "role": r["role"]} for r in
                      db.all_("SELECT item_id, role FROM outfit_items WHERE outfit_id = %s ORDER BY position", (o["id"],))],
            "photos": [{"key": s["image_key"], "model": s["model"]} for s in shots],
        })
    images = {}
    for k in keys:
        row = db.one("SELECT mime, data FROM images WHERE ikey = %s AND user_id = %s", (k, uid))
        if row:
            images[k] = _b64(row["data"], row["mime"])
    return {
        "format": "fitcheck-backup", "version": 2, "exported_at": sec.iso(sec.now()),
        "user": {"email": g.user["email"], "display_name": g.user["display_name"]},
        "preferences": store.prefs(uid),
        "items": [{**{k: it[k] for k in ("id", "name", "category", "subcategory", "main_color_hex", "secondary_color_hex",
                                          "pattern", "seasons", "style", "occasions", "description", "image_key",
                                          "cutout_key", "image_source")},
                   "created_at": sec.iso(it["created_at"]), "deleted_at": sec.iso(it["deleted_at"])} for it in items],
        "outfits": out_outfits,
        "feedback": [{"outfit_id": f["outfit_id"], "verdict": f["verdict"]} for f in
                     db.all_("SELECT outfit_id, verdict FROM feedback WHERE user_id = %s", (uid,))],
        "saved": [{"outfit_id": s["outfit_id"], "name": s["name"]} for s in
                  db.all_("SELECT outfit_id, name FROM saved_outfits WHERE user_id = %s", (uid,))],
        "images": images,
    }


def _date(v):
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S")
    except (TypeError, ValueError):
        return sec.now()


@bp.post("/api/profile/import")
@sec.login_required
def import_data():
    """A backup is untrusted input: sizes first, every item validated before anything is replaced."""
    from api_wardrobe import _fields          # same rules as adding a piece by hand
    backup = request.get_json(silent=True)
    if not isinstance(backup, dict) or backup.get("format") != "fitcheck-backup" or not isinstance(backup.get("items"), list):
        raise bad("That file isn't a FitCheck.AI backup.")
    items_in = backup["items"]
    outfits_in = backup.get("outfits") if isinstance(backup.get("outfits"), list) else []
    images_in = backup.get("images") if isinstance(backup.get("images"), dict) else {}
    if len(items_in) > current_app.config["MAX_ITEMS"] or len(outfits_in) > 5000 or len(images_in) > 25000:
        raise bad("That backup is larger than FitCheck.AI accepts.")
    cleaned = []
    for it in items_in:
        if not isinstance(it, dict):
            raise bad("That backup has a damaged item.")
        cleaned.append((it, _fields({"name": it.get("name"), "category": it.get("category"), "subcategory": it.get("subcategory"),
                                     "style": it.get("style"), "seasons": it.get("seasons"), "occasions": it.get("occasions"),
                                     "description": it.get("description") or "", "main_color": it.get("main_color_hex"),
                                     "secondary_color": it.get("secondary_color_hex") or "",
                                     **({"pattern": it["pattern"]} if it.get("pattern") else {})})))
    uid = g.user["id"]
    # replace this account's wardrobe and history
    db.run("DELETE FROM outfits WHERE user_id = %s", (uid,))
    db.run("DELETE FROM items WHERE user_id = %s", (uid,))
    db.run("DELETE FROM images WHERE user_id = %s", (uid,))
    key_map = {}
    for old, url in images_in.items():
        if not isinstance(url, str) or len(url) > 22_000_000 or not url.startswith(("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")):
            continue
        try:
            raw = base64.b64decode(url.split(",", 1)[1], validate=True)
            data, mime = store.clean_photo(raw, keep_alpha=True, max_side=1400)
        except Exception:
            continue
        key_map[old] = store.save_image(uid, data, mime)
    id_map = {}
    for it, c in cleaned:
        iid = db.run("INSERT INTO items (user_id, name, category, subcategory, main_color_hex, main_color_name, "
                     "secondary_color_hex, secondary_color_name, pattern, seasons, style, occasions, description, image_key, "
                     "cutout_key, image_source, created_at, updated_at, deleted_at) VALUES "
                     "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (uid, c["name"], c["category"], c["subcategory"], c["main_color_hex"], c["main_color_name"],
                      c.get("secondary_color_hex"), c.get("secondary_color_name"), c.get("pattern") or "",
                      db.as_json(c["seasons"]), c["style"], db.as_json(c["occasions"]), c.get("description") or "",
                      key_map.get(it.get("image_key")), key_map.get(it.get("cutout_key")),
                      it.get("image_source") if it.get("image_source") in ("upload", "stock") else None,
                      _date(it.get("created_at")), sec.now(), _date(it["deleted_at"]) if it.get("deleted_at") else None))
        id_map[it.get("id")] = iid
    outfit_map = {}
    for o in outfits_in:
        if not isinstance(o, dict) or o.get("occasion") not in C.OCCASIONS or o.get("weather") not in C.WEATHER:
            continue
        refs = [r for r in (o.get("items") or []) if isinstance(r, dict) and r.get("id") in id_map]
        if not refs:
            continue
        try:
            temp = max(-40.0, min(50.0, float(o.get("temperature_c"))))
            score = max(0, min(100, int(o.get("score") or 0)))
        except (TypeError, ValueError):
            continue
        bd = o.get("breakdown") if isinstance(o.get("breakdown"), dict) else {}
        if len(json.dumps(bd)) > 60_000:
            bd = {}
        sig = ",".join(sorted(str(id_map[r["id"]]) for r in refs))
        oid = db.run("INSERT INTO outfits (user_id, occasion, weather, temperature_c, style_pref, palette_pref, score, breakdown, "
                     "explanation, signature, engine, created_at, worn_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (uid, o["occasion"], o["weather"], temp, o.get("style_pref") if o.get("style_pref") in C.STYLES else None,
                      o.get("palette_pref") if o.get("palette_pref") in C.PALETTES else "any", score, db.as_json(bd),
                      str(o.get("explanation") or "")[:2000], sig, "rules" if o.get("engine") == "rules" else "hybrid",
                      _date(o.get("created_at")), _date(o["worn_at"]) if o.get("worn_at") else None))
        for pos, r in enumerate(refs):
            db.run("INSERT IGNORE INTO outfit_items (outfit_id, item_id, role, position) VALUES (%s,%s,%s,%s)",
                   (oid, id_map[r["id"]], r.get("role") if r.get("role") in C.CATEGORIES else "top", pos))
        shots = [s for s in (o.get("photos") or []) if isinstance(s, dict) and s.get("key") in key_map][-store.MAX_SHOTS:]
        for s in shots:
            db.run("INSERT INTO outfit_photos (outfit_id, image_key, model) VALUES (%s,%s,%s)",
                   (oid, key_map[s["key"]], str(s.get("model") or "")[:80] or None))
        if shots:
            cover = o.get("photo_cover") if isinstance(o.get("photo_cover"), int) else len(shots) - 1
            db.run("UPDATE outfits SET photo_cover = %s WHERE id = %s", (max(0, min(cover, len(shots) - 1)), oid))
        outfit_map[o.get("id")] = oid
    for f in backup.get("feedback") or []:
        if isinstance(f, dict) and f.get("outfit_id") in outfit_map and f.get("verdict") in ("like", "dislike"):
            db.run("INSERT IGNORE INTO feedback (outfit_id, user_id, verdict) VALUES (%s,%s,%s)", (outfit_map[f["outfit_id"]], uid, f["verdict"]))
    for s in backup.get("saved") or []:
        if isinstance(s, dict) and s.get("outfit_id") in outfit_map:
            db.run("INSERT IGNORE INTO saved_outfits (user_id, outfit_id, name, created_at) VALUES (%s,%s,%s,%s)",
                   (uid, outfit_map[s["outfit_id"]], str(s.get("name") or "Saved outfit")[:80], sec.now()))
    if isinstance(backup.get("preferences"), dict):
        pv = _clean_prefs(uid, backup["preferences"])
        if not pv.errors:
            db.run("INSERT INTO preferences (user_id, data) VALUES (%s,%s) ON DUPLICATE KEY UPDATE data = VALUES(data)",
                   (uid, db.as_json(pv.clean)))
    return {"items": sum(1 for it, _ in cleaned if not it.get("deleted_at")), "outfits": len(outfit_map)}


# ---------------------------------------------------------------- demo wardrobe

@bp.post("/api/demo/load")
@sec.login_required
def demo_load():
    """The 40 real CC0 garment photos shipped with the site, added to this wardrobe."""
    uid = g.user["id"]
    root = current_app.config["FRONTEND_DIR"]
    catalog = json.loads((root / "assets/images/garments/catalog.json").read_text())
    n_now = db.one("SELECT COUNT(*) AS n FROM items WHERE user_id = %s AND deleted_at IS NULL", (uid,))["n"]
    if n_now + len(catalog) > current_app.config["MAX_ITEMS"]:
        raise bad("There isn't room in your wardrobe for the demo pieces.")
    added = 0
    for gm in catalog:
        photo = (root / gm["image"]).resolve()
        cut = (root / gm["cutout"]).resolve() if gm.get("cutout") else None
        if root.resolve() not in photo.parents:
            continue
        data, mime = store.clean_photo(photo.read_bytes())
        ikey = store.save_image(uid, data, mime)
        ckey = None
        if cut and root.resolve() in cut.parents and cut.exists():
            cdata, cmime = store.clean_photo(cut.read_bytes(), keep_alpha=True)
            ckey = store.save_image(uid, cdata, cmime)
        sec_hex = gm.get("secondary_color")
        db.run("INSERT INTO items (user_id, name, category, subcategory, main_color_hex, main_color_name, secondary_color_hex, "
               "secondary_color_name, pattern, seasons, style, occasions, description, image_key, cutout_key, image_source, "
               "created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
               (uid, gm["name"], gm["category"], gm["subcategory"], gm["main_color"], store.nearest_name(gm["main_color"]),
                sec_hex, store.nearest_name(sec_hex) if sec_hex else None, gm.get("pattern", ""),
                db.as_json(gm["seasons"]), gm["style"], db.as_json(gm["occasions"]),
                "Demo photo from the CC0 clothing dataset.", ikey, ckey, "upload", sec.now(), sec.now()))
        added += 1
    return {"added": added}
