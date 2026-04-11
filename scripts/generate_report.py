"""Generate executive markdown report consolidating all pipeline outputs — Phase A.4.3.

This is the "uau" centerpiece of v3.1.0-legacy. It takes all the structured
JSON outputs of the pipeline and produces a single rich markdown document
(REPORT.md) that becomes the final deliverable of /juriscan.

Inputs (all optional — sections degrade gracefully when JSON missing):
    --analyzed analyzed.json           (required)
    --contradictions contradictions.json
    --instances instances.json
    --prazos prazos.json
    --risk risk.json
    --recommendations recommendations.json

Output:
    --output REPORT.md

The resulting markdown is designed to be:
- Terminal-renderable as Claude's final response to the user
- Copy-pasteable into email, Obsidian, or any markdown viewer
- Self-contained: has executive summary, alerts, pieces, contradictions
  with verbatim citations, risk assessment, strategic recommendations per
  polo, Mermaid timeline, prazos dashboard, and file listing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

try:
    from utils.monetary import format_brl, normalize_brl  # noqa: E402
except ImportError:
    def format_brl(v: float) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def normalize_brl(s: str) -> float | None:
        if not s:
            return None
        try:
            return float(s.replace("R$", "").replace(".", "").replace(",", ".").strip())
        except (ValueError, AttributeError):
            return None


# ---------- loaders ----------

def _load_json(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------- helpers ----------

def _escape_md(text: Any) -> str:
    """Escape markdown special chars in user content (minimal, preserves readability)."""
    if text is None:
        return ""
    s = str(text)
    # Escape pipes in table cells (caller already decides if inside table)
    return s.replace("\n", " ").strip()


def _escape_table_cell(text: Any) -> str:
    """Escape content for safe placement inside a markdown table cell."""
    if text is None:
        return ""
    s = str(text).replace("\n", " ").replace("|", "\\|").strip()
    # Truncate very long cells
    if len(s) > 200:
        s = s[:197] + "..."
    return s


def _blockquote(text: str) -> str:
    """Render a multi-line string as a markdown blockquote."""
    if not text:
        return ""
    lines = str(text).splitlines()
    return "\n".join(f"> {line}" if line.strip() else ">" for line in lines)


def _pick_first(*values: Any) -> Any:
    for v in values:
        if v is not None and v != "" and v != [] and v != {}:
            return v
    return None


# ---------- section renderers ----------

def render_header(analyzed: dict, risk: dict | None) -> str:
    """Cabeçalho com metadados do processo."""
    processo = analyzed.get("processo_number") or "(não identificado)"
    metadata = analyzed.get("processo_metadata") or {}
    chunks = analyzed.get("chunks") or []

    # Extract parties from first chunk that has them
    autor_list: list[str] = []
    reu_list: list[str] = []
    vara: str | None = metadata.get("vara")
    for ch in chunks:
        partes = ch.get("partes") or {}
        if not autor_list and partes.get("autor"):
            autor_list = partes["autor"] if isinstance(partes["autor"], list) else [partes["autor"]]
        if not reu_list and partes.get("reu"):
            reu_list = partes["reu"] if isinstance(partes["reu"], list) else [partes["reu"]]
        if not vara and partes.get("vara"):
            vara = partes["vara"]

    autor_str = ", ".join(autor_list) if autor_list else "(não identificado)"
    reu_str = ", ".join(reu_list) if reu_list else "(não identificado)"

    # Valor da causa
    valor_causa: str | None = None
    for ch in chunks:
        valores = ch.get("valores") or {}
        if valores.get("causa"):
            valor_causa = valores["causa"]
            break
    if not valor_causa:
        valor_causa = "(não identificado)"

    # Status
    status = _pick_first(
        metadata.get("fase_atual"),
        analyzed.get("process_state"),
        "(em andamento)",
    )

    instance = metadata.get("instancia_atual") or "(não identificada)"

    risk_badge = ""
    if risk:
        level = risk.get("risk_level", "")
        score = risk.get("overall_score")
        if level:
            emoji = {"ALTO": "🔴", "MÉDIO": "🟡", "BAIXO": "🟢"}.get(level, "⚪")
            risk_badge = f" · **Risco:** {emoji} {level}"
            if score is not None:
                risk_badge += f" ({score}/10)"

    return f"""# 📋 Análise Forense — Processo nº {_escape_md(processo)}

