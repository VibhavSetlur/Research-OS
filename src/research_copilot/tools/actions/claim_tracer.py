#!/usr/bin/env python3
"""Claim Tracer — builds claim-to-evidence graph for the entire manuscript.

Every factual claim must be traceable to computed data or a verified citation.

Usage:
    python .research/scripts/utils/claim_tracer.py --manuscript 03_synthesis/manuscript/research_findings.md
    python .research/scripts/utils/claim_tracer.py --manuscript ... --data-lineage docs/data_lineage.json
    python .research/scripts/utils/claim_tracer.py --manuscript ... --citation-report 00_inputs/literature/citation_verification_report.json
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


from research_copilot.utils.common import find_project_root


def load_json(path: Path) -> Optional[dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def file_hash(path: Path) -> Optional[str]:
    if path.exists() and path.is_file():
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    return None


# ── Claim Extraction ─────────────────────────────────────────────────────

def extract_claims_from_manuscript(path: Path) -> list[dict]:
    """Extract all factual claims from a manuscript markdown file."""
    try:
        content = path.read_text()
    except FileNotFoundError:
        return []

    claims = []
    lines = content.split("\n")
    claim_id = 0

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("---"):
            continue

        # Statistical claims: numbers with statistical context
        stat_patterns = [
            (r"r\s*=\s*([-\d.]+)", "statistical_correlation"),
            (r"([Rr]²|[Rr]-squared)\s*=?\s*([-\d.]+)", "statistical_r_squared"),
            (r"p\s*[<>=]\s*([\d.]+)", "statistical_pvalue"),
            (r"([-\d.]+)%\s*(?:confidence\s*interval|CI)", "statistical_ci"),
            (r"(?:effect\s*size|Cohen['']?\s*d)\s*=?\s*([-\d.]+)", "statistical_effect_size"),
            (r"(?:mean|average)\s*(?:of\s*)?([-\d.]+)", "statistical_mean"),
            (r"(?:n|N|sample)\s*=?\s*(\d+)", "statistical_sample_size"),
            (r"([-\d.]+)\s*±\s*([-\d.]+)", "statistical_mean_sd"),
        ]

        for pattern, claim_type in stat_patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                claim_id += 1
                claims.append({
                    "id": f"claim_{claim_id:03d}",
                    "text": line[:200],
                    "type": claim_type,
                    "location": f"{path.name}:line_{line_num}",
                    "matched_value": match.group(0),
                    "line": line_num,
                })

        # Literature claims: citations with claims
        citation_patterns = [
            (r"(?:Prior\s+studies|Previous\s+research|Earlier\s+work)\s+(?:show|found|report|suggest)[^.]*(?:DOI[:\s]+)?(10\.\d{4,}[^\s\"'\]]+)", "literature_prior_work"),
            (r"(?:consistent\s+with|aligns?\s+with|supports?)\s+[^.]*?(?:DOI[:\s]+)?(10\.\d{4,}[^\s\"'\]]+)", "literature_consistent"),
            (r"(?:contradicts?\|differs?\s+from)\s+[^.]*?(?:DOI[:\s]+)?(10\.\d{4,}[^\s\"'\]]+)", "literature_contradiction"),
        ]

        for pattern, claim_type in citation_patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                claim_id += 1
                claims.append({
                    "id": f"claim_{claim_id:03d}",
                    "text": line[:200],
                    "type": claim_type,
                    "location": f"{path.name}:line_{line_num}",
                    "matched_value": match.group(0),
                    "line": line_num,
                })

        # DOI references (standalone)
        doi_matches = re.finditer(r"(10\.\d{4,}[^\s\"'\)\]]+)", line)
        for match in doi_matches:
            already_found = any(c["line"] == line_num and c["type"].startswith("literature") for c in claims)
            if not already_found:
                claim_id += 1
                claims.append({
                    "id": f"claim_{claim_id:03d}",
                    "text": line[:200],
                    "type": "citation_reference",
                    "location": f"{path.name}:line_{line_num}",
                    "matched_value": match.group(0),
                    "line": line_num,
                })

        # arXiv references
        arxiv_matches = re.finditer(r"(?:arXiv[:\s]+)?(\d{4}\.\d{4,5}(?:v\d+)?)\b", line)
        for match in arxiv_matches:
            claim_id += 1
            claims.append({
                "id": f"claim_{claim_id:03d}",
                "text": line[:200],
                "type": "arxiv_reference",
                "location": f"{path.name}:line_{line_num}",
                "matched_value": match.group(0),
                "line": line_num,
            })

    return claims


# ── Trace Building ───────────────────────────────────────────────────────

def trace_statistical_claim(claim: dict, data_lineage: Optional[dict], root: Path) -> dict:
    """Trace a statistical claim back to its data source."""
    trace = {
        "source_type": "computed_data",
        "source_file": None,
        "data_file": None,
        "data_hash": None,
        "raw_file": None,
        "raw_hash": None,
        "script": None,
        "verified": False,
    }

    # Look for analysis result files
    analysis_dir = root / "03_synthesis" / "analysis"
    if analysis_dir.exists():
        for q_dir in analysis_dir.iterdir():
            if q_dir.is_dir():
                for result_file in q_dir.glob("*.json"):
                    try:
                        with open(result_file) as f:
                            results = json.load(f)
                        # Check if the claimed value exists in results
                        result_str = json.dumps(results)
                        if claim["matched_value"] in result_str:
                            trace["source_file"] = str(result_file.relative_to(root))
                            trace["verified"] = True
                            break
                    except (json.JSONDecodeError, OSError):
                        continue
                if trace["source_file"]:
                    break

    # Trace through data lineage
    if data_lineage:
        datasets = data_lineage.get("datasets", data_lineage.get("transformations", []))
        if isinstance(datasets, list):
            for ds in datasets:
                if isinstance(ds, dict):
                    output = ds.get("output", ds.get("output_file", ""))
                    if output and trace.get("source_file") and output in trace["source_file"]:
                        trace["data_file"] = ds.get("input", ds.get("input_file", ""))
                        if trace["data_file"]:
                            data_path = root / trace["data_file"]
                            trace["data_hash"] = file_hash(data_path)
                        break

    # Check for raw data files
    raw_dir = root / "00_inputs" / "raw_data"
    if raw_dir.exists():
        raw_files = list(raw_dir.glob("*"))
        if raw_files:
            trace["raw_file"] = str(raw_files[0].relative_to(root))
            trace["raw_hash"] = file_hash(raw_files[0])

    # Check for analysis scripts
    scripts_dir = root / "scripts"
    if scripts_dir.exists():
        analysis_scripts = sorted(scripts_dir.glob("[0-9]*analysis*.py"))
        if analysis_scripts:
            trace["script"] = str(analysis_scripts[0].relative_to(root))

    return trace


def trace_citation_claim(claim: dict, citation_report: Optional[dict]) -> dict:
    """Trace a citation claim to its verification status."""
    trace = {
        "source_type": "literature",
        "identifier": None,
        "crossref_verified": False,
        "content_verified": False,
        "retraction_status": "unknown",
        "verified": False,
    }

    # Extract DOI or arXiv ID from claim
    doi_match = re.search(r"(10\.\d{4,}[^\s\"'\)\]]+)", claim.get("matched_value", ""))
    arxiv_match = re.search(r"(\d{4}\.\d{4,5})", claim.get("matched_value", ""))

    if doi_match:
        trace["identifier"] = doi_match.group(1)
    elif arxiv_match:
        trace["identifier"] = arxiv_match.group(1)

    if not trace["identifier"]:
        return trace

    # Check against citation verification report
    if citation_report:
        for cited in citation_report.get("citations", []):
            if cited.get("identifier") == trace["identifier"]:
                p1 = cited.get("pass_1", {})
                p2 = cited.get("pass_2", {})
                p3 = cited.get("pass_3", {})
                trace["crossref_verified"] = p1.get("status") == "verified"
                trace["content_verified"] = p2.get("status") == "supported"
                trace["retraction_status"] = p3.get("status", "unknown")
                trace["verified"] = (
                    trace["crossref_verified"]
                    and trace["content_verified"]
                    and trace["retraction_status"] == "clear"
                )
                break

    return trace


def trace_claim(claim: dict, data_lineage: Optional[dict], citation_report: Optional[dict], root: Path) -> dict:
    """Build a complete trace for a single claim."""
    if claim["type"].startswith("statistical"):
        return trace_statistical_claim(claim, data_lineage, root)
    elif claim["type"].startswith("literature") or claim["type"] in ("citation_reference", "arxiv_reference"):
        return trace_citation_claim(claim, citation_report)
    else:
        return {
            "source_type": "unknown",
            "verified": False,
            "error": f"No trace method for claim type: {claim['type']}",
        }


# ── Main Pipeline ────────────────────────────────────────────────────────

def run_claim_tracing(
    manuscript_path: Path,
    data_lineage: Optional[dict],
    citation_report: Optional[dict],
    output_path: Path,
    root: Path,
) -> dict:
    """Run full claim tracing pipeline."""
    claims = extract_claims_from_manuscript(manuscript_path)

    if not claims:
        print("  No claims found in manuscript.")
        report = {
            "schema_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_claims": 0,
            "summary": {"fully_traced": 0, "partially_traced": 0, "unsupported": 0},
            "verdict": "PASS",
            "claims": [],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        return report

    traced_claims = []
    for i, claim in enumerate(claims):
        print(f"  [{i+1}/{len(claims)}] Tracing: {claim['type']} at {claim['location']}")
        trace = trace_claim(claim, data_lineage, citation_report, root)
        claim["trace"] = trace

        if trace.get("verified"):
            claim["status"] = "fully_traced"
        elif trace.get("source_type") and trace["source_type"] != "unknown":
            claim["status"] = "partially_traced"
        else:
            claim["status"] = "unsupported"

        traced_claims.append(claim)

    summary = {
        "fully_traced": sum(1 for c in traced_claims if c["status"] == "fully_traced"),
        "partially_traced": sum(1 for c in traced_claims if c["status"] == "partially_traced"),
        "unsupported": sum(1 for c in traced_claims if c["status"] == "unsupported"),
    }

    if summary["unsupported"] > 0:
        verdict = "FAIL"
    elif summary["partially_traced"] > 0:
        verdict = "CONDITIONAL"
    else:
        verdict = "PASS"

    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_claims": len(traced_claims),
        "summary": summary,
        "verdict": verdict,
        "claims": traced_claims,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    return report


def print_report_summary(report: dict) -> None:
    """Print a human-readable summary of the claim trace report."""
    print()
    print("=" * 60)
    print("CLAIM TRACE REPORT")
    print("=" * 60)
    print()
    print(f"  Total claims: {report['total_claims']}")
    print(f"  Verdict: {report['verdict']}")
    print()
    summary = report["summary"]
    print(f"  Fully traced:    {summary['fully_traced']}")
    print(f"  Partially traced: {summary['partially_traced']}")
    print(f"  Unsupported:     {summary['unsupported']}")
    print()

    for claim in report["claims"]:
        status_icon = {
            "fully_traced": "✓",
            "partially_traced": "?",
            "unsupported": "✗",
        }.get(claim["status"], "?")
        print(f"  {status_icon} [{claim['type']}] {claim['text'][:80]}")
        print(f"    Location: {claim['location']}")
        trace = claim.get("trace", {})
        print(f"    Source: {trace.get('source_type', 'unknown')}")
        if trace.get("identifier"):
            print(f"    ID: {trace['identifier']}")
        print(f"    Verified: {trace.get('verified', False)}")
        if claim["status"] == "unsupported":
            print(f"    ⚠ UNSUPPORTED — must be removed or traced")
        print()


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Claim Tracer — Evidence Graph Builder")
    parser.add_argument("--manuscript", type=str, required=True, help="Path to manuscript markdown file")
    parser.add_argument("--data-lineage", type=str, help="Path to data lineage JSON")
    parser.add_argument("--citation-report", type=str, help="Path to citation verification report JSON")
    parser.add_argument("--output", type=str, help="Output report path (default: 03_synthesis/audit/claim_trace_report.json)")
    args = parser.parse_args()

    root = find_project_root()

    manuscript_path = Path(args.manuscript) if Path(args.manuscript).is_absolute() else root / args.manuscript

    data_lineage = None
    if args.data_lineage:
        dl_path = Path(args.data_lineage) if Path(args.data_lineage).is_absolute() else root / args.data_lineage
        data_lineage = load_json(dl_path)

    citation_report = None
    if args.citation_report:
        cr_path = Path(args.citation_report) if Path(args.citation_report).is_absolute() else root / args.citation_report
        citation_report = load_json(cr_path)

    output_path = Path(args.output) if args.output else root / "03_synthesis" / "audit" / "claim_trace_report.json"
    if not output_path.is_absolute():
        output_path = root / output_path

    if not manuscript_path.exists():
        print(f"ERROR: Manuscript not found: {manuscript_path}")
        sys.exit(1)

    print(f"Tracing claims from: {manuscript_path}")
    report = run_claim_tracing(manuscript_path, data_lineage, citation_report, output_path, root)
    print_report_summary(report)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
