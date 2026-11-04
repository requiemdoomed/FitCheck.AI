"""
Browser-only modules run under Node: Smart buys and the weather mapping.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def node(script):
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_smart_buys_rules():
    res = node(f"""
      import {{ suggestBuys, BASICS }} from "{(ROOT / 'assets/js/engine/shop.js').as_posix()}";
      import fs from "fs";
      const cat = JSON.parse(fs.readFileSync("assets/images/garments/catalog.json"));
      const items = cat.map((g, i) => ({{ id: i + 1, name: g.name, category: g.category, subcategory: g.subcategory,
        main_color_hex: g.main_color, style: g.style, occasions: g.occasions, seasons: g.seasons }}));
      const owned = [{{ id: 1, name: "white tee", category: "top", subcategory: "t-shirt", main_color_hex: "#f5f5f2",
        style: "minimalist", occasions: ["casual"], seasons: ["summer"] }}];
      const mk = (w, p) => suggestBuys(w, p).map((s) => ({{ key: s.basic.key, cat: s.basic.category, price: s.price,
        unlocks: s.unlocks, n: s.best.items.length, ids: s.best.items.map((x) => x.id), score: s.score }}));
      console.log(JSON.stringify({{
        demo: mk(items, {{ budget: "budget" }}), mid: mk(items, {{ budget: "mid" }}),
        empty: mk([], {{}}), owned: mk(owned, {{}}), avoid: mk(items, {{ avoided_colors: ["black"] }}),
        prices: BASICS.map((b) => b.price),
        ids: items.map((x) => x.id),
      }}));
    """)
    for key in ("demo", "mid", "empty", "owned", "avoid"):
        lst = res[key]
        assert 1 <= len(lst) <= 8
        cats = [s["cat"] for s in lst]
        assert all(cats.count(c) <= 2 for c in cats)
        assert lst == sorted(lst, key=lambda s: -s["score"])
        for s in lst:
            assert s["n"] >= 2                        # always pictured as an outfit
            assert all(isinstance(i, int) or str(i).startswith("shop:") for i in s["ids"])
    assert "white-tee" not in [s["key"] for s in res["owned"]]           # already owned
    assert not any(k.startswith("black") for k in [s["key"] for s in res["avoid"]])
    assert all(s["unlocks"] > 0 for s in res["demo"])
    valid = set(res["ids"])
    assert all(i in valid for s in res["demo"] for i in s["ids"] if isinstance(i, int))
    # budget tier is cheaper than mid for every basic
    low = lambda r: int(r.split("–")[0].lstrip("$"))
    assert all(low(a) < low(b) for a, b in res["prices"])
    assert all(low(a) <= 45 for a, _ in res["prices"])                     # "affordable"


def test_weather_codes_map_to_the_form_choices():
    res = node(f"""
      import {{ weatherWord }} from "{(ROOT / 'assets/js/local/weather.js').as_posix()}";
      console.log(JSON.stringify([0, 2, 3, 45, 51, 63, 65, 71, 75, 80, 95].map((c) => weatherWord(c, 5)).concat([weatherWord(0, 50)])));
    """)
    assert set(res) <= {"sunny", "cloudy", "rainy", "snowy", "windy"}
    assert res[0] == "sunny" and res[5] == "rainy" and res[7] == "snowy" and res[-1] == "windy"
