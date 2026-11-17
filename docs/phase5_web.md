# Phase 5: the web page

A plain static site in `web/` (no build step, no server). Arabic, right to left, works on a phone. GASTAT is credited in the header and in the footer of every view.

| View | What it shows |
|---|---|
| أحدث الإصدارات | Newest releases first, with the computed headline numbers, all insights of a release, and links to GASTAT's Excel and PDF files. |
| مستكشف المؤشرات | Keyword search over table names and item names (Arabic or English), up to 6 series on one chart (hover for exact values), the numbers table with the source cell in GASTAT's file, CSV download of the chosen series, link to the full table (Parquet or CSV). |
| حداثة البيانات | For each of the 79 publications: last release, next scheduled release from GASTAT's calendar (or the expected date), and whether it has passed a full cycle plus 10 days without a release. |
| جودة البيانات | Checks every table passes, all stored values compared with their original Excel cell, quarantined releases, recipe review status, open issues, and GASTAT's revisions of published values. |

## How it stays current
- `gastat/webdata.py` writes `catalog/catalog.json`, `catalog/search_index.json` and everything under `web/data/`.
- It runs after every ingested release (collector) and once a day (health workflow, because freshness depends on today's date). Both commit `web/` and `catalog/`.
- Vercel redeploys on each commit, so the page needs no other action.

## Deploying on Vercel (once, from your own Vercel account)
1. vercel.com, Add New, Project, import the GitHub repository `gastat-data-monitor`.
2. Root Directory: `web`. Framework Preset: Other. Build Command and Output Directory: leave empty.
3. Deploy. Cost: the free Hobby plan is enough (static files only).

## Tests
`python3 -I tests/test_web.py` checks that every dataset has a series file whose number of values equals the stored values, that series are aligned, that the GASTAT credit is on the page shell and that no long dash appears in the page files.
