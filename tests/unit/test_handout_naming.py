"""v1.11.1 — handout filename naming is the dot form.

The v1.10 surface ended up writing slides/poster handouts with two
different stems: ``slides_handout.pdf`` (underscore) in the writer
code, but ``slides.handout.pdf`` (dot) in the reference-project
manifests + smoke runners. This test pins the dot form across:

  1. the slide compiler (``compile_slides``) — both engines.
  2. the poster compiler (``compile_poster``).
  3. the manifest fixtures that declare ``print_handout_emitted`` /
     ``handout_pdf_emitted`` — they must use the dot form.

The dot form (``<stem>.handout.<ext>``) matches the existing
``<stem>.caption.md`` / ``<stem>.summary.md`` sidecar convention:
the suffix after the dot is a variant marker on the same stem,
not a separate filename.

When the ``typst`` CLI is not installed, the compile half of the
test skips (CI parity with ``test_slides_engine.py``).
"""
from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest
import yaml

from research_os.tools.actions.synthesis.slides import compile_slides

HAS_TYPST = shutil.which("typst") is not None

# Tiny 1x1 PNG fixture (kept self-contained — no shared conftest needed).
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEX///+nxBvI"
    "AAAAC0lEQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES_ROOT = _REPO_ROOT / "tests" / "fixtures" / "projects"
_SRC_ROOT = _REPO_ROOT / "src" / "research_os"


# ── 1. Source-level: writer uses the dot form ────────────────────────


def test_slides_writer_uses_dot_form_filenames():
    """Static guard against regressing to ``slides_handout.pdf``."""
    slides_src = _SRC_ROOT / "tools" / "actions" / "synthesis" / "slides.py"
    text = slides_src.read_text(encoding="utf-8")
    # Must reference the dot-form paths the manifests expect.
    assert '"slides.handout.pdf"' in text, (
        "slides.py must write the handout PDF as slides.handout.pdf"
    )
    assert '"slides.handout.typ"' in text, (
        "slides.py must write the handout source as slides.handout.typ"
    )
    # Must NOT reference the legacy underscore form anywhere in code.
    assert '"slides_handout.pdf"' not in text, (
        "slides.py still references the legacy slides_handout.pdf"
    )
    assert '"slides_handout.typ"' not in text, (
        "slides.py still references the legacy slides_handout.typ"
    )


def test_poster_writer_uses_dot_form_filenames():
    """Static guard against regressing to ``poster_handout.pdf``."""
    poster_src = (
        _SRC_ROOT / "tools" / "actions" / "synthesis" / "poster_typst.py"
    )
    text = poster_src.read_text(encoding="utf-8")
    assert '"poster.handout.pdf"' in text
    assert '"poster.handout.typ"' in text
    assert '"poster_handout.pdf"' not in text, (
        "poster_typst.py still references the legacy poster_handout.pdf"
    )
    assert '"poster_handout.typ"' not in text, (
        "poster_typst.py still references the legacy poster_handout.typ"
    )


# ── 2. Manifest fixtures use the dot form ────────────────────────────


def test_reference_manifests_declare_dot_form_handouts():
    """Every reference-project manifest that declares a handout output
    must use the dot form. Catches future fixture drift."""
    for manifest_path in _FIXTURES_ROOT.rglob("manifest.yaml"):
        manifest = yaml.safe_load(manifest_path.read_text()) or {}
        delivs = manifest.get("synthesis_deliverables") or []
        for d in delivs:
            checks = d.get("checks") or {}
            for key in ("print_handout_emitted", "handout_pdf_emitted"):
                val = checks.get(key)
                if not val:
                    continue
                assert ".handout." in val, (
                    f"{manifest_path.name} declares {key}={val!r} — "
                    "expected dot form (<stem>.handout.<ext>)"
                )
                assert "_handout." not in val, (
                    f"{manifest_path.name} declares {key}={val!r} — "
                    "legacy underscore form must be replaced"
                )


# ── 3. End-to-end: touying engine emits slides.handout.pdf ───────────


@pytest.fixture
def project(tmp_path: Path) -> Path:
    step = tmp_path / "workspace" / "step01_pilot"
    step.mkdir(parents=True)
    (step / "conclusions.md").write_text(
        "# Findings\n- effect held at n=120\n\n# Decision\nProceed.\n",
        encoding="utf-8",
    )
    fig_dir = step / "outputs" / "figures"
    fig_dir.mkdir(parents=True)
    (fig_dir / "focal.png").write_bytes(_PNG_1x1)
    (fig_dir / "focal.summary.md").write_text("ok", encoding="utf-8")
    (fig_dir / "focal.caption.md").write_text("Fig 1.", encoding="utf-8")
    return tmp_path


@pytest.mark.skipif(not HAS_TYPST, reason="typst CLI not installed")
def test_touying_handout_emitted_with_dot_form(project: Path) -> None:
    res = compile_slides(project, engine="touying", print_handout=True)
    assert res["status"] == "success", res
    files = res["files"]
    handouts = [f for f in files if f.endswith("slides.handout.pdf")]
    assert handouts, (
        f"touying engine must emit slides.handout.pdf; files={files}"
    )
    # Defensive: legacy underscore name must not appear.
    legacy = [f for f in files if f.endswith("slides_handout.pdf")]
    assert not legacy, (
        f"touying engine still emitting legacy slides_handout.pdf: {legacy}"
    )
    handout_path = Path(handouts[0])
    assert handout_path.exists()
    assert handout_path.stat().st_size > 0
    assert res["print_handout_emitted"] is True
