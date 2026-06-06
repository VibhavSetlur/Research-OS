#!/usr/bin/env python
"""Phase 15a synthesis: aggregate 20 validation_baseline JSON reports."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path("/scratch/vsetlur/Research-OS")
BASELINE_DIR = ROOT / "docs" / "v2_handoff" / "validation_baseline"
OUT_MD = ROOT / "docs" / "V2_VALIDATION_REPORT_BASELINE.md"
OUT_CANDIDATES = ROOT / "docs" / "v2_handoff" / "never_called_candidates.json"


def load_reports() -> list[dict]:
    reports = []
    for p in sorted(BASELINE_DIR.glob("*.json")):
        with p.open() as f:
            data = json.load(f)
        data["_file"] = p.name
        reports.append(data)
    return reports


def deliverable_flag(r: dict) -> bool:
    # Different reports may use different field name; check both
    if "every_deliverable_produced" in r:
        return bool(r["every_deliverable_produced"])
    if "deliverable_produced" in r:
        return bool(r["deliverable_produced"])
    return False


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def main() -> None:
    reports = load_reports()
    n = len(reports)
    assert n == 20, f"Expected 20 reports, got {n}"

    # ---------- 1. overall averages ----------
    ratings = [r["final_rating"] for r in reports]
    high_friction_counts = [r["high_friction_count"] for r in reports]
    first_5_high = [r["first_5_turns_high_friction"] for r in reports]
    deliverable_rate = sum(1 for r in reports if deliverable_flag(r)) / n

    avg_rating = mean(ratings)
    total_high = sum(high_friction_counts)
    total_first5 = sum(first_5_high)

    # ---------- 2. per-perspective averages ----------
    by_persp: dict[str, list[dict]] = {}
    for r in reports:
        by_persp.setdefault(r["perspective"], []).append(r)
    persp_rows = []
    for persp in sorted(by_persp):
        items = by_persp[persp]
        persp_rows.append([
            persp,
            len(items),
            round(mean(r["final_rating"] for r in items), 2),
            sum(r["high_friction_count"] for r in items),
            sum(r["first_5_turns_high_friction"] for r in items),
            f"{sum(1 for r in items if deliverable_flag(r))}/{len(items)}",
        ])

    # ---------- 3. per-scenario averages ----------
    by_scen: dict[str, list[dict]] = {}
    for r in reports:
        by_scen.setdefault(r["scenario"], []).append(r)
    scen_rows = []
    for scen in sorted(by_scen):
        items = by_scen[scen]
        scen_rows.append([
            scen,
            len(items),
            round(mean(r["final_rating"] for r in items), 2),
            sum(r["high_friction_count"] for r in items),
            sum(r["first_5_turns_high_friction"] for r in items),
            f"{sum(1 for r in items if deliverable_flag(r))}/{len(items)}",
        ])

    # ---------- 4. never_called_tools union ----------
    never_called_union: set[str] = set()
    never_called_counter: Counter = Counter()
    for r in reports:
        for t in r.get("never_called_tools", []):
            # Normalize: strip parenthetical commentary, take token before " ("
            base = t.split(" (")[0].strip()
            # Also handle "X / Y / Z" forms by splitting
            for sub in base.split(" / "):
                sub = sub.strip()
                if sub:
                    never_called_union.add(sub)
                    never_called_counter[sub] += 1

    # ---------- 5. top friction categories ----------
    friction_counter: Counter = Counter()
    friction_by_category: dict[str, list[dict]] = {}
    for r in reports:
        for fi in r.get("friction_items", []):
            cat = fi.get("category", "uncategorized")
            friction_counter[cat] += 1
            friction_by_category.setdefault(cat, []).append({
                "scenario": r["scenario"],
                "perspective": r["perspective"],
                "severity": fi.get("severity", "?"),
            })
    top_friction = friction_counter.most_common(20)

    # ---------- 6. top convoluted_tools ----------
    convoluted_counter: Counter = Counter()
    for r in reports:
        for t in r.get("convoluted_tools", []):
            base = t.split(" (")[0].strip()
            # "X vs Y vs Z" -> count each
            if " vs " in base:
                for sub in base.split(" vs "):
                    sub = sub.strip()
                    if sub:
                        convoluted_counter[sub] += 1
            else:
                # split on "/" too for "X / Y"
                # but be conservative: only split when both sides start with tool_/sys_/mem_
                if " / " in base and all(
                    s.strip().startswith(("tool_", "sys_", "mem_"))
                    for s in base.split(" / ")
                ):
                    for sub in base.split(" / "):
                        sub = sub.strip()
                        if sub:
                            convoluted_counter[sub] += 1
                else:
                    convoluted_counter[base] += 1
    top_convoluted = convoluted_counter.most_common(10)

    # ---------- 7. top confusing_protocols ----------
    confusing_counter: Counter = Counter()
    for r in reports:
        for p in r.get("confusing_protocols", []):
            base = p.split(" (")[0].strip()
            confusing_counter[base] += 1
    top_confusing = confusing_counter.most_common(10)

    # ---------- write markdown ----------
    lines: list[str] = []
    lines.append("# Research-OS v2.0.0 — Baseline Validation Report (Phase 15a)")
    lines.append("")
    lines.append(
        "Synthesis of 20 baseline validation reports (5 scenarios x 4 perspectives) "
        "produced before Phase 9 consolidation. Source: "
        "`docs/v2_handoff/validation_baseline/*.json`."
    )
    lines.append("")
    lines.append("## 1. Overall averages")
    lines.append("")
    lines.append(md_table(
        ["Metric", "Value"],
        [
            ["Reports", n],
            ["Average final_rating", round(avg_rating, 2)],
            ["Total HIGH friction items", total_high],
            ["Total first-5-turn HIGH friction", total_first5],
            ["Deliverable-produced rate", f"{deliverable_rate:.0%}"],
            ["Min rating", min(ratings)],
            ["Max rating", max(ratings)],
        ],
    ))
    lines.append("")

    lines.append("## 2. Per-perspective averages")
    lines.append("")
    lines.append(md_table(
        ["Perspective", "N", "Avg rating", "Total HIGH", "Total first-5 HIGH", "Deliverable rate"],
        persp_rows,
    ))
    lines.append("")

    lines.append("## 3. Per-scenario averages")
    lines.append("")
    lines.append(md_table(
        ["Scenario", "N", "Avg rating", "Total HIGH", "Total first-5 HIGH", "Deliverable rate"],
        scen_rows,
    ))
    lines.append("")

    lines.append("## 4. Never-called tools (union across 20 reports)")
    lines.append("")
    lines.append(
        f"Total distinct tool names flagged as never-called by at least one perspective: "
        f"**{len(never_called_union)}**. Full list with frequency below; the JSON candidate "
        f"file is `docs/v2_handoff/never_called_candidates.json`."
    )
    lines.append("")
    lines.append(md_table(
        ["Tool", "# reports flagging"],
        [[t, c] for t, c in never_called_counter.most_common()],
    ))
    lines.append("")

    lines.append("## 5. Top 20 friction categories (frequency)")
    lines.append("")
    lines.append(md_table(
        ["Rank", "Category", "Frequency", "Example perspectives"],
        [
            [
                i + 1,
                cat,
                cnt,
                ", ".join(sorted({f"{x['perspective']}@{x['scenario']}" for x in friction_by_category[cat]}))[:90],
            ]
            for i, (cat, cnt) in enumerate(top_friction)
        ],
    ))
    lines.append("")

    lines.append("## 6. Top 10 convoluted tools (frequency)")
    lines.append("")
    lines.append(md_table(
        ["Rank", "Tool", "# reports flagging"],
        [[i + 1, t, c] for i, (t, c) in enumerate(top_convoluted)],
    ))
    lines.append("")

    lines.append("## 7. Top 10 confusing protocols (frequency)")
    lines.append("")
    lines.append(md_table(
        ["Rank", "Protocol", "# reports flagging"],
        [[i + 1, p, c] for i, (p, c) in enumerate(top_confusing)],
    ))
    lines.append("")

    lines.append("## 8. Headline findings")
    lines.append("")
    lines.append(
        f"- Average rating across all 20 baseline runs: **{round(avg_rating, 2)} / 10**."
    )
    lines.append(
        f"- Total HIGH-severity friction items reported: **{total_high}** "
        f"(of which **{total_first5}** hit in the first 5 turns)."
    )
    lines.append(
        f"- Distinct never-called tool candidates: **{len(never_called_union)}** "
        f"(Phase 9 should cross-reference these against actual production callers)."
    )
    lines.append(
        f"- Deliverable-produced rate: **{deliverable_rate:.0%}** — i.e. "
        f"every requested artifact landed in only ~{deliverable_rate:.0%} of runs."
    )
    lines.append("")

    OUT_MD.write_text("\n".join(lines))

    # ---------- write candidates JSON ----------
    candidates = {
        "generated_from": str(BASELINE_DIR.relative_to(ROOT)),
        "n_reports": n,
        "n_candidates": len(never_called_union),
        "phase": "15a",
        "note": (
            "Union of `never_called_tools` across all 20 baseline reports. "
            "Each entry has the number of reports that flagged it. This is the input "
            "to Phase 9 consolidation — a tool here is a *candidate* for deprecation, "
            "to be confirmed against production callers and pack adapters before removal."
        ),
        "candidates": [
            {"tool": t, "reports_flagging": c}
            for t, c in never_called_counter.most_common()
        ],
    }
    OUT_CANDIDATES.write_text(json.dumps(candidates, indent=2))

    # ---------- console summary for sub-agent stdout ----------
    print(f"avg_rating={avg_rating:.2f}")
    print(f"total_HIGH={total_high}")
    print(f"first5_HIGH={total_first5}")
    print(f"deliverable_rate={deliverable_rate:.0%}")
    print(f"never_called_candidates={len(never_called_union)}")
    print(f"reports_loaded={n}")


if __name__ == "__main__":
    main()
