# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.1.1] - 2026-04-11

Patch fix release after the v3.1.0-legacy smoke test exposed 3 concrete
bugs. The centerpiece (REPORT.md) and per-chunk file pattern worked, but
the split-semantic index contract was broken and the pieces table was out
of chronological order. This patch closes all 3.

### Fixed

- **merge_chunk_analysis.py renumber contract** — string indices from
  split-semantic per-chunk files (`"1a"`, `"2a"`, etc.) were passed through
  to `analyzed.json`, where `output_schema_v2.json` rejects non-integer
  indices. Result: `schema_validator.py` failed on first try and Claude
  wrote a one-off Python renumber fix-up (a shadow of the v3.0.1 anti-pattern).
  Now `merge_chunk_analysis.py` renumbers ALL entries to sequential integers
  (0..N-1) at the end of the merge pass, preserving the original user-facing
  index as `original_index` for debugging.
- **merge_chunk_analysis.py suffixed ordering** — suffixed children
  (`01a`, `01b`) were appended at the end of the merged list instead of
  being inserted right after their parent. When a physical chunk contained
  a sequence of pieces (laudo → sentença → apelação → acórdão), the
  resulting `analyzed.chunks[]` order was scrambled. Now suffixed children
  are placed immediately after their parent, producing natural
  chronological flow.
- **generate_report.py chronological pieces table** — `render_pieces_table()`
  now sorts chunks by `primary_date` ascending (with fallback to `index`
  when date is missing or unparseable). Even if the input `analyzed.json`
  has entries out of order, the rendered table is always chronological.
- **generate_report.py chronological timeline** — `render_timeline()` now
  also sorts by date before emitting the Mermaid gantt.

### Changed

- **SKILL.md Step 10 rewritten with LITERAL ONLY rule** — the v3.1.0-legacy
  smoke test showed Claude enriched his final response with a
  "Conclusão estratégica" paragraph that was NOT in `REPORT.md`, breaking
  reproducibility. Step 10 now has absolute, non-negotiable rules:
  "Cole o conteúdo exato como sua mensagem ao usuário. Caractere por caractere.
  Zero edições. Zero adições. Zero reformatação." Explicit ban on
  "Conclusão estratégica", "Observações finais", expanded summaries,
  re-tabulation, and decorative emojis. Only allowed addition: one line
  with file paths at the very end.

### Tests

- 406 → 414 passed (+8 new tests):
  - `test_merge_renumbers_to_sequential_integers`
  - `test_merge_split_semantic_inserts_after_parent`
  - `test_merge_preserves_original_index_for_debugging`
  - `test_merge_multiple_split_children_alphabetical_order`
  - `test_merge_output_passes_integer_index_contract`
  - `test_render_pieces_table_sorts_chronologically`
  - `test_render_pieces_table_missing_date_sorts_last`
  - `test_render_timeline_sorts_chronologically`

## [3.1.0-legacy] - 2026-04-11

**"The Uau Release"** — A transformação da saída do pipeline legacy de "6 JSONs + vault Obsidian + narrativa verbal do Claude" para **"um comando → um relatório executivo markdown, reproduzível, com citações verbatim, que fica bonito no terminal"**. Os dados já estavam corretos no v3.0.1 — o que mudou foi a apresentação e o processo de construção.

### Added

- `scripts/generate_report.py` — gerador de `REPORT.md` executivo consolidando
  `analyzed.json` + `contradictions.json` + `prazos.json` + `risk.json` +
  `recommendations.json` em um único documento markdown com:
  - Cabeçalho com metadados do processo e badge de risco
  - Resumo executivo gerado a partir dos campos estruturados
  - Caixas de alerta críticos (Art. 942 CPC, Lei 14.905/2024, prazos urgentes)
  - Tabela de peças processuais
  - Contradições agrupadas por impacto com citações verbatim das peças fonte
  - Avaliação de risco com breakdown por dimensão (processual/mérito/monetário)
  - Recomendações estratégicas por polo ordenadas por prioridade, cada uma
    com `evidence_quote` verbatim obrigatória
  - Cronograma Mermaid gantt (quando ≥ 3 peças com datas)
  - Dashboard de prazos
  - 30 testes unit + integration
- `scripts/analyzed_init.py` — inicializa skeleton de `analyzed.json` a partir
  de `index.json`, preservando campos técnicos (`chunk_file`, `char_count`,
  `page_range`, etc.) e marcando chunks com `_pending_analysis: true`
- `scripts/merge_chunk_analysis.py` — consolida arquivos per-chunk
  (`chunks/NN.analysis.json`) no `analyzed.json`, com validação via schema
  Draft-07, suporte a split-semantic (múltiplas peças num arquivo físico) e
  detecção de scripts helper anti-pattern (`build_analyzed.py`)
