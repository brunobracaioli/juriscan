---
name: juriscan
description: "Análise forense de processos judiciais brasileiros. Extrai, classifica e cruza peças processuais, detecta contradições, calcula prazos CPC e gera relatórios de risco com exportação para Obsidian. Use quando mencionar: processo judicial, petição, sentença, acórdão, contradições, prazos, timeline, análise forense, Obsidian."
allowed-tools: Read Bash(python3 *) Bash(pip install *) Bash(pdftotext *) Bash(pdfinfo *) Glob Grep Task
---

# JuriScan

## Quick Run

Quando o usuário invocar `/juriscan <caminho_do_pdf>` ou pedir para analisar um processo, execute TODO o pipeline abaixo em sequência, sem parar para perguntar. O PDF pode estar em qualquer diretório — o usuário passa o caminho.

Se o usuário não passar um caminho, pergunte: "Qual o caminho do PDF do processo?"

**CWD check:** Se `pwd` apontar para `*/.claude/skills/juriscan*` (ou seja, a sessão do Claude foi iniciada dentro do diretório da própria skill), avise o usuário:

> "Você iniciou o Claude Code dentro do diretório da skill (`~/.claude/skills/juriscan`). Skills são globais — o normal é rodar o Claude na pasta do seu projeto, onde estão os PDFs. Saia desta sessão, faça `cd` para a pasta do processo e rode `claude` de novo. Posso continuar aqui mesmo assim se você passar o caminho absoluto do PDF."

Prossiga apenas se o usuário insistir ou fornecer caminho absoluto.

**Fluxo completo automático:**

1. Resolver `SKILL_DIR` e garantir dependências (Setup)
2. Criar diretório de análise ao lado do PDF: `<pdf_dir>/juriscan-output/`
3. Resolver o **modo de execução** (ver "Modos de execução" abaixo)
4. Executar o pipeline correspondente ao modo escolhido
5. No final, informar ao usuário:
   - Resumo executivo do processo (3-5 frases)
   - Quantas peças encontradas
   - Contradições detectadas (quantidade e as mais graves)
   - Prazos calculados (se houver)
   - Nível de risco
   - Onde estão os arquivos de saída
   - Se quiser Obsidian: "O vault está em `<output>/obsidian/` — abra essa pasta no Obsidian como vault"
   - run_id do audit trail (`.juriscan/audit/<run_id>.jsonl`) quando em modo agents

---

## Modos de execução

O juriscan suporta dois pipelines. O modo é resolvido a partir dos argumentos:

| Invocação | Modo | Status |
|---|---|---|
| `/juriscan --selftest` | Selftest | Ativo (ver seção Selftest) |
| `/juriscan --pipeline=legacy <pdf>` | **Legacy** (default até Phase 6) | Ativo — pipeline determinístico descrito em "Step-by-Step Pipeline" |
| `/juriscan --pipeline=agents <pdf>` | **Agents** (opt-in durante Phases 2–5) | Em construção — ver "Agents Pipeline" |
| `/juriscan <pdf>` (sem flag) | Legacy (por enquanto) | Flip do default acontece na Phase 6 Step 6.4 |

**Parsing dos argumentos:** quando o usuário invocar `/juriscan`, o primeiro token não-flag é o caminho do PDF. Flags reconhecidas: `--selftest`, `--pipeline=legacy`, `--pipeline=agents`. Qualquer flag desconhecida → avisar e cair em legacy.

**Gate de pré-requisitos (modo agents):** antes de seguir o modo agents, confirme que:

1. O arquivo `.claude/agents/juriscan-echo.md` existe em `$SKILL_DIR/.claude/agents/` (proxy para "subagents foram instalados").
2. `python3 "$SKILL_DIR/scripts/agent_io.py" validate --agent echo --input "$SKILL_DIR/tests/fixtures/agent_io/echo_valid.json"` retorna exit 0 (proxy para "schemas + jsonschema ok").

Se algum check falhar, **não** prossiga em modo agents. Informe o usuário o check que falhou e sugira `./install.sh` + `/juriscan --selftest`.

