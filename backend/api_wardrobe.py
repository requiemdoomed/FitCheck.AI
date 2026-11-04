"""The wardrobe: pieces of clothing and their photos."""

from flask import Blueprint, Response, current_app, g, request

import db
import security as sec
import store
from errors import ApiError, bad, not_found
from validation import V

bp = Blueprint("wardrobe", __name__)
C = store.CATALOG

SORTS = {
    "newest": "created_at DESC, id DESC", "oldest": "created_at ASC, id ASC", "name": "name ASC, id ASC",
    "category": "FIELD(category,'outerwear','top','dress','bottom','footwear','accessory'), name ASC",
}


def _fields(data, partial=False):
    v = V(data)
    has = lambda f: not partial or f in data  # noqa: E731
    req = not partial
    if has("name"):
        v.text("name", max=80, required=req)
    if has("category"):
        v.choice("category", C.CATEGORIES, required=req)
    if has("subcategory"):
        v.text("subcategory", max=40, required=req)
    if has("style"):
        v.choice("style", C.STYLES, required=req)
    if has("seasons"):
        v.multi("seasons", C.SEASONS, required=req)
    if has("occasions"):
        v.multi("occasions", C.OCCASIONS, required=req)
    if has("description"):
        v.text("description", required=False, max=500, default="")
    if "pattern" in data:
        v.choice("pattern", ["striped", "patterned"], required=False, default="")
    out = dict(v.clean)
    if out.get("subcategory"):
        out["subcategory"] = out["subcategory"].lower()
    if has("main_color"):
        hx = store.color.normalize_hex(data.get("main_color"))
        if not hx:
            v.errors["main_color"] = "Pick the main colour."
        else:
            out["main_color_hex"], out["main_color_name"] = hx, store.nearest_name(hx)
    if "secondary_color" in data:
        raw = data.get("secondary_color")
        if raw in (None, "", "none"):
            out["secondary_color_hex"] = out["secondary_color_name"] = None
        else:
            hx = store.color.normalize_hex(raw)
            if not hx:
                v.errors["secondary_color"] = "That isn't a valid colour."
            else:
                out["secondary_color_hex"], out["secondary_color_name"] = hx, store.nearest_name(hx)
    v.done()
    return out


