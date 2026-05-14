"""
src/graph/regime_detector.py

시장 레짐 탐지기 — L4 Orchestration 신규 노드
계획서 9.1절 규칙 기반 레짐 분류기 (4단계)

레짐 분류 우선순위 (높음 → 낮음):
  1. volatile  : VIX > 30 OR 일일변동폭 > 3%        (극단 상황 최우선)
  2. bull      : 20일 MA > 60일 MA AND VIX < 20
  3. bear      : 20일 MA < 60일 MA AND 20일 수익률 < -5%
  4. sideways  : |20MA - 60MA| / 60MA ≤ 2%
  5. neutral   : 위 4가지 조건 미충족 (추세 전환 구간)
  6. unknown   : 데이터 수집 실패

[설계 노트]
- 데이터 소스: yfinance (^KS11 KOSPI, ^VIX) 직접 호출
- MCP 서버 사용 안 함 — 레짐 탐지가 완전히 자급자족(self-contained)
- Sideways의 "볼린저밴드 폭 축소" 조건은 다음 이터레이션에서 추가 예정
  (임계값 설계를 데이터 보면서 결정해야 하므로 현 버전에서 제외)
"""

import asyncio

import yfinance as yf

from src.schemas.graph_state import GraphState


# ─────────────────────────────────────────────────────────
# 분류 임계값 상수 (계획서 9.1 기준 — 한 곳에서 관리)
# ─────────────────────────────────────────────────────────

VIX_STABLE_MAX        = 20.0   # Bull 조건: VIX < 이 값
VIX_VOLATILE_MIN      = 30.0   # Volatile 진입: VIX > 이 값
MA_SIDEWAYS_BAND_PCT  = 2.0    # Sideways: 20MA ≈ 60MA 오차 ±2%
BEAR_RETURN_THRESHOLD = -5.0   # Bear: KOSPI 20일 수익률 < -5%
VOLATILE_DAILY_MOVE   = 3.0    # Volatile: 일중 변동폭 > 3%


# ─────────────────────────────────────────────────────────
# Step 1: 데이터 수집
# ─────────────────────────────────────────────────────────

