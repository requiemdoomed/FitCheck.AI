"""Outfit suggestions, history, saved outfits and the dashboard."""

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, request

import db
import security as sec
import store
from errors import ApiError, bad, not_found
from validation import V
from fitcheck_ml import ml, recommender  # noqa: E402  (path set up by store)

bp = Blueprint("outfits", __name__)
C = store.CATALOG
MISSING_WORDS = {"top": "a top", "bottom": "a bottom", "footwear": "a pair of shoes"}


def _bundle():
    return ml.get_bundle(current_app.config["MODEL_DIR"])


def _feedback_inputs(user_id):
    rows = db.all_("SELECT f.verdict, o.id, o.breakdown FROM feedback f JOIN outfits o ON o.id = f.outfit_id "
                   "WHERE f.user_id = %s ORDER BY f.updated_at DESC LIMIT 200", (user_id,))
    history, liked, disliked = [], Counter(), Counter()
    for r in rows:
        feats = (r["breakdown"] or {}).get("features")
        if feats:
            history.append((feats, r["verdict"]))
        target = liked if r["verdict"] == "like" else disliked
        for it in db.all_("SELECT item_id FROM outfit_items WHERE outfit_id = %s", (r["id"],)):
            target[it["item_id"]] += 1
    return history, dict(liked), dict(disliked)


@bp.get("/api/health")
def health():
    try:
        db.one("SELECT 1 AS ok")
        database = "ok"
    except Exception:
        database = "unreachable"
    status = _bundle().status()
    return ({"status": "ok" if database == "ok" else "degraded", "database": database, "models": status},
            200 if database == "ok" else 503)


@bp.get("/api/meta/options")
def options():
    opts = C.options()
    opts["colors"] = [{"name": n, "hex": h} for n, h in store.color.NAMED_COLORS.items()]
    return opts


@bp.post("/api/recommendations/generate")
@sec.login_required
def generate():
    body = request.get_json(silent=True) or {}
    clean = (V(body).choice("occasion", C.OCCASIONS).choice("weather", C.WEATHER)
             .number("temperature_c", -40, 50, label="Temperature")
             .choice("style", C.STYLES, required=False).choice("palette", C.PALETTES, required=False).done())
    exclude = body.get("exclude") or []
    if not isinstance(exclude, list) or len(exclude) > 200 or any(not isinstance(s, str) or len(s) > 255 for s in exclude):
        raise bad("exclude must be a list of outfit signatures.")
    uid = g.user["id"]
    p = store.prefs(uid)
    ctx = {"occasion": clean["occasion"], "weather": clean["weather"], "temperature_c": clean["temperature_c"],
           "style": clean.get("style"), "palette": clean.get("palette") or p["preferred_palette"] or "any",
           "favorite_colors": p["favorite_colors"], "avoided_colors": p["avoided_colors"],
           "preferred_styles": p["preferred_styles"]}
    items = store.active_items(uid)
    recent = []
    prev = body.get("previous_id")
    if isinstance(prev, int):
        recent += [{"id": r["item_id"], "category": r["role"]} for r in
                   db.all_("SELECT oi.item_id, oi.role FROM outfit_items oi JOIN outfits o ON o.id = oi.outfit_id "
                           "WHERE o.id = %s AND o.user_id = %s", (prev, uid))]
    # pieces worn in the last three days rest for a while
    recent += [{"id": r["item_id"], "category": r["role"]} for r in
               db.all_("SELECT oi.item_id, oi.role FROM outfit_items oi JOIN outfits o ON o.id = oi.outfit_id "
                       "WHERE o.user_id = %s AND o.worn_at >= %s", (uid, sec.now() - timedelta(days=3)))]
    history, liked, disliked = _feedback_inputs(uid)
    try:
        res = recommender.recommend(items, ctx, bundle=_bundle(), history=history, liked_counts=liked,
                                    disliked_counts=disliked, exclude=exclude, recent=recent or None)
    except recommender.NotEnoughItems as e:
        if not e.missing:
            raise ApiError(409, "no_more_combinations", "You've seen every combination your wardrobe can make for this. "
                           "Change the occasion or weather, or add more pieces.")
        raise ApiError(422, "wardrobe_incomplete", f"Add {', '.join(MISSING_WORDS[m] for m in e.missing)} to your wardrobe "
                       "first. An outfit needs a top and bottom (or a dress) plus shoes.", {"missing": e.missing})
    oid = db.run("INSERT INTO outfits (user_id, occasion, weather, temperature_c, style_pref, palette_pref, score, "
                 "breakdown, explanation, signature, engine, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                 (uid, ctx["occasion"], ctx["weather"], ctx["temperature_c"], ctx["style"], ctx["palette"], res["score"],
                  db.as_json(res["breakdown"]), res["explanation"], res["signature"], res["engine"], sec.now()))
    for pos, it in enumerate(res["items"]):
        db.run("INSERT INTO outfit_items (outfit_id, item_id, role, position) VALUES (%s, %s, %s, %s)",
               (oid, it["id"], it["category"], pos))
    out = store.outfit_json(store.own_outfit(uid, oid))
    out["candidates_considered"] = res["breakdown"]["candidates_considered"]
    return {"outfit": out}, 201


