"""Incremental, polite crawler for Nepali property portals that publish sitemaps.

    python crawl_sites.py basobaas npb gharjagganepal gharghaderi nepalhomes jaggaghar [--budget-min 40] [--max 0]

For each site the property sitemap is read, and only pages that are new, or whose
sitemap <lastmod> changed since the last visit, are fetched. Each visit appends one
record to raw/<site>.jsonl, so the newest record per URL is the current state and the
file doubles as the crawler's memory between runs (it is committed with the repo).

Only property attributes are kept: type, title, address/place, price, land area, road,
floors, rooms, listing dates and (where the site publishes them) map coordinates.
Seller names, phone numbers, e-mails and free-text descriptions are never stored.
robots.txt of all four sites allows these pages (checked November 2026).
"""
import argparse, html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date

UA = "Mozilla/5.0 (compatible; nepal-property-price-estimator; +https://github.com/biggyatz/nepal-property-price-estimator)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")
PHONE = re.compile(r"(\+?977[-\s]?)?\b9[678]\d[-\s]?\d{3}[-\s]?\d{4}\b")

class Challenged(Exception):
    """The site answered with an anti-bot "please wait" page: we are going too fast."""

def fetch(url, timeout=60, tries=3):
    """GET a page. If the site shows its rate-limit challenge instead, back off and retry;
    the challenge is never solved or bypassed."""
    for k in range(tries):
        req = urllib.request.Request(urllib.parse.quote(url, safe=":/?&=%#+,;@!$'()*~"), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final, page = r.geturl(), r.read().decode("utf-8", "ignore")
        if not ("window.location.reload" in page[:3000] and len(page) < 30000):
            return final, page
        time.sleep(60 * (k + 1))
    raise Challenged(url)

def lines_of(page):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", s)).split("\n") if l.strip()]

def sitemap_urls(index_url, keep):
    """{url: lastmod} for every URL matching `keep` in a sitemap or sitemap index."""
    out = {}
    for k in range(3):
        _, s = fetch(index_url)
        time.sleep(2)
        if "<urlset" in s or "<sitemapindex" in s:
            break
        time.sleep(60 * (k + 1))          # not a sitemap: the site's "please wait" page; back off
    else:
        raise Challenged(index_url)
    if "<sitemapindex" in s:
        subs = [x for x in re.findall(r"<loc>\s*(?:<!\[CDATA\[)?([^<\]\s]+)", s)
                if re.search(r"propert|land|house|post-sitemap|sitemap\d*\.xml", x) and "page-sitemap" not in x]
        for sub in subs:
            try:
                out.update(sitemap_urls(sub, keep)); time.sleep(1)
            except Challenged:
                # Keep what was read (the index lists the newest files first); the rest next run.
                print(f"sitemap {sub} rate-limited; continuing with {len(out)} URLs", file=sys.stderr)
                if not out:
                    raise
                break
        return out
    for blk in re.findall(r"<url>.*?</url>", s, re.S):
        loc = re.search(r"<loc>\s*(?:<!\[CDATA\[)?([^<\]\s]+)", blk)
        mod = re.search(r"<lastmod>\s*(?:<!\[CDATA\[)?([^<\]\s]+)", blk)
        if loc and keep(loc.group(1)):
            out[html.unescape(loc.group(1))] = mod.group(1)[:10] if mod else ""
    return out

def clean(s):
    return PHONE.sub("", s or "").strip(" -,:|") or None

def scrub(obj):
    """Remove phone numbers from every string in a record (keys included), except the source URL."""
    if isinstance(obj, dict):
        return {(scrub(k) if isinstance(k, str) else k): (v if k == "url" else scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return PHONE.sub("", obj).strip() if isinstance(obj, str) else obj

# ---------------------------------------------------------------- basobaas.com
BB_KEYS = ("Land Area", "Road Access In Feet", "Road Type", "Built Year", "Built Up Area", "Property Face", "Total Floors")

def parse_basobaas(url, final, page):
    if "/property/" not in final:          # sold / withdrawn: redirects to the search page
        return {"gone": True}
    L = lines_of(page)
    rec = {}
    try:
        k = L.index("Like")                # "... <category> <Sale|Rent> Like Share <title> <address> ..."
    except ValueError:
        return {"gone": True}
    rec["category"], rec["purpose"] = L[k - 2], L[k - 1]
    rec["title"], rec["address"] = clean(L[k + 2]), clean(L[k + 3])
    head = L[k + 3:k + 40]
    for x in head:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s+(Bedroom|Bathroom|Floors)", x)
        if m:
            rec[m.group(2).lower()] = float(m.group(1))
    pi = next((i for i, x in enumerate(head) if x.startswith("Rs.")), None)
    if pi is not None:
        rec["price"] = head[pi]
        nxt = head[pi + 1] if pi + 1 < len(head) else ""
        rec["price_unit"] = nxt if nxt.lower().startswith("per") else None
    if "Last updated:" in head:
        rec["updated"] = head[head.index("Last updated:") + 1]
    if "Overview" in L:
        o = len(L) - 1 - L[::-1].index("Overview")
        for i in range(o + 1, min(o + 40, len(L) - 1)):
            if L[i] == "Description":
                break
            if L[i] in BB_KEYS:
                rec[L[i]] = L[i + 1]
    return rec

# ---------------------------------------------------- nepalpropertybazaar.com (Houzez)
NPB_KEYS = {"Price", "Land Area", "Property Size", "Property Type", "Property Status", "Bedroom", "Bedrooms",
            "Bathroom", "Bathrooms", "Floors", "Floor", "Road Access", "Road Size", "Year Built", "Built Year", "Facing"}

def parse_npb(url, final, page):
    if "/property/" not in final:
        return {"gone": True}
    L = lines_of(page)
    rec = {}
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    rec["title"] = clean(html.unescape(m.group(1)).replace(" - Nepal Property Bazaar", "").strip()) if m else None
    if "Details" in L:
        d = L.index("Details")
        if d + 1 < len(L) and L[d + 1].startswith("Updated on"):
            rec["updated"] = L[d + 1].replace("Updated on", "").split(" at ")[0].strip()
        for i in range(d + 1, min(d + 40, len(L) - 1)):
            if L[i] in ("Features", "Address", "Mortgage Calculator"):
                break
            if L[i] in NPB_KEYS:
                rec[L[i].lower().replace(" ", "_")] = L[i + 1]
    for key in ("Address:", "City:", "Area:", "State/county:", "Zip/Postal Code:"):
        if key in L:
            rec[key.rstrip(":").lower().split("/")[0]] = clean(L[L.index(key) + 1])
    m = re.search(r"latitude&quot;:&quot;(-?[\d.]+)&quot;,&quot;longitude&quot;:&quot;(-?[\d.]+)", page)
    if m:
        rec["lat"], rec["lon"] = round(float(m.group(1)), 5), round(float(m.group(2)), 5)
    m = re.search(r'"datePublished":"([^"]+)"', page)
    rec["published"] = m.group(1)[:10] if m else None
    # Road width and floors are often only in the description; keep the numbers, not the text.
    desc = " ".join(L[L.index("Description") + 1:L.index("Details")]) if "Description" in L and "Details" in L else ""
    m = re.search(r"(\d{1,2})\s*(?:ft|feet|fit)\b[^.#]{0,25}?(?:road|bato|access|pitch|black)", desc, re.I) or \
        re.search(r"road[^.#\d]{0,20}(\d{1,2})\s*(?:ft|feet|fit)", desc, re.I)
    if m:
        rec["road_ft"] = float(m.group(1))
    m = re.search(r"(\d(?:\.\d)?)\s*(?:storey|story|storied|floors?|tale)\b", desc, re.I)
    if m:
        rec["storeys"] = float(m.group(1))
    if not rec.get("land_area"):
        m = re.search(r"(?:land|area|size)[^#:]{0,15}:\s*([\d.]+\s*(?:ropani|aana|ana|anna|paisa|dhur|kattha|katha|bigha)[^#]{0,30})", desc, re.I)
        if m:
            rec["land_area_desc"] = m.group(1).strip()
    return rec

# ------------------------------------------------------------------ gharghaderi.com
GG_KEYS = {"District :", "Muncipality :", "Municipality :", "VDC :", "Ward No :", "Tole :", "Land area :", "Road size :",
           "Direction :", "Date :", "Status :", "Floor :", "Floors :", "No of floor :", "Bedroom :", "Bathroom :",
           "Built Year :", "Price Rs :"}

def parse_gharghaderi(url, final, page):
    L = lines_of(page)
    if "Property Details" not in L:
        return {"gone": True}
    rec = {"kind": url.split("/")[3]}
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    rec["title"] = clean(html.unescape(m.group(1)).split("|")[0].split(" - Ghar")[0].strip()) if m else None
    owner = L.index("Owner Information") if "Owner Information" in L else -1
    loc = L.index("Location") if "Location" in L else 0
    for i in range(min(owner, loc) if owner >= 0 else loc, len(L) - 1):
        if owner <= i < loc and L[i] not in ("Date :", "Status :"):   # from the owner block only the date and status
            continue
        if L[i] in GG_KEYS and L[i + 1] not in GG_KEYS and L[i + 1] not in ("Property Details", "Location", "Owner Information"):
            rec[L[i].rstrip(" :").lower().replace(" ", "_")] = clean(L[i + 1])
    # Headline price, e.g. "रु." "18,00,000" "Per Aana".
    for i, x in enumerate(L[:200]):
        if x in ("रु.", "रू.", "Rs.") and i + 1 < len(L) and re.fullmatch(r"[\d,]+", L[i + 1]):
            rec["price"] = L[i + 1]
            if i + 2 < len(L) and L[i + 2].lower().startswith("per "):
                rec["price_unit"] = L[i + 2]
            break
    return rec

# ------------------------------------------------------- gharjagganepal.com (GeoDirectory)
GJ_KEYS = {"Price:", "Property Status:", "Property Type:", "Published:", "Modified:", "Address:", "Municipality:", "District:",
           "Bedrooms:", "Bathrooms:", "Floors:", "Land Area:", "Area:", "Road:", "Road Size:"}

def parse_gharjagganepal(url, final, page):
    if "/properties/" not in final:
        return {"gone": True}
    L = lines_of(page)
    rec = {}
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    rec["title"] = clean(html.unescape(m.group(1)).split(" - Ghar Jagga Nepal")[0].strip()) if m else None
    d = L.index("Details") if "Details" in L else None
    if d is None:
        return {"gone": True}
    for i in range(d + 1, min(d + 60, len(L) - 1)):
        if L[i] in GJ_KEYS and L[i + 1] not in GJ_KEYS:
            rec[L[i].rstrip(":").lower().replace(" ", "_")] = clean(L[i + 1])
    m = re.search(r'"geo":\{"@type":"GeoCoordinates","latitude":(-?[\d.]+),"longitude":(-?[\d.]+)', page)
    if m:
        rec["lat"], rec["lon"] = round(float(m.group(1)), 5), round(float(m.group(2)), 5)
    # Land area and road width are written in the description; keep the values only.
    desc = " ".join(L[L.index("Description") + 1:L.index("Features") if "Features" in L else d]) if "Description" in L else ""
    m = re.search(r"Land Area:?\**:?\s*([\d.]+\s*(?:ropani|aana|ana|anna|paisa|dam|daam|dhur|kattha|kaththa|katha|bigha)(?:[\s,]*[\d.]+\s*(?:aana|ana|paisa|dam|daam|dhur|kattha|kaththa))*)", desc, re.I)
    if m:
        rec["land_area"] = m.group(1).strip()
    m = re.search(r"Road Width:?\**:?\s*([\d.]+)\s*(ft|feet|foot|metres?|meters?|m)\b", desc, re.I)
    if m:
        v = float(m.group(1))
        rec["road_ft"] = round(v * 3.281, 1) if m.group(2).lower().startswith("m") else v
    m = re.search(r"(\d(?:\.\d)?)[\s-]*(?:storey|story|storied|floors?|tale)\b", desc, re.I)
    if m:
        rec["storeys"] = float(m.group(1))
    return rec

SITES = {
    "basobaas": ("https://basobaas.com/sitemap.xml", lambda u: "/property/" in u and not re.search(r"rent|lease|hostel|office|shutter|space|room-|bhk", u.lower()), parse_basobaas),
    "npb": ("https://nepalpropertybazaar.com/sitemap.xml", lambda u: "/property/" in u and not re.search(r"rent|room|shutter|space|hostel|office", u.lower()), parse_npb),
    "gharjagganepal": ("https://gharjagganepal.com/gd_place-sitemap.xml", lambda u: re.search(r"/properties/[^/]+/[^/]+/[^/]+/$", u) is not None and "rent" not in u.lower(), parse_gharjagganepal),
    "gharghaderi": ("https://www.gharghaderi.com/sitemap.xml", lambda u: re.search(r"gharghaderi\.com/(land|house|land-for-sale|house-for-sale)/\d+", u) is not None and not re.search(r"rent|lease|room|flat|office", u.lower()), parse_gharghaderi),
}

# Slowest pace each site has asked for (Nepal Property Bazaar rate-limits faster clients).
MIN_DELAY = {"npb": 4.0}

# ------------------------------------------------------------- nepalhomes.com (Next.js)
NH_SEARCH = "https://www.nepalhomes.com/search?find_property_purpose=5db2bdb42485621618ecdae6&page={}"   # purpose = Sale

def _nh_name(v):
    return (v.get("name") or v.get("title")) if isinstance(v, dict) else v

def nepalhomes_record(x):
    """Only property attributes from one search result; the poster's name, phone, e-mail
    and agency contact fields that the site embeds are dropped here."""
    b, a, lp, bd, pr = (x.get(k) or {} for k in ("basic", "address", "location_property", "building", "price"))
    return {"url": "https://www.nepalhomes.com/detail/" + x["slug_url"], "title": clean((b.get("title") or "").strip()),
            "category": _nh_name(b.get("property_category")), "purpose": _nh_name(b.get("property_purpose")),
            "district": _nh_name(a.get("district_id")), "municipality": _nh_name(a.get("city_id")), "area": _nh_name(a.get("area_id")),
            "total_area": lp.get("total_area"), "road_ft": lp.get("road_access_value"), "road_unit": _nh_name(lp.get("road_access_length_unit")),
            "floors": bd.get("total_floor"), "built_year": bd.get("built_year"),
            "price": None if pr.get("is_price_on_call") else pr.get("value"), "price_label": _nh_name(pr.get("label")),
            "sold_out": x.get("is_sold_out"), "is_project": x.get("is_project"), "published": (x.get("added_at") or "")[:10],
            "lastmod": (x.get("added_at") or "")[:10]}

def _nh_items(s):
    d = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S).group(1))
    return d["props"]["pageProps"]["properties"]["data"]["data"]

# ---------------------------------------------- jaggaghar.com (public JSON API behind the site)
JG_API = "https://api.namaestate.com/properties/?city=13&limit=50&offset={}&order=-created_at"

def jaggaghar_record(x):
    """Property attributes only: the agency's name, phone and e-mail, the description and media are dropped."""
    cat = (x.get("category") or {}).get("name")
    return {"url": "https://www.jaggaghar.com/property/" + x["slug"], "title": clean(x.get("name")), "category": cat,
            "listing_type": x.get("listing_type"), "location": clean(x.get("location")), "price": x.get("price"),
            "pricing_structure": x.get("pricing_structure"), "land_area": x.get("land_area"), "area_unit": x.get("area_unit"),
            "road_length": x.get("road_length"), "road_unit": x.get("road_measuring_unit"), "floors": x.get("counter_floor"),
            "bedrooms": x.get("counter_bedroom"), "lat": x.get("latitude"), "lon": x.get("longitude"),
            "status": x.get("status"), "published": (x.get("created_at") or "")[:10], "lastmod": (x.get("updated_at") or x.get("created_at") or "")[:10]}

def crawl_paged(name, page_url, items_of, record, budget_s, max_pages, delay, step):
    """Paged crawl of a newest-first listing. Phase 1 reads from the top until 3 pages bring
    nothing new (catches new listings). Phase 2 continues the backlog from where the last
    run stopped (raw/<name>.cursor.json), so a time-limited run still covers everything over time."""
    path = os.path.join(RAW, f"{name}.jsonl")
    cur_path = os.path.join(RAW, f"{name}.cursor.json")
    state = load_state(path)
    cursor = json.load(open(cur_path)) if os.path.exists(cur_path) else {"backfill_page": len(state) // step, "done": False}
    t0, n, out = time.time(), 0, open(path, "a")

    def read(page):
        nonlocal n
        _, s = fetch(page_url(page))
        items = items_of(s)
        new = 0
        for x in items:
            try:
                rec = record(x)
            except (KeyError, TypeError):
                continue
            if rec["url"] in state and state[rec["url"]].get("lastmod") == rec["lastmod"]:
                continue
            rec["fetched"] = str(date.today())
            out.write(json.dumps(scrub(rec), ensure_ascii=False) + "\n"); state[rec["url"]] = rec; new += 1; n += 1
        out.flush()
        time.sleep(delay)
        return len(items), new

    pages = 0
    try:
        page, known = 0, 0
        while known < 3 and time.time() - t0 < budget_s and (not max_pages or pages < max_pages):
            got, new = read(page); pages += 1
            if not got:
                break
            known = known + 1 if new == 0 else 0
            page += 1
        page = max(cursor["backfill_page"], page)
        while not cursor["done"] and time.time() - t0 < budget_s and (not max_pages or pages < max_pages):
            got, _ = read(page); pages += 1
            if not got:
                cursor["done"] = True; break
            page += 1
            cursor["backfill_page"] = page
            if pages % 50 == 0:
                print(f"{name}: backlog page {page}, {n} new", file=sys.stderr, flush=True)
    except Challenged:
        print(f"{name}: rate-limited; stopping this run", file=sys.stderr)
    except Exception as e:
        print(f"ERR {name}", e, file=sys.stderr)
    out.close()
    json.dump(cursor, open(cur_path, "w"))
    print(f"{name}: {n} new or changed listings from {pages} pages; backlog {'complete' if cursor['done'] else 'continues at page ' + str(cursor['backfill_page'])}", file=sys.stderr)
    return n

def load_state(path):
    state = {}
    if os.path.exists(path):
        for l in open(path):
            r = json.loads(l)
            state[r["url"]] = r
    return state

def crawl(name, budget_s, max_pages, delay):
    index, keep, parse = SITES[name]
    delay = max(delay, MIN_DELAY.get(name, 0))
    path = os.path.join(RAW, f"{name}.jsonl")
    state = load_state(path)
    # Reuse a sitemap read in the last 6 hours, so an interrupted run resumes straight away.
    cache = os.path.join(RAW, f"{name}.sitemap.json")
    try:
        if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 6 * 3600:
            urls = json.load(open(cache))
        else:
            urls = sitemap_urls(index, keep)
            json.dump(urls, open(cache, "w"))
    except Challenged:
        print(f"{name}: sitemap is rate-limited right now; will try on the next run", file=sys.stderr)
        return 0
    todo = [u for u, mod in urls.items() if u not in state or (mod and mod > (state[u].get("lastmod") or ""))]
    # Newest first, so a time-limited run always picks up the latest listings.
    todo.sort(key=lambda u: urls[u], reverse=True)
    if max_pages:
        todo = todo[:max_pages]
    print(f"{name}: {len(urls)} in sitemap, {len(state)} known, {len(todo)} to fetch", file=sys.stderr, flush=True)
    t0, n, out = time.time(), 0, open(path, "a")
    for u in todo:
        if time.time() - t0 > budget_s:
            print(f"{name}: time budget reached", file=sys.stderr); break
        try:
            final, page = fetch(u)
            rec = parse(u, final, page)
        except Challenged:
            print(f"{name}: site keeps rate-limiting us; stopping this run", file=sys.stderr); break
        except Exception as e:
            if "404" in str(e) or "410" in str(e):
                rec = {"gone": True}
            else:
                print("ERR", u, e, file=sys.stderr, flush=True); time.sleep(delay); continue
        rec.update(url=u, lastmod=urls[u], fetched=str(date.today()))
        out.write(json.dumps(scrub(rec), ensure_ascii=False) + "\n"); out.flush()
        n += 1
        if n % 200 == 0:
            print(f"{name}: {n}/{len(todo)}", file=sys.stderr, flush=True)
        time.sleep(delay)
    out.close()
    print(f"{name}: fetched {n}", file=sys.stderr)
    return n

def compact(name):
    """Keep only the newest record per URL."""
    path = os.path.join(RAW, f"{name}.jsonl")
    state = load_state(path)
    with open(path, "w") as f:
        for r in state.values():
            f.write(json.dumps(scrub(r), ensure_ascii=False) + "\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sites", nargs="+", choices=list(SITES) + ["nepalhomes", "jaggaghar"])
    ap.add_argument("--budget-min", type=float, default=40, help="stop each site after this many minutes")
    ap.add_argument("--max", type=int, default=0, help="fetch at most this many pages per site (0 = all)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests to a site")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    for s in a.sites:
        if s == "nepalhomes":
            crawl_paged(s, lambda p: NH_SEARCH.format(p + 1), _nh_items, nepalhomes_record, a.budget_min * 60, a.max, max(a.delay, 2.0), 8)
        elif s == "jaggaghar":
            crawl_paged(s, lambda p: JG_API.format(p * 50), lambda t: json.loads(t)["results"], jaggaghar_record, a.budget_min * 60, a.max, max(a.delay, 2.0), 50)
        else:
            crawl(s, a.budget_min * 60, a.max, a.delay)
        compact(s)
