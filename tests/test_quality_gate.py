"""
tests/test_quality_gate.py

Quality Gate 노드 단위 테스트.
LLM/MCP 호출 없이 순수 필터링 로직만 검증한다.
"""

import pytest
from src.schemas.agent_output import AnalysisReport
from src.schemas.graph_state   import GraphState
from src.graph.quality_gate    import (
    _check_report,
    quality_gate_node,
    CONFIDENCE_MIN,
    REASONING_MIN,
    DATA_SOURCES_MIN,
    MIN_QUALIFIED,
)


# ──────────────────────────────────────────
# 픽스처: 보고서 생성 헬퍼
# ──────────────────────────────────────────

def make_report(
    name:           str   = "test_agent",
    confidence:     float = 0.8,
    n_reasoning:    int   = 3,
    n_sources:      int   = 2,
    recommendation: str   = "BUY",
) -> AnalysisReport:
    """
    Pydantic 검증을 통과하는 정상 보고서 생성 헬퍼.
    n_reasoning < 3 또는 n_sources < 2를 넘기면 ValidationError 발생.
    → 정상 흐름 테스트에 사용.
    """
    return AnalysisReport(
        agent_name=name,
        confidence=confidence,
        recommendation=recommendation,
        reasoning=[f"추론 {i+1}" for i in range(n_reasoning)],
        data_sources=[f"출처{i+1}" for i in range(n_sources)],
        prediction_basis=["근거1", "근거2"],
        risk_factors=["리스크1"],
    )


def make_report_raw(
    name:           str   = "test_agent",
    confidence:     float = 0.8,
    n_reasoning:    int   = 3,
    n_sources:      int   = 2,
    recommendation: str   = "BUY",
) -> AnalysisReport:
    """
    Pydantic 검증을 우회하는 보고서 생성 헬퍼 (model_construct 사용).

    model_construct()는 Pydantic v2의 검증 우회 생성자다.
    reasoning=2개, data_sources=1개 같은 "원래 만들 수 없는" 객체를
    의도적으로 생성할 때 사용한다.

    → _check_report의 reasoning/data_sources 체크가
      방어적 중복 코드로서 올바로 동작하는지 검증할 때 사용.
    """
    return AnalysisReport.model_construct(
        agent_name=name,
        confidence=confidence,
        recommendation=recommendation,
        reasoning=[f"추론 {i+1}" for i in range(n_reasoning)],
        data_sources=[f"출처{i+1}" for i in range(n_sources)],
        prediction_basis=["근거1", "근거2"],
        risk_factors=["리스크1"],
    )


def make_state(reports: list[AnalysisReport]) -> GraphState:
    return GraphState(analysis_reports=reports)


# ──────────────────────────────────────────
# 1. _check_report 단위 테스트
# ──────────────────────────────────────────

class TestCheckReport:

    def test_passes_when_all_conditions_met(self):
        """세 조건 모두 충족하면 통과."""
        ok, failures = _check_report(make_report(confidence=0.6, n_reasoning=3, n_sources=2))
        assert ok is True
        assert failures == []

    def test_fails_low_confidence(self):
        """confidence < 0.6이면 탈락."""
        ok, failures = _check_report(make_report(confidence=0.59))
        assert ok is False
        assert any("confidence" in f for f in failures)

    def test_fails_insufficient_reasoning(self):
        """reasoning 2단계이면 탈락.
        Pydantic min_length=3을 우회하기 위해 make_report_raw 사용.
        이 조건은 방어적 중복 체크 — 런타임에서는 발동되지 않지만 로직 자체는 검증한다.
        """
        ok, failures = _check_report(make_report_raw(n_reasoning=2))
        assert ok is False
        assert any("reasoning" in f for f in failures)

    def test_fails_insufficient_sources(self):
        """data_sources 1개이면 탈락.
        Pydantic min_length=2를 우회하기 위해 make_report_raw 사용.
        """
        ok, failures = _check_report(make_report_raw(n_sources=1))
        assert ok is False
        assert any("data_sources" in f for f in failures)

    def test_fails_multiple_conditions(self):
        """여러 조건 동시 실패 시 모두 failure_reasons에 포함.
        Pydantic 제약을 동시에 우회하기 위해 make_report_raw 사용.
        """
        ok, failures = _check_report(make_report_raw(confidence=0.3, n_reasoning=1, n_sources=1))
        assert ok is False
        assert len(failures) == 3

    def test_boundary_confidence_exact(self):
        """confidence = 0.6 경계값은 통과."""
        ok, _ = _check_report(make_report(confidence=0.6))
        assert ok is True

    def test_boundary_confidence_just_below(self):
        """confidence = 0.599는 탈락."""
        ok, _ = _check_report(make_report(confidence=0.599))
        assert ok is False


