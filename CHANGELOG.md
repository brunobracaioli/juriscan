# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.1] - 2026-04-11

Quality patch addressing a friction surfaced by the first real-world smoke
test of v3.0.0 in a fresh-user install. The legacy pipeline previously
allowed Claude to take a shortcut during Step 3 (Per-Chunk Analysis) by
writing a Python helper script that hardcoded a partial set of enrichments,
producing an `analyzed.json` skeleton with `tipo_peca: null`, `partes: null`,
`pedidos: []`, `valores: null` in every chunk. The schema validator passed
because all those fields are technically optional, but the resulting
Obsidian vault and downstream `risk.json` / `instances.json` were empty
shells.

### Added

- `scripts/content_quality_check.py` — non-blocking sanity check that
  emits stderr WARNs when canonical fields are suspiciously empty across
  chunks. Default exit 0; pass `--strict` for exit 1 on warnings.
- 21 tests in `tests/test_content_quality_check.py`

### Changed

- `SKILL.md` Step 3 (Per-Chunk Analysis) tightened with:
  - Explicit ban on writing helper Python scripts that hardcode enrichments
  - Mandatory minimum-fields table per `tipo_peca`
  - Two explicit strategies (split semântico vs peça dominante) when the
    regex chunker groups multiple peças in one file (issue #3)
  - New Step 4 wires `content_quality_check.py` after `schema_validator.py`
    so the orchestrator sees warnings and can re-do Step 3

### Documentation

- CHANGELOG.md updated (this file)

## [3.0.0] - 2026-04-11

First stable release of the v3 hybrid architecture. Pipeline `legacy` is the
default and is validated in field. Pipeline `agents` is beta opt-in via
`--pipeline=agents`.

### Added

- Pipeline `--pipeline=agents` (beta opt-in) with 8 native Claude Code subagents
  - `juriscan-segmenter` (haiku) — semantic chunking with coverage invariants
  - `juriscan-parser` (haiku) — per-chunk field extraction, parallel via Task tool
  - `juriscan-advogado-autor` (sonnet) — pole-ativo dialectical analysis
  - `juriscan-advogado-reu` (sonnet) — pole-passivo dialectical analysis
  - `juriscan-auditor-processual` (sonnet) — impartial 6-item checklist with mandatory art. 942 CPC detection
  - `juriscan-verificador` (haiku) — jurisprudence verification via WebFetch with whitelist enforcement
  - `juriscan-sintetizador` (sonnet) — preservation-invariant final synthesis
  - `juriscan-echo` (haiku) — selftest plumbing
- Schema v3 (`references/output_schema_v3.json`) — superset of v2 with `perspectives`, `auditor_findings`, `verifications`, `monetary_recalculations`, `dissensos`, `process_state`, `audit_trail_uri`
- Append-only audit trail at `.juriscan/audit/<run_id>.jsonl` capturing every Task invocation with `latency_ms`, `schema_valid`, `error`
- `scripts/agent_io.py` — glue CLI between SKILL.md orchestrator and subagents (`new-run`, `validate`, `log`, `extract-field`)
- `scripts/audit.py` + `scripts/cleanup_audit.py` — audit trail infrastructure with 90-day TTL
- `scripts/persist_chunks.py` — validates segmenter output and writes physical chunks with 4 invariants
- `scripts/enrich_deterministic.py` — re-normalizes LLM output with `utils/dates`, `utils/monetary`, `utils/cnj`; raises if mismatch rate > 10%
- `scripts/confidence_rules.py` — preservation invariant + downgrade rules for unverified citations
- `scripts/finalize.py` — Decimal-based monetary recalculations (Lei 14.905/2024 juros split, honorários post-reform)
- `scripts/migrate_v2_to_v3.py` — additive-only v2 → v3 migration
- `scripts/report_metrics.py` — per-subagent latency p50/p95/max + budget gate (`--enforce`)
- `references/whitelist_fontes.json` — categorized authoritative hosts for verificador
- `references/agent_schemas/*.json` — strict JSON Schemas (Draft-07) for each subagent output
- Golden fixtures: `processo_01_sintetico_simples` (baseline) and `processo_02_sintetico_art942` (Phase 3 invariant gate)
- Phase 3 hard gate: `auditor_findings[].descricao` must contain literal tokens `ampliação`, `colegiado`, `maioria` for art. 942 detections
- Post-hoc whitelist enforcement: verificador outputs with `source_url` outside `whitelist_fontes.json` are rejected at validation time
- Preservation invariant: sintetizador cannot drop auditor findings (`len(synthesis.auditor_findings) >= len(auditor_input.findings)`)
- `docs/architecture.md`, `docs/subagents.md`, `docs/operations.md`, `docs/subagent_contract.md`
- GitHub Actions CI workflow (matrix Python 3.10 / 3.12, poppler/tesseract, full pytest, contract smoke test)

### Changed

- `scripts/contradiction_report.py` and `scripts/risk_scorer.py` moved to `scripts/legacy/` with `DeprecationWarning`
- `scripts/prazo_calculator.py` accepts optional `process_state` parameter; switches to CPC art. 523 cumprimento voluntário when `transito_em_julgado`, suspends when `suspenso`, returns None when `arquivado`
- `SKILL.md` rewritten with dual-mode dispatch (`--pipeline=legacy` / `--pipeline=agents`), agents pipeline orchestration, and subagent contract section

### Fixed

- `risk_scorer.likely_range` now guarantees `min ≤ likely ≤ max` via `sorted()` + assertion (Phase 1.1)
- `contradiction_report` no longer marks legitimate partial reform as `VALOR_INCONSISTENTE`; emits `REFORMA_PARCIAL` note in `instance_tracking` instead (Phase 1.3)
- `prazo_calculator --tipo` is now accent-insensitive — `apelacao` resolves to `apelação` via `unicodedata.NFD` normalization (Phase A.1)
- `prazo_calculator --analysis` no longer drops prazos silently — emits per-prazo WARN to stderr and exits 1 when input had prazos but every single one was dropped (Phase A.2)
- `SKILL.md` `SKILL_DIR` resolution handles symlinked installs correctly (commit `9641e86`)
- `SKILL.md` Step 3 explicitly preserves `chunk_file` when merging semantic fields into chunks (commit `9641e86`)

### Documentation

- README updated with "Status & Pipelines" section explaining legacy (stable default) vs agents (beta opt-in)
- README "Limitações conhecidas" section listing honest constraints
- CHANGELOG.md created (this file)

### Migration notes

Backwards compatible — schema v2 outputs continue to validate against `references/output_schema_v2.json` indefinitely. To upgrade an existing v2 `analyzed.json` to v3:

```bash
python3 scripts/migrate_v2_to_v3.py --input old.json --output new.json
```

## [3.0.0-rc2] - 2026-04-11

### Fixed

- `SKILL.md` `SKILL_DIR` resolution for installs via symlink (find without `-L` did not traverse symlinks)
- `SKILL.md` Step 3 explicit recipe for merging semantic fields into existing `chunks[]` without losing `chunk_file`

## [3.0.0-rc1] - 2026-04-11

### Added

- Complete v2 → v3 migration (Phases 0-7 of the implementation plan)

## [2.x] and earlier

Pipeline legacy established. See git log before tag `v3.0.0-rc1`.
