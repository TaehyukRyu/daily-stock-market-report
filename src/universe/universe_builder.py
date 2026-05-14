"""
src/universe/universe_builder.py

투자 유니버스 자동 구축 모듈

구조:
  Step 1: KOSPI 시총 상위 100개 → 2단계 필터 → KOSPI Pool
  Step 2: KOSDAQ 시총 상위 20개 → 2단계 필터 → KOSDAQ Pool
  Step 3: KOSPI Pool + KOSDAQ Pool → ticker 중복 제거 → 최종 유니버스

[핵심 설계]
  pykrx get_market_cap_by_ticker는 종목명 컬럼을 반환하지 않는다.
  → _add_ticker_names()로 종목명 컬럼을 직접 추가한 뒤 필터를 실행한다.

실행:
  python -m src.universe.universe_builder
  from src.universe.universe_builder import load_universe
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from pykrx import stock as pykrx_stock

from src.universe.filters import apply_all_filters


# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────

KOSPI_TOP_N  = 100
KOSDAQ_TOP_N = 20
KOSDAQ_MAX_N = 40

CONFIG_PATH = Path("src/config/universe_config.json")


def _get_latest_trading_date() -> str:
    for delta in range(5):
        d = datetime.now() - timedelta(days=delta)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return datetime.now().strftime("%Y%m%d")


# ──────────────────────────────────────────
# 종목명 컬럼 추가 헬퍼
# ──────────────────────────────────────────

def _add_ticker_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    pykrx get_market_cap_by_ticker 결과에 '종목명' 컬럼을 추가합니다.

    get_market_ticker_name()을 각 ticker에 호출합니다.
    실패한 ticker는 ticker 코드 자체를 이름으로 사용합니다.
    """
    if "종목명" in df.columns:
        return df  # 이미 있으면 건너뜀

    names = {}
    for ticker in df.index:
        try:
            names[ticker] = pykrx_stock.get_market_ticker_name(ticker)
        except Exception:
            names[ticker] = ticker  # 실패 시 코드 자체 사용

    df = df.copy()
    df["종목명"] = df.index.map(names)
    return df


# ──────────────────────────────────────────
# Step 1: KOSPI Pool
# ──────────────────────────────────────────

def build_kospi_pool(date: str) -> pd.DataFrame:
    print(f"\n[Step 1] KOSPI 시총 상위 {KOSPI_TOP_N}개 조회 ({date})")

    df = pykrx_stock.get_market_cap_by_ticker(date, market="KOSPI")
    if "시가총액" in df.columns:
        df = df.sort_values("시가총액", ascending=False).head(KOSPI_TOP_N)
    else:
        df = df.head(KOSPI_TOP_N)

    df = _add_ticker_names(df)   # ← 종목명 추가
    print(f"  조회 완료: {len(df)}개")
    return apply_all_filters(df, market="KOSPI")


# ──────────────────────────────────────────
# Step 2: KOSDAQ Pool
# ──────────────────────────────────────────

def build_kosdaq_pool(date: str) -> pd.DataFrame:
    print(f"\n[Step 2] KOSDAQ 시총 상위 {KOSDAQ_TOP_N}개 조회 ({date})")

    df = pykrx_stock.get_market_cap_by_ticker(date, market="KOSDAQ")
    if "시가총액" in df.columns:
        df = df.sort_values("시가총액", ascending=False).head(KOSDAQ_TOP_N)
    else:
        df = df.head(KOSDAQ_TOP_N)

    df = _add_ticker_names(df)   # ← 종목명 추가
    print(f"  조회 완료: {len(df)}개")
    df = apply_all_filters(df, market="KOSDAQ")

    if len(df) < 5:
        print(f"  ⚠️ 잔여 {len(df)}개 < 5개 → 상위 {KOSDAQ_MAX_N}개로 확장")
        df_ext = pykrx_stock.get_market_cap_by_ticker(date, market="KOSDAQ")
        if "시가총액" in df_ext.columns:
            df_ext = df_ext.sort_values("시가총액", ascending=False).head(KOSDAQ_MAX_N)
        else:
            df_ext = df_ext.head(KOSDAQ_MAX_N)
        df_ext = _add_ticker_names(df_ext)
        df = apply_all_filters(df_ext, market="KOSDAQ")

    return df


# ──────────────────────────────────────────
# Step 3: Concat + 중복 제거
# ──────────────────────────────────────────

def merge_pools(kospi_df: pd.DataFrame, kosdaq_df: pd.DataFrame) -> list[str]:
    kospi_tickers  = list(kospi_df.index)
    kosdaq_tickers = list(kosdaq_df.index)

    print(f"\n[Step 3] 중복 제거")
    print(f"  KOSPI Pool:  {len(kospi_tickers)}개")
    print(f"  KOSDAQ Pool: {len(kosdaq_tickers)}개")

    seen:  set[str]  = set()
    final: list[str] = []
    for ticker in (kospi_tickers + kosdaq_tickers):
        if ticker not in seen:
            seen.add(ticker)
            final.append(ticker)

    print(f"  → 최종 유니버스: {len(final)}개")
    return final


# ──────────────────────────────────────────
# 저장 / 로드
# ──────────────────────────────────────────

def save_universe(tickers: list[str], date: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "version":        "1.0",
        "built_at":       datetime.now().isoformat(),
        "reference_date": date,
        "ticker_count":   len(tickers),
        "tickers":        tickers,
    }
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✅ 저장 완료: {CONFIG_PATH} ({len(tickers)}개)")


_FALLBACK_TICKERS = ["005930", "000660", "005380", "035420", "051910"]


def load_universe() -> list[str]:
    """
    저장된 유니버스를 로드합니다.
    파일이 없으면 폴백 반환.
    에이전트에서: from src.universe.universe_builder import load_universe
    """
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return config.get("tickers", _FALLBACK_TICKERS)
    return _FALLBACK_TICKERS


# ──────────────────────────────────────────
# 메인 실행
# ──────────────────────────────────────────

def build_universe(date: str | None = None) -> list[str]:
    if date is None:
        date = _get_latest_trading_date()

    print("=" * 60)
    print(f"유니버스 빌더 — 기준일: {date}")
    print("=" * 60)

    kospi_df  = build_kospi_pool(date)
    kosdaq_df = build_kosdaq_pool(date)
    final     = merge_pools(kospi_df, kosdaq_df)

    save_universe(final, date)
    return final


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    universe = build_universe()
    print(f"\n최종 유니버스 ({len(universe)}개):")
    for i, t in enumerate(universe, 1):
        name = pykrx_stock.get_market_ticker_name(t)
        print(f"  {i:3d}. {t}  {name}")