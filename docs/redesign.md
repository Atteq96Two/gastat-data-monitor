# Redesign: report specs and one-page front end (Phase A)

## What changed
- **Scope:** an explicit allow-list of 13 core reports in `gastat/scope.py` (wholesale prices and non-oil trade are details, never cards). Annual and biennial reports are `out_of_scope`; the four planned for phase 2 are `phase2`.
- **Report specs:** `report_specs/<report>.yaml` names every series a report shows (headline, level 1, 2, 3, description, press release value). The engine never decides the presentation. A selector that does not resolve to exactly one series stops the build.
- **Headline check against the press release:** the build fails if a headline differs from the value printed in GASTAT's own press release for that edition (`press_release_value`).
- **Front end:** one page, six theme groups, cards with three elements, report opened in place. No top navigation, no insight sentences, no red or green. Data files load lazily when a report opens (`web/data/home.json`, `web/data/reports/<id>.json`).
- **Bundle:** `web/` is 0.1 MB (it was 39 MB). Series files for programs moved to `catalog/series/` (not served by the site).

## Fixes found while checking the numbers
- Fingerprints now treat `أكتوبر2026م` and `يناير 2026` as the same layout, so a monthly report no longer looks like a new layout every month (recipes migrated).
- Dataset ids are stable per report (`scope.py` prefix); sheet names carrying a quarter or year (for example `Q3_2026`) no longer change the id.
- Average Prices: month columns now carry their month (2025-01 to 2026-10), price columns are SAR (they were labelled percent), change columns record the base month.
- Industrial Production summary tables: change columns hold fractions; they were shown as 0.1 instead of 10.9%.
- Wholesale Price Index summary tables: year-over-year columns had no base period.

## Open items
- PPI headline: the press release says 6.6% (index without the oil-inclusive total). The oil-inclusive total (21.5%) is shown in level 2.
- November 2025 is missing from the Average Prices series (no edition in the register); the chart line skips it.
- `catalog/series/*.json` (about 43 MB) duplicates the Parquet data for the News Tracker. Decision needed: read Parquet instead and stop committing the JSON.

## Phase B (2026-11-19): the remaining seven core reports

All 13 core reports now have a card. Headlines are checked against the GASTAT press release at build time (a mismatch stops the build).

| Report | Headline | Value | Change shown |
|---|---|---|---|
| GDP and National Accounts (Q2 2026) | real GDP growth, year on year | -4.7% | points vs previous quarter |
| Foreign direct investment (Q2 2026) | net flows | 19.1 bn SAR | -19.5% on the same quarter last year (press release) |
| International trade in goods (Aug 2026) | goods exports | 87.2 bn SAR | -11.5% year on year (published) |
| Labor market statistics (Q2 2026) | unemployment, total population | 3.0% | points vs previous quarter (Saudis 6.5% in level 2) |
| Real estate price index (Q3 2026) | general index (2023=100) | 105.1 | +1.2% year on year (published) |
| Consumer confidence (Q2 2026) | general index | 110.0 | -3.1% vs previous month (derived) |
| Tourism establishments (Q2 2026) | hotel room occupancy | 51.0% | -2.2 points vs Q2 2025 (as in the press release) |

Extractor additions (all recipe-driven, so existing recipes and fingerprints are unchanged):
`col_overrides` (explicit column definitions), `col_label_overrides` (retype columns by header text), `header_fill_right`,
`extra_header_rows`, `month_in_text`, `row_period_labels` ("الربع الأول 2021" as a row label), quarter rows inside a year (Q1..Q4),
provisional years (`*2026`, `2026*`), recipe status `held` (a table the owner chose to leave out: no alert, not published).
Non-oil trade now has its own dataset prefix (`non-oil-trade_*`) so its sheet numbers cannot collide with the main release.

Left out on purpose (status `held`, reasons in each recipe's notes): trade sheets 9, 10, 11, 12.x, 13.x, Sheet1; tourism daily-price
tables (no unit written) and employee-change tables (count read as a rate); labour summary table 1 and 2-10; the GDP menu sheet.
Tourism and labour quarterly tables that share a layout with a held table are also held (a recipe is per layout).
