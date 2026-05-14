"""
Chief Strategist 에이전트 통합 테스트

다른 에이전트와 다른 점:
- MCP 호출 없음 → 빠름
- 입력이 list[AnalysisReport] → Mock 리포트로 테스트
- Mock을 쓰는 이유: 다른 에이전트 7개를 전부 실행하면
  테스트 1회에 수분 + 높은 API 비용 발생
  Chief Strategist 로직 자체는 Mock 입력으로도 완전히 검증 가능
"""

import pytest
import asyncio
from src.agents.chief_strategist import run_chief_strategist
from src.schemas.agent_output import AnalysisReport


# ─────────────────────────────────────────────────────────
# Mock 에이전트 결과 (7개 에이전트를 흉내냄)
# ─────────────────────────────────────────────────────────

MOCK_REPORTS = [
    AnalysisReport(
        agent_name="macro_economist",
        confidence=0.75,
        recommendation="BUY",
        reasoning=["미 10Y 금리 4.2%로 안정", "VIX 18 — 공포 임계선 하회", "리스크 ON 환경 판단"],
        data_sources=["FRED DGS10", "Yahoo Finance VIX"],
        prediction_basis=["미 10Y 4.2%", "VIX 18.0"],
        risk_factors=["CPI 재가속 시 금리 반등 가능"],
    ),
    AnalysisReport(
        agent_name="kr_market_specialist",
        confidence=0.70,
        recommendation="BUY",
        reasoning=["외국인 3일 연속 순매수", "삼성전자 목표주가 괴리율 +22%", "수급 긍정적"],
        data_sources=["pykrx 수급 데이터", "한경컨센서스"],
        prediction_basis=["외국인 순매수 3일 연속", "삼성전자 TP 괴리율 +22%"],
        risk_factors=["기관 동반 매도 전환 시 신호 약화"],
        selection_rationale="삼성전자 — 수급+밸류에이션 동시 긍정",
    ),
    AnalysisReport(
        agent_name="us_market_specialist",
        confidence=0.65,
        recommendation="HOLD",
        reasoning=["S&P500 단기 과매수 구간", "나스닥 RSI 72", "추가 상승 여력 제한적"],
        data_sources=["Yahoo Finance S&P500", "Yahoo Finance NASDAQ"],
        prediction_basis=["S&P500 RSI 68", "나스닥 RSI 72"],
        risk_factors=["미국 실적 시즌 어닝 서프라이즈 시 추가 상승 가능"],
    ),
    AnalysisReport(
        agent_name="quant_analyst",
        confidence=0.72,
        recommendation="BUY",
        reasoning=["KOSPI 20일 이평 돌파", "거래량 20일 평균 대비 +15%", "모멘텀 긍정"],
        data_sources=["pykrx KOSPI 일봉", "pykrx 거래량"],
        prediction_basis=["KOSPI 20일선 돌파", "거래량 +15%"],
        risk_factors=["단기 급등 후 되돌림 가능성"],
    ),
    AnalysisReport(
        agent_name="technical_analyst",
        confidence=0.68,
        recommendation="BUY",
        reasoning=["골든크로스 형성", "MACD 히스토그램 양전환", "상승 추세 유효"],
        data_sources=["pykrx 기술적 지표", "TA-Lib"],
        prediction_basis=["5일선 > 20일선 골든크로스", "MACD 양전환"],
        risk_factors=["저항선 돌파 실패 시 되돌림"],
    ),
    AnalysisReport(
        agent_name="fundamental_analyst",
        confidence=0.70,
        recommendation="BUY",
        reasoning=["삼성전자 PBR 1.1배 — 역사적 저점 근접", "SK하이닉스 EPS 상향", "밸류에이션 매력"],
        data_sources=["DART 재무제표", "한경컨센서스 EPS"],
        prediction_basis=["삼성전자 PBR 1.1배", "SK하이닉스 EPS 상향 조정"],
        risk_factors=["반도체 업황 둔화 시 EPS 하향 전환 가능"],
        selection_rationale="SK하이닉스 — EPS 상향 + 모멘텀 동반",
    ),
    AnalysisReport(
        agent_name="sentiment_analyst",
        confidence=0.60,
        recommendation="HOLD",
        reasoning=["긍정 헤드라인 55% — 과열 아님", "부정 뉴스 일부 혼재", "중립 심리"],
        data_sources=["Google News economy", "Google News finance"],
        prediction_basis=["긍정 헤드라인 55%", "부정 헤드라인 30%"],
        risk_factors=["지정학 이슈 재부각 시 심리 급반전 가능"],
    ),
]


