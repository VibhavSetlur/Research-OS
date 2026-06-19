"""Shared design-token + colour-science module — the single source of truth
for the Research-OS visual identity, consumed by BOTH the deliverable chrome
(dashboard / poster / slide scaffolds) AND the design audits.

Before 3.2.8 the palette lived in three drifting places: ``viz/style.py``
(figures), the embedded ``_DASHBOARD_HTML`` CSS (chrome), and
``audit/dashboard_content.py`` (an allow-list that *punished* any custom
palette). This module centralises:

* ``PALETTES`` — three professional, selectable palette systems (RO house,
  Okabe-Ito categorical, cool clinical). The AI picks ONE per deliverable;
  all are AA-contrast on their own ground, CVD-distinguishable, and survive
  greyscale. They are OPTIONS, not a mandate — the audit judges a custom
  palette on *quality* (restraint / contrast / no-neon), not on membership.
* ``SEQUENTIAL`` / ``DIVERGING`` anchor sets + ``BANNED_COLORMAPS`` for
  quantitative encodings.
* colour-science predicates (``hex_to_hsv``, ``is_neon``, ``is_near_neutral``,
  ``relative_luminance``, ``contrast_ratio``) so chrome and audit share ONE
  implementation of "is this professional?".

Nothing here imports matplotlib — it is pure data + stdlib, safe to import
from handlers, audits, and the scaffold.
"""

from __future__ import annotations

import colorsys
import re

# ---------------------------------------------------------------------------
# Selectable palette systems (the AI picks ONE per deliverable).
# Each carries a light + dark token set so a deliverable honours
# prefers-color-scheme with the SAME semantic mapping.
# ---------------------------------------------------------------------------

PALETTES: dict[str, dict] = {
    # Option A — RO house (warm editorial). Default; matches
    # viz/style.py apply_research_os_style() so embedded figures cohere.
    "ro_house": {
        "label": "RO house (warm editorial)",
        "when": "default; cohesion with apply_research_os_style figures",
        "light": {
            "ground": "#FBF8F3", "card": "#FFFDF8", "fg": "#3D3A35",
            "muted": "#6E665A", "rule": "#D6CFC2",
            "primary": "#1F4D7A", "secondary": "#9B7E2D",
            "positive": "#3F6049", "negative": "#9B3737", "fifth": "#C3A14E",
        },
        "dark": {
            "ground": "#1C1A17", "card": "#24221E", "fg": "#E8E3D8",
            "muted": "#A89E8E", "rule": "#3A372F",
            "primary": "#7FA8D4", "secondary": "#C3A14E",
            "positive": "#6FA07C", "negative": "#C97A7A", "fifth": "#C3A14E",
        },
        # Categorical chart hues (CVD-safe), in priority order.
        "categorical": ["#1F4D7A", "#9B7E2D", "#3F6049", "#9B3737", "#C3A14E"],
    },
    # Option B — Okabe-Ito categorical on a neutral ground. Maximum CVD
    # safety; use 3-4 of the 8, not all of them.
    "okabe_ito": {
        "label": "Okabe-Ito categorical (max CVD safety)",
        "when": "many categories; colour-blind-critical audiences",
        "light": {
            "ground": "#FFFFFF", "card": "#FAFAFA", "fg": "#1A1A1A",
            "muted": "#595959", "rule": "#E0E0E0",
            "primary": "#0072B2", "secondary": "#E69F00",
            "positive": "#009E73", "negative": "#D55E00", "fifth": "#CC79A7",
        },
        "dark": {
            "ground": "#15171A", "card": "#1E2125", "fg": "#ECECEC",
            "muted": "#A0A0A0", "rule": "#33363B",
            "primary": "#56B4E9", "secondary": "#E69F00",
            "positive": "#009E73", "negative": "#D55E00", "fifth": "#CC79A7",
        },
        "categorical": ["#E69F00", "#56B4E9", "#009E73", "#F0E442",
                        "#0072B2", "#D55E00", "#CC79A7", "#000000"],
    },
    # Option C — cool institutional / clinical. Formal venues / med journals.
    "clinical": {
        "label": "Cool institutional / clinical",
        "when": "formal venue; clinical / policy audience",
        "light": {
            "ground": "#F7F8FA", "card": "#FFFFFF", "fg": "#1F2933",
            "muted": "#52606D", "rule": "#E1E5EA",
            "primary": "#2B5F8C", "secondary": "#2A7F7B",
            "positive": "#2E7D5B", "negative": "#B3401F", "fifth": "#7B6CA8",
        },
        "dark": {
            "ground": "#11161C", "card": "#1A2129", "fg": "#E4E9EF",
            "muted": "#9AA6B2", "rule": "#2A333D",
            "primary": "#6FA8D4", "secondary": "#5BC0BA",
            "positive": "#6FBF93", "negative": "#D88A6E", "fifth": "#A99BD0",
        },
        "categorical": ["#2B5F8C", "#2A7F7B", "#B3401F", "#7B6CA8", "#52606D"],
    },
}

