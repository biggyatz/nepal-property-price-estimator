"""Clean raw property listings (99aana, Hamrobazar, Basobaas) into one table: property.csv.

Inputs (any that exist):
  raw_99aana_v2.jsonl            99aana pages (crawl_99aana.py); if absent, the 99aana rows of
                                 property_listings.csv are re-used and only their places re-parsed
  raw_hamrobazar_re_details.jsonl Hamrobazar detail pages (crawl_hamrobazar_details.js)
  raw_basobaas.jsonl             Basobaas pages (crawl_basobaas.py)
  property_listings.csv          previous cleaned table; rows whose raw file is gone are kept
"""
import json, os, re
from collections import Counter
import pandas as pd
from nepal_units import area_sqft, npr, first_float, strip_phones, SQFT
from places import split_address, locality_from_text, district_from_words, find_town, TERAI

AANA = SQFT["aana"]
DEFAULT_SCRAPED = pd.Timestamp("2026-10-09")
COLS = ["source", "url", "title", "type", "locality", "city", "district", "address", "price_text", "area_text",
        "floors", "road_ft", "rooms", "bathrooms", "listed"]

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
    if r.get("purpose") != "Sale" or r.get("category") not in ("House", "Land"):
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
    try:
        listed = str(pd.to_datetime(r.get("updated"), format="%b %d, %Y").date())
    except (TypeError, ValueError):
        listed = ""
    return dict(source="basobaas.com", url=r["url"], title=title, type=typ, address=r.get("address"), price_text=price_text,
                area_text=area, floors=r.get("floors") or None, road_ft=first_float(r.get("Road Access In Feet")),
                rooms=r.get("bedroom") or None, bathrooms=r.get("bathroom") or None, listed=listed)

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
        if x["locality"] and x["district"]:
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
    return df.sort_values(["source", "listed"]).reset_index(drop=True)

def load_jsonl(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []

if __name__ == "__main__":
    rows, have_raw = [], set()
    for r in load_jsonl("raw_99aana_v2.jsonl"):
        rows.append(from_99aana(r)); have_raw.add("99aana.com")
    for r in load_jsonl("raw_hamrobazar_re_details.jsonl"):
        if r.get("title"):
            rows.append(from_hamrobazar(r))
    for r in load_jsonl("raw_basobaas.jsonl"):
        x = from_basobaas(r)
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
