import logging
import json
import hashlib
from pathlib import Path

logger = logging.getLogger("research.tools.profiling")


def _profile_inputs(root: Path) -> None:
    try:
        raw_data_dir = root / "inputs" / "raw_data"
        if not raw_data_dir.exists():
            return

        inventory = {
            "files": [],
            "total_size_mb": 0.0,
            "estimated_processing_time_seconds": 0,
        }

        for p in raw_data_dir.rglob("*"):
            if not p.is_file():
                continue

            ext = p.suffix.lower()
            size_bytes = p.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            inventory["total_size_mb"] += size_mb

            file_info = {
                "path": str(p.relative_to(root)),
                "size_mb": round(size_mb, 2),
                "rows": 0,
                "columns": 0,
                "column_names": [],
                "dtypes": {},
                "missing_pct": {},
                "sha256": "",
                "encoding": "",
            }

            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            file_info["sha256"] = h.hexdigest()

            try:
                import pandas as pd
                has_pandas = True
            except ImportError:
                has_pandas = False

            try:
                df = None
                if has_pandas:
                    if ext == ".csv":
                        # Encoding fallback: a latin-1/cp1252 CSV would
                        # otherwise raise UnicodeDecodeError, get swallowed by
                        # the outer except, and be inventoried as 0 rows / 0
                        # columns — indistinguishable from a genuinely empty
                        # file. Try UTF-8, then cp1252, then latin-1, then
                        # errors='replace', recording which encoding worked.
                        from research_os.tools.actions.data.data import (
                            _read_csv_with_fallback,
                        )

                        df = _read_csv_with_fallback(p)
                        note = df.attrs.get("_ro_encoding_note")
                        file_info["encoding"] = note or "utf-8"
                    elif ext == ".parquet":
                        df = pd.read_parquet(p)

                if df is not None:
                    file_info["rows"] = len(df)
                    file_info["columns"] = len(df.columns)
                    file_info["column_names"] = list(df.columns)
                    file_info["dtypes"] = {k: str(v) for k, v in df.dtypes.items()}
                    file_info["missing_pct"] = {
                        k: round(v, 2) for k, v in (df.isna().mean() * 100).items()
                    }
                    inventory["estimated_processing_time_seconds"] += int(
                        (len(df) * len(df.columns) * 0.0001) * 3
                    )
            except Exception:
                pass

            inventory["files"].append(file_info)

        inventory["total_size_mb"] = round(inventory["total_size_mb"], 2)

        log_path = root / "workspace" / "logs" / "data_inventory.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(inventory, f, indent=2)

    except Exception as e:
        logger.error(f"Data profiling failed: {e}")
