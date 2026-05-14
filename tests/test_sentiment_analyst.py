"""
Sentiment Analyst 에이전트 통합 테스트
실제 MCP 서버 + 실제 LLM 호출 (네트워크 필요)
"""

import pytest
import asyncio
from src.agents.sentiment_analyst import run_sentiment_analyst
from src.schemas.agent_output import AnalysisReport


@pytest.fixture(scope="module")
def report():
    return asyncio.get_event_loop().run_until_complete(run_sentiment_analyst())


def test_sentiment_analyst_returns_analysis_report(report):
    assert isinstance(report, AnalysisReport)

def test_sentiment_analyst_agent_name(report):
    assert report.agent_name != ""

def test_sentiment_analyst_recommendation_valid(report):
    assert report.recommendation in ("BUY", "SELL", "HOLD")

def test_sentiment_analyst_confidence_range(report):
    assert 0.0 <= report.confidence <= 1.0

def test_sentiment_analyst_reasoning_chain(report):
    assert len(report.reasoning) >= 3

def test_sentiment_analyst_data_sources(report):
    assert len(report.data_sources) >= 2

def test_sentiment_analyst_prediction_basis(report):
    assert len(report.prediction_basis) >= 2

def test_sentiment_analyst_risk_factors(report):
    assert len(report.risk_factors) >= 1