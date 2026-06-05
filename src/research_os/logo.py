"""Research OS brand banner.

A single source of truth for the ASCII logo and tagline rendered at the
top of ``research-os init``. The "hexagon pipeline" mark evokes a chain
of analytical steps — input → process → output — and reads well in any
monospace terminal that supports basic Unicode.

The same mark is mirrored in ``assets/logo.txt`` (for embedding in
external docs) and ``assets/logo.svg`` (for the README badge).
"""

from __future__ import annotations

# Lazy ANSI — avoids importing wizard here (circular).
import os
import sys

# Hexagon pipeline glyphs render in any modern terminal (Unicode 6.0+).
# Width is 38 columns including the two-space left gutter; chosen so it
# centres comfortably inside a 68-column wizard banner.
_LOGO = r"""
   ⬢───⬢───⬢
   │   │   │
   ⬡───⬡───⬡
"""

_WORDMARK = "R E S E A R C H   O S"
_TAGLINE = "grounded · cited · auditable"


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def render(width: int = 68, version: str | None = None) -> str:
    """Return the multi-line banner, framed and ready to print.

    ``width`` is the inside width of the box. ``version`` is appended
    after the wordmark on the same visual line (e.g. ``v1.0``).
    """
    cyan = lambda s: _c("36", s)          # noqa: E731
    bold = lambda s: _c("1", s)           # noqa: E731
    dim  = lambda s: _c("2", s)           # noqa: E731
    grey = lambda s: _c("90", s)          # noqa: E731

    inner = max(48, width - 2)
    border_top = cyan("╭" + "─" * inner + "╮")
    border_bot = cyan("╰" + "─" * inner + "╯")
    side       = cyan("│")
    empty      = f"  {side}{' ' * inner}{side}"

    # Compose the inside lines. We hand-build each row so the colors do
    # not throw off the visible-width calculation (raw glyphs only).
    wordmark = bold(_WORDMARK) + (f"   {dim('v' + version)}" if version else "")
    wordmark_raw = _WORDMARK + (f"   v{version}" if version else "")
    tagline = grey(_TAGLINE)

    def _row(left_raw: str, right_raw: str, left: str, right: str) -> str:
        gap = inner - 3 - len(left_raw) - 3 - len(right_raw)
        gap = max(2, gap)
        return f"  {side}   {left}{' ' * gap}{right}   {side}"

    rows = [
        border_top,
        empty,
        _row("⬢───⬢───⬢", wordmark_raw, cyan("⬢───⬢───⬢"), wordmark),
        _row("│   │   │", "", cyan("│   │   │"), ""),
        _row("⬡───⬡───⬡", tagline.replace("\033[90m", "").replace("\033[0m", ""),
             cyan("⬡───⬡───⬡"), tagline),
        empty,
        border_bot,
    ]
    return "\n".join(rows)


def render_compact() -> str:
    """One-line minimalist mark, for nested or already-banner'd contexts."""
    cyan = lambda s: _c("36", s)          # noqa: E731
    bold = lambda s: _c("1", s)           # noqa: E731
    return f"  {cyan('⬢─⬢─⬢')}  {bold('Research OS')}"


if __name__ == "__main__":  # pragma: no cover
    from research_os import __version__
    print(render(version=__version__))
    print()
    print(render_compact())
