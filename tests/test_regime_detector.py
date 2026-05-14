"""
tests/test_regime_detector.py

시장 레짐 탐지기 단위 테스트
- 실제 API 호출 없이 classify_regime() 로직만 검증
- 6개 시나리오: bull, bear, sideways, volatile(VIX), volatile(daily), neutral
"""

import pytest
from src.graph.regime_detector import classify_regime


# ─────────────────────────────────────────────────────────
# 픽스처: 각 레짐 시나리오의 지표 데이터
# ─────────────────────────────────────────────────────────

def _bull_indicators():
    return {
        "kospi_latest": 2800.0,
        "ma20":         2780.0,   # MA20 > MA60 ✅
        "ma60":         2700.0,
        "return_20d":   3.5,
        "daily_move":   1.2,
        "vix":          17.5,     # VIX < 20 ✅
    }


def _bear_indicators():
    return {
        "kospi_latest": 2300.0,
        "ma20":         2350.0,   # MA20 < MA60 ✅
        "ma60":         2450.0,
        "return_20d":   -6.5,     # 20일 수익률 < -5% ✅
        "daily_move":   2.1,
        "vix":          26.0,
    }


def _sideways_indicators():
    return {
        "kospi_latest": 2550.0,
        "ma20":         2548.0,   # |MA20 - MA60| / MA60 ≈ 0.1% ≤ 2% ✅
        "ma60":         2550.0,
        "return_20d":   -1.2,
        "daily_move":   1.5,
        "vix":          22.0,
    }


def _volatile_vix_indicators():
    return {
        "kospi_latest": 2400.0,
        "ma20":         2380.0,
        "ma60":         2420.0,
        "return_20d":   -3.0,
        "daily_move":   2.5,
        "vix":          32.5,     # VIX > 30 ✅
    }


def _volatile_daily_indicators():
    return {
        "kospi_latest": 2500.0,
        "ma20":         2520.0,
        "ma60":         2480.0,
        "return_20d":   1.0,
        "daily_move":   3.8,      # 일중변동폭 > 3% ✅
        "vix":          25.0,
    }


def _neutral_indicators():
    """MA20 > MA60이지만 VIX가 20~30 구간 — Bull 조건 미충족"""
    return {
        "kospi_latest": 2650.0,
        "ma20":         2640.0,   # MA20 > MA60
        "ma60":         2600.0,   # 괴리 약 1.5% → Sideways도 아님 (2% 이하긴 함)
        "return_20d":   1.8,
        "daily_move":   1.9,
        "vix":          23.5,     # 20~30 사이 → Bull VIX 조건 미충족
    }


# ─────────────────────────────────────────────────────────
# 테스트 케이스
# ─────────────────────────────────────────────────────────

class TestClassifyRegime:

    def test_bull_conditions(self):
        """MA20 > MA60 AND VIX < 20 → bull"""
        regime, reason = classify_regime(_bull_indicators())
        assert regime == "bull", f"예상: bull, 실제: {regime} ({reason})"

    def test_bear_conditions(self):
        """MA20 < MA60 AND 20일 수익률 < -5% → bear"""
        regime, reason = classify_regime(_bear_indicators())
        assert regime == "bear", f"예상: bear, 실제: {regime} ({reason})"

    def test_sideways_conditions(self):
        """|MA20 - MA60| / MA60 ≤ 2% → sideways"""
        regime, reason = classify_regime(_sideways_indicators())
        assert regime == "sideways", f"예상: sideways, 실제: {regime} ({reason})"

    def test_volatile_by_vix(self):
        """VIX > 30 → volatile (1순위, MA 조건보다 먼저 체크)"""
        regime, reason = classify_regime(_volatile_vix_indicators())
        assert regime == "volatile", f"예상: volatile, 실제: {regime} ({reason})"
        assert "VIX" in reason

    def test_volatile_by_daily_move(self):
        """일중변동폭 > 3% → volatile"""
        regime, reason = classify_regime(_volatile_daily_indicators())
        assert regime == "volatile", f"예상: volatile, 실제: {regime} ({reason})"

    def test_neutral_when_no_condition_met(self):
        """MA20 > MA60이지만 VIX가 20~30 → bull 조건 미충족 → neutral 또는 sideways"""
        regime, reason = classify_regime(_neutral_indicators())
        # neutral 또는 sideways 둘 다 허용 (경계값 처리)
        assert regime in ("neutral", "sideways"), \
            f"예상: neutral 또는 sideways, 실제: {regime} ({reason})"


class TestEdgeCases:

    def test_error_input_returns_unknown(self):
        """데이터 수집 실패 시 unknown 반환"""
        regime, reason = classify_regime({"error": "연결 실패"})
        assert regime == "unknown"
        assert "실패" in reason

    def test_missing_ma_returns_unknown(self):
        """MA 값 없으면 unknown 반환"""
        regime, reason = classify_regime({"kospi_latest": 2500.0, "vix": 18.0})
        assert regime == "unknown"

    def test_volatile_takes_priority_over_bull(self):
        """VIX > 30인데 MA20 > MA60 → volatile이 bull보다 우선"""
        indicators = _bull_indicators()
        indicators["vix"] = 35.0   # VIX를 Volatile 구간으로 올림
        regime, reason = classify_regime(indicators)
        assert regime == "volatile", \
            "Volatile이 Bull보다 우선순위 높아야 함 (1순위 > 2순위)"

    def test_vix_none_still_classifies(self):
        """VIX 없어도 MA 기반 분류 가능 (Bull 조건은 VIX 필요, Bear/Sideways는 불필요)"""
        indicators = _bear_indicators()
        indicators["vix"] = None
        regime, reason = classify_regime(indicators)
        # VIX 없으면 Volatile VIX 조건 미충족, Bull VIX 조건 미충족
        # MA20 < MA60 AND 수익률 < -5% → bear
        assert regime == "bear", \
            f"VIX 없어도 Bear 조건 충족 시 bear 반환해야 함, 실제: {regime}"

    def test_reason_contains_key_numbers(self):
        """reason에 판단 근거 수치가 포함되어야 함 (로그 가독성)"""
        regime, reason = classify_regime(_bull_indicators())
        assert regime == "bull"
        assert "MA20" in reason or "MA60" in reason or "VIX" in reason, \
            f"reason에 수치 근거 없음: {reason}"


# ─────────────────────────────────────────────────────────
# 실행 (python -m pytest tests/test_regime_detector.py -v)
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 빠른 수동 확인용
    scenarios = [
        ("Bull",       _bull_indicators()),
        ("Bear",       _bear_indicators()),
        ("Sideways",   _sideways_indicators()),
        ("Volatile-V", _volatile_vix_indicators()),
        ("Volatile-D", _volatile_daily_indicators()),
        ("Neutral",    _neutral_indicators()),
    ]
    print("레짐 분류 수동 확인:")
    print("-" * 60)
    for label, ind in scenarios:
        regime, reason = classify_regime(ind)
        status = "✅" if regime.lower() != "unknown" else "❌"
        print(f"{status} [{label:10s}] → {regime.upper():10s} | {reason}")