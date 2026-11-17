# Runbook: what to do when an alert arrives

All alerts come from the address configured in the repository secrets and start with "[GASTAT monitor]". GitHub also emails you if a workflow run fails, as a backup.

| Alert subject | What it means | What to do |
|---|---|---|
| Attention needed: new release | A new publication arrived. Some tables have a layout the system has never seen, or failed a validation gate. They are quarantined, not published. The rest of the release is published normally. | Open Claude Code in the `gastat-data-monitor` folder and say: **resolve quarantine**. Claude reads `quarantine/<id>.json`, shows you the ambiguous tables in plain language, asks you the questions, records your answers in `recipes/`, reruns, and publishes. |
| Health check failed: "site structure changed" | GASTAT changed its website data format. Nothing can be collected until the reader is updated. | Say in Claude Code: **fix the collector, health check failed**. Nothing is lost. The next run catches up. |
| Health check failed: "endpoint unreachable" | The site or its data feed is down or blocking. | Usually temporary. If it repeats on two days in a row, say: **investigate GASTAT access**. |
| Health check failed: "scheduled release not seen yet" | The release calendar promised a publication that has not appeared in our register. | Check the GASTAT site. If it is published, say: **missing release**. If not, GASTAT is late and nothing is needed. |
| Health check failed: "collector last succeeded N hours ago" | The scheduled job stopped running. | Open the Actions tab of the repository, check the `collect` workflow, and say: **collector stalled**. |
| Collector run failed | One run crashed. The next run retries on its own. | Do nothing unless it repeats three times in a row. |

## Revisions
When GASTAT republishes a file with changed numbers, the old and new values are written to `registry/revisions.jsonl`. Nothing is overwritten silently.

## Secrets (set once, by you)
`GMAIL_USER`, `GMAIL_APP_PASSWORD` and `ALERT_TO` in the repository secrets. The recipient is a secret because this repository is public.

## Insights and re-running the engine (Phase 4)

- Insights are written to `catalog/insights/` after every ingest. If one fails, the ingest still succeeds and the alert email says "insights not computed".
- After any change to the extraction engine: `python3 -I gastat/reingest.py` (dry run, lists datasets that would change), then `--apply`, then `python3 -I gastat/insights.py --all` and `python3 -I tests/test_insights.py`.
