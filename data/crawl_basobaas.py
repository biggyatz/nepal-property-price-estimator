"""Polite crawler for basobaas.com property pages (robots.txt: allow all except /dashboard/).
Usage: python crawl_basobaas.py urls_basobaas.txt raw_basobaas.jsonl
Keeps only property attributes (category, title, address, price, area, road, floors,
rooms, last-updated date) and the source URL. Seller names and phone numbers are never stored."""
import html, json, re, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

KEYS = ("Land Area", "Road Access In Feet", "Road Type", "Built Year", "Built Up Area", "Property Face",
        "Furnishing", "Total Floors", "Property Id")

def lines_of(page):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    return [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", s)).split("\n") if l.strip()]

def parse(url, page):
    L = lines_of(page)
    rec = {"source": "basobaas.com", "url": url}
    try:
        k = L.index("Like")          # "... <category> <Sale|Rent> Like Share <title> <address> ..."
    except ValueError:
        return rec
    rec["category"], rec["purpose"] = L[k - 2], L[k - 1]
    rec["title"], rec["address"] = L[k + 2], L[k + 3]
    head = L[k + 3:k + 40]
    for x in head:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)\s+(Bedroom|Bathroom|Floors|Kitchen|Living Room|Parking)", x)
        if m:
            rec[m.group(2).lower().replace(" ", "_")] = float(m.group(1))
    pi = next((i for i, x in enumerate(head) if x.startswith("Rs.")), None)
    if pi is not None:
        rec["price"] = head[pi]
        nxt = head[pi + 1] if pi + 1 < len(head) else ""
        rec["price_unit"] = nxt if nxt.lower().startswith("per") else None
    if "Last updated:" in head:
        rec["updated"] = head[head.index("Last updated:") + 1]
    if "Overview" in L:
        o = len(L) - 1 - L[::-1].index("Overview") if L.count("Overview") > 1 else L.index("Overview")
        for i in range(o + 1, min(o + 40, len(L) - 1)):
            if L[i] == "Description":
                break
            if L[i] in KEYS:
                rec[L[i]] = L[i + 1]
    return rec

if __name__ == "__main__":
    url_file, out_file = sys.argv[1], sys.argv[2]
    done = set()
    try:
        done = {json.loads(l)["url"] for l in open(out_file)}
    except FileNotFoundError:
        pass
    todo = [u.strip() for u in open(url_file) if u.strip() and u.strip() not in done]
    out, lock = open(out_file, "a"), threading.Lock()

    def work(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research crawler; contact via github.com/biggyatz)"})
            rec = parse(url, urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore"))
            with lock:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
        except Exception as e:
            print("ERR", url, e, file=sys.stderr, flush=True)
        time.sleep(2.5)  # per worker; 3 workers stay near ~1 request/second overall

    print("todo", len(todo), file=sys.stderr, flush=True)
    with ThreadPoolExecutor(3) as ex:
        for n, _ in enumerate(ex.map(work, todo)):
            if n % 200 == 0:
                print(n, time.strftime("%H:%M:%S"), file=sys.stderr, flush=True)
