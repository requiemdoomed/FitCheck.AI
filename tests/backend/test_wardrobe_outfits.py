"""Wardrobe, photos, ownership, recommendations, history, saved, dashboard."""

from conftest import ITEM, add_item, basic_wardrobe, jpeg


def test_item_validation_and_crud(user):
    r = user.post("/api/wardrobe", json={})
    assert r.status_code == 400 and len(r.json["error"]["details"]) >= 6
    it = add_item(user)
    assert it["main_color"] == {"hex": "#f5f5f2", "name": "white"} and it["seasons"] == ["spring", "autumn"]
    r = user.put(f"/api/wardrobe/{it['id']}", json={"name": "Oxford shirt", "main_color": "#A9C4E4"})
    assert r.json["item"]["name"] == "Oxford shirt" and r.json["item"]["main_color"]["name"] == "light blue"
    assert user.delete(f"/api/wardrobe/{it['id']}").status_code == 204
    assert user.get(f"/api/wardrobe/{it['id']}").status_code == 404


def test_upload_is_checked_and_re_encoded(app, user):
    data = {**ITEM, "seasons": "spring,autumn", "occasions": "work"}
    form = {**data, "image": (__import__("io").BytesIO(jpeg(exif_gps=True)), "p.jpg"), "image_source": "upload", "pattern": "striped"}
    r = user.post("/api/wardrobe", data=form, content_type="multipart/form-data")
    assert r.status_code == 201, r.json
    item = r.json["item"]
    assert item["image_url"].startswith("api/images/") and item["pattern"] == "striped"
    img = user.get("/" + item["image_url"])
    assert img.status_code == 200 and img.mimetype == "image/webp" and b"GPS" not in img.data
    assert "private" in img.headers["Cache-Control"]
    bad = {**data, "image": (__import__("io").BytesIO(b"<?php echo 1; ?>" + b"x" * 200), "p.jpg")}
    r = user.post("/api/wardrobe", data=bad, content_type="multipart/form-data")
    assert r.status_code == 400 and r.json["error"]["code"] == "invalid_image"


def test_other_people_see_nothing(client_for, user):
    it = add_item(user)
    form = {**ITEM, "seasons": "spring", "occasions": "work", "image": (__import__("io").BytesIO(jpeg()), "p.jpg")}
    photo = user.post("/api/wardrobe", data=form, content_type="multipart/form-data").json["item"]["image_url"]
    other = client_for()
    other.register("other-person@example.com")
    assert other.get(f"/api/wardrobe/{it['id']}").status_code == 404
    assert other.put(f"/api/wardrobe/{it['id']}", json={"name": "x"}).status_code == 404
    assert other.delete(f"/api/wardrobe/{it['id']}").status_code == 404
    assert other.get("/" + photo).status_code == 404
    assert client_for().get("/" + photo).status_code == 404                      # signed out
    assert other.get("/api/wardrobe").json["count"] == 0


def test_search_is_parameterised(user):
    add_item(user)
    for q in ("' OR 1=1 --", "%", "_", "\\", "shirt'; DROP TABLE items; --"):
        r = user.get("/api/wardrobe", query_string={"q": q})
        assert r.status_code == 200 and r.json["count"] == 0, q
    assert user.get("/api/wardrobe", query_string={"q": "white"}).json["count"] == 1


def test_generate_feedback_save_wear_history_dashboard(user):
    r = user.post("/api/recommendations/generate", json={"occasion": "work", "weather": "sunny", "temperature_c": 18})
    assert r.status_code == 422 and set(r.json["error"]["details"]["missing"]) == {"footwear", "top", "bottom"}
    basic_wardrobe(user)
    r = user.post("/api/recommendations/generate", json={"occasion": "work", "weather": "sunny", "temperature_c": 18})
    assert r.status_code == 201, r.json
    o = r.json["outfit"]
    assert 0 <= o["score"] <= 100 and o["engine"] == "hybrid" and len(o["items"]) >= 3 and o["breakdown"]["components"]
    oid = o["id"]
    assert user.post(f"/api/recommendations/{oid}/feedback", json={"verdict": "like"}).json["feedback"] == "like"
    assert user.post(f"/api/recommendations/{oid}/save", json={"name": "Monday"}).json["name"] == "Monday"
    assert user.post(f"/api/recommendations/{oid}/wear", json={"worn": True}).json["worn_at"]
    got = user.get(f"/api/recommendations/{oid}").json["outfit"]
    assert got["feedback"] == "like" and got["saved_name"] == "Monday" and got["worn_at"]
    assert user.get("/api/recommendations/history", query_string={"verdict": "like"}).json["total"] == 1
    saved = user.get("/api/outfits/saved").json
    assert saved["count"] == 1
    assert user.delete(f"/api/outfits/saved/{got['saved_id']}").status_code == 204
    r = user.post("/api/recommendations/generate",
                  json={"occasion": "work", "weather": "sunny", "temperature_c": 18, "exclude": [o["signature"]]})
    assert r.status_code == 409 and r.json["error"]["code"] == "no_more_combinations"
    s = user.get("/api/dashboard/summary").json
    assert s["counts"]["items"] == 3 and s["counts"]["outfits"] == 1 and s["ready_to_generate"]
    st = user.get("/api/dashboard/statistics").json
    assert len(st["weekly"]) == 8 and st["most_recommended"]


def test_generate_validates_input(user):
    for body in ({"occasion": "rave", "weather": "sunny", "temperature_c": 1}, {"occasion": "work", "weather": "sunny", "temperature_c": 99},
                 {"occasion": "work", "weather": "sunny", "temperature_c": "hot"},
                 {"occasion": "work", "weather": "sunny", "temperature_c": 1, "exclude": "x"}):
        assert user.post("/api/recommendations/generate", json=body).status_code == 400


def test_demo_wardrobe(user):
    r = user.post("/api/demo/load")
    assert r.status_code == 200 and r.json["added"] == 40
    items = user.get("/api/wardrobe").json["items"]
    assert len(items) == 40 and sum(1 for i in items if i["pattern"]) == 9
