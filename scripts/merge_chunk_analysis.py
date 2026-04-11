"""Merge per-chunk analysis files into analyzed.json — Phase A.4.1.

This script consolidates the per-chunk semantic analysis files produced
during SKILL.md Step 3b (chunks/NN.analysis.json — one per chunk) into the
single analyzed.json skeleton produced by analyzed_init.py.

Workflow:
    1. analyzed_init.py → analyzed.json skeleton with _pending_analysis markers
    2. Claude reads each chunks/NN-*.txt and Writes chunks/NN.analysis.json
    3. merge_chunk_analysis.py (this script) → validates each analysis file
       against references/chunk_analysis_schema.json and merges semantic
       fields into the corresponding entry of analyzed.chunks[]

Split-semantic support:
    When the chunker groups multiple pieces in a single physical file, the
    user can produce multiple analysis files (chunks/02a.analysis.json,
    chunks/02b.analysis.json) for the same physical chunk. Each entry must
    set `chunk_file_override` to the original chunk_file path. The merged
    analyzed.chunks[] will contain N entries all pointing to the same
    physical file, satisfying the integrity gate.

Error modes:
    - Missing chunks/NN.analysis.json for a pending index → exit 1 with list
    - Schema validation failure → exit 1 with details
    - Detected helper-script pattern (chunks/build_analyzed.py etc.) → warns
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "references" / "chunk_analysis_schema.json"

SEMANTIC_FIELDS = [
    "tipo_peca",
    "partes",
    "pedidos",
    "argumentos_chave",
    "valores",
    "fatos_relevantes",
    "decisao",
    "resumo",
    "acordao_structure",
    "artigos_lei",
    "jurisprudencia",
    "binding_precedents",
    "prazos",
    "citation_spans",
    "instancia",
]

# Filename pattern: 00.analysis.json, 02a.analysis.json, etc.
ANALYSIS_FILE_RE = re.compile(r"^(?P<idx>[0-9]+[a-z]?)\.analysis\.json$")

HELPER_SCRIPT_PATTERNS = [
    "build_analyzed.py",
    "build_analysis.py",
    "populate_analyzed.py",
    "fix_analyzed.py",
]


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(data: dict, schema: dict, source: str) -> list[str]:
    """Validate a per-chunk analysis file against the schema. Returns errors."""
    try:
        import jsonschema
    except ImportError:
        return [f"{source}: jsonschema package not available"]

    validator = jsonschema.Draft7Validator(schema)
    errors = []
    for err in validator.iter_errors(data):
        path = ".".join(str(p) for p in err.absolute_path)
        loc = f" at {path}" if path else ""
        errors.append(f"{source}{loc}: {err.message}")
    return errors


def discover_analysis_files(chunks_dir: Path) -> dict[str, Path]:
    """Find all chunks/NN.analysis.json files and index them by string index."""
    found: dict[str, Path] = {}
    if not chunks_dir.exists():
        return found
    for p in sorted(chunks_dir.iterdir()):
        m = ANALYSIS_FILE_RE.match(p.name)
        if m:
            found[m.group("idx")] = p
    return found


def check_helper_scripts(chunks_dir: Path, output_dir: Path) -> list[str]:
    """Warn if the user wrote a helper Python script to hardcode enrichments."""
    warnings = []
    for d in [chunks_dir, output_dir, output_dir.parent]:
        if not d.exists():
            continue
        for pattern in HELPER_SCRIPT_PATTERNS:
            matches = list(d.glob(pattern))
            if matches:
                warnings.append(
                    f"WARN: detected helper script {matches[0]} — "
                    f"this is the anti-pattern from v3.0.1. Prefer one "
                    f"chunks/NN.analysis.json Write per chunk."
                )
    return warnings


def merge(
    analyzed: dict, analysis_files: dict[str, Path], schema: dict
) -> tuple[dict, list[str]]:
    """Merge analysis files into analyzed.chunks[]. Returns (analyzed, errors)."""
    errors: list[str] = []
    chunks = analyzed.get("chunks", []) or []

    # Map pending chunks by int index for fast lookup
    pending_by_int_idx = {int(ch["index"]): ch for ch in chunks if "index" in ch}

    # Track which analysis files have been consumed (for split-semantic detection)
    merged_chunks: list[dict] = []
    consumed_file_keys: set[str] = set()

    # First pass: numeric-only indexes replace their counterparts
    numeric_keys = [k for k in analysis_files if k.isdigit()]
    suffixed_keys = [k for k in analysis_files if not k.isdigit()]

    for ch in chunks:
        idx = int(ch["index"])
        str_idx = str(idx).zfill(2) if idx < 10 else str(idx)
        # Look for file with exact numeric match (00, 01, ..., or 0, 1, ...)
        key = None
        for candidate in [f"{idx:02d}", str(idx)]:
            if candidate in numeric_keys:
                key = candidate
                break
        if key is None:
            errors.append(
                f"ERROR: chunk[{idx}] ({ch.get('label', '?')}) has no matching "
                f"chunks/{idx:02d}.analysis.json file. Produce one via Write."
            )
            merged_chunks.append(ch)  # Keep skeleton
            continue

        # Load and validate the analysis file
        try:
            analysis = json.loads(analysis_files[key].read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"ERROR: {analysis_files[key]}: invalid JSON: {e}")
            merged_chunks.append(ch)
            continue

        schema_errors = _validate(analysis, schema, str(analysis_files[key]))
        if schema_errors:
            errors.extend(schema_errors)
            merged_chunks.append(ch)
            continue

        merged = dict(ch)
        merged.pop("_pending_analysis", None)
        for field in SEMANTIC_FIELDS:
            if field in analysis:
                merged[field] = analysis[field]
        # Prefer tipo_peca as the canonical label if provided
        if "tipo_peca" in analysis and analysis["tipo_peca"]:
            merged["tipo_peca"] = analysis["tipo_peca"]
        merged_chunks.append(merged)
        consumed_file_keys.add(key)

    # Second pass: suffixed files (split-semantic) append new entries
    for key in sorted(suffixed_keys):
        path = analysis_files[key]
        try:
            analysis = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"ERROR: {path}: invalid JSON: {e}")
            continue

        schema_errors = _validate(analysis, schema, str(path))
        if schema_errors:
            errors.extend(schema_errors)
            continue

        # Find the parent numeric chunk to copy technical fields from
        m = re.match(r"^(\d+)", key)
        if not m:
            errors.append(f"ERROR: {path}: suffixed index {key!r} has no numeric prefix")
            continue
        parent_idx = int(m.group(1))
        parent = pending_by_int_idx.get(parent_idx)
        if parent is None:
            errors.append(
                f"ERROR: {path}: parent chunk {parent_idx} not found in skeleton"
            )
            continue

        new_entry = {
            k: parent.get(k)
            for k in ["char_count", "chunk_file", "page_range", "ocr_confidence"]
            if k in parent
        }
        new_entry["index"] = analysis.get("index", key)
        new_entry["label"] = analysis.get("tipo_peca", parent.get("label"))
        # Allow override of chunk_file (split-semantic may reuse parent's file)
        if "chunk_file_override" in analysis:
            new_entry["chunk_file"] = analysis["chunk_file_override"]

        for field in SEMANTIC_FIELDS:
            if field in analysis and field != "chunk_file_override":
                new_entry[field] = analysis[field]

        merged_chunks.append(new_entry)

    analyzed["chunks"] = merged_chunks
    analyzed["total_chunks"] = len(merged_chunks)
    # Drop any remaining pending markers
    for ch in merged_chunks:
        ch.pop("_pending_analysis", None)

    return analyzed, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge per-chunk analysis files into analyzed.json",
    )
    parser.add_argument(
        "--analyzed",
        "-a",
        required=True,
        help="Path to analyzed.json skeleton (produced by analyzed_init.py)",
    )
    parser.add_argument(
        "--chunks-dir",
        "-c",
        required=True,
        help="Directory containing chunks/NN.analysis.json files",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path to write merged analyzed.json",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Continue even if some chunks have no analysis file (exit 0 with warnings)",
    )
    args = parser.parse_args(argv)

    analyzed_path = Path(args.analyzed)
    chunks_dir = Path(args.chunks_dir)

    if not analyzed_path.exists():
        print(f"ERROR: analyzed file not found: {analyzed_path}", file=sys.stderr)
        return 2

    try:
        analyzed = json.loads(analyzed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {analyzed_path}: {e}", file=sys.stderr)
        return 2

    try:
        schema = _load_schema()
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot load schema at {SCHEMA_PATH}: {e}", file=sys.stderr)
        return 2

    # Warn about helper scripts
    for w in check_helper_scripts(chunks_dir, analyzed_path.parent):
        print(w, file=sys.stderr)

    analysis_files = discover_analysis_files(chunks_dir)
    if not analysis_files:
        print(
            f"ERROR: no chunks/NN.analysis.json files found in {chunks_dir}. "
            f"Run Step 3b: for each chunk, Read the source and Write "
            f"chunks/NN.analysis.json with the semantic analysis.",
            file=sys.stderr,
        )
        return 1

    merged, errors = merge(analyzed, analysis_files, schema)

    if errors:
        print(f"[merge_chunk_analysis] {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        if not args.allow_missing:
            return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    n = len(merged.get("chunks", []))
    print(f"[merge_chunk_analysis] merged {n} chunk(s) → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
