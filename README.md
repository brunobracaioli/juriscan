# JuriScan

Skill para [Claude Code](https://claude.ai/code) de análise forense de processos judiciais brasileiros.

Extrai PDFs de processos, divide por peça processual, detecta contradições, rastreia argumentos entre instâncias, calcula prazos CPC e exporta para Obsidian.

## Instalação (plug-and-play)

### Opção 1: Clone direto como skill

```bash
git clone <repo> ~/.claude/skills/juriscan
cd ~/.claude/skills/juriscan
./install.sh
```

### Opção 2: Clone em qualquer lugar + instalar

```bash
git clone <repo>
cd juriscan
./install.sh    # cria symlink para ~/.claude/skills/ e instala dependências
```

O `install.sh` cuida de tudo: instala dependências Python, verifica dependências de sistema, e registra a skill no Claude Code.

### Dependências de sistema (opcionais mas recomendadas)

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-por

# macOS
brew install poppler tesseract tesseract-lang
```

Sem `poppler-utils`, a extração de PDF usa `pypdf` como fallback. Sem `tesseract`, PDFs escaneados não terão OCR.

## Uso

### Via Claude Code (recomendado)

Após a instalação, basta pedir naturalmente:

> "Analise este processo e mapeie as contradições"
>
> "Calcule os prazos deste processo"
>
> "Exporte a análise para Obsidian"
>
> "Quais argumentos foram reformados em segunda instância?"

O Claude ativa a skill automaticamente e executa o pipeline de 10 estágios.

### Via linha de comando

```bash
# 1. Extrair e dividir PDF por peça processual
python3 scripts/extract_and_chunk.py --input processo.pdf --output ./analise/

# 2. Verificar integridade (OCR quality, anomalias)
python3 scripts/integrity_check.py --input ./analise/

# 3. Calcular prazos CPC
python3 scripts/prazo_calculator.py --date 2025-03-15 --tipo contestação --state SP

# 4. Rastrear argumentos entre instâncias
python3 scripts/instance_tracker.py --analysis ./analise/analyzed.json --output ./analise/instances.json

# 5. Detectar contradições
python3 scripts/contradiction_report.py --analysis ./analise/analyzed.json --output ./analise/contradictions.json

# 6. Avaliar risco litigioso
python3 scripts/risk_scorer.py --analysis ./analise/analyzed.json --output ./analise/risk.json

# 7. Validar output contra schema
python3 scripts/schema_validator.py --input ./analise/analyzed.json

# 8. Exportar para Obsidian
python3 scripts/obsidian_export.py --analysis ./analise/analyzed.json --output ./vault/
```

## Pipeline

```
PDF(s)
 │
 ▼
[1] Extração (pdftotext → pypdf → OCR)
[2] Verificação de integridade (OCR confidence, anomalias)
[3] Chunking por peça processual (25+ tipos detectados)
[4] Análise por chunk via Claude (extração estruturada + citation grounding)
[5] Validação de schema
[6] Síntese cruzada (contradições + instâncias + precedentes vinculantes)
[7] Cálculo de prazos CPC (Art. 219-232, feriados, recesso forense)
[8] Scoring de risco (processual + mérito + exposição monetária)
[9] Output consolidado (JSON)
[10] Exportação Obsidian (7 views + peças + legislação + jurisprudência)
```

## Vault Obsidian

A exportação gera um vault completo com backlinks automáticos:

```
processo-NNNNNNN/
├── _INDEX.md          # Resumo executivo
├── _TIMELINE.md       # Cronologia com Mermaid
├── _CONTRADIÇÕES.md   # Mapa de contradições
├── _ENTIDADES.md      # Partes, advogados, juízes
├── _RISCO.md          # Avaliação de risco
├── _INSTÂNCIAS.md     # Evolução de argumentos por instância
├── _PRAZOS.md         # Dashboard de prazos
├── peças/             # Uma nota por peça processual
├── legislação/        # Stubs dos artigos citados
├── jurisprudência/    # Stubs dos precedentes citados
└── diagramas/         # Mermaid (timeline, grafo de referências)
```

## Testes

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Cobertura de Funcionalidades

| Feature | Status |
|---|---|
| Extração PDF (text + OCR fallback) | Implementado |
| Chunking por peça processual (27 tipos) | Implementado |
| OCR confidence scoring | Implementado |
| Parsing de datas BR (DD/MM/YYYY, extenso, ISO) | Implementado |
| Parsing/validação de número CNJ | Implementado |
| Normalização monetária BRL | Implementado |
| Calculadora de prazos CPC (dias úteis, feriados, recesso) | Implementado |
| Detecção de contradições (valores, datas, fatos, jurisprudência) | Implementado |
| Rastreamento multi-instância (1ª inst → TJ → STJ → STF) | Implementado |
| Parsing tripartite de acórdão (ementa/relatório/voto) | Via prompt |
| Detecção de precedentes vinculantes (SV, IRDR, IAC, RG) | Via prompt |
| Citation grounding (afirmações com trecho fonte) | Via prompt |
| Scoring de risco litigioso | Implementado |
| Exportação Obsidian (7 views) | Implementado |
| Validação de schema JSON | Implementado |