- `scripts/finalize_legacy.py` — recálculo Lei 14.905/2024 standalone para o
  pipeline legacy. Varre `chunks[].valores.condenacao` diretamente, detecta
  condenações cruzando o marco de 30/08/2024 e adiciona
  `monetary_recalculations[]` com juros pré-cutover calculados (1% a.m.)
- `references/chunk_analysis_schema.json` — schema Draft-07 strict
  (`additionalProperties: false`) para arquivos per-chunk, com enum de
  `tipo_peca` vindo de `piece_type_taxonomy.json`
- `references/agent_schemas/recommendations_output.json` — schema para
  `recommendations.json` com `polo`, `priority`, `action`, `fundamentacao`,
  `evidence_quote` (obrigatório), `evidence_chunk_ref`, `deadline_days`,
  `deadline_basis`, `impact`, `confidence`
- `references/prompt_templates.md` seção 7 "Geração de Recomendações
  Estratégicas" — prompt com regras explícitas, incluindo obrigatoriedade de
  `evidence_quote` verbatim e recomendação ALTA compulsória quando há art. 942
  detectado
- Enforcement de citation grounding em `content_quality_check.py`:
  `_check_art_942_grounding()` exige citation_spans com tokens verbatim
  (`ampliação`, `colegiado`, `maioria`, `vencido`) quando ACÓRDÃO por maioria
  reforma mérito
- Plano de retry per-chunk em `content_quality_check.py`: novo campo
  `chunks_needing_retry[]` no output JSON identificando exatamente qual chunk
  precisa ser re-analisado e quais campos estão faltando; flag
  `--per-chunk-retry-plan` imprime plano legível
- Agent type `recommendations` registrado em `scripts/agent_io.py` com
  validação via `agent_io.py validate --agent recommendations`

### Changed

- **SKILL.md Step 3 reestruturado** — causa raiz do helper-script anti-pattern
  (`build_analyzed.py` do v3.0.1) endereçada por mudança de workflow, não por
  mais proibições. O novo fluxo tem 3 sub-steps:
  1. `analyzed_init.py` cria skeleton com campos técnicos
  2. Para cada chunk: Read + Write `chunks/NN.analysis.json` (um por chunk)
  3. `merge_chunk_analysis.py` consolida com validação strict
- **SKILL.md Step 4** — `content_quality_check.py --strict --per-chunk-retry-plan`
  é bloqueante. Retry loop direcionado: Claude vê exatamente quais chunks
  refazer, max 2 iterações
- **SKILL.md Step 8.5** (novo) — `finalize_legacy.py --inplace` detecta e
  aplica recálculo Lei 14.905/2024 automaticamente
- **SKILL.md Step 9a** (novo) — geração de `recommendations.json` após risk
  scoring, via prompt template dedicado
- **SKILL.md Step 9b** (novo) — `generate_report.py` produz `REPORT.md`
- **SKILL.md Step 10 reescrito** — a resposta final do Claude ao usuário **é**
  literalmente o conteúdo de `REPORT.md`, não uma paráfrase. Regra explícita:
  "não re-resuma, não parafraseie — o relatório é reproduzível e auditável"
- `content_quality_check.py` — `EXPECTED_FIELDS_BY_TYPE["ACÓRDÃO"]` corrigido
  de `acordao_detail` (campo legacy incorreto) para `acordao_structure`
  (campo canônico no schema v2)

### Fixed

- `generate_report.py` renderização de `monetary_recalculations` agora
  suporta ambos os shapes: `{periodo_1, periodo_2}` (finalize.py agents) e
  `{periods: [...]}` (finalize_legacy.py)
- `generate_report.py` chunk_ref=0 falsy bug: referências de peça usando
  `.get("chunk_ref") or ...` agora usam `is None` check explícito,
  preservando chunk_ref=0 como referência válida

### Documentation

- CHANGELOG.md (esta entrada)
- Plano detalhado em Part III do spec-driven plan
  (`~/.claude/plans/fluffy-honking-graham.md`)

### Migration notes

Retrocompat total. Schema v2 continua válido. `analyzed.json` antigos
continuam abrindo no `obsidian_export.py`. Pipeline agents não foi tocado.

Para beneficiar-se do novo relatório executivo em análises antigas, rode:
```bash
python3 scripts/generate_report.py \
  --analyzed old-output/analyzed.json \
  --contradictions old-output/contradictions.json \
  --prazos old-output/prazos.json \
  --risk old-output/risk.json \
  --output old-output/REPORT.md
```


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
