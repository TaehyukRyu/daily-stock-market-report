import pytest
from src.graph.pipeline import build_pipeline
from src.schemas.agent_output import AnalysisReport


@pytest.fixture
def pipeline():
    """테스트 파이프라인 픽스쳐"""
    return build_pipeline()


@pytest.fixture
def initial_state():
    """테스트용 초기 State"""
    return {
        "ticker":             "005930",   # validate_ticker 통과용
        "market_data":        {},
        "analysis_reports":   [],
        "qualified_reports":  [],
        "reconciled_signals": [],
        "final_strategy":     "",
        "report_content":     "",
        "current_regime":     "unknown",
        "debate_summary":     "",
        "error_log":          [],
    }


class TestpipelineFlow:
    """파이프라인 전체 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_pipeline_completes_without_error(self, pipeline, initial_state):
        """파이프라인이 오류 없이 완료되는지 확인"""
        result = await pipeline.ainvoke(initial_state)
        assert result is not None

    @pytest.mark.asyncio
    async def test_market_data_is_filled(self, pipeline, initial_state):
        """data_ingest 노드가 market_data를 채우는지 확인"""
        result = await pipeline.ainvoke(initial_state)
        assert result.get("market_data") is not None

    @pytest.mark.asyncio
    async def test_analysis_reports_generated(self, pipeline, initial_state):
        """parallel_analysis 노드가 리포트를 생성하는지 확인"""
        result = await pipeline.ainvoke(initial_state)
        assert len(result.get("analysis_reports", [])) >= 1

    @pytest.mark.asyncio
    async def test_report_content_is_not_empty(self, pipeline, initial_state):
        """report_formatter 노드가 리포트 내용을 만드는지 확인"""
        result = await pipeline.ainvoke(initial_state)
        assert result.get("report_content", "") != ""


class TestAnalysisReportSchema:
    """AnalysisReport 스키마 준수 테스트"""

    @pytest.mark.asyncio
    async def test_report_confidence_range(self, pipeline, initial_state):
        """confidence 값이 0.0~1.0 사이인지 확인"""
        result = await pipeline.ainvoke(initial_state)
        for report in result.get("analysis_reports", []):
            assert 0.0 <= report.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_report_recommendation_valid(self, pipeline, initial_state):
        """recommendation이 BUY/SELL/HOLD 중 하나인지 확인"""
        result = await pipeline.ainvoke(initial_state)
        valid_recommendations = {"BUY", "SELL", "HOLD"}
        for report in result.get("analysis_reports", []):
            assert report.recommendation in valid_recommendations

    @pytest.mark.asyncio
    async def test_report_has_data_sources(self, pipeline, initial_state):
        """data_sources가 비어있지 않은지 확인"""
        result = await pipeline.ainvoke(initial_state)
        for report in result.get("analysis_reports", []):
            assert len(report.data_sources) >= 1