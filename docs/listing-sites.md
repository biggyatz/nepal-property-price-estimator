# Property listing sites in Nepal

A survey of the portals where houses and land are listed for sale in Nepal, done in
November 2026 to decide which ones the estimator can keep reading automatically.
Nepal has no central listing system (no MLS), so asking prices are scattered across
these portals, Facebook groups and agents' own pages.

Counts are the for-sale house/land pages in each site's sitemap or search on
23 November 2026. "Fresh" is how many of those were added or updated since June 2026.

## Sites the app reads

| Site | Listings | Fresh | Coverage | How it is read | robots.txt | Status |
| --- | --- | --- | --- | --- | --- | --- |
| [nepalpropertybazaar.com](https://nepalpropertybazaar.com) | ~4,000 | ~1,470 | All Nepal; strong on the Valley, Pokhara, Chitwan, the eastern Terai | Sitemap + property pages (`crawl_sites.py npb`); pages carry a map pin | Allows all but `/wp-admin/` | **Added.** Rate-limits fast clients with a "please wait" page, so it is read slowly (one page per 4 s) and the crawler backs off when asked |
| [basobaas.com](https://basobaas.com) | ~5,200 in sitemap, ~950 live | ~640 | Mostly the Valley, some Pokhara and Banepa | Sitemap + property pages (`crawl_sites.py basobaas`) | Allows all but `/dashboard/` | Added (Nov 2026). Sold listings redirect to search and are kept as history |
| [gharghaderi.com](https://www.gharghaderi.com) | ~3,300 in sitemap | none (sitemap dated April 2025) | All 7 provinces, with district / municipality / ward fields | Sitemap + property pages (`crawl_sites.py gharghaderi`) | No restrictions | **Added.** Many sitemap entries now 404; live ones are 2024–25 asking prices |
| [gharjagganepal.com](https://gharjagganepal.com) | ~180 | ~180 | Bharatpur/Chitwan, Nawalpur, Banepa and the Valley | Sitemap (`gd_place-sitemap.xml`) + property pages (`crawl_sites.py gharjagganepal`); pages carry a map pin and published date | Allows all | **Added (23 Nov 2026).** Land area and road width are read from the description (values only) |
| [hamrobazaar.com](https://hamrobazaar.com) | 10+ new property ads a day | daily | All Nepal, free-text titles | Headless browser on search and detail pages (`crawl_hamrobazar*.js`) | Allows `/search/product`, `/detail/` | Added (Oct 2026). Search returns few results per query; daily run covers 29 towns |
| [99aana.com](https://99aana.com) | ~3,100 | none since Feb 2024 | Mostly the Valley | Sitemap + property pages (`crawl_99aana.py`) | Allows all | Kept as 2021–24 history; no new listings to fetch |

## Sites looked at and not added (yet)

| Site | What we found | Why not now |
| --- | --- | --- |
| [99ropani.com](https://99ropani.com) | New portal with price estimates and land checks; sitemap lists 1 listing | Too few listings yet; `/api` is disallowed |
| [gharbazar.com](https://www.gharbazar.com) | 678 property URLs in sitemap | Detail pages sampled redirect to the home page (expired) |
| [propertynepal.com](https://propertynepal.com) | 79 property URLs, includes auctions | Small; next candidate |
| [nepalhomes.com](https://www.nepalhomes.com) | JavaScript app, no sitemap | Needs a headless-browser crawler like Hamrobazaar |
| housingnepal.com | Developer association site | Returns HTTP 406 to non-browser clients |
| nepalproperty.com, merojagga.com, gharjagga.com, hamrogharjagga.com, ghar.com.np, jagga.com.np | Unreachable (connection refused / DNS) in November 2026 | Offline or blocked |

## How "fresh" the data stays

The `Refresh listings` GitHub Action (`.github/workflows/refresh-data.yml`) runs every
3 hours. For each sitemap portal it compares the sitemap's `<lastmod>` dates with what
it fetched before (`data/raw/*.jsonl`) and downloads only new or changed listings,
newest first, so a typical run fetches a few dozen pages. Hamrobazaar is crawled once a
day. When anything changed the action retrains the model, commits the new data to
`main`, and the site is republished. A listing posted on a portal therefore appears in
the app within about 3 hours (24 hours for Hamrobazaar).

True "instant" updates would need the portals to push new listings to us (a feed or
webhook); none of them offers one, so polling their sitemaps is the fastest polite option.

## Rules the crawlers follow

* Only pages that robots.txt allows; one request per second or slower per site, and
  slower still where a site asks (Nepal Property Bazaar).
* A site's anti-bot "please wait" page is never solved or bypassed: the crawler backs
  off and tries again on the next scheduled run.
* Only property attributes are stored. Seller names, phone numbers (also scrubbed from
  titles), e-mails and descriptions are never kept.
* Asking prices, not sale prices: they usually exceed what properties sell for.
