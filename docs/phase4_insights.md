# Phase 4: release insights (computed numbers only)

Every release gets a short list of facts computed from the stored data. No language model is involved: each sentence is a fixed template filled with numbers.
Output: `catalog/insights/<publication id>.json` (all insights of a release) and `catalog/latest_insights.json` (headlines of the 10 newest releases, for the web page).
They are rebuilt automatically after every ingest, and by hand with `python3 -I gastat/insights.py --all`.

## What is computed

| Kind | Meaning |
|---|---|
| series_change | Latest value of a series against the previous period and against the same period a year earlier (percent change for indices and quantities, point difference for rates and shares). Adds "highest / lowest in the available data since <period>" when the series has at least 6 observations. |
| mover_up / mover_down | Biggest rise and biggest fall among the members of one table for the latest period (needs at least 3 members). |
| cross_section | Highest and lowest member of a table published for one period only (no history yet). |
| revision | Values GASTAT changed in a file it had already published, with a note when the change is a factor of 10, 100, 1000 or a million (looks like a unit correction). |

Rules that keep the numbers honest:
- A series is only compared with itself (same sheet, block, row, column, unit, scale, comparison base). Nothing is interpolated: if the previous or year-earlier period is missing, that comparison is left out.
- "Highest in the available data" always names where the available data starts. It never says "record" without that.
- Weights and distributions are not reported as news. Unchanged series are skipped.
- Units: a number gets a unit only when it is known. Rates stored as "percent or fraction" are printed as percent only when the dataset itself proves it (some value above 1.5). Otherwise the number is printed without a unit. A scale such as "thousand" is never attached to a percentage.
- Headlines: totals first, then record highs and lows, then biggest movers, at most 2 per table and 10 per release. The same figure published in several summary tables is one insight.
- Every insight lists its source cells (`evidence`), so each figure can be checked against the original Excel file.

## Validation (tests/test_insights.py, exit code 1 on any failure)

Result on 2026-11-17: 1,068 source cells re-read from the original Excel files and equal to the stored values, 140 changes recomputed (difference and percent), 509 sentences checked (every printed number comes from the stored numbers, no dash characters), 228 cross-table comparisons (published rates against rates recomputed from the published index of the same file) with 0 failures.

One difference in GASTAT's own file is documented in the test as a source inconsistency: Business Confidence Index, Services sector, February 2026. Sheet 3 publishes -0.463%, while the index values on sheet 2 give -0.352%. January and March of the same series agree exactly.

## Engine fixes found while building Phase 4 (all re-run on the stored data, regression test still 25 of 25 sheets)

1. Rate tables with one date per column (Business Confidence sheet 3) had every month stored as October 2026. Dates on rate columns are now periods when 3 or more columns share the same header text; a single date on a rate column still means "compared with that month".
2. Tables with a year column and rows named by month (consumer and wholesale price sheets 2.3, 3.x, 4.x, 5.x) stored only the year. The month is now part of the period (`2026-10`) and the row no longer carries the month as a label or code.
3. The title of each table is now stored (`table_title`) so identical row names in different tables can be told apart.
4. Business Confidence sheet 3 is recorded in its recipe as fractions of 1 (checked against the index sheet).

`python3 -I gastat/reingest.py` shows which stored datasets an engine fix would change (dry run). `--apply` replaces only that publication's rows and logs value changes as revisions. It re-downloads the file when the cached copy is older than the registered version.

## Open items

- Research and Development Statistics 2025 and Producer Price Index September 2026 are quarantined (new layouts), so they have no insights yet.
- Some column headers still carry a wrong unit text (for example "التنويم" in consumer price sheets 5.x). Phase 4 leaves the unit out of those sentences. The values themselves are not affected.
- Several tables repeat the same item name in different rows (for example the two "الغاز" rows in sheet 5.x of the consumer price index). The sentence then ends with the table title. A cleaner label needs the table owner's naming and is left for the review round.
