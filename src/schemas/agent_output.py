from pydantic import BaseModel, Field
from typing import Literal, Optional


class AnalysisReport(BaseModel):
    """8개 전문가 에이전트가 공통으로 출력하는 분석 보고서 스키마.

    LangChain의 with_structured_output()으로 LLM 출력을 강제한다.
    Quality Gate (계획서 8.2절 Pattern 2): confidence ≥ 0.6, reasoning ≥ 3단계,
    data_sources ≥ 2개 인용이 통과 조건이다.
    """

    agent_name: str = Field(
        description="에이전트 식별자. 예: 'macro_economist', 'kr_market_specialist'"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="이 분석의 확신도. 0.0(전혀 확신 없음) ~ 1.0(매우 확신). "
                    "근거가 약하거나 데이터가 충돌할 때는 반드시 0.6 미만으로 낮출 것."
    )

    recommendation: Literal['BUY', 'SELL', 'HOLD'] = Field(
        description="투자 판단. BUY=매수 우호, SELL=매도 우호, HOLD=관망. "
                    "거시 에이전트는 시장 환경 판단을 BUY(리스크 ON)/SELL(리스크 OFF)/HOLD로 표현."
    )

    reasoning: list[str] = Field(
        min_length=3,
        description="Chain-of-Thought 형식의 사고 흐름을 단계별로 작성. "
                    "각 항목은 한 단계의 추론. 최소 3단계 이상 필수. "
                    "예: ['관찰 1', '관찰 1로부터 도출되는 함의', '결론']"
    )

    data_sources: list[str] = Field(
        min_length=2,
        description="이 분석에 실제로 사용한 데이터 출처. "
                    "예: ['FRED DGS10 (4월 30일)', 'BOK ECOS 기준금리 (4월 25일)']. "
                    "단일 출처 의존을 막기 위해 최소 2개 이상 필수."
    )

    selection_rationale: Optional[str] = Field(
        default=None,
        description="특정 종목을 선별한 이유. 종목 단위로 판단하는 에이전트만 작성. "
                    "거시 에이전트처럼 시장 전체를 보는 경우 None으로 둘 것."
    )

    prediction_basis: list[str] = Field(
        min_length=2,
        description="예측을 뒷받침하는 구체적·정량적 근거. reasoning이 사고 과정이라면 "
                    "이것은 그 사고의 출발점이 된 실제 숫자/사실. "
                    "예: ['DXY 102.5, 전월 대비 -2.3%', '미 10Y 금리 4.0%, 60일 평균 대비 -20bp']. "
                    "최소 2개 이상 필수."
    )

    risk_factors: list[str] = Field(
        min_length=1,
        description="이 예측이 틀릴 수 있는 시나리오나 리스크 요인. "
                    "Bull/Bear 토론에서 Bear 측이 활용하는 핵심 입력. "
                    "예: ['미 CPI 재가속 시 금리 재상승 가능', '중국 디플레 리스크 확산 시 원화 약세']. "
                    "최소 1개 이상 필수."
    )

    # ── 거래 파라미터 (chief_strategist 전용, 나머지 에이전트는 None) ──────────
    entry_price: Optional[float] = Field(
        default=None,
        description="추천 진입가. 현재가 기준, BUY 시에만 입력."
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="손절가. 기술적 지지선 또는 현재가 × (1 + stop_loss_pct/100)."
    )
    stop_loss_pct: Optional[float] = Field(
        default=None,
        description="손절 비율(%). 음수. 예: -4.0 → -4%. 범위: -3 ~ -6."
    )
    take_profit_1: Optional[float] = Field(
        default=None,
        description="1차 익절가. 손절폭 × 2 기준 (R:R 1:2 최소 보장)."
    )
    take_profit_2: Optional[float] = Field(
        default=None,
        description="2차 익절가. 손절폭 × 3 기준 (R:R 1:3)."
    )
    rr_ratio: Optional[float] = Field(
        default=None,
        description="Risk:Reward 비율. (take_profit_1 - entry_price) / (entry_price - stop_loss)."
    )
    position_size_pct: Optional[float] = Field(
        default=None,
        description="포지션 사이즈 (시드 대비 %). confidence × 10, 최대 15."
    )
    holding_period_weeks: Optional[int] = Field(
        default=None,
        description="예상 보유 기간 (주 단위)."
    )
    entry_strategy: Optional[str] = Field(
        default=None,
        description="진입 전략. '시장가' / '분할매수' / '지정가대기' 중 하나."
    )