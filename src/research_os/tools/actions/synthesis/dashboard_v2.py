"""Dashboard v2 — single-page web app renderer.

Replaces the long-scroll v1 dashboard with a single-page app: sidebar
nav + full-text search + filter panel + per-figure static-vs-interactive
toggle + reactive tables. The v1 renderer (``render_dashboard`` in
``dashboard.py``) stays available as a fallback via
``dashboard_legacy=true`` on ``tool_dashboard_create``.

Design constraints:

* Offline-only: no fetch() to external URLs at runtime. All JS bundles
  are vendored under ``src/research_os/assets/js/`` and inlined into
  the output HTML. Bundles load conditionally based on what the
  project needs (no Mermaid bytes for projects without ``.mermaid``
  files, no Plotly bytes without ``*.plotly.json`` sidecars, etc.).
* Single file: ``synthesis/dashboard.html`` is self-contained when
  embed_figures == "inline" (default for small projects), or paired
  with relative ``<img src=>`` pointers into ``workspace/`` for large
  ones (auto-mode picks based on figure count + total size).
* Vanilla custom elements (no React/Vue/Svelte) — every component is
  a ``<ro-*>`` element whose ``connectedCallback`` wires up behavior.

This module is intentionally separate from the v1 ``dashboard.py`` so
both can coexist. Data-collection helpers (``_collect_steps``,
``_load_state``, etc.) are imported from v1 rather than duplicated.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Vendored JS bundle loader
# ──────────────────────────────────────────────────────────────────────

_ASSETS_JS_DIR = Path(__file__).resolve().parents[3] / "assets" / "js"

# Bundles that ship in every dashboard.
_ALWAYS_BUNDLES = ("minisearch.min.js", "vega.min.js",
                   "vega-lite.min.js", "vega-embed.min.js")
# Bundles loaded conditionally based on what the project contains.
_CONDITIONAL_BUNDLES = {
    "plotly.min.js":     "has_plotly",
    "mermaid.min.js":    "has_mermaid",
    "vis-network.min.js": "has_network",
}


def _read_bundle(name: str) -> str:
    """Return the contents of a vendored JS file, or empty on miss.

    Missing bundles degrade gracefully — the dashboard still renders,
    just without the corresponding interactive feature. This keeps
    test fixtures cheap (they can drop tiny placeholder files instead
    of the real multi-MB minified bundles).
    """
    p = _ASSETS_JS_DIR / name
    if not p.exists():
        logger.warning("vendored bundle missing: %s", name)
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        logger.warning("could not read vendored bundle %s: %s", name, e)
        return ""


def _detect_capabilities(root: Path) -> dict[str, bool]:
    """Look across the workspace to decide which JS bundles to inline."""
    ws = root / "workspace"
    caps = {"has_plotly": False, "has_mermaid": False, "has_network": False}
    if not ws.is_dir():
        return caps
    for p in ws.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if name.endswith(".plotly.json") or name.endswith("_plotly.json"):
            caps["has_plotly"] = True
        elif name.endswith(".mermaid"):
            caps["has_mermaid"] = True
        elif name.endswith(".graphml"):
            caps["has_network"] = True
        if all(caps.values()):
            break
    return caps


def bundled_js(root: Path) -> tuple[str, list[str]]:
    """Concatenate the JS bundles needed by this dashboard.

    Returns ``(concatenated_js, included_bundle_names)``. Each bundle
    is wrapped in a ``/* === <name> === */`` banner so a maintainer
    inspecting the rendered HTML can tell which library a block came
    from. The custom-element layer (see ``CUSTOM_ELEMENTS_JS``) is
    appended after the third-party bundles so it can rely on globals
    like ``vegaEmbed`` and ``Plotly``.
    """
    parts: list[str] = []
    included: list[str] = []
    for name in _ALWAYS_BUNDLES:
        body = _read_bundle(name)
        if body:
            parts.append(f"/* === {name} === */\n{body}\n")
            included.append(name)
    caps = _detect_capabilities(root)
    for name, cap in _CONDITIONAL_BUNDLES.items():
        if caps.get(cap):
            body = _read_bundle(name)
            if body:
                parts.append(f"/* === {name} === */\n{body}\n")
                included.append(name)
    parts.append(f"/* === ro-custom-elements === */\n{CUSTOM_ELEMENTS_JS}\n")
    included.append("ro-custom-elements")
    return "".join(parts), included


# ──────────────────────────────────────────────────────────────────────
# CSS (kept inline; ~12 KB).
# Vendored design system: Okabe-Ito accent palette + viridis-inspired
# greys, system font stack, CSS-grid layout that collapses to a single
# column < 768 px wide, print stylesheet that hides chrome.
# ──────────────────────────────────────────────────────────────────────

DASHBOARD_V2_CSS = r"""
:root {
  --bg: #fafafa; --panel: #ffffff; --ink: #1a1a1a; --muted: #5a5a5a;
  --line: #e5e5e5; --line-strong: #c8c8c8;
  --accent: #0072B2; --accent-soft: #cce5f5;
  --ok: #009E73; --warn: #E69F00; --bad: #D55E00;
  --serif: 'Source Serif Pro', 'Georgia', 'Times New Roman', serif;
  --sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Roboto, sans-serif;
  --mono: ui-monospace, 'SF Mono', 'Menlo', monospace;
}
@media (prefers-color-scheme: dark) {
  :root.auto-theme {
    --bg: #1a1a1a; --panel: #242424; --ink: #f0f0f0; --muted: #a0a0a0;
    --line: #333; --line-strong: #555; --accent-soft: #003a5c;
  }
}
html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink);
             font-family: var(--sans); font-size: 16px; line-height: 1.5; }
* { box-sizing: border-box; }
a { color: var(--accent); }
a:hover { text-decoration: underline; }
button { font: inherit; cursor: pointer; border-radius: 6px; padding: 6px 12px;
         border: 1px solid var(--line-strong); background: var(--panel);
         color: var(--ink); }
button:hover { background: var(--accent-soft); }

.app {
  display: grid;
  grid-template-columns: 280px 1fr;
  grid-template-rows: 56px 1fr;
  grid-template-areas: "header header" "sidebar main";
  min-height: 100vh;
}

header.ro-header {
  grid-area: header;
  display: flex; align-items: center; gap: 16px;
  padding: 0 20px; background: var(--panel);
  border-bottom: 1px solid var(--line);
  position: sticky; top: 0; z-index: 50;
}
header.ro-header .title { font-weight: 600; }
header.ro-header .grow { flex: 1 1 auto; }

aside.ro-sidebar {
  grid-area: sidebar;
  background: var(--panel); border-right: 1px solid var(--line);
  overflow-y: auto; padding: 16px 12px;
}