# ──────────────────────────────────────────
# 2. quality_gate_node 통합 테스트
# ──────────────────────────────────────────

class TestQualityGateNode:

    @pytest.mark.asyncio
    async def test_filters_low_confidence_reports(self):
        """낮은 confidence 에이전트는 qualified_reports에서 제외."""
        reports = [
            make_report("agent_a", confidence=0.8),   # 통과
            make_report("agent_b", confidence=0.4),   # 탈락
            make_report("agent_c", confidence=0.7),   # 통과
        ]
        state  = make_state(reports)
        result = await quality_gate_node(state)

        qualified_names = [r.agent_name for r in result["qualified_reports"]]
        assert "agent_a" in qualified_names
        assert "agent_c" in qualified_names
        assert "agent_b" not in qualified_names

    @pytest.mark.asyncio
    async def test_soft_fallback_when_too_few_pass(self):
        """통과 에이전트 < MIN_QUALIFIED이면 원본 전체 반환 (소프트 폴백)."""
        reports = [
            make_report("agent_a", confidence=0.3),   # 탈락
            make_report("agent_b", confidence=0.2),   # 탈락
            make_report("agent_c", confidence=0.4),   # 탈락
        ]
        state  = make_state(reports)
        result = await quality_gate_node(state)

        # 소프트 폴백 → 원본 3개 모두 반환
        assert len(result["qualified_reports"]) == 3
        # 경고 로그 포함 확인
        assert any("소프트 폴백" in log for log in result["error_log"])

    @pytest.mark.asyncio
    async def test_chief_strategist_excluded_from_filter(self):
        """chief_strategist 보고서는 필터 대상에서 제외 (아직 실행 전).
        chief_strategist는 confidence=0.0이지만 필터 대상 자체가 아니므로
        qualified_reports에 포함되지 않아야 한다.
        model_construct로 confidence=0.0 객체 생성 (ge=0.0이므로 정상이지만 명시적 우회).
        """
        reports = [
            make_report_raw("chief_strategist", confidence=0.0, n_reasoning=3, n_sources=2),
            make_report("macro_economist",  confidence=0.8),   # 통과
            make_report("quant_analyst",    confidence=0.7),   # 통과
        ]
        state  = make_state(reports)
        result = await quality_gate_node(state)

        qualified_names = [r.agent_name for r in result["qualified_reports"]]
        assert "chief_strategist" not in qualified_names

    @pytest.mark.asyncio
    async def test_all_pass_returns_all(self):
        """모두 통과하면 전체 반환."""
        reports = [make_report(f"agent_{i}", confidence=0.9) for i in range(5)]
        state   = make_state(reports)
        result  = await quality_gate_node(state)

        assert len(result["qualified_reports"]) == 5

    @pytest.mark.asyncio
    async def test_error_log_contains_failed_agents(self):
        """탈락 에이전트 이름이 error_log에 포함."""
        reports = [
            make_report("agent_good", confidence=0.9),
            make_report("agent_bad",  confidence=0.1),
            make_report("agent_ok",   confidence=0.7),
        ]
        state  = make_state(reports)
        result = await quality_gate_node(state)

        assert any("agent_bad" in log for log in result["error_log"])

    @pytest.mark.asyncio
    async def test_empty_reports_triggers_fallback(self):
        """빈 보고서 리스트는 소프트 폴백 (0 < MIN_QUALIFIED)."""
        state  = make_state([])
        result = await quality_gate_node(state)

        assert result["qualified_reports"] == []
        assert any("소프트 폴백" in log for log in result["error_log"])