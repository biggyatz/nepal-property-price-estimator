# Property listing sites in Nepal

A survey of the portals where houses and land are listed for sale in Nepal, done in
November 2026 to decide which ones the estimator can keep reading automatically.
Nepal has no central listing system (no MLS), so asking prices are scattered across
these portals, Facebook groups and agents' own pages.

Counts are the for-sale house/land listings in each site's sitemap, search or API on
23 November 2026. "Fresh" is how many of those were added or updated since June 2026.

## Sites the app reads

| Site | Listings | Fresh | Coverage | How it is read | robots.txt | Status |
| --- | --- | --- | --- | --- | --- | --- |
| [nepalpropertybazaar.com](https://nepalpropertybazaar.com) | ~4,000 | ~1,470 | All Nepal; strong on the Valley, Pokhara, Chitwan, the eastern Terai | Sitemap + property pages (`crawl_sites.py npb`); pages carry a map pin | Allows all but `/wp-admin/` | **Added.** Rate-limits fast clients with a "please wait" page, so it is read slowly (one page per 4 s) and the crawler backs off when asked |
| [basobaas.com](https://basobaas.com) | ~5,200 in sitemap, ~950 live | ~640 | Mostly the Valley, some Pokhara and Banepa | Sitemap + property pages (`crawl_sites.py basobaas`) | Allows all but `/dashboard/` | Added (Nov 2026). Sold listings redirect to search and are kept as history |
| [gharghaderi.com](https://www.gharghaderi.com) | ~3,300 in sitemap | none (sitemap dated April 2025) | All 7 provinces, with district / municipality / ward fields | Sitemap + property pages (`crawl_sites.py gharghaderi`) | No restrictions | **Added.** Many sitemap entries now 404; live ones are 2024–25 asking prices |
| [gharjagganepal.com](https://gharjagganepal.com) | ~180 | ~180 | Bharatpur/Chitwan, Nawalpur, Banepa and the Valley | Sitemap (`gd_place-sitemap.xml`) + property pages (`crawl_sites.py gharjagganepal`); pages carry a map pin and published date | Allows all | **Added (23 Nov 2026).** Land area and road width are read from the description (values only) |
| [nepalhomes.com](https://www.nepalhomes.com) | ~6,500 for sale | daily | All Nepal, mostly the Valley; agencies post here | Its for-sale search pages, newest first, 8 per page (`crawl_sites.py nepalhomes`); the page data already holds district / municipality / area, land size, road, floors and price | No robots.txt | **Added (23 Nov 2026).** Seller names, phones and e-mails that the page data contains are dropped at crawl time |
| [jaggaghar.com](https://www.jaggaghar.com) | ~11,300 | daily | All Nepal | The public listing API behind the site (`api.namaestate.com/properties/`), 50 per request, newest first (`crawl_sites.py jaggaghar`) | No robots.txt on the site or API | **Added (23 Nov 2026).** Agency phone/e-mail, descriptions and media are dropped |
| [hamrobazaar.com](https://hamrobazaar.com) | 10+ new property ads a day | daily | All Nepal, free-text titles | Headless browser on search and detail pages (`crawl_hamrobazar*.js`) | Allows `/search/product`, `/detail/` | Added (Oct 2026). Search returns few results per query; daily run covers 29 towns |
| [99aana.com](https://99aana.com) | ~3,100 | none since Feb 2024 | Mostly the Valley | Sitemap + property pages (`crawl_99aana.py`) | Allows all | Kept as 2021–24 history; no new listings to fetch |

## Sites looked at and not added (yet)

| Site | What we found | Why not now |
| --- | --- | --- |
| [99ropani.com](https://99ropani.com) | New portal with price estimates and land checks; sitemap lists 1 listing | Too few listings yet; `/api` is disallowed |
| [gharbazar.com](https://www.gharbazar.com) | 678 property URLs; many redirect to the home page (expired); no district field, only "3 weeks ago" dates | Its footer prohibits copying or reproducing the site's information |
| [propertynepal.com](https://propertynepal.com) | Now a "demo version" page recovered from the Wayback Machine; no listings | Site is defunct |
| [propertyinnepal.com.np](https://www.propertyinnepal.com.np) | ~1,230 listings (an agency's own site) | JavaScript app whose data comes only from `/api/`, which its robots.txt disallows; the agency posts the same listings on Nepal Homes and Jagga Ghar, which are read |
| [housingnepal.com](https://www.housingnepal.com) | Developer association site: ~40 project pages, mostly apartments | Project and apartment prices, not house/land listings |
| [landnepal.com](https://www.landnepal.com) | WordPress blog/news posts | No structured listings |
| [realestatenepal.com](https://www.realestatenepal.com) | Sitemap empty | Nothing to read |
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
