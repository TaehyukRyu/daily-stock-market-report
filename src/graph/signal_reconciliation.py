"""
src/graph/signal_reconciliation.py

신호 충돌 해소 모듈 — 계획서 12.5절

[역할]
여러 종목을 분석할 때 같은 날 BUY 신호가 다수 발생할 경우,
confidence 기반으로 우선순위를 결정하고
섹터 집중도를 체크하여 최대 N개 종목만 선별합니다.

[동작 흐름]
1. 당일 신호 레지스트리(data/signals/signals_YYYY-MM-DD.json) 로드
2. 현재 종목 신호 추가/갱신
3. BUY 신호에 대해 score = confidence 계산
4. 섹터 집중도 체크 (동일 섹터 최대 MAX_PER_SECTOR개)
5. 상위 MAX_BUY_SIGNALS개 선별
6. 레지스트리 저장 후 결과 반환

[확장 포인트]
- score 계산식에 예상수익률 대리지표(모멘텀, RSI 등) 반영 가능
- SECTOR_MAP을 universe_config.json에서 동적으로 로드하도록 이전 가능
"""

import json
import os
from datetime import date

from src.schemas.graph_state import GraphState


# ─────────────────────────────────────────────────
# 설정 상수
# ─────────────────────────────────────────────────

MAX_BUY_SIGNALS = 5   # 하루 최대 신규 매수 종목 수
MAX_PER_SECTOR  = 2   # 동일 섹터 최대 종목 수
SIGNAL_DIR      = "data/signals"


# ─────────────────────────────────────────────────
# 섹터 맵 (KOSPI/KOSDAQ 주요 종목)
# 추후 universe_config.json 에 sector 필드 추가 후 동적 로드로 이전 예정
# ─────────────────────────────────────────────────

SECTOR_MAP: dict[str, str] = {
    # 반도체
    "005930": "반도체",    # 삼성전자
    "000660": "반도체",    # SK하이닉스
    "402340": "반도체",    # SK스퀘어
    "009150": "반도체",    # 삼성전기
    # 자동차
    "005380": "자동차",    # 현대차
    "000270": "자동차",    # 기아
    "012330": "자동차",    # 현대모비스
    "271560": "자동차",    # 오리온 (실제로는 식품 — 이 항목은 예시용)
    # 배터리
    "373220": "배터리",    # LG에너지솔루션
    "006400": "배터리",    # 삼성SDI
    "096770": "배터리",    # SK이노베이션
    # 화학
    "051910": "화학",      # LG화학
    "011170": "화학",      # 롯데케미칼
    # 바이오/제약
    "207940": "바이오",    # 삼성바이오로직스
    "068270": "바이오",    # 셀트리온
    "000100": "바이오",    # 유한양행
    "128940": "바이오",    # 한미약품
    # 에너지/발전
    "034020": "에너지",    # 두산에너빌리티
    "015760": "에너지",    # 한국전력
    "267250": "에너지",    # HD현대
    # 조선
    "329180": "조선",      # HD현대중공업
    "042660": "조선",      # 한화오션
    "009540": "조선",      # HD한국조선해양
    "010140": "조선",      # 삼성중공업
    # 방산/항공
    "012450": "방산",      # 한화에어로스페이스
    "047810": "방산",      # 한국항공우주
    "064350": "방산",      # 현대로템
    # 금융
    "105560": "금융",      # KB금융
    "055550": "금융",      # 신한지주
    "086790": "금융",      # 하나금융지주
    "316140": "금융",      # 우리금융지주
    "032830": "금융",      # 삼성생명
    # IT/플랫폼
    "035420": "IT플랫폼",  # NAVER
    "035720": "IT플랫폼",  # 카카오
    "263750": "IT플랫폼",  # 펄어비스
    # 통신
    "017670": "통신",      # SK텔레콤
    "030200": "통신",      # KT
    "032640": "통신",      # LG유플러스
    # 유통/소비재
    "028260": "유통",      # 삼성물산
    "069960": "유통",      # 현대백화점
    "023530": "유통",      # 롯데쇼핑
    "004170": "유통",      # 신세계
    # 철강
    "005490": "철강",      # POSCO홀딩스
    "004020": "철강",      # 현대제철
}


