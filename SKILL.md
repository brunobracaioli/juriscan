---
name: juriscan
description: "Análise forense de processos judiciais brasileiros. Extrai, classifica e cruza peças processuais, detecta contradições, calcula prazos CPC e gera relatórios de risco com exportação para Obsidian."
allowed-tools: Read Bash(python3 *) Bash(pip install *) Bash(pdftotext *) Bash(pdfinfo *) Glob Grep
---

# JuriScan

Análise sênior e forense de processos judiciais brasileiros de qualquer tamanho. Extrai, estrutura, mapeia contradições, rastreia argumentos entre instâncias, calcula prazos CPC, avalia riscos e exporta para Obsidian.

## Setup (primeira execução)

Antes de qualquer script, determine o diretório desta skill e garanta as dependências:

```bash
# Detectar diretório da skill
SKILL_DIR="$(dirname "$(find ~/.claude/skills -name 'SKILL.md' -path '*/juriscan/*' 2>/dev/null | head -1)" 2>/dev/null)"
[ -z "$SKILL_DIR" ] && SKILL_DIR="$(find . -name 'SKILL.md' -path '*/juriscan/*' -exec dirname {} \; 2>/dev/null | head -1)"
echo "Skill directory: $SKILL_DIR"

# Instalar dependências Python (se necessário)
python3 -c "import pypdf, jsonschema" 2>/dev/null || pip install pypdf pytesseract Pillow jsonschema
```

Use `$SKILL_DIR` como prefixo para todos os caminhos de scripts e referências abaixo.

## Architecture

```
PDF(s) → [1] Extração → [2] Integridade → [3] Chunking → [4] Análise por Chunk
→ [5] Validação → [6] Síntese Cruzada → [7] Prazos → [8] Risco → [9] Output → [10] Obsidian
```

## Step-by-Step Execution

### Step 1: Extraction & Inventory

```bash
python3 $SKILL_DIR/scripts/extract_and_chunk.py --input <pdf_path> --output <analysis_dir>/
```

Se o script não estiver disponível, extrair manualmente:
```bash
pdfinfo <pdf_path>
pdftotext -layout <pdf_path> <analysis_dir>/full_text.txt
```

### Step 2: Integrity Check

```bash
python3 $SKILL_DIR/scripts/integrity_check.py --input <analysis_dir>/
```

Flag chunks com OCR confidence < 0.7 para re-extração via vision.

### Step 3: Intelligent Chunking

Executado automaticamente pelo Step 1. Divide por **PEÇA PROCESSUAL** (não por página) usando 25+ patterns regex. Tipos detectados em [piece_type_taxonomy.json](references/piece_type_taxonomy.json).

Output: `index.json` + `chunks/*.txt`

### Step 4: Per-Chunk Analysis

Para cada chunk, usar o prompt **Análise Per-Chunk** de [prompt_templates.md](references/prompt_templates.md#1-análise-per-chunk-extração-estruturada).

Para chunks ACÓRDÃO, também usar **Parsing Tripartite** de [prompt_templates.md](references/prompt_templates.md#3-parsing-tripartite-de-acórdão).

Referência de entidades: [brazilian_legal_entities.md](references/brazilian_legal_entities.md).

### Step 5: Schema Validation

```bash
python3 $SKILL_DIR/scripts/schema_validator.py --input <analysis_dir>/analyzed.json
```

Se falhar, re-prompt Claude com os erros. Repetir até válido.

### Step 6: Cross-Synthesis

**6a. Contradições:**
```bash
python3 $SKILL_DIR/scripts/contradiction_report.py --analysis <analysis_dir>/analyzed.json --output <analysis_dir>/contradictions.json
```
Complementar com prompt **Detecção de Contradições** de [prompt_templates.md](references/prompt_templates.md#2-detecção-de-contradições).

**6b. Instâncias:**
```bash
python3 $SKILL_DIR/scripts/instance_tracker.py --analysis <analysis_dir>/analyzed.json --output <analysis_dir>/instances.json
```
Complementar com prompt **Rastreamento por Instância** de [prompt_templates.md](references/prompt_templates.md#4-rastreamento-de-argumentos-por-instância).

**6c. Precedentes Vinculantes:**
Usar prompt **Alinhamento de Precedentes** de [prompt_templates.md](references/prompt_templates.md#5-alinhamento-de-precedentes-vinculantes). Referência: [binding_precedents.md](references/binding_precedents.md).

### Step 7: Prazo Calculation

```bash
python3 $SKILL_DIR/scripts/prazo_calculator.py --analysis <analysis_dir>/analyzed.json --output <analysis_dir>/prazos.json --state SP
```

Python puro (CPC Art. 219-232). Dados: [cpc_prazos.json](references/cpc_prazos.json), [feriados_forenses.json](references/feriados_forenses.json).

### Step 8: Risk Scoring

```bash
python3 $SKILL_DIR/scripts/risk_scorer.py --analysis <analysis_dir>/analyzed.json --output <analysis_dir>/risk.json
```

Complementar com prompt **Avaliação de Risco** de [prompt_templates.md](references/prompt_templates.md#6-avaliação-de-risco-litigioso). Rubrica: [risk_scoring_rubric.md](references/risk_scoring_rubric.md).

### Step 9: Consolidate Output

Merge todos os resultados em `analyzed.json` conforme [output_schema.json](references/output_schema.json). Re-validar com Step 5.

### Step 10: Obsidian Export

```bash
python3 $SKILL_DIR/scripts/obsidian_export.py --analysis <analysis_dir>/analyzed.json --output <vault_dir>/
```

Gera vault com 7 views: `_INDEX`, `_TIMELINE`, `_CONTRADIÇÕES`, `_ENTIDADES`, `_RISCO`, `_INSTÂNCIAS`, `_PRAZOS`, mais notas por peça, legislação e jurisprudência.

## Edge Cases

- **500+ páginas**: Chunk primeiro, analise em batches de 5-10 peças, persista JSON incrementalmente
- **PDFs de tribunais (PJe, e-SAJ, PROJUDI)**: Headers repetitivos são removidos automaticamente
- **PDFs escaneados**: OCR fallback via pytesseract; flag chunks de baixa confiança para re-extração via vision
- **Múltiplos volumes**: Trate cada volume separadamente, concatene chunks antes da síntese cruzada
- **Multi-instância**: Instance tracker lida com 1ª instância → TJ → STJ → STF automaticamente

## Dependencies

- Python 3.10+ | poppler-utils (pdftotext, pdfinfo) | tesseract-ocr (opcional, para OCR)
- Python: pypdf, pytesseract, Pillow, jsonschema

## Reference Files

- [references/output_schema.json](references/output_schema.json) — JSON Schema v2
- [references/prompt_templates.md](references/prompt_templates.md) — Todos os prompt templates
- [references/brazilian_legal_entities.md](references/brazilian_legal_entities.md) — NER reference
- [references/piece_type_taxonomy.json](references/piece_type_taxonomy.json) — Metadata de tipos de peça
- [references/cpc_prazos.json](references/cpc_prazos.json) — Regras de prazos CPC
- [references/feriados_forenses.json](references/feriados_forenses.json) — Feriados forenses
- [references/appellate_structure.md](references/appellate_structure.md) — Hierarquia de instâncias
- [references/binding_precedents.md](references/binding_precedents.md) — Precedentes vinculantes
- [references/risk_scoring_rubric.md](references/risk_scoring_rubric.md) — Rubrica de risco
