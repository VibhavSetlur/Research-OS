"""Tabular data tools: sample, profile, convert."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger("research_os.tools.data")

# Upper bound on the on-disk size of a file we will materialise fully into a
# pandas DataFrame (profile, random/tail sample, every non-streamable format).
# Above this we refuse with a clear message rather than risk OOM-ing the MCP
# server. sys_file_read caps plain reads at 50 MB and redirects big tabular
# data here, so the data tools get a larger ceiling — but still bounded.
_MAX_READ_BYTES = 500 * 1024 * 1024  # 500 MB


def _contained_data_path(filepath: str, root: Path) -> tuple[Path | None, dict | None]:
    """Resolve ``root / filepath`` and reject anything that escapes ``root``.

    An absolute or ``../``-escaping ``filepath`` makes ``root / filepath``
    resolve outside the project (pathlib discards ``root`` for an absolute
    operand). Mirrors the up-front guard ``data_convert`` already uses so
    ``data_sample`` / ``data_profile`` share the same containment contract.

    Returns ``(path, None)`` when contained, or ``(None, error_dict)`` when it
    escapes — the error dict reuses the existing "escapes project root"
    message string the tests assert on.
    """
    data_path = root / filepath
    try:
        data_path.resolve().relative_to(root.resolve())
    except ValueError:
        return None, {
            "status": "error",
            "message": f"Path escapes project root: {filepath}",
        }
    return data_path, None


def _read_csv_with_fallback(path: Path, **kwargs):
    """Read a CSV/TSV, falling back through common encodings.

    pandas defaults to UTF-8 and raises ``UnicodeDecodeError`` on the first
    invalid byte. latin-1 / cp1252 CSVs are extremely common (Excel exports,
    European datasets), so try UTF-8 (incl. BOM), then cp1252, then latin-1
    (which never raises on bytes); as a last resort decode UTF-8 with
    ``errors='replace'``. When a non-UTF-8 encoding succeeds, record a note on
    ``df.attrs`` so callers can surface that bytes were reinterpreted.
    """
    import pandas as pd

    last_exc: UnicodeDecodeError | None = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, **kwargs)
            if enc != "utf-8-sig":
                df.attrs["_ro_encoding_note"] = (
                    f"decoded with fallback encoding '{enc}' (not valid UTF-8)"
                )
            return df
        except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 catches first
            last_exc = exc
            continue
    # Last resort: replace undecodable bytes rather than raise.
    try:
        df = pd.read_csv(path, encoding="utf-8", encoding_errors="replace", **kwargs)
    except TypeError:
        # Very old pandas without encoding_errors kwarg — re-raise the
        # original decode error so the caller still gets a real message.
        if last_exc is not None:
            raise last_exc
        raise
    df.attrs["_ro_encoding_note"] = (
        "decoded UTF-8 with errors='replace'; some bytes lost"
    )
    return df


def _read(path: Path):
    """Read a tabular file into a pandas DataFrame, raising on unknown format."""
    import pandas as pd

    ext = path.suffix.lower()
    if ext == ".csv":
        return _read_csv_with_fallback(path)
    if ext == ".tsv":
        return _read_csv_with_fallback(path, sep="\t")
    if ext in (".parquet", ".feather"):
        try:
            return (
                pd.read_parquet(path) if ext == ".parquet" else pd.read_feather(path)
            )
        except ImportError as exc:
            from research_os.server.errors import RoError

            raise RoError(
                what="pyarrow is required for .parquet/.feather files",
                why="pyarrow/fastparquet is an optional dependency and is not installed",
                next_action="run: pip install --upgrade research-os  (or: pip install pyarrow)",
            ) from exc
    if ext in (".xlsx", ".xls"):
        try:
            return pd.read_excel(path)
        except ImportError as exc:
            from research_os.server.errors import RoError

            raise RoError(
                what="openpyxl (.xlsx) / xlrd (.xls) is required to read Excel files",
                why="the Excel engine is an optional dependency and is not installed",
                next_action="run: pip install --upgrade research-os  (or: pip install openpyxl xlrd)",
            ) from exc
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
        data_path, esc = _contained_data_path(filepath, root)
        if esc is not None:
            return esc
        if not data_path.exists():
            return {"status": "error", "message": f"File not found: {filepath}"}

        # Validate n_rows here (not in the handler) so direct callers and the
        # unified tool_data dispatch are both covered. A negative n_rows is
        # *valid* pandas for head/tail ("all rows except the last N") and
        # would silently mis-select rows with status=success; reject it so
        # the contract matches the random branch, which already errors.
        if n_rows < 0:
            return {
                "status": "error",
                "message": (
                    f"n_rows must be >= 0 (got {n_rows}). Negative values "
                    "silently mis-select rows for head/tail."
                ),
            }
        if n_rows == 0:
            return {
                "status": "error",
                "message": "n_rows must be >= 1 to produce a non-empty sample.",
            }

        ext = data_path.suffix.lower()
        encoding_note: str | None = None

        # Streaming fast-path for head on CSV/TSV: pandas can read only the
        # first n_rows without materialising the whole (possibly multi-GB)
        # file. Random/tail still need the full frame, so they go through the
        # size-gated full read below.
        if strategy == "head" and ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            sampled = _read_csv_with_fallback(data_path, sep=sep, nrows=n_rows)
            encoding_note = sampled.attrs.get("_ro_encoding_note")
        else:
            size = data_path.stat().st_size
            if size > _MAX_READ_BYTES:
                return {
                    "status": "error",
                    "message": (
                        f"File is {size / (1024 * 1024):.0f} MB (> "
                        f"{_MAX_READ_BYTES // (1024 * 1024)} MB cap). "
                        "Use strategy='head' on a CSV/TSV (streamed) or "
                        "pre-slice the file before sampling."
                    ),
                }
            df = _read(data_path)
            encoding_note = df.attrs.get("_ro_encoding_note")
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

        result = {
            "status": "success",
            "filepath": str(out_path.relative_to(root)),
            "rows": len(sampled),
            "columns": list(sampled.columns),
            "preview": preview_rows,
        }
        if encoding_note:
            result["encoding_note"] = encoding_note
        return result
    except Exception as e:
        logger.error(f"data_sample failed: {e}")
        return {"status": "error", "message": str(e)}


def data_profile(filepath: str, root: Path = Path(".")) -> dict[str, Any]:
    """Profile a tabular dataset: schema, missingness, dtypes, descriptive stats."""
    try:
        from pandas.api.types import (
            is_bool_dtype,
            is_datetime64_any_dtype,
            is_numeric_dtype,
        )

        data_path, esc = _contained_data_path(filepath, root)
        if esc is not None:
            return esc
        if not data_path.exists():
            return {"status": "error", "message": f"File not found: {filepath}"}

        # A profile needs the full frame (column-wide stats), so a multi-GB
        # file would OOM the server. Refuse above the cap with a clear pointer
        # to head-sampling rather than crash.
        size = data_path.stat().st_size
        if size > _MAX_READ_BYTES:
            return {
                "status": "error",
                "message": (
                    f"File is {size / (1024 * 1024):.0f} MB (> "
                    f"{_MAX_READ_BYTES // (1024 * 1024)} MB cap) — profiling "
                    "loads the whole frame. Sample first with "
                    "tool_data_sample (strategy='head'), then profile the sample."
                ),
            }

        df = _read(data_path)
        encoding_note = df.attrs.get("_ro_encoding_note")
        n_rows, n_cols = df.shape

        def _fin(x):
            """Coerce a stat to a JSON-finite float (NaN/Inf → None).

            std of a single value is NaN, an all-NaN column makes every stat
            NaN, and overflow gives inf — all of which serialise to the
            JS-only `NaN`/`Infinity` tokens (invalid JSON). Null them here so
            every consumer gets valid JSON.
            """
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            return v if math.isfinite(v) else None

        columns = []
        for col in df.columns:
            series = df[col]
            null_pct = float(series.isna().mean()) * 100.0
            dtype = str(series.dtype)
            # nunique()/value_counts() hash every cell and raise
            # `TypeError: unhashable type` on list/dict-valued columns
            # (normal in .json/.jsonl). Guard per-column so one bad column
            # degrades instead of killing the whole profile.
            try:
                n_unique: int | None = int(series.nunique(dropna=True))
            except TypeError:
                n_unique = None
            entry = {
                "name": str(col),
                "dtype": dtype,
                "null_pct": round(null_pct, 2),
                "n_unique": n_unique,
            }
            if n_unique is None:
                entry["note"] = (
                    "nested/complex values (unhashable) — n_unique unavailable"
                )
            # Use pandas type introspection (not a lowercase string-prefix
            # test) so nullable extension dtypes (Int64/Float64) and
            # datetime columns are covered, not silently skipped.
            if is_numeric_dtype(series) and not is_bool_dtype(series):
                try:
                    desc = series.describe()
                    entry.update(
                        {
                            "min": _fin(desc["min"]),
                            "max": _fin(desc["max"]),
                            "mean": _fin(desc["mean"]),
                            "std": _fin(desc["std"]),
                        }
                    )
                except Exception:
                    pass
            elif is_datetime64_any_dtype(series):
                try:
                    non_null = series.dropna()
                    if len(non_null):
                        entry["min"] = non_null.min().isoformat()
                        entry["max"] = non_null.max().isoformat()
                except Exception:
                    pass
            elif dtype == "object" or "category" in dtype:
                try:
                    top_values = series.value_counts().head(5).to_dict()
                    entry["top_values"] = {
                        str(k): int(v) for k, v in top_values.items()
                    }
                except TypeError:
                    pass  # unhashable values; skip top_values

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
        if encoding_note:
            suggestions.append(
                f"Encoding: {encoding_note} — verify text columns look correct."
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
            uniq = c["n_unique"] if c["n_unique"] is not None else "n/a"
            lines.append(
                f"| {c['name']} | {c['dtype']} | {c['null_pct']:.1f} | {uniq} |"
            )
        lines.extend(["", "## Suggested next steps", ""])
        for s in suggestions:
            lines.append(f"- {s}")
        out_path.write_text("\n".join(lines) + "\n")

        result = {
            "status": "success",
            "rows": n_rows,
            "columns": columns,
            "suggestions": suggestions,
            "report_path": str(out_path.relative_to(root)),
        }
        if encoding_note:
            result["encoding_note"] = encoding_note
        return result
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
        elif output_format in ("parquet", "feather"):
            try:
                if output_format == "parquet":
                    df.to_parquet(out_path, index=False)
                else:
                    df.to_feather(out_path)
            except ImportError:
                return {
                    "status": "error",
                    "message": (
                        "pyarrow required for .parquet/.feather output — "
                        "run: pip install --upgrade research-os"
                    ),
                }
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