def _form():
    """Fields from JSON or multipart; lists may repeat or be comma-separated."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    data = {}
    for key in request.form:
        vals = request.form.getlist(key)
        data[key] = vals if key in ("seasons", "occasions") and len(vals) > 1 else vals[0]
    return data


def _pictures(data):
    """The uploaded photo and cut-out (made in the browser), checked and re-encoded here."""
    photo = request.files.get("image")
    cut = request.files.get("cutout")
    source = data.get("image_source") if data.get("image_source") in ("upload", "stock") else None
    out = {}
    if photo and photo.filename is not None:
        blob, mime = store.clean_photo(photo.read(), keep_alpha=source == "stock")
        out["image_key"] = store.save_image(g.user["id"], blob, mime)
        out["image_source"] = source or "upload"
    if cut:
        blob, mime = store.clean_photo(cut.read(), keep_alpha=True)
        out["cutout_key"] = store.save_image(g.user["id"], blob, mime)
    if "image_key" in out and "cutout_key" not in out and out["image_source"] == "stock":
        out["cutout_key"] = out["image_key"]
    return out


def _own_item(item_id):
    it = db.one("SELECT * FROM items WHERE id = %s AND user_id = %s AND deleted_at IS NULL", (item_id, g.user["id"]))
    if not it:
        raise not_found("That clothing item")
    return it


@bp.get("/api/wardrobe")
@sec.login_required
def list_items():
    f = (V(request.args.to_dict()).choice("category", C.CATEGORIES, required=False).choice("season", C.SEASONS, required=False)
         .choice("style", C.STYLES, required=False).choice("occasion", C.OCCASIONS, required=False)
         .choice("color", list(store.color.NAMED_COLORS), required=False).text("q", required=False, max=80)
         .choice("sort", list(SORTS), required=False, default="newest").done("That filter isn't valid."))
    where, args = ["user_id = %s", "deleted_at IS NULL"], [g.user["id"]]
    if f.get("category"):
        where.append("category = %s"); args.append(f["category"])
    if f.get("color"):
        where.append("(main_color_name = %s OR secondary_color_name = %s)"); args += [f["color"]] * 2
    if f.get("season"):
        where.append("JSON_CONTAINS(seasons, JSON_QUOTE(%s))"); args.append(f["season"])
    if f.get("occasion"):
        where.append("JSON_CONTAINS(occasions, JSON_QUOTE(%s))"); args.append(f["occasion"])
    if f.get("style"):
        where.append("style = %s"); args.append(f["style"])
    if f.get("q"):
        like = "%" + f["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(name LIKE %s OR subcategory LIKE %s OR description LIKE %s OR main_color_name LIKE %s)")
        args += [like] * 4
    rows = db.all_(f"SELECT * FROM items WHERE {' AND '.join(where)} ORDER BY {SORTS[f['sort'] or 'newest']}", args)  # nosec B608: fixed clauses and a whitelisted sort; values bound
    counts = db.all_("SELECT main_color_name AS name, COUNT(*) AS n FROM items WHERE user_id = %s AND deleted_at IS NULL "
                     "GROUP BY main_color_name ORDER BY n DESC, name", (g.user["id"],))
    return {"items": [store.item_json(r) for r in rows], "count": len(rows),
            "colors": [{"name": c["name"], "hex": store.color.NAMED_COLORS.get(c["name"], "#888888"), "count": c["n"]} for c in counts]}


@bp.post("/api/wardrobe")
@sec.login_required
def create_item():
    data = _form()
    clean = _fields(data)
    n = db.one("SELECT COUNT(*) AS n FROM items WHERE user_id = %s AND deleted_at IS NULL", (g.user["id"],))["n"]
    if n >= current_app.config["MAX_ITEMS"]:
        raise bad(f"A wardrobe can hold up to {current_app.config['MAX_ITEMS']} items.")
    pics = _pictures(data)
    row = {"secondary_color_hex": None, "secondary_color_name": None, "description": "", "pattern": "",
           "image_key": None, "cutout_key": None, "image_source": None, **clean, **pics}
    cols = ["user_id", "name", "category", "subcategory", "main_color_hex", "main_color_name", "secondary_color_hex",
            "secondary_color_name", "pattern", "seasons", "style", "occasions", "description", "image_key",
            "cutout_key", "image_source", "created_at", "updated_at"]
    vals = [g.user["id"], row["name"], row["category"], row["subcategory"], row["main_color_hex"], row["main_color_name"],
            row["secondary_color_hex"], row["secondary_color_name"], row["pattern"] or "", db.as_json(row["seasons"]),
            row["style"], db.as_json(row["occasions"]), row["description"] or "", row["image_key"], row["cutout_key"],
            row["image_source"], sec.now(), sec.now()]
    iid = db.run(f"INSERT INTO items ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)  # nosec B608: constant column list; values bound
    return {"item": store.item_json(db.one("SELECT * FROM items WHERE id = %s", (iid,)))}, 201


@bp.get("/api/wardrobe/<int:item_id>")
@sec.login_required
def get_item(item_id):
    return {"item": store.item_json(_own_item(item_id))}


@bp.put("/api/wardrobe/<int:item_id>")
@sec.login_required
def update_item(item_id):
    it = _own_item(item_id)
    data = _form()
    changes = _fields(data, partial=True)
    old_keys = []
    pics = _pictures(data)
    if pics:
        changes.update(pics)
        old_keys = [it["image_key"], it["cutout_key"]]
    elif str(data.get("remove_image", "")).lower() in ("1", "true", "yes"):
        changes.update({"image_key": None, "cutout_key": None, "image_source": None})
        old_keys = [it["image_key"], it["cutout_key"]]
    if changes:
        for k in ("seasons", "occasions"):
            if k in changes:
                changes[k] = db.as_json(changes[k])
        sets = ", ".join(f"{k} = %s" for k in changes)
        db.run(f"UPDATE items SET {sets}, updated_at = %s WHERE id = %s", (*changes.values(), sec.now(), it["id"]))  # nosec B608: keys come from the validator's fixed field list
    keep = {changes.get("image_key"), changes.get("cutout_key")}
    store.delete_images([k for k in old_keys if k not in keep])
    return {"item": store.item_json(db.one("SELECT * FROM items WHERE id = %s", (it["id"],)))}


@bp.delete("/api/wardrobe/<int:item_id>")
@sec.login_required
def delete_item(item_id):
    it = _own_item(item_id)
    db.run("UPDATE items SET deleted_at = %s WHERE id = %s", (sec.now(), it["id"]))
    return "", 204


@bp.get("/api/images/<string:key>")
def image(key):
    if len(key) != 32 or not key.isalnum():
        raise not_found("That image")
    row = db.one("SELECT user_id, mime, data FROM images WHERE ikey = %s", (key,))
    if not row:
        raise not_found("That image")
    if row["user_id"] is not None:
        user = sec.current_user(optional=True)
        if not user or user["id"] != row["user_id"]:
            raise not_found("That image")          # same answer as missing: keys can't be probed
    resp = Response(bytes(row["data"]), mimetype=row["mime"])
    resp.headers["Cache-Control"] = "private, max-age=604800, immutable" if row["user_id"] else "public, max-age=86400"
    resp.headers["Content-Disposition"] = "inline"
    return resp
