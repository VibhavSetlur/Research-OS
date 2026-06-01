"""Research-summary dashboard generator (project-agnostic).

Produces ``synthesis/dashboard.html`` as a single self-contained HTML file
(figures base64-embedded) with the polished structure of a real research
deliverable: Abstract → Overview → Sample / Cleaning → Workflow → Verdicts
at a glance → per-hypothesis findings → Methodological considerations →
Limitations → Open questions → Glossary → References.

The dashboard is built from whatever the project already records:

* ``inputs/researcher_config.yaml`` — project name, audience, intake
* ``.os_state/state_ledger.yaml`` — hypothesis tracker (drives verdicts)
* ``workspace/<step>/conclusions.md`` — section-level extraction
* ``synthesis/figures/*.png`` + sibling ``.caption.md`` — curated figures
* ``workspace/<step>/outputs/figures/<step>_*.png`` — per-step focal fig
* ``workspace/citations.md`` — references
* Optional ``synthesis/dashboard_spec.yaml`` — explicit RQ → figure mapping
  for projects that want to author the structure rather than auto-derive it

Editorial conventions enforced by the generator:

* Supportive, professional research voice. The dashboard never says
  "wrong" / "smoking gun" / "Megan failed to"; it says "would benefit
  from" / "consider" / "the alternative interpretation is".
* No filesystem paths in the visible text — the reader of a dashboard
  should not have to open the project folder.
* Every figure carries a substantive caption (placeholder text is
  surfaced as an editorial TODO, not hidden).
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.synthesis.dashboard")


# ---------------------------------------------------------------------------
# Glossary — same 16-card grid the reference dashboard ships with. Cards
# are search-link augmented, not auto-injected into prose, so the
# dashboard reads as a finished document.
# ---------------------------------------------------------------------------

GLOSSARY: list[dict[str, str]] = [
    {"name": "Cronbach's α (alpha)", "body": "A number 0–1 measuring how internally consistent a multi-item scale is — whether the items \"hang together\" as if they're measuring the same underlying construct.<br><strong>Conventional thresholds:</strong> ≥ .80 good, ≥ .70 acceptable, ≥ .60 questionable, &lt; .60 unacceptable.", "search": "cronbach alpha explained", "wiki": "Cronbach%27s_alpha"},
    {"name": "Reverse-coding", "body": "When a scale mixes positively-worded items with negatively-worded items, the negatives are flipped (new = max − original) before combining — otherwise the composite stops being internally coherent.", "search": "reverse coding likert scale", "wiki": "Likert_scale#Reverse_scoring"},
    {"name": "Item-rest correlation", "body": "For each item, the correlation between its score and the sum of all the other items in its scale. Low values (&lt; .30) suggest the item is measuring something different from the rest of the scale.", "search": "item-rest correlation psychometrics"},
    {"name": "Spearman ρ vs Pearson r", "body": "Both measure correlation from −1 to +1. <strong>Pearson</strong> assumes linearity and normal data. <strong>Spearman</strong> works on ranks and is robust to non-normal data. For Likert-type data, Spearman is the safer default.", "search": "spearman vs pearson correlation"},
    {"name": "Welch's t-test", "body": "A t-test that does <em>not</em> assume the two groups have equal variances. Modern statistical practice prefers Welch as the default over the standard (Student's) t-test.", "search": "welch t test when to use", "wiki": "Welch%27s_t-test"},
    {"name": "Mann-Whitney U test", "body": "A non-parametric rank-based test for whether two groups differ in central tendency. The robust alternative to the t-test when the data are not normally distributed.", "search": "mann whitney u test explained", "wiki": "Mann%E2%80%93Whitney_U_test"},
    {"name": "Kruskal-Wallis ANOVA", "body": "The non-parametric version of one-way ANOVA, working on ranks. Used when comparing three or more groups whose underlying data are not normally distributed.", "search": "kruskal wallis test explained", "wiki": "Kruskal%E2%80%93Wallis_one-way_analysis_of_variance"},
    {"name": "Benjamini-Hochberg (BH) correction", "body": "When many statistical tests are run, the chance of at least one false positive grows. BH adjusts p-values to control the false discovery rate — \"of tests called significant, about 5% will be false alarms.\" Less harsh than Bonferroni; modern default.", "search": "benjamini hochberg false discovery rate", "wiki": "False_discovery_rate"},
    {"name": "Bootstrap 95% CI", "body": "Instead of formula-based intervals, the bootstrap simulates \"what would happen if I drew another sample like this one\" by resampling the data many times and taking the middle 95% of the resulting statistics. Especially honest for small samples and non-normal data.", "search": "bootstrap confidence interval explained", "wiki": "Bootstrapping_(statistics)"},
    {"name": "Effect size — Cohen's d, η², r", "body": "How <em>big</em> an effect is, separately from \"is it significant.\" A p-value can be tiny in a huge sample even when the effect itself is trivially small.<br><strong>Cohen's d:</strong> .20 small, .50 medium, .80 large. <strong>η² (eta squared):</strong> .01 small, .06 medium, .14 large.", "search": "cohen d effect size interpretation", "wiki": "Effect_size"},
    {"name": "Relative Risk (RR)", "body": "The ratio of two probabilities. RR = 3.55 means group A is 3.55× as likely as group B to do something. RR = 1 means no difference. A 95% CI that excludes 1 indicates a detectable difference.", "search": "relative risk vs odds ratio"},
    {"name": "Ceiling effect", "body": "When most respondents pick the top of a scale, the item cannot distinguish among high-end respondents — it is \"topped out.\" Common in items where it is socially difficult to disagree.", "search": "ceiling effect survey research", "wiki": "Ceiling_effect_(statistics)"},
    {"name": "\"Fail to reject\" vs \"reject\" the null", "body": "<em>Reject</em> the null = there is evidence of an effect. <em>Fail to reject</em> = there is no evidence of an effect — which is <strong>not</strong> the same as \"there is no effect.\" In small samples, \"no evidence of an effect\" is the honest framing.", "search": "fail to reject null hypothesis meaning"},
    {"name": "Statistical power", "body": "The probability of detecting a real effect, if one exists. Depends on sample size, effect size, and α. Modest sample sizes typically leave moderate-effect tests underpowered, which is why \"no detectable difference\" findings deserve careful framing.", "search": "statistical power sample size explained", "wiki": "Statistical_power"},
    {"name": "Common-method bias", "body": "When two constructs are measured with the same instrument at the same time, some of the observed correlation reflects shared response style rather than a true substantive relationship between the constructs.", "search": "common method bias survey research", "wiki": "Common-method_variance"},
    {"name": "Partial correlation", "body": "The correlation between two variables after controlling for a third. Used to check that an observed relationship is not just an artifact of a confounding variable.", "search": "partial correlation explained", "wiki": "Partial_correlation"},
]


# ---------------------------------------------------------------------------
# CSS / JS — the polished research-publication style. Single string so the
# dashboard remains self-contained.
# ---------------------------------------------------------------------------

DASHBOARD_CSS = r"""
:root {
  --bg: #ffffff; --fg: #1a202c; --fg-soft: #2d3748; --muted: #6b7280;
  --soft-bg: #f7fafc; --card-bg: #ffffff;
  --border: #e2e8f0; --border-strong: #cbd5e1;
  --primary: #2c5282; --primary-soft: #ebf4ff; --primary-dark: #1a365d;
  --accent: #b7791f; --accent-soft: #fffbeb;
  --good: #276749; --good-soft: #f0fff4;
  --warn: #b7791f; --warn-soft: #fffaf0;
  --bad: #9b2c2c; --bad-soft: #fff5f5;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.04);
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
}
html[data-theme="dark"] {
  --bg: #0d1117; --fg: #e6edf3; --fg-soft: #c9d1d9; --muted: #8b949e;
  --soft-bg: #161b22; --card-bg: #161b22; --border: #30363d; --border-strong: #484f58;
  --primary: #79b8ff; --primary-soft: #1f2a48; --primary-dark: #58a6ff;
  --accent: #f0883e; --accent-soft: #2d1f0f;
  --good: #56d364; --good-soft: #0e2a16;
  --warn: #d29922; --warn-soft: #2d2406;
  --bad: #f85149; --bad-soft: #2d0a0a;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.4); --shadow: 0 1px 3px rgba(0,0,0,.5);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: 'Charter', 'Iowan Old Style', 'Cambria', Georgia, serif;
  font-size: 17px; line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--primary); text-decoration: none; border-bottom: 1px solid transparent; transition: border-color .15s; }
