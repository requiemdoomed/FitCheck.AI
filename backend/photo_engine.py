"""
Realistic outfit photos, made on the server so API keys never reach a browser.
Swayam Shakya

Two engines:
  * free, open source (default): Pollinations (MIT, github.com/pollinations/pollinations)
    running open-weight models. With no key: FLUX.1 text-to-image. With a free
    Pollinations key (the user's own, or a server-wide one in POLLINATIONS_KEY):
    Z-Image Turbo / FLUX.2 klein for text-to-image, and FLUX.2 klein, Qwen-Image or
    FLUX.1 Kontext looking at a board of the outfit's real clothing photos.
  * Google Gemini with the user's own key: the clothing photos as references.

Every call has a timeout; answers must really be images; nothing the services
return is trusted beyond that.
"""

import base64
import io
import random
import time
from urllib.parse import quote, urlencode

import requests
from PIL import Image

from errors import ApiError

# ---------------------------------------------------------------- shared wording

SKIN = {"light": "fair", "medium": "medium", "tan": "tan, olive", "deep": "deep brown"}
BODY = {"slim": "slim", "average": "average", "athletic": "athletic", "curvy": "curvy", "plus": "plus-size"}
BACKDROPS = ["warm peach", "pale sky blue", "soft butter yellow", "pale mint", "soft lilac", "blush pink"]
ROLE_WORD = {"top": "top", "bottom": "bottoms", "dress": "dress", "outerwear": "outer layer, worn open over the top",
             "footwear": "shoes", "accessory": "accessory"}
PLACES = {
    "casual": "a sunlit city street with softly blurred shopfronts", "college": "a leafy university campus walkway",
    "work": "a bright modern office lobby", "formal": "an elegant hotel lobby with warm light",
    "party": "a softly lit lounge in the evening", "sports": "a park running path in the morning",
    "date": "a restaurant terrace at golden hour", "travel": "a light-filled airport terminal",
}
LOOK = {
    "t-shirt": "crew-neck cotton t-shirt", "tank top": "tank top", "polo": "piqué polo shirt",
    "shirt": "cotton button-up shirt with a collar", "dress shirt": "crisp button-up dress shirt with a collar",
    "blouse": "softly draped blouse", "sweater": "crew-neck knit sweater", "turtleneck": "fine-knit turtleneck",
    "hoodie": "cotton fleece hoodie", "sweatshirt": "crew-neck sweatshirt", "athletic top": "athletic t-shirt",
    "jeans": "straight-leg denim jeans", "chinos": "cotton chinos", "trousers": "tailored trousers",
    "cargo pants": "cargo trousers", "shorts": "knee-length shorts", "skirt": "midi skirt",
    "joggers": "tapered joggers", "leggings": "leggings", "athletic shorts": "athletic shorts",
    "casual dress": "knee-length casual dress", "sundress": "light sundress", "cocktail dress": "cocktail dress",
    "evening gown": "floor-length evening gown", "jumpsuit": "jumpsuit",
    "cardigan": "open cardigan", "denim jacket": "denim jacket worn open", "bomber jacket": "bomber jacket worn open",
    "leather jacket": "leather jacket worn open", "blazer": "blazer worn open", "suit jacket": "suit jacket",
    "wool coat": "long wool overcoat worn open", "trench coat": "trench coat worn open", "raincoat": "raincoat",
    "windbreaker": "windbreaker jacket", "puffer jacket": "padded puffer jacket", "parka": "parka",
    "sneakers": "low-top sneakers", "running shoes": "running shoes", "loafers": "leather loafers",
    "dress shoes": "polished leather dress shoes", "ankle boots": "ankle boots", "heels": "heeled pumps",
    "flats": "ballet flats", "sandals": "sandals", "rain boots": "rain boots", "snow boots": "snow boots",
    "watch": "wristwatch", "belt": "belt", "tie": "tie", "jewellery": "simple jewellery", "bag": "shoulder bag",
    "cap": "baseball cap", "scarf": "scarf", "beanie": "beanie", "umbrella": "folded umbrella",
}
SKIP = {"sunglasses", "umbrella", "cap", "beanie"}          # would need a face, or a lookbook leaves them out
COLOUR_WORD = {"denim": "mid-blue"}
ORDER = ["top", "dress", "outerwear", "bottom", "footwear", "accessory"]