**Manifesto (ambos os modos):** no início de qualquer análise (não-selftest), crie/atualize `<output>/manifest.json`:

```bash
RUN_ID="$(python3 "$SKILL_DIR/scripts/agent_io.py" new-run --root "$OUTPUT_DIR/.juriscan/audit")"
python3 -c "
import json, os, time
manifest = {
    'run_id': '$RUN_ID',
    'pipeline_mode': '$PIPELINE_MODE',  # 'legacy' | 'agents'
    'pdf_path': os.path.abspath('$PDF_PATH'),
    'started_at': time.time(),
    'skill_dir': '$SKILL_DIR',
}
open('$OUTPUT_DIR/manifest.json','w').write(json.dumps(manifest, indent=2))
"
```

Nota: por ora `.juriscan/audit/` vive dentro de `<output>/` (não na raiz do projeto) para evitar poluir o cwd do usuário. Depois do Phase 6 podemos discutir se faz sentido centralizar.

---

## Agents Pipeline (modo `--pipeline=agents`)

Sequência quando o modo agents está selecionado. Cada passo é `[Python]` (script determinístico) ou `[Task]` (invocação de subagent via Task tool). Passos marcados `[PENDING: Phase N]` ainda não têm subagent real e abortam a pipeline com mensagem clara até serem implementados.

```
1. [Python]  scripts/extract_pdf.py              -> raw_text.txt + page_map.json
                                                    (Phase 2.x, stub usa extract_and_chunk.py)
2. [Task]    juriscan-segmenter                  -> /tmp/$RUN_ID-segmenter.json
3. [Python]  scripts/agent_io.py validate --agent segmenter ...
4. [Python]  scripts/persist_chunks.py           -> chunks/*.txt + index.json
5. [Task×N]  juriscan-parser (paralelo)          -> /tmp/$RUN_ID-parser-NN.json por chunk
6. [Python]  scripts/agent_io.py validate (N×)
7. [Python]  scripts/enrich_deterministic.py     -> pieces enriquecidas (normalizações)
8. [Task×3]  juriscan-advogado-autor, juriscan-advogado-reu, juriscan-auditor-processual (paralelo)
             [PENDING: Phase 3]
9. [Task]    juriscan-verificador                 [PENDING: Phase 4]
10.[Task]    juriscan-sintetizador                [PENDING: Phase 3]
11.[Python]  scripts/confidence_rules.py          [PENDING: Phase 3/4]
12.[Python]  scripts/finalize.py                  [PENDING: Phase 5]
13.[Python]  scripts/obsidian_export.py           (esquema v2 até Phase 6)
```

Regra geral para cada `[Task]`:

1. Defina um output path em `/tmp/juriscan-${RUN_ID}-<role>[-<idx>].json` e instrua o subagent a escrever nele.
2. Invoque via Task tool: `Task(subagent_type="juriscan-<role>", prompt="...")`.
3. Rode `python3 "$SKILL_DIR/scripts/agent_io.py" validate --agent <role> --input <path>`.
   - Exit 0 → passo 4.
   - Exit ≠ 0 → re-invocar o subagent **uma vez** passando o stderr do validate como feedback. Segunda falha → abortar pipeline e reportar `run_id`.
4. Rode `agent_io.py log --run-id $RUN_ID --agent <role> --input <path> --schema-valid true [--latency-ms N]`.
5. Consuma o arquivo validado no próximo passo Python.

**Invocações paralelas (passos 5 e 8):** emita todas as chamadas Task na **mesma mensagem** ao modelo. Não serialize — Claude Code executa-as em paralelo quando estão na mesma resposta do assistant.

---

## Selftest (`/juriscan --selftest`)

Quando o usuário invocar `/juriscan --selftest`, **não** rode o pipeline de análise. Em vez disso, execute o selftest abaixo para verificar que o contrato com subagents está funcionando. Esse é o único diagnóstico que prova, end-to-end, que a máquina de subagents + validação + audit trail está saudável antes de qualquer análise real.