a:hover { border-bottom-color: var(--primary); }
h1, h2, h3, h4 {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', Helvetica, Arial, sans-serif;
  color: var(--fg); letter-spacing: -0.01em;
  margin-top: 1.8em; margin-bottom: 0.5em; line-height: 1.25;
}
h1 { font-size: 2.2rem; font-weight: 700; letter-spacing: -0.02em; margin-top: 0; }
h2 { font-size: 1.55rem; font-weight: 700; color: var(--primary);
  border-bottom: 1px solid var(--border); padding-bottom: 0.45rem; }
h3 { font-size: 1.2rem; font-weight: 600; color: var(--fg-soft); }
h4 { font-size: 1.02rem; font-weight: 600; color: var(--fg-soft); margin-top: 1.4em; }
p { margin: 0.6em 0 1.1em; }
ul, ol { padding-left: 1.5em; }
li { margin: 0.35em 0; }
code {
  font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.86em; background: var(--soft-bg);
  padding: 0.12rem 0.4rem; border-radius: 3px; color: var(--accent);
  border: 1px solid var(--border);
}
blockquote {
  margin: 1.4em 0; padding: 1rem 1.4rem;
  background: var(--primary-soft); border-left: 3px solid var(--primary);
  border-radius: 0 6px 6px 0; color: var(--fg-soft); font-style: italic;
}
blockquote p { margin: 0.3em 0; }

.layout { display: grid; grid-template-columns: 260px 1fr; min-height: 100vh; }
@media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } aside.toc { display: none; } }

aside.toc {
  background: var(--soft-bg); border-right: 1px solid var(--border);
  padding: 1.8rem 1rem 2rem;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.9rem;
}
aside.toc .brand { padding: 0 0.5rem 1.1rem; border-bottom: 1px solid var(--border); margin-bottom: 0.9rem; }
aside.toc .brand .title { font-weight: 700; color: var(--primary); font-size: 1rem; }
aside.toc .brand .subtitle { color: var(--muted); font-size: 0.78rem; margin-top: 0.3rem; line-height: 1.4; }
aside.toc h5 {
  margin: 1.1em 0 0.35em 0.5em; font-size: 0.7rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.11em; color: var(--muted);
}
aside.toc ul { list-style: none; padding: 0; margin: 0; }
aside.toc a {
  display: block; padding: 0.4rem 0.75rem; border-radius: 4px;
  color: var(--fg-soft); font-size: 0.88rem; border-bottom: none;
  transition: background .12s, color .12s;
}
aside.toc a:hover { background: var(--primary-soft); color: var(--primary); }
aside.toc a.active { background: var(--primary); color: white; font-weight: 600; }

main { padding: 3rem 4rem; max-width: 1080px; margin: 0 auto; }
@media (max-width: 900px) { main { padding: 2rem 1.2rem; } }

header.frontpage {
  margin: -3rem -4rem 2.5rem; padding: 4rem 4rem 2.8rem;
  background: var(--soft-bg); border-bottom: 3px solid var(--primary);
}
@media (max-width: 900px) { header.frontpage { margin: -2rem -1.2rem 2rem; padding: 3rem 1.5rem 2rem; } }
header.frontpage .eyebrow {
  color: var(--primary); font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; font-size: 0.78rem; margin-bottom: 0.6rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
}
header.frontpage h1 { color: var(--fg); }
header.frontpage .subtitle {
  font-size: 1.1rem; color: var(--fg-soft); max-width: 720px;
  margin-top: 0.8rem; line-height: 1.55;
}
header.frontpage .meta {
  margin-top: 1.8rem; display: grid;
  grid-template-columns: auto 1fr; gap: 0.35rem 1.2rem;
  font-size: 0.9rem; color: var(--fg-soft); max-width: 720px;
}
header.frontpage .meta dt { font-weight: 600; color: var(--muted); }
header.frontpage .actions { margin-top: 1.8rem; display: flex; gap: 0.5rem; flex-wrap: wrap; }
header.frontpage button {
  background: var(--primary); color: white; border: 1px solid var(--primary);
  border-radius: 4px; padding: 0.45rem 0.95rem; cursor: pointer;
  font-size: 0.86rem; font-weight: 500;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  transition: opacity .12s;
}
header.frontpage button.secondary { background: transparent; color: var(--primary); }
header.frontpage button:hover { opacity: 0.85; }

section { margin: 3rem 0; scroll-margin-top: 1rem; }

.card { background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 6px; padding: 1.3rem 1.6rem; margin: 1.2rem 0; box-shadow: var(--shadow); }
.card.abstract { background: var(--primary-soft); border-color: var(--primary); border-left: 4px solid var(--primary); }
.card.flag { background: var(--bad-soft); border-color: var(--bad); border-left: 4px solid var(--bad); }
.card.note { background: var(--warn-soft); border-color: var(--warn); border-left: 4px solid var(--warn); }
.card.ok { background: var(--good-soft); border-color: var(--good); border-left: 4px solid var(--good); }
.card .label {
  display: inline-block; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.7rem; font-weight: 700; letter-spacing: 0.11em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem;
}
.card.flag .label { color: var(--bad); }
.card.note .label { color: var(--warn); }
.card.ok .label { color: var(--good); }
.card.abstract .label { color: var(--primary); }
.card h4 { margin-top: 0; }

