"""Clean raw property listings (99aana, Hamrobazar, Basobaas) into one table: property.csv.

Inputs (any that exist):
  raw/99aana.jsonl               99aana pages (crawl_99aana.py); if absent, the 99aana rows of
                                 property_listings.csv are re-used and only their places re-parsed
  raw/hamrobazaar_details.jsonl  Hamrobazar detail pages (crawl_hamrobazar_details.js)
  raw/basobaas.jsonl, raw/npb.jsonl, raw/gharghaderi.jsonl, raw/gharjagganepal.jsonl
                                 Basobaas, Nepal Property Bazaar, Gharghaderi, Ghar Jagga Nepal pages (crawl_sites.py)
  raw/nepalhomes.jsonl, raw/jaggaghar.jsonl
                                 Nepal Homes search pages and Jagga Ghar's listing API (crawl_sites.py)
  property_listings.csv          previous cleaned table; rows whose raw page is gone (sold,
                                 withdrawn, expired) are kept as historical asking prices
"""
import json, os, re
from collections import Counter
import pandas as pd
from nepal_units import area_sqft, npr, first_float, strip_phones, SQFT
from places import split_address, locality_from_text, district_from_words, find_town, TERAI

AANA = SQFT["aana"]
DEFAULT_SCRAPED = pd.Timestamp("2026-10-09")
COLS = ["source", "url", "title", "type", "locality", "city", "district", "address", "price_text", "area_text",
        "floors", "road_ft", "rooms", "bathrooms", "listed", "lat", "lon"]

def from_99aana(r):
    h = r.get("header") or []
    kv = {}
    hl = r.get("highlights") or []
    for i, l in enumerate(hl):
        key = l.rstrip(":").strip()
        if i + 1 < len(hl) and key in ("Type", "Price", "Address", "Total Land Area", "Area", "Land Area", "Road", "Floor", "Floors",
                                       "Total no. of rooms", "Total no. of Bathroom", "Built up Area", "Facing", "Road Type", "Built Year"):
            kv[key] = hl[i + 1].lstrip(":–- \xa0").strip()
    title = r.get("title") or ""
    typ = "Land" if title.lower().startswith("land") else "House"
    addr = h[3] if len(h) > 3 else kv.get("Address")
    price_text = h[4] if len(h) > 4 else kv.get("Price")
    area_text = kv.get("Total Land Area") or kv.get("Area") or kv.get("Land Area")
    if not area_text and "sq m" in h:
        k = h.index("sq m"); area_text = h[k + 1] if k + 1 < len(h) else None
    rooms = first_float(h[h.index("Rooms") + 1]) if "Rooms" in h and h.index("Rooms") + 1 < len(h) else first_float(kv.get("Total no. of rooms"))
    baths = first_float(h[h.index("Bathrooms") + 1]) if "Bathrooms" in h and h.index("Bathrooms") + 1 < len(h) else first_float(kv.get("Total no. of Bathroom"))
    return dict(source="99aana.com", url=r["url"], title=title, type=typ, address=addr, price_text=price_text, area_text=area_text,
                floors=first_float(kv.get("Floor") or kv.get("Floors")), road_ft=first_float(kv.get("Road")), rooms=rooms,
                bathrooms=baths, listed=(r.get("published") or "")[:10])

