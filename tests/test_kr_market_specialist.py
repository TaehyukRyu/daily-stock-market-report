"""
KR Market Specialist 에이전트 통합 테스트
실제 MCP 서버 + 실제 LLM 호출 (네트워크 필요)
"""

import pytest
import asyncio
from src.agents.kr_market_specialist import run_kr_market_specialist
from src.schemas.agent_output import AnalysisReport


@pytest.fixture(scope="module")
def report():
    """KR Market Specialist를 1번 실행하고 모든 테스트가 결과를 공유"""
    return asyncio.get_event_loop().run_until_complete(run_kr_market_specialist())


def test_kr_market_returns_analysis_report(report):
    assert isinstance(report, AnalysisReport)

def test_kr_market_agent_name(report):
    assert report.agent_name != ""

def test_kr_market_recommendation_valid(report):
    assert report.recommendation in ("BUY", "SELL", "HOLD")

def test_kr_market_confidence_range(report):
    assert 0.0 <= report.confidence <= 1.0

def test_kr_market_reasoning_chain(report):
    """Quality Gate 기준: reasoning 3단계 이상"""
    assert len(report.reasoning) >= 3

def test_kr_market_data_sources(report):
    """단일 출처 편향 방지: 2개 이상"""
    assert len(report.data_sources) >= 2

def test_kr_market_prediction_basis(report):
    assert len(report.prediction_basis) >= 2

def test_kr_market_risk_factors(report):
    """Bull/Bear 토론 입력: 1개 이상"""
    assert len(report.risk_factors) >= 1

def test_kr_market_selection_rationale_filled(report):
    """KR Market은 종목 선별 역할 — selection_rationale이 None이 아닌지 확인"""
    assert report.selection_rationale is not None
    assert len(report.selection_rationale) > 0