@bp.get("/api/recommendations/history")
@sec.login_required
def history():
    try:
        page = max(1, min(1000, int(request.args.get("page", 1))))
        per = max(1, min(50, int(request.args.get("per_page", 12))))
    except ValueError:
        raise bad("page and per_page must be numbers.")
    verdict = request.args.get("verdict", "")
    if verdict not in ("", "like", "dislike"):
        raise bad("verdict must be like or dislike.")
    uid = g.user["id"]
    join = "JOIN feedback f ON f.outfit_id = o.id AND f.verdict = %s" if verdict else ""
    args = ([verdict] if verdict else []) + [uid]
    total = db.one(f"SELECT COUNT(*) AS n FROM outfits o {join} WHERE o.user_id = %s", args)["n"]  # nosec B608: join is a fixed string, values are bound
    rows = db.all_(f"SELECT o.* FROM outfits o {join} WHERE o.user_id = %s ORDER BY o.created_at DESC, o.id DESC "
                   "LIMIT %s OFFSET %s", args + [per, (page - 1) * per])  # nosec B608: as above
    return {"outfits": [store.outfit_json(o, breakdown=False) for o in rows], "page": page, "per_page": per,
            "total": total, "pages": max(1, -(-total // per))}


@bp.get("/api/recommendations/<int:oid>")
@sec.login_required
def get_outfit(oid):
    return {"outfit": store.outfit_json(store.own_outfit(g.user["id"], oid))}


@bp.post("/api/recommendations/<int:oid>/feedback")
@sec.login_required
def feedback(oid):
    verdict = (request.get_json(silent=True) or {}).get("verdict")
    if verdict not in ("like", "dislike", None):
        raise bad("verdict must be like, dislike or null.", {"verdict": "Choose like or dislike."})
    o = store.own_outfit(g.user["id"], oid)
    if verdict is None:
        db.run("DELETE FROM feedback WHERE outfit_id = %s", (o["id"],))
    else:
        db.run("INSERT INTO feedback (outfit_id, user_id, verdict, created_at, updated_at) VALUES (%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE verdict = VALUES(verdict), updated_at = VALUES(updated_at)",
               (o["id"], g.user["id"], verdict, sec.now(), sec.now()))
    return {"outfit_id": o["id"], "feedback": verdict}


@bp.post("/api/recommendations/<int:oid>/wear")
@sec.login_required
def wear(oid):
    worn = (request.get_json(silent=True) or {}).get("worn", True) is not False
    o = store.own_outfit(g.user["id"], oid)
    when = sec.now() if worn else None
    db.run("UPDATE outfits SET worn_at = %s WHERE id = %s", (when, o["id"]))
    return {"worn_at": sec.iso(when)}


@bp.post("/api/recommendations/<int:oid>/save")
@sec.login_required
def save(oid):
    o = store.own_outfit(g.user["id"], oid)
    fallback = f"{o['occasion'].capitalize()} outfit"
    name = V(request.get_json(silent=True) or {}).text("name", required=False, max=80, default=fallback).done()["name"] or fallback
    existing = db.one("SELECT id FROM saved_outfits WHERE outfit_id = %s", (o["id"],))
    if existing:
        db.run("UPDATE saved_outfits SET name = %s WHERE id = %s", (name, existing["id"]))
        sid = existing["id"]
    else:
        sid = db.run("INSERT INTO saved_outfits (user_id, outfit_id, name, created_at) VALUES (%s,%s,%s,%s)",
                     (g.user["id"], o["id"], name, sec.now()))
    return {"saved_id": sid, "outfit_id": o["id"], "name": name}, 201


@bp.get("/api/outfits/saved")
@sec.login_required
def saved():
    rows = db.all_("SELECT o.* FROM saved_outfits s JOIN outfits o ON o.id = s.outfit_id WHERE s.user_id = %s "
                   "ORDER BY s.created_at DESC, s.id DESC", (g.user["id"],))
    return {"outfits": [store.outfit_json(o, breakdown=False) for o in rows], "count": len(rows)}


@bp.delete("/api/outfits/saved/<int:sid>")
@sec.login_required
def unsave(sid):
    if not db.run("DELETE FROM saved_outfits WHERE id = %s AND user_id = %s", (sid, g.user["id"])):
        raise not_found("That saved outfit")
    return "", 204


@bp.get("/api/dashboard/summary")
@sec.login_required
def summary():
    uid = g.user["id"]
    items = store.active_items(uid)
    cats = Counter(i["category"] for i in items)
    missing = [] if cats["footwear"] else ["footwear"]
    if not cats["dress"] and not (cats["top"] and cats["bottom"]):
        missing += [c for c in ("top", "bottom") if not cats[c]]
    stats = db.one("SELECT COUNT(*) AS n, COALESCE(ROUND(AVG(score)),0) AS avg FROM outfits WHERE user_id = %s", (uid,))
    fb = Counter(r["verdict"] for r in db.all_("SELECT verdict FROM feedback WHERE user_id = %s", (uid,)))
    recent = db.all_("SELECT * FROM outfits WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 3", (uid,))
    return {
        "counts": {"items": len(items), "outfits": stats["n"],
                   "saved": db.one("SELECT COUNT(*) AS n FROM saved_outfits WHERE user_id = %s", (uid,))["n"],
                   "likes": fb["like"], "dislikes": fb["dislike"], "avg_score": int(stats["avg"])},
        "by_category": dict(cats), "ready_to_generate": not missing, "missing": missing,
        "recent_outfits": [store.outfit_json(o, breakdown=False) for o in recent],
    }


@bp.get("/api/dashboard/statistics")
@sec.login_required
def statistics():
    uid = g.user["id"]
    items = store.active_items(uid)
    outfits = db.all_("SELECT id, occasion, score, created_at FROM outfits WHERE user_id = %s", (uid,))
    colours = Counter(i["main_color_name"] for i in items).most_common()
    seasons = Counter(s for i in items for s in i["seasons"])
    styles = Counter(i["style"] for i in items)
    occ = {}
    for o in outfits:
        e = occ.setdefault(o["occasion"], [0, 0])
        e[0] += 1
        e[1] += o["score"]
    today = datetime.combine(sec.now().date(), datetime.min.time())
    start = today - timedelta(days=49)
    start -= timedelta(days=start.weekday())
    weekly = []
    for w in range(8):
        a, b = start + timedelta(weeks=w), start + timedelta(weeks=w + 1)
        inw = [o for o in outfits if a <= o["created_at"] < b]
        weekly.append({"week_start": a.date().isoformat(), "outfits": len(inw),
                       "avg_score": round(sum(o["score"] for o in inw) / len(inw)) if inw else None})
    use = Counter(r["item_id"] for r in db.all_("SELECT oi.item_id FROM outfit_items oi JOIN outfits o ON o.id = oi.outfit_id "
                                                "WHERE o.user_id = %s", (uid,)))
    active = {i["id"]: i for i in items}
    most = sorted(((iid, n) for iid, n in use.items() if iid in active), key=lambda x: (-x[1], active[x[0]]["name"]))[:5]
    return {
        "colors": [{"name": n, "hex": store.color.NAMED_COLORS.get(n, "#888888"), "count": c} for n, c in colours],
        "seasons": dict(seasons), "styles": dict(styles.most_common()),
        "occasions": [{"occasion": k, "count": v[0], "avg_score": round(v[1] / v[0])} for k, v in sorted(occ.items(), key=lambda x: -x[1][0])],
        "weekly": weekly,
        "most_recommended": [{**{k: store.item_json(active[i])[k] for k in ("id", "name", "category", "subcategory", "image_url", "cutout_url", "image_source")},
                              "hex": active[i]["main_color_hex"], "count": n} for i, n in most],
        "never_recommended": [{"id": i["id"], "name": i["name"], "category": i["category"]}
                              for i in sorted(items, key=lambda i: i["created_at"]) if i["id"] not in use][:5],
    }
