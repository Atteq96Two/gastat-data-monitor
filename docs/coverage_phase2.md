# Phase 2 coverage report (November 2026 pilot)

Generated 2026-11-15T07:57:44+00:00. Only tables that pass every gate are written to /data. Others are quarantined and not published.

| Publication | Data tables | Validated | Quarantined | Rows published |
|---|---|---|---|---|
| ICT Access and Usage Statistics by Households and Individuals 2026 | 58 | 58 | 0 | 985 |
| GDP - Flash Estimate Q3/2026 | 4 | 4 | 0 | 264 |
| Road Transport Statistics 2025 | 83 | 76 | 7 | 20348 |
| Business Confidence Index for October 2026 | 3 | 3 | 0 | 376 |
| Industrial Production Index- September 2026 | 3 | 3 | 0 | 1065 |
| Livestock Statistics 2025 | 56 | 56 | 0 | 3306 |
| Consumer Price Index – October 2026 | 14 | 9 | 5 | 44248 |
| Wholesale Price Index – October 2026 | 12 | 9 | 3 | 50609 |
| Average service prices for October 2026 | 4 | 4 | 0 | 952 |

**Total: 222 of 237 data tables validated (94%), 122153 numbers published.**

## Integrity test: every published number equals the original Excel cell

| Publication | Values checked | Mismatches |
|---|---|---|
| Livestock Statistics 2025 | 3306 | 0 |
| Consumer Price Index – October 2026 | 44248 | 0 |
| Wholesale Price Index – October 2026 | 50609 | 0 |
| Average service prices for October 2026 | 952 | 0 |
| Industrial Production Index- September 2026 | 1065 | 0 |
| Business Confidence Index for October 2026 | 376 | 0 |
| Road Transport Statistics 2025 | 20348 | 0 |
| ICT Access and Usage Statistics by Households and Individuals 2026 | 985 | 0 |
| GDP - Flash Estimate Q3/2026 | 264 | 0 |

## Quarantined tables

| Publication | Sheet | Status | Reason |
|---|---|---|---|
| Consumer Price Index – October 2026 | 1.1  (block 1) | review | 1/1 columns not 100, e.g. ['الأوزان* (%)/2026-10: sums to 78.1'] |
| Consumer Price Index – October 2026 | 1.1  (block 2) | review | 1/1 columns not 100, e.g. ['الأوزان* (%)/2026-10: sums to 148.9'] |
| Consumer Price Index – October 2026 | 2.1 (block 1) | fail | 1 duplicate keys, e.g. (1, '', '', '', '', '', '', '', '', '', '2026-10', None); measure type could not be determined |
| Consumer Price Index – October 2026 | 5.2 (block 0) | fail | index outside 0..5000 |
| Consumer Price Index – October 2026 | 5.3 (block 0) | fail | index outside 0..5000 |
| Wholesale Price Index – October 2026 | 2.1 (block 0) | fail | 1 duplicate keys, e.g. (0, '', '', '', '', '', 'Wholesale Price Index Time Series by Administrative Region', ' |
| Wholesale Price Index – October 2026 | 2.2 (block 0) | fail | 1 duplicate keys, e.g. (0, '', '', '', '', '', 'Time Series of Monthly Rates of Change by Administrative Regio |
| Wholesale Price Index – October 2026 | 3.1 (block 0) | review | measure type could not be determined |
| Road Transport Statistics 2025 | 1-2-1 (block 0) | fail | 11 duplicate keys, e.g. (0, '', '', '', 'الرياض / الرياض', '', '', '', '', '', '2025', None) |
| Road Transport Statistics 2025 | 1-3 (block 0) | review | measure type could not be determined |
| Road Transport Statistics 2025 | 7-1 (block 0) | review | 8/8 total checks failed, e.g. ['/2018: total 229944.82 vs sum 375076.82'] |
| Road Transport Statistics 2025 | 7-2 (block 0) | review | measure type could not be determined |
| Road Transport Statistics 2025 | 7-5 (block 0) | review | measure type could not be determined |
| Road Transport Statistics 2025 | 7-6 (block 0) | review | measure type could not be determined |
| Road Transport Statistics 2025 | 7-7 (block 0) | review | measure type could not be determined |
