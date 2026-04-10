<p align="center">
  <img src="assets/banner.svg" alt="JuriScan — Análise forense de processos judiciais brasileiros" width="900"/>
</p>

<p align="center">
  <a href="#instalação"><img src="https://img.shields.io/badge/plug--and--play-Claude_Code_Skill-blue?style=for-the-badge" alt="Claude Code Skill"/></a>
  <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"/>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="MIT License"/></a>
</p>

<p align="center">
  Skill para <a href="https://claude.ai/code">Claude Code</a> de análise forense de processos judiciais brasileiros.<br/>
  Extrai PDFs, divide por peça processual, detecta contradições, calcula prazos CPC,<br/>
  rastreia argumentos entre instâncias e exporta para Obsidian.
</p>

---

## O que é?

Um processo judicial pode ter centenas de páginas: petição, contestação, réplica, sentença, recurso... Um advogado levaria dias lendo tudo, cruzando informações e procurando inconsistências.

O **JuriScan** faz isso em minutos. Você joga o PDF do processo e recebe:

- **Separação automática** de cada peça processual (27 tipos detectados)
- **Mapa de contradições** entre o que autor e réu disseram
- **Prazos calculados** com feriados forenses e recesso (CPC Art. 219-232)
- **Rastreamento de argumentos** — o que foi aceito, rejeitado ou reformado em cada instância
- **Nota de risco** do caso (processual, mérito e exposição monetária)
- **Vault Obsidian** navegável com links entre peças, leis e jurisprudência

### Para quem é?

| Perfil | Como usa |
|---|---|
| **Advogado** | Análise rápida de processos grandes, preparação de peças, due diligence |
| **Escritório** | Padronização de análise forense, onboarding de casos novos |
| **Departamento jurídico** | Triagem de riscos, acompanhamento de prazos, auditoria processual |
| **Estudante de Direito** | Estudo de casos reais com estrutura visual |

---

## Instalação

### Clone e instale (uma vez)

```bash
git clone https://github.com/brunobracaioli/juriscan.git ~/.claude/skills/juriscan
cd ~/.claude/skills/juriscan
./install.sh
```

<details>
<summary><b>Opção alternativa:</b> clonar em qualquer lugar</summary>

```bash
git clone https://github.com/brunobracaioli/juriscan.git
cd juriscan
./install.sh    # cria symlink para ~/.claude/skills/ e instala dependências
```

</details>

<details>
<summary><b>Dependências de sistema</b> (opcionais mas recomendadas)</summary>

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-por

# macOS
brew install poppler tesseract tesseract-lang
```

Sem `poppler-utils`, a extração usa `pypdf` como fallback. Sem `tesseract`, PDFs escaneados não terão OCR.

</details>

---

## Uso

### Quick Run (um comando)

No Claude Code, com o PDF em qualquer pasta:

```
/juriscan ~/Downloads/processo.pdf
```

O Claude executa o pipeline completo automaticamente (extração → chunking → análise → contradições → prazos → risco → Obsidian) e apresenta o resultado.

### Linguagem natural

A skill também ativa quando você pede naturalmente:

> *"Analise este processo e mapeie as contradições"*
>
> *"Calcule os prazos deste processo"*
>
> *"Quais argumentos foram reformados em segunda instância?"*

### Via linha de comando

<details>
<summary>Ver todos os comandos</summary>

```bash
# Extrair e dividir PDF por peça processual
python3 scripts/extract_and_chunk.py --input processo.pdf --output ./analise/

# Verificar integridade (OCR quality, anomalias)
python3 scripts/integrity_check.py --input ./analise/

# Calcular prazos CPC
python3 scripts/prazo_calculator.py --date 2025-03-15 --tipo contestação --state SP

# Rastrear argumentos entre instâncias
python3 scripts/instance_tracker.py --analysis ./analise/analyzed.json --output ./analise/instances.json

# Detectar contradições
python3 scripts/contradiction_report.py --analysis ./analise/analyzed.json --output ./analise/contradictions.json

# Avaliar risco litigioso
python3 scripts/risk_scorer.py --analysis ./analise/analyzed.json --output ./analise/risk.json

# Validar output contra schema
python3 scripts/schema_validator.py --input ./analise/analyzed.json

# Exportar para Obsidian
python3 scripts/obsidian_export.py --analysis ./analise/analyzed.json --output ./vault/
```

</details>

---

## Pipeline

```
PDF(s)
 │
 ▼
[1]  Extração ─────────── pdftotext → pypdf → OCR
[2]  Integridade ──────── OCR confidence, anomalias, lacunas
[3]  Chunking ─────────── 27 tipos de peça processual detectados
[4]  Análise por chunk ── Claude: extração estruturada + citation grounding
[5]  Validação ────────── JSON Schema v2
[6]  Síntese cruzada ──── contradições + instâncias + precedentes vinculantes
[7]  Prazos CPC ───────── Art. 219-232, feriados, recesso forense
[8]  Scoring de risco ─── processual + mérito + exposição monetária
[9]  Output ───────────── JSON consolidado
[10] Obsidian ─────────── 7 views + peças + legislação + jurisprudência
```

---

## Vault Obsidian

A exportação gera um vault completo com backlinks automáticos:

```
processo-NNNNNNN/
├── _INDEX.md            Resumo executivo
├── _TIMELINE.md         Cronologia com Mermaid
├── _CONTRADIÇÕES.md     Mapa de contradições
├── _ENTIDADES.md        Partes, advogados, juízes
├── _RISCO.md            Avaliação de risco
├── _INSTÂNCIAS.md       Evolução de argumentos por instância
├── _PRAZOS.md           Dashboard de prazos
├── peças/               Uma nota por peça processual
├── legislação/          Stubs dos artigos citados
├── jurisprudência/      Stubs dos precedentes citados
└── diagramas/           Mermaid (timeline, grafo de referências)
```

---

## Funcionalidades

| Feature | Status |
|---|:---:|
| Extração PDF (text + OCR fallback) | :white_check_mark: |
| Chunking por peça processual (27 tipos) | :white_check_mark: |
| OCR confidence scoring | :white_check_mark: |
| Parsing de datas BR (DD/MM/YYYY, extenso, ISO) | :white_check_mark: |
| Parsing/validação de número CNJ | :white_check_mark: |
| Normalização monetária BRL | :white_check_mark: |
| Calculadora de prazos CPC (dias úteis, feriados, recesso) | :white_check_mark: |
| Detecção de contradições (valores, datas, fatos, jurisprudência) | :white_check_mark: |
| Rastreamento multi-instância (1ª inst → TJ → STJ → STF) | :white_check_mark: |
| Parsing tripartite de acórdão (ementa/relatório/voto) | :white_check_mark: |
| Detecção de precedentes vinculantes (SV, IRDR, IAC, RG) | :white_check_mark: |
| Citation grounding (afirmações com trecho fonte) | :white_check_mark: |
| Scoring de risco litigioso | :white_check_mark: |
| Exportação Obsidian (7 views) | :white_check_mark: |
| Validação de schema JSON | :white_check_mark: |

---

## Testes

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

```
============================= 146 passed in 0.58s ==============================
```

---

<p align="center">
  Feito para advogados brasileiros que precisam de análise forense séria.<br/>
  <sub>MIT License</sub>
</p>
