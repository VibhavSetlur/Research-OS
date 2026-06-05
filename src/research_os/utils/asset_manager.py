"""Access packaged Research OS assets with optional local overrides.

The installed package owns immutable prompts, skills, schemas, workflows, and
domain registries under ``research_os.assets``. A project may override a
single asset by creating the same relative path under ``.os_state/assets/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Optional


ASSET_PACKAGE = "research_os.assets"
ASSET_ROOTS = {"agents", "skills", "schemas", "workflows", "domains"}


@dataclass(frozen=True)
class AssetRef:
    """A resolved asset entry."""

    relative_path: str
    source: str
    local_path: Optional[Path] = None


class AssetManager:
    """Resolve bundled assets and project-local overrides."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (
            Path(project_root) if project_root else self.find_project_root()
        )
        self.override_root = self.project_root / ".os_state" / "assets"

    @staticmethod
    def find_project_root(start: Optional[Path] = None) -> Path:
        """Find a Research OS workspace without requiring ``.os_state/``."""
        p = Path(start or Path.cwd()).resolve()
        markers = (
            ".os_state",
        )
        for _ in range(10):
            if any((p / marker).exists() for marker in markers):
                return p
            if p.parent == p:
                break
            p = p.parent
        return Path.cwd().resolve()

    def _validate_relative(self, relative_path: str) -> str:
        rel = relative_path.strip().replace("\\", "/").lstrip("/")
        first = rel.split("/", 1)[0]
        if first not in ASSET_ROOTS and rel not in {"config.yaml", "models.yaml"}:
            raise ValueError(f"Unsupported packaged asset path: {relative_path}")
        if ".." in Path(rel).parts:
            raise ValueError(f"Asset path cannot traverse parents: {relative_path}")
        return rel

    def package_root(self):
        """Return the importlib Traversable root for packaged assets."""
        return resources.files(ASSET_PACKAGE)

    def package_asset(self, relative_path: str):
        rel = self._validate_relative(relative_path)
        return self.package_root().joinpath(*rel.split("/"))

    @staticmethod
    def _walk_traversable(base, prefix: str = ""):
        for item in base.iterdir():
            rel = f"{prefix}/{item.name}" if prefix else item.name
            if item.is_file():
                yield rel, item
            elif item.is_dir():
                yield from AssetManager._walk_traversable(item, rel)

    def local_override(self, relative_path: str) -> Path:
        rel = self._validate_relative(relative_path)
        return self.override_root / rel

    def exists(self, relative_path: str) -> bool:
        return (
            self.local_override(relative_path).exists()
            or self.package_asset(relative_path).is_file()
        )

    def read_text(self, relative_path: str, encoding: str = "utf-8") -> str:
        """Read a text asset, preferring an explicit local override."""
        local = self.local_override(relative_path)
        if local.exists() and local.is_file():
            return local.read_text(encoding=encoding)

        asset = self.package_asset(relative_path)
        if not asset.is_file():
            raise FileNotFoundError(relative_path)
        return asset.read_text(encoding=encoding)

