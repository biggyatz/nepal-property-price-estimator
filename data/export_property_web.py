"""Write web/model.json and web/listings.json for the property app.

Each listing gets map coordinates: the site's own pin when it publishes one (and it lies
near the listing's district), otherwise its locality, town or district from geo_places.json.
`geo` records which of these was used, so the map can leave district-level points out
of the heatmap."""
import json, sys
import pandas as pd
from geocode import load, lookup, valid_point

out_dir = sys.argv[1]
model = json.load(open("property_model.json"))
df = pd.read_csv("property_model_rows.csv")
cache = load()
s = lambda v: v if isinstance(v, str) else None
rows = []
for r in df.itertuples():
    lat, lon = getattr(r, "lat", None), getattr(r, "lon", None)
    if valid_point(cache, r.district, lat, lon):
        p, geo = (round(lat, 4), round(lon, 4)), "pin"
    else:
        p, geo = lookup(cache, r.district, s(getattr(r, "city", None)), s(r.locality))
    rows.append({"title": r.title[:90], "type": r.type, "locality": s(r.locality), "district": r.district,
                 "city": s(getattr(r, "city", None)), "price": int(r.price_npr), "area": round(float(r.area_aana), 3),
                 "url": r.url, "source": r.source, "year": int(r.year), "listed": str(r.listed)[:10],
                 "lat": p[0] if p else None, "lon": p[1] if p else None, "geo": geo})
model["geo_coverage"] = {k: sum(x["geo"] == k for x in rows) for k in ("pin", "locality", "town", "district", None) if k}
json.dump(model, open(f"{out_dir}/model.json", "w"), separators=(",", ":"))
json.dump(rows, open(f"{out_dir}/listings.json", "w"), ensure_ascii=False, separators=(",", ":"))
print("model + listings", len(rows), model["geo_coverage"])