1. **Gerar run_id e abrir audit trail:**
   ```bash
   RUN_ID="$(python3 "$SKILL_DIR/scripts/agent_io.py" new-run)"
   echo "selftest run_id=$RUN_ID"
   ```
2. **Invocar o subagent echo via Task tool** com `subagent_type="juriscan-echo"`. Instrua o echo a escrever em `/tmp/juriscan_selftest_${RUN_ID}.json` com `input_echo="selftest ping"`.
3. **Validar o JSON retornado:**
   ```bash
   python3 "$SKILL_DIR/scripts/agent_io.py" validate \
     --agent echo --input "/tmp/juriscan_selftest_${RUN_ID}.json"
   ```
4. **Registrar no audit trail:**
   ```bash
   python3 "$SKILL_DIR/scripts/agent_io.py" log \
     --run-id "$RUN_ID" --agent echo \
     --input "/tmp/juriscan_selftest_${RUN_ID}.json" \
     --schema-valid true --model-hint haiku
   ```
5. **Reportar ao usuário:**
   - Sucesso: `"Selftest OK — subagent echo respondeu e foi validado. run_id=$RUN_ID"`
   - Falha (validate retornou ≠ 0 ou arquivo ausente): mostre a mensagem do validator e o `run_id` para inspeção do audit trail.

Se o subagent `juriscan-echo` não estiver registrado (Task tool retornar erro de `subagent_type` desconhecido), oriente o usuário a rodar `./install.sh` novamente — o instalador é responsável por expor `.claude/agents/juriscan-*.md` ao Claude Code.

---

## Contract com subagents

A partir do Phase 2 do plano de migração (flag `--pipeline=agents`), o `juriscan` passa a delegar raciocínio semântico para subagents nativos do Claude Code, definidos em `.claude/agents/juriscan-*.md` dentro do repositório. O contrato entre este SKILL.md (orquestrador) e cada subagent é rígido e determinístico:

| Item | Onde mora | Papel |
|---|---|---|
| System prompt do subagent | `.claude/agents/juriscan-<role>.md` (frontmatter + corpo) | Define persona, ferramentas permitidas, modelo sugerido |
| Schema do output JSON | `references/agent_schemas/<role>_output.json` | Contrato de forma do output |
| Validador e logger | `scripts/agent_io.py` | CLI: `validate`, `log`, `new-run`, `extract-field` |
| Audit trail append-only | `.juriscan/audit/{run_id}.jsonl` | Uma linha por invocação Task |

**Fluxo obrigatório por invocação** (modo `--pipeline=agents`):

1. SKILL.md emite uma chamada `Task(subagent_type="juriscan-<role>", prompt=..., ...)`.
2. O subagent escreve seu resultado num arquivo JSON em caminho que o orquestrador escolheu.
3. SKILL.md roda `python3 $SKILL_DIR/scripts/agent_io.py validate --agent <role> --input <path>`.
   - Exit 0 → prosseguir.
   - Exit ≠ 0 → re-invocar o subagent **uma vez** com a mensagem de erro como feedback. Segundo erro → abortar o pipeline e reportar falha ao usuário com o `run_id`.
4. SKILL.md roda `agent_io.py log ...` para gravar a invocação (timestamp, schema_valid, input_hash, latency_ms quando aplicável).
5. Só depois de `schema_valid=true` o output é consumido por Python determinístico (enrich, persist_chunks, finalize).

**Invariantes não-negociáveis:**

- Nenhum subagent escreve direto em `analyzed.json`. Toda escrita canônica passa por scripts Python.
- Nenhum subagent consulta a web fora da whitelist (`references/whitelist_fontes.json`, Phase 4). O verificador é o único com `WebFetch` nas `tools:`.
- Nenhum Task call fica sem linha no audit trail. Se o subagent falhou, loga com `error=<msg>` e `schema_valid=false`.
- Paralelismo: quando houver múltiplas invocações independentes (parser por chunk, advogado-autor + advogado-réu + auditor), SKILL.md emite as chamadas Task **na mesma mensagem** para aproveitar a execução paralela nativa do Claude Code.

