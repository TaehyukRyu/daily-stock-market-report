"""
RAG Walking Skeleton 검증 테스트

실행 방법:
  .\.venv\Scripts\python -m tests.test_rag

테스트 순서:
  1. 한국어 토크나이저 동작 확인
  2. 벡터 검색 (ChromaDB 단독) — 뉴스 3건 저장 후 검색
  3. 하이브리드 검색 (BM25 + ChromaDB EnsembleRetriever)
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (단독 실행 시)
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.documents import Document
from src.rag.chroma_store import add_documents, search, get_collection_count
from src.rag.hybrid_retriever import build_hybrid_retriever, korean_tokenize


# ── 테스트용 뉴스 3건 ────────────────────────────────────────
TEST_DOCS = [
    Document(
        page_content=(
            "삼성전자가 HBM3E 메모리 양산에 성공하며 엔비디아에 납품을 확정했다. "
            "AI 반도체 수요 증가에 따른 실적 개선이 기대된다."
        ),
        metadata={
            "source": "테스트뉴스",
            "ticker": "005930",
            "date": "2026-05-07",
            "category": "industry",
        },
    ),
    Document(
        page_content=(
            "FOMC 회의에서 연준이 기준금리를 5.25%로 동결했다. "
            "파월 의장은 인플레이션 진행 상황을 더 지켜봐야 한다고 발언했다."
        ),
        metadata={
            "source": "테스트뉴스",
            "date": "2026-05-07",
            "category": "economy",
        },
    ),
    Document(
        page_content=(
            "원달러 환율이 1,477원으로 상승했다. "
            "달러 강세와 외국인 매도세가 겹치면서 환율 변동성이 커지고 있다."
        ),
        metadata={
            "source": "테스트뉴스",
            "date": "2026-05-07",
            "category": "economy",
        },
    ),
]


def test_korean_tokenize():
    """한국어 정규식 토크나이저 동작 확인."""
    print("=== Step 0: 한국어 토크나이저 테스트 ===")
    sample = "삼성전자가 HBM3E 메모리를 엔비디아에 납품했다"
    tokens = korean_tokenize(sample)
    print(f"  입력: '{sample}'")
    print(f"  출력: {tokens}")
    assert len(tokens) > 0, "토큰이 비어있음"
    # 조사 제거 확인
    assert "삼성전자" in tokens, "'삼성전자가' → '삼성전자' 변환 실패"
    print("  ✅ 정규식 토크나이저 정상 동작\n")


def test_vector_search():
    """ChromaDB 저장 + 벡터 검색 테스트."""
    print("=== Step 1: ChromaDB 벡터 검색 ===")

    # 저장
    count = add_documents("news_articles", TEST_DOCS)
    total = get_collection_count("news_articles")
    print(f"  저장: {count}건 추가 (컬렉션 누적: {total}건)")

    # 검색 1 — 의미 유사도로 잘 잡히는 케이스
    query1 = "반도체 HBM AI 수요"
    results1 = search("news_articles", query1, k=2)
    print(f"\n  [벡터] 쿼리: '{query1}'")
    for i, r in enumerate(results1, 1):
        print(f"    [{i}] {r.page_content[:70]}...")

    # 검색 2 — 고유명사 (BM25가 유리한 케이스)
    query2 = "FOMC 파월"
    results2 = search("news_articles", query2, k=2)
    print(f"\n  [벡터] 쿼리: '{query2}'")
    for i, r in enumerate(results2, 1):
        print(f"    [{i}] {r.page_content[:70]}...")

    print("  ✅ 벡터 검색 완료\n")


def test_hybrid_search():
    """하이브리드 검색 (BM25 + ChromaDB EnsembleRetriever) 테스트."""
    print("=== Step 2: 하이브리드 검색 (7주차 교안 방식) ===")

    retriever = build_hybrid_retriever(
        collection_name="news_articles",
        documents=TEST_DOCS,
        k=3,
        bm25_weight=0.5,
    )

    # 검색 1 — 고유명사 위주 (BM25 강점)
    query1 = "FOMC 파월"
    results1 = retriever.invoke(query1)
    print(f"  [하이브리드] 쿼리: '{query1}'")
    for i, r in enumerate(results1, 1):
        print(f"    [{i}] {r.page_content[:70]}...")

    # 검색 2 — 의미 표현 위주 (벡터 강점)
    query2 = "통화정책 긴축 금리 동결"
    results2 = retriever.invoke(query2)
    print(f"\n  [하이브리드] 쿼리: '{query2}'")
    for i, r in enumerate(results2, 1):
        print(f"    [{i}] {r.page_content[:70]}...")

    print("  ✅ 하이브리드 검색 완료\n")


if __name__ == "__main__":
    print("=" * 55)
    print("RAG Walking Skeleton 검증")
    print("=" * 55 + "\n")

    test_korean_tokenize()
    test_vector_search()
    test_hybrid_search()

    print("=" * 55)
    print("✅ 모든 테스트 통과 — RAG L2 레이어 기본 동작 확인")
    print("=" * 55)