.pill {
  display: inline-block; padding: 0.2rem 0.6rem;
  background: var(--primary-soft); color: var(--primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.72rem; font-weight: 600; border-radius: 999px; margin-right: 0.3rem;
}
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.bad { background: var(--bad-soft); color: var(--bad); }
.pill.ok { background: var(--good-soft); color: var(--good); }

.verdicts { background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.verdict-row {
  display: grid; grid-template-columns: 1fr auto auto; gap: 1rem; align-items: center;
  padding: 1rem 1.3rem; border-bottom: 1px solid var(--border);
}
.verdict-row:last-child { border-bottom: none; }
.verdict-row .name { font-weight: 600; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; }
.verdict-row .desc { color: var(--muted); font-size: 0.88rem; margin-top: 0.2rem; }
.verdict-row .verdict {
  padding: 0.32rem 0.75rem; border-radius: 4px;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.8rem; font-weight: 600; white-space: nowrap;
}
.verdict-row .verdict.reject { background: var(--bad-soft); color: var(--bad); border: 1px solid var(--bad); }
.verdict-row .verdict.refuted { background: var(--bad-soft); color: var(--bad); border: 1px solid var(--bad); }
.verdict-row .verdict.ftr { background: var(--good-soft); color: var(--good); border: 1px solid var(--good); }
.verdict-row .verdict.supported { background: var(--good-soft); color: var(--good); border: 1px solid var(--good); }
.verdict-row .verdict.mixed { background: var(--warn-soft); color: var(--warn); border: 1px solid var(--warn); }
.verdict-row .verdict.inconclusive { background: var(--warn-soft); color: var(--warn); border: 1px solid var(--warn); }
.verdict-row .verdict.testing { background: var(--soft-bg); color: var(--muted); border: 1px solid var(--border); }

table {
  border-collapse: collapse; width: 100%; margin: 1.2rem 0;
  font-size: 0.9rem; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
}
th, td { border: 1px solid var(--border); padding: 0.55rem 0.8rem; text-align: left; vertical-align: top; }
th { background: var(--soft-bg); color: var(--fg-soft); font-weight: 600;
  cursor: pointer; user-select: none; font-size: 0.84rem; }
th:hover { background: var(--primary-soft); color: var(--primary); }
th[data-sort-asc]::after { content: " ▲"; opacity: 0.7; }
th[data-sort-desc]::after { content: " ▼"; opacity: 0.7; }
tbody tr:nth-child(even) { background: var(--soft-bg); }
tbody tr:hover { background: var(--primary-soft); }

.figure { margin: 2rem 0; padding: 1rem; background: var(--soft-bg); border-radius: 6px; border: 1px solid var(--border); }
.figure img {
  width: 100%; max-width: 100%; border: 1px solid var(--border-strong); border-radius: 4px;
  background: white; display: block; cursor: zoom-in; transition: opacity .15s;
}
.figure img:hover { opacity: 0.92; }
.figure figcaption { padding: 0.9rem 0 0.2rem; font-size: 0.93rem; color: var(--fg-soft); line-height: 1.55; }
.figure figcaption .figlabel {
  display: block; font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-weight: 700; font-size: 0.78rem; color: var(--primary); letter-spacing: 0.05em;
  text-transform: uppercase; margin-bottom: 0.4rem;
}
.figure figcaption .figcap-placeholder {
  background: var(--warn-soft); color: var(--warn);
  padding: 0.6rem 0.9rem; border-radius: 4px; border: 1px dashed var(--warn);
  font-style: italic; display: block;
}

#lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.92);
  display: none; align-items: center; justify-content: center; z-index: 100; cursor: zoom-out; padding: 2rem; }
#lightbox.open { display: flex; }
#lightbox img { max-width: 95vw; max-height: 95vh; border-radius: 6px; }

details {
  background: var(--soft-bg); border: 1px solid var(--border);
  border-radius: 4px; margin: 0.8rem 0; padding: 0.7rem 1.2rem;
}
details summary {
  cursor: pointer; font-weight: 600; color: var(--primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.92rem; padding: 0.2rem 0;
}
details[open] summary { margin-bottom: 0.8rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }

.glossary { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; margin-top: 1.4rem; }
.glossary .term { background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; padding: 1.1rem; box-shadow: var(--shadow-sm); }
.glossary .term h4 { margin: 0 0 0.5rem; color: var(--primary); font-size: 0.98rem; }
.glossary .term p { margin: 0.4rem 0; font-size: 0.88rem; line-height: 1.55; }
.glossary .term .lookup { margin-top: 0.7rem; display: flex; gap: 0.4rem; flex-wrap: wrap; }
.glossary .term .lookup a {
  background: var(--primary-soft); color: var(--primary);
  padding: 0.2rem 0.55rem; border-radius: 3px;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-size: 0.75rem; border: none;
}
.glossary .term .lookup a:hover { background: var(--primary); color: white; border-bottom: none; }

.summary-card {
  background: var(--good-soft); border-left: 4px solid var(--good);
  padding: 1.1rem 1.4rem; margin: 1.4rem 0; border-radius: 0 6px 6px 0;
}
.summary-card .label {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
  font-weight: 700; font-size: 0.72rem; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--good); margin-bottom: 0.4rem; display: block;
}

footer { margin-top: 5rem; padding: 2rem 0 1rem; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 0.85rem; text-align: center; }

@media print {
  aside.toc, header.frontpage .actions, #lightbox { display: none !important; }
  main { padding: 1rem; max-width: none; }
  .figure { break-inside: avoid; }
  details { break-inside: avoid; }
  details > *:not(summary) { display: block !important; }
  .card { break-inside: avoid; }
  body { font-size: 11pt; line-height: 1.5; }
}
"""


DASHBOARD_JS = r"""
function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("dashboard-theme", next); } catch(e) {}
}
try { const saved = localStorage.getItem("dashboard-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved); } catch(e) {}

document.querySelectorAll(".figure img").forEach(img => {
  img.addEventListener("click", e => {
    e.preventDefault();
    const lb = document.getElementById("lightbox");
    document.getElementById("lightbox-img").src = img.src;
    lb.classList.add("open");
  });
});

document.querySelectorAll("aside.toc a").forEach(a => {
  a.addEventListener("click", e => {
    const id = a.getAttribute("href").slice(1);
    const el = document.getElementById(id);
    if (el) { e.preventDefault(); el.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + id); }
  });
});
const sections = [...document.querySelectorAll("section[id]")];
const tocLinks = [...document.querySelectorAll("aside.toc a")];
function updateActive() {
  let active = sections[0];
  for (const s of sections) { if (s.getBoundingClientRect().top < 250) active = s; }
  tocLinks.forEach(a => a.classList.toggle("active",
    active && a.getAttribute("href") === "#" + active.id));
}
window.addEventListener("scroll", updateActive);
updateActive();

document.querySelectorAll("table").forEach(table => {
  table.querySelectorAll("th").forEach((th, idx) => {
    th.addEventListener("click", () => {
      const tbody = table.querySelector("tbody"); if (!tbody) return;
      const rows = [...tbody.querySelectorAll("tr")];
      const asc = !th.hasAttribute("data-sort-asc");
      table.querySelectorAll("th").forEach(h => {
        h.removeAttribute("data-sort-asc"); h.removeAttribute("data-sort-desc"); });
      th.setAttribute(asc ? "data-sort-asc" : "data-sort-desc", "");
      rows.sort((a, b) => {
        const A = a.children[idx].textContent.trim();
        const B = b.children[idx].textContent.trim();
        const nA = parseFloat(A); const nB = parseFloat(B);
        if (!isNaN(nA) && !isNaN(nB)) return asc ? nA - nB : nB - nA;
        return asc ? A.localeCompare(B) : B.localeCompare(A);
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });
});
"""


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _md_inline(text: str) -> str:
    """Tiny markdown-to-HTML for inline formatting only (no block parsing).

    Handles **bold**, *italic*, `code`, [text](url) — enough for caption
    sidecars and one-line snippets. Block content stays in <pre> elsewhere.
    """
    if not text:
        return ""
    out = _escape(text)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    return out


def _b64_img(path: Path) -> str | None:
    try:
        suffix = path.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "svg": "image/svg+xml", "gif": "image/gif", "webp": "image/webp"}.get(suffix, "image/png")
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception as e:
        logger.warning("b64 encode failed for %s: %s", path, e)
        return None


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def _load_state(root: Path) -> dict[str, Any]:
    from research_os.project_ops import load_state
    try:
        return load_state(root) or {}
    except Exception:
        return {}


def _load_config(root: Path) -> dict[str, Any]:
    cfg_path = root / "inputs" / "researcher_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}


def _load_spec(root: Path) -> dict[str, Any]:
    """Optional per-project authored structure. If present, overrides
    auto-derivation for specific sections (abstract, RQ list, etc.).

    Looks for ``synthesis/synthesis_spec.yaml`` first (canonical name),
    then falls back to ``synthesis/dashboard_spec.yaml`` (legacy). The
    file is the single editorial source consumed by the paper,
    dashboard, and poster builders so they share titles, abstracts,
    findings, limitations, and references."""
    for fname in ("synthesis_spec.yaml", "dashboard_spec.yaml"):
        spec_path = root / "synthesis" / fname
        if spec_path.exists():
            try:
                import yaml  # type: ignore
                return yaml.safe_load(spec_path.read_text()) or {}
            except Exception:
                return {}
    return {}


def _section_from_md(text: str, header_pattern: str) -> str:
    pat = re.compile(rf"^##\s+{header_pattern}\s*\n(.*?)(?=^##\s|\Z)",
                     re.MULTILINE | re.DOTALL | re.IGNORECASE)
    m = pat.search(text or "")
    return m.group(1).strip() if m else ""


def _collect_steps(root: Path) -> list[dict[str, Any]]:
    """Collect each step's full context for the dashboard.

    Per step we surface:
      * ``conclusions``        — full text for the appendix.
      * ``focal_figure``       — Path to the most representative PNG.
      * ``focal_caption``      — technical caption (from .caption.md).
      * ``focal_summary``      — plain-English (from .summary.md).
      * ``plain_summary``      — pulled from context/notes.md or
                                  conclusions.md's "Plain-language summary".
      * ``headline``           — first bullet of Findings.
      * ``readme``             — short overview for non-experts.
      * ``decision``           — proceed | branch | dead-end.
    """
    ws = root / "workspace"
    out: list[dict[str, Any]] = []
    if not ws.exists():
        return out
    for p in sorted(ws.iterdir()):
        if not (p.is_dir() and re.match(r"^\d{2,3}_", p.name)):
            continue
        conc_text = (p / "conclusions.md").read_text() if (p / "conclusions.md").exists() else ""
        readme_text = (p / "README.md").read_text() if (p / "README.md").exists() else ""

        info: dict[str, Any] = {
            "id": p.name,
            "is_dead_end": p.name.endswith("__DEAD_END"),
            "conclusions": conc_text,
            "readme": readme_text,
        }

        # Focal figure: prefer one starting with step number; else first.
        focal: Path | None = None
        figs_dir = p / "outputs" / "figures"
        if figs_dir.exists():
            step_num = p.name.split("_", 1)[0]
            cands = [
                f for f in sorted(figs_dir.iterdir())
                if f.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
            ]
            focal = next(
                (f for f in cands if f.name.startswith(f"{step_num}_")),
                cands[0] if cands else None,
            )
        info["focal_figure"] = focal
        info["focal_caption"] = ""
        info["focal_summary"] = ""
        if focal:
            cap = focal.with_suffix(".caption.md")
            sumf = focal.with_suffix(".summary.md")
            if cap.exists():
                info["focal_caption"] = cap.read_text().strip()
            if sumf.exists():
                info["focal_summary"] = sumf.read_text().strip()

        # Plain-language summary: README "In plain English" → context notes →
        # conclusions "Plain-language summary".
        plain = _section_from_md(readme_text, r"In plain English")
        if not plain or plain.startswith("*("):
            notes = p / "context" / "notes.md"
            if notes.exists():
                ntxt = notes.read_text()
                m = re.search(
                    r"##\s*Plain-language summary\s*\n(.+?)(?=^##|\Z)",
                    ntxt, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
                )
                if m:
                    body = m.group(1).strip()
                    if body and not body.startswith("_If you"):
                        plain = body
        if not plain or plain.startswith("*("):
            plain = _section_from_md(conc_text, r"Plain-language summary")
        info["plain_summary"] = plain.strip()

        # Headline finding.
        info["headline"] = ""
        findings = _section_from_md(conc_text, r"Findings")
        if findings:
            for line in findings.splitlines():
                line = line.strip()
                if line.startswith(("-", "*")):
                    info["headline"] = line.lstrip("-* ").strip()
                    break
        info["decision"] = _section_from_md(conc_text, r"Decision")
        out.append(info)
    return out


def _collect_curated_figures(root: Path) -> list[dict[str, Any]]:
    """Numbered figures in synthesis/figures/, with caption sidecars."""
    fig_dir = root / "synthesis" / "figures"
    if not fig_dir.exists():
        return []
    figures: list[dict[str, Any]] = []
    for f in sorted(fig_dir.iterdir()):
        if f.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
            continue
        cap_path = f.with_suffix(".caption.md")
        if not cap_path.exists():
            cap_path = f.parent / f"{f.stem}.caption.md"
        figures.append({
            "path": f,
            "name": f.stem,
            "caption": cap_path.read_text().strip() if cap_path.exists() else "",
        })
    return figures


def _verdict_class(status: str) -> str:
    s = (status or "").lower()
    return {
        "supported": "supported",
        "refuted": "refuted",
        "inconclusive": "inconclusive",
        "testing": "testing",
    }.get(s, "testing")


def _verdict_label(status: str) -> str:
    s = (status or "").lower()
    return {
        "supported": "SUPPORTED",
        "refuted": "REFUTED",
        "inconclusive": "INCONCLUSIVE",
        "testing": "IN PROGRESS",
    }.get(s, "IN PROGRESS")


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _figure_block(idx: int | str, fig: dict[str, Any] | None,
                  label: str = "", fallback_caption: str = "") -> str:
    """Render a single figure block. If figure is missing, render an
    inline note explaining how to add one (placeholder — not silently
    blank)."""
    if not fig:
        if not fallback_caption:
            return ""
        return (
            f"<div class='figure'><figcaption><span class='figlabel'>{_escape(label)}</span>"
            f"<span class='figcap-placeholder'>{_escape(fallback_caption)}</span>"
            "</figcaption></div>"
        )
    src = _b64_img(fig["path"]) or ""
    cap = fig.get("caption") or ""
    label = label or f"Figure {idx}"
    if cap:
        cap_html = _md_inline(cap)
    else:
        cap_html = (
            "<span class='figcap-placeholder'>"
            f"Caption missing for <code>{_escape(fig['path'].name)}</code> — "
            f"add <code>{_escape(fig['path'].stem)}.caption.md</code> "
            "next to the figure. Captions should lead with the substantive "
            "finding the figure shows.</span>"
        )
    return (
        f"<figure class='figure' id='figure-{idx}'>"
        f"<img src='{src}' alt='{_escape(label)}'>"
        f"<figcaption><span class='figlabel'>{_escape(label)}</span>{cap_html}</figcaption>"
        "</figure>"
    )


def _build_abstract(spec: dict[str, Any], state: dict[str, Any],
                    steps: list[dict[str, Any]], cfg: dict[str, Any]) -> str:
    """Spec-authored abstract first; else pull from final synthesis step."""
    if spec.get("abstract"):
        body = _md_inline(spec["abstract"])
    else:
        # Look for a "synthesis" / "cross_path" / "summary" / "audit" step's conclusions
        candidates = [s for s in steps if not s["is_dead_end"]
                      and any(k in s["id"].lower() for k in
                              ("synthesis", "summary", "audit", "validation"))]
        if not candidates:
            candidates = [s for s in steps if not s["is_dead_end"]]
        body = ""
        if candidates:
            txt = candidates[-1]["conclusions"]
            # Grab the first non-empty paragraph after the title.
            paras = [p.strip() for p in re.split(r"\n\s*\n", txt) if p.strip()]
            for p in paras:
                if p.startswith("#") or p.startswith("**Status"):
                    continue
                body = _md_inline(p)
                break
        if not body:
            goal = (cfg.get("research_goal") or {}).get("primary_question") or ""
            body = _md_inline(goal) if goal else (
                "<em>Add a short abstract via <code>synthesis/dashboard_spec.yaml</code> "
                "(key: <code>abstract</code>) or write a summary section in the "
                "project's final synthesis step.</em>"
            )
    return (
        "<section id='abstract'><h2>Abstract</h2>"
        "<div class='card abstract'><div class='label'>summary</div>"
        f"<p style='font-size: 1.04rem; margin-bottom: 0;'>{body}</p>"
        "</div></section>"
    )


def _build_overview(spec: dict[str, Any], cfg: dict[str, Any]) -> str:
    """Project context: what was studied, what questions, what was planned."""
    overview = spec.get("overview") or {}
    parts = ["<section id='overview'><h2>Research overview</h2>"]
    if overview.get("background"):
        parts.append(f"<h3>{_escape(overview.get('background_heading') or 'Background')}</h3>"
                     f"<p>{_md_inline(overview['background'])}</p>")
    elif cfg.get("research_goal", {}).get("background"):
        parts.append(f"<h3>Background</h3><p>{_md_inline(cfg['research_goal']['background'])}</p>")

    # Research questions
    rqs: list[dict[str, str]] = overview.get("research_questions") or []
    if not rqs:
        # Try to derive from researcher_config
        primary = (cfg.get("research_goal") or {}).get("primary_question")
        if primary:
            rqs = [{"id": "RQ1", "text": primary}]
    if rqs:
        parts.append("<h3>Research questions</h3><div class='card'>")
        for rq in rqs:
            parts.append(f"<p><strong>{_escape(rq.get('id', ''))}.</strong> "
                         f"{_md_inline(rq.get('text', ''))}</p>")
        parts.append("</div>")
    parts.append("</section>")
    return "".join(parts)


def _build_workflow(curated_figs: list[dict[str, Any]], steps: list[dict[str, Any]]) -> str:
    # Prefer a curated workflow figure (any of fig00_workflow_*, workflow_*, *workflow*)
    workflow_fig = None
    for f in curated_figs:
        nm = f["name"].lower()
        if "workflow" in nm or "pipeline" in nm or nm.startswith("fig00"):
            workflow_fig = f
            break
    parts = ["<section id='workflow'><h2>Workflow</h2>"]
    parts.append("<p>The analysis ran as a sequence of numbered steps, each producing "
                 "a self-contained artifact (data, figure, or report) that the next "
                 "step consumes. The diagram below shows how the steps connect.</p>")
    if workflow_fig:
        parts.append(_figure_block("workflow", workflow_fig, label="Analytical workflow"))
    else:
        # Inline list of step IDs as a textual fallback
        rows = []
        for i, s in enumerate(steps, start=1):
            status = "dead-end" if s["is_dead_end"] else "completed"
            rows.append(f"<tr><td>{i:02d}</td><td><code>{_escape(s['id'])}</code></td>"
                        f"<td>{status}</td></tr>")
        parts.append(
            "<table><thead><tr><th>#</th><th>Step</th><th>Status</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "<p class='muted'><em>Tip: add a <code>fig00_workflow_diagram.png</code> "
            "(plus <code>.caption.md</code>) to <code>synthesis/figures/</code> for a "
            "polished diagram. The <code>tool_workflow_dag</code> tool can render one.</em></p>"
        )
    parts.append("</section>")
    return "".join(parts)


def _build_verdicts(state: dict[str, Any], spec: dict[str, Any]) -> str:
    rows: list[str] = []
    hyps: list[dict[str, Any]] = state.get("active_hypotheses") or []
    spec_verdicts = spec.get("verdicts") or {}
    for h in hyps:
        hid = h.get("id", "")
        status = h.get("status", "testing")
        statement = h.get("statement", "")
        # Optional spec override: friendly name + summary
        sv = spec_verdicts.get(hid) or {}
        name = sv.get("name") or f"{hid} — {statement[:80] + ('…' if len(statement) > 80 else '')}"
        desc = sv.get("desc") or ""
        if not desc and h.get("evidence"):
            ev = h["evidence"][-1]
            note = ev.get("note", "")
            desc = (note[:160] + ("…" if len(note) > 160 else "")) if note else ""
        klass = _verdict_class(status)
        label = _verdict_label(status)
        rows.append(
            f"<div class='verdict-row'>"
            f"<div><div class='name'>{_escape(name)}</div>"
            f"<div class='desc'>{_md_inline(desc)}</div></div>"
            f"<span class='verdict {klass}'>{label}</span>"
            f"<span class='pill'>{_escape(hid)}</span>"
            "</div>"
        )
    if not rows:
        body = ("<p><em>No hypotheses recorded yet. Use "
                "<code>mem_hypothesis_add</code> at the start of each analytical "
                "step so the dashboard can render verdicts.</em></p>")
    else:
        body = f"<div class='verdicts'>{''.join(rows)}</div>"
    return (
        "<section id='verdicts'><h2>Verdicts at a glance</h2>"
        "<p>Each row is one hypothesis the project tracks. The verdict reflects "
        "the latest evidence logged against that hypothesis.</p>"
        f"{body}</section>"
    )


def _build_findings(spec: dict[str, Any], state: dict[str, Any],
                    steps: list[dict[str, Any]], curated_figs: list[dict[str, Any]]) -> str:
    """One section per hypothesis (or per spec-authored research question).

    Each section is rendered as a top-level ``<section>`` so it gets its own
    TOC entry. The first finding is preceded by a short Findings-section
    header card for navigation context.
    """
    spec_findings = spec.get("findings") or []
    parts: list[str] = []
    # Lead-in section that the TOC picks up as "Findings".
    parts.append(
        "<section id='findings'><h2>Findings</h2>"
        "<p>Each subsection below answers one of the research questions. "
        "Findings start with a plain-language framing, then the headline result, "
        "then the supporting figure, then the interpretation.</p></section>"
    )
    if spec_findings:
        for i, item in enumerate(spec_findings):
            parts.append(_render_finding_spec(item, curated_figs, i + 1))
        return "".join(parts)

    hyps = state.get("active_hypotheses") or []
    if not hyps:
        parts.append(
            "<section id='no-findings'><div class='card note'>"
            "<p><em>No hypotheses recorded yet. Use <code>mem_hypothesis_add</code> at "
            "the start of each analytical step so the dashboard can render findings, "
            "or author them directly in <code>synthesis/dashboard_spec.yaml</code> "
            "(key: <code>findings</code>).</em></p></div></section>"
        )
        return "".join(parts)
    for i, h in enumerate(hyps):
        parts.append(_render_finding_from_hypothesis(h, steps, curated_figs, i + 1))
    return "".join(parts)


def _render_finding_spec(item: dict[str, Any], curated_figs: list[dict[str, Any]], idx: int) -> str:
    name = item.get("name") or item.get("id", f"Finding {idx}")
    plain_english = item.get("plain_english")
    finding = item.get("finding")
    verdict = (item.get("verdict") or "").lower()
    klass = "ok" if verdict in {"supported", "refuted"} else "note"
    fig_name = item.get("figure")
    fig = next((f for f in curated_figs if f["name"] == fig_name or f["name"].startswith(fig_name or "____")), None) if fig_name else None
    how_to_read = item.get("how_to_read")
    detail = item.get("detail")

    parts = [f"<section id='finding-{idx}'><h2>{_escape(name)}</h2>"]
    if plain_english:
        parts.append(f"<blockquote><p><strong>In plain English.</strong> "
                     f"{_md_inline(plain_english)}</p></blockquote>")
    if finding:
        label_text = "Finding" + (f" — {verdict}" if verdict else "")
        parts.append(f"<div class='card {klass}'><div class='label'>{label_text}</div>"
                     f"<p style='margin: 0; font-size: 1.04rem;'>{_md_inline(finding)}</p></div>")
    if fig:
        parts.append(_figure_block(idx, fig, label=f"Figure {idx} — {name}"))
    if how_to_read:
        parts.append(f"<h3>How to read this figure</h3><p>{_md_inline(how_to_read)}</p>")
    if detail:
        parts.append(f"<details><summary>Numerical detail</summary>{_md_inline(detail)}</details>")
    parts.append("</section>")
    return "".join(parts)


def _render_finding_from_hypothesis(h: dict[str, Any], steps: list[dict[str, Any]],
                                    curated_figs: list[dict[str, Any]], idx: int) -> str:
    hid = h.get("id", f"H{idx}")
    status = h.get("status", "testing")
    statement = h.get("statement", "")
    ev_list = h.get("evidence") or []
    most_recent = ev_list[-1] if ev_list else {}
    note = most_recent.get("note", "")
    step_id = most_recent.get("step", "")
    klass = "ok" if status in {"supported", "refuted"} else "note"

    # Find a curated figure for this hypothesis
    fig = None
    for f in curated_figs:
        nm = f["name"].lower()
        if hid.lower() in nm or hid.lower().replace("0", "") in nm:
            fig = f
            break
    # Fall back to the focal figure of the step that logged the most recent evidence
    if not fig and step_id:
        match = next((s for s in steps if s["id"] == step_id), None)
        if match and match.get("focal_figure"):
            fig = {"path": match["focal_figure"], "name": match["focal_figure"].stem, "caption": ""}

    parts = [f"<section id='finding-{idx}'>"
             f"<h2>{_escape(hid)} — {_escape(statement[:120])}</h2>"]
    parts.append(f"<div class='card {klass}'>"
                 f"<div class='label'>Latest evidence — {status}</div>"
                 f"<p style='margin: 0;'>{_md_inline(note)}</p></div>")
    if fig:
        parts.append(_figure_block(idx, fig, label=f"Figure {idx} — {hid}"))
    if step_id:
        parts.append(f"<p class='muted'><small>Most recent evidence logged from step "
                     f"<code>{_escape(step_id)}</code>.</small></p>")
    parts.append("</section>")
    return "".join(parts)


def _build_limitations(spec: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """Spec-authored takes precedence; else pull aggregated 'Limitations' sections."""
    parts = ["<section id='limitations'><h2>Limitations</h2><div class='card'>"]
    if spec.get("limitations"):
        items = spec["limitations"] if isinstance(spec["limitations"], list) else [spec["limitations"]]
        parts.append("<ul>")
        for item in items:
            parts.append(f"<li>{_md_inline(item)}</li>")
        parts.append("</ul>")
    else:
        bullets: list[str] = []
        for s in steps:
            lim = _section_from_md(s["conclusions"], r"Limitations?")
            if lim:
                for line in lim.splitlines():
                    line = line.strip()
                    if line.startswith("-") or line.startswith("*"):
                        bullets.append(line.lstrip("-* ").strip())
        if bullets:
            parts.append("<ul>")
            # Dedupe while preserving order, cap at 12 to keep the section scannable
            seen: set[str] = set()
            for b in bullets:
                key = b.lower()[:80]
                if key in seen:
                    continue
                seen.add(key)
                parts.append(f"<li>{_md_inline(b)}</li>")
                if len(seen) >= 12:
                    break
            parts.append("</ul>")
        else:
            parts.append("<p><em>Add limitations via <code>synthesis/dashboard_spec.yaml</code> "
                         "(key: <code>limitations</code>) or under <code>## Limitations</code> "
                         "in each step's <code>conclusions.md</code>.</em></p>")
    parts.append("</div></section>")
    return "".join(parts)


def _build_methodological(spec: dict[str, Any]) -> str:
    """Optional 'methodological considerations' section. Supportive tone."""
    items = spec.get("methodological_considerations") or []
    if not items:
        return ""
    parts = ["<section id='methodological'><h2>Methodological considerations</h2>"]
    for item in items:
        klass = item.get("priority", "note")  # "high" → flag, "medium" → note
        if klass == "high":
            klass = "flag"
        elif klass not in {"flag", "note", "ok"}:
            klass = "note"
        heading = item.get("name", "Consideration")
        body = item.get("body", "")
        parts.append(
            f"<div class='card {klass}'><div class='label'>{_escape(item.get('priority_label', 'consideration'))}</div>"
            f"<h4 style='margin-top: 0;'>{_escape(heading)}</h4>"
            f"<p style='margin-bottom: 0;'>{_md_inline(body)}</p></div>"
        )
    parts.append("</section>")
    return "".join(parts)


def _build_open_questions(spec: dict[str, Any]) -> str:
    items = spec.get("open_questions") or []
    if not items:
        return ""
    parts = ["<section id='open-questions'><h2>Open questions</h2>",
             "<p>Questions that emerged during the analysis and would benefit "
             "from clarification or follow-up.</p>"]
    for item in items:
        prio = item.get("priority", "")
        klass = "flag" if prio == "high" else "note" if prio == "medium" else ""
        parts.append(
            f"<div class='card {klass}'>"
            + (f"<div class='label'>priority: {_escape(prio)}</div>" if prio else "")
            + f"<h4 style='margin-top: 0;'>{_escape(item.get('title', ''))}</h4>"
            f"<p style='margin-bottom: 0;'>{_md_inline(item.get('body', ''))}</p></div>"
        )
    parts.append("</section>")
    return "".join(parts)


def _build_glossary() -> str:
    parts = ["<section id='glossary'><h2>Statistical glossary</h2>",
             "<p>Plain-language explanations of every statistical concept used "
             "in this dashboard. Click 🔍 to open a search for deeper reading.</p>",
             "<div class='glossary'>"]
    for t in GLOSSARY:
        search = (f"<a href='https://www.google.com/search?q={t['search'].replace(' ', '+')}' "
                  "target='_blank' rel='noopener'>🔍 Search</a>")
        wiki = (f"<a href='https://en.wikipedia.org/wiki/{t['wiki']}' "
                "target='_blank' rel='noopener'>Wikipedia</a>" if t.get("wiki") else "")
        parts.append(
            f"<div class='term'><h4>{_escape(t['name'])}</h4>"
            f"<p>{t['body']}</p>"
            f"<div class='lookup'>{search}{wiki}</div></div>"
        )
    parts.append("</div></section>")
    return "".join(parts)


def _build_traceability_matrix(
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> str:
    """Table that maps each hypothesis to the step(s) and figure(s) that
    actually informed its verdict. Lets a reviewer audit the evidence chain
    without trawling per-step folders.
    """
    hyps = state.get("active_hypotheses") or []
    if not hyps:
        return ""
    # step → set of figure file names (for compact display)
    step_to_figures: dict[str, list[str]] = {}
    for s in steps:
        if s.get("focal_figure"):
            step_to_figures.setdefault(s["id"], []).append(
                s["focal_figure"].name
            )

    rows: list[str] = []
    for h in hyps:
        hid = h.get("id", "?")
        status = (h.get("status") or "testing").lower()
        klass = _verdict_class(status)
        label = _verdict_label(status)
        statement = (h.get("statement") or "")[:140]
        steps_touched: list[str] = []
        for ev in (h.get("evidence") or []):
            sid = ev.get("step")
            if sid and sid not in steps_touched:
                steps_touched.append(sid)
        if not steps_touched:
            steps_link = "<em>(no logged evidence yet)</em>"
            figs_link = "&mdash;"
        else:
            steps_link = ", ".join(f"<code>{_escape(s)}</code>" for s in steps_touched)
            figs: list[str] = []
            for s in steps_touched:
                figs.extend(step_to_figures.get(s, []))
            figs_link = (
                ", ".join(f"<code>{_escape(f)}</code>" for f in figs[:4])
                if figs else "&mdash;"
            )
        rows.append(
            "<tr>"
            f"<td><span class='pill'>{_escape(hid)}</span></td>"
            f"<td>{_md_inline(statement)}</td>"
            f"<td><span class='verdict {klass}' style='padding: 0.18rem 0.5rem;'>"
            f"{label}</span></td>"
            f"<td>{steps_link}</td>"
            f"<td>{figs_link}</td>"
            "</tr>"
        )
    return (
        "<section id='traceability'><h2>Evidence traceability</h2>"
        "<p>Which steps and figures inform each hypothesis verdict — "
        "the audit chain a reviewer can walk in either direction.</p>"
        "<table><thead><tr>"
        "<th>Hypothesis</th><th>Statement</th><th>Verdict</th>"
        "<th>Steps</th><th>Focal figures</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _build_audit_summary(root: Path) -> str:
    """Surface the latest step-completeness audit so reviewers see what's
    outstanding without leaving the dashboard."""
    report = root / "workspace" / "logs" / "step_completeness.md"
    if not report.exists():
        return ""
    txt = report.read_text()
    # Trim very long reports for the dashboard.
    if len(txt) > 6000:
        txt = txt[:6000] + "\n\n… (truncated; see workspace/logs/step_completeness.md)"
    return (
        "<section id='audit'><h2>Outstanding artefacts</h2>"
        "<p>Server-side completeness audit. Anything listed under a "
        "<strong>BLOCKERS</strong> heading must be resolved before the "
        "final deliverable.</p>"
        "<div class='card'><pre style='white-space: pre-wrap; font-size: "
        "0.85rem;'>"
        + _escape(txt) +
        "</pre></div></section>"
    )


def _build_references(root: Path, spec: dict[str, Any]) -> str:
    parts = ["<section id='refs'><h2>References</h2><div class='card'>"]
    spec_refs = spec.get("references") or []
    if spec_refs:
        for group in spec_refs:
            if isinstance(group, dict):
                title = group.get("heading")
                items = group.get("items") or []
                if title:
                    parts.append(f"<h4 style='margin-top: 0;'>{_escape(title)}</h4>")
                parts.append("<ul>")
                for it in items:
                    parts.append(f"<li>{_md_inline(it)}</li>")
                parts.append("</ul>")
            else:
                parts.append(f"<p>{_md_inline(str(group))}</p>")
    else:
        cit_path = root / "workspace" / "citations.md"
        text = cit_path.read_text() if cit_path.exists() else ""
        if text and "No literature yet" not in text and "(No literature" not in text:
            parts.append(f"<pre>{_escape(text[:8000])}</pre>")
        else:
            parts.append(
                "<p><em>No references recorded. Drop PDFs in "
                "<code>inputs/literature/</code> or call <code>tool_literature_search_and_save</code> "
                "to populate this section, or author them directly in "
                "<code>synthesis/dashboard_spec.yaml</code> (key: <code>references</code>).</em></p>"
            )
    parts.append("</div></section>")
    return "".join(parts)


def _build_per_step_appendix(
    steps: list[dict[str, Any]],
    curated_figs: list[dict[str, Any]],
) -> str:
    """Per-step appendix: collapsible cards with plain-English summary,
    headline finding, focal figure (with both technical caption and
    plain-English summary), full conclusions excerpt, and decision."""
    if not steps:
        return ""
    parts = [
        "<section id='per-step'><h2>Per-step appendix</h2>",
        "<p>One entry per analytical step. Each card opens to a "
        "plain-English summary, the headline finding, the focal figure, "
        "and the full conclusions text. The decision (proceed / branch / "
        "dead-end) sits at the bottom so the reasoning chain is "
        "auditable end-to-end.</p>",
    ]
    for i, s in enumerate(steps):
        title = s["id"]
        if s["is_dead_end"]:
            title += "  ⚑ dead-end (preserved)"

        open_attr = " open" if i < 2 else ""
        parts.append(f"<details{open_attr}><summary>{_escape(title)}</summary>")

        # In-plain-English summary card.
        if s.get("plain_summary"):
            parts.append(
                "<div class='card ok'><div class='label'>In plain English</div>"
                f"<p style='margin: 0;'>{_md_inline(s['plain_summary'])}</p></div>"
            )

        # Headline finding card.
        if s.get("headline"):
            parts.append(
                "<div class='card abstract'><div class='label'>Headline finding</div>"
                f"<p style='margin: 0; font-size: 1.02rem;'>"
                f"{_md_inline(s['headline'])}</p></div>"
            )

        # Focal figure with BOTH captions.
        if s.get("focal_figure"):
            focal = {
                "path": s["focal_figure"],
                "name": s["focal_figure"].stem,
                "caption": s.get("focal_caption", ""),
            }
            parts.append(_figure_block(
                s["id"], focal, label=f"Focal figure — {s['id']}",
            ))
            if s.get("focal_summary"):
                parts.append(
                    "<div class='card note' style='margin-top: -0.6rem;'>"
                    "<div class='label'>Plain-language description</div>"
                    f"<div>{_md_inline(s['focal_summary'])}</div></div>"
                )

        # Full conclusions — folded by default but scannable.
        body = re.sub(r"^#\s+[^\n]+\n+", "", s["conclusions"])
        snippet = body[:6000] + ("\n\n… (truncated; see workspace/" + s["id"]
                                 + "/conclusions.md)" if len(body) > 6000 else "")
        if snippet.strip():
            parts.append("<h4>Full conclusions</h4>")
            parts.append(
                "<pre style='white-space: pre-wrap; font-size: 0.85rem; "
                "background: var(--soft-bg); padding: 0.9rem; "
                "border-radius: 4px;'>"
                f"{_escape(snippet)}</pre>"
            )

        # Decision footer.
        if s.get("decision"):
            parts.append(
                "<div class='card'><div class='label'>Decision</div>"
                f"<p style='margin: 0;'>{_md_inline(s['decision'])}</p></div>"
            )

        parts.append("</details>")
    parts.append("</section>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_dashboard(root: Path, title: str | None = None,
                     audience: str = "academic",
                     suppress_audit_panel: bool = False) -> dict[str, Any]:
    """Generate the polished research-summary dashboard.

    When ``suppress_audit_panel`` is true (researcher-authorised
    override), the step-completeness audit section is dropped from the
    rendered HTML. The override is still logged at the handler layer.
    """
    try:
        state = _load_state(root)
        cfg = _load_config(root)
        spec = _load_spec(root)
        steps = _collect_steps(root)
        curated_figs = _collect_curated_figures(root)

        project_title = (
            title
            or spec.get("title")
            or state.get("project_name")
            or cfg.get("project_name")
            or "Research project"
        )
        subtitle = (
            spec.get("subtitle")
            or (cfg.get("research_goal") or {}).get("primary_question")
            or ""
        )
        eyebrow = spec.get("eyebrow") or "Research dashboard"
        meta_items = spec.get("meta") or []
        if not meta_items:
            # Sensible defaults from config
            owner = (cfg.get("researcher") or {}).get("name")
            if owner:
                meta_items.append({"label": "Researcher", "value": owner})
            meta_items.append({"label": "Format", "value": "Self-contained dashboard; figures embedded"})

        from research_os.project_ops import ensure_lazy_dir
        synthesis_dir = ensure_lazy_dir(root, "synthesis")
        out_path = synthesis_dir / "dashboard.html"

        # Audience profiles change the section ordering + which sections to
        # include. Defaults below collapse to the same ordering as before
        # for the 'academic' audience.
        audience_sections: dict[str, list[str]] = {
            "academic": [
                "abstract", "overview", "workflow", "verdicts", "findings",
                "traceability", "methodological", "open_questions",
                "limitations", "per_step", "audit", "glossary", "references",
            ],
            "executive": [
                # Headline first; everything else collapsed/optional.
                "abstract", "verdicts", "findings", "limitations",
                "audit", "references",
            ],
            "technical": [
                "abstract", "overview", "workflow", "verdicts", "findings",
                "traceability", "methodological", "per_step", "audit",
                "limitations", "open_questions", "glossary", "references",
            ],
            "teaching": [
                # Lead with plain-English; defer jargon.
                "abstract", "overview", "findings", "workflow", "verdicts",
                "glossary", "per_step", "references",
            ],
        }
        order = audience_sections.get(audience, audience_sections["academic"])
        if spec.get("hide_per_step_appendix") and "per_step" in order:
            order = [s for s in order if s != "per_step"]
        if not (root / "workspace" / "logs" / "step_completeness.md").exists():
            order = [s for s in order if s != "audit"]
        if suppress_audit_panel:
            order = [s for s in order if s != "audit"]

        section_builders = {
            "abstract":      lambda: _build_abstract(spec, state, steps, cfg),
            "overview":      lambda: _build_overview(spec, cfg),
            "workflow":      lambda: _build_workflow(curated_figs, steps),
            "verdicts":      lambda: _build_verdicts(state, spec),
            "findings":      lambda: _build_findings(spec, state, steps, curated_figs),
            "traceability":  lambda: _build_traceability_matrix(state, steps),
            "methodological":lambda: _build_methodological(spec),
            "open_questions":lambda: _build_open_questions(spec),
            "limitations":   lambda: _build_limitations(spec, steps),
            "per_step":      lambda: _build_per_step_appendix(steps, curated_figs),
            "audit":         lambda: _build_audit_summary(root),
            "glossary":      lambda: _build_glossary(),
            "references":    lambda: _build_references(root, spec),
        }
        sections_html = [section_builders[name]() for name in order]

        toc = _build_toc(sections_html, spec)

        meta_dl = "".join(
            f"<dt>{_escape(m['label'])}</dt><dd>{_md_inline(m['value'])}</dd>"
            for m in meta_items
        )

        header_html = (
            "<header class='frontpage'>"
            f"<div class='eyebrow'>{_escape(eyebrow)}</div>"
            f"<h1>{_escape(project_title)}</h1>"
            + (f"<div class='subtitle'>{_md_inline(subtitle)}</div>" if subtitle else "")
            + (f"<dl class='meta'>{meta_dl}</dl>" if meta_dl else "")
            + "<div class='actions'>"
            "<button onclick=\"document.querySelectorAll('details').forEach(d=>d.open=true)\">📖 Expand all</button>"
            "<button class='secondary' onclick=\"document.querySelectorAll('details').forEach(d=>d.open=false)\">📕 Collapse</button>"
            "<button class='secondary' onclick='toggleTheme()'>🌓 Toggle theme</button>"
            "<button class='secondary' onclick='window.print()'>🖨️ Print / PDF</button>"
            "</div></header>"
        )

        body = "".join([
            "<!doctype html>\n<html lang='en'><head>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
            f"<title>{_escape(project_title)}</title>",
            f"<style>{DASHBOARD_CSS}</style>",
            "</head><body><div class='layout'>",
            toc,
            "<main>",
            header_html,
            *[s for s in sections_html if s],
            f"<footer>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
            f"Audience: {_escape(audience)} · Research OS</footer>",
            "</main></div>",
            "<div id='lightbox' onclick=\"this.classList.remove('open')\"><img id='lightbox-img' src='' alt=''></div>",
            f"<script>{DASHBOARD_JS}</script>",
            "</body></html>",
        ])

        out_path.write_text(body)
        return {
            "status": "success",
            "dashboard_path": str(out_path.relative_to(root)),
            "size_kb": round(out_path.stat().st_size / 1024, 1),
            "figures_embedded": sum(1 for f in curated_figs if f["path"].exists()),
            "steps": len(steps),
            "hypotheses": len(state.get("active_hypotheses") or []),
            "uses_spec": bool(spec),
        }
    except Exception as e:
        logger.exception("render_dashboard failed")
        return {"status": "error", "message": str(e)}


def curate_figures(root: Path) -> dict[str, Any]:
    """Collect, number, and copy each step's focal figure into
    ``synthesis/figures/`` with stable naming for the dashboard + paper.

    Behaviour:
      * Walk ``workspace/NN_*/outputs/figures/`` in step order.
      * Pick each step's focal figure (heuristic: file starting with the
        step number, else alphabetically first PNG/SVG/JPG).
      * Copy to ``synthesis/figures/figNN_<step-descriptor>.png`` so the
        ordering is deterministic and stable across rebuilds.
      * Copy the figure's existing ``.caption.md`` sidecar if present, OR
        seed a placeholder caption noting that an interpretive caption
        is required.
      * Skip steps with no figures (returns them in ``missing_figures``
        so the audit can flag them).
    """
    ws = root / "workspace"
    target = root / "synthesis" / "figures"
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    missing_captions: list[str] = []
    missing_figures: list[str] = []

    if not ws.exists():
        return {
            "status": "error",
            "message": "workspace/ not found; nothing to curate.",
        }

    fig_no = 1
    for p in sorted(ws.iterdir()):
        if not (p.is_dir() and re.match(r"^\d{2,3}_", p.name)):
            continue
        if p.name.endswith("__DEAD_END"):
            continue
        figs_dir = p / "outputs" / "figures"
        if not figs_dir.exists():
            missing_figures.append(p.name)
            continue
        # Prefer a focal figure whose name starts with the step number.
        candidates = [
            f for f in sorted(figs_dir.iterdir())
            if f.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
            and f.is_file()
        ]
        if not candidates:
            missing_figures.append(p.name)
            continue
        step_num = p.name.split("_", 1)[0]
        focal = next((f for f in candidates if f.name.startswith(step_num + "_")), candidates[0])

        # Descriptor: take the step name (everything after NN_).
        slug = re.sub(r"^\d{2,3}_", "", p.name)
        dest_name = f"fig{fig_no:02d}_{slug}{focal.suffix.lower()}"
        dest = target / dest_name
        try:
            if not dest.exists() or dest.stat().st_mtime < focal.stat().st_mtime:
                import shutil as _shutil
                _shutil.copy2(focal, dest)
        except Exception as e:
            logger.warning("curate copy failed %s: %s", focal, e)
            continue

        # Caption sidecar: copy or seed placeholder.
        focal_cap = focal.with_suffix(".caption.md")
        if not focal_cap.exists():
            focal_cap = focal.parent / f"{focal.stem}.caption.md"
        dest_cap = dest.with_suffix(".caption.md")
        if focal_cap.exists():
            try:
                import shutil as _shutil
                if not dest_cap.exists() or dest_cap.stat().st_mtime < focal_cap.stat().st_mtime:
                    _shutil.copy2(focal_cap, dest_cap)
            except Exception:
                pass
        else:
            missing_captions.append(p.name)
            if not dest_cap.exists():
                dest_cap.write_text(
                    f"**Figure {fig_no} — {slug.replace('_', ' ')}.** "
                    "_Caption pending. Lead with the substantive finding the "
                    "figure shows (not just 'histogram of X'); name the unit "
                    "on each axis; call out one specific feature the reader "
                    "should look for._\n"
                )

        copied.append({
            "source": str(focal.relative_to(root)),
            "dest": str(dest.relative_to(root)),
            "step": p.name,
            "has_caption": focal_cap.exists(),
        })
        fig_no += 1

    return {
        "status": "success",
        "curated": len(copied),
        "missing_captions": missing_captions,
        "missing_figures": missing_figures,
        "figures": copied,
        "synthesis_figures_dir": str(target.relative_to(root)),
    }


def _build_toc(sections_html: list[str], spec: dict[str, Any]) -> str:
    """Build the sticky-sidebar TOC by scanning rendered sections for ids+h2."""
    items: list[tuple[str, str]] = []
    pat = re.compile(r"<section id='([^']+)'><h2>([^<]+)</h2>")
    for s in sections_html:
        if not s:
            continue
        for sid, label in pat.findall(s):
            items.append((sid, label))
    brand_title = spec.get("brand_title", "Research dashboard")
    brand_subtitle = spec.get("brand_subtitle", "")
    links = "".join(f"<li><a href='#{_escape(sid)}'>{_escape(lbl)}</a></li>"
                    for sid, lbl in items)
    return (
        "<aside class='toc'>"
        f"<div class='brand'><div class='title'>{_escape(brand_title)}</div>"
        + (f"<div class='subtitle'>{_escape(brand_subtitle)}</div>" if brand_subtitle else "")
        + "</div>"
        f"<h5>Contents</h5><ul>{links}</ul></aside>"
    )
