"""
tests/test_report_formatter.py

report_formatter v4.0 단위 테스트 — LLM / API 호출 없음.
"""

import pytest
from src.graph.report_formatter import (
    format_report_v4,
    _header,
    _action_now_section,
    _signal_summary_section,
    _market_context_section,
    _analysis_rationale_section,
    _appendix_section,
    SIGNAL_EMOJI,
)
from src.schemas.agent_output import AnalysisReport


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

def _make_agent(name: str, rec: str, conf: float) -> AnalysisReport:
    return AnalysisReport(
        agent_name=name,
        recommendation=rec,
        confidence=conf,
        reasoning=["근거1", "근거2", "근거3"],
        data_sources=["소스A", "소스B"],
        prediction_basis=["정량1", "정량2"],
        risk_factors=["리스크1"],
    )


@pytest.fixture
def agents() -> list[AnalysisReport]:
    return [
        _make_agent("macro_economist",     "BUY",  0.75),
        _make_agent("kr_market_specialist","HOLD", 0.60),
        _make_agent("us_market_specialist","SELL", 0.55),
        _make_agent("quant_analyst",       "BUY",  0.70),
    ]


@pytest.fixture
def chief_buy() -> AnalysisReport:
    return AnalysisReport(
        agent_name="chief_strategist",
        recommendation="BUY",
        confidence=0.78,
        reasoning=["이유1", "이유2", "이유3"],
        data_sources=["소스X", "소스Y"],
        prediction_basis=["숫자1", "숫자2"],
        risk_factors=["리스크A"],
        entry_price=300_000.0,
        stop_loss=288_000.0,
        stop_loss_pct=-4.0,
        take_profit_1=324_000.0,
        take_profit_2=336_000.0,
        rr_ratio=2.0,
        position_size_pct=7.8,
        holding_period_weeks=2,
        entry_strategy="분할매수",
    )


@pytest.fixture
def chief_hold() -> AnalysisReport:
    return AnalysisReport(
        agent_name="chief_strategist",
        recommendation="HOLD",
        confidence=0.60,
        reasoning=["이유1", "이유2", "이유3"],
        data_sources=["소스X", "소스Y"],
        prediction_basis=["숫자1", "숫자2"],
        risk_factors=["리스크A"],
    )


@pytest.fixture
def qualified(agents) -> list[AnalysisReport]:
    return agents[:2]


@pytest.fixture
def report_buy(agents, chief_buy, qualified) -> str:
    return format_report_v4(
        ticker="005930",
        regime="bull",
        strategy="BUY",
        final=chief_buy,
        agents=agents,
        qualified_reports=qualified,
        debate_summary="Bull: 강세. Bear: 과열 우려.",
        error_log=[],
    )


@pytest.fixture
def report_hold(agents, chief_hold, qualified) -> str:
    return format_report_v4(
        ticker="005930",
        regime="sideways",
        strategy="HOLD",
        final=chief_hold,
        agents=agents,
        qualified_reports=qualified,
        debate_summary="",
        error_log=[],
    )


# ─────────────────────────────────────────────────────────
# 기본 구조 검증
# ─────────────────────────────────────────────────────────

def test_report_is_string(report_buy):
    assert isinstance(report_buy, str)


def test_report_nonempty(report_buy):
    assert len(report_buy) > 200


def test_report_has_header(report_buy):
    assert "AI 투자 리포트" in report_buy


def test_report_has_ticker(report_buy):
    assert "005930" in report_buy


def test_report_has_regime(report_buy):
    assert "BULL" in report_buy


# ─────────────────────────────────────────────────────────
# validate_report() 호환 — 필수 섹션 존재
# ─────────────────────────────────────────────────────────

def test_validate_compat_final_section(report_buy):
    """'최종 판단' 문자열이 포함돼야 validate_report() 통과."""
    assert "최종 판단" in report_buy


def test_validate_compat_agent_section(report_buy):
    """'에이전트별 분석' 문자열이 포함돼야 validate_report() 통과."""
    assert "에이전트별 분석" in report_buy


def test_validate_compat_hold_report(report_hold):
    assert "최종 판단" in report_hold
    assert "에이전트별 분석" in report_hold


# ─────────────────────────────────────────────────────────
# 섹션 1: Action Now
# ─────────────────────────────────────────────────────────

def test_action_now_buy_has_entry_price(report_buy):
    assert "300,000" in report_buy


def test_action_now_buy_has_stop_loss(report_buy):
    assert "288,000" in report_buy


def test_action_now_buy_has_take_profit_1(report_buy):
    assert "324,000" in report_buy


def test_action_now_buy_has_rr(report_buy):
    assert "2.0" in report_buy


def test_action_now_buy_has_position_pct(report_buy):
    assert "8%" in report_buy or "7%" in report_buy  # 7.8% → 8% 반올림 아님, fmt는 :.0f


