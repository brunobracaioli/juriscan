#!/usr/bin/env python3
"""
prazo_calculator.py — CPC-compliant procedural deadline calculator.

Implements CPC Art. 219-232 rules:
- Business day counting (Art. 219)
- Start/end rules (Art. 224)
- Court holidays (forense) + state holidays
- Recesso forense (Art. 220): Dec 20 - Jan 20
- Suspension ranges

Usage:
    python3 prazo_calculator.py --analysis analyzed.json --output prazos.json
    python3 prazo_calculator.py --date 2025-03-15 --tipo contestação --state SP
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from typing import Literal

REFERENCES_DIR = os.path.join(os.path.dirname(__file__), '..', 'references')


def _easter(year: int) -> date:
    """Calculate Easter Sunday using Butcher/Meeus algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def load_feriados(state: str | None = None, year: int | None = None) -> set[date]:
    """Load court holidays for a given year (defaults to current year).

    Includes: national fixed + mobile (Easter-based) + optional state holidays.
    """
    if year is None:
        year = date.today().year

    feriados_path = os.path.join(REFERENCES_DIR, 'feriados_forenses.json')
    with open(feriados_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    holidays: set[date] = set()

    # National fixed holidays
    for h in data.get('nacionais_fixos', []):
        try:
            holidays.add(date(year, h['mes'], h['dia']))
        except ValueError:
            continue

    # Mobile holidays (Easter-based)
    easter = _easter(year)
    offsets = data.get('moveis', {}).get('offsets_from_easter', {})
    for name, offset in offsets.items():
        holidays.add(easter + timedelta(days=offset))

    # State holidays
    if state:
        state_holidays = data.get('estaduais', {}).get(state.upper(), [])
        for h in state_holidays:
            try:
                holidays.add(date(year, h['mes'], h['dia']))
            except ValueError:
                continue

    return holidays


def is_recesso(d: date) -> bool:
    """Check if a date falls within the recesso forense (CPC Art. 220).

    Recesso: Dec 20 to Jan 20 (inclusive).
    """
    if d.month == 12 and d.day >= 20:
        return True
    if d.month == 1 and d.day <= 20:
        return True
    return False


def is_business_day(d: date, feriados: set[date]) -> bool:
    """Check if a date is a business day (dia útil forense)."""
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    if d in feriados:
        return False
    if is_recesso(d):
        return False
    return True


def next_business_day(d: date, feriados: set[date]) -> date:
    """Find the next business day on or after the given date.

    CPC Art. 224 §1: if deadline falls on non-business day, extends to next business day.
    """
    while not is_business_day(d, feriados):
        d += timedelta(days=1)
    return d


def calculate_prazo(
    start_date: date,
    days: int,
    unit: Literal['úteis', 'corridos'] = 'úteis',
    feriados: set[date] | None = None,
    suspended_ranges: list[tuple[date, date]] | None = None,
) -> date:
    """Calculate procedural deadline per CPC rules.

    CPC Art. 224: Exclude start day, include end day.
    CPC Art. 219: Count only business days (for 'úteis').
    CPC Art. 224 §1: If deadline falls on non-business day, extend to next business day.

    Args:
        start_date: Date of intimation/publication (dia do começo — excluded).
        days: Number of days for the deadline.
        unit: 'úteis' (business days) or 'corridos' (calendar days).
        feriados: Set of holiday dates.
        suspended_ranges: List of (start, end) suspension periods.
    """
    if feriados is None:
        feriados = set()

    def is_suspended(d: date) -> bool:
        if suspended_ranges:
            return any(start <= d <= end for start, end in suspended_ranges)
        return False

    current = start_date
    counted = 0

    if unit == 'úteis':
        while counted < days:
            current += timedelta(days=1)
            if is_suspended(current):
                continue
            if is_business_day(current, feriados):
                counted += 1
    else:  # corridos
        while counted < days:
            current += timedelta(days=1)
            if is_suspended(current):
                continue
            counted += 1
        # Even for corridos, deadline must end on business day
        current = next_business_day(current, feriados)

    return current


def get_standard_prazo(tipo: str) -> dict | None:
    """Look up the standard CPC deadline for a procedural act."""
    prazos_path = os.path.join(REFERENCES_DIR, 'cpc_prazos.json')
    with open(prazos_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tipo_normalized = tipo.lower().strip().replace(' ', '_')

    for prazo in data.get('prazos_legais', []):
        if prazo['ato'] == tipo_normalized:
            return prazo

    # Fuzzy match
    for prazo in data.get('prazos_legais', []):
        if tipo_normalized in prazo['ato'] or prazo['ato'] in tipo_normalized:
            return prazo

    return None


def check_prazo_status(
    intimation_date: date,
    prazo_type: str,
    current_date: date | None = None,
    state: str | None = None,
) -> dict | None:
    """Check the status of a procedural deadline.

    Returns dict with deadline, days_remaining, and status.
    """
    if current_date is None:
        current_date = date.today()

    prazo_info = get_standard_prazo(prazo_type)
    if not prazo_info:
        return None

    # Load holidays for both the intimation year and deadline year
    feriados = load_feriados(state, intimation_date.year)
    if intimation_date.year != current_date.year:
        feriados |= load_feriados(state, current_date.year)

    deadline = calculate_prazo(
        start_date=intimation_date,
        days=prazo_info['dias'],
        unit=prazo_info['unidade'],
        feriados=feriados,
    )

    days_remaining = None
    if current_date <= deadline:
        # Count business days remaining
        d = current_date
        count = 0
        while d < deadline:
            d += timedelta(days=1)
            if is_business_day(d, feriados):
                count += 1
        days_remaining = count

    if current_date > deadline:
        status = 'vencido'
    elif current_date == deadline:
        status = 'ultimo_dia'
    else:
        status = 'em_prazo'

    return {
        'tipo': prazo_type,
        'fundamento_legal': prazo_info['fundamento'],
        'data_intimacao': intimation_date.isoformat(),
        'data_limite': deadline.isoformat(),
        'dias': prazo_info['dias'],
        'unidade': prazo_info['unidade'],
        'status': status,
        'dias_restantes': days_remaining,
    }


def main():
    parser = argparse.ArgumentParser(description='CPC Prazo Calculator')
    parser.add_argument('--date', '-d', help='Intimation date (YYYY-MM-DD)')
    parser.add_argument('--tipo', '-t', help='Prazo type (e.g., contestação, apelação)')
    parser.add_argument('--state', '-s', help='State for holidays (e.g., SP, RJ)')
    parser.add_argument('--analysis', '-a', help='Path to analyzed.json for batch calculation')
    parser.add_argument('--output', '-o', help='Output path for prazos.json')
    args = parser.parse_args()

    if args.date and args.tipo:
        # Single calculation mode
        intimation = date.fromisoformat(args.date)
        result = check_prazo_status(intimation, args.tipo, state=args.state)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[ERROR] Unknown prazo type: {args.tipo}", file=sys.stderr)
            sys.exit(1)
    elif args.analysis:
        # Batch mode from analyzed.json
        with open(args.analysis, 'r', encoding='utf-8') as f:
            analysis = json.load(f)

        prazos = []
        for chunk in analysis.get('chunks', []):
            for prazo in chunk.get('prazos', []):
                tipo = prazo.get('tipo', '')
                start = prazo.get('data_inicio')
                if start:
                    from utils.dates import parse_brazilian_date
                    d = parse_brazilian_date(start)
                    if d:
                        result = check_prazo_status(d, tipo, state=args.state)
                        if result:
                            prazos.append(result)

        output_path = args.output or os.path.join(os.path.dirname(args.analysis), 'prazos.json')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(prazos, f, ensure_ascii=False, indent=2)

        print(f"Calculated {len(prazos)} deadline(s). Output: {output_path}")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