> **Partes:** {_escape_md(autor_str)} × {_escape_md(reu_str)}
> **Vara/Órgão:** {_escape_md(vara) or "(não identificado)"}
> **Valor da causa:** {_escape_md(valor_causa)}
> **Fase:** {_escape_md(status)} · **Instância atual:** {_escape_md(instance)}{risk_badge}
> **Pipeline:** legacy v3.1.0 — análise assistida por IA, requer revisão profissional"""


def render_executive_summary(
    analyzed: dict,
    contradictions: dict | None,
    risk: dict | None,
) -> str:
    """Resumo executivo gerado a partir dos campos estruturados."""
    chunks = analyzed.get("chunks") or []
    n_pieces = len(chunks)

    # Find sentença + acórdão
    sentenca = next((c for c in chunks if (c.get("tipo_peca") or "").upper() == "SENTENÇA"), None)
    acordao = next((c for c in chunks if (c.get("tipo_peca") or "").upper() == "ACÓRDÃO"), None)

    parts = []
    parts.append(f"O processo contém **{n_pieces} peça(s) processual(is)** analisada(s).")

    if sentenca:
        dec = sentenca.get("decisao")
        if dec:
            parts.append(f"A sentença de primeiro grau decidiu: *{_escape_md(dec)[:200]}*.")

    if acordao:
        dec = acordao.get("decisao")
        ac_struct = acordao.get("acordao_structure") or {}
        votacao = ac_struct.get("votacao")
        resultado = ac_struct.get("resultado")
        if dec or resultado:
            txt = f"Em segunda instância, o acórdão"
            if resultado:
                txt += f" resultou em **{resultado.replace('_', ' ').lower()}**"
            if votacao:
                txt += f" por **{votacao.lower()}**"
            if dec:
                txt += f": *{_escape_md(dec)[:200]}*"
            else:
                txt += "."
            parts.append(txt)

    if contradictions:
        n_contr = len(contradictions.get("contradictions", []))
        if n_contr:
            parts.append(f"A análise detectou **{n_contr} contradição(ões)** entre as peças.")

    if risk:
        level = risk.get("risk_level")
        score = risk.get("overall_score")
        if level:
            parts.append(f"Avaliação global de risco: **{level}** ({score}/10).")

    return "## 📋 Resumo Executivo\n\n" + " ".join(parts)


def render_alerts(analyzed: dict, prazos: dict | None, contradictions: dict | None) -> str:
    """Caixas de alerta críticos — art. 942, Lei 14.905, prazos urgentes."""
    alerts: list[str] = []
    chunks = analyzed.get("chunks") or []

    # Art. 942 detection
    for ch in chunks:
        if (ch.get("tipo_peca") or "").upper() != "ACÓRDÃO":
            continue
        ac = ch.get("acordao_structure") or {}
        if ac.get("votacao") == "MAIORIA":
            # Check if it's a reform (not just desprovimento)
            resultado = ac.get("resultado") or ""
            if resultado in ("PROVIDO", "PARCIALMENTE_PROVIDO"):
                quote = None
                for cit in ch.get("citation_spans") or []:
                    src = cit.get("source_text", "")
                    if "maioria" in src.lower() or "vencido" in src.lower():
                        quote = src
                        break
                alerts.append(
                    "> 🚨 **ALERTA CRÍTICO — Art. 942 CPC (possível nulidade)**\n"
                    f"> O acórdão (peça #{ch.get('index')}) foi proferido por **maioria** e "
                    f"reformou a sentença em {resultado.replace('_', ' ').lower()}. "
                    "Em apelação com reforma por maioria, o art. 942 do CPC impõe a "
                    "**técnica de ampliação do colegiado**. Se não aplicada, há nulidade "
                    "arguível via embargos de declaração e/ou Recurso Especial.\n"
                    + (f">\n> *Trecho fonte:* {_escape_md(quote)[:300]}" if quote else "")
                )

    # Lei 14.905/2024 — monetary_recalculations (supports both shapes:
    # finalize.py legacy {periodo_1, periodo_2} and finalize_legacy.py {periods: [...]})
    for recalc in analyzed.get("monetary_recalculations") or []:
        tipo = recalc.get("tipo", "")
        if "14905" not in tipo and "LEI_14905" not in tipo:
            continue
        base = recalc.get("base") or recalc.get("base_original") or ""
        periods = recalc.get("periods")
        if not periods:
            p1 = recalc.get("periodo_1") or {}
            p2 = recalc.get("periodo_2") or {}
            periods = [p for p in [p1, p2] if p]

        lines = [
            "> 💰 **Lei 14.905/2024 — Recálculo de juros obrigatório**",
            f"> Base: {_escape_md(base)}",
        ]
        for i, p in enumerate(periods, 1):
            de = p.get("de") or ""
            ate = p.get("ate") or ""
            taxa = p.get("taxa") or ""
            valor = p.get("valor_com_juros") or p.get("valor") or "—"
            lines.append(
                f"> Período {i} ({_escape_md(de)} → {_escape_md(ate)}): "
                f"{_escape_md(taxa)} → {_escape_md(valor)}"
            )
        alerts.append("\n".join(lines))

    # Prazos urgentes (< 10 dias)
    if prazos:
        prazo_list = prazos if isinstance(prazos, list) else prazos.get("prazos") or prazos.get("prazos_calculados") or []
        for p in prazo_list:
            dias = p.get("dias_restantes")
            status = p.get("status", "")
            if status in ("ultimo_dia", "vencido") or (isinstance(dias, int) and dias <= 10):
                emoji = "🔴" if status == "vencido" else "⏰"
                alerts.append(
                    f"> {emoji} **Prazo {'VENCIDO' if status == 'vencido' else 'URGENTE'}** — "
                    f"{_escape_md(p.get('tipo'))} "
                    f"(limite: {_escape_md(p.get('data_limite'))}, "
                    f"dias restantes: {dias if dias is not None else 'N/A'})\n"
                    f"> Fundamento: {_escape_md(p.get('fundamento_legal'))}"
                )

    # High-impact contradictions
    if contradictions:
        high = [c for c in (contradictions.get("contradictions") or []) if c.get("impacto") == "ALTO"]
        if len(high) >= 3:
            alerts.append(
                f"> ⚠️ **{len(high)} contradições de ALTO impacto detectadas** — "
                f"ver seção Contradições abaixo."
            )

    if not alerts:
        return ""

    return "## ⚠️ Alertas Críticos\n\n" + "\n>\n".join(alerts).replace(">\n>\n>", ">\n>\n> ")


def render_pieces_table(analyzed: dict) -> str:
    """Tabela de peças processuais."""
    chunks = analyzed.get("chunks") or []
    if not chunks:
        return ""

    rows = ["## 📑 Peças do Processo\n"]
    rows.append(f"**Total:** {len(chunks)} peça(s)\n")
    rows.append("| # | Peça | Data | Instância | Decisão/Resumo |")
    rows.append("|---|---|---|---|---|")
    for ch in chunks:
        idx = ch.get("index", "")
        tipo = ch.get("tipo_peca") or ch.get("label") or "(desconhecido)"
        data = ch.get("primary_date") or ch.get("data") or "—"
        instancia = ch.get("instancia") or "—"
        # Prefer decisao, then resumo (truncated)
        summary = ch.get("decisao") or ch.get("resumo") or ""
        rows.append(
            f"| {idx} | {_escape_table_cell(tipo)} | {_escape_table_cell(data)} | "
            f"{_escape_table_cell(instancia)} | {_escape_table_cell(summary)} |"
        )
    return "\n".join(rows)


def render_contradictions(contradictions: dict | None) -> str:
    """Contradições agrupadas por impacto com citações verbatim."""
    if not contradictions:
        return ""
    items = contradictions.get("contradictions") or []
    if not items:
        return "## 🔍 Contradições\n\nNenhuma contradição estrutural detectada."

    out = [f"## 🔍 Contradições Detectadas ({len(items)})\n"]

    # Group by impact
    groups: dict[str, list[dict]] = {"ALTO": [], "MÉDIO": [], "BAIXO": []}
    for c in items:
        impact = (c.get("impacto") or "BAIXO").upper()
        if impact not in groups:
            impact = "BAIXO"
        groups[impact].append(c)

    impact_emoji = {"ALTO": "🔴", "MÉDIO": "🟡", "BAIXO": "🟢"}
    for impact in ["ALTO", "MÉDIO", "BAIXO"]:
        if not groups[impact]:
            continue
        out.append(f"\n### {impact_emoji[impact]} Impacto {impact.title()} ({len(groups[impact])})\n")
        for c in groups[impact]:
            tipo = c.get("tipo", "CONTRADIÇÃO")
            desc = c.get("descricao") or c.get("descriçao") or ""
            out.append(f"#### {_escape_md(tipo)}\n")
            if desc:
                out.append(f"{_escape_md(desc)}\n")

            # Verbatim evidence from citation_spans or evidence[]
            evidence = c.get("evidence") or c.get("citation_spans") or []
            for i, ev in enumerate(evidence[:3]):
                # chunk_ref=0 is falsy but valid — use explicit None check
                chunk_ref = ev.get("chunk_ref")
                if chunk_ref is None:
                    chunk_ref = ev.get("peca_ref")
                if chunk_ref is None:
                    chunk_ref = "?"
                quote = ev.get("quote") or ev.get("source_text") or ev.get("trecho") or ""
                if quote:
                    label = f"**Fonte {chr(65 + i)} (peça #{chunk_ref}):**"
                    out.append(f"{label}")
                    out.append(_blockquote(quote[:500]))
                    out.append("")

            resolucao = c.get("resolucao") or c.get("resolution")
            if resolucao:
                out.append(f"**Resolução:** {_escape_md(resolucao)}\n")

    return "\n".join(out)


def render_risk_assessment(risk: dict | None) -> str:
    """Avaliação de risco com breakdown por dimensão."""
    if not risk:
        return ""

    level = risk.get("risk_level", "—")
    score = risk.get("overall_score")
    emoji = {"ALTO": "🔴", "MÉDIO": "🟡", "BAIXO": "🟢"}.get(level, "⚪")

    out = [f"## 📊 Avaliação de Risco\n"]
    out.append(f"### Risco Global: {emoji} **{level}** ({score}/10)\n")

    procedural = risk.get("procedural_risk") or {}
    merit = risk.get("merit_indicators") or {}
    monetary = risk.get("monetary_exposure") or {}

    out.append("| Dimensão | Score | Fatores |")
    out.append("|---|---|---|")

    p_score = procedural.get("score", "—")
    p_factors = procedural.get("factors") or procedural.get("fatores") or []
    out.append(
        f"| Processual | {p_score}/10 | {_escape_table_cell(', '.join(str(f) for f in p_factors[:5]))} |"
    )

    m_score = merit.get("score", "—")
    m_fav = merit.get("favorable_factors") or merit.get("fatores_favoraveis") or []
    m_unf = merit.get("unfavorable_factors") or merit.get("fatores_desfavoraveis") or []
    fav_str = "✅ " + ", ".join(str(f) for f in m_fav[:3]) if m_fav else ""
    unf_str = "❌ " + ", ".join(str(f) for f in m_unf[:3]) if m_unf else ""
    factors = " / ".join(x for x in [fav_str, unf_str] if x)
    out.append(f"| Mérito | {m_score}/10 | {_escape_table_cell(factors)} |")

    max_v = monetary.get("max_exposure") or monetary.get("max")
    likely = monetary.get("likely_range") or {}
    likely_min = likely.get("min")
    likely_likely = likely.get("likely")
    likely_max = likely.get("max")
    mon_str = ""
    if likely_min is not None and likely_max is not None:
        try:
            mon_str = f"R$ {float(likely_min):,.0f}–{float(likely_max):,.0f}"
            if likely_likely is not None:
                mon_str += f" (provável: R$ {float(likely_likely):,.0f})"
        except (TypeError, ValueError):
            mon_str = f"{likely_min}–{likely_max}"
    out.append(f"| Monetário | — | {_escape_table_cell(mon_str)} |")

    return "\n".join(out)


def render_recommendations(recommendations: dict | None) -> str:
    """Recomendações estratégicas por polo, com fundamentação e citação."""
    if not recommendations:
        return ""
    items = recommendations.get("recommendations") or []
    if not items:
        return ""

    out = ["## 🎯 Recomendações Estratégicas\n"]

    # Group by polo
    groups: dict[str, list[dict]] = {"autor": [], "reu": []}
    for r in items:
        polo = (r.get("polo") or "").lower()
        if polo in groups:
            groups[polo].append(r)

    polo_labels = {
        "autor": "### 👤 Polo Ativo",
        "reu": "### 🛡️ Polo Passivo",
    }

    for polo, label in polo_labels.items():
        if not groups[polo]:
            continue
        out.append(f"\n{label}\n")
        # Sort by priority
        priority_order = {"ALTA": 0, "MÉDIA": 1, "BAIXA": 2}
        sorted_items = sorted(
            groups[polo],
            key=lambda r: priority_order.get((r.get("priority") or "BAIXA").upper(), 3),
        )
        for i, r in enumerate(sorted_items, 1):
            action = r.get("action") or r.get("acao") or "(ação não especificada)"
            priority = r.get("priority") or "—"
            deadline = r.get("deadline_days")
            deadline_str = f" (prazo: {deadline} dias úteis)" if deadline else ""
            fundamentacao = r.get("fundamentacao") or r.get("fundamentation") or ""
            evidence = r.get("evidence_quote") or ""
            chunk_ref = r.get("evidence_chunk_ref")
            deadline_basis = r.get("deadline_basis") or ""
            impact = r.get("impact") or ""

            out.append(f"**{i}. [{priority}] {_escape_md(action)}{deadline_str}**")
            if deadline_basis:
                out.append(f"*Fundamento processual:* {_escape_md(deadline_basis)}")
            if fundamentacao:
                out.append(f"\n{_escape_md(fundamentacao)}")
            if evidence:
                label_ref = f"*Trecho fonte (peça #{chunk_ref}):*" if chunk_ref is not None else "*Trecho fonte:*"
                out.append(f"\n{label_ref}")
                out.append(_blockquote(evidence[:400]))
            if impact:
                out.append(f"*Impacto esperado:* {_escape_md(impact)}")
            out.append("")

    return "\n".join(out)


def render_timeline(analyzed: dict) -> str:
    """Cronograma Mermaid gantt (só se >= 3 peças com datas)."""
    chunks = analyzed.get("chunks") or []
    dated = [(c.get("primary_date"), c.get("tipo_peca") or c.get("label")) for c in chunks]
    dated = [(d, t) for d, t in dated if d and t]
    if len(dated) < 3:
        return ""

    # Convert DD/MM/YYYY to YYYY-MM-DD
    def _to_iso(d: str) -> str | None:
        try:
            parts = d.split("/")
            if len(parts) == 3:
                dd, mm, yyyy = parts
                return f"{yyyy}-{mm.zfill(2)}-{dd.zfill(2)}"
        except (AttributeError, ValueError):
            pass
        return None

    iso_dated = [(i, _to_iso(d), t) for i, (d, t) in enumerate(dated)]
    iso_dated = [(i, d, t) for i, d, t in iso_dated if d]
    if len(iso_dated) < 3:
        return ""

    lines = [
        "## 📅 Cronologia",
        "",
        "```mermaid",
        "gantt",
        "    title Cronologia do Processo",
        "    dateFormat YYYY-MM-DD",
        "    axisFormat %d/%m/%y",
    ]
    for i, d, t in iso_dated:
        # Mermaid task: name :id, start, duration
        safe_name = str(t).replace(":", " -").replace(",", " ")[:40]
        lines.append(f"    {safe_name} :p{i}, {d}, 1d")
    lines.append("```")
    return "\n".join(lines)


def render_prazos_table(prazos: dict | None) -> str:
    """Dashboard de prazos."""
    if not prazos:
        return ""
    prazo_list = prazos if isinstance(prazos, list) else prazos.get("prazos") or prazos.get("prazos_calculados") or []
    if not prazo_list:
        return ""

    out = ["## ⏰ Prazos\n"]
    out.append("| Tipo | Intimação | Limite | Status | Dias restantes |")
    out.append("|---|---|---|---|---|")
    for p in prazo_list:
        status = (p.get("status") or "").lower()
        status_emoji = {"em_prazo": "🟢", "ultimo_dia": "🟡", "vencido": "🔴", "suspenso": "⏸️"}.get(status, "⚪")
        dias = p.get("dias_restantes")
        out.append(
            f"| {_escape_table_cell(p.get('tipo'))} | "
            f"{_escape_table_cell(p.get('data_intimacao'))} | "
            f"{_escape_table_cell(p.get('data_limite'))} | "
            f"{status_emoji} {status or '—'} | "
            f"{dias if dias is not None else '—'} |"
        )
    return "\n".join(out)


def render_file_listing(output_dir: Path) -> str:
    """Lista de arquivos de saída."""
    files = [
        ("analyzed.json", "Análise estruturada consolidada"),
        ("contradictions.json", "Contradições detectadas"),
        ("instances.json", "Rastreamento por instância"),
        ("prazos.json", "Prazos CPC calculados"),
        ("risk.json", "Avaliação de risco"),
        ("recommendations.json", "Recomendações estratégicas"),
        ("REPORT.md", "Este relatório executivo"),
        ("obsidian/", "Vault Obsidian navegável"),
    ]
    lines = ["## 📂 Arquivos de Saída\n"]
    for fname, desc in files:
        p = output_dir / fname
        if p.exists():
            lines.append(f"- `{fname}` — {desc}")
    return "\n".join(lines) if len(lines) > 1 else ""


def render_footer() -> str:
    return (
        "---\n\n"
        "*Análise gerada por [JuriScan](https://github.com/brunobracaioli/juriscan) v3.1.0 "
        "(pipeline legacy). Análise assistida por IA, requer revisão profissional. "
        "Não substitui parecer jurídico nem produz peça vinculante.*"
    )


# ---------- main ----------

def build_report(
    analyzed: dict,
    contradictions: dict | None,
    instances: dict | None,
    prazos: dict | None,
    risk: dict | None,
    recommendations: dict | None,
    output_dir: Path,
) -> str:
    """Build the full markdown report."""
    sections = [
        render_header(analyzed, risk),
        "",
        render_executive_summary(analyzed, contradictions, risk),
        "",
        render_alerts(analyzed, prazos, contradictions),
        "",
        render_pieces_table(analyzed),
        "",
        render_contradictions(contradictions),
        "",
        render_risk_assessment(risk),
        "",
        render_recommendations(recommendations),
        "",
        render_timeline(analyzed),
        "",
        render_prazos_table(prazos),
        "",
        render_file_listing(output_dir),
        "",
        render_footer(),
    ]
    # Filter empty sections
    non_empty = [s for s in sections if s is not None and s != ""]
    return "\n\n".join(non_empty) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate executive markdown report from pipeline outputs",
    )
    parser.add_argument("--analyzed", "-a", required=True, help="Path to analyzed.json")
    parser.add_argument("--contradictions", help="Path to contradictions.json")
    parser.add_argument("--instances", help="Path to instances.json")
    parser.add_argument("--prazos", help="Path to prazos.json")
    parser.add_argument("--risk", help="Path to risk.json")
    parser.add_argument("--recommendations", help="Path to recommendations.json")
    parser.add_argument("--output", "-o", required=True, help="Output path for REPORT.md")
    args = parser.parse_args(argv)

    analyzed_path = Path(args.analyzed)
    if not analyzed_path.exists():
        print(f"ERROR: analyzed.json not found: {analyzed_path}", file=sys.stderr)
        return 2

    analyzed = _load_json(analyzed_path)
    if analyzed is None:
        print(f"ERROR: could not load {analyzed_path}", file=sys.stderr)
        return 2

    contradictions = _load_json(Path(args.contradictions)) if args.contradictions else None
    instances = _load_json(Path(args.instances)) if args.instances else None
    prazos = _load_json(Path(args.prazos)) if args.prazos else None
    risk = _load_json(Path(args.risk)) if args.risk else None
    recommendations = _load_json(Path(args.recommendations)) if args.recommendations else None

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = build_report(
        analyzed=analyzed,
        contradictions=contradictions,
        instances=instances,
        prazos=prazos,
        risk=risk,
        recommendations=recommendations,
        output_dir=output_path.parent,
    )

    output_path.write_text(report, encoding="utf-8")
    print(f"[generate_report] REPORT.md written → {output_path}")
    print(f"  {len(report.splitlines())} lines · {len(report)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
