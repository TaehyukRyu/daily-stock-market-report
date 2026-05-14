"""
News & Economy MCP Server 테스트
실행: python -m pytest tests/test_news_economy_mcp.py -v
"""

import pytest
from src.mcp_servers.news_economy.server import (
    get_exchange_rate,
    get_interest_rate,
    search_news,
    search_policy_news,
)


# ─────────────────────────────────────────────────────────
# Test 1: search_news — 네이버
# ─────────────────────────────────────────────────────────
def test_search_news_naver():
    result = search_news(query="삼성전자", source="naver", max_results=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["source"] == "naver"
    assert result["count"] > 0, "기사가 0건입니다"
    assert len(result["articles"]) > 0

    first = result["articles"][0]
    assert "title" in first
    assert "link" in first
    assert "pub_date" in first

    print(f"\n✅ 네이버 뉴스 {result['count']}건 수집")
    print(f"   첫 번째 기사: {first['title'][:40]}...")


# ─────────────────────────────────────────────────────────
# Test 2: search_news — Google 한국어
# ─────────────────────────────────────────────────────────
def test_search_news_google_ko():
    result = search_news(query="Fed 금리", source="google_ko", max_results=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["source"] == "google_ko"
    assert result["count"] > 0, "기사가 0건입니다"

    print(f"\n✅ Google KO 뉴스 {result['count']}건 수집")
    print(f"   첫 번째 기사: {result['articles'][0]['title'][:40]}...")


# ─────────────────────────────────────────────────────────
# Test 3: search_news — Google 영어
# ─────────────────────────────────────────────────────────
def test_search_news_google_en():
    result = search_news(query="Fed rate decision", source="google_en", max_results=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["source"] == "google_en"
    assert result["count"] > 0, "기사가 0건입니다"

    print(f"\n✅ Google EN 뉴스 {result['count']}건 수집")
    print(f"   첫 번째 기사: {result['articles'][0]['title'][:60]}...")


# ─────────────────────────────────────────────────────────
# Test 4: search_news — 잘못된 source
# ─────────────────────────────────────────────────────────
def test_search_news_invalid_source():
    result = search_news(query="테스트", source="invalid_source")

    assert "error" in result
    print(f"\n✅ 잘못된 source 에러 처리 정상: {result['error']}")


# ─────────────────────────────────────────────────────────
# Test 5: search_policy_news
# ─────────────────────────────────────────────────────────
def test_search_policy_news():
    result = search_policy_news(max_results_per_query=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["count"] > 0, "정책 뉴스가 0건입니다"
    assert "queries_used" in result
    assert "note" in result

    # 국내/해외 기사가 섞여 있는지 확인
    langs = {a.get("source_lang") for a in result["articles"]}
    assert "ko" in langs, "국내 뉴스(ko)가 없습니다"
    assert "en" in langs, "해외 뉴스(en)가 없습니다"

    # 중복 링크 없는지 확인
    links = [a["link"] for a in result["articles"] if a.get("link")]
    assert len(links) == len(set(links)), "중복 기사가 있습니다"

    print(f"\n✅ 정책 뉴스 총 {result['count']}건 수집 (국내+해외)")
    print(f"   국내: {sum(1 for a in result['articles'] if a.get('source_lang') == 'ko')}건")
    print(f"   해외: {sum(1 for a in result['articles'] if a.get('source_lang') == 'en')}건")


# ─────────────────────────────────────────────────────────
# Test 6: get_exchange_rate
# ─────────────────────────────────────────────────────────
def test_get_exchange_rate():
    result = get_exchange_rate(days=10)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["series_id"] == "DEXKOUS"
    assert result["latest_rate"] is not None
    assert 900 < result["latest_rate"] < 2000, "환율이 비정상 범위입니다"
    assert len(result["history"]) > 0

    print(f"\n✅ USD/KRW 환율: {result['latest_rate']}원 ({result['latest_date']})")
    if result["change_pct"] is not None:
        print(f"   전일 대비: {result['change_pct']:+.4f}%")


# ─────────────────────────────────────────────────────────
# Test 7: get_interest_rate
# ─────────────────────────────────────────────────────────
def test_get_interest_rate():
    result = get_interest_rate(periods=6)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["latest_rate"] is not None
    assert 0 < result["latest_rate"] < 10, "금리가 비정상 범위입니다"
    assert len(result["history"]) > 0

    print(f"\n✅ 한국 기준금리: {result['latest_rate']}% ({result['latest_date']})")
    print(f"   직전: {result['prev_rate']}%")


# ─────────────────────────────────────────────────────────
# Test 8: search_news — 카테고리 모드 (v5.4 신규)
# ─────────────────────────────────────────────────────────
def test_search_news_category_mode():
    """Phase 3: 5개 카테고리 병렬 수집 + nano 관련성 스코어링"""
    all_categories = ["economy", "finance", "politics", "international", "industry"]
    result = search_news(categories=all_categories, max_per_category=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["mode"] == "category"
    assert result["count"] > 0, "수집 기사가 0건입니다"

    if result["scored"]:
        for article in result["articles"]:
            assert article["relevance_score"] is not None
            assert 0.0 <= article["relevance_score"] <= 1.0
            assert article["relevance_score"] >= 0.5
    else:
        print("\n⚠️  스코어링 Fallback 발생 — 원본 기사 반환")

    links = [a["link"] for a in result["articles"] if a.get("link")]
    assert len(links) == len(set(links)), "중복 기사가 있습니다"

    from collections import Counter
    dist = Counter(a["category"] for a in result["articles"])

    print(f"\n✅ [v5.4 Phase 3] 카테고리 수집 + nano 스코어링")
    print(f"   수집 후 필터링 결과: {result['count']}건")
    print(f"   scored: {result['scored']}")
    print(f"   phase: {result['phase']}")
    print(f"   errors: {result['errors']}")
    for cat, cnt in sorted(dist.items()):
        print(f"   {cat}: {cnt}건")
    if result["scored"] and result["articles"]:
        scores = [a["relevance_score"] for a in result["articles"]]
        print(f"   관련성 점수 범위: {min(scores):.2f} ~ {max(scores):.2f}")
        print(f"   평균 점수: {sum(scores)/len(scores):.2f}")


def test_search_news_no_params():
    """categories도 query도 없으면 에러 반환"""
    result = search_news()
    assert "error" in result
    print(f"\n✅ 파라미터 없음 에러 처리: {result['error']}")