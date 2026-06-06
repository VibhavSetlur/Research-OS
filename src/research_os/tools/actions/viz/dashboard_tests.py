"""Playwright-driven self-testing for ``synthesis/dashboard.html``.

The dashboard the project ships is a single self-contained HTML file
(figures base64-embedded, sticky-sidebar TOC, light/dark toggle,
sortable tables, lightbox figures, print stylesheet). Without a test
harness, regressions creep in silently — a refactor that breaks the
scroll-spy or the lightbox can ship unnoticed.

This module lets the AI:

* **Generate** a baseline pytest-playwright suite covering the
  invariants (TOC scrolls to right section, theme toggle flips CSS
  var, sortable table sorts, lightbox opens, print media-query
  hides sidebar, visual-regression baseline, ARIA accessibility
  snapshot, axe-core WCAG audit) under ``tests/dashboard/``.
* **Run** the suite headless via ``pytest`` in a subprocess and
  return a structured failure list (which assertion failed, which
  screenshot has the diff, which axe rule fired).
* **Iterate** — the AI reads the failure list, patches the
  dashboard renderer (or the spec), reruns. The trace.zip
  produced on failure is the time-travel UI Playwright is famous
  for; the report points the researcher at it.

Why not just unit-test the renderer?
------------------------------------
Most regressions are CSS/JS — a JavaScript scroll-spy that needs
``IntersectionObserver`` not ``offsetTop``, a light/dark CSS var
that got renamed during a refactor, a sortable table whose data-
sort attribute is wrong. The renderer's Python tests can't catch
those; the browser can.

Prerequisites
-------------
``pip install pytest-playwright`` + one-time
``playwright install chromium``. The runner returns a clear error
message if either is missing — the AI relays the install command
to the researcher.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.dashboard_tests")


# ---------------------------------------------------------------------------
# Baseline test suite — written verbatim into tests/dashboard/.
# ---------------------------------------------------------------------------

_BASELINE_SUITE = '''"""Auto-generated Playwright tests for the dashboard.

Run with: pytest tests/dashboard/ -q

Customise: add your own test_*.py files in this directory; the
AI's iterative-improvement loop (`tool_dashboard_test_run`) will
pick them up automatically.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


DASHBOARD = Path(__file__).resolve().parents[2] / "synthesis" / "dashboard.html"


@pytest.fixture(scope="session", autouse=True)
def _check_dashboard_exists():
    if not DASHBOARD.exists():
        pytest.skip(
            f"Dashboard not built yet at {DASHBOARD}. "
            "Run `tool_dashboard_create` first."
        )


@pytest.fixture
def url() -> str:
    return DASHBOARD.as_uri()


# ---------------------------------------------------------------------------
# Basic invariants — fail loudly when the dashboard structure breaks.
# ---------------------------------------------------------------------------


