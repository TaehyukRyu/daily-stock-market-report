"""
src/universe/filters.py

유니버스 빌더 2단계 필터

적용 순서:
  ① 우선주 제거
  ② 바이오/제약 제거

[핵심 설계 원칙]
  pykrx get_market_cap_by_ticker 반환값에는 '종목명' 컬럼이 없다.
  universe_builder.py에서 종목명을 미리 추가해서 넘겨주지만,
  컬럼이 없더라도 최소한 기계적 기준(코드 끝자리)으로는 필터가 동작해야 한다.
"""

import re
import pandas as pd


# ──────────────────────────────────────────
# 필터 ①: 우선주 제거
# ──────────────────────────────────────────

_PREFERRED_NAME_PATTERN = re.compile(r"우$|우B$|\d우$|\d우B$|B우$")
_PREFERRED_CODE_SUFFIX  = {"5", "7"}


def filter_preferred_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """
    우선주를 제거합니다.

    [변경] 종목명 컬럼 없어도 코드 끝자리 기반 필터는 항상 실행.
    종목명이 있으면 코드 + 이름 OR 조건으로 더 정확하게 탐지.
    """
    name_col = "종목명"

    # 코드 끝자리 기반 (항상 실행)
    code_mask = df.index.str[-1].isin(_PREFERRED_CODE_SUFFIX)

    # 종목명 기반 (컬럼이 있을 때만 추가)
    if name_col in df.columns:
        name_mask = df[name_col].str.contains(_PREFERRED_NAME_PATTERN, na=False)
        pref_mask = code_mask | name_mask
    else:
        pref_mask = code_mask  # 코드만으로 판단

    n_removed = pref_mask.sum()
    if n_removed:
        removed_codes = df[pref_mask].index.tolist()
        removed_names = df[pref_mask][name_col].tolist() if name_col in df.columns else removed_codes
        print(f"  [필터①-우선주] {n_removed}개 제거: {removed_names[:5]}{'...' if n_removed > 5 else ''}")

    return df[~pref_mask]


# ──────────────────────────────────────────
# 필터 ②: 바이오/제약 제거
# ──────────────────────────────────────────

_BIO_SECTORS = {
    "의약품", "제약", "바이오", "의료기기",
    "헬스케어", "의료서비스", "생명과학",
}

_BIO_NAME_KEYWORDS = [
    "바이오", "파마", "제약", "의약", "헬스", "메디",
    "테라피", "케어", "클리닉", "셀", "진단", "젠", "바이오텍",
]
_BIO_NAME_PATTERN = re.compile("|".join(_BIO_NAME_KEYWORDS))

_BIO_EXCEPTIONS = {
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
}


def filter_bio_pharma(df: pd.DataFrame) -> pd.DataFrame:
    """
    바이오/제약 종목을 제거합니다.

    [변경] 업종 + 종목명 OR 조건. 컬럼이 없으면 해당 조건은 건너뜀.
    둘 다 없으면 필터 불가 → df 원본 반환 (로그 출력).
    """
    name_col   = "종목명"
    sector_col = "업종"

    has_name   = name_col   in df.columns
    has_sector = sector_col in df.columns

    if not has_name and not has_sector:
        print(f"  [필터②-바이오] ⚠️ 종목명/업종 컬럼 없음 → 건너뜀")
        return df

    # 종목명 키워드 마스크
    name_kw_mask = (
        df[name_col].str.contains(_BIO_NAME_PATTERN, na=False)
        if has_name else pd.Series(False, index=df.index)
    )

    # 업종 마스크
    sector_mask = (
        df[sector_col].apply(
            lambda s: any(k in str(s) for k in _BIO_SECTORS) if pd.notna(s) else False
        )
        if has_sector else pd.Series(False, index=df.index)
    )

    bio_mask_raw  = sector_mask | name_kw_mask
    exception_mask = df.index.isin(_BIO_EXCEPTIONS)
    bio_mask       = bio_mask_raw & ~exception_mask

    n_removed = bio_mask.sum()
    if n_removed:
        removed_names = df[bio_mask][name_col].tolist() if has_name else df[bio_mask].index.tolist()
        print(f"  [필터②-바이오] {n_removed}개 제거: {removed_names[:5]}{'...' if n_removed > 5 else ''}")

    return df[~bio_mask]


# ──────────────────────────────────────────
# 편의 함수: 2단계 필터 적용
# ──────────────────────────────────────────

def apply_all_filters(df: pd.DataFrame, market: str = "KOSPI") -> pd.DataFrame:
    """① 우선주 → ② 바이오/제약 순서로 필터 적용."""
    n_before = len(df)
    df = filter_preferred_stocks(df)
    df = filter_bio_pharma(df)
    n_after = len(df)
    print(f"  → 필터 결과: {n_before}개 → {n_after}개 (제거 {n_before - n_after}개)")
    return df