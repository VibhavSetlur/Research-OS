"""Optional-dependency inventory + lazy imports.

`_lazy_import` returns either a real module attribute or a `_MissingDependency`
placeholder that raises a friendly RuntimeError when called. Failed imports are
collected in `_MISSING_DEPS` so the AI can ask once for the full inventory
(via sys_dep_inventory) instead of finding out tool-by-tool.
"""
from __future__ import annotations


class _MissingDependency:
    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, *args, **kwargs):
        raise RuntimeError(
            f"Optional dependency missing for {self.name}. "
            "Install with: pip install research-os"
        )


# Tracks (module, attribute) pairs that failed to import so the AI can ask
# for a real status read instead of finding out tool-by-tool.
_MISSING_DEPS: list[tuple[str, str]] = []


def _lazy_import(module_name: str, names: list[str]):
    try:
        mod = __import__(module_name, fromlist=names)
        return [getattr(mod, name) for name in names]
    except ImportError:
        for n in names:
            _MISSING_DEPS.append((module_name, n))
        return [_MissingDependency(name) for name in names]


def _optional_dep_inventory() -> dict:
    """Return a structured report of what's installed vs missing."""
    return {
        "missing": [
            {"module": m, "symbol": n} for (m, n) in _MISSING_DEPS
        ],
        "missing_count": len(_MISSING_DEPS),
        "advice": (
            "Install with: pip install research-os "
            "(omits R / Julia / Docker bindings — install those separately)."
            if _MISSING_DEPS
            else "All optional dependencies present."
        ),
    }
