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


# -- B8: %PDF magic-byte check is ANCHORED, not a window scan --------------


def test_is_valid_pdf_anchors_after_bom_and_whitespace():
    from research_os.tools.actions.search.literature import is_valid_pdf
    r = _root()

    def mk(name: str, data: bytes) -> Path:
        p = r / name
        p.write_bytes(data)
        return p

    # Valid: header at byte 0, after a UTF-8 BOM, after stray whitespace.
    assert is_valid_pdf(mk("a.pdf", b"%PDF-1.4\nbody")) is True
    assert is_valid_pdf(mk("b.pdf", b"\xef\xbb\xbf%PDF-1.4")) is True
    assert is_valid_pdf(mk("c.pdf", b"  \r\n\t%PDF-1.7")) is True
    # Invalid: an HTML / JSON page that merely CONTAINS "%PDF-" near its
    # start must be rejected (the old head[:64] window scan accepted these).
    assert is_valid_pdf(mk("d.pdf", b'<html><script>var x="%PDF-fake";</script></html>')) is False
    assert is_valid_pdf(mk("e.pdf", b'{"error":"not a %PDF-"}')) is False


# -- B6: arxiv abstract URLs are rewritten to the real /pdf/...pdf target --


def test_search_arxiv_rewrites_abs_url_to_pdf(monkeypatch):
    import research_os.tools.actions.search.search as search
    abs_atom = "http://arxiv.org/abs/2401.12345v1"
    body = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<title>Demo</title><summary>S</summary>"
        f"<id>{abs_atom}</id><published>2024-01-01T00:00:00Z</published>"
        "<author><name>A. Author</name></author>"
        "</entry></feed>"
    ).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return body

    monkeypatch.setattr(search, "_read_cache", lambda *a, **k: None)
    monkeypatch.setattr(search, "_write_cache", lambda *a, **k: None)
    monkeypatch.setattr(search.urllib.request, "urlopen", lambda *a, **k: _Resp())
    out = search.search_arxiv("demo", limit=1)
    assert out, out
    hit = out[0]
    # download target is the real PDF; abstract page preserved for metadata.
    assert hit["url"] == "https://arxiv.org/pdf/2401.12345v1.pdf", hit
    assert hit["abs_url"] == abs_atom, hit


# -- A4: package_install neutralises pip-option injection -----------------


def test_package_install_rejects_dash_prefixed_names():
    from research_os.tools.actions.exec import environment as env
    res = env.package_install(["--index-url=http://attacker/simple", "requests"])
    assert res["status"] == "error", res
    assert "-" in res.get("error", "")  # names beginning with '-' rejected


def test_package_install_uses_end_of_options_separator():
    import research_os.tools.actions.exec.environment as env
    src = Path(env.__file__).read_text()
    # The argv must place a '--' end-of-options separator before *packages.
    assert '"install", "--", *packages' in src


# -- A5: cytoscape .cys extractor rejects zip-slip + caps member size -----


def test_cytoscape_export_rejects_path_escape():
    import zipfile

    import research_os_adapter_cytoscape as cy
    root = _root()
    (root / "workspace").mkdir()
    cys = root / "workspace" / "demo.cys"
    with zipfile.ZipFile(cys, "w") as z:
        z.writestr(
            "demo.xgmml",
            '<graph label="d"><node id="1"/><node id="2"/>'
            '<edge source="1" target="2"/></graph>',
        )

    def _msg(envelope) -> str:
        item = envelope[0] if isinstance(envelope, list) else envelope
        return getattr(item, "text", str(item))

    # ../ traversal in output_path is rejected.
    r1 = cy._handle_export_static(
        "x",
        {"cys_file": "workspace/demo.cys", "output_path": "../../escape.png"},
        root,
    )
    assert "escapes project root" in _msg(r1)
    # absolute cys_file outside the project root is rejected.
    r2 = cy._handle_export_static(
        "x", {"cys_file": "/etc/passwd", "output_path": "workspace/o.png"}, root
    )
    assert "escapes project root" in _msg(r2)


def test_cytoscape_safe_zip_read_caps_member_size(monkeypatch):
    import zipfile

    import research_os_adapter_cytoscape as cy
    root = _root()
    z = root / "a.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("m.txt", b"hello world")
    monkeypatch.setattr(cy, "_MAX_MEMBER_BYTES", 4)
    with zipfile.ZipFile(z) as zf:
        assert cy._safe_zip_read(zf, "m.txt") is None  # over the cap → dropped


# -- B7: the "verified" badge reflects real verification, not identifiers --


def test_citations_badge_not_verified_from_identifier_alone():
    yaml = pytest.importorskip("yaml")
    from research_os.project_ops import generate_citations_md
    root = _root()
    idx = root / "inputs" / "literature_index.yaml"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(
        yaml.safe_dump(
            {
                "entries": {
                    "a.pdf": {"citation_key": "hasdoi2024", "title": "X",
                              "doi": "10.1/a"},
                    "b.pdf": {"citation_key": "real2024", "title": "Y",
                              "doi": "10.1/b", "verified": True},
                }
            }
        )
    )
    generate_citations_md(root)
    text = (root / "workspace" / "citations.md").read_text()
    # An entry that merely has a DOI must NOT read as verified.
    assert "identifier present, not yet verified" in text
    # An explicitly-verified entry keeps the ✅ verified badge.
    assert "✅ verified" in text


# -- B4: distinct references sharing a citation key are disambiguated ------


def test_citation_key_collision_disambiguated():
    from research_os.project_ops import _insert_citation_entry
    entries: dict = {}
    k1 = _insert_citation_entry(
        entries, "smith2024", {"title": "Paper A", "doi": "10.1/a"})
    k2 = _insert_citation_entry(
        entries, "smith2024", {"title": "Paper B", "doi": "10.1/b"})
    assert k1 == "smith2024" and k2 == "smith2024a", (k1, k2)
    assert len(entries) == 2  # neither reference clobbered
    # The SAME reference seen again is deduped, not re-suffixed.
    k3 = _insert_citation_entry(
        entries, "smith2024", {"title": "Paper A", "doi": "10.1/a"})
    assert k3 == "smith2024" and len(entries) == 2


# -- B9: paywall cache key is reason-aware (URL- vs DOI-scoped) ------------


def test_paywall_memory_url_scoped_failure_does_not_block_other_url():
    from research_os.tools.actions.state.paywall_memory import (
        is_known_bad,
        record_failure,
    )
    root = _root()
    (root / "workspace" / ".os_state").mkdir(parents=True)
    pub = "https://publisher.com/doi/full/10.1234/foo"
    other = "https://mirror.org/article/10.1234/foo"
    # A URL-scoped 403 blocks only that exact URL.
    record_failure(root, tool="t", target=pub, reason="permanent_403",
                   permanent=True)
    assert is_known_bad(root, pub)["known_bad"] is True
    assert is_known_bad(root, other).get("known_bad") is False


def test_paywall_memory_doi_scoped_failure_still_blocks_same_doi():
    from research_os.tools.actions.state.paywall_memory import (
        is_known_bad,
        record_failure,
    )
    root = _root()
    (root / "workspace" / ".os_state").mkdir(parents=True)
    pub = "https://publisher.com/doi/full/10.1234/foo"
    same_doi = "https://doi.org/10.1234/foo"
    # A paywall verdict (DOI-scoped) blocks any same-DOI URL.
    record_failure(root, tool="t", target=pub, reason="paywall",
                   permanent=True)
    assert is_known_bad(root, pub)["known_bad"] is True
    assert is_known_bad(root, same_doi)["known_bad"] is True
