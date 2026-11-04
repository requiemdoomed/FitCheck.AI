"""Realistic outfit photos: settings, per-outfit photos, and landing-page samples."""

import hashlib

from flask import Blueprint, current_app, g, request

import db
import photo_engine as pe
import security as sec
import store
from errors import ApiError, bad, not_found

bp = Blueprint("photos", __name__)
C = store.CATALOG


# ---------------------------------------------------------------- settings (keys sealed in the database)

def _settings(uid):
    row = db.one("SELECT engine, sealed FROM secrets WHERE user_id = %s", (uid,))
    data = sec.unseal(row["sealed"]) if row else {}
    return {"engine": (row or {}).get("engine") or "free", "pollen": data.get("pollen", ""), "gemini": data.get("gemini")}


def _save_settings(uid, s):
    sealed = sec.seal({"pollen": s.get("pollen", ""), "gemini": s.get("gemini")})
    engine = s["engine"] if s["engine"] == "gemini" and s.get("gemini") else "free"
    db.run("INSERT INTO secrets (user_id, engine, sealed) VALUES (%s, %s, %s) "
           "ON DUPLICATE KEY UPDATE engine = VALUES(engine), sealed = VALUES(sealed)", (uid, engine, sealed))


def _status(uid):
    s = _settings(uid)
    gem = s["gemini"] or {}
    engine = "gemini" if s["engine"] == "gemini" and gem.get("key") else "free"
    server_key = bool(current_app.config["POLLINATIONS_KEY"])
    return {
        "configured": True, "engine": engine,
        "model": gem.get("model") if engine == "gemini" else
        ("Z-Image / FLUX.2 klein (Pollinations)" if s["pollen"] or server_key else "FLUX.1 (Pollinations)"),
        "free": {"key_hint": f"…{s['pollen'][-4:]}" if s["pollen"] else None, "server_key": server_key},
        "gemini": {"configured": bool(gem.get("key")), "model": gem.get("model"), "hint": f"…{gem['key'][-4:]}" if gem.get("key") else None},
    }


@bp.get("/api/photos/status")
@sec.login_required
def status():
    return _status(g.user["id"])


@bp.put("/api/photos/free")
@sec.login_required
def use_free():
    body = request.get_json(silent=True) or {}
    s = _settings(g.user["id"])
    if "key" in body:
        k = str(body.get("key") or "").strip()
        if k and (len(k) < 12 or len(k) > 200 or not all(c.isalnum() or c in "_-" for c in k)):
            raise bad("That doesn't look like a Pollinations key.", {"pollen_key": "That doesn't look like a Pollinations key. Copy it from enter.pollinations.ai."})
        s["pollen"] = k
    s["engine"] = "free"
    _save_settings(g.user["id"], s)
    return _status(g.user["id"])


@bp.post("/api/photos/gemini")
@sec.login_required
def connect_gemini():
    key = str((request.get_json(silent=True) or {}).get("key") or "").strip()
    if not (20 <= len(key) <= 200) or not all(c.isalnum() or c in "_-" for c in key):
        raise ApiError(400, "photo_bad_key", "That doesn't look like a Gemini API key. They're long codes that usually start with AIza.")
    models = pe.Gemini(current_app.config, key).connect()
    s = _settings(g.user["id"])
    s.update(engine="gemini", gemini={"key": key, "model": models[0]})
    _save_settings(g.user["id"], s)
    return {**_status(g.user["id"]), "models": models}


@bp.post("/api/photos/gemini/use")
@sec.login_required
def use_gemini():
    s = _settings(g.user["id"])
    if not (s["gemini"] or {}).get("key"):
        raise ApiError(409, "photo_key_missing", "Add your Gemini API key first.")
    s["engine"] = "gemini"
    _save_settings(g.user["id"], s)
    return _status(g.user["id"])


@bp.delete("/api/photos/gemini")
@sec.login_required
def disconnect_gemini():
    s = _settings(g.user["id"])
    s.update(engine="free", gemini=None)
    _save_settings(g.user["id"], s)
    return _status(g.user["id"])


# ---------------------------------------------------------------- making a photo

def _limit_user():
    uid = str(g.user["id"])
    wait = sec.limited("photo", uid, current_app.config["PHOTOS_PER_HOUR"], 60)
    if wait:
        raise ApiError(429, "photo_quota", f"That's a lot of photos for one hour. Try again in {wait // 60 + 1} minutes.")
    sec.record("photo", uid)


