"""PDF integrity: magic-byte validation + fake-download deletion + count sites.

Closes the audit gap where the literature download path wrote ANY bytes
and gates counted *.pdf by extension — so a renamed 403/HTML page passed
as a downloaded paper.
"""

from pathlib import Path
from unittest import mock

from research_os.tools.actions.search.literature import (
    count_valid_pdfs,
    download_literature,
    is_valid_pdf,
)


# ── is_valid_pdf ─────────────────────────────────────────────────────


def test_is_valid_pdf_accepts_magic_header(tmp_path: Path):
    p = tmp_path / "real.pdf"
    p.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n")
    assert is_valid_pdf(p) is True


def test_is_valid_pdf_accepts_header_after_bom(tmp_path: Path):
    p = tmp_path / "bom.pdf"
    p.write_bytes(b"\xef\xbb\xbf%PDF-1.4\n")
    assert is_valid_pdf(p) is True


def test_is_valid_pdf_rejects_html(tmp_path: Path):
    p = tmp_path / "fake.pdf"
    p.write_bytes(b"<!DOCTYPE html><html><body>403 Forbidden</body></html>")
    assert is_valid_pdf(p) is False


def test_is_valid_pdf_rejects_json_error(tmp_path: Path):
    p = tmp_path / "err.pdf"
    p.write_bytes(b'{"error": "paywall", "status": 403}')
    assert is_valid_pdf(p) is False


def test_is_valid_pdf_rejects_empty(tmp_path: Path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    assert is_valid_pdf(p) is False


def test_is_valid_pdf_rejects_missing(tmp_path: Path):
    assert is_valid_pdf(tmp_path / "nope.pdf") is False


# ── count_valid_pdfs ─────────────────────────────────────────────────


def test_count_valid_pdfs_counts_only_real(tmp_path: Path):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.5\nreal")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4\nreal")
    (tmp_path / "fake.pdf").write_bytes(b"<html>nope</html>")
    assert count_valid_pdfs(tmp_path) == 2


def test_count_valid_pdfs_missing_dir(tmp_path: Path):
    assert count_valid_pdfs(tmp_path / "absent") == 0


# ── download path: magic-byte gate ──────────────────────────────────


def _fake_urlretrieve(payload: bytes):
    def _impl(url, out_path):
        Path(out_path).write_bytes(payload)
        return out_path, None
    return _impl


def test_download_rejects_non_pdf_and_deletes_file(tmp_path: Path):
    (tmp_path / "inputs" / "literature").mkdir(parents=True)
    html = b"<!DOCTYPE html><html>Access denied (403)</html>"
    with mock.patch(
        "research_os.tools.actions.search.literature.urllib.request.urlretrieve",
        _fake_urlretrieve(html),
    ):
        res = download_literature(
            "https://example.com/paper.pdf",
            "paper.pdf",
            tmp_path,
            skip_unpaywall=True,
        )
    assert res["status"] == "error"
    assert res.get("not_a_pdf") is True
    # No fake .pdf left behind.
    assert list((tmp_path / "inputs" / "literature").glob("*.pdf")) == []


def test_download_records_structured_failure_for_fake_pdf(tmp_path: Path):
    (tmp_path / "inputs" / "literature").mkdir(parents=True)
    html = b"<html>paywall interstitial</html>"
    with mock.patch(
        "research_os.tools.actions.search.literature.urllib.request.urlretrieve",
        _fake_urlretrieve(html),
    ):
        download_literature(
            "https://example.com/x.pdf",
            "x.pdf",
            tmp_path,
            skip_unpaywall=True,
        )
    # The paywall_memory failure log should carry a 'not_a_pdf' reason.
    failures = tmp_path / "workspace" / ".os_state" / "tool_failures.jsonl"
    assert failures.exists()
    text = failures.read_text()
    assert "not_a_pdf" in text


def test_download_accepts_real_pdf(tmp_path: Path):
    (tmp_path / "inputs" / "literature").mkdir(parents=True)
    pdf = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nbody\n%%EOF\n"
    with mock.patch(
        "research_os.tools.actions.search.literature.urllib.request.urlretrieve",
        _fake_urlretrieve(pdf),
    ):
        res = download_literature(
            "https://example.com/real.pdf",
            "real.pdf",
            tmp_path,
            skip_unpaywall=True,
        )
    assert res["status"] == "success"
    saved = list((tmp_path / "inputs" / "literature").glob("*.pdf"))
    assert len(saved) == 1
    assert is_valid_pdf(saved[0])


# ── gate counters route through magic validation ─────────────────────


def test_step_literature_audit_ignores_fake_pdf(tmp_path: Path):
    from research_os.tools.actions.audit.step_literature import (
        audit_step_literature,
    )

    step = tmp_path / "workspace" / "01_eda"
    (step / "literature").mkdir(parents=True)
    # A fake PDF must not count as a downloaded paper.
    (step / "literature" / "fake.pdf").write_bytes(b"<html>nope</html>")
    (step / "conclusions.md").write_text("# conclusions\n")
    res = audit_step_literature(tmp_path, step_id="01_eda")
    # papers_downloaded (per-step info) reflects only valid PDFs (0 here).
    per_step = res.get("per_step") or []
    assert per_step, f"expected per_step info, got {res}"
    assert per_step[0].get("papers_downloaded", 0) == 0
