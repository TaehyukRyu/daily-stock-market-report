"""
Macro Economist 에이전트 통합 테스트
실제 MCP 서버 + 실제 LLM 호출 (네트워크 필요)
"""

import pytest
import asyncio
from src.agents.macro_economist import run_macro_economist
from src.schemas.agent_output import AnalysisReport


# ─────────────────────────────────────────────────────────
# fixture: 모듈 전체에서 에이전트를 딱 1번만 실행
# ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def report():
    """Macro Economist를 1번 실행하고 모든 테스트가 결과를 공유"""
    return asyncio.get_event_loop().run_until_complete(run_macro_economist())


# ─────────────────────────────────────────────────────────
# 테스트 (모두 fixture에서 결과를 받음 — API 호출 없음)
# ─────────────────────────────────────────────────────────

def test_macro_economist_returns_analysis_report(report):
    assert isinstance(report, AnalysisReport)

def test_macro_economist_agent_name(report):
    assert report.agent_name != ""

def test_macro_economist_recommendation_valid(report):
    assert report.recommendation in ("BUY", "SELL", "HOLD")

def test_macro_economist_confidence_range(report):
    assert 0.0 <= report.confidence <= 1.0

def test_macro_economist_reasoning_chain(report):
    """Quality Gate 기준: reasoning 3단계 이상"""
    assert len(report.reasoning) >= 3

def test_macro_economist_data_sources(report):
    """단일 출처 편향 방지: 2개 이상"""
    assert len(report.data_sources) >= 2

def test_macro_economist_prediction_basis(report):
    assert len(report.prediction_basis) >= 2

def test_macro_economist_risk_factors(report):
    """Bull/Bear 토론 입력: 1개 이상"""
    assert len(report.risk_factors) >= 1