def _image_bytes(key):
    row = db.one("SELECT data FROM images WHERE ikey = %s", (key,)) if key else None
    return bytes(row["data"]) if row else None


def make_photo(uid, pieces_rows, occasion, backdrop):
    """pieces_rows: item dicts with role. Returns (bytes, mime, model)."""
    cfg = current_app.config
    p = store.prefs(uid)
    person = {"build": p["model_build"], "skin": p["model_skin"], "body": p["model_body"]}
    setting = p.get("photo_setting") or "studio"
    order = {r: i for i, r in enumerate(pe.ORDER)}
    rows = sorted(pieces_rows, key=lambda r: order.get(r["role"], 9))
    pieces = [{"role": r["role"], "subcategory": r["subcategory"], "colour": r["main_color_name"], "hex": r["main_color_hex"],
               "pattern": r.get("pattern") or "", "secondary": r.get("secondary_color_name") if r.get("pattern") else ""} for r in rows]
    refs = []
    for r in rows:
        key = (r.get("image_key") or r.get("cutout_key")) if r.get("image_source") == "upload" else (r.get("cutout_key") or r.get("image_key"))
        refs.append(_image_bytes(key))
    s = _settings(uid)
    seed = pe.new_seed()
    if s["engine"] == "gemini" and (s["gemini"] or {}).get("key"):
        gem = pe.Gemini(cfg, s["gemini"]["key"], s["gemini"]["model"])
        jpegs = [pe.board([b]) if b else None for b in refs]
        try:
            data, model = gem.make(pieces, jpegs, person, occasion, backdrop, setting)
        except ApiError as e:
            if e.code != "photo_no_model":
                raise
            models = gem.connect()                      # model retired: pick again, once
            s["gemini"]["model"] = gem.model = models[0]
            _save_settings(uid, s)
            data, model = gem.make(pieces, jpegs, person, occasion, backdrop, setting)
    else:
        key = s["pollen"] or cfg["POLLINATIONS_KEY"]
        free = pe.Free(cfg, key)
        prompt = pe.prompt_for(pieces, person, occasion, backdrop, setting)
        board_note = pe.prompt_for(pieces, person, occasion, backdrop, setting, board_note=True)
        jpeg = pe.board([b for b in refs if b]) if key else None
        data, model = free.make(prompt, board_note, jpeg, seed)
        model = f"{model} (Pollinations)"
    data, mime = pe.check_image(data)
    return data, mime, model


@bp.post("/api/photos/outfit/<int:oid>")
@sec.login_required
def outfit_photo(oid):
    uid = g.user["id"]
    o = store.own_outfit(uid, oid)
    force = bool((request.get_json(silent=True) or {}).get("force"))
    shots = store.photos_of(o["id"])
    if shots and not force:
        return {**store.photos_json(o, shots), "cached": True, "model": store.photos_json(o, shots)["photo_model"]}
    _limit_user()
    data, mime, model = make_photo(uid, store.outfit_items(o["id"]), o["occasion"], o["id"] + len(shots))
    key = store.save_image(uid, data, mime)
    db.run("INSERT INTO outfit_photos (outfit_id, image_key, model) VALUES (%s, %s, %s)", (o["id"], key, model[:80]))
    shots = store.photos_of(o["id"])
    if len(shots) > store.MAX_SHOTS:
        for old in shots[:-store.MAX_SHOTS]:
            db.run("DELETE FROM outfit_photos WHERE id = %s", (old["id"],))
            store.delete_images([old["image_key"]])
        shots = shots[-store.MAX_SHOTS:]
    db.run("UPDATE outfits SET photo_cover = %s WHERE id = %s", (len(shots) - 1, o["id"]))
    o = store.own_outfit(uid, oid)
    pj = store.photos_json(o, shots)
    return {**pj, "model": pj["photo_model"], "cached": False}


@bp.post("/api/photos/outfit/<int:oid>/choose")
@sec.login_required
def choose(oid):
    o = store.own_outfit(g.user["id"], oid)
    shots = store.photos_of(o["id"])
    idx = (request.get_json(silent=True) or {}).get("index")
    if not isinstance(idx, int) or not 0 <= idx < len(shots):
        raise bad("That photo doesn't exist.")
    db.run("UPDATE outfits SET photo_cover = %s WHERE id = %s", (idx, o["id"]))
    pj = store.photos_json(store.own_outfit(g.user["id"], oid), shots)
    return {**pj, "model": pj["photo_model"]}


