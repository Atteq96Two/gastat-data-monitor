# Using the GASTAT Data Monitor from the News Tracker

الخلاصة بالعربية: يقرأ News Tracker ملفات JSON عامة من هذا المستودع ليحكم على ادعاء ضيف في البرنامج بأحد أربعة أحكام: **يؤيده، يناقضه، بيانات غير كافية، بيانات قديمة**. لا يُعدَّل News Tracker من هنا، ولا حاجة لمفاتيح أو حساب. كل حكم يُرفق بالخلية الأصلية في ملف الهيئة العامة للإحصاء وتاريخ نشر البيانات.

This repository does **not** change the News Tracker. It only publishes files the News Tracker can read. Everything below is read-only and needs no key or login.

## 1. What to read

Base URL (always the latest committed version): `https://raw.githubusercontent.com/Atteq96Two/gastat-data-monitor/main/`
The same files are served by the Vercel site (`https://gastat-data-monitor-web.vercel.app`) under `/data/` (series and catalog) if you prefer that host.

| File | Use |
|---|---|
| `catalog/catalog.json` | One entry per stored table (40 today): title (Arabic and English), release it came from, `release_date`, `frequency`, `first_period`, `last_period`, units, `keywords` (first 30 item names), `freshness` (`status`, `last_release`, `expected_next`, `calendar_next`), download links. Read `generated_at` and `coverage` first. |
| `catalog/search_index.json` | Every item name of every table, for keyword matching: `labels[dataset_id] = [names]`. |
| `web/data/series/<dataset_id>.json` | The numbers. `periods` (sorted), `sheet`, and `series[]`, each with `label`, `label_en`, `measure` (index, level, rate, share, weight, distribution...), `unit`, `unit_text`, `unit_ok`, `base` (comparison period of a published rate), `values` (aligned with `periods`, `null` = none) and `cells` (the cell in GASTAT's Excel file for each value, `R9C48`; the sheet is `sheet`). |
| `data/<domain>/<dataset_id>.parquet` or `.csv` | The full tidy table, if you need every column (period, unit, scale, source cell, release date). |
| `catalog/insights/<publication_id>.json` | Computed headline numbers of a release (useful for "what is new" stories, not needed for verdicts). |
| `registry/revisions.jsonl` | Every value GASTAT changed after publishing it (old value, new value). Check it when a verdict is old. |

**Coverage today:** monthly and quarterly economic releases published from 2026-11-01 (annual, environment and social reports are out of scope by the owner's decision). Earlier releases (January to October 2026) are registered as titles only until the backfill is approved. A claim about an older period gets `insufficient_data`, never a guess.

## 2. The four verdicts

| Verdict | Meaning | Typical reason |
|---|---|---|
| `supports` | GASTAT's published number agrees with the claim within rounding (or has the stated direction). | "inflation was 1.7%" and the file says 1.700148. |
| `contradicts` | GASTAT's number is there and differs from the claim beyond rounding (or has the opposite direction). | "inflation was 3%" or "confidence rose" when the index fell 1.92%. |
| `insufficient_data` | The data cannot decide. Never use this as a soft "false". | No matching indicator, several different series match, the period is not in the data, no comparison period for a change, the unit is not settled, or the claim has no number or direction. |
| `data_too_old` | The claim is about a period GASTAT has not published yet, or the newest data is more than one full cycle (month, quarter, year, plus 10 days) before the date of the claim. | "December inflation was 2%" when the newest data is October, or a "latest" claim made three months after the last release. |

Decision order (the reference code follows exactly this):
1. Resolve the indicator to one series (section 3). Nothing found: `insufficient_data`. Several series that give different answers: `insufficient_data` with the candidates listed.
2. Take the claim's period (default: the newest period the series has).
3. Period after the newest period, or no period given and the newest release is more than one cycle + 10 days older than the claim date: `data_too_old`.
4. Period not in the series, or the comparison period for a change is missing: `insufficient_data`.
5. Compute the metric (value, change on the previous period, change on the same period a year earlier).
6. Compare with the claim: `supports` or `contradicts`.

## 3. Matching an indicator without guessing

Reference implementation: `gastat/verdict.py` (`check_claim(claim)`), with 14 test cases in `tests/test_verdict.py`. Claim fields:

```json
{
  "query": "الرقم القياسي لأسعار المستهلك",
  "dataset_id": "consumer-price-index_1-1",
  "series": "الرقم القياسي العام",
  "column": "معدل أكتوبر 2025",
  "period": "2026-10",
  "metric": "value",
  "claimed": 1.7,
  "as_of": "2026-11-17"
}
```

- `query` words must all appear in the table title, its release title or an item name (Arabic text is normalized: hamza, tashkeel, ta marbuta). `dataset_id` skips the search.
- `series` is the item name inside the table. An exact item-name match wins over partial matches. `column` narrows to the column of that item.
- If several series still match, the checker evaluates all of them. If they give the **same** answer (the headline index appears in a summary table and in a detail table) it is one answer (`agreeing_series` says how many). If they differ it returns `insufficient_data` with the candidates, so the News Tracker can ask for a narrower claim instead of picking one.
- Rates already published by GASTAT (for example the yearly change of the price index) are separate series with a `base` period. Prefer them over recomputing: they are GASTAT's own number.

## 4. Numbers, rounding and units

- A claim stated with `d` decimals matches within half of its last digit: 1.7 matches 1.65 to 1.75, 1.70 matches 1.695 to 1.705. Pass `tolerance` to override.
- `change_prev` / `change_yoy`: for indices and quantities the change is in **percent** of the earlier value; for rates, shares and weights it is the difference in **percentage points**.
- `direction`: `up` and `down` require a change larger than the tolerance; `flat` requires it to be within the tolerance.
- Units are shown in `unit_text` (`%`, `نقطة`, `ريال`...). Series with `unit_ok: false` have a unit that the source does not settle; numeric claims on them return `insufficient_data` (direction claims still work).
- Values in the series files keep 7 significant digits. The exact value is in the Parquet or CSV table and in the Excel cell named by `cells`.
- Some tables hold fractions of 1 (for example the Business Confidence monthly rates). The series files already show them in percent; the stored table keeps the original with `unit = fraction`.

## 5. What to keep with each verdict

Store these so any verdict can be re-checked and shown to the audience:

```json
{
  "verdict": "supports",
  "reason": "October 2026 value: data says 1.7001, claim says 1.7",
  "computed": 1.700148,
  "tolerance": 0.05,
  "period": "2026-10",
  "data_as_of": "2026-11-15",
  "dataset_id": "consumer-price-index_1-1",
  "series": "الرقم القياسي العام | معدل التغيّر (مقارنة مع أكتوبر 2025)",
  "evidence": [{"period": "2026-10", "value": 1.700148, "cell": "1.1 !R15C7"}],
  "source": "الهيئة العامة للإحصاء / General Authority for Statistics (stats.gov.sa)"
}
```

Always show the source line. `data_as_of` is the release date, so a verdict can say "according to GASTAT data published on 15 November 2026".

## 6. Timing and change

- GASTAT publishes in the morning (Riyadh). The monitor checks every 15 minutes from 08:45 to 12:00 on release days and hourly otherwise, and rebuilds the catalog and series files after each new release. Check `generated_at` in `catalog/catalog.json`.
- GASTAT sometimes republishes a file with changed values. Such changes are never silent: they are appended to `registry/revisions.jsonl` (old and new value). When a stored verdict is older than the newest `generated_at`, re-check it.
- `freshness.status` of a table: `current` (inside its cycle), `scheduled` (next release is on GASTAT's calendar), `overdue` (a full cycle plus 10 days passed without a release in the registry).
- Known open issues (a source inconsistency, unit text, naming) are listed in `registry/known_issues.json` and on the quality page.

## 7. Rules for the News Tracker

1. Do not turn `insufficient_data` or `data_too_old` into "false". They mean the claim could not be settled with this data.
2. Do not average or merge different series to reach an answer. If they differ, ask for a narrower claim.
3. Do not edit these files. Re-run the checker when new data arrives.
4. Credit GASTAT wherever a verdict is shown.

## 8. Trying it

```bash
python3 -I gastat/verdict.py '{"query":"ثقة الأعمال","dataset_id":"business-confidence-index-for_2","series":"مؤشر ثقة الأعمال العام","period":"2026-10","metric":"change_prev","direction":"up","as_of":"2026-11-17"}'
```

returns `contradicts` (the index fell 1.92% from September to October 2026; cells `2!R9C48` and `2!R9C47`). Run `python3 -I tests/test_verdict.py` to see all four verdicts on real data, and to confirm that every evidence cell equals the cell in GASTAT's Excel file.
