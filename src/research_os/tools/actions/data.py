import logging
from typing import Dict, Any
from pathlib import Path
import pandas as pd
import numpy as np

logger = logging.getLogger("research.tools.data")

def data_sample(filepath: str, n_rows: int, strategy: str, root: Path) -> Dict[str, Any]:
    try:
        data_path = root / filepath
        if not data_path.exists():
            return {"error": f"File not found: {filepath}"}
            
        ext = data_path.suffix.lower()
        if ext == ".csv":
             df = pd.read_csv(data_path)
        elif ext == ".parquet":
             df = pd.read_parquet(data_path)
        else:
             return {"error": f"Unsupported file format: {ext}"}
             
        if strategy == "head":
            sampled = df.head(n_rows)
        elif strategy == "random":
            sampled = df.sample(n=min(n_rows, len(df)), random_state=42)
        else:
            return {"error": f"Unknown strategy: {strategy}"}
            
        out_path = root / f"workspace/data/derived/sampled_{data_path.name}"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        if ext == ".csv":
             sampled.to_csv(out_path, index=False)
        else:
             sampled.to_parquet(out_path, index=False)
             
        return {"status": "success", "filepath": str(out_path.absolute()), "rows": len(sampled)}
    except Exception as e:
        logger.error(f"Data sample failed: {e}")
        return {"status": "error", "message": str(e)}
