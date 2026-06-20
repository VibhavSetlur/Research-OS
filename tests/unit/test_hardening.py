"""3.2.10 — security + bibliography-integrity hardening regression tests.

Locks: SSRF/local-file-read guard on download (A1), api-key exclusion from the
share archive (A2), latex shell-escape hardening (A3), Retry-After cap (E1),
autopilot gate ../ bypass (E2), the CRITICAL Hayagriva parser fix (B1), citation
hallucination-laundering (B2), and YAML escaping of doi/url (B3).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def _root():
    return Path(tempfile.mkdtemp())


# -- A1: SSRF / local-file read on download -------------------------------


def test_download_rejects_non_http_schemes_and_writes_nothing():
    from research_os.tools.actions.search.literature import download_literature
    r = _root()
    secret = Path(tempfile.mkdtemp()) / "secret.txt"
    secret.write_text("TOKEN=leak")
    for url, name in ((f"file://{secret}", "exfil.ps"),
                      ("ftp://host/x.pdf", "x.pdf"),
                      ("data:text/plain;base64,QQ==", "y.pdf")):
        res = download_literature(url, name, r, skip_unpaywall=True)
        assert res["status"] == "error", (url, res)
    assert not (r / "inputs" / "literature" / "exfil.ps").exists()


# -- A2: API keys never ship in the share archive -------------------------


def test_share_archive_template_excludes_researcher_config():
    from research_os.project_ops import _EXPORT_PY_TEMPLATE, _SHARE_EXCLUDE_NAMES
    assert "researcher_config.yaml" in _EXPORT_PY_TEMPLATE
    assert "researcher_config.yaml" in _SHARE_EXCLUDE_NAMES


# -- A3: latex compile is shell-escape-hardened ---------------------------


def test_latex_compile_uses_no_shell_escape():
    import research_os.tools.actions.synthesis.latex as latex
    src = Path(latex.__file__).read_text()
    assert "-no-shell-escape" in src
    assert "_HARDENED_TEX_ENV" in src and 'shell_escape": "f"' in src


# -- E1: untrusted Retry-After is capped ----------------------------------


def test_retry_after_is_capped():
    import research_os.tools.actions.search.search as search
    src = Path(search.__file__).read_text()
    assert "min(float(retry_after), 30.0)" in src


# -- E2: autopilot gate is not bypassable via ../ -------------------------


def test_autopilot_gate_resolves_dotdot_synthesis_writes():
    from research_os.server.autopilot_gate import _requires_confirmation
    r = _root()
    assert _requires_confirmation(
        "sys_file_write", {"filepath": "workspace/../synthesis/paper.md", "force": True}, r)
    assert _requires_confirmation(
        "sys_file_write", {"filepath": "synthesis/paper.md", "force": True}, r)
    assert not _requires_confirmation(
        "sys_file_write", {"filepath": "workspace/eda.py", "force": True}, r)


# -- B1: the canonical citations.md parses to a real bibliography ----------


def test_citations_md_canonical_format_parses_to_bibliography():
    yaml = pytest.importorskip("yaml")
    from research_os.tools.actions.synthesis.typst import citations_md_to_hayagriva
    md = _root() / "citations.md"
    md.write_text(
        "# Citations\n\nA bibliography.\n\n"
        "### `smith2024neural`\n- Scope: `project`\n- Title: Neural reranking\n"
        "- Authors: Jane Smith; Bob Lee\n- Year: 2024\n- DOI: `10.1/x`\n- Status: ✅ verified\n\n"
        "### `jones2023survey`\n- Title: A survey\n- Authors: Alice Jones\n- Year: 2023\n"
    )
    out = citations_md_to_hayagriva(md)
    d = yaml.safe_load(out)
    assert set(d.keys()) == {"smith2024neural", "jones2023survey"}, d  # doc title excluded
    assert d["smith2024neural"]["author"] == ["Jane Smith", "Bob Lee"]
    assert d["smith2024neural"]["title"] == "Neural reranking"


# -- B3: doi/url with quotes/backslashes stay valid YAML ------------------


def test_bibliography_escapes_doi_url():
    yaml = pytest.importorskip("yaml")
    from research_os.tools.actions.synthesis.typst import citations_md_to_hayagriva
    md = _root() / "citations.md"
    md.write_text('### `x2024`\n- Title: T\n- Year: 2024\n- DOI: `10.1/a"b\\c`\n')
    d = yaml.safe_load(citations_md_to_hayagriva(md))  # must not raise
    assert d["x2024"]["doi"] == '10.1/a"b\\c'


# -- B2: hallucinated citation keys are NOT verified by keyword match ------


def test_verify_citation_key_requires_author_year_match(monkeypatch):
    import research_os.tools.actions.synthesis.citations as cit
    # Crossref returns a real-but-DIFFERENT paper for a hallucinated key.
    fake_hit = [{"doi": "10.1/real", "year": "2010",
                 "authors": ["Gregor Mendel"], "title": "Pea genetics"}]
    monkeypatch.setattr(
        "research_os.tools.actions.search.search.search_crossref",
        lambda q, limit=5: fake_hit)
    # Hallucinated key (smith 2099) must NOT verify against a Mendel 2010 hit.
    assert cit.verify_citation_key("smith2099neural") is None
    # A matching key (mendel 2010) DOES verify.
    assert cit.verify_citation_key("mendel2010peas") == fake_hit[0]
