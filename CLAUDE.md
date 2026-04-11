# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Forensic legal analysis skill for Claude Code — the definitive tool for Brazilian judicial proceedings (processos judiciais). Extracts text from PDF court filings, chunks them by legal piece (peça processual), analyzes each piece structurally, detects contradictions, tracks arguments across judicial instances, calculates CPC-compliant deadlines, scores litigation risk, and exports to Obsidian vaults or structured JSON.

This repository IS the skill directory. Clone it to `~/.claude/skills/juriscan` and it works immediately.

## Commands

```bash
# Install (one time)
./install.sh

# Run all tests
pip install -r requirements.txt
python -m pytest tests/ -v

# Scripts (all in scripts/)
python3 scripts/extract_and_chunk.py --input <pdf> --output <dir>
python3 scripts/integrity_check.py --input <dir>
python3 scripts/prazo_calculator.py --date 2025-03-15 --tipo contestação --state SP
python3 scripts/instance_tracker.py --analysis <analyzed.json> --output <instances.json>
python3 scripts/legacy/contradiction_report.py --analysis <analyzed.json> --output <contradictions.json>
python3 scripts/legacy/risk_scorer.py --analysis <analyzed.json> --output <risk.json>
python3 scripts/schema_validator.py --input <analyzed.json>
python3 scripts/obsidian_export.py --analysis <analyzed.json> --output <vault_dir>

# Agents pipeline (opt-in during transition; see docs/architecture.md)
python3 scripts/agent_io.py new-run
python3 scripts/agent_io.py validate --agent <role> --input <output.json>
python3 scripts/persist_chunks.py --segmenter-output <seg.json> --raw-text <raw.txt> --output-dir <out>
python3 scripts/enrich_deterministic.py --input <pieces.json> --output <enriched.json>
python3 scripts/confidence_rules.py --synthesis <s.json> --auditor <a.json> --output <final.json>
python3 scripts/finalize.py --input <analyzed.json> --output <final.json>
python3 scripts/report_metrics.py --all-runs --enforce
python3 scripts/migrate_v2_to_v3.py --input <v2.json> --output <v3.json>
```

## Architecture

**Principle: Claude = semantic analysis engine. Python = deterministic data wrangling.**

### Two pipelines (during transition)

1. **Legacy** (`--pipeline=legacy`, current default) — 10-stage deterministic
   pipeline from `extract_and_chunk.py` through regex chunking, per-chunk analysis
   by Claude via prompt templates, and scripts/legacy for contradiction_report
   and risk_scorer.
2. **Agents** (`--pipeline=agents`, opt-in) — hybrid pipeline where semantic
   reasoning is delegated to native Claude Code subagents in `.claude/agents/`
   orchestrated by SKILL.md via the Task tool. Python still owns every
   deterministic computation (dates, BRL, CNJ, prazos CPC, schema, export).
   See `docs/architecture.md` for the full flow and `docs/subagents.md` for
   per-subagent contracts.

### Legacy 10-Stage Pipeline

```
PDF → [1] Extraction → [2] Integrity Check → [3] Chunking → [4] Per-Chunk Analysis (Claude)
→ [5] Schema Validation → [6] Cross-Synthesis (Claude) → [7] Prazo Calculation
→ [8] Risk Scoring → [9] Output → [10] Obsidian Export
```

### Agents Pipeline (see SKILL.md § Agents Pipeline)

```
PDF → extract_pdf → juriscan-segmenter → persist_chunks → juriscan-parser (parallel)
    → enrich_deterministic → [juriscan-advogado-autor × juriscan-advogado-reu × juriscan-auditor-processual] (parallel)
    → juriscan-verificador → juriscan-sintetizador → confidence_rules → finalize → obsidian_export
```

The agents pipeline uses **zero** `ANTHROPIC_API_KEY` — it runs on the user's
Claude Code subscription. Every subagent output is JSON-schema-validated by
`scripts/agent_io.py validate` and logged to an append-only audit trail at
`.juriscan/audit/<run_id>.jsonl`. See `docs/operations.md` for troubleshooting.

### Script Responsibilities

