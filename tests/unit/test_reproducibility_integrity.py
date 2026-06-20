"""Reproducibility re-run integrity (B1 / B4).

The reproducibility audit must compare a re-run output's fresh sha256
against the recorded baseline (the .prov.json sidecar's output.sha256,
falling back to workspace/logs/output_hashes.json) and refuse to report
``success`` when an output drifted — not gate purely on returncode.
"""

import json
from pathlib import Path

from research_os.tools.actions.audit.audit import audit_reproducibility_full
from research_os.tools.actions.state.provenance import write_output_provenance


def _make_step(root: Path, step: str = "01_repro") -> Path:
    exp = root / "workspace" / step
    (exp / "scripts").mkdir(parents=True, exist_ok=True)
    (exp / "outputs" / "figures").mkdir(parents=True, exist_ok=True)
    return exp


def test_drifted_output_is_not_reported_success(tmp_path):
    """A script whose output differs from its recorded baseline must
    downgrade status to warning and count a blocker — not 'success'."""
    exp = _make_step(tmp_path)
    out_file = exp / "outputs" / "figures" / "curve.txt"

    # The script overwrites the output with NEW (drifted) content each run.
    script = exp / "scripts" / "make_curve.py"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "step = Path(os.environ['RESEARCH_OS_STEP_DIR'])\n"
        "out = step / 'outputs' / 'figures' / 'curve.txt'\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text('DRIFTED CONTENT')\n"
    )

    # Pre-existing output + a baseline sidecar recording a DIFFERENT hash
    # (i.e. what the artefact hashed to when it was 'correctly' produced).
    out_file.write_text("BASELINE CONTENT")
    write_output_provenance(
        output_path=out_file,
        root=tmp_path,
        produced_by={"script": "scripts/make_curve.py"},
        step_id="01_repro",
    )
    # Sanity: the sidecar recorded the baseline content's hash.
    sidecar = out_file.with_name("curve.prov.json")
    recorded = json.loads(sidecar.read_text())["output"]["sha256"]
    assert recorded.startswith("sha256:") and "unavailable" not in recorded

    res = audit_reproducibility_full(tmp_path)

    assert res["status"] == "warning", (
        "a drifted re-run output must NOT report success — got "
        f"{res['status']} / {res.get('message')}"
    )
    assert res["hash_mismatches"] >= 1
    assert res["blocker_count"] >= 1
    # The script itself exited cleanly, so returncode alone would have
    # said 'success' — the mismatch is what escalates.
    assert all(r["returncode"] == 0 for r in res["results"])


def test_stable_output_with_baseline_reports_success(tmp_path):
    """An output that re-runs to the same bytes as its baseline passes."""
    exp = _make_step(tmp_path, "02_stable")
    out_file = exp / "outputs" / "figures" / "const.txt"

    script = exp / "scripts" / "make_const.py"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "step = Path(os.environ['RESEARCH_OS_STEP_DIR'])\n"
        "out = step / 'outputs' / 'figures' / 'const.txt'\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text('STABLE')\n"
    )
    # Baseline matches what the script will reproduce.
    out_file.write_text("STABLE")
    write_output_provenance(
        output_path=out_file,
        root=tmp_path,
        produced_by={"script": "scripts/make_const.py"},
        step_id="02_stable",
    )

    res = audit_reproducibility_full(tmp_path)
    assert res["status"] == "success", res.get("message")
    assert res["hash_mismatches"] == 0


def test_no_baseline_does_not_falsely_pass_as_verified(tmp_path):
    """With no sidecar / output_hashes.json, the audit must disclose that
    bit-stability was not verified rather than silently 'succeeding'."""
    exp = _make_step(tmp_path, "03_nobaseline")
    script = exp / "scripts" / "make.py"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "step = Path(os.environ['RESEARCH_OS_STEP_DIR'])\n"
        "out = step / 'outputs' / 'figures' / 'x.txt'\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text('whatever')\n"
    )
    res = audit_reproducibility_full(tmp_path)
    # No mismatch (nothing to compare), but the message + report must say
    # bit-stability was not verified, and outputs_without_baseline > 0.
    assert res["hash_mismatches"] == 0
    assert res["outputs_without_baseline"] >= 1
    report = (tmp_path / "workspace" / "logs" / "reproducibility_report.md")
    # Report path may live under the active step; read whatever was written.
    rp = tmp_path / res["report_path"]
    text = rp.read_text() if rp.exists() else (report.read_text() if report.exists() else "")
    assert "bit-stability" in text.lower() or "no baseline" in text.lower()


def test_output_hashes_json_fallback_detects_drift(tmp_path):
    """When no sidecar exists, the project-wide output_hashes.json baseline
    is used and a mismatch is still caught (B1 fallback path)."""
    exp = _make_step(tmp_path, "04_fallback")
    out_file = exp / "outputs" / "figures" / "y.txt"
    script = exp / "scripts" / "make_y.py"
    script.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "step = Path(os.environ['RESEARCH_OS_STEP_DIR'])\n"
        "out = step / 'outputs' / 'figures' / 'y.txt'\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text('NEW')\n"
    )
    out_file.write_text("OLD")
    # Record a baseline in output_hashes.json keyed by root-relative path,
    # but deliberately NOT matching what the script will write.
    logs = tmp_path / "workspace" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    rel = "workspace/04_fallback/outputs/figures/y.txt"
    (logs / "output_hashes.json").write_text(
        json.dumps({rel: "sha256:deadbeef" + "0" * 56})
    )

    res = audit_reproducibility_full(tmp_path)
    assert res["status"] == "warning"
    assert res["hash_mismatches"] >= 1
    # Confirm the baseline source was the json fallback.
    sources = {
        c["baseline_source"]
        for r in res["results"]
        for c in r.get("hash_checks", [])
    }
    assert "output_hashes.json" in sources