def _fetch_market_indicators() -> dict:
    """KOSPI 지수와 VIX를 yfinance로 수집, 레짐 판단용 지표를 계산합니다.

    Returns:
        {
          "kospi_latest": float,
          "ma20":         float,   # 20일 이동평균
          "ma60":         float,   # 60일 이동평균
          "return_20d":   float,   # 20일 수익률 (%)
          "daily_move":   float,   # 당일 고저 변동폭 (%)
          "vix":          float | None,
        }
        또는 {"error": str} (수집 실패 시)
    """
    try:
        # KOSPI 90일 — 60일 MA를 계산하려면 최소 60거래일 필요
        # 주말/공휴일 제외하면 90 캘린더일 ≈ 60~63 거래일
        kospi = yf.Ticker("^KS11")
        hist = kospi.history(period="90d")

        if hist.empty:
            return {"error": "KOSPI(^KS11) 데이터 없음 — yfinance 응답 확인 필요"}
        if len(hist) < 60:
            return {"error": f"KOSPI 데이터 부족: {len(hist)}일 (60일 이상 필요)"}

        close = hist["Close"]

        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])

        latest       = float(close.iloc[-1])
        price_20d    = float(close.iloc[-20])
        return_20d   = (latest - price_20d) / price_20d * 100

        # 일중 변동폭: (고가 - 저가) / 저가 × 100 — 극단 변동성 포착
        today_row  = hist.iloc[-1]
        daily_move = (float(today_row["High"]) - float(today_row["Low"])) / float(today_row["Low"]) * 100

        # VIX — 별도 호출 (실패해도 KOSPI 지표는 유효)
        vix_value = None
        try:
            vix_hist = yf.Ticker("^VIX").history(period="5d")
            if not vix_hist.empty:
                vix_value = float(vix_hist["Close"].iloc[-1])
        except Exception:
            pass  # VIX 없어도 MA 기반 분류는 가능

        return {
            "kospi_latest": round(latest, 2),
            "ma20":         round(ma20, 2),
            "ma60":         round(ma60, 2),
            "return_20d":   round(return_20d, 2),
            "daily_move":   round(daily_move, 2),
            "vix":          round(vix_value, 2) if vix_value is not None else None,
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────
# Step 2: 레짐 분류
# ─────────────────────────────────────────────────────────

def classify_regime(indicators: dict) -> tuple[str, str]:
    """수집된 지표로 시장 레짐을 분류합니다.

    Args:
        indicators: _fetch_market_indicators() 반환값

    Returns:
        (regime, reason)
        - regime: "bull" | "bear" | "sideways" | "volatile" | "neutral" | "unknown"
        - reason: 판단 근거 한 줄 요약 (로그/디버그용)
    """
    if "error" in indicators:
        return "unknown", f"데이터 수집 실패: {indicators['error']}"

    ma20       = indicators.get("ma20")
    ma60       = indicators.get("ma60")
    return_20d = indicators.get("return_20d")
    daily_move = indicators.get("daily_move")
    vix        = indicators.get("vix")

    if ma20 is None or ma60 is None:
        return "unknown", "이동평균 계산 불가"

    # ── 1순위: Volatile ─────────────────────────────────────
    # VIX > 30 OR 일중변동폭 > 3% — 둘 중 하나만 충족해도 Volatile
    volatile_vix   = vix is not None and vix > VIX_VOLATILE_MIN
    volatile_daily = daily_move is not None and daily_move > VOLATILE_DAILY_MOVE
    if volatile_vix or volatile_daily:
        reasons = []
        if volatile_vix:
            reasons.append(f"VIX {vix:.1f} > {VIX_VOLATILE_MIN}")
        if volatile_daily:
            reasons.append(f"일중변동폭 {daily_move:.1f}% > {VOLATILE_DAILY_MOVE}%")
        return "volatile", " / ".join(reasons)

    # ── 2순위: Bull ──────────────────────────────────────────
    # 20MA > 60MA AND VIX < 20 (둘 다 충족해야 Bull)
    bull_ma  = ma20 > ma60
    bull_vix = vix is not None and vix < VIX_STABLE_MAX
    if bull_ma and bull_vix:
        return "bull", (
            f"MA20({ma20:,.0f}) > MA60({ma60:,.0f}), "
            f"VIX {vix:.1f} < {VIX_STABLE_MAX}"
        )

    # ── 3순위: Bear ──────────────────────────────────────────
    # 20MA < 60MA AND 20일 수익률 < -5% (둘 다 충족해야 Bear)
    bear_ma     = ma20 < ma60
    bear_return = return_20d is not None and return_20d < BEAR_RETURN_THRESHOLD
    if bear_ma and bear_return:
        return "bear", (
            f"MA20({ma20:,.0f}) < MA60({ma60:,.0f}), "
            f"20일수익률 {return_20d:.1f}% < {BEAR_RETURN_THRESHOLD}%"
        )

    # ── 4순위: Sideways ──────────────────────────────────────
    # |MA20 - MA60| / MA60 ≤ 2% — 두 이평선이 수렴 상태
    # 볼린저밴드 폭 축소 조건은 다음 이터레이션에서 추가 예정
    ma_gap_pct = abs(ma20 - ma60) / ma60 * 100
    if ma_gap_pct <= MA_SIDEWAYS_BAND_PCT:
        return "sideways", (
            f"MA20/60 괴리 {ma_gap_pct:.1f}% ≤ {MA_SIDEWAYS_BAND_PCT}% "
            f"(볼린저밴드 조건은 다음 이터레이션 추가 예정)"
        )

    # ── 5순위: Neutral ───────────────────────────────────────
    # 위 4가지 조건 미충족 — 추세 전환 중이거나 조건이 애매한 구간
    # 예시: MA20 > MA60이지만 VIX가 20~30 사이 (Bull 조건 미충족)
    #       MA20 < MA60이지만 20일 수익률 -3% (Bear 조건 미충족)
    direction = "상승배열" if ma20 > ma60 else "하락배열" if ma20 < ma60 else "수렴"
    return "neutral", (
        f"MA배열={direction}, MA괴리={ma_gap_pct:.1f}%, "
        f"20일수익률={return_20d:.1f}% — 명확한 레짐 조건 미충족"
    )


# ─────────────────────────────────────────────────────────
# LangGraph 노드
# ─────────────────────────────────────────────────────────

async def regime_detector_node(state: GraphState) -> dict:
    """
    LangGraph 노드 — 시장 레짐 탐지.

    위치: data_ingest → [regime_detector] → parallel_analysis

    입력:  GraphState (state.market_data는 참조하지 않음 — 자체 수집)
    출력:  {"current_regime": str}
    사이드이펙트 없음 (외부 쓰기 없음, 순수 계산 노드)
    """
    print(f"\n[1.5/5] regime_detector — 시장 레짐 탐지")

    indicators = await asyncio.to_thread(_fetch_market_indicators)
    regime, reason = classify_regime(indicators)

    # ── 콘솔 출력 (파이프라인 진행 상황용) ────────────────
    print(f"  → 레짐: {regime.upper()}")
    print(f"     근거: {reason}")
    if "error" not in indicators:
        kospi = indicators.get("kospi_latest", "N/A")
        ma20  = indicators.get("ma20", "N/A")
        ma60  = indicators.get("ma60", "N/A")
        r20   = indicators.get("return_20d", "N/A")
        vix   = indicators.get("vix", "N/A")
        print(f"     KOSPI: {kospi:,.2f}  MA20: {ma20:,.0f}  MA60: {ma60:,.0f}")
        print(f"     20일수익률: {r20:.1f}%  VIX: {vix if vix != 'N/A' else '조회실패'}")

    return {"current_regime": regime}