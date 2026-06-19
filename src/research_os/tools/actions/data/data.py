"""Tabular data tools: sample, profile, convert."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.data")


def _read(path: Path):
    """Read a tabular file into a pandas DataFrame, raising on unknown format."""
    import pandas as pd

    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext == ".feather":
        return pd.read_feather(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".json":
        return pd.read_json(path)
    if ext == ".jsonl":
        return pd.read_json(path, lines=True)
    if ext == ".rds":
        try:
            import pyreadr  # type: ignore

            result = pyreadr.read_r(str(path))
            return next(iter(result.values()))
        except ImportError as exc:
            from research_os.server.errors import RoError
            raise RoError(
                what="pyreadr is required for .rds files",
                why="pyreadr is an optional dependency and is not installed",
                next_action="run: pip install pyreadr",
            ) from exc
    from research_os.server.errors import RoError
    supported = ".csv, .tsv, .parquet, .feather, .xlsx, .xls, .json, .jsonl, .rds"
    raise RoError(
        what=f"Unsupported file format: {ext}",
        why=f"reader is only wired for: {supported}",
        next_action="convert to one of the supported formats or open an issue",
    )


def _current_path(root: Path) -> str:
    try:
        from research_os.project_ops import load_state

        state = load_state(root)
        current = state.get("current_path")
        if current and current != "main":
            return current
    except Exception:
        pass
    workspace = root / "workspace"
    if workspace.exists():
        dirs = [
            d.name
            for d in workspace.iterdir()
            if d.is_dir() and d.name[:2].isdigit() and not d.name.endswith("__DEAD_END")
        ]
        if dirs:
            return sorted(dirs)[-1]
    return ""


def data_sample(
    filepath: str, n_rows: int, strategy: str = "head", root: Path = Path(".")
) -> dict[str, Any]:
    """Sample N rows from a tabular dataset and write the sample to the current step."""
    try:
        data_path = root / filepath
        if not data_path.exists():
            return {"status": "error", "message": f"File not found: {filepath}"}

        df = _read(data_path)
        if strategy == "head":
            sampled = df.head(n_rows)
        elif strategy == "tail":
            sampled = df.tail(n_rows)
        elif strategy == "random":
            sampled = df.sample(n=min(n_rows, len(df)), random_state=42)
        else:
            return {"status": "error", "message": f"Unknown strategy: {strategy}"}

        current = _current_path(root)
        if current:
            out_path = (
                root / "workspace" / current / "data" / f"sampled_{data_path.name}"
            )
        else:
            out_path = root / "workspace" / "logs" / f"sampled_{data_path.name}"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ext = data_path.suffix.lower()
        if ext == ".parquet":
            sampled.to_parquet(out_path, index=False)
        elif ext == ".feather":
            sampled.to_feather(out_path)
        else:
            sampled.to_csv(out_path.with_suffix(".csv"), index=False)
            out_path = out_path.with_suffix(".csv")

        # Round-trip through pandas' JSON writer so Timestamp values
        # become ISO strings and NaN becomes null — a raw to_dict()
        # preview leaks Timestamp objects + NaN (invalid JSON).
        preview_rows = json.loads(
            sampled.head(min(10, len(sampled))).to_json(
                orient="records", date_format="iso"
            )
        )

        return {
            "status": "success",
            "filepath": str(out_path.relative_to(root)),
            "rows": len(sampled),
            "columns": list(sampled.columns),
            "preview": preview_rows,
        }
    except Exception as e:
        logger.error(f"data_sample failed: {e}")
        return {"status": "error", "message": str(e)}


def data_profile(filepath: str, root: Path = Path(".")) -> dict[str, Any]:
    """Profile a tabular dataset: schema, missingness, dtypes, descriptive stats."""
    try:
        data_path = root / filepath
        if not data_path.exists():
            return {"status": "error", "message": f"File not found: {filepath}"}

        df = _read(data_path)
        n_rows, n_cols = df.shape

        columns = []
        for col in df.columns:
            series = df[col]
            null_pct = float(series.isna().mean()) * 100.0
            dtype = str(series.dtype)
            entry = {
                "name": str(col),
                "dtype": dtype,
                "null_pct": round(null_pct, 2),
                "n_unique": int(series.nunique(dropna=True)),
            }
            if dtype.startswith(("int", "float")):
                try:
                    desc = series.describe()
                    entry.update(
                        {
                            "min": float(desc["min"]),
                            "max": float(desc["max"]),
                            "mean": float(desc["mean"]),
                            "std": float(desc["std"]),
                        }
                    )
                except Exception:
                    pass
            elif dtype == "object" or "category" in dtype:
                top_values = series.value_counts().head(5).to_dict()
                entry["top_values"] = {str(k): int(v) for k, v in top_values.items()}
            columns.append(entry)

        suggestions: list[str] = []
        high_missing = [c for c in columns if c["null_pct"] > 20]
        if high_missing:
            names = ", ".join(c["name"] for c in high_missing[:5])
            suggestions.append(
                f"{len(high_missing)} column(s) have >20% missing values "
                f"(e.g., {names}). Decide on imputation or exclusion."
            )
        if n_rows < 30:
            suggestions.append(
                f"Sample size n={n_rows} is small — consider whether this is "
                "enough for the planned statistical test."
            )
        suggestions.append(
            "Next step: create an experiment (sys_path(operation='create')) for baseline EDA."
        )

        # Persist
        current = _current_path(root)
        if current:
            out_path = (
                root
                / "workspace"
                / current
                / "outputs"
                / "reports"
                / f"profile_{data_path.stem}.md"
            )
        else:
            out_path = (
                root / "workspace" / "logs" / f"profile_{data_path.stem}.md"
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Data Profile — {data_path.name}",
            "",
            f"- Rows: {n_rows:,}",
            f"- Columns: {n_cols}",
            "",
            "## Column summary",
            "",
            "| Column | dtype | % missing | unique |",
            "|---|---|---:|---:|",
        ]
        for c in columns:
            lines.append(
                f"| {c['name']} | {c['dtype']} | {c['null_pct']:.1f} | {c['n_unique']} |"
            )
        lines.extend(["", "## Suggested next steps", ""])
        for s in suggestions:
            lines.append(f"- {s}")
        out_path.write_text("\n".join(lines) + "\n")

        return {
            "status": "success",
            "rows": n_rows,
            "columns": columns,
            "suggestions": suggestions,
            "report_path": str(out_path.relative_to(root)),
        }
    except Exception as e:
        logger.error(f"data_profile failed: {e}")
        return {"status": "error", "message": str(e)}


def data_convert(filepath: str, output_format: str, root: Path) -> dict[str, Any]:
    try:
        p = root / filepath
        # Verify containment up front: an absolute filepath outside root
        # makes `root / filepath` resolve to that absolute path (Path
        # discards root), which would write the converted file OUTSIDE the
        # project and then make `relative_to(root)` raise. Reject it here
        # instead of writing-then-failing.
        try:
            p.resolve().relative_to(root.resolve())
        except ValueError:
            return {"status": "error", "message": f"Path escapes project root: {filepath}"}
        if not p.exists() or not p.is_file():
            return {"status": "error", "message": f"File not found: {filepath}"}

        df = _read(p)
        output_format = output_format.lower().lstrip(".")
        out_path = p.with_suffix(f".{output_format}")
        # Never overwrite the source in place when the target extension equals
        # the input's (e.g. convert a .csv "to csv") — write a distinct file.
        if out_path.resolve() == p.resolve():
            out_path = p.with_name(f"{p.stem}_converted.{output_format}")

        if output_format == "csv":
            df.to_csv(out_path, index=False)
        elif output_format == "parquet":
            df.to_parquet(out_path, index=False)
        elif output_format == "feather":
            df.to_feather(out_path)
        elif output_format == "rds":
            try:
                import pyreadr  # type: ignore

                pyreadr.write_rds(str(out_path), df)
            except ImportError:
                return {
                    "status": "error",
                    "message": "pyreadr required for .rds output",
                }
        else:
            return {
                "status": "error",
                "message": f"Unsupported output format: {output_format}",
            }

        # out_path is guaranteed inside root by the up-front check, but mirror
        # the established _fake_pdfs idiom so a symlink edge case can't crash.
        try:
            rel = str(out_path.relative_to(root))
        except ValueError:
            rel = str(out_path)
        return {
            "status": "success",
            "message": f"Converted to {output_format}",
            "filepath": rel,
        }
    except Exception as e:
        logger.error(f"data_convert failed: {e}")
        return {"status": "error", "message": str(e)}
