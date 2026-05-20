"""Format router: detect file formats and produce a data format manifest.

This is a lightweight, safe scaffold used by the larger plan. It performs
extension-based detection and writes a JSON manifest consumed by downstream
phases. Parsers are lazy-checked via importlib.
"""
from pathlib import Path
import json
import importlib.util
from typing import Dict, Any

FORMAT_REGISTRY = {
    # tabular
    ".csv": {"format": "CSV", "pandera_applicable": True, "domain_hint": "general", "parser": "pandas"},
    ".tsv": {"format": "TSV", "pandera_applicable": True, "domain_hint": "general", "parser": "pandas"},
    ".parquet": {"format": "PARQUET", "pandera_applicable": True, "domain_hint": "general", "parser": "pyarrow"},
    ".xlsx": {"format": "XLSX", "pandera_applicable": True, "domain_hint": "general", "parser": "openpyxl"},
    ".json": {"format": "JSON_TABLE", "pandera_applicable": True, "domain_hint": "general", "parser": "json"},
    # genomics
    ".fastq": {"format": "FASTQ", "pandera_applicable": False, "domain_hint": "genomics", "parser": "Bio"},
    ".fq": {"format": "FASTQ", "pandera_applicable": False, "domain_hint": "genomics", "parser": "Bio"},
    ".bam": {"format": "BAM", "pandera_applicable": False, "domain_hint": "genomics", "parser": "pysam"},
    ".vcf": {"format": "VCF", "pandera_applicable": False, "domain_hint": "genomics", "parser": "cyvcf2"},
    # neuro
    ".nii": {"format": "NIFTI", "pandera_applicable": False, "domain_hint": "neuroimaging", "parser": "nibabel"},
    ".nii.gz": {"format": "NIFTI_GZ", "pandera_applicable": False, "domain_hint": "neuroimaging", "parser": "nibabel"},
}


def _lazy_has_module(name: str) -> bool:
    if not name:
        return False
    return importlib.util.find_spec(name) is not None


def detect_format(filepath: str) -> Dict[str, Any]:
    p = Path(filepath)
    # prefer full suffix chain (e.g., .nii.gz)
    suffix_chain = "".join(p.suffixes) if p.suffixes else p.suffix
    if suffix_chain in FORMAT_REGISTRY:
        entry = FORMAT_REGISTRY[suffix_chain].copy()
    else:
        ext = p.suffix.lower()
        entry = FORMAT_REGISTRY.get(ext, {"format": "UNKNOWN", "pandera_applicable": False, "domain_hint": None, "parser": None})

    parser = entry.get("parser")
    entry["parser_available"] = _lazy_has_module(parser) if parser else False
    entry["path"] = str(p)
    return entry


def route_file(filepath: str) -> Dict[str, Any]:
    info = detect_format(filepath)
    domain = info.get("domain_hint")
    info["requires_container"] = domain in ("genomics", "neuroimaging")
    return info


def scan_directory(dirpath: str, out_path: str = ".research/cache/data_format_manifest.json") -> Dict[str, Any]:
    base = Path(dirpath)
    manifest = {"files": [], "tabular_count": 0, "non_tabular_count": 0}
    if not base.exists():
        return manifest
    for p in base.rglob("*"):
        if p.is_file():
            meta = route_file(str(p))
            manifest["files"].append(meta)
            if meta.get("pandera_applicable"):
                manifest["tabular_count"] += 1
            else:
                manifest["non_tabular_count"] += 1

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    return manifest


def is_pandera_applicable(format_meta: Dict[str, Any]) -> bool:
    return bool(format_meta.get("pandera_applicable", False))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("dir", help="Directory to scan")
    ap.add_argument("--out", default=".research/cache/data_format_manifest.json")
    args = ap.parse_args()
    m = scan_directory(args.dir, args.out)
    print(f"Wrote manifest: {args.out} — {len(m['files'])} files")