# ─────────────────────────────────────────────────────────
# fixture: Mock 리포트로 Chief Strategist 1번 실행
# ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def report():
    return asyncio.get_event_loop().run_until_complete(
        run_chief_strategist(MOCK_REPORTS, current_price=300000.0)
    )


# ─────────────────────────────────────────────────────────
# 테스트
# ─────────────────────────────────────────────────────────

def test_chief_strategist_returns_analysis_report(report):
    assert isinstance(report, AnalysisReport)

def test_chief_strategist_agent_name(report):
    assert report.agent_name != ""

def test_chief_strategist_recommendation_valid(report):
    assert report.recommendation in ("BUY", "SELL", "HOLD")

def test_chief_strategist_confidence_range(report):
    assert 0.0 <= report.confidence <= 1.0

def test_chief_strategist_reasoning_chain(report):
    assert len(report.reasoning) >= 3

def test_chief_strategist_data_sources(report):
    assert len(report.data_sources) >= 2

def test_chief_strategist_prediction_basis(report):
    assert len(report.prediction_basis) >= 2

def test_chief_strategist_risk_factors(report):
    """반대 의견 핵심 논거 포함 필수"""
    assert len(report.risk_factors) >= 1

def test_chief_strategist_confidence_capped(report):
    """에이전트 충돌 시 confidence 과신 방지 — 0.85 초과 금지"""
    assert report.confidence <= 0.85


# ── v4.0: 거래 파라미터 검증 ─────────────────────────────────────────────────

def test_chief_trade_params_buy_has_entry_price(report):
    """BUY 판단 시 entry_price 필수"""
    if report.recommendation == "BUY":
        assert report.entry_price is not None
        assert report.entry_price > 0

def test_chief_trade_params_buy_has_stop_loss(report):
    """BUY 판단 시 stop_loss < entry_price"""
    if report.recommendation == "BUY":
        assert report.stop_loss is not None
        assert report.stop_loss < report.entry_price

def test_chief_trade_params_buy_stop_loss_pct_range(report):
    """손절 비율 -3% ~ -6% 범위"""
    if report.recommendation == "BUY":
        assert report.stop_loss_pct is not None
        assert -6.0 <= report.stop_loss_pct <= -3.0

def test_chief_trade_params_buy_take_profit_ordered(report):
    """익절가 순서: entry_price < take_profit_1 < take_profit_2"""
    if report.recommendation == "BUY":
        assert report.take_profit_1 is not None
        assert report.take_profit_2 is not None
        assert report.take_profit_1 > report.entry_price
        assert report.take_profit_2 > report.take_profit_1

def test_chief_trade_params_buy_rr_ratio(report):
    """R:R 비율 1.5 이상 (최소 1:2 기준의 여유분)"""
    if report.recommendation == "BUY":
        assert report.rr_ratio is not None
        assert report.rr_ratio >= 1.5

def test_chief_trade_params_buy_position_size(report):
    """포지션 사이즈 0 < pct ≤ 15%"""
    if report.recommendation == "BUY":
        assert report.position_size_pct is not None
        assert 0 < report.position_size_pct <= 15.0

def test_chief_trade_params_buy_holding_weeks(report):
    """보유 기간 1주 이상"""
    if report.recommendation == "BUY":
        assert report.holding_period_weeks is not None
        assert report.holding_period_weeks >= 1

def test_chief_trade_params_buy_entry_strategy(report):
    """진입 전략이 허용된 값 중 하나"""
    if report.recommendation == "BUY":
        assert report.entry_strategy in ("시장가", "분할매수", "지정가대기")

def test_chief_trade_params_non_buy_no_entry(report):
    """HOLD/SELL 판단 시 entry_price None"""
    if report.recommendation in ("HOLD", "SELL"):
        assert report.entry_price is None