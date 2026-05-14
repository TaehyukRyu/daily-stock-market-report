from src.mcp_servers.news_economy.server import search_news

def test_search_news_category_mode():
    """Phase 3: 5개 카테고리 병렬 수집 + nano 관련성 스코어링"""
    all_categories = ["economy", "finance", "politics", "international", "industry"]
    result = search_news(categories=all_categories, max_per_category=5)

    assert "error" not in result, f"에러 발생: {result.get('error')}"
    assert result["mode"] == "category"
    assert result["count"] > 0, "수집 기사가 0건입니다"

    # 스코어링 성공 여부 확인
    if result["scored"]:
        # 스코어링 성공 시: 점수가 0~1 범위인지, 필터링이 적용됐는지 확인
        for article in result["articles"]:
            assert article["relevance_score"] is not None
            assert 0.0 <= article["relevance_score"] <= 1.0
            assert article["relevance_score"] >= 0.5  # min_relevance_score 기본값
    else:
        # 스코어링 Fallback 시: 원본 기사 그대로 반환
        print("\n⚠️  스코어링 Fallback 발생 — 원본 기사 반환")

    # URL 중복 없는지 확인
    links = [a["link"] for a in result["articles"] if a.get("link")]
    assert len(links) == len(set(links)), "중복 기사가 있습니다"

    from collections import Counter
    dist = Counter(a["category"] for a in result["articles"])

    print(f"\n✅ [v5.4 Phase 3] 카테고리 수집 + nano 스코어링")
    print(f"   수집 후 필터링 결과: {result['count']}건")
    print(f"   scored: {result['scored']}")
    print(f"   phase: {result['phase']}")
    for cat, cnt in sorted(dist.items()):
        print(f"   {cat}: {cnt}건")
    if result["scored"] and result["articles"]:
        scores = [a["relevance_score"] for a in result["articles"]]
        print(f"   관련성 점수 범위: {min(scores):.2f} ~ {max(scores):.2f}")
        print(f"   평균 점수: {sum(scores)/len(scores):.2f}")