TEXT_MODELS = ["zimage", "klein", "flux"]
EDIT_MODELS = ["klein", "qwen-image", "kontext"]
MODEL_NAME = {"zimage": "Z-Image Turbo", "klein": "FLUX.2 klein", "flux": "FLUX.1", "qwen-image": "Qwen-Image",
              "kontext": "FLUX.1 Kontext"}
GEMINI_MODELS = ["gemini-3.1-flash-image", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image",
                 "gemini-3-pro-image", "gemini-3-pro-image-preview", "gemini-2.5-flash-image-preview"]


def person_phrase(person):
    who = "a woman" if person.get("build") == "fem" else "a man"
    skin = SKIN.get(person.get("skin"), SKIN["medium"])
    body = BODY.get(person.get("body"))
    return f"{who} with {skin} skin" + (f" and a {body} build" if body and body != "average" else "")


def scene_phrase(setting, occasion, backdrop=0):
    if setting == "occasion" and occasion in PLACES:
        return f"Standing in {PLACES[occasion]}, shallow depth of field, natural light"
    return f"Seamless {BACKDROPS[backdrop % len(BACKDROPS)]} studio backdrop, soft even lighting"


def style_notes(pieces, occasion):
    by = {p["role"]: p for p in pieces}
    top, bottom = by.get("top"), by.get("bottom")
    notes = []
    sub = (top or {}).get("subcategory", "")
    collared = bool(top) and any(w in sub for w in ("shirt", "blouse", "polo")) and sub not in ("t-shirt", "sweatshirt")
    if collared and bottom and bottom["subcategory"] != "skirt":
        notes.append("the shirt is neatly tucked in, with a simple belt that suits the shoes")
    if collared and occasion not in ("work", "formal"):
        notes.append("sleeves casually rolled to just below the elbow")
    if bottom and any(w in bottom["subcategory"] for w in ("jeans", "chinos", "trousers")):
        notes.append("trousers fall straight with a slight break over the shoes")
    return notes


def describe(p):
    kind = LOOK.get(p["subcategory"], p["subcategory"] or p["role"])
    colour = COLOUR_WORD.get(p.get("colour"), p.get("colour") or "")
    if p.get("pattern") and p.get("secondary"):
        return f"{colour} and {p['secondary']} {p['pattern']} {kind}"
    if p.get("pattern"):
        return f"{colour} {p['pattern']} {kind}"
    return f"{colour} {kind}".strip()


def prompt_for(pieces, person, occasion="casual", backdrop=0, setting="studio", board_note=False):
    worn = [describe(p) for p in sorted(pieces, key=lambda p: ORDER.index(p["role"]) if p["role"] in ORDER else 9)
            if not (p["role"] == "accessory" and p["subcategory"] in SKIP)]
    notes = style_notes(pieces, occasion)
    parts = [
        f"Photorealistic full-length e-commerce fashion photo of {person_phrase(person)}, cropped at the chin so the "
        "face is not visible, standing straight facing the camera, arms relaxed at the sides.",
        "The person wears exactly the clothes shown in the reference image, same colours, patterns and cut." if board_note else "",
        f"Wearing: {', '.join(worn)}.",
        f"{', '.join(notes)}." if notes else "",
        f"{scene_phrase(setting, occasion, backdrop)}, natural fabric folds and seams, true-to-life textures, accurate "
        "proportions, realistic hands, natural skin texture, sharp focus, real person, real clothes, 50mm catalogue "
        "photography, no text, no logo.",
    ]
    return " ".join(" ".join(p for p in parts if p).split())


# ---------------------------------------------------------------- image checks

def check_image(data, content_type=""):
    """The bytes must decode as JPEG/PNG/WebP. Returns (bytes, mime)."""
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        fmt = Image.open(io.BytesIO(data)).format
    except Exception:
        raise ApiError(502, "photo_empty", "The image service didn't send back a usable photo. Try again.")
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt)
    if not mime:
        raise ApiError(502, "photo_empty", "The image service sent a format FitCheck.AI doesn't accept.")
    return data, mime


