"""Tests for scripts/risk_scorer.py"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from risk_scorer import (
    score_procedural_risk,
    score_merit_indicators,
    score_monetary_exposure,
    generate_risk_report,
)


class TestProceduralRisk:
    def test_perfect_score(self):
        analysis = {
            'chunks': [
                {'label': 'PETIÇÃO INICIAL'},
                {'label': 'CONTESTAÇÃO'},
                {'label': 'SENTENÇA'},
            ],
            'prazos_calculados': [],
            'integrity_report': {'anomalies': [], 'ocr_scores': []},
        }
        result = score_procedural_risk(analysis)
        assert result['score'] == 10.0
        assert len(result['factors']) == 0

    def test_missing_contestacao(self):
        analysis = {
            'chunks': [
                {'label': 'PETIÇÃO INICIAL'},
                {'label': 'SENTENÇA'},
            ],
        }
        result = score_procedural_risk(analysis)
        assert result['score'] < 10.0
        assert any('Contestação ausente' in f['fator'] for f in result['factors'])

    def test_vencido_prazos(self):
        analysis = {
            'chunks': [],
            'prazos_calculados': [
                {'tipo': 'contestação', 'status': 'vencido'},
            ],
        }
        result = score_procedural_risk(analysis)
        assert result['score'] < 10.0


class TestMeritIndicators:
    def test_neutral_baseline(self):
        analysis = {'chunks': [], 'contradictions': []}
        result = score_merit_indicators(analysis)
        assert result['score'] == 5.0

    def test_high_contradictions_lower_score(self):
        analysis = {
            'chunks': [],
            'contradictions': [
                {'tipo': 'FATO_DIVERGENTE', 'impacto': 'ALTO', 'descricao': 'Divergência grave'},
            ],
        }
        result = score_merit_indicators(analysis)
        assert result['score'] < 5.0

    def test_laudo_pericial_raises_score(self):
        analysis = {
            'chunks': [{'label': 'LAUDO PERICIAL'}],
            'contradictions': [],
        }
        result = score_merit_indicators(analysis)
        assert result['score'] > 5.0

    def test_sentenca_procedente_raises_score(self):
        analysis = {
            'chunks': [
                {'label': 'SENTENÇA', 'decisao': 'JULGO PROCEDENTE a ação'},
            ],
            'contradictions': [],
        }
        result = score_merit_indicators(analysis)
        assert result['score'] > 5.0


class TestMonetaryExposure:
    def test_with_values(self):
        analysis = {
            'chunks': [
                {
                    'label': 'PETIÇÃO INICIAL',
                    'valores': {'causa': 'R$ 75.000,00', 'condenacao': None, 'outros': []},
                },
                {
                    'label': 'SENTENÇA',
                    'valores': {'causa': None, 'condenacao': 'R$ 48.500,00', 'outros': []},
                },
            ],
        }
        result = score_monetary_exposure(analysis)
        assert result['max_exposure'] is not None
        assert '75' in result['max_exposure']

    def test_empty(self):
        analysis = {'chunks': []}
        result = score_monetary_exposure(analysis)
        assert result['max_exposure'] is None


class TestGenerateRiskReport:
    def test_generates_all_sections(self, sample_analyzed):
        report = generate_risk_report(sample_analyzed)
        assert 'risk_level' in report
        assert report['risk_level'] in ('ALTO', 'MÉDIO', 'BAIXO')
        assert 'overall_score' in report
        assert 'procedural_risk' in report
        assert 'merit_indicators' in report
        assert 'monetary_exposure' in report
        assert 'strategic_recommendations' in report
