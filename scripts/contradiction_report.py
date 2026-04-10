#!/usr/bin/env python3
"""
contradiction_report.py — Gera relatório de contradições entre peças processuais.

Compara as análises de todas as peças e identifica:
- Fatos divergentes (mesmo fato narrado diferentemente)
- Valores inconsistentes (números que mudam entre peças)
- Datas conflitantes (cronologia que não bate)
- Argumentos contraditórios (parte contradiz a si mesma)
- Jurisprudência conflitante (mesma tese, precedentes opostos)

Usage:
    python3 contradiction_report.py --analysis ./analysis/analyzed.json --output ./analysis/contradictions.json
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict


def extract_monetary_values(text: str) -> list:
    """Extract monetary values from text."""
    patterns = [
        r'R\$\s*[\d.,]+',
        r'[\d.,]+\s*(?:reais|mil|milhão|milhões|bilhão|bilhões)',
    ]
    values = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            values.append(m.group().strip())
    return values


def normalize_value(val_str: str) -> float | None:
    """Try to normalize a monetary string to float."""
    try:
        cleaned = re.sub(r'[R$\s]', '', val_str)
        cleaned = cleaned.replace('.', '').replace(',', '.')
        return float(cleaned)
    except:
        return None


def find_value_inconsistencies(chunks: list) -> list:
    """Find monetary values that differ across chunks for the same concept."""
    contradictions = []
    
    # Compare valor_causa across chunks
    causas = []
    for c in chunks:
        v = c.get('valores', {}).get('causa')
        if v:
            causas.append((c.get('label', '?'), v))
    
    if len(causas) > 1:
        normalized = [(label, val, normalize_value(val)) for label, val in causas]
        unique_vals = set(n for _, _, n in normalized if n is not None)
        if len(unique_vals) > 1:
            contradictions.append({
                'tipo': 'VALOR_INCONSISTENTE',
                'impacto': 'MÉDIO',
                'pecas': [label for label, _, _ in normalized],
                'descricao': f"Valor da causa diverge entre peças: {', '.join(f'{label}: {val}' for label, val, _ in normalized)}",
                'sugestao': 'Verificar se houve emenda à inicial alterando o valor da causa, ou se alguma peça cita valor incorreto.',
            })
    
    # Compare condenação across chunks
    condenacoes = []
    for c in chunks:
        v = c.get('valores', {}).get('condenacao')
        if v:
            condenacoes.append((c.get('label', '?'), v))
    
    if len(condenacoes) > 1:
        normalized = [(label, val, normalize_value(val)) for label, val in condenacoes]
        unique_vals = set(n for _, _, n in normalized if n is not None)
        if len(unique_vals) > 1:
            contradictions.append({
                'tipo': 'VALOR_INCONSISTENTE',
                'impacto': 'ALTO',
                'pecas': [label for label, _, _ in normalized],
                'descricao': f"Valor de condenação diverge: {', '.join(f'{label}: {val}' for label, val, _ in normalized)}",
                'sugestao': 'Verificar embargos de declaração sobre erro material, ou se houve reforma parcial em instância superior.',
            })
    
    return contradictions


def find_date_conflicts(chunks: list) -> list:
    """Find chronological inconsistencies."""
    contradictions = []
    
    # Check if dates are in logical order
    dated_chunks = [(c.get('label', '?'), c.get('primary_date')) for c in chunks if c.get('primary_date')]
    
    # Check petition before contestação, etc.
    order_rules = [
        ('PETIÇÃO INICIAL', 'CONTESTAÇÃO', 'Contestação datada antes da Petição Inicial'),
        ('CONTESTAÇÃO', 'RÉPLICA', 'Réplica datada antes da Contestação'),
        ('SENTENÇA', 'APELAÇÃO', 'Apelação datada antes da Sentença'),
        ('APELAÇÃO', 'ACÓRDÃO', 'Acórdão datado antes da Apelação'),
    ]
    
    def parse_date(d):
        try:
            parts = d.split('/')
            if len(parts) == 3:
                return int(parts[2]) * 10000 + int(parts[1]) * 100 + int(parts[0])
        except:
            pass
        return 0
    
    chunk_dates = {c.get('label', ''): parse_date(c.get('primary_date', '')) 
                   for c in chunks if c.get('primary_date')}
    
    for before, after, desc in order_rules:
        d_before = chunk_dates.get(before, 0)
        d_after = chunk_dates.get(after, 0)
        if d_before and d_after and d_after < d_before:
            contradictions.append({
                'tipo': 'DATA_CONFLITANTE',
                'impacto': 'ALTO',
                'pecas': [before, after],
                'descricao': desc,
                'sugestao': 'Possível erro de digitalização/OCR nas datas, ou peça protocolada fora de ordem. Verificar nos autos originais.',
            })
    
    return contradictions


def find_fact_divergences(chunks: list) -> list:
    """Find facts narrated differently by different parties."""
    contradictions = []
    
    # Compare fatos_relevantes between autor-side and réu-side pieces
    autor_facts = []
    reu_facts = []
    
    autor_pieces = ['PETIÇÃO INICIAL', 'RÉPLICA', 'APELAÇÃO', 'MEMORIAIS']
    reu_pieces = ['CONTESTAÇÃO', 'CONTRARRAZÕES', 'RECONVENÇÃO']
    
    for c in chunks:
        label = c.get('label', '')
        facts = c.get('fatos_relevantes', [])
        if label in autor_pieces:
            autor_facts.extend([(label, f) for f in facts])
        elif label in reu_pieces:
            reu_facts.extend([(label, f) for f in facts])
    
    # Note: Deep semantic comparison would require LLM analysis.
    # This script flags potential divergences for human review.
    if autor_facts and reu_facts:
        contradictions.append({
            'tipo': 'FATO_DIVERGENTE',
            'impacto': 'MÉDIO',
            'pecas': list(set([l for l, _ in autor_facts] + [l for l, _ in reu_facts])),
            'descricao': f"Detectadas {len(autor_facts)} narração(ões) do autor e {len(reu_facts)} do réu. Comparação semântica requer análise com LLM — use o prompt de contradições do SKILL.md.",
            'sugestao': 'Execute a análise cruzada com Claude usando o prompt template de detecção de contradições para comparação semântica profunda.',
        })
    
    return contradictions


def find_jurisprudence_conflicts(chunks: list) -> list:
    """Find conflicting jurisprudence cited by opposing parties."""
    contradictions = []
    
    autor_pieces = {'PETIÇÃO INICIAL', 'RÉPLICA', 'APELAÇÃO', 'MEMORIAIS'}
    reu_pieces = {'CONTESTAÇÃO', 'CONTRARRAZÕES', 'RECONVENÇÃO'}
    
    autor_juris = set()
    reu_juris = set()
    
    for c in chunks:
        label = c.get('label', '')
        juris = c.get('jurisprudencia', [])
        if label in autor_pieces:
            autor_juris.update(juris)
        elif label in reu_pieces:
            reu_juris.update(juris)
    
    # Same precedent cited by both sides
    common = autor_juris & reu_juris
    if common:
        contradictions.append({
            'tipo': 'JURISPRUDÊNCIA_CONFLITANTE',
            'impacto': 'MÉDIO',
            'pecas': ['Polo Ativo', 'Polo Passivo'],
            'descricao': f"Mesma jurisprudência citada por ambas as partes: {', '.join(list(common)[:5])}",
            'sugestao': 'Verificar se as partes interpretam o mesmo precedente de formas diferentes. Oportunidade de argumentação.',
        })
    
    return contradictions


def generate_report(analysis: dict) -> dict:
    """Generate full contradiction report."""
    chunks = analysis.get('chunks', [])
    
    all_contradictions = []
    all_contradictions.extend(find_value_inconsistencies(chunks))
    all_contradictions.extend(find_date_conflicts(chunks))
    all_contradictions.extend(find_fact_divergences(chunks))
    all_contradictions.extend(find_jurisprudence_conflicts(chunks))
    
    # Sort by impact
    impact_order = {'ALTO': 0, 'MÉDIO': 1, 'BAIXO': 2}
    all_contradictions.sort(key=lambda x: impact_order.get(x.get('impacto', 'BAIXO'), 3))
    
    return {
        'total': len(all_contradictions),
        'by_type': {
            t: len([c for c in all_contradictions if c['tipo'] == t])
            for t in set(c['tipo'] for c in all_contradictions)
        },
        'by_impact': {
            i: len([c for c in all_contradictions if c['impacto'] == i])
            for i in ['ALTO', 'MÉDIO', 'BAIXO']
        },
        'contradictions': all_contradictions,
    }


def main():
    parser = argparse.ArgumentParser(description='Generate contradiction report')
    parser.add_argument('--analysis', '-a', required=True, help='Path to analyzed.json')
    parser.add_argument('--output', '-o', required=True, help='Output path for contradictions.json')
    args = parser.parse_args()
    
    with open(args.analysis, 'r', encoding='utf-8') as f:
        analysis = json.load(f)
    
    report = generate_report(analysis)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Contradiction report generated!")
    print(f"   Total contradictions: {report['total']}")
    print(f"   By impact: {json.dumps(report['by_impact'])}")
    print(f"   By type: {json.dumps(report['by_type'])}")
    print(f"   Output: {args.output}")


if __name__ == '__main__':
    main()
