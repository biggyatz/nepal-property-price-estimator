# Nepal Property Price Estimator

**Live app:** <https://biggyatz.github.io/nepal-property-price-estimator/>

Estimate the asking price of a house or plot of land anywhere in Nepal (Kathmandu Valley, Pokhara, Bharatpur, Butwal, Itahari, Hetauda, Banepa, Birtamod and more) from **2,901 real listings** across 28 districts. Enter the type, district, locality, land area (ropani-aana-paisa-dam, or bigha-kattha-dhur in the Terai), road width and storeys. You get an estimate with a likely range, the price per aana, the most similar listings on the market (linked to their source), a map of prices per aana by area (with a listings heatmap and every listing marked with its site), a searchable table of all listings showing which site each came from, a ranking of areas by price per aana (Valley or outside), and the hotspot towns outside the Valley with their change since 2021–23.

The app is a static page on GitHub Pages: the model runs in the browser, with no server and no cost.

> This repository started as a Boston house-price regression. That original project is preserved in [`legacy-boston/`](legacy-boston/).

## Data

| Source | Listings used | Period | How it was collected |
| --- | --- | --- | --- |
| [99aana.com](https://99aana.com) | 1,672 | 2021–2024 | Property pages from the site's sitemap (`robots.txt`: allow all); no new listings since Feb 2024 |
| [basobaas.com](https://basobaas.com) | 578 | 2024–2026 | Property pages from the site's sitemap (`robots.txt`: allow all but `/dashboard/`) |
| [gharjagganepal.com](https://gharjagganepal.com) | 145 | 2026 | Property pages from its sitemap; most carry a map pin |
| [gharghaderi.com](https://www.gharghaderi.com) | 183 so far | 2024–2025 | Property pages from its sitemap; being read a few hundred per run |
| [hamrobazaar.com](https://hamrobazaar.com) | 323 | 2025–2026 | Search and listing pages for 36 towns (`/search/product`, `/detail/`, both allowed in `robots.txt`) |

* Collected in October–November 2026 at roughly one request per second. Sold or withdrawn Basobaas listings (which redirect to its search page) are skipped.
* Only property attributes are kept: type, price, address, land area, road, storeys, listing date and source URL. Phone numbers and seller names are never stored.
* These are **asking prices**, which usually exceed final sale prices. Treat estimates as market-listing levels, not a valuation.

Cleaning (`data/clean_property.py`):
* Nepali prices are parsed (`1 crore 50 lakh`, `Rs 2,20,00,000`, `18 lakh per aana`, and `270` meaning 270 lakh).
* Land units are converted to aana (1 ropani = 16 aana = 5,476 sq ft; 1 dhur = 182.25 sq ft). Hamrobazar's "Aana/Dhur" field is read as dhur in Terai districts.
* District, town and locality come from the address or title via `data/places.py` (about 150 towns, misspellings such as Kathamndu tolerated), with spelling variants merged (Buddhanilkantha → Budhanilkantha).
* Price-per-aana outliers more than 5× from their district median are dropped.

## Model

A hedonic regression on log(price) with ridge regularisation:

`log(price) = district + locality + type + type × log(area) + log(road width) + storeys + listing year`

* Localities with at least 4 listings get their own effect, shrunk toward the district by the ridge penalty; others use the district level.
* Year effects let older listings inform the model while estimates are made at 2026 levels.

| 5-fold cross-validation | Ridge (deployed) | Gradient boosting |
| --- | --- | --- |
| R² (log price) | 0.729 | 0.704 |
| Median absolute error | 23.1% | 22.8% |
| Within ±25% | 53.6% | 53.8% |

The regression is kept because it is as accurate as gradient boosting here, every effect is explainable, and it behaves sensibly for areas with few listings. `web/predict.js` reproduces the Python model exactly (max relative difference ~1e-14 over all listings). The likely range shown in the app is the 10th–90th percentile of cross-validated errors.

## Repository layout

| Path | What it is |
| --- | --- |
| `web/` | The app: `index.html`, `app.js`, `predict.js`, `style.css`, plus `model.json` and `listings.json` |
| `data/crawl_sites.py` | Incremental sitemap crawler for Basobaas, Nepal Property Bazaar, Ghar Jagga Nepal and Gharghaderi |
| `data/crawl_99aana.py`, `data/crawl_hamrobazar*.js` | Crawlers for 99aana and Hamrobazaar (robots.txt-compliant, rate-limited, no personal data) |
| `data/raw/` | What each crawler has seen (one record per listing URL); also the crawlers' memory between runs |
| `data/geocode.py`, `data/geo_places.json` | Coordinates for districts, towns and localities (OpenStreetMap Nominatim, cached) |
| `data/update.py` | One full refresh: crawl, clean, geocode, retrain, export |
| `.github/workflows/refresh-data.yml` | Runs `update.py` every 3 hours and republishes the site |
| `docs/listing-sites.md` | Survey of Nepal's property listing sites and which ones are read |
| `data/clean_property.py`, `data/nepal_units.py` | Parsing of Nepali prices, land units and years; merging of the sources |
| `data/places.py` | Gazetteer of districts, towns and Valley localities used to place each listing |
| `data/train_property_model.py` | Model training and cross-validation |
| `data/export_property_web.py` | Writes `web/model.json` and `web/listings.json` |
| `data/property_listings.csv` | The cleaned dataset |
| `legacy-boston/` | The original Boston Housing project (Flask, Docker) |

## Keeping the data fresh

The **Refresh listings** workflow runs every 3 hours (Hamrobazaar once a day). It reads
each portal's sitemap, fetches only listings that are new or changed since the last run,
rebuilds the dataset, retrains the model, commits to `main` and republishes the site, so
new listings reach the app within about 3 hours. See [docs/listing-sites.md](docs/listing-sites.md)
for every site surveyed and why some are not read. Run it by hand from the Actions tab
(*Run workflow*), or locally:

```bash
cd data
pip install -r requirements.txt
python update.py                      # sitemap portals only
python update.py --hamrobazaar        # also Hamrobazaar (needs: npm i playwright && npx playwright install chromium)
```

## Licence

Copyright © 2024–2026 Biggyat Kumar Pandey. All rights reserved. The code is public for viewing only; see [LICENSE](LICENSE). For permission to use it, email hello@biggyatkumarpandey.com.np.