def board(images, cell=384):
    """The outfit's clothing photos side by side on white, as one JPEG."""
    tiles = []
    for data in images[:5]:
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, "white")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            tiles.append(im.convert("RGB"))
        except Exception:
            continue
    if not tiles:
        return None
    cols = min(3, len(tiles))
    rows = -(-len(tiles) // cols)
    out = Image.new("RGB", (cols * cell, rows * cell), "white")
    for i, im in enumerate(tiles):
        im.thumbnail((cell - 24, cell - 24))
        x = (i % cols) * cell + (cell - im.width) // 2
        y = (i // cols) * cell + (cell - im.height) // 2
        out.paste(im, (x, y))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------------------------------------------------------------- Pollinations (free, open source)

class Free:
    def __init__(self, cfg, key=""):
        self.cfg = cfg
        self.key = key
        self.timeout = cfg["PHOTO_TIMEOUT"]

    def _get(self, url, headers=None):
        for attempt in range(3):
            try:
                r = requests.get(url, headers=headers or {}, timeout=self.timeout)
            except requests.RequestException:
                raise ApiError(502, "photo_offline", "Couldn't reach the free image service. Try again in a minute.")
            if r.status_code in (402, 429) and attempt < 2:
                time.sleep(min(20, int(r.headers.get("Retry-After", "5") or 5)))
                continue
            if r.status_code in (401, 403):
                raise ApiError(400, "photo_bad_key", "Pollinations didn't accept that key. Check it in your profile, or remove it.")
            if r.status_code in (402, 429):
                raise ApiError(429, "photo_quota", "The free image service is busy. Wait a minute and try again.")
            if not r.ok:
                raise ApiError(502, "photo_failed", f"The free image service couldn't make the photo (error {r.status_code}). Try again.")
            return r.content
        raise ApiError(429, "photo_quota", "The free image service is busy. Wait a minute and try again.")

    def models(self):
        try:
            r = requests.get(f"{self.cfg['POLLINATIONS_GEN_URL']}/image/models", timeout=15)
            rows = r.json() if r.ok else []
            rows = rows if isinstance(rows, list) else rows.get("data") or rows.get("models") or []
            info = []
            for m in rows:
                if isinstance(m, str):
                    info.append((m, False, False))
                    continue
                mid = str(m.get("name") or m.get("id") or "").split("/")[-1]
                inputs = m.get("input_modalities") or m.get("inputModalities") or []
                paid = bool(m.get("paid_only") or m.get("paidOnly") or m.get("tier") == "paid" or m.get("premium"))
                info.append((mid, "image" in inputs, paid))
            ids = {i for i, _, paid in info if not paid}
            flagged = any(img for _, img, _ in info)
            text = [m for m in TEXT_MODELS if m in ids] or TEXT_MODELS
            edit = [m for m in EDIT_MODELS if m in ids and (not flagged or any(i == m and img for i, img, _ in info))] or EDIT_MODELS
            return text, edit
        except Exception:
            return TEXT_MODELS, EDIT_MODELS

    def make(self, prompt, prompt_board, board_jpeg, seed):
        q = {"width": "768", "height": "1024", "seed": str(seed), "nologo": "true", "private": "true",
             "safe": "true", "enhance": "false"}
        if self.key:
            text_models, edit_models = self.models()
            auth = {"Authorization": f"Bearer {self.key}"}
            if board_jpeg:
                for model in edit_models:
                    try:
                        r = requests.post(f"{self.cfg['POLLINATIONS_GEN_URL']}/v1/images/edits", headers=auth,
                                          data={"model": model, "prompt": prompt_board, "size": "768x1024", "seed": str(seed)},
                                          files={"image": ("outfit.jpg", board_jpeg, "image/jpeg")}, timeout=self.timeout)
                    except requests.RequestException:
                        continue
                    if r.status_code in (401, 403):
                        raise ApiError(400, "photo_bad_key", "Pollinations didn't accept that key.")
                    if not r.ok:
                        continue
                    try:
                        item = (r.json().get("data") or [{}])[0]
                    except ValueError:
                        continue
                    if item.get("b64_json"):
                        return base64.b64decode(item["b64_json"]), MODEL_NAME.get(model, model)
                    if item.get("url", "").startswith("https://"):
                        return self._get(item["url"]), MODEL_NAME.get(model, model)
            last = None
            for model in text_models:
                url = f"{self.cfg['POLLINATIONS_GEN_URL']}/image/{quote(prompt, safe='')}?{urlencode({**q, 'model': model})}"
                try:
                    return self._get(url, auth), MODEL_NAME.get(model, model)
                except ApiError as e:
                    if e.code == "photo_bad_key":
                        raise
                    last = e
            raise last
        # no key: the public endpoint, FLUX.1 within the free size limit
        q.update({"width": "640", "height": "864", "model": "flux"})
        url = f"{self.cfg['POLLINATIONS_IMAGE_URL']}/prompt/{quote(prompt, safe='')}?{urlencode(q)}"
        return self._get(url), MODEL_NAME["flux"]


# ---------------------------------------------------------------- Google Gemini (optional)

class Gemini:
    def __init__(self, cfg, key, model=None):
        self.cfg, self.key, self.model = cfg, key, model
        self.timeout = cfg["PHOTO_TIMEOUT"]

    def _call(self, method, path, body=None):
        try:
            r = requests.request(method, f"{self.cfg['GEMINI_URL']}/{path}", json=body,
                                 headers={"x-goog-api-key": self.key}, timeout=self.timeout)
        except requests.RequestException:
            raise ApiError(502, "photo_offline", "Couldn't reach Google's Gemini service.")
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not r.ok:
            msg = (data.get("error") or {}).get("message", "")
            if r.status_code == 400 and "api key" in msg.lower():
                raise ApiError(400, "photo_bad_key", "Google says that API key isn't valid. Check it in your profile.")
            if r.status_code in (401, 403):
                raise ApiError(400, "photo_bad_key", "That Gemini key isn't allowed to make images.")
            if r.status_code == 404:
                raise ApiError(404, "photo_no_model", "That Gemini image model isn't available for your key.")
            if r.status_code == 429:
                raise ApiError(429, "photo_quota", "Your Gemini quota is used up for now. Try again later.")
            raise ApiError(502, "photo_failed", "Gemini couldn't make the photo. Try again.")
        return data

    def connect(self):
        names = []
        data = self._call("GET", "models?pageSize=200")
        for m in data.get("models", []):
            mid = str(m.get("name", "")).replace("models/", "")
            if "image" in mid and not mid.startswith("imagen") and "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(mid)
        if not names:
            raise ApiError(404, "photo_no_model", "This key works, but no Gemini image model is available to it.")
        rank = lambda i: GEMINI_MODELS.index(i) if i in GEMINI_MODELS else 100  # noqa: E731
        return sorted(names, key=lambda i: (rank(i), i))

    def make(self, pieces, refs, person, occasion, backdrop, setting):
        lines, parts, n = [], [], 0
        for p, img in zip(pieces, refs):
            what = f"{p.get('colour') or ''} {p['subcategory']}".strip()
            if img and n < 5:
                n += 1
                lines.append(f"- Reference image {n} is the {ROLE_WORD.get(p['role'], p['role'])}: {what}. Reproduce it "
                             f"exactly: same colour ({p['hex']}), pattern, fabric, collar, buttons and cut.")
                parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(img).decode()}})
            else:
                lines.append(f"- {ROLE_WORD.get(p['role'], p['role'])}: {what}, colour {p['hex']}.")
        notes = style_notes(pieces, occasion)
        prompt = "\n".join(x for x in [
            f"Photorealistic e-commerce fashion photograph of {person_phrase(person)} wearing exactly this outfit:",
            *lines,
            f"Styling: {'; '.join(notes)}." if notes else "",
            "Framing: vertical full-length shot, cropped at the chin so the face is not shown, from the neck down to "
            "the shoes, centred, standing straight facing the camera, arms relaxed at the sides.",
            f"Setting: {scene_phrase(setting, occasion, backdrop)}.",
            "The clothes fit the body naturally, with real fabric folds and drape, true to the reference colours. "
            "A real person, real clothes, shot on a full-frame camera with a 50mm lens.",
            "Do not add any garment, accessory, logo, text or watermark that isn't listed. Do not show the face. "
            "No collage: a single photo.",
        ] if x)
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}, *parts]}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "3:4"}}}
        data = self._call("POST", f"models/{quote(self.model, safe='')}:generateContent", body)
        cand = (data.get("candidates") or [{}])[0]
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data") and not part.get("thought"):
                return base64.b64decode(inline["data"]), self.model
        why = (data.get("promptFeedback") or {}).get("blockReason") or cand.get("finishReason") or ""
        if any(w in why for w in ("SAFETY", "BLOCK", "PROHIBITED")):
            raise ApiError(422, "photo_declined", "Gemini declined to make this photo. Try again or try another outfit.")
        raise ApiError(502, "photo_empty", "Gemini didn't return a photo. Try again.")


def new_seed():
    return random.randrange(1, 2**31)  # nosec B311: picks a picture variation, not security
