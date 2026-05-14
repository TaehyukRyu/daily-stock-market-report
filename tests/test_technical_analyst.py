import pytest
import asyncio
from src.agents.technical_analyst import run_technical_analyst
from src.schemas.agent_output import AnalysisReport


@pytest.fixture(scope="module")
def report():
    return asyncio.get_event_loop().run_until_complete(run_technical_analyst())


def test_returns_analysis_report(report):
    assert isinstance(report, AnalysisReport)


def test_agent_name(report):
    assert report.agent_name != ""


def test_recommendation_valid(report):
    assert report.recommendation in ("BUY", "SELL", "HOLD")


def test_confidence_range(report):
    assert 0.0 <= report.confidence <= 1.0


def test_reasoning_chain(report):
    assert len(report.reasoning) >= 3


def test_data_sources(report):
    assert len(report.data_sources) >= 2


def test_prediction_basis(report):
    assert len(report.prediction_basis) >= 2


def test_risk_factors(report):
    assert len(report.risk_factors) >= 1


def test_selection_rationale_filled(report):
    assert report.selection_rationale is not None
    assert len(report.selection_rationale) > 0