@bp.post("/api/photos/suggestion")
@sec.login_required
def suggestion_photo():
    """A Smart buys basic worn with some of the person's own pieces (not stored)."""
    body = request.get_json(silent=True) or {}
    basic = body.get("basic") or {}
    if basic.get("category") not in C.CATEGORIES or not isinstance(basic.get("subcategory"), str) or len(basic["subcategory"]) > 40:
        raise bad("That suggestion isn't valid.")
    hx = store.color.normalize_hex(basic.get("hex"))
    if not hx:
        raise bad("That suggestion isn't valid.")
    ids = [i for i in (body.get("item_ids") or []) if isinstance(i, int)][:5]
    rows = [r for r in store.active_items(g.user["id"]) if r["id"] in ids]
    pieces = [{**r, "role": r["category"]} for r in rows]
    pieces.append({"role": basic["category"], "subcategory": basic["subcategory"].lower(), "main_color_hex": hx,
                   "main_color_name": store.nearest_name(hx), "pattern": "", "image_key": None, "cutout_key": None,
                   "image_source": None})
    occasion = body.get("occasion") if body.get("occasion") in C.OCCASIONS else "casual"
    _limit_user()
    data, mime, model = make_photo(g.user["id"], pieces, occasion, len(basic["subcategory"]))
    key = store.save_image(g.user["id"], data, mime)
    return {"photo_url": store.image_url(key), "model": model}


# ---------------------------------------------------------------- landing page samples (no account)

@bp.post("/api/public/photo")
def public_photo():
    """
    A sample photo for the landing page: catalogue values only, no account,
    cached by its exact description so a repeat costs nothing, and limited per IP.
    """
    body = request.get_json(silent=True) or {}
    raw = body.get("pieces")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4:
        raise bad("Send 1 to 4 pieces.")
    pieces = []
    for p in raw:
        if not isinstance(p, dict) or p.get("role") not in C.CATEGORIES:
            raise bad("That piece isn't valid.")
        sub = p.get("subcategory")
        if sub not in C.SUBCATEGORIES.get(p["role"], {}):
            raise bad("That piece isn't valid.")
        colour = p.get("colour")
        if colour not in store.color.NAMED_COLORS:
            raise bad("That colour isn't valid.")
        pattern = p.get("pattern") if p.get("pattern") in ("striped", "patterned") else ""
        secondary = p.get("secondary") if p.get("secondary") in store.color.NAMED_COLORS else ""
        pieces.append({"role": p["role"], "subcategory": sub, "colour": colour, "pattern": pattern,
                       "secondary": secondary if pattern else ""})
    person = body.get("person") or {}
    person = {"build": "fem" if person.get("build") == "fem" else "masc",
              "skin": person.get("skin") if person.get("skin") in pe.SKIN else "medium"}
    occasion = body.get("occasion") if body.get("occasion") in C.OCCASIONS else "casual"
    backdrop = body.get("backdrop") if isinstance(body.get("backdrop"), int) and 0 <= body["backdrop"] < 100 else 0
    prompt = pe.prompt_for(pieces, person, occasion, backdrop)
    cache_key = hashlib.sha256(prompt.encode()).hexdigest()
    hit = db.one("SELECT ikey FROM images WHERE cache_key = %s AND user_id IS NULL LIMIT 1", (cache_key,))
    if hit:
        return {"photo_url": store.image_url(hit["ikey"]), "cached": True}
    ip = sec.client_ip()
    wait = sec.limited("public_photo", ip, current_app.config["PUBLIC_PHOTOS_PER_HOUR"], 60)
    if wait:
        raise ApiError(429, "photo_quota", "Sample photos are limited per hour. Create an account to see your own outfits.")
    sec.record("public_photo", ip)
    cfg = current_app.config
    data, _model = pe.Free(cfg, cfg["POLLINATIONS_KEY"]).make(prompt, prompt, None, int(cache_key[:8], 16) % 2**31)
    data, mime = pe.check_image(data)
    key = store.save_image(None, data, mime, cache_key=cache_key)
    return {"photo_url": store.image_url(key), "cached": False}
