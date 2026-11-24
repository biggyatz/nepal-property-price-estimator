"""Coordinates for the places in property.csv, cached in geo_places.json.

    python geocode.py [--max 300]

Looks up each district, town and locality once with OpenStreetMap's Nominatim service
(at most one request per second, as its usage policy asks) and keeps the answer, so
later runs only query places that are new. Only place names are sent.
Results outside Nepal, or a locality far from its district, are stored as null.
"""
import argparse, json, math, os, sys, time, urllib.parse, urllib.request
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "geo_places.json")
UA = "nepal-property-price-estimator/1.0 (+https://github.com/biggyatz/nepal-property-price-estimator)"
NEPAL = (26.3, 30.5, 80.0, 88.3)

def in_nepal(lat, lon):
    return NEPAL[0] <= lat <= NEPAL[1] and NEPAL[2] <= lon <= NEPAL[3]

def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    x = math.radians(lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    return 6371 * math.hypot(x, math.radians(la2 - la1))

def nominatim(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "np"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    time.sleep(2.0)
    if not res:
        return None
    lat, lon = float(res[0]["lat"]), float(res[0]["lon"])
    return [round(lat, 5), round(lon, 5)] if in_nepal(lat, lon) else None

def load():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}

def key(name, district):
    return f"{name or ''}|{district}"

def lookup(cache, district, city=None, locality=None):
    """Best coordinates for a listing's place, and how precise they are."""
    for name, level in ((locality, "locality"), (city, "town"), (None, "district")):
        if name is None and level != "district":
            continue
        p = cache.get(key(name, district))
        if p:
            return p, level
    return None, None

def valid_point(cache, district, lat, lon, max_km=40):
    """A listing's own map pin, if it is in Nepal and near its district."""
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon) or not in_nepal(lat, lon):
        return False
    c = cache.get(key(None, district))
    return c is None or km(c, (lat, lon)) <= max_km

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "property.csv"))
    ap.add_argument("--max", type=int, default=300, help="most new places to look up in one run")
    a = ap.parse_args()
    df = pd.read_csv(a.csv)
    df = df[df.district.notna()]
    cache = load()
    todo = []
    for d in sorted(df.district.unique()):
        todo.append((key(None, d), f"{d} District, Nepal", d, None))
    for col in ("city", "locality"):
        for (name, d), n in df.groupby([col, "district"]).size().items():
            if n >= 2:
                todo.append((key(name, d), f"{name}, {d}, Nepal", d, name))
    todo = [t for t in todo if t[0] not in cache][:a.max]
    print("places to geocode:", len(todo), file=sys.stderr)
    for k, q, d, name in todo:
        try:
            p = nominatim(q)
        except Exception as e:
            print("ERR", q, e, file=sys.stderr)
            if "429" in str(e) or "629" in str(e):
                print("Nominatim asks us to slow down; stopping until the next run", file=sys.stderr); break
            continue
        centre = cache.get(key(None, d))
        if p and name and centre and km(centre, p) > 60:
            p = None                           # same name elsewhere in Nepal
        cache[k] = p
    json.dump(dict(sorted(cache.items())), open(CACHE, "w"), ensure_ascii=False, indent=0)
    print("cached places:", len(cache), "with coordinates:", sum(v is not None for v in cache.values()), file=sys.stderr)