def posted_date(text, scraped):
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month|year)", text or "")
    if not m:
        return scraped
    n, u = int(m.group(1)), m.group(2)
    return scraped - pd.Timedelta(days={"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[u] * n)

def from_hamrobazar(r):
    title = r.get("title") or ""
    scraped = pd.Timestamp(r["scraped"][:10]) if r.get("scraped") else DEFAULT_SCRAPED
    return dict(source="hamrobazaar.com", url=r["url"], title=title, type="Land" if "/for-sale-land/" in r["url"] else "House",
                address=None, price_text=r.get("price"), area_text=r.get("area_text"),
                spec_area=(r.get("specs") or {}).get("Land Size (Aana/Dhur)"), floors=first_float(r.get("storeys")),
                road_ft=first_float(r.get("road_ft")), rooms=None, bathrooms=None,
                listed=str(posted_date(r.get("posted"), scraped).date()))

AREA_IN_TEXT = re.compile(r"(\d+(?:\.\d+)?\s*(?:ropani|aana|anna|ana|paisa|dam|daam|dhur|kattha|katha|kathha|bigha)\b(?:\s*\d+(?:\.\d+)?\s*(?:aana|anna|ana|paisa|dam|daam|dhur|kattha|katha))*)", re.I)

def from_basobaas(r):
    if r.get("gone") or r.get("purpose") != "Sale" or r.get("category") not in ("House", "Land"):
        return None
    title = r.get("title") or ""
    area = (r.get("Land Area") or "").split("/")[0].strip()
    area = re.sub(r"\b(daam)\b", "dam", re.sub(r"\b(kathha)\b", "kattha", area, flags=re.I), flags=re.I)
    if not area_sqft(area):
        m = AREA_IN_TEXT.search(title)
        area = m.group(1) if m else (area if re.fullmatch(r"\d+(?:\.\d+)?", area) else None)  # bare number: unit decided later
    unit = (r.get("price_unit") or "")
    price_text = r.get("price") or ""
    if unit.lower().startswith("per") and "month" not in unit.lower():
        price_text += " " + unit
    elif "month" in unit.lower():
        return None
    typ = r["category"]
    if typ == "Land" and re.search(r"\bhouse\b", title, re.I) and not re.search(r"\bland\b", title, re.I):
        typ = "House"
    listed = _date(r.get("updated"))
    return dict(source="basobaas.com", url=r["url"], title=title, type=typ, address=r.get("address"), price_text=price_text,
                area_text=area, floors=r.get("floors") or None, road_ft=first_float(r.get("Road Access In Feet")),
                rooms=r.get("bedroom") or None, bathrooms=r.get("bathroom") or None, listed=listed)

def _date(text, fmts=("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d")):
    if not text:
        return ""
    for f in fmts:
        try:
            d = pd.to_datetime(text, format=f)
            if not pd.isna(d):
                return str(d.date())
        except (TypeError, ValueError):
            pass
    return ""

def from_npb(r):
    """nepalpropertybazaar.com (Houzez theme): structured price / area / city / area fields + map pin."""
    if r.get("gone") or "sale" not in (r.get("property_status") or "").lower():
        return None
    typ = (r.get("property_type") or "").split(",")[0].strip()
    if typ not in ("House", "Land"):
        return None
    title = r.get("title") or ""
    price = (r.get("price") or "").replace("Rs", "Rs ")
    area = r.get("land_area") or r.get("land_area_desc") or r.get("property_size")
    if area and not area_sqft(area):
        m = AREA_IN_TEXT.search(title)
        area = m.group(1) if m else area
    address = ", ".join(x for x in (r.get("area"), r.get("city")) if x) or r.get("address")
    return dict(source="nepalpropertybazaar.com", url=r["url"], title=title, type=typ, address=address, price_text=price,
                area_text=area, floors=first_float(r.get("floors") or r.get("floor")) or r.get("storeys"), road_ft=first_float(r.get("road_access") or r.get("road_size")) or r.get("road_ft"),
                rooms=first_float(r.get("bedrooms") or r.get("bedroom")), bathrooms=first_float(r.get("bathrooms") or r.get("bathroom")),
                listed=(r.get("published") or _date(r.get("updated")) or r.get("lastmod") or "")[:10], lat=r.get("lat"), lon=r.get("lon"))

# Gharghaderi stores road width as a band, e.g. "ThirteenToTwentyFeet": use the lower edge.
GG_ROAD = {"LessThanEightFeet": 6.0, "EightToTwelveFeet": 8.0, "ThirteenToTwentyFeet": 13.0, "TwentyToThirtyFeet": 20.0,
           "MoreThanThirtyFeet": 30.0, "ThirtyFeetAndAbove": 30.0}

def from_gharghaderi(r):
    """gharghaderi.com: district / municipality / VDC / tole fields, price with optional 'Per Aana'."""
    if r.get("gone") or (r.get("status") or "Active").lower() != "active":
        return None
    kind = r.get("kind", "")
    typ = "Land" if kind.startswith("land") else "House" if kind.startswith("house") else None
    if not typ or not r.get("price"):
        return None
    address = ", ".join(x for x in (r.get("tole"), r.get("muncipality") or r.get("municipality"), r.get("vdc"), r.get("district")) if x)
    price = "Rs " + r["price"] + (" " + r["price_unit"] if r.get("price_unit") else "")
    return dict(source="gharghaderi.com", url=r["url"], title=r.get("title") or "", type=typ, address=address, price_text=price,
                area_text=r.get("land_area"), floors=first_float(r.get("floor") or r.get("floors") or r.get("no_of_floor")),
                road_ft=first_float(r.get("road_size")) or GG_ROAD.get(r.get("road_size")), rooms=first_float(r.get("bedroom")), bathrooms=first_float(r.get("bathroom")),
                listed=_date(r.get("date")) or r.get("lastmod") or "")

def from_gharjagganepal(r):
    """gharjagganepal.com (GeoDirectory): address / municipality / district fields + map pin."""
    if r.get("gone") or "sale" not in (r.get("property_status") or "").lower():
        return None
    typ = (r.get("property_type") or "").strip()
    if typ not in ("House", "Land"):
        return None
    title = r.get("title") or ""
    area = r.get("land_area")
    if not area_sqft(area):
        m = AREA_IN_TEXT.search(title)
        area = m.group(1) if m else None
    muni = re.sub(r"\b(Maha|Upa-?Maha)?nagarpalika\b|\bGaunpalika\b", "", r.get("municipality") or "", flags=re.I).strip()
    address = ", ".join(x for x in (r.get("address"), muni, r.get("district")) if x)
    return dict(source="gharjagganepal.com", url=r["url"], title=title, type=typ, address=address,
                price_text=(r.get("price") or "").replace("Rs", "Rs "), area_text=area, floors=r.get("storeys"),
                road_ft=r.get("road_ft"), rooms=first_float(r.get("bedrooms")), bathrooms=first_float(r.get("bathrooms")),
                listed=_date(r.get("published")) or r.get("lastmod") or "", lat=r.get("lat"), lon=r.get("lon"))

def _bkd(text):
    """'1-2-5' in the Terai is bigha-kattha-dhur."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*", text or "")
    return f"{m.group(1)} bigha {m.group(2)} kattha {m.group(3)} dhur" if m else text

def from_nepalhomes(r):
    """nepalhomes.com search results: district / municipality / area fields, area as ropani-aana-paisa-dam."""
    if r.get("purpose") != "Sale" or r.get("category") not in ("House", "Land") or r.get("is_project") or not r.get("price"):
        return None
    label = (r.get("price_label") or "").lower()
    if "month" in label:
        return None
    price = f"Rs {r['price']}" + (" " + label if label.startswith("per") else "")
    road = first_float(str(r.get("road_ft") or ""))
    if road and (r.get("road_unit") or "").lower().startswith("met"):
        road = round(road * 3.281, 1)
    muni = re.sub(r"\b(Sub-?)?Metropolitan( City)?\b|\bMunicipality\b|\bRural\b", "", r.get("municipality") or "", flags=re.I).strip()
    address = ", ".join(x for x in (r.get("area"), muni, r.get("district")) if x)
    return dict(source="nepalhomes.com", url=r["url"], title=r.get("title") or "", type=r["category"], address=address,
                price_text=price, area_text=_bkd(r.get("total_area")), floors=r.get("floors") if r["category"] == "House" else None,
                road_ft=road, rooms=None, bathrooms=None, listed=r.get("published") or "")

def from_jaggaghar(r):
    """jaggaghar.com (namaestate API): location text, land area with unit, total or per-unit price."""
    if r.get("listing_type") != "sell" or r.get("category") not in ("House", "Land") or r.get("status") != "published":
        return None
    price = first_float(str(r.get("price") or ""))
    if not price:
        return None
    ps = (r.get("pricing_structure") or "total").lower()
    unit = r.get("area_unit") or "aana"
    price_text = f"Rs {price:.0f}" + ("" if ps == "total" else f" per {unit}")
    area = r.get("land_area") or ""
    if area and not area_sqft(area):
        area = f"{area} {unit}" if re.fullmatch(r"[\d.]+", area.strip()) and unit in ("aana", "ropani", "dhur", "kattha", "bigha") else None
    if not area:
        m = AREA_IN_TEXT.search(r.get("title") or "")
        area = m.group(1) if m else None
    road = first_float(str(r.get("road_length") or ""))
    if road and (r.get("road_unit") or "").lower().startswith("met"):
        road = round(road * 3.281, 1)
    floors = first_float(str(r.get("floors") or "")) if r["category"] == "House" else None
    return dict(source="jaggaghar.com", url=r["url"], title=r.get("title") or "", type=r["category"], address=r.get("location"),
                price_text=price_text, area_text=area, floors=floors, road_ft=road, rooms=None, bathrooms=None,
                listed=r.get("published") or "", lat=first_float(str(r.get("lat") or "")) or None, lon=first_float(str(r.get("lon") or "")) or None)

def merge_spellings(rows, cutoff=0.9):
    """Map near-identical locality spellings within a district onto the most common one
    (e.g. 'Bhiasepati' -> 'Bhaisepati', 'Budanilkantha' -> 'Budhanilkantha')."""
    import difflib
    by_d = {}
    for x in rows:
        if x["locality"]:
            by_d.setdefault(x["district"], Counter())[x["locality"]] += 1
    distinct = {frozenset({"Narayanthan", "Narayantar"}), frozenset({"Dhaneshwor", "Baneshwor"})}
    canon = {}
    for d, cnt in by_d.items():
        kept = []
        for n, _ in cnt.most_common():
            key = n.lower().replace(" ", "").replace("h", "")
            match = next((k for k in kept if frozenset({n, k}) not in distinct and difflib.SequenceMatcher(None, key, k.lower().replace(" ", "").replace("h", "")).ratio() >= cutoff), None)
            canon[(d, n)] = match or n
            if not match:
                kept.append(n)
    for x in rows:
        if x["locality"]:
            x["locality"] = canon.get((x["district"], x["locality"]), x["locality"])
    return {k: v for k, v in canon.items() if k[1] != v}

def place(rows):
    """Assign locality / city / district. Structured addresses (99aana, Basobaas) first, then
    learn a locality vocabulary from them for free-text titles (Hamrobazar)."""
    for x in rows:
        if x["source"] != "hamrobazaar.com":
            x["locality"], x["city"], x["district"] = split_address(x["address"], x["title"])
    known = {}
    for x in rows:
        if x.get("locality") and x.get("district"):
            known.setdefault(x["locality"].lower(), Counter())[x["district"]] += 1
    known = {k: c.most_common(1)[0][0] for k, c in known.items() if c.most_common(1)[0][1] >= 2}
    vocab = {k: (k.title(), d) for k, d in known.items()}
    for x in rows:
        if x["source"] != "hamrobazaar.com" and not x["district"]:
            x["locality"], x["city"], x["district"] = split_address(x["address"], x["title"], known)
        if x["source"] != "hamrobazaar.com" and not x["district"]:
            text = f'{x["address"] or ""} , {x["title"]}'
            loc, dist = locality_from_text(text, vocab)
            x["district"] = dist or district_from_words(text, known)
    for x in rows:
        if x["source"] == "hamrobazaar.com":
            loc, dist = locality_from_text(x["title"], vocab)
            town = find_town(x["title"])
            _, _, d2 = split_address(None, x["title"])
            x["district"] = d2 or dist
            x["locality"] = loc if loc and dist == x["district"] else (town[0] if town and town[1] == x["district"] else None)
            x["city"] = town[0] if town and town[1] == x["district"] and x["district"] not in ("Kathmandu", "Lalitpur", "Bhaktapur") else None
    # Outside the Valley a locality is often just the town itself.
    for x in rows:
        if x["city"] and not x["locality"]:
            x["locality"] = x["city"]

def finalize(rows):
    place(rows)
    merged = merge_spellings(rows)
    print("merged spellings:", len(merged))
    # A rare locality (a tole) gives the model nothing; if the title or address also names a
    # well-covered locality of the same district ("Shital Height, Imadol"), use that instead.
    cnt = Counter((x["district"], x["locality"]) for x in rows if x["locality"])
    common = {}
    for (d, l), n in cnt.items():
        if n >= 6 and d:
            common.setdefault(d, {})[l.lower()] = (l, d)
    for x in rows:
        if x["district"] in common and cnt.get((x["district"], x["locality"]), 0) < 4:
            loc, _ = locality_from_text(f'{x["address"] or ""} , {x["title"]}', common[x["district"]])
            if loc:
                x["locality"] = loc
    out = []
    for x in rows:
        area_text = x["area_text"]
        spec = x.pop("spec_area", None)
        if not area_text and spec:
            area_text = f"{spec} {'dhur' if x['district'] in TERAI else 'aana'}"
        if area_text and re.fullmatch(r"\d+(?:\.\d+)?", str(area_text).strip()):
            area_text = f"{area_text} {'dhur' if x['district'] in TERAI else 'aana'}"
        x["area_text"] = area_text
        sqft = area_sqft(area_text)
        price, per = npr(x["price_text"])
        if price and price < 10000:          # shorthand in lakh: "270" -> 270 lakh
            price *= 1e5
        if price and per:
            if not sqft: continue
            price = price * sqft / SQFT[per]
        if not (price and sqft):
            continue
        aana = sqft / AANA
        x.update(price_npr=round(price), area_aana=round(aana, 3), price_per_aana=round(price / aana), title=strip_phones(x["title"]))
        out.append(x)
    df = pd.DataFrame(out)
    # The same property is often re-posted on a site under a new URL: keep the newest copy.
    df = df.sort_values("listed", ascending=False)
    df = df.drop_duplicates(subset=["url"]).drop_duplicates(subset=["source", "type", "district", "locality", "price_npr", "area_aana"])
    # Agents cross-post the same property to several portals: exact same place, price and area.
    df = df.drop_duplicates(subset=["type", "district", "locality", "price_npr", "area_aana"])
    return df.sort_values(["source", "listed"]).reset_index(drop=True)

def load_jsonl(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []

if __name__ == "__main__":
    rows, have_raw = [], set()
    for r in load_jsonl("raw/99aana.jsonl"):
        rows.append(from_99aana(r)); have_raw.add("99aana.com")
    for r in load_jsonl("raw/hamrobazaar_details.jsonl"):
        if r.get("title"):
            rows.append(from_hamrobazar(r))
    for path, fn in (("raw/basobaas.jsonl", from_basobaas), ("raw/npb.jsonl", from_npb), ("raw/gharghaderi.jsonl", from_gharghaderi),
                     ("raw/gharjagganepal.jsonl", from_gharjagganepal), ("raw/nepalhomes.jsonl", from_nepalhomes),
                     ("raw/jaggaghar.jsonl", from_jaggaghar)):
        for r in load_jsonl(path):
            x = fn(r)
            if x:
                rows.append(x)
    # Keep earlier cleaned rows whose raw pages are no longer on disk (e.g. 99aana, which
    # has stopped adding listings, and older Hamrobazar posts that have since expired).
    seen = {x["url"] for x in rows}
    if os.path.exists("property_listings.csv"):
        old = pd.read_csv("property_listings.csv", dtype=str, keep_default_na=False)
        for r in old.to_dict("records"):
            if r["url"] in seen or r["source"] in have_raw:
                continue
            x = {c: (r.get(c) or None) for c in COLS}
            x["address"] = x["address"] if x["address"] and not x["address"].startswith("Rs") else None
            x["floors"], x["road_ft"] = first_float(x["floors"]), first_float(x["road_ft"])
            x["lat"], x["lon"] = first_float(x["lat"]), first_float(x["lon"])
            if x["source"] == "hamrobazaar.com":    # area/price were already parsed
                x["area_text"] = x["area_text"] or (f"{float(r['area_aana'])} aana" if r.get("area_aana") else None)
            rows.append(x)
    df = finalize(rows)
    print(len(rows), "raw ->", len(df), "usable")
    print(df.source.value_counts().to_string())
    print(df.district.value_counts(dropna=False).head(30).to_string())
    print(df.groupby(["district", "type"]).price_per_aana.median().round(-3).head(30))
    df.to_csv("property.csv", index=False)
    print("wrote property.csv", len(df))
