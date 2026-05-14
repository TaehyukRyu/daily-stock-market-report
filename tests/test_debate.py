"""
tests/test_debate.py

토론 메커니즘 단위 테스트 — API 호출 없이 should_debate 로직만 검증
"""

import pytest
from src.agents.debate import should_debate, _collect_side_context, DEBATE_THRESHOLD
from src.schemas.agent_output import AnalysisReport


# ─────────────────────────────────────────────────────────
# 픽스처: 시나리오별 에이전트 보고서
# ─────────────────────────────────────────────────────────

def _make_report(name: str, rec: str, conf: float) -> AnalysisReport:
    return AnalysisReport(
        agent_name=name,
        recommendation=rec,
        confidence=conf,
        reasoning=["관찰", "함의", f"{rec} 결론"],
        data_sources=["source_a", "source_b"],
        prediction_basis=[f"{name} 수치 근거 1", f"{name} 수치 근거 2"],
        risk_factors=[f"{name} 리스크"],
    )


# 시나리오 1: 한쪽 압도적 우세 — 토론 불필요
# 방금 파이프라인 실행 결과와 유사 (SELL 2.45 vs BUY 0.85)
def _reports_sell_dominant():
    return [
        _make_report("kr_market",   "SELL", 0.80),
        _make_report("fundamental", "SELL", 0.80),
        _make_report("sentiment",   "SELL", 0.85),
        _make_report("quant",       "BUY",  0.85),
        _make_report("technical",   "HOLD", 0.85),
        _make_report("macro",       "HOLD", 0.60),
        _make_report("us_market",   "HOLD", 0.85),
    ]


# 시나리오 2: 팽팽한 분열 — 토론 필요
def _reports_tight_split():
    return [
        _make_report("quant",       "BUY",  0.85),
        _make_report("macro",       "BUY",  0.70),
        _make_report("us_market",   "BUY",  0.75),
        _make_report("fundamental", "SELL", 0.80),
        _make_report("kr_market",   "SELL", 0.75),
        _make_report("technical",   "HOLD", 0.85),
        _make_report("sentiment",   "HOLD", 0.60),
    ]


# 시나리오 3: HOLD 다수 — 토론 필요 (BUY-SELL 차이 작음)
def _reports_hold_majority():
    return [
        _make_report("quant",       "BUY",  0.80),
        _make_report("macro",       "SELL", 0.80),
        _make_report("technical",   "HOLD", 0.85),
        _make_report("fundamental", "HOLD", 0.80),
        _make_report("kr_market",   "HOLD", 0.85),
        _make_report("us_market",   "HOLD", 0.85),
        _make_report("sentiment",   "HOLD", 0.60),
    ]


# 시나리오 4: 전원 BUY — 토론 불필요
def _reports_all_buy():
    return [_make_report(f"agent_{i}", "BUY", 0.80) for i in range(7)]


# ─────────────────────────────────────────────────────────
# should_debate 테스트
# ─────────────────────────────────────────────────────────

class TestShouldDebate:

    def test_sell_dominant_no_debate(self):
        """SELL 2.45 vs BUY 0.85 → 차이 1.6 ≥ 1.0 → 토론 불필요"""
        reports = _reports_sell_dominant()
        buy_w  = sum(r.confidence for r in reports if r.recommendation == "BUY")
        sell_w = sum(r.confidence for r in reports if r.recommendation == "SELL")
        assert abs(buy_w - sell_w) >= DEBATE_THRESHOLD
        assert should_debate(reports) is False

    def test_tight_split_needs_debate(self):
        """BUY ≈ SELL → 차이 작음 → 토론 필요"""
        reports = _reports_tight_split()
        assert should_debate(reports) is True

    def test_hold_majority_needs_debate(self):
        """BUY 1개 vs SELL 1개 → 차이 0.0 → 토론 필요"""
        reports = _reports_hold_majority()
        assert should_debate(reports) is True

    def test_all_buy_no_debate(self):
        """전원 BUY → 차이 큼 → 토론 불필요"""
        reports = _reports_all_buy()
        assert should_debate(reports) is False

    def test_empty_reports_no_debate(self):
        """빈 리스트 → 차이 0.0 < 1.0 → should_debate True 반환
        (실제로는 bull_reports or bear_reports 없어서 run_debate에서 조기 종료)"""
        assert should_debate([]) is True  # 차이 0이므로 True


# ─────────────────────────────────────────────────────────
# _collect_side_context 테스트
# ─────────────────────────────────────────────────────────

class TestCollectSideContext:

    def test_empty_list_returns_message(self):
        """빈 진영은 메시지 반환"""
        result = _collect_side_context([])
        assert "없음" in result

    def test_context_contains_agent_name(self):
        """에이전트 이름이 컨텍스트에 포함됨"""
        reports = [_make_report("quant_analyst", "BUY", 0.85)]
        result = _collect_side_context(reports)
        assert "quant_analyst" in result

    def test_context_contains_confidence(self):
        """확신도가 컨텍스트에 포함됨"""
        reports = [_make_report("quant_analyst", "BUY", 0.85)]
        result = _collect_side_context(reports)
        assert "0.85" in result

    def test_context_contains_prediction_basis(self):
        """수치 근거가 포함됨"""
        reports = [_make_report("quant_analyst", "BUY", 0.85)]
        result = _collect_side_context(reports)
        assert "수치 근거" in result


# ─────────────────────────────────────────────────────────
# 수동 확인용 (pytest 외 직접 실행)
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    scenarios = [
        ("SELL 압도적 우세 (토론 불필요)", _reports_sell_dominant()),
        ("팽팽한 분열 (토론 필요)",        _reports_tight_split()),
        ("HOLD 다수 (토론 필요)",          _reports_hold_majority()),
        ("전원 BUY (토론 불필요)",         _reports_all_buy()),
    ]

    print(f"DEBATE_THRESHOLD = {DEBATE_THRESHOLD}\n")
    print("-" * 60)
    for label, reports in scenarios:
        buy_w  = sum(r.confidence for r in reports if r.recommendation == "BUY")
        sell_w = sum(r.confidence for r in reports if r.recommendation == "SELL")
        hold_w = sum(r.confidence for r in reports if r.recommendation == "HOLD")
        diff   = abs(buy_w - sell_w)
        result = should_debate(reports)
        status = "🔥 토론" if result else "⏭️  생략"
        print(f"{status} | {label}")
        print(f"       BUY {buy_w:.2f} / SELL {sell_w:.2f} / HOLD {hold_w:.2f} (차이 {diff:.2f})")
        print()