def test_action_now_hold_no_entry_price(report_hold):
    assert "진입가" not in report_hold


def test_action_now_holds_correct_label(report_hold):
    assert "관망" in report_hold


def test_action_now_none_chief(agents, qualified):
    report = format_report_v4(
        ticker="005930", regime="bull", strategy="HOLD",
        final=None, agents=agents, qualified_reports=qualified,
    )
    assert "분석 결과 없음" in report


# ─────────────────────────────────────────────────────────
# 섹션 2: 에이전트 신호 요약
# ─────────────────────────────────────────────────────────

def test_signal_summary_contains_all_agents(report_buy, agents):
    for r in agents:
        assert r.agent_name in report_buy


def test_signal_summary_contains_chief(report_buy):
    assert "chief_strategist" in report_buy


def test_signal_summary_qg_mark(report_buy, agents, qualified):
    # qualified_names = {agents[0].agent_name, agents[1].agent_name}
    # agents[2] and [3] are NOT in qualified → should have ⚠️
    # The signal table uses ✅ for qualified, ⚠️ for others
    assert "✅" in report_buy
    assert "⚠️" in report_buy


# ─────────────────────────────────────────────────────────
# 섹션 3: 시장 컨텍스트
# ─────────────────────────────────────────────────────────

def test_market_context_regime(report_buy):
    assert "시장 컨텍스트" in report_buy


def test_market_context_debate_summary_included(report_buy):
    assert "Bull" in report_buy
    assert "Bear" in report_buy


def test_market_context_no_debate_if_empty(report_hold):
    assert "토론 요약" not in report_hold


# ─────────────────────────────────────────────────────────
# 섹션 4: 에이전트별 분석
# ─────────────────────────────────────────────────────────

def test_analysis_section_has_agent_names(report_buy, agents):
    for r in agents:
        assert r.agent_name in report_buy


def test_analysis_section_has_reasoning(report_buy):
    assert "근거1" in report_buy


def test_analysis_section_has_risk(report_buy):
    assert "리스크1" in report_buy


# ─────────────────────────────────────────────────────────
# 섹션 5: 부록
# ─────────────────────────────────────────────────────────

def test_appendix_has_data_sources(report_buy):
    assert "소스A" in report_buy or "소스X" in report_buy


def test_appendix_has_risk_summary(report_buy):
    assert "통합 리스크" in report_buy


def test_appendix_timestamp(report_buy):
    assert "KST" in report_buy


# ─────────────────────────────────────────────────────────
# 오류 로그
# ─────────────────────────────────────────────────────────

def test_error_log_included(agents, chief_hold, qualified):
    report = format_report_v4(
        ticker="005930", regime="bull", strategy="HOLD",
        final=chief_hold, agents=agents, qualified_reports=qualified,
        error_log=["regime_detector 타임아웃"],
    )
    assert "regime_detector 타임아웃" in report


# ─────────────────────────────────────────────────────────
# _header 단위 테스트
# ─────────────────────────────────────────────────────────

def test_header_contains_kst():
    lines = _header("005930", "bull", "BUY")
    combined = " ".join(lines)
    assert "KST" in combined


def test_header_contains_ticker():
    lines = _header("005930", "bull", "BUY")
    assert any("005930" in l for l in lines)


def test_header_contains_regime():
    lines = _header("035720", "bear", "SELL")
    assert any("BEAR" in l for l in lines)


# ─────────────────────────────────────────────────────────
# _action_now_section 단위 테스트
# ─────────────────────────────────────────────────────────

def test_action_now_section_none():
    lines = _action_now_section(None)
    assert any("결과 없음" in l for l in lines)


def test_action_now_section_buy_entry(chief_buy):
    lines = _action_now_section(chief_buy)
    combined = "\n".join(lines)
    assert "300,000" in combined
    assert "진입가" in combined


def test_action_now_section_hold(chief_hold):
    lines = _action_now_section(chief_hold)
    combined = "\n".join(lines)
    assert "관망" in combined
    assert "진입가" not in combined


# ─────────────────────────────────────────────────────────
# _signal_summary_section 정렬 검증 (SELL → HOLD → BUY)
# ─────────────────────────────────────────────────────────

def test_signal_sort_order(agents, chief_buy, qualified):
    qualified_names = {r.agent_name for r in qualified}
    lines = _signal_summary_section(agents, chief_buy, qualified_names)
    content = "\n".join(lines)
    sell_pos = content.find("SELL")
    hold_pos = content.find("HOLD")
    buy_pos  = content.find("BUY")
    # SELL이 HOLD보다 먼저, HOLD가 BUY보다 먼저 등장해야 함
    assert sell_pos < hold_pos < buy_pos