DEFAULT_PALETTE = "ro_house"

# Sequential + diverging anchors for quantitative encodings.
SEQUENTIAL = {
    "viridis": ["#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725"],
}
DIVERGING = {
    "puor": ["#B35806", "#E08214", "#FDB863", "#FEE0B6",
             "#D8DAEB", "#B2ABD2", "#8073AC", "#542788"],
    "rdbu": ["#B2182B", "#EF8A62", "#FDDBC7", "#D1E5F0", "#67A9CF", "#2166AC"],
}

# Never acceptable for a quantitative encoding (non-monotonic luminance →
# misleads + fails CVD). Matched case-insensitively against plotting source.
BANNED_COLORMAPS = frozenset({
    "jet", "turbo", "rainbow", "gist_rainbow", "hsv", "nipy_spectral",
    "prism", "flag",
})


# ---------------------------------------------------------------------------
# Colour-science helpers (one implementation, shared by chrome + audit).
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})\b")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Return (h, s, v) in 0..1 for a #rrggbb string."""
    r, g, b = _rgb(hex_color)
    return colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)


def is_near_neutral(hex_color: str, tol: int = 12) -> bool:
    """True for greys / near-greys (chrome text/rules) — excluded from the
    chart-colour palette judgement."""
    try:
        r, g, b = _rgb(hex_color)
    except (ValueError, IndexError):
        return False
    return max(r, g, b) - min(r, g, b) <= tol


def is_neon(hex_color: str) -> bool:
    """True for electric / fluorescent colours that read as amateur on a
    research deliverable (e.g. #00FF00, #FF00FF). Thresholds are deliberately
    strict so professional-but-saturated palette colours — Okabe-Ito amber
    #E69F00 (V≈0.90), vermillion #D55E00 — are NOT flagged. Near-neutrals are
    never neon."""
    if is_near_neutral(hex_color):
        return False
    _, s, v = hex_to_hsv(hex_color)
    return s > 0.9 and v > 0.92


def relative_luminance(hex_color: str) -> float:
    def chan(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    lf = relative_luminance(fg_hex)
    lb = relative_luminance(bg_hex)
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def palette_hexes(name: str | None = None) -> set[str]:
    """Lowercase hexes belonging to a named palette (light+dark+categorical),
    or to ALL palettes when name is None. Used by the audit to judge whether a
    chart colour belongs to the *declared* palette (quality, not a mandate)."""
    out: set[str] = set()
    names = [name] if name and name in PALETTES else list(PALETTES)
    for n in names:
        p = PALETTES[n]
        for scheme in ("light", "dark"):
            out |= {v.lower() for v in p[scheme].values() if isinstance(v, str) and v.startswith("#")}
        out |= {c.lower() for c in p.get("categorical", [])}
    return out


def all_allowed_chart_hexes() -> set[str]:
    """Union of every professional palette + sequential/diverging anchors.
    A chart colour outside this set (and not near-neutral) is 'off-palette'."""
    out = palette_hexes(None)
    for ramp in SEQUENTIAL.values():
        out |= {c.lower() for c in ramp}
    for ramp in DIVERGING.values():
        out |= {c.lower() for c in ramp}
    return out


def extract_hexes(text: str) -> list[str]:
    """Every #rrggbb in a blob (CSS, inline style, SVG), lowercased."""
    return [("#" + m.group(1)).lower() for m in _HEX_RE.finditer(text)]
