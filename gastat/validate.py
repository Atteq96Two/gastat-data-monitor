"""Validation gates. Status: pass | review (cannot tell if data or parsing is wrong) | fail (technical error)."""
import math, re, collections

TOL_REL, TOL_ABS = 0.006, 0.6   # rounding tolerance: 0.6% or 0.6 units


def close(a, b):
    return abs(a - b) <= max(TOL_ABS, TOL_REL * max(abs(a), abs(b)))


def validate_table(rows, skip=()):
    checks, status = [], "pass"

    def add(name, ok, detail="", level="fail"):
        nonlocal status
        if name in skip:
            checks.append(dict(check=name, ok=True, detail="skipped by reviewed recipe: " + detail[:80]))
            return
        checks.append(dict(check=name, ok=ok, detail=detail))
        if not ok:
            status = level if (status == "pass" or level == "fail") else status
    if not rows:
        return "fail", [dict(check="has_rows", ok=False, detail="no numeric values")]
    add("numeric_values", all(isinstance(r["value"], float) and math.isfinite(r["value"]) for r in rows))
    add("period_present", all(r["period"] for r in rows), "missing reference period")
    keys = collections.Counter((r["block"], r["row_code"], r["row_level"], r["col_code"], r["row_label_ar"], r["row_label_en"], r["row_group"], r["row_unit"],
                                r["col_label_ar"], r["col_label_en"], r["col_sub"], r["period"], r["base_period"]) for r in rows)
    dups = [k for k, n in keys.items() if n > 1]
    add("no_duplicate_keys", not dups, f"{len(dups)} duplicate keys, e.g. {dups[0] if dups else ''}")
    # range checks by measure type
    for mt in {r["measure_type"] for r in rows}:
        vs = [r["value"] for r in rows if r["measure_type"] == mt]
        if mt == "index":
            add("range_index", all(0 < v < 5000 for v in vs), "index outside 0..5000")
        elif mt in ("share", "weight", "distribution", "multi_response"):
            add("range_share_0_100", all(-0.5 <= v <= 100.5 for v in vs), "share outside 0..100", "review")
        elif mt == "rate":
            add("range_rate", all(abs(v) < 1000 for v in vs), "rate beyond +-1000", "review")
    # distributions: every column sums to 100 (rows are categories). Percentages: total lies between components.
    grp = collections.defaultdict(list)
    for r in rows:
        if r["col_sub"]:   # flattened header: each row x second dimension is its own distribution
            grp[(r["block"], r["row_label_ar"] + "|" + r["row_group"], r["col_sub"], r["period"], r["base_period"], r["measure_type"])].append(r)
        else:
            grp[(r["block"], r["col_label_ar"], r["col_label_en"], r["period"], r["base_period"], r["measure_type"])].append(r)
    dist_fail, dist_n, multi, pct_fail, pct_n = [], 0, 0, [], 0
    for key, rs in grp.items():
        mt = key[-1]
        comp = [r for r in rs if not r["is_total_row"]]
        tot = [r for r in rs if r["is_total_row"]]
        if mt in ("distribution", "weight") and len(comp) >= 2 and (comp[0]["col_sub"] or (not any(r["row_level"] for r in comp) and len({len(r["row_code"]) for r in comp}) <= 1)):
            dist_n += 1
            sm = sum(r["value"] for r in comp)
            if abs(sm - 100) > 1.5 and not (tot and abs(tot[0]["value"] - 100) < 0.5 and abs(sm - 100) <= 2.5):
                dist_fail.append(f"{key[1] or key[2]}|{key[3]}: sums to {sm:.1f}")
        elif mt == "percentage":
            vs = [r["value"] for r in comp]
            if len(vs) >= 2 and sum(vs) > 100.5 and not tot:
                multi += 1  # sums above 100: multi-response style, range check only
            if len(tot) == 1 and len(vs) >= 2:
                pct_n += 1
                t0 = tot[0]["value"]
                if t0 in (1.0, 100.0) or abs(t0 - 100) < 0.6 or abs(t0 - 1) < 0.006:
                    if abs(sum(vs) - t0) <= max(0.6, 0.006 * t0) + 0.05 * len(vs):
                        continue  # shares of a whole: components sum to the total (100% or 1.0)
                if not (min(vs) - 0.6 <= t0 <= max(vs) + 0.6):
                    pct_fail.append(f"{key[1] or key[2]}|{key[3]}: total {tot[0]['value']} outside {min(vs)}..{max(vs)}")
    if dist_n:
        add("distribution_sums_100", not dist_fail, f"{len(dist_fail)}/{dist_n} columns not 100, e.g. {dist_fail[:1]}", "review")
    if pct_n:
        add("percentage_total_between_components", not pct_fail, f"{len(pct_fail)}/{pct_n} failed, e.g. {pct_fail[:1]}", "review")
    if multi:
        checks.append(dict(check="multi_response_detected", ok=True, detail=f"{multi} column(s) sum above 100: range check only"))
    if any(r["measure_type"] == "percentage" for r in rows):
        add("range_percentage_0_100", all(-0.5 <= r["value"] <= 100.5 for r in rows if r["measure_type"] == "percentage"), "percentage outside 0..100", "review")
    # hierarchy reconciliation: each parent equals the sum of its direct children (levels or code lengths)
    hier_fail, hier_n = [], 0
    by_col = collections.defaultdict(list)
    for r in rows:
        by_col[(r["block"], r["col_label_ar"], r["col_label_en"], r["period"], r["base_period"], r["measure_type"])].append(r)
    for key, rs in by_col.items():
        if key[-1] not in ("level", "weight", "distribution"):
            continue
        rs = sorted(rs, key=lambda r: r["source_row"])
        if any(r["row_level"] for r in rs):
            lv = [int(r["row_level"]) if str(r["row_level"]).isdigit() else None for r in rs]
        elif all(re.fullmatch(r"\d+(\.\d+)*", r["row_code"].split("|")[-1]) for r in rs) and any("." in r["row_code"] for r in rs):
            lv = [r["row_code"].split("|")[-1].count(".") for r in rs]  # dotted codes only: 1, 1.1, 1.1.2
        else:
            continue
        if None in lv or len(set(lv)) < 2:
            continue
        for i, r in enumerate(rs):
            kids, j = [], i + 1
            while j < len(rs) and lv[j] > lv[i]:
                if lv[j] == lv[i] + 1:
                    kids.append(rs[j]["value"])
                j += 1
            if len(kids) >= 2:
                hier_n += 1
                if abs(sum(kids) - r["value"]) > max(0.6, 0.006 * abs(r["value"]), 0.05 * len(kids)):
                    hier_fail.append(f"{r['row_label_ar'] or r['row_label_en']}|{key[1] or key[2]}|{key[3]}: {r['value']:.2f} vs children {sum(kids):.2f}")
    if hier_n:
        add("hierarchy_parent_equals_children", len(hier_fail) <= 0.02 * hier_n, f"{len(hier_fail)}/{hier_n} parents differ, e.g. {hier_fail[:2]}", "review")
        checks[-1]["hier_checked"] = hier_n
    # reconciliation: weights and levels against a total row / total column
    by_block = collections.defaultdict(list)
    for r in rows:
        by_block[(r["block"], r["col_label_ar"], r["col_label_en"], r["period"], r["base_period"], r["measure_type"])].append(r)
    recon, recon_fail, recon_n = 0, [], 0
    for key, rs0 in by_block.items():
        mt = key[-1]
        if mt != "level":
            continue
        parents = collections.defaultdict(list)
        for r in rs0:
            parents[r.get("row_parent", "")].append(r)
        units = list(parents.values())
        if len(units) > 1 and not any(len([r for r in u if r["is_total_row"]]) == 1 and len([r for r in u if not r["is_total_row"]]) >= 2 for u in units):
            units = [rs0]   # no group carries its own total: try the whole table
        for rs in units:
            tot = [r for r in rs if r["is_total_row"]]
            comp = [r for r in rs if not r["is_total_row"]]
            if len(tot) != 1 or len(comp) < 2:
                continue
            t = tot[0]["value"]
            tops = [r for r in comp if len(r["row_code"]) <= min((len(x["row_code"]) for x in comp if x["row_code"]), default=0) or not r["row_code"]]
            cands = [sum(r["value"] for r in comp), sum(r["value"] for r in tops) if tops else None]
            recon_n += 1
            if any(c is not None and close(c, t) for c in cands):
                recon += 1
            else:
                recon_fail.append(f"{key[1] or key[2]}|{key[3]}: total {t:.2f} vs sum {cands[0]:.2f}")
    if recon_n:
        add("totals_reconcile", not recon_fail, f"{len(recon_fail)}/{recon_n} total checks failed, e.g. {recon_fail[:1]}", "review")
    else:
        checks.append(dict(check="totals_reconcile", ok=True, detail="no single total row to reconcile (not applicable)"))
    nounit = [r for r in rows if r["measure_type"] in ("level", "ratio") and not r["unit"]]
    if nounit:
        add("unit_known", False, f"{len(nounit)} values are quantities with no unit in the header, title, footnote or unit column", "review")
    if any(r["measure_type"] == "unknown" for r in rows):
        add("measure_type_known", False, "measure type could not be determined", "review")
    return status, checks