Phase 0 Step 0.4 introduz apenas o subagent `juriscan-echo` (selftest) e o esqueleto dos schemas. Os subagents reais (`segmenter`, `parser`, `advogado-autor`, `advogado-reu`, `auditor-processual`, `verificador`, `sintetizador`) entram nas Phases 2–4 do plano e cada um é um PR próprio.

---

## Setup

Executar uma vez no início da sessão:

```bash
# install.sh cria um symlink em ~/.claude/skills/juriscan apontando para a
# cópia clonada do repo. Se o link existe, essa é a fonte de verdade.
if [ -L "$HOME/.claude/skills/juriscan" ] || [ -d "$HOME/.claude/skills/juriscan" ]; then
    SKILL_DIR="$HOME/.claude/skills/juriscan"
else
    # Fallback: rodando direto do repo sem instalar (dev mode)
    SKILL_DIR="$(find -L . -maxdepth 3 -name 'SKILL.md' -path '*juriscan*' -exec dirname {} \; 2>/dev/null | head -1)"
fi
[ -z "$SKILL_DIR" ] && { echo "ERROR: could not locate juriscan skill. Run ./install.sh first."; exit 1; }
echo "SKILL_DIR=$SKILL_DIR"

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

Esta é a etapa mais importante do pipeline. Toda a qualidade dos arquivos persistidos (`analyzed.json`, `risk.json`, `instances.json`, vault Obsidian) depende dela. **Não tome atalhos.**

Para **cada chunk** em `chunks/`:

1. **Leia o arquivo do chunk** usando o tool Read (não invente conteúdo, não escreva script Python que hardcoda enrichments — leia o arquivo real).
2. **Identifique o `tipo_peca`** consultando [piece_type_taxonomy.json](references/piece_type_taxonomy.json). Use o nome canônico exato (ex.: `"PETIÇÃO INICIAL"`, `"SENTENÇA"`, `"ACÓRDÃO"`) — não inventar variantes.
3. **Aplique o prompt Análise Per-Chunk** de [prompt_templates.md](references/prompt_templates.md#1-análise-per-chunk-extração-estruturada) ao conteúdo do chunk e gere o objeto JSON populado **em sessão** (não em script Python externo).
4. Para chunks `ACÓRDÃO`, também aplicar **Parsing Tripartite** de [prompt_templates.md](references/prompt_templates.md#3-parsing-tripartite-de-acórdão) e popular `acordao_detail`.

Referência de entidades: [brazilian_legal_entities.md](references/brazilian_legal_entities.md).

**REGRA CRÍTICA — proibido improvisar script Python que hardcoda enrichments.** Se você se pegar escrevendo um arquivo `build_analyzed.py` (ou similar) com dicionários `enrichments = {0: {...}, 1: {...}}`, **pare**. Isso é o sintoma do atalho que produz `analyzed.json` esqueleto. Em vez disso, leia cada chunk via Read tool, faça a análise no seu próprio raciocínio, e construa o dict diretamente em código curto que apenas mescla com `index.json`.

**Campos mínimos obrigatórios** (toda execução real deve populá-los conforme o `tipo_peca`):

| Campo | Quando popular | Comentário |
|---|---|---|
| `tipo_peca` | **Sempre** | Nome canônico da `piece_type_taxonomy.json` |
| `partes` | Sempre que aparecerem nomes de partes | Object `{autor, reu, advogados[]}` |
| `pedidos[]` | `PETIÇÃO INICIAL`, `RECONVENÇÃO`, recursos | Lista de strings |
| `valores` | Quando houver R$ no texto | Object `{causa, condenacao, ...}` |
| `fatos_relevantes[]` | Sempre que houver narrativa fática | Lista de strings |
| `decisao` | `SENTENÇA`, `ACÓRDÃO`, `DESPACHO` | String com o dispositivo |
| `acordao_detail` | `ACÓRDÃO` | Object tripartite (ementa, relatório, voto) + `votos_divergentes[]` |
| `artigos_lei[]` | Sempre que citar artigos | Lista de strings (ex.: `"CPC art. 942"`) |
| `jurisprudencia[]` | Sempre que citar precedente | Lista de objetos |
| `prazos[]` | Quando houver intimação/publicação com data | Lista de objetos `{tipo, data_inicio, ...}` |

**IMPORTANTE — como montar o `analyzed.json` final:** não reconstrua `chunks[]` do zero. Carregue o `index.json` existente (produzido pelo `extract_and_chunk.py`) e **ADICIONE** os campos semânticos a cada chunk. Os campos técnicos já existentes — especialmente `index`, `label`, `char_count`, `chunk_file`, `primary_date`, `dates_found`, `page_range`, `ocr_confidence` — **devem** ser preservados, pois o `schema_validator.py` roda um integrity gate que exige correspondência 1:1 entre chunks do JSON e arquivos físicos em `chunks/`. Omitir `chunk_file` aborta a validação.

Receita correta:
```python
import json
idx = json.load(open('<output_dir>/index.json'))
for chunk in idx['chunks']:
    # 1. Leia o conteúdo via Read tool ANTES desta linha — não dentro do loop
    # 2. Analise mentalmente seguindo prompt_templates.md
    # 3. Mescle os campos resultantes nesta iteração:
    chunk['tipo_peca'] = '...'           # canônico
    chunk['partes'] = {...}
    chunk['pedidos'] = [...]
    chunk['valores'] = {...}
    chunk['fatos_relevantes'] = [...]
    chunk['decisao'] = '...'             # quando aplicável
    chunk['acordao_detail'] = {...}      # quando ACÓRDÃO
    # ... demais campos conforme tipo_peca
