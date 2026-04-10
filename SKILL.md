---
name: juriscan
description: "Análise forense de processos judiciais brasileiros. Extrai, classifica e cruza peças processuais, detecta contradições, calcula prazos CPC e gera relatórios de risco com exportação para Obsidian. Use quando mencionar: processo judicial, petição, sentença, acórdão, contradições, prazos, timeline, análise forense, Obsidian."
allowed-tools: Read Bash(python3 *) Bash(pip install *) Bash(pdftotext *) Bash(pdfinfo *) Glob Grep
---

# JuriScan

## Quick Run

Quando o usuário invocar `/juriscan <caminho_do_pdf>` ou pedir para analisar um processo, execute TODO o pipeline abaixo em sequência, sem parar para perguntar. O PDF pode estar em qualquer diretório — o usuário passa o caminho.

Se o usuário não passar um caminho, pergunte: "Qual o caminho do PDF do processo?"

**Fluxo completo automático:**

1. Resolver `SKILL_DIR` e garantir dependências (Setup)
2. Criar diretório de análise ao lado do PDF: `<pdf_dir>/juriscan-output/`
3. Executar Steps 1-10 em sequência
4. No final, informar ao usuário:
   - Resumo executivo do processo (3-5 frases)
   - Quantas peças encontradas
   - Contradições detectadas (quantidade e as mais graves)
   - Prazos calculados (se houver)
   - Nível de risco
   - Onde estão os arquivos de saída
   - Se quiser Obsidian: "O vault está em `<output>/obsidian/` — abra essa pasta no Obsidian como vault"

---

## Setup

Executar uma vez no início da sessão:

```bash
SKILL_DIR="$(dirname "$(find ~/.claude/skills -name 'SKILL.md' -path '*/juriscan/*' 2>/dev/null | head -1)" 2>/dev/null)"
[ -z "$SKILL_DIR" ] && SKILL_DIR="$(find . -name 'SKILL.md' -path '*/juriscan/*' -exec dirname {} \; 2>/dev/null | head -1)"

python3 -c "import pypdf, jsonschema" 2>/dev/null || pip install pypdf pytesseract Pillow jsonschema
```

---

## Step-by-Step Pipeline

### Step 1: Extraction & Chunking

```bash
python3 $SKILL_DIR/scripts/extract_and_chunk.py --input <pdf_path> --output <output_dir>/
```

Extrai texto do PDF (pdftotext → pypdf → OCR) e divide por **peça processual** (27 tipos detectados). Output: `index.json` + `chunks/*.txt`.

### Step 2: Integrity Check

```bash
python3 $SKILL_DIR/scripts/integrity_check.py --input <output_dir>/
```

Verifica OCR quality, anomalias de metadata, lacunas de páginas. Flag chunks com confidence < 0.7.

### Step 3: Per-Chunk Analysis

Para **cada chunk** em `chunks/`, ler o arquivo e analisar usando o prompt **Análise Per-Chunk** de [prompt_templates.md](references/prompt_templates.md#1-análise-per-chunk-extração-estruturada).

Para chunks ACÓRDÃO, também usar **Parsing Tripartite** de [prompt_templates.md](references/prompt_templates.md#3-parsing-tripartite-de-acórdão).

Referência de entidades: [brazilian_legal_entities.md](references/brazilian_legal_entities.md).
Campos esperados por tipo: [piece_type_taxonomy.json](references/piece_type_taxonomy.json).

Salvar resultado consolidado em `<output_dir>/analyzed.json`.

### Step 4: Schema Validation

```bash
python3 $SKILL_DIR/scripts/schema_validator.py --input <output_dir>/analyzed.json
```

Se falhar, corrigir o JSON e re-validar. Repetir até válido.

### Step 5: Cross-Synthesis

**5a. Contradições:**
```bash
python3 $SKILL_DIR/scripts/contradiction_report.py --analysis <output_dir>/analyzed.json --output <output_dir>/contradictions.json
```
Complementar com prompt **Detecção de Contradições** de [prompt_templates.md](references/prompt_templates.md#2-detecção-de-contradições) para análise semântica.

**5b. Instâncias:**
```bash
python3 $SKILL_DIR/scripts/instance_tracker.py --analysis <output_dir>/analyzed.json --output <output_dir>/instances.json
```
Complementar com prompt **Rastreamento por Instância** de [prompt_templates.md](references/prompt_templates.md#4-rastreamento-de-argumentos-por-instância).

**5c. Precedentes Vinculantes:**
Usar prompt **Alinhamento de Precedentes** de [prompt_templates.md](references/prompt_templates.md#5-alinhamento-de-precedentes-vinculantes). Referência: [binding_precedents.md](references/binding_precedents.md).

### Step 6: Prazo Calculation

```bash
python3 $SKILL_DIR/scripts/prazo_calculator.py --analysis <output_dir>/analyzed.json --output <output_dir>/prazos.json
```

Python puro (CPC Art. 219-232). Dados: [cpc_prazos.json](references/cpc_prazos.json), [feriados_forenses.json](references/feriados_forenses.json).

### Step 7: Risk Scoring

```bash
python3 $SKILL_DIR/scripts/risk_scorer.py --analysis <output_dir>/analyzed.json --output <output_dir>/risk.json
```

Complementar com prompt **Avaliação de Risco** de [prompt_templates.md](references/prompt_templates.md#6-avaliação-de-risco-litigioso). Rubrica: [risk_scoring_rubric.md](references/risk_scoring_rubric.md).

### Step 8: Consolidate

Merge contradictions, instances, prazos e risk no `analyzed.json` final. Re-validar com `schema_validator.py`.

### Step 9: Obsidian Export

```bash
python3 $SKILL_DIR/scripts/obsidian_export.py --analysis <output_dir>/analyzed.json --output <output_dir>/obsidian/
```

Gera vault com 7 views: `_INDEX`, `_TIMELINE`, `_CONTRADIÇÕES`, `_ENTIDADES`, `_RISCO`, `_INSTÂNCIAS`, `_PRAZOS`.

### Step 10: Report to User

Apresentar ao usuário:
- Resumo executivo do processo
- Peças encontradas (tabela)
- Contradições graves
- Prazos ativos/vencidos
- Nível de risco (ALTO/MÉDIO/BAIXO)
- Caminho do vault Obsidian

---

## Edge Cases

- **500+ páginas**: Chunk primeiro, analise em batches de 5-10 peças, persista JSON incrementalmente
- **PDFs de tribunais (PJe, e-SAJ, PROJUDI)**: Headers repetitivos removidos automaticamente
- **PDFs escaneados**: OCR fallback via pytesseract; flag chunks baixa confiança para vision
- **Múltiplos volumes**: Trate cada volume separadamente, concatene antes da síntese
- **Multi-instância**: Instance tracker lida com 1ª instância → TJ → STJ → STF

## Dependencies

- Python 3.10+ | poppler-utils (pdftotext, pdfinfo) | tesseract-ocr (opcional)
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
