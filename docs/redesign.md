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