def get_sector(ticker: str) -> str:
    """종목 섹터 조회. 미등록 종목은 '기타' 반환."""
    return SECTOR_MAP.get(ticker, "기타")


# ─────────────────────────────────────────────────
# 일별 신호 레지스트리 I/O
# ─────────────────────────────────────────────────

def _get_registry_path(today: str | None = None) -> str:
    os.makedirs(SIGNAL_DIR, exist_ok=True)
    day = today or date.today().isoformat()
    return os.path.join(SIGNAL_DIR, f"signals_{day}.json")


def _load_registry(today: str | None = None) -> dict:
    path = _get_registry_path(today)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_registry(registry: dict, today: str | None = None) -> None:
    path = _get_registry_path(today)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────
# 핵심 로직: 우선순위화
# ─────────────────────────────────────────────────

def _score_signal(recommendation: str, confidence: float) -> float:
    """
    BUY 신호에만 양수 점수 부여. SELL/HOLD는 0.0.

    현재: score = confidence (단순)
    확장: score = confidence × 모멘텀지표 등 반영 가능
    """
    if recommendation == "BUY":
        return round(confidence, 4)
    return 0.0


def _reconcile_registry(
    registry: dict,
    max_buy: int = MAX_BUY_SIGNALS,
    max_per_sector: int = MAX_PER_SECTOR,
) -> list[dict]:
    """
    레지스트리 전체 신호를 우선순위화하여 결과 목록 반환.

    반환 형식 (항목 예시):
    {
        "ticker": "005930",
        "recommendation": "BUY",
        "confidence": 0.82,
        "score": 0.82,
        "sector": "반도체",
        "rank": 1,           # BUY 선별 순위 (미선별/SELL/HOLD = None)
        "included": True,    # 최종 매수 후보 포함 여부
        "exclusion_reason": None  # 미선별 시 이유
    }
    """
    # ① BUY 신호 추출 & 점수 내림차순 정렬
    buy_signals = sorted(
        [
            {
                "ticker":         ticker,
                "recommendation": info["recommendation"],
                "confidence":     info["confidence"],
                "score":          info["score"],
                "sector":         info["sector"],
            }
            for ticker, info in registry.items()
            if info["recommendation"] == "BUY"
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    # ② 섹터 집중도 체크하며 선별
    sector_count: dict[str, int] = {}
    selected: list[dict] = []
    excluded_buy: list[dict] = []

    for sig in buy_signals:
        sector = sig["sector"]
        count  = sector_count.get(sector, 0)

        if len(selected) < max_buy and count < max_per_sector:
            sector_count[sector] = count + 1
            selected.append({
                **sig,
                "rank":             len(selected) + 1,
                "included":         True,
                "exclusion_reason": None,
            })
        else:
            if count >= max_per_sector:
                reason = f"섹터 집중 ({sector} 이미 {count}종목)"
            else:
                reason = f"일일 매수 한도 초과 (최대 {max_buy}종목)"
            excluded_buy.append({
                **sig,
                "rank":             None,
                "included":         False,
                "exclusion_reason": reason,
            })

    # ③ SELL/HOLD 신호 (정보용 — 매수 후보 아님)
    non_buy = [
        {
            "ticker":         ticker,
            "recommendation": info["recommendation"],
            "confidence":     info["confidence"],
            "score":          0.0,
            "sector":         info["sector"],
            "rank":           None,
            "included":       False,
            "exclusion_reason": "BUY 신호 아님",
        }
        for ticker, info in registry.items()
        if info["recommendation"] != "BUY"
    ]

    return selected + excluded_buy + non_buy


# ─────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────

def run_signal_reconciliation(
    ticker: str,
    recommendation: str,
    confidence: float,
    today: str | None = None,
) -> dict:
    """
    단일 종목 신호를 레지스트리에 등록하고 전체 신호를 재조정.

    Args:
        ticker:         종목 코드 (예: "005930")
        recommendation: "BUY" / "SELL" / "HOLD"
        confidence:     신뢰도 (0.0~1.0)
        today:          날짜 문자열 YYYY-MM-DD (None이면 오늘, 테스트용)

    Returns:
        {
            "current":     dict | None,  # 현재 종목 결과
            "all_signals": list[dict],   # 전체 신호 우선순위 목록
            "buy_count":   int,          # 선별된 BUY 종목 수
            "summary":     str,          # 한 줄 요약
        }
    """
    sector = get_sector(ticker)
    score  = _score_signal(recommendation, confidence)

    # 레지스트리 로드 → 현재 종목 추가/갱신 → 저장
    registry = _load_registry(today)
    registry[ticker] = {
        "recommendation": recommendation,
        "confidence":     confidence,
        "score":          score,
        "sector":         sector,
    }
    _save_registry(registry, today)

    # 전체 재조정
    all_signals = _reconcile_registry(registry)

    # 현재 종목 결과 추출
    current   = next((s for s in all_signals if s["ticker"] == ticker), None)
    buy_count = sum(1 for s in all_signals if s.get("included"))

    # 요약 문자열 생성
    if current and current.get("included"):
        summary = (
            f"{ticker}({sector}) {recommendation} "
            f"→ 오늘의 매수 후보 {current['rank']}위 / {MAX_BUY_SIGNALS}종목"
        )
    elif recommendation == "BUY" and current:
        summary = (
            f"{ticker}({sector}) {recommendation} "
            f"→ 매수 후보 미선정 ({current.get('exclusion_reason', '우선순위 미달')})"
        )
    else:
        summary = (
            f"{ticker}({sector}) {recommendation} "
            f"(신뢰도 {confidence:.2f}) — 매수 후보 대상 아님"
        )

    return {
        "current":     current,
        "all_signals": all_signals,
        "buy_count":   buy_count,
        "summary":     summary,
    }


# ─────────────────────────────────────────────────
# LangGraph 노드
# ─────────────────────────────────────────────────

async def signal_reconciliation_node(state: GraphState) -> dict:
    """
    chief_strategist 결과를 신호 레지스트리에 등록하고 우선순위를 조정.

    pipeline 위치: chief_strategist → [이 노드] → report_formatter
    """
    print(f"\n[4.5/6] signal_reconciliation — 신호 등록 및 우선순위 조정")

    # chief_strategist 결과 추출
    final = next(
        (r for r in state.analysis_reports if r.agent_name == "chief_strategist"),
        None,
    )

    if not final:
        print("  ⚠️ chief_strategist 결과 없음 — 스킵")
        return {"reconciled_signals": []}

    # 신호 등록 및 재조정
    result = run_signal_reconciliation(
        ticker         = state.ticker,
        recommendation = final.recommendation,
        confidence     = final.confidence,
    )

    # 결과 출력
    current = result["current"]
    if current and current.get("included"):
        print(f"  ✅ {state.ticker} {final.recommendation} → 매수 후보 {current['rank']}위")
    elif final.recommendation == "BUY":
        print(f"  ⚠️ {state.ticker} BUY → 미선정 ({current.get('exclusion_reason') if current else '미분류'})")
    else:
        print(f"  → {state.ticker} {final.recommendation} (매수 후보 아님)")

    print(f"  → 오늘 매수 후보: {result['buy_count']}/{MAX_BUY_SIGNALS}종목")
    print(f"  → {result['summary']}")

    return {"reconciled_signals": result["all_signals"]}