analyzed = {'analysis_version': '2.0', **idx, 'chunks': idx['chunks']}
json.dump(analyzed, open('<output_dir>/analyzed.json','w'), ensure_ascii=False, indent=2)
```

**Quando o chunker agrupa peças (issue #3):** se o chunker criar 1 arquivo físico contendo várias peças (ex.: laudo + sentença + apelação juntos), você tem duas opções:

- **Opção A — split semântico (preferido):** mantenha o `chunk_file` original, mas adicione múltiplas entradas em `chunks[]` que apontem para ele, cada uma com `tipo_peca` próprio. Use índices repetidos com sufixo (`"0a"`, `"0b"`) ou mantenha índices únicos preservando `chunk_file` repetido. Importante: o integrity_gate aceita N entradas → 1 arquivo físico desde que `chunk_file` seja idêntico.
- **Opção B — peça dominante:** identifique a peça mais importante do agrupamento (geralmente a decisória — sentença, acórdão) e use ela como `tipo_peca` do chunk; documente as outras em `fatos_relevantes` ou `acordao_detail`.

Salvar resultado consolidado em `<output_dir>/analyzed.json`.

### Step 4: Schema Validation + Content Quality Check

```bash
python3 $SKILL_DIR/scripts/schema_validator.py --input <output_dir>/analyzed.json
```

Se falhar, corrigir o JSON e re-validar. Repetir até válido.

**Depois do schema OK, rode o sanity check de qualidade:**
```bash
python3 $SKILL_DIR/scripts/content_quality_check.py --input <output_dir>/analyzed.json
```

Esse script é **não-bloqueante** (sempre exit 0) — ele lista warnings em stderr quando os campos canônicos estão suspeitamente vazios. Se aparecerem mensagens tipo `WARN: 0/4 chunks têm campo 'tipo_peca' populado`, **volte ao Step 3** e re-faça a análise per-chunk preenchendo os campos faltantes. Não prossiga com analyzed.json esqueleto — os passos seguintes vão produzir vault Obsidian vazio.

### Step 5: Cross-Synthesis

**5a. Contradições:**
```bash
python3 $SKILL_DIR/scripts/legacy/contradiction_report.py --analysis <output_dir>/analyzed.json --output <output_dir>/contradictions.json
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
python3 $SKILL_DIR/scripts/legacy/risk_scorer.py --analysis <output_dir>/analyzed.json --output <output_dir>/risk.json
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
