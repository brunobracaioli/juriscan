"""Content quality sanity check for analyzed.json — non-blocking WARN script.

Phase A.3 — Surfaces shallow analyses where the per-chunk semantic
extraction left canonical fields empty. The script does NOT fail the
pipeline (it always exits 0) — it only emits human-readable warnings to
stderr and a structured JSON summary to stdout.

Why this exists
---------------
Real-world legacy runs sometimes produce analyzed.json files where the
orchestrating Claude session took a shortcut (eg. wrote a build_analyzed.py
helper that hardcoded a few enrichments) instead of doing thorough
per-chunk analysis. The schema validator passes because every canonical
field is technically optional, but the result is an empty shell:
`tipo_peca: null` everywhere, `partes: null`, `valores: null`, vault
notes with only frontmatter and a back-link.

This script measures the populated rate of the canonical fields and
flags suspicious ratios so the user (and the running Claude session) can
notice the gap and re-do Step 3 properly.

Usage
-----
    python3 scripts/content_quality_check.py --input analyzed.json
    python3 scripts/content_quality_check.py --input analyzed.json --json
    python3 scripts/content_quality_check.py --input analyzed.json --strict   # exit 1 on warnings

The default exit code is 0 even when warnings exist. Pass `--strict` to
make warnings block (useful in CI or when wiring this into SKILL.md as a
gate).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Fields we expect to see populated when the corresponding piece type is
# present. Keys are canonical tipo_peca values (matching the taxonomy).
# Values are field names that should be non-empty for that piece type.
EXPECTED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "PETIÇÃO INICIAL": ["pedidos", "fatos_relevantes", "valores"],
    "CONTESTAÇÃO": ["fatos_relevantes"],
    "RÉPLICA": ["fatos_relevantes"],
    "SENTENÇA": ["decisao", "valores"],
    "ACÓRDÃO": ["decisao", "acordao_detail"],
    "DESPACHO": ["decisao"],
    "APELAÇÃO": ["pedidos"],
    "AGRAVO": ["pedidos"],
    "EMBARGOS": [],
    "RECURSO ESPECIAL": ["pedidos"],
    "RECURSO EXTRAORDINÁRIO": ["pedidos"],
    "LAUDO PERICIAL": ["fatos_relevantes"],
}

# Fields whose absence anywhere is suspicious for any pipeline run with
# > 1 chunks (these are the "every analyzed.json should have at least
# *some* of these populated" canonical fields).
GLOBAL_CANONICAL_FIELDS = [
    "tipo_peca",
    "partes",
    "pedidos",
    "valores",
    "fatos_relevantes",
]


def _is_populated(value) -> bool:
    """Treat None, empty string, empty list, empty dict as not populated."""
    if value is None:
        return False
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return False
    return True


def evaluate(analyzed: dict) -> dict:
    """Evaluate the content quality of an analyzed.json document.

    Returns a dict with `warnings` (list of human-readable strings),
    `stats` (per-field populated counts), and `total_chunks`.
    """
    chunks = analyzed.get("chunks", []) or []
    total = len(chunks)
    warnings: list[str] = []
    stats: dict[str, dict] = {}

    if total == 0:
        warnings.append("WARN: analyzed.json has zero chunks — extraction or chunking failed")
        return {"warnings": warnings, "stats": stats, "total_chunks": 0}

    # Count populated rate for each global canonical field across chunks
    for field in GLOBAL_CANONICAL_FIELDS:
        populated = sum(1 for c in chunks if _is_populated(c.get(field)))
        stats[field] = {"populated": populated, "total": total}
        if populated == 0:
            warnings.append(
                f"WARN: 0/{total} chunks têm campo {field!r} populado — "
                f"análise per-chunk pode estar incompleta (SKILL.md Step 3)"
            )
        elif populated < total / 2 and total >= 4:
            warnings.append(
                f"WARN: apenas {populated}/{total} chunks têm campo {field!r} populado"
            )

    # Per-piece-type expected-field check
    for i, chunk in enumerate(chunks):
        tipo = chunk.get("tipo_peca")
        if not tipo:
            continue
        expected = EXPECTED_FIELDS_BY_TYPE.get(tipo.upper(), [])
        for field in expected:
            if not _is_populated(chunk.get(field)):
                warnings.append(
                    f"WARN: chunk[{i}] tipo_peca={tipo!r} sem campo esperado {field!r}"
                )

    # Schema version sanity
    if not analyzed.get("schema_version") and not analyzed.get("analysis_version"):
        warnings.append(
            "WARN: analyzed.json sem schema_version/analysis_version — "
            "marcação de versão recomendada"
        )

    return {"warnings": warnings, "stats": stats, "total_chunks": total}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Non-blocking content quality check for analyzed.json",
    )
    parser.add_argument("--input", "-i", required=True, help="Path to analyzed.json")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any warning is emitted (default: always exit 0)",
    )
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        analyzed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        return 2

    result = evaluate(analyzed)

    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        if not result["warnings"]:
            print(f"[OK] content quality check passed ({result['total_chunks']} chunks)")
        else:
            print(
                f"[CONTENT QUALITY] {len(result['warnings'])} warning(s) "
                f"in {result['total_chunks']} chunk(s):",
                file=sys.stderr,
            )
            for w in result["warnings"]:
                print(f"  - {w}", file=sys.stderr)

    if args.strict and result["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
