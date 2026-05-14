"""
tests/test_universe_builder.py

유니버스 빌더 단위 테스트.
pykrx 실제 호출 없이 Mock으로 필터 로직만 검증.
"""

import json
import pandas as pd
import pytest

from src.universe.filters import (
    filter_preferred_stocks,
    filter_bio_pharma,
    apply_all_filters,
)
from src.universe.universe_builder import merge_pools, load_universe


# ──────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────

def make_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows).set_index("ticker")
    return df


# ──────────────────────────────────────────
# 1. 우선주 필터
# ──────────────────────────────────────────

class TestFilterPreferred:

    def test_removes_preferred_by_name_suffix(self):
        df = make_df([
            {"ticker": "005930", "종목명": "삼성전자"},
            {"ticker": "005935", "종목명": "삼성전자우"},
        ])
        result = filter_preferred_stocks(df)
        assert "005930" in result.index
        assert "005935" not in result.index

    def test_removes_preferred_by_code_suffix_5(self):
        df = make_df([
            {"ticker": "000270", "종목명": "기아"},
            {"ticker": "000275", "종목명": "기아우"},
        ])
        result = filter_preferred_stocks(df)
        assert "000270" in result.index
        assert "000275" not in result.index

    def test_keeps_normal_stocks(self):
        df = make_df([
            {"ticker": "005930", "종목명": "삼성전자"},
            {"ticker": "000660", "종목명": "SK하이닉스"},
        ])
        assert len(filter_preferred_stocks(df)) == 2

    def test_removes_b_preferred(self):
        df = make_df([
            {"ticker": "005380", "종목명": "현대차"},
            {"ticker": "005385", "종목명": "현대차우B"},
        ])
        assert "005385" not in filter_preferred_stocks(df).index


# ──────────────────────────────────────────
# 2. 바이오/제약 필터
# ──────────────────────────────────────────

class TestFilterBio:

    def test_removes_bio_by_sector(self):
        df = make_df([
            {"ticker": "005930", "종목명": "삼성전자",        "업종": "전기전자"},
            {"ticker": "207940", "종목명": "삼성바이오로직스", "업종": "바이오"},
        ])
        result = filter_bio_pharma(df)
        assert "005930" in result.index
        assert "207940" not in result.index

    def test_removes_bio_by_name_keyword(self):
        df = make_df([
            {"ticker": "000100", "종목명": "유한양행바이오", "업종": "기타"},
            {"ticker": "005380", "종목명": "현대차",         "업종": "자동차"},
        ])
        result = filter_bio_pharma(df)
        assert "000100" not in result.index
        assert "005380" in result.index

    def test_samsung_electronics_exception(self):
        df = make_df([{"ticker": "005930", "종목명": "삼성전자", "업종": "전기전자"}])
        assert "005930" in filter_bio_pharma(df).index

    def test_removes_pharma(self):
        df = make_df([{"ticker": "000100", "종목명": "유한제약", "업종": "제약"}])
        assert "000100" not in filter_bio_pharma(df).index


# ──────────────────────────────────────────
# 3. 2단계 통합 필터
# ──────────────────────────────────────────

class TestApplyAllFilters:

    def test_applies_both_filters_in_order(self):
        df = make_df([
            {"ticker": "005930", "종목명": "삼성전자",   "업종": "전기전자"},
            {"ticker": "005935", "종목명": "삼성전자우", "업종": "전기전자"},  # ① 우선주
            {"ticker": "207940", "종목명": "삼성바이오", "업종": "바이오"},    # ② 바이오
        ])
        result = apply_all_filters(df, market="KOSPI")
        assert len(result) == 1
        assert "005930" in result.index


# ──────────────────────────────────────────
# 4. merge_pools
# ──────────────────────────────────────────

class TestMergePools:

    def test_deduplicates_tickers(self):
        kospi_df  = make_df([{"ticker": "005930", "종목명": "삼성전자"}])
        kosdaq_df = make_df([
            {"ticker": "000660", "종목명": "SK하이닉스"},
            {"ticker": "005930", "종목명": "삼성전자"},   # 중복
        ])
        result = merge_pools(kospi_df, kosdaq_df)
        assert result.count("005930") == 1

    def test_includes_all_unique_tickers(self):
        kospi_df  = make_df([{"ticker": "005930", "종목명": "A"}])
        kosdaq_df = make_df([{"ticker": "000660", "종목명": "B"}])
        result = merge_pools(kospi_df, kosdaq_df)
        assert set(result) == {"005930", "000660"}

    def test_kospi_comes_first(self):
        kospi_df  = make_df([
            {"ticker": "005930", "종목명": "A"},
            {"ticker": "000660", "종목명": "B"},
        ])
        kosdaq_df = make_df([{"ticker": "035720", "종목명": "C"}])
        result = merge_pools(kospi_df, kosdaq_df)
        assert result.index("005930") < result.index("035720")

    def test_empty_kosdaq(self):
        kospi_df  = make_df([{"ticker": "005930", "종목명": "A"}])
        kosdaq_df = pd.DataFrame(columns=["종목명"]).rename_axis("ticker")
        result = merge_pools(kospi_df, kosdaq_df)
        assert result == ["005930"]


# ──────────────────────────────────────────
# 5. load_universe 폴백
# ──────────────────────────────────────────

class TestLoadUniverse:

    def test_fallback_when_no_file(self, monkeypatch):
        import src.universe.universe_builder as ub
        from pathlib import Path
        monkeypatch.setattr(ub, "CONFIG_PATH", Path("/tmp/nonexistent_xyz.json"))
        result = load_universe()
        assert len(result) > 0

    def test_loads_saved_tickers(self, tmp_path, monkeypatch):
        import src.universe.universe_builder as ub
        config_file = tmp_path / "universe_config.json"
        config_file.write_text(json.dumps({
            "tickers":        ["005930", "000660", "005380"],
            "built_at":       "2025-01-01",
            "reference_date": "20250101",
            "ticker_count":   3,
            "version":        "1.0",
        }), encoding="utf-8")
        monkeypatch.setattr(ub, "CONFIG_PATH", config_file)
        assert load_universe() == ["005930", "000660", "005380"]