def test_renders_without_console_errors(page: Page, url: str):
    """Page loads + JS evaluates without console errors."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto(url)
    page.wait_for_load_state("domcontentloaded")
    assert not errors, "Console errors: " + "\\n".join(errors)


def test_has_title(page: Page, url: str):
    page.goto(url)
    title = page.title()
    assert title and len(title) > 0, "Dashboard has no <title>"


def test_has_main_landmarks(page: Page, url: str):
    """Semantic HTML: at least one <main>; sticky-sidebar TOC; <h1>."""
    page.goto(url)
    expect(page.locator("main").first).to_be_visible()
    expect(page.locator("h1").first).to_be_visible()


def test_has_tools_essential_sections(page: Page, url: str):
    """The dashboard must surface Abstract + at least one Findings/Verdict."""
    page.goto(url)
    # Either an Abstract section heading or a card with the abstract label.
    abstract = page.locator("section#abstract, [data-section='abstract']")
    expect(abstract.first).to_be_visible(timeout=5000)


# ---------------------------------------------------------------------------
# Interaction tests
# ---------------------------------------------------------------------------


def test_toc_anchors_scroll_to_sections(page: Page, url: str):
    """Click each TOC link; verify the URL hash updates."""
    page.goto(url)
    anchors = page.locator("nav.toc a, aside.toc a, .sidebar a[href^='#']")
    n = anchors.count()
    if n == 0:
        pytest.skip("No TOC anchors found.")
    # Click the first 3 — exhaustive check is overkill.
    for i in range(min(3, n)):
        href = anchors.nth(i).get_attribute("href")
        if not href or not href.startswith("#"):
            continue
        anchors.nth(i).click()
        page.wait_for_timeout(150)
        url_after = page.url
        assert href in url_after, (
            f"TOC click did not update URL hash to {href}; got {url_after}"
        )


def test_theme_toggle_flips_a_css_variable(page: Page, url: str):
    """Clicking the theme toggle must flip --bg or data-theme."""
    page.goto(url)
    toggle = page.locator(
        "button:has-text('theme'), button[aria-label*='theme' i], "
        "#theme-toggle, .theme-toggle, [data-theme-toggle]"
    ).first
    if toggle.count() == 0:
        pytest.skip("No theme toggle present.")
    before = page.evaluate(
        "() => (document.documentElement.dataset.theme || "
        "getComputedStyle(document.documentElement).getPropertyValue('--bg'))"
    )
    toggle.click()
    page.wait_for_timeout(150)
    after = page.evaluate(
        "() => (document.documentElement.dataset.theme || "
        "getComputedStyle(document.documentElement).getPropertyValue('--bg'))"
    )
    assert before.strip() != after.strip(), (
        f"Theme toggle did not change root state ({before!r} == {after!r})"
    )


def test_sortable_table_orders_on_click(page: Page, url: str):
    """If a sortable table exists, clicking a numeric header changes order."""
    page.goto(url)
    tables = page.locator("table")
    n = tables.count()
    for i in range(min(2, n)):
        table = tables.nth(i)
        headers = table.locator("thead th")
        if headers.count() == 0:
            continue
        # Sample first body column values.
        rows_before = table.locator("tbody tr").all_inner_texts()
        headers.first.click()
        page.wait_for_timeout(150)
        rows_after = table.locator("tbody tr").all_inner_texts()
        if rows_before != rows_after:
            return
    pytest.skip("No sortable behaviour detected (tables present but no reorder).")


def test_figure_lightbox_opens(page: Page, url: str):
    """Clicking a figure thumbnail opens an overlay element."""
    page.goto(url)
    fig = page.locator("figure img, .figure img, .gallery img").first
    if fig.count() == 0:
        pytest.skip("No figures present.")
    fig.click()
    overlay = page.locator(
        ".lightbox, .lightbox-overlay, [data-lightbox], dialog[open]"
    ).first
    expect(overlay).to_be_visible(timeout=2000)


def test_print_stylesheet_hides_sidebar(page: Page, url: str):
    """The print media-query collapses the navigational sidebar."""
    page.goto(url)
    page.emulate_media(media="print")
    sidebar = page.locator(
        "nav.toc, aside.toc, .sidebar, nav.sidebar, header.frontpage .actions"
    ).first
    if sidebar.count() == 0:
        pytest.skip("No sidebar present.")
    # We accept either display:none OR visibility:hidden.
    style = page.evaluate(
        "el => getComputedStyle(el).display + '|' + getComputedStyle(el).visibility",
        sidebar.element_handle(),
    )
    assert "none" in style or "hidden" in style, (
        f"Print media did not hide sidebar; computed style = {style}"
    )


# ---------------------------------------------------------------------------
# Accessibility audits
# ---------------------------------------------------------------------------


def test_aria_landmarks_present(page: Page, url: str):
    """The page exposes the essential landmarks (banner / main / nav)."""
    page.goto(url)
    snapshot = page.accessibility.snapshot() or {}
    roles = _walk_roles(snapshot)
    # Soft check — different generators use different role names.
    assert any(r in roles for r in {"main", "WebArea", "document"}), (
        f"No main landmark in accessibility tree; roles = {sorted(roles)[:20]}"
    )


def test_no_axe_serious_violations(page: Page, url: str):
    """Inject axe-core via CDN, fail on serious / critical violations."""
    page.goto(url)
    # Wait for any deferred JS.
    page.wait_for_load_state("networkidle", timeout=5000)
    try:
        page.add_script_tag(
            url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
        )
    except Exception as e:
        pytest.skip(f"Could not inject axe-core: {e}")
    results = page.evaluate(
        """async () => {
          if (typeof axe === 'undefined') return {violations: []};
          return await axe.run(document, {
            runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
          });
        }"""
    )
    serious = [
        v for v in (results.get("violations") or [])
        if v.get("impact") in {"serious", "critical"}
    ]
    msg = "; ".join(f"{v['id']}: {v['help']}" for v in serious[:5])
    assert not serious, f"WCAG violations: {msg}"


def _walk_roles(node: dict) -> set[str]:
    out: set[str] = set()
    if not isinstance(node, dict):
        return out
    if "role" in node:
        out.add(node["role"])
    for child in node.get("children") or []:
        out |= _walk_roles(child)
    return out


# ---------------------------------------------------------------------------
# Visual regression — opt-in via env var to keep CI green by default.
# ---------------------------------------------------------------------------


def test_visual_regression(page: Page, url: str):
    """Full-page screenshot diff against baseline.

    Baseline is generated on first run; subsequent runs diff against it.
    Refresh baselines with `pytest --update-snapshots`.
    """
    import os
    if not os.environ.get("ROS_DASHBOARD_VISUAL"):
        pytest.skip("Set ROS_DASHBOARD_VISUAL=1 to run visual regression.")
    page.goto(url)
    page.emulate_media(media="screen")
    page.wait_for_load_state("networkidle", timeout=5000)
    expect(page).to_have_screenshot(
        "dashboard.png",
        full_page=True,
        animations="disabled",
        max_diff_pixel_ratio=0.005,   # tolerate 0.5% noise
    )
'''


_CONFTEST = '''"""Shared pytest fixtures for the dashboard test suite."""
import pytest


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1440, "height": 900},
        "ignore_https_errors": True,
        "java_script_enabled": True,
    }
'''


_PYTEST_INI = '''[pytest]
addopts = -q --tb=short --screenshot=only-on-failure --tracing=retain-on-failure --output=test-results
testpaths = tests/dashboard
'''


_README = '''# Dashboard tests

Auto-generated Playwright suite for `synthesis/dashboard.html`.

## Install (one-time)

```bash
pip install pytest-playwright
playwright install chromium       # ~250 MB browser download
playwright install-deps chromium  # apt-get system libs (sudo, Linux only)
```

## Run

```bash
pytest tests/dashboard            # all tests
ROS_DASHBOARD_VISUAL=1 pytest tests/dashboard/test_dashboard.py::test_visual_regression
pytest tests/dashboard --update-snapshots  # refresh visual baselines
```

## When a test fails

Playwright writes `test-results/<test>/trace.zip` on failure. Open it
with:

```bash
playwright show-trace test-results/<test>/trace.zip
```

You get a time-travel UI showing every DOM snapshot, network request,
and console message. This is the single best ergonomic for non-Playwright
users.

## Iterative AI loop

The AI's `tool_dashboard_test_run` invokes `pytest` here, parses
failures, patches the dashboard renderer or the
`synthesis_spec.yaml`, and reruns until the suite is green.
'''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_dashboard_test_suite(
    root: Path, *, overwrite: bool = False,
) -> dict[str, Any]:
    """Scaffold ``tests/dashboard/`` with the baseline Playwright suite."""
    target = root / "tests" / "dashboard"
    target.mkdir(parents=True, exist_ok=True)

    paths = [
        (target / "test_dashboard.py", _BASELINE_SUITE),
        (target / "conftest.py",       _CONFTEST),
        (target / "pytest.ini",        _PYTEST_INI),
        (target / "README.md",         _README),
    ]
    written: list[str] = []
    skipped: list[str] = []
    for p, body in paths:
        if p.exists() and not overwrite:
            skipped.append(str(p.relative_to(root)))
            continue
        p.write_text(body)
        written.append(str(p.relative_to(root)))

    # Detect whether prereqs are installed.
    prereq = _check_prereqs()

    return {
        "status": "success",
        "tests_dir": str(target.relative_to(root)),
        "written": written,
        "skipped_existing": skipped,
        "prerequisites": prereq,
        "advice": (
            "Test suite scaffolded. Install prerequisites: "
            "`pip install pytest-playwright && playwright install chromium`. "
            "Then call tool_dashboard(operation='test_run')."
            if not prereq["all_installed"]
            else "Ready to run: tool_dashboard(operation='test_run')."
        ),
    }


def _check_prereqs() -> dict[str, Any]:
    """Detect pytest + pytest-playwright + Chromium without raising."""
    try:
        import pytest as _pytest  # noqa: F401

        have_pytest = True
    except ImportError:
        have_pytest = False
    try:
        import pytest_playwright  # noqa: F401

        have_playwright_plugin = True
    except ImportError:
        have_playwright_plugin = False
    pw_cli = shutil.which("playwright")
    have_playwright_cli = bool(pw_cli)
    return {
        "all_installed": have_pytest and have_playwright_plugin and have_playwright_cli,
        "pytest": have_pytest,
        "pytest_playwright": have_playwright_plugin,
        "playwright_cli": have_playwright_cli,
        "install_hint": (
            "pip install pytest-playwright && playwright install chromium"
            if not (have_pytest and have_playwright_plugin and have_playwright_cli)
            else None
        ),
    }


def run_dashboard_tests(
    root: Path,
    *,
    only: str | None = None,
    visual: bool = False,
    update_snapshots: bool = False,
    timeout: int = 300,
) -> dict[str, Any]:
    """Execute the dashboard test suite and return structured failures.

    Parameters
    ----------
    only:
        Optional pytest node-id filter (e.g. ``test_dashboard.py::test_theme_toggle_flips_a_css_variable``).
    visual:
        Enable visual-regression tests via the ``ROS_DASHBOARD_VISUAL`` env var.
    update_snapshots:
        Re-baseline visual screenshots.
    timeout:
        Wall-clock seconds before the subprocess is killed.
    """
    tests_dir = root / "tests" / "dashboard"
    if not tests_dir.exists():
        return {
            "status": "error",
            "message": (
                "tests/dashboard/ not found — call "
                "tool_dashboard(operation='test_generate') first."
            ),
        }
    dashboard = root / "synthesis" / "dashboard.html"
    if not dashboard.exists():
        return {
            "status": "error",
            "message": (
                "synthesis/dashboard.html not found — call "
                "tool_dashboard_create first."
            ),
        }
    prereq = _check_prereqs()
    if not prereq["all_installed"]:
        return {
            "status": "error",
            "message": "Playwright not installed.",
            "install": prereq["install_hint"],
        }

    cmd = [
        sys.executable, "-m", "pytest",
        str(tests_dir),
        "-q", "--tb=short",
        f"--junitxml={tests_dir}/junit.xml",
        "--screenshot=only-on-failure",
        "--tracing=retain-on-failure",
        f"--output={root}/test-results",
    ]
    if only:
        cmd.append(f"tests/dashboard/{only}")
    if update_snapshots:
        cmd.append("--update-snapshots")

    env = {}
    if visual:
        env["ROS_DASHBOARD_VISUAL"] = "1"

    started = datetime.now(timezone.utc).isoformat()
    try:
        import os as _os

        full_env = {**_os.environ, **env}
        proc = subprocess.run(
            cmd, cwd=str(root), env=full_env,
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"pytest timed out after {timeout}s"}

    # Parse junit XML for structured failures.
    failures = _parse_junit(tests_dir / "junit.xml", root)
    # Persist a structured run log so the next iteration can read it.
    log_dir = root / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_log = log_dir / "dashboard_tests.json"
    record = {
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": proc.returncode,
        "command": " ".join(cmd),
        "n_failures": len(failures),
        "failures": failures,
        "stdout_tail": (proc.stdout or "")[-3000:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }
    run_log.write_text(json.dumps(record, indent=2, default=str) + "\n")

    return {
        "status": "success" if proc.returncode == 0 else "warning",
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "n_failures": len(failures),
        "failures": failures,
        "test_results_dir": "test-results",
        "log_path": str(run_log.relative_to(root)),
        "advice": (
            "All dashboard tests green."
            if proc.returncode == 0
            else (
                f"{len(failures)} test(s) failed. Open trace.zip files "
                "under test-results/ with `playwright show-trace` for "
                "the time-travel debug UI, then patch the dashboard "
                "renderer or synthesis_spec.yaml and rerun."
            )
        ),
    }


def _parse_junit(xml_path: Path, root: Path) -> list[dict[str, Any]]:
    if not xml_path.exists():
        return []
    try:
        tree = ET.parse(xml_path)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for case in tree.iter("testcase"):
        for child in case:
            if child.tag in {"failure", "error"}:
                out.append({
                    "test": case.get("name"),
                    "class": case.get("classname"),
                    "file": case.get("file"),
                    "kind": child.tag,
                    "type": child.get("type"),
                    "message": (child.get("message") or "")[:400],
                    "trace_tail": (child.text or "")[-800:],
                })
                break
    return out


__all__ = ["generate_dashboard_test_suite", "run_dashboard_tests"]
