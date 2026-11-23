"""One refresh of the whole pipeline; what the scheduled GitHub Action runs.

    python update.py [--sites basobaas npb gharghaderi] [--hamrobazaar] [--budget-min 25]

1. crawl_sites.py   fetch listings that are new or changed in each portal's sitemap
2. Hamrobazaar      (optional, needs Node + Playwright) search pages and new detail pages
3. clean            merge all sources into property.csv -> property_listings.csv
4. geocode          look up coordinates for any new places (cached)
5. train + export   refit the model and write web/model.json, web/listings.json
Exits 0 whether or not anything changed; the workflow commits only if files differ.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HB_TOWNS = ("pokhara lekhnath chitwan bharatpur butwal bhairahawa dharan itahari biratnagar birtamod damak hetauda "
            "nepalgunj dhangadhi banepa dhulikhel janakpur birgunj ghorahi surkhet kawasoti damauli "
            "kathmandu lalitpur bhaktapur budhanilkantha tokha imadol").split()

def run(*cmd, check=True):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=HERE, check=check).returncode

def scrub_file(path):
    from crawl_sites import scrub
    if os.path.exists(path):
        rows = [scrub(json.loads(l)) for l in open(path) if l.strip()]
        with open(path, "w") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="*", default=["basobaas", "npb", "gharghaderi"])
    ap.add_argument("--hamrobazaar", action="store_true")
    ap.add_argument("--budget-min", type=float, default=25)
    a = ap.parse_args()
    if a.sites:
        run(sys.executable, "crawl_sites.py", *a.sites, "--budget-min", str(a.budget_min), check=False)
    if a.hamrobazaar:
        queries = [f"{k} sale {t}" for t in HB_TOWNS for k in ("land", "house")]
        run("node", "crawl_hamrobazar.js", "/detail/for-sale-(house|land)/", "raw/hamrobazaar_search.jsonl", *queries, check=False)
        run("node", "crawl_hamrobazar_details.js", "raw/hamrobazaar_search.jsonl", "raw/hamrobazaar_details.jsonl", check=False)
        for p in ("raw/hamrobazaar_search.jsonl", "raw/hamrobazaar_details.jsonl"):
            scrub_file(os.path.join(HERE, p))
    run(sys.executable, "clean_property.py")
    os.replace(os.path.join(HERE, "property.csv"), os.path.join(HERE, "property_listings.csv"))
    run(sys.executable, "geocode.py", "--csv", "property_listings.csv", "--max", "150", check=False)
    run(sys.executable, "train_property_model.py")
    run(sys.executable, "export_property_web.py", "../web")