main.ro-main {
  grid-area: main; padding: 24px 36px; overflow-y: auto;
  max-width: 100%;
}

footer.ro-footer {
  border-top: 1px solid var(--line); padding: 12px 36px; color: var(--muted);
  font-size: 13px;
}

/* Sidebar tree */
.tree { list-style: none; padding: 0; margin: 0; font-size: 14px; }
.tree li { padding: 4px 0; }
.tree a { color: var(--ink); text-decoration: none; display: block; padding: 4px 6px; border-radius: 4px; }
.tree a:hover, .tree a.active { background: var(--accent-soft); color: var(--accent); }
.tree details > summary { cursor: pointer; padding: 4px 6px; font-weight: 600; }
.tree details[open] > summary { color: var(--accent); }

/* Search */
ro-search { display: block; }
ro-search input[type=search] {
  width: 360px; max-width: 100%; padding: 6px 10px; border: 1px solid var(--line-strong);
  border-radius: 6px; font: inherit; background: var(--bg); color: var(--ink);
}
.ro-search-results {
  position: absolute; top: 50px; left: 0; right: 0; max-width: 480px; z-index: 60;
  background: var(--panel); border: 1px solid var(--line-strong); border-radius: 6px;
  max-height: 60vh; overflow-y: auto; padding: 6px; display: none;
}
.ro-search-results.open { display: block; }
.ro-search-results .hit { padding: 8px; border-bottom: 1px solid var(--line); cursor: pointer; }
.ro-search-results .hit:last-child { border-bottom: 0; }
.ro-search-results .hit:hover { background: var(--accent-soft); }
.ro-search-results mark { background: #FFE799; padding: 0 2px; }

/* Filter chips */
ro-filter { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.chip { font-size: 12px; padding: 4px 10px; border-radius: 999px;
        border: 1px solid var(--line-strong); background: var(--panel);
        cursor: pointer; user-select: none; }
.chip.active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* Sections */
section.ro-section {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 20px 24px; margin-bottom: 20px;
}
section.ro-section h2 { margin-top: 0; }
section.ro-section.hidden-by-filter { display: none; }

/* Figure toggle */
ro-figure-toggle {
  display: block; border: 1px solid var(--line); border-radius: 6px;
  margin: 12px 0; padding: 0;
}
ro-figure-toggle .tabs {
  display: flex; gap: 0; border-bottom: 1px solid var(--line);
}
ro-figure-toggle .tabs button {
  border: 0; border-radius: 0; background: transparent; padding: 8px 14px;
  border-bottom: 2px solid transparent;
}
ro-figure-toggle .tabs button.active {
  border-bottom-color: var(--accent); color: var(--accent); font-weight: 600;
}
ro-figure-toggle .body { padding: 10px; }
ro-figure-toggle .body img { max-width: 100%; height: auto; }
ro-figure-toggle .body iframe { width: 100%; height: 480px; border: 0; }

/* Reactive tables */
ro-table { display: block; overflow-x: auto; margin: 12px 0; }
ro-table table { border-collapse: collapse; width: 100%; font-size: 14px; }
ro-table th, ro-table td { padding: 6px 10px; border-bottom: 1px solid var(--line); text-align: left; }
ro-table th { background: var(--bg); font-weight: 600; cursor: pointer; user-select: none; }
ro-table th:hover { background: var(--accent-soft); }
ro-table th[data-sort-dir="asc"]::after { content: " ▲"; }
ro-table th[data-sort-dir="desc"]::after { content: " ▼"; }
ro-table .table-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
ro-table .table-controls input { padding: 4px 8px; border: 1px solid var(--line-strong);
                                  border-radius: 4px; font: inherit; }
ro-table tr.brushed { background: #FFE79922; }

/* Story mode */
body.story-mode aside.ro-sidebar { display: none; }
body.story-mode main.ro-main {
  grid-column: 1 / -1;
  font-family: var(--serif); max-width: 70ch; margin: 0 auto;
  padding-top: 40px; padding-bottom: 80px; font-size: 18px; line-height: 1.7;
}
body.story-mode .app { grid-template-columns: 1fr; grid-template-areas: "header" "main"; }
body.story-mode .story-only { display: block; }
body.story-mode .explore-only { display: none; }
body.story-mode ro-search, body.story-mode ro-filter { display: none; }
.story-only { display: none; }

body.story-mode blockquote {
  border-left: 3px solid var(--accent); margin: 1em 0; padding: 0.5em 1em;
  background: var(--accent-soft); color: var(--ink);
}
body.story-mode .reading-time { color: var(--muted); font-style: italic; font-size: 16px; }
body.story-mode .adversarial-callout {
  border-left: 4px solid var(--warn); background: #FFF4E0; padding: 12px 16px;
  margin: 16px 0; border-radius: 0 6px 6px 0;
}

/* Mode toggle */
ro-mode-toggle .pill {
  display: inline-flex; border: 1px solid var(--line-strong); border-radius: 999px;
  padding: 2px; background: var(--panel);
}
ro-mode-toggle .pill button {
  border: 0; border-radius: 999px; padding: 4px 12px; background: transparent;
  font-size: 13px;
}
ro-mode-toggle .pill button.active { background: var(--accent); color: #fff; }

/* Mermaid + Plotly + Vega slots */
ro-mermaid, ro-plotly, ro-vega { display: block; min-height: 100px; margin: 12px 0; }
ro-mermaid svg, ro-vega .vega-embed { max-width: 100%; }

/* Responsive */
@media (max-width: 768px) {
  .app { grid-template-columns: 1fr; grid-template-areas: "header" "sidebar" "main"; }
  aside.ro-sidebar { border-right: 0; border-bottom: 1px solid var(--line);
                     max-height: 200px; }
  main.ro-main { padding: 16px; }
  ro-search input[type=search] { width: 100%; }
}

/* Print */
@media print {
  aside.ro-sidebar, header.ro-header, ro-search, ro-filter,
  ro-mode-toggle, .ro-search-results, .ro-print-hidden { display: none !important; }
  body, .app, main.ro-main { display: block !important; padding: 0; margin: 0; background: #fff; color: #000; }
  section.ro-section { break-before: page; border: 0; padding: 0; }
  ro-figure-toggle iframe { display: none; }
  ro-figure-toggle .interactive-tab { display: none; }
  ro-figure-toggle img { max-width: 100%; max-height: 90vh; }
  a { color: #000; text-decoration: none; }
  @page { margin: 1in; }
}
"""


# ──────────────────────────────────────────────────────────────────────
# Custom elements (~10 KB of vanilla JS).
#
# Each ``<ro-*>`` element is a small custom element whose constructor
# stays cheap so the page paints fast; heavier work (Vega-Lite parse,
# Plotly render, Mermaid layout) defers to an IntersectionObserver
# so off-screen figures don't tax the first paint.
# ──────────────────────────────────────────────────────────────────────

CUSTOM_ELEMENTS_JS = r"""
(() => {
  'use strict';
  const RO = (window.RO = window.RO || {});
  RO.bus = new EventTarget();          // simple cross-component event bus
  RO.brushState = {};                  // {sourceId: Set(keys)} for brushing
  RO.lazyObs = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting && typeof e.target._roLazy === 'function') {
        try { e.target._roLazy(); } catch (err) { console.warn('lazy render failed', err); }
        e.target._roLazy = null;
        RO.lazyObs.unobserve(e.target);
      }
    }
  }, {rootMargin: '200px'});

  // <ro-mode-toggle> — story | explore switcher
  customElements.define('ro-mode-toggle', class extends HTMLElement {
    connectedCallback() {
      const saved = (localStorage.getItem('ro-mode')
                     || this.getAttribute('default') || 'explore');
      this.innerHTML = `<div class="pill" role="tablist" aria-label="Reading mode">
        <button data-mode="story"   role="tab">Story</button>
        <button data-mode="explore" role="tab">Explore</button></div>`;
      this.querySelectorAll('button').forEach(b => {
        b.addEventListener('click', () => this.setMode(b.dataset.mode));
      });
      this.setMode(this._modeFromHash() || saved);
      window.addEventListener('hashchange', () => {
        const m = this._modeFromHash();
        if (m) this.setMode(m, /*skipHash*/ true);
      });
    }
    _modeFromHash() {
      const m = (location.hash.match(/mode=(story|explore)/) || [])[1];
      return m || null;
    }
    setMode(mode, skipHash) {
      if (mode !== 'story' && mode !== 'explore') mode = 'explore';
      document.body.classList.toggle('story-mode', mode === 'story');
      document.body.classList.toggle('explore-mode', mode === 'explore');
      this.querySelectorAll('button').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
        b.setAttribute('aria-selected', b.dataset.mode === mode ? 'true' : 'false');
      });
      localStorage.setItem('ro-mode', mode);
      if (!skipHash) {
        const h = (location.hash || '#').replace(/[#&]?mode=(story|explore)/g, '');
        location.hash = (h && h !== '#' ? h + '&' : '#') + 'mode=' + mode;
      }
      RO.bus.dispatchEvent(new CustomEvent('mode-change', {detail: {mode}}));
    }
  });

  // <ro-sidebar> — sticky nav tree
  customElements.define('ro-sidebar', class extends HTMLElement {
    connectedCallback() {
      // Sidebar content is server-rendered in the original HTML;
      // we just wire scroll-spy + collapsible groups.
      this.querySelectorAll('.tree a').forEach(a => {
        a.addEventListener('click', (e) => {
          const t = a.getAttribute('href');
          if (t && t.startsWith('#')) {
            e.preventDefault();
            const el = document.querySelector(t);
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
            history.replaceState(null, '', t);
            this.querySelectorAll('.tree a').forEach(x => x.classList.remove('active'));
            a.classList.add('active');
          }
        });
      });
    }
  });

  // <ro-search> — MiniSearch full-text search
  customElements.define('ro-search', class extends HTMLElement {
    connectedCallback() {
      this.innerHTML = `<input type="search" placeholder="Search..." aria-label="Search dashboard">
        <div class="ro-search-results" role="listbox"></div>`;
      this.input = this.querySelector('input');
      this.results = this.querySelector('.ro-search-results');
      const docsScript = document.querySelector('script[type="application/x-ro-search-index"]');
      let docs = [];
      try { docs = docsScript ? JSON.parse(docsScript.textContent) : []; }
      catch (e) { console.warn('search index parse failed', e); }
      if (typeof MiniSearch === 'undefined' || !docs.length) {
        this.input.disabled = true; this.input.placeholder = 'Search unavailable';
        return;
      }
      this.idx = new MiniSearch({
        fields: ['title', 'body'],
        storeFields: ['title', 'section', 'figure', 'anchor', 'body'],
        searchOptions: {boost: {title: 2}, prefix: true, fuzzy: 0.2},
      });
      this.idx.addAll(docs);
      this.input.addEventListener('input', () => this.runQuery());
      this.input.addEventListener('focus', () => this.runQuery());
      document.addEventListener('click', (e) => {
        if (!this.contains(e.target)) this.results.classList.remove('open');
      });
    }
    runQuery() {
      const q = this.input.value.trim();
      if (!q) { this.results.classList.remove('open'); return; }
      const hits = this.idx.search(q, {prefix: true, fuzzy: 0.2}).slice(0, 12);
      if (!hits.length) {
        this.results.innerHTML = '<div class="hit">No matches.</div>';
        this.results.classList.add('open'); return;
      }
      const esc = (s) => (s || '').replace(/[&<>"]/g,
        c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
      const hl = (s, q) => {
        if (!q) return esc(s);
        const re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
        return esc(s).replace(re, '<mark>$1</mark>');
      };
      this.results.innerHTML = hits.map(h => {
        const snippet = (h.body || '').slice(0, 160);
        return `<div class="hit" data-anchor="${esc(h.anchor || '')}">
          <strong>${esc(h.title || h.section || '')}</strong><br>
          <small>${esc(h.section || '')}</small><br>${hl(snippet, q)}</div>`;
      }).join('');
      this.results.querySelectorAll('.hit').forEach(el => {
        el.addEventListener('click', () => {
          const a = el.dataset.anchor;
          if (a) {
            const t = document.querySelector(a.startsWith('#') ? a : '#' + a);
            if (t) t.scrollIntoView({behavior: 'smooth', block: 'start'});
            history.replaceState(null, '', a.startsWith('#') ? a : '#' + a);
          }
          this.results.classList.remove('open');
        });
      });
      this.results.classList.add('open');
    }
  });

  // <ro-filter> — chip-based section filter
  customElements.define('ro-filter', class extends HTMLElement {
    connectedCallback() {
      // Chips are server-rendered; we wire toggle behaviour + URL sync.
      this.active = new Set();
      const fromHash = (location.hash.match(/filter=([^&]+)/) || [])[1];
      if (fromHash) {
        decodeURIComponent(fromHash).split(',').filter(Boolean).forEach(k => this.active.add(k));
      }
      this.querySelectorAll('.chip').forEach(c => {
        if (this.active.has(c.dataset.key)) c.classList.add('active');
        c.addEventListener('click', () => {
          c.classList.toggle('active');
          if (c.classList.contains('active')) this.active.add(c.dataset.key);
          else this.active.delete(c.dataset.key);
          this._sync();
          this.apply();
        });
      });
      this.apply();
    }
    _sync() {
      const keys = [...this.active].join(',');
      const h = (location.hash || '#').replace(/[#&]?filter=[^&]*/g, '');
      const next = keys ? ((h && h !== '#' ? h + '&' : '#') + 'filter=' + encodeURIComponent(keys)) : (h || '');
      location.hash = next;
    }
    apply() {
      const active = this.active;
      document.querySelectorAll('section.ro-section').forEach(s => {
        if (!active.size) { s.classList.remove('hidden-by-filter'); return; }
        const tags = (s.dataset.tags || '').split(',').filter(Boolean);
        const match = tags.some(t => active.has(t));
        s.classList.toggle('hidden-by-filter', !match);
      });
    }
  });

  // <ro-figure-toggle> — static PNG ↔ interactive HTML companion
  customElements.define('ro-figure-toggle', class extends HTMLElement {
    connectedCallback() {
      const stem = this.getAttribute('figure-stem') || '';
      const staticSrc = this.getAttribute('static-src') || '';
      const interactiveSrc = this.getAttribute('interactive-src') || '';
      const caption = this.getAttribute('caption') || '';
      const hasInteractive = !!interactiveSrc;
      this.innerHTML = `<div class="tabs" role="tablist">
        <button class="active" data-tab="static" role="tab" aria-controls="${stem}-body">Static</button>
        ${hasInteractive ? `<button class="interactive-tab" data-tab="interactive" role="tab">Interactive</button>` : ''}
        </div>
        <div class="body" id="${stem}-body" role="tabpanel"></div>
        ${caption ? `<figcaption style="padding:4px 12px;font-size:13px;color:var(--muted)">${caption}</figcaption>` : ''}`;
      this.body = this.querySelector('.body');
      this._showStatic(staticSrc, caption);
      this.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
        this.querySelectorAll('button').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        if (b.dataset.tab === 'static') this._showStatic(staticSrc, caption);
        else this._showInteractive(interactiveSrc, caption);
      }));
    }
    _showStatic(src, alt) {
      this.body.innerHTML = src
        ? `<img src="${src}" alt="${alt || ''}" loading="lazy">`
        : `<em>(static figure missing)</em>`;
    }
    _showInteractive(src, alt) {
      if (!src) { this.body.innerHTML = '<em>(no interactive companion)</em>'; return; }
      this.body.innerHTML = `<iframe src="${src}" title="${alt || ''}" loading="lazy" sandbox="allow-scripts allow-same-origin"></iframe>`;
    }
  });

  // <ro-table> — sort + filter + CSV export
  customElements.define('ro-table', class extends HTMLElement {
    connectedCallback() {
      const dataAttr = this.getAttribute('data');
      let rows = null, cols = null;
      if (dataAttr) {
        try {
          const obj = JSON.parse(dataAttr);
          cols = obj.columns; rows = obj.rows;
        } catch (e) { console.warn('ro-table parse failed', e); }
      }
      const inline = this.querySelector('script[type="application/json"]');
      if (!rows && inline) {
        try {
          const obj = JSON.parse(inline.textContent);
          cols = obj.columns; rows = obj.rows;
        } catch (e) { console.warn('ro-table parse failed', e); }
      }
      if (!rows || !cols) { this.innerHTML = '<em>(no rows)</em>'; return; }
      this._cols = cols; this._rows = rows; this._sortKey = null; this._sortDir = null;
      this._filter = '';
      this.render();
    }
    render() {
      const cols = this._cols; let rows = this._rows;
      if (this._filter) {
        const q = this._filter.toLowerCase();
        rows = rows.filter(r => cols.some(c => String(r[c] || '').toLowerCase().includes(q)));
      }
      if (this._sortKey) {
        const k = this._sortKey, dir = this._sortDir === 'asc' ? 1 : -1;
        rows = rows.slice().sort((a, b) => {
          const va = a[k], vb = b[k];
          if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
          return String(va || '').localeCompare(String(vb || '')) * dir;
        });
      }
      const esc = (s) => String(s == null ? '' : s).replace(/[&<>]/g,
        c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
      const header = cols.map(c => `<th data-key="${esc(c)}"${c === this._sortKey ? ` data-sort-dir="${this._sortDir}"` : ''}>${esc(c)}</th>`).join('');
      const body = rows.map(r => '<tr data-key="' + esc(r[cols[0]] || '') + '">' +
        cols.map(c => `<td>${esc(r[c])}</td>`).join('') + '</tr>').join('');
      this.innerHTML = `<div class="table-controls">
        <input type="search" placeholder="Filter rows..." value="${esc(this._filter)}">
        <button type="button" class="csv-export">CSV</button>
        <small>${rows.length} row${rows.length === 1 ? '' : 's'}</small>
        </div>
        <table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
      this.querySelector('input').addEventListener('input', (e) => {
        this._filter = e.target.value; this.render();
        const inp = this.querySelector('input'); if (inp) inp.focus();
      });
      this.querySelector('.csv-export').addEventListener('click', () => this._exportCsv(rows));
      this.querySelectorAll('th[data-key]').forEach(th => th.addEventListener('click', () => {
        const k = th.dataset.key;
        if (this._sortKey === k) this._sortDir = this._sortDir === 'asc' ? 'desc' : 'asc';
        else { this._sortKey = k; this._sortDir = 'asc'; }
        this.render();
      }));
    }
    _exportCsv(rows) {
      const esc = (v) => {
        const s = String(v == null ? '' : v);
        return /["',\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const csv = [this._cols.join(',')].concat(
        rows.map(r => this._cols.map(c => esc(r[c])).join(','))
      ).join('\n');
      const blob = new Blob([csv], {type: 'text/csv'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (this.getAttribute('name') || 'table') + '.csv';
      document.body.appendChild(a); a.click(); a.remove();
    }
    applyBrush(keys) {
      this.querySelectorAll('tbody tr').forEach(tr => {
        tr.classList.toggle('brushed', keys.has(tr.dataset.key));
      });
    }
  });

  // <ro-brush-link source="X" target="Y" /> — wire selection from one component
  // to highlight rows in a sibling table.
  customElements.define('ro-brush-link', class extends HTMLElement {
    connectedCallback() {
      const source = this.getAttribute('source'); const target = this.getAttribute('target');
      RO.bus.addEventListener('brush:' + source, (e) => {
        const tgt = document.getElementById(target);
        if (tgt && typeof tgt.applyBrush === 'function') tgt.applyBrush(new Set(e.detail.keys || []));
      });
    }
  });

  // <ro-vega spec="..."> — lazy-render Vega-Lite into the element
  customElements.define('ro-vega', class extends HTMLElement {
    connectedCallback() {
      this._roLazy = () => {
        if (typeof vegaEmbed === 'undefined') { this.innerHTML = '<em>(vega unavailable)</em>'; return; }
        let spec = this.getAttribute('spec');
        if (!spec) {
          const s = this.querySelector('script[type="application/json"]');
          if (s) spec = s.textContent;
        }
        try { spec = JSON.parse(spec || '{}'); }
        catch (e) { this.innerHTML = '<em>(invalid spec)</em>'; return; }
        vegaEmbed(this, spec, {actions: false}).then(r => {
          if (r.view && this.id) {
            // Forward Vega selections as brush events under the element ID.
            const sigName = (spec.params || []).find(p => p.select)?.name;
            if (sigName) {
              r.view.addSignalListener(sigName, (_, val) => {
                const keys = (val?.vlPoint?.or || []).map(o => o[Object.keys(o)[0]]);
                RO.bus.dispatchEvent(new CustomEvent('brush:' + this.id, {detail: {keys}}));
              });
            }
          }
        }).catch(e => { this.innerHTML = '<em>vega render failed: ' + e.message + '</em>'; });
      };
      RO.lazyObs.observe(this);
    }
  });

  // <ro-plotly> — inline Plotly figure
  customElements.define('ro-plotly', class extends HTMLElement {
    connectedCallback() {
      this._roLazy = () => {
        if (typeof Plotly === 'undefined') { this.innerHTML = '<em>(plotly unavailable)</em>'; return; }
        let raw = this.getAttribute('spec');
        if (!raw) {
          const s = this.querySelector('script[type="application/json"]');
          if (s) raw = s.textContent;
        }
        try {
          const spec = JSON.parse(raw || '{}');
          Plotly.newPlot(this, spec.data || [], spec.layout || {}, {responsive: true, displayModeBar: false});
        } catch (e) { this.innerHTML = '<em>plotly parse failed: ' + e.message + '</em>'; }
      };
      RO.lazyObs.observe(this);
    }
  });

  // <ro-mermaid> — render the mermaid source inside the element
  customElements.define('ro-mermaid', class extends HTMLElement {
    connectedCallback() {
      this._roLazy = async () => {
        if (typeof mermaid === 'undefined') return; // graceful: pre-text stays
        try {
          mermaid.initialize({startOnLoad: false, theme: 'default'});
          const src = this.textContent.trim();
          const id = 'm' + Math.random().toString(36).slice(2);
          const out = await mermaid.render(id, src);
          this.innerHTML = out.svg || out;
        } catch (e) { /* leave source visible */ }
      };
      RO.lazyObs.observe(this);
    }
  });

  // <ro-jump-to figure="..."> — smooth-scroll anchor + transient highlight
  customElements.define('ro-jump-to', class extends HTMLElement {
    connectedCallback() {
      this.style.cursor = 'pointer'; this.style.color = 'var(--accent)';
      this.style.textDecoration = 'underline';
      this.addEventListener('click', () => {
        const id = this.getAttribute('figure') || this.getAttribute('section');
        const t = document.getElementById(id);
        if (t) {
          t.scrollIntoView({behavior: 'smooth', block: 'start'});
          t.style.transition = 'background 1.5s'; t.style.background = '#FFE79988';
          setTimeout(() => { t.style.background = ''; }, 1500);
        }
      });
    }
  });

  // Reading-time badge for story mode
  function updateReadingTime() {
    const el = document.querySelector('.reading-time');
    if (!el) return;
    const text = (document.querySelector('main') || document.body).innerText || '';
    const minutes = Math.max(1, Math.round(text.trim().split(/\s+/).length / 220));
    el.textContent = '~' + minutes + ' minute read';
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', updateReadingTime);
  } else { updateReadingTime(); }
})();
"""


# ──────────────────────────────────────────────────────────────────────
# Pack detection
# ──────────────────────────────────────────────────────────────────────

_QUALITATIVE_WORKSPACE_MARKERS = (
    "codebooks", "themes", "transcripts", "member_checks",
)
_HUMANITIES_WORKSPACE_MARKERS = (
    "edition", "apparatus", "transcriptions", "close_readings", "citations",
)


def _config_pack(root: Path) -> str | None:
    """Return the pack name from researcher_config.yaml, or None.

    Accepts any of: top-level ``pack:`` / ``domain:`` / ``packs: [...]``.
    """
    for rel in ("inputs/researcher_config.yaml", "researcher_config.yaml"):
        cfg_path = root / rel
        if not cfg_path.exists():
            continue
        try:
            import yaml  # type: ignore
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8",
                                                     errors="ignore")) or {}
        except Exception:
            continue
        if not isinstance(cfg, dict):
            continue
        for key in ("pack", "domain"):
            val = cfg.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()
        packs = cfg.get("packs")
        if isinstance(packs, list) and packs:
            for entry in packs:
                if isinstance(entry, str) and entry.strip():
                    return entry.strip().lower()
    return None


def _workspace_has_markers(root: Path, markers: tuple[str, ...]) -> bool:
    ws = root / "workspace"
    if not ws.is_dir():
        return False
    try:
        # Direct children first (cheap), then a shallow rglob fallback.
        children = {p.name for p in ws.iterdir() if p.is_dir()}
        if any(m in children for m in markers):
            return True
        for marker in markers:
            for hit in ws.rglob(marker):
                if hit.is_dir():
                    return True
    except OSError:
        return False
    return False


def detect_active_pack(root: Path) -> str | None:
    """Decide which domain-pack renderer (if any) the dashboard should use.

    Resolution order:
      1. ``researcher_config.yaml`` ``pack:`` / ``domain:`` / ``packs:``.
      2. Workspace markers (codebooks/themes/... for qualitative;
         edition/apparatus/... for humanities).

    Returns one of ``"qualitative"``, ``"humanities"``, or ``None`` for
    every other project (the generic renderer keeps running).
    """
    cfg_pack = _config_pack(root)
    if cfg_pack in {"qualitative", "humanities"}:
        return cfg_pack
    # Filesystem fallback. Humanities markers win ties because the
    # qualitative markers (e.g. transcripts/) are sometimes present in
    # humanities projects with interview-shaped oral-history sources.
    if _workspace_has_markers(root, _HUMANITIES_WORKSPACE_MARKERS):
        return "humanities"
    if _workspace_has_markers(root, _QUALITATIVE_WORKSPACE_MARKERS):
        return "qualitative"
    return None


# ──────────────────────────────────────────────────────────────────────
# Section + index builders
# ──────────────────────────────────────────────────────────────────────


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "section"


def _build_search_index(steps: list[dict[str, Any]], spec: dict[str, Any],
                        curated_figs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the MiniSearch document set. Each doc has ``id``, ``title``,
    ``section``, ``body``, ``anchor``. Kept small (~10-50 KB JSON for
    typical projects) so inlining stays cheap."""
    docs: list[dict[str, Any]] = []
    nid = 0
    abstract = (spec.get("abstract") or "").strip()
    if abstract:
        docs.append({"id": nid, "title": "Abstract", "section": "Abstract",
                     "body": abstract, "anchor": "#abstract"})
        nid += 1
    for fig in curated_figs:
        cap = (fig.get("caption") or "").strip()
        if not cap:
            continue
        stem = Path(fig.get("path") or "fig").stem
        docs.append({
            "id": nid,
            "title": f"Figure {stem}",
            "section": "Figures",
            "figure": stem,
            "body": cap[:1200],
            "anchor": f"#fig-{_slug(stem)}",
        })
        nid += 1
    for s in steps:
        title = s.get("id") or "step"
        body_chunks = [
            s.get("conclusions", "")[:2500],
            s.get("readme", "")[:1000],
            s.get("plain_summary", "")[:800],
        ]
        body = "\n".join(c for c in body_chunks if c).strip()
        if not body:
            continue
        docs.append({
            "id": nid,
            "title": title,
            "section": "Step appendix",
            "body": body[:3000],
            "anchor": f"#step-{_slug(title)}",
        })
        nid += 1
    for f in (spec.get("findings") or []):
        t = (f.get("title") or "Finding")[:120]
        body = (f.get("summary") or f.get("text") or "")[:1500]
        if not body:
            continue
        docs.append({
            "id": nid, "title": t, "section": "Findings", "body": body,
            "anchor": "#findings",
        })
        nid += 1
    return docs


def _step_status(step: dict[str, Any]) -> str:
    if step.get("is_dead_end"):
        return "dead-end"
    dec = (step.get("decision") or "").lower()
    if "proceed" in dec:
        return "completed"
    if "branch" in dec:
        return "branch"
    return "active"


def _build_sidebar(steps: list[dict[str, Any]], spec: dict[str, Any],
                   curated_figs: list[dict[str, Any]]) -> str:
    items = ['<details open><summary>Overview</summary><ul class="tree">'
             '<li><a href="#abstract">Abstract</a></li>'
             '<li><a href="#findings">Headline findings</a></li>'
             '<li><a href="#verdicts">Hypothesis verdicts</a></li>'
             '</ul></details>']
    if curated_figs:
        items.append('<details><summary>Figures</summary><ul class="tree">')
        for fig in curated_figs:
            stem = Path(fig.get("path") or "fig").stem
            items.append(f'<li><a href="#fig-{_slug(stem)}">{_escape(stem)}</a></li>')
        items.append("</ul></details>")
    if steps:
        items.append('<details open><summary>Steps</summary><ul class="tree">')
        for s in steps:
            label = s.get("id") or "step"
            status = _step_status(s)
            items.append(
                f'<li><a href="#step-{_slug(label)}" data-status="{status}">'
                f'{_escape(label)}</a></li>'
            )
        items.append("</ul></details>")
    items.append('<details><summary>Reproducibility</summary><ul class="tree">'
                 '<li><a href="#references">References</a></li>'
                 '<li><a href="#methods">Methodology</a></li></ul></details>')
    return f'<aside class="ro-sidebar"><ro-sidebar>{"".join(items)}</ro-sidebar></aside>'


def _build_filter_chips(steps: list[dict[str, Any]], state: dict[str, Any]) -> str:
    chips: list[str] = []
    hyps = state.get("active_hypotheses") or []
    for h in hyps[:6]:
        hid = h.get("id") or "H?"
        chips.append(f'<button class="chip" data-key="hyp:{_escape(hid)}">{_escape(hid)}</button>')
    seen = set()
    for s in steps:
        st = _step_status(s)
        if st in seen:
            continue
        seen.add(st)
        chips.append(f'<button class="chip" data-key="status:{st}">{st}</button>')
    chips.append('<button class="chip" data-key="verdict:disagrees">DISAGREES verdicts</button>')
    chips.append('<button class="chip" data-key="has:pdf">Has PDF evidence</button>')
    return f'<ro-filter>{"".join(chips)}</ro-filter>'


def _figure_companion(fig_path: Path, root: Path) -> dict[str, Any]:
    """For a static figure, look for an interactive HTML companion
    (``<stem>.html``) next to it. Return a dict with `static_src` and
    `interactive_src` (or empty string) — both as paths relative to
    the dashboard output dir (synthesis/)."""
    stem = fig_path.stem
    htmlc = fig_path.parent / f"{stem}.html"
    out: dict[str, Any] = {"stem": stem}
    try:
        out["static_src"] = str(fig_path.relative_to(root.parent)).replace("\\", "/") \
            if root.parent in fig_path.parents else str(fig_path)
    except ValueError:
        out["static_src"] = str(fig_path)
    # Compute relative path from the dashboard at <root>/synthesis/dashboard.html
    try:
        out["static_src"] = _rel_to_dashboard(fig_path, root)
    except Exception:
        pass
    out["interactive_src"] = ""
    if htmlc.exists():
        try:
            out["interactive_src"] = _rel_to_dashboard(htmlc, root)
        except Exception:
            out["interactive_src"] = ""
    caption_md = fig_path.with_suffix(".caption.md")
    summary_md = fig_path.with_suffix(".summary.md")
    out["caption"] = caption_md.read_text().strip() if caption_md.exists() else ""
    out["summary"] = summary_md.read_text().strip() if summary_md.exists() else ""
    return out


def _rel_to_dashboard(p: Path, root: Path) -> str:
    """Return ``p`` as a path relative to ``<root>/synthesis/`` (where
    dashboard.html lives). Uses POSIX separators."""
    import os as _os
    base = root / "synthesis"
    return _os.path.relpath(p, base).replace("\\", "/")


def _collect_figures_with_companions(root: Path) -> list[dict[str, Any]]:
    """Walk workspace + synthesis for figures and pair each with its
    optional interactive HTML companion. Order: synthesis/figures first
    (curated), then per-step outputs/figures."""
    out: list[dict[str, Any]] = []
    syn = root / "synthesis" / "figures"
    if syn.is_dir():
        for f in sorted(syn.iterdir()):
            if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}:
                out.append(_figure_companion(f, root))
    ws = root / "workspace"
    if ws.is_dir():
        for step in sorted(ws.iterdir()):
            figs = step / "outputs" / "figures"
            if not figs.is_dir():
                continue
            for f in sorted(figs.iterdir()):
                if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}:
                    out.append(_figure_companion(f, root))
    return out


def _build_figures_section(figures: list[dict[str, Any]]) -> str:
    if not figures:
        return ""
    blocks = []
    for fig in figures:
        stem = fig["stem"]
        cap = _escape(fig.get("caption") or "")[:400]
        static_src = _escape(fig.get("static_src") or "")
        inter_src = _escape(fig.get("interactive_src") or "")
        blocks.append(
            f'<figure id="fig-{_slug(stem)}">'
            f'<ro-figure-toggle figure-stem="{_escape(stem)}" '
            f'static-src="{static_src}" interactive-src="{inter_src}" '
            f'caption="{cap}"></ro-figure-toggle>'
            f'</figure>'
        )
    return (
        '<section class="ro-section" id="figures" data-tags="figures">'
        '<h2>Figures</h2>' + "".join(blocks) + '</section>'
    )


def _build_findings_section(spec: dict[str, Any]) -> str:
    findings = spec.get("findings") or []
    if not findings:
        return (
            '<section class="ro-section" id="findings" data-tags="findings">'
            '<h2>Headline findings</h2><p><em>(none authored in synthesis_spec.yaml)</em></p>'
            '</section>'
        )
    items = []
    for f in findings:
        t = _escape(f.get("title", "Finding"))
        body = _escape(f.get("summary") or f.get("text") or "")
        items.append(f"<li><strong>{t}</strong> — {body}</li>")
    return (
        '<section class="ro-section" id="findings" data-tags="findings">'
        '<h2>Headline findings</h2><ul>' + "".join(items) + "</ul></section>"
    )


def _build_abstract_section(spec: dict[str, Any]) -> str:
    abstract = (spec.get("abstract") or "").strip()
    if not abstract:
        return (
            '<section class="ro-section" id="abstract" data-tags="abstract">'
            '<h2>Abstract</h2><p><em>(authored in synthesis_spec.yaml)</em></p>'
            '</section>'
        )
    return (
        '<section class="ro-section" id="abstract" data-tags="abstract">'
        f'<h2>Abstract</h2><p>{_escape(abstract)}</p></section>'
    )


def _build_verdicts_section(state: dict[str, Any]) -> str:
    hyps = state.get("active_hypotheses") or []
    if not hyps:
        return ""
    rows = []
    for h in hyps:
        hid = _escape(h.get("id") or "H?")
        txt = _escape(h.get("text") or "")
        status = _escape((h.get("status") or "").upper() or "IN PROGRESS")
        rows.append({"id": hid, "hypothesis": txt, "status": status})
    cols = ["id", "hypothesis", "status"]
    data = json.dumps({"columns": cols, "rows": rows})
    return (
        '<section class="ro-section" id="verdicts" data-tags="verdicts">'
        '<h2>Hypothesis verdicts</h2>'
        f'<ro-table name="verdicts"><script type="application/json">{data}</script></ro-table>'
        '</section>'
    )


def _build_steps_section(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return ""
    blocks = []
    for s in steps:
        sid = s.get("id") or "step"
        status = _step_status(s)
        plain = _escape((s.get("plain_summary") or "")[:1200])
        headline = _escape(s.get("headline") or "")
        decision = _escape(s.get("decision") or "")
        body_parts = []
        if headline:
            body_parts.append(f"<p><strong>Headline:</strong> {headline}</p>")
        if plain:
            body_parts.append(f"<p>{plain}</p>")
        if decision:
            body_parts.append(f"<p><em>Decision:</em> {decision}</p>")
        blocks.append(
            f'<section class="ro-section" id="step-{_slug(sid)}" '
            f'data-tags="step,status:{status}">'
            f'<h2>{_escape(sid)}</h2>'
            + "".join(body_parts) + "</section>"
        )
    return "".join(blocks)


def _build_references_section(root: Path) -> str:
    cit = root / "workspace" / "citations.md"
    if cit.exists():
        body = cit.read_text()[:50000]
        return (
            '<section class="ro-section" id="references" data-tags="references">'
            '<h2>References</h2><pre style="white-space:pre-wrap;font-family:var(--mono);'
            'font-size:13px">' + _escape(body) + "</pre></section>"
        )
    return ""


def _build_methods_section(spec: dict[str, Any]) -> str:
    m = (spec.get("methodology") or spec.get("methods") or "").strip()
    if not m:
        return ""
    return (
        '<section class="ro-section" id="methods" data-tags="methods">'
        f'<h2>Methodology</h2><p>{_escape(m)}</p></section>'
    )


def _build_story_section(root: Path, spec: dict[str, Any],
                          steps: list[dict[str, Any]]) -> str:
    """Render the story-mode markdown view. Pulls
    ``synthesis/dashboard_story.md`` if present, else assembles a
    fallback from the abstract + per-step plain summaries."""
    story_md_path = root / "synthesis" / "dashboard_story.md"
    if story_md_path.exists():
        md = story_md_path.read_text()
    else:
        md = _autogen_story_md(spec, steps)
    html_body = _tiny_md_to_html(md)
    return (
        '<section class="ro-section story-only" id="story" data-tags="story">'
        '<div class="reading-time">~? minute read</div>'
        + html_body +
        '</section>'
    )


def _autogen_story_md(spec: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    title = spec.get("title") or "Research story"
    parts.append(f"# {title}\n")
    if spec.get("abstract"):
        parts.append(spec["abstract"].strip() + "\n")
    for s in steps:
        sid = s.get("id") or "step"
        parts.append(f"\n## {sid}\n")
        if s.get("plain_summary"):
            parts.append(s["plain_summary"].strip() + "\n")
        if s.get("headline"):
            parts.append(f"\n> {s['headline']}\n")
    for f in (spec.get("findings") or [])[:5]:
        t = f.get("title", "Finding")
        body = f.get("summary") or f.get("text") or ""
        parts.append(f"\n### {t}\n{body}\n")
    return "\n".join(parts).strip() + "\n"


def _tiny_md_to_html(md: str) -> str:
    """Tiny markdown subset: headings (##/###), paragraphs, blockquotes,
    callouts. Enough for the auto-generated story; researcher polishes
    via ``tool_dashboard_story_edit``."""
    out: list[str] = []
    block: list[str] = []

    def flush(tag: str = "p"):
        if block:
            txt = " ".join(block).strip()
            if txt:
                out.append(f"<{tag}>{_escape(txt)}</{tag}>")
            block.clear()

    in_callout = False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("# "):
            flush()
            out.append(f"<h1>{_escape(s[2:])}</h1>")
        elif s.startswith("## "):
            flush()
            out.append(f"<h2>{_escape(s[3:])}</h2>")
        elif s.startswith("### "):
            flush()
            out.append(f"<h3>{_escape(s[4:])}</h3>")
        elif s.startswith("> "):
            flush()
            if not in_callout:
                out.append('<div class="adversarial-callout">')
                in_callout = True
            out.append(f"<p>{_escape(s[2:])}</p>")
        elif not s:
            flush()
            if in_callout:
                out.append("</div>")
                in_callout = False
        else:
            block.append(s)
    flush()
    if in_callout:
        out.append("</div>")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────
# Top-level renderer
# ──────────────────────────────────────────────────────────────────────


def render_dashboard_v2(
    root: Path,
    title: str | None = None,
    audience: str = "academic",
    default_mode: str = "explore",
    search_enabled: bool = True,
    print_optimized: bool = True,
    suppress_audit_panel: bool = False,
) -> dict[str, Any]:
    """Render the new single-page dashboard.

    Args:
        root: project root.
        title: optional override for header title.
        audience: kept for compat with v1; v2 currently treats every
            audience the same and lets the user toggle Story/Explore.
        default_mode: ``"story"`` or ``"explore"``. URL hash
            (``#mode=story``) and localStorage override this.
        search_enabled: when False, the search element + index are
            omitted (smaller HTML, faster paint).
        print_optimized: when False, the print stylesheet is dropped
            (a few KB saved; rare).
        suppress_audit_panel: passthrough from the handler. The audit
            panel isn't a v2 first-class section yet — the flag is
            recorded in result-meta for the override log.

    Returns: same shape as v1's ``render_dashboard`` plus an
    ``renderer="v2"`` discriminator and ``js_bundles`` list.
    """
    # Lazy imports: v1 module owns the data-collection helpers; we
    # avoid duplicating ~600 lines by reusing them.
    from research_os.tools.actions.synthesis.dashboard import (
        _collect_steps, _load_config, _load_spec, _load_state,
    )
    from research_os.project_ops import ensure_lazy_dir
    try:
        state = _load_state(root)
        cfg = _load_config(root)
        spec = _load_spec(root)
        steps = _collect_steps(root)
        figures = _collect_figures_with_companions(root)

        project_title = (
            title or spec.get("title")
            or state.get("project_name")
            or cfg.get("project_name")
            or "Research project"
        )

        # Build the index + sections
        search_docs = _build_search_index(steps, spec, figures) if search_enabled else []
        sidebar_html = _build_sidebar(steps, spec, figures)
        filter_html = _build_filter_chips(steps, state)
        # Pack-aware section dispatch. The qualitative + humanities
        # renderers append after figures/verdicts and before the generic
        # step appendix so reviewers see the domain-shaped artefacts
        # first. The generic STEM renderer keeps its existing layout.
        pack = detect_active_pack(root)
        pack_sections_html = ""
        if pack == "qualitative":
            try:
                from research_os.tools.actions.synthesis.dashboard_v2_qualitative \
                    import render_qualitative_section
                pack_sections_html = render_qualitative_section(root, spec, state)
            except Exception:
                logger.exception("qualitative section render failed")
                pack_sections_html = ""
        elif pack == "humanities":
            try:
                from research_os.tools.actions.synthesis.dashboard_v2_humanities \
                    import render_humanities_section
                pack_sections_html = render_humanities_section(root, spec, state)
            except Exception:
                logger.exception("humanities section render failed")
                pack_sections_html = ""
        sections_html = "".join([
            _build_abstract_section(spec),
            _build_story_section(root, spec, steps),
            _build_findings_section(spec),
            _build_verdicts_section(state),
            _build_figures_section(figures),
            pack_sections_html,
            _build_steps_section(steps),
            _build_methods_section(spec),
            _build_references_section(root),
        ])

        # Header chrome
        search_html = "<ro-search></ro-search>" if search_enabled else ""
        toggle_html = f'<ro-mode-toggle default="{_escape(default_mode)}"></ro-mode-toggle>'
        header_html = (
            f'<header class="ro-header"><div class="title">{_escape(project_title)}</div>'
            f'<div class="grow"></div>{search_html}{toggle_html}</header>'
        )

        # JS bundles
        js_blob, included = bundled_js(root)

        # Search-index payload
        search_index_html = ""
        if search_enabled and search_docs:
            search_index_html = (
                '<script type="application/x-ro-search-index">'
                + json.dumps(search_docs).replace("</", "<\\/")
                + "</script>"
            )

        css = DASHBOARD_V2_CSS
        if not print_optimized:
            css = re.sub(r"@media print \{[^}]*\}.*", "", css, count=1, flags=re.DOTALL)

        commit_hash = _detect_commit_hash(root)
        version = _ro_version()
        gen_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        footer = (
            f'<footer class="ro-footer">Generated {gen_ts} '
            f'· Research-OS {_escape(version)}'
            + (f' · commit {_escape(commit_hash[:12])}' if commit_hash else "")
            + ' · <span class="ro-print-hidden">'
            f'audience={_escape(audience)}, suppress_audit={str(bool(suppress_audit_panel)).lower()}'
            '</span></footer>'
        )

        body = "".join([
            "<!doctype html>\n<html lang='en'><head>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
            '<meta name="ro-renderer" content="v2">',
            '<meta name="ro-default-mode" content="', _escape(default_mode), '">',
            f"<title>{_escape(project_title)}</title>",
            f"<style>{css}</style>",
            "</head><body>",
            '<div class="app">',
            header_html,
            sidebar_html,
            '<main class="ro-main">',
            filter_html,
            sections_html,
            "</main>",
            footer,
            "</div>",
            search_index_html,
            f"<script>{js_blob}</script>",
            "</body></html>",
        ])

        synthesis_dir = ensure_lazy_dir(root, "synthesis")
        out_path = synthesis_dir / "dashboard.html"
        out_path.write_text(body)
        figures_embedded = len(figures)
        result = {
            "status": "success",
            "renderer": "v2",
            "dashboard_path": str(out_path.relative_to(root)),
            "size_kb": round(out_path.stat().st_size / 1024, 1),
            "figures_embedded": figures_embedded,
            "steps": len(steps),
            "hypotheses": len(state.get("active_hypotheses") or []),
            "uses_spec": bool(spec),
            "js_bundles": included,
            "default_mode": default_mode,
            "search_enabled": search_enabled,
            "search_index_docs": len(search_docs),
            "active_pack": pack or "",
        }
        return result
    except Exception as e:
        logger.exception("render_dashboard_v2 failed")
        return {"status": "error", "renderer": "v2", "message": str(e)}


def _ro_version() -> str:
    try:
        from research_os import __version__ as v
        return v
    except Exception:
        return "?"


def _detect_commit_hash(root: Path) -> str:
    """Find a reproducibility commit hash if the project has been
    init'd as a git repo. Returns empty string on any failure — the
    dashboard renders fine without one."""
    head = root / ".git" / "HEAD"
    if not head.exists():
        return ""
    try:
        h = head.read_text().strip()
        if h.startswith("ref:"):
            ref = h.split(" ", 1)[1].strip()
            f = root / ".git" / ref
            if f.exists():
                return f.read_text().strip()
        return h
    except Exception:
        return ""


__all__ = [
    "render_dashboard_v2",
    "bundled_js",
    "DASHBOARD_V2_CSS",
    "CUSTOM_ELEMENTS_JS",
    "detect_active_pack",
]