| Script | Purpose |
|---|---|
| `extract_and_chunk.py` | PDF extraction (pdftotext→pypdf→OCR), intelligent chunking by legal piece, OCR confidence, page mapping |
| `integrity_check.py` | OCR quality scoring, metadata anomaly detection, page gap detection |
| `prazo_calculator.py` | CPC Art. 219-232 deadline calculation, feriados forenses, recesso forense |
| `instance_tracker.py` | Classify pieces by judicial instance (1ª inst→TJ→STJ→STF), argument evolution tracking |
| `contradiction_report.py` | Structural contradiction detection (values, dates, facts, jurisprudence) |
| `risk_scorer.py` | Procedural risk, merit indicators, monetary exposure scoring |
| `schema_validator.py` | Validates JSON output against `references/output_schema.json` |
| `obsidian_export.py` | Generates Obsidian vault with 7 main views + piece notes + stub notes |

### Utils (`scripts/utils/`)

| Module | Purpose |
|---|---|
| `dates.py` | Brazilian date parsing (DD/MM/YYYY, written Portuguese, ISO), piece-type-aware primary date extraction |
| `monetary.py` | BRL value extraction/normalization (R$ format, written forms, multipliers) |
| `filenames.py` | Collision-safe filename generation with `FilenameRegistry` |
| `cnj.py` | CNJ process number parsing, check digit validation, court name resolution |

### Reference Data (`references/`)

| File | Purpose |
|---|---|
| `output_schema.json` | JSON Schema v2 — full output specification with all analysis fields |
| `prompt_templates.md` | All 7 prompt templates used by Claude during analysis |
| `piece_type_taxonomy.json` | 27 piece types with phase, polo, instance, expected fields |
| `cpc_prazos.json` | 14 standard CPC deadlines with exceptions (Fazenda, JEC, Defensoria) |
| `feriados_forenses.json` | National + mobile (Easter-based) + state court holidays (SP,RJ,MG,RS,PR,SC,BA,PE) |
| `brazilian_legal_entities.md` | Courts, electronic systems, legislation codes, citation regex patterns |
| `appellate_structure.md` | Instance hierarchy, detection patterns, piece classification rules |
| `binding_precedents.md` | Binding precedent types (SV, IRDR, IAC, RG, Rep.) with detection regex |
| `risk_scoring_rubric.md` | Risk scoring rubric: procedural, merit, monetary dimensions |

## Key Design Decisions

- **Chunk by legal piece, not by page** — core invariant. Brazilian filings contain multiple procedural pieces that are semantic units.
- **Deduplication threshold: 200 chars** — close regex matches within 200 chars are deduplicated.
- **Fragments under 50 chars skipped** — noise from headers.
- **ISO 8601 internally, DD/MM/YYYY for display** — eliminates DD/MM vs MM/DD ambiguity.
- **Piece-type-aware date extraction** — SENTENÇA uses "Publique-se" date, ACÓRDÃO uses session date, PETIÇÃO uses protocol date.
- **OCR confidence per chunk** — heuristic based on vowel ratios, legal term density, encoding quality.
- **Recesso forense Dec 20–Jan 20** — all prazo calculations suspend during this period (CPC Art. 220).
- **Fact divergence detection defers to Claude** — script flags structural contradictions, semantic comparison via prompt template.

## Domain Context

- All legal terminology and user-facing text in **Brazilian Portuguese**.
- Process numbers follow **CNJ format**: `NNNNNNN-DD.YYYY.J.TT.OOOO` (Res. 65/2008).
- Judicial instances: 1ª Instância (Varas) → TJ/TRF (Câmaras) → STJ (Turmas) → STF (Plenário/Turmas).
- Binding precedents: Súmula Vinculante, IRDR, IAC, Repercussão Geral, Recurso Repetitivo.

## Dependencies

- Python 3.10+ (uses `X | Y` union syntax)
- System: `poppler-utils` (pdftotext, pdfinfo, pdftoppm), `tesseract-ocr` + `tesseract-ocr-por`
- Python: `pip install -r requirements.txt` (pypdf, pytesseract, Pillow, jsonschema, pytest)
