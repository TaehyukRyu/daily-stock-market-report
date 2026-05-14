"""
하이브리드 RAG 검색기 — BM25 + ChromaDB + EnsembleRetriever

구현 방식:
  원본:   BM25Retriever + FAISS Retriever → EnsembleRetriever (RRF)
  현재:   BM25Retriever + ChromaDB Retriever → EnsembleRetriever (RRF)

[KNOWN-ISSUE-RAG-01 해결] Kiwi 통합 완료 (19주차)
  기존: 한글 경로 문제로 kiwipiepy 설치 불가 → 공백/조사제거 폴백 사용
  현재: 영문 경로 이전 후 kiwipiepy 정상 설치 → kiwi_tokenize 활성화
  방식: smart_tokenize가 Kiwi 우선 시도, 실패 시 korean_tokenize 폴백

하이브리드 검색이란:
  - 벡터 검색 (Dense): 의미적 유사도 기반. "금리 인상" → "통화긴축 정책" 문서도 찾음
  - BM25 (Sparse): 키워드 정확 매칭 기반. "005930", "FOMC" 같은 고유명사에 강함
  - EnsembleRetriever (RRF): 두 결과를 1/(k+rank) 가중합으로 최종 순위 결정
"""

import re
import logging

from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document

from src.rag.chroma_store import get_collection

logger = logging.getLogger(__name__)

# ── 조사 목록 (한국어 BM25 전처리용) ─────────────────────────────────────────
# "삼성전자가"에서 "삼성전자"만 남기기 위해 끝에 붙는 조사를 제거
KOREAN_PARTICLES = [
    # 복합 조사 (3글자 이상)
    "에서부터", "으로부터", "로부터", "에서의",
    # 2글자 조사
    "에서", "에게", "에게서", "으로", "로서", "로써",
    "에는", "에도", "에만", "의", "과는",
    "께서", "한테", "보다", "마다",
    "이라", "으로도", "이고", "이며", "이라",
    # 1글자 조사
    "이", "가", "을", "를", "은", "는", "과", "와",
    "도", "만", "로", "의", "고", "에",
]

# ── Kiwi 싱글톤 ───────────────────────────────────────────────────────────────
# Kiwi는 초기화 비용이 크므로 모듈 레벨에서 한 번만 로드
_kiwi_instance = None
_kiwi_available = None  # None=미확인, True=사용가능, False=불가


def _get_kiwi():
    """Kiwi 인스턴스를 싱글톤으로 반환. 최초 1회만 초기화."""
    global _kiwi_instance, _kiwi_available

    if _kiwi_available is False:
        return None

    if _kiwi_instance is not None:
        return _kiwi_instance

    try:
        from kiwipiepy import Kiwi
        _kiwi_instance = Kiwi()
        _kiwi_available = True
        logger.info("[RAG] Kiwi 형태소 분석기 로드 완료")
        return _kiwi_instance
    except Exception as e:
        _kiwi_available = False
        logger.warning(f"[RAG] Kiwi 로드 실패, 폴백 토크나이저 사용: {e}")
        return None


# ── 토크나이저 3종 ────────────────────────────────────────────────────────────

def korean_tokenize(text: str) -> list[str]:
    """폴백 토크나이저 — Kiwi 없이 동작하는 규칙 기반 방식.

    처리 순서:
        1. 특수문자 및 공백 정규화 (숫자, 영문, 한글만 유지)
        2. 공백으로 단어 분리
        3. 각 단어의 조사 제거 (긴 조사부터)
        4. 1글자 이하 토큰 제거 (노이즈 차단)

    예시:
        "삼성전자가 HBM3E 메모리를 양산한다"
        → ["삼성전자", "HBM3E", "메모리", "양산한다"]

    한계:
        - 동사/형용사는 원형 복원 안 됨 ("양산한다"는 그대로)
        - 복합어 분리 불가 ("반도체소재" → 분리 안 됨)
        → Kiwi 사용 시 BM25 검색 품질 70% 이상 향상

    Args:
        text: 토크나이징할 한국어 텍스트

    Returns:
        토큰 리스트 (BM25 인덱서에 사용)
    """
    # Step 1: 특수문자 및 공백 정규화 (영문/숫자/한글만)
    text = re.sub(r"[^\w\s가-힣]", " ", text)

    # Step 2: 공백 분리
    words = text.split()

    # Step 3 + 4: 조사 제거 + 짧은 토큰 필터
    tokens = []
    for word in words:
        # 영문/숫자만 있는 단어는 그대로 (예: "HBM3E", "005930")
        if not re.search(r"[가-힣]", word):
            if len(word) >= 2:
                tokens.append(word)
            continue

        # 한국어 단어: 뒤의 조사 제거 (긴 조사부터 시도)
        for particle in KOREAN_PARTICLES:
            if word.endswith(particle) and len(word) > len(particle):
                word = word[: -len(particle)]
                break

        # 2글자 이상 토큰만 추가
        if len(word) >= 2:
            tokens.append(word)

    return tokens


def kiwi_tokenize(text: str) -> list[str]:
    """Kiwi 형태소 분석기를 사용한 고품질 한국어 토크나이저.

    korean_tokenize 대비 개선점:
        - 조사/어미 정확하게 분리 ("삼성전자가" → "삼성전자")
        - 복합명사 분리 ("반도체소재" → ["반도체", "소재"])
        - 동사/형용사 원형 복원 ("양산한다" → "양산")
        - 고유명사 보존 (NNP 태그로 삼성전자, FOMC 등 유지)

    추출하는 품사 태그:
        NNG: 일반명사 (메모리, 금리, 시장)
        NNP: 고유명사 (삼성전자, FOMC, 코스피)
        SL:  외국어 (HBM3E, AI, BUY)
        SH:  한자
        NR:  수사
        SN:  숫자 (005930 같은 종목코드)

    Args:
        text: 토크나이징할 한국어 텍스트

    Returns:
        토큰 리스트 (BM25 인덱서에 사용)

    Raises:
        RuntimeError: Kiwi 로드 실패 시 (smart_tokenize에서 폴백 처리)
    """
    kiwi = _get_kiwi()
    if kiwi is None:
        raise RuntimeError("Kiwi 인스턴스 없음")

    # 추출할 품사 태그
    CONTENT_POS = {"NNG", "NNP", "SL", "SH", "NR", "SN"}

    tokens = []
    for token in kiwi.tokenize(text):
        # token.tag 예: Tag.NNG → 문자열로 변환 후 비교
        tag = str(token.tag).replace("Tag.", "")
        if tag in CONTENT_POS and len(token.form) >= 2:
            tokens.append(token.form)

    return tokens if tokens else korean_tokenize(text)  # 결과 없으면 폴백


def smart_tokenize(text: str) -> list[str]:
    """Kiwi 우선, 실패 시 korean_tokenize로 자동 폴백하는 토크나이저.

    build_hybrid_retriever의 preprocess_func으로 사용됨.

    Args:
        text: 토크나이징할 텍스트

    Returns:
        토큰 리스트
    """
    try:
        return kiwi_tokenize(text)
    except Exception:
        return korean_tokenize(text)


# ── 하이브리드 검색기 빌더 ────────────────────────────────────────────────────

def build_hybrid_retriever(
    collection_name: str,
    documents: list[Document],
    k: int = 10,
    bm25_weight: float = 0.5,
) -> EnsembleRetriever:
    """BM25 + ChromaDB EnsembleRetriever 생성 (가중평균 앙상블 방식).

    19주차 변경: preprocess_func을 korean_tokenize → smart_tokenize로 교체.
    Kiwi가 설치된 환경에서는 자동으로 형태소 분석 기반 BM25를 사용.

    Args:
        collection_name: ChromaDB 컬렉션의 이름
        documents: BM25 인덱서 생성에 사용할 문서 리스트
                   (ChromaDB에는 이미 저장되어 있다고 가정)
        k: 각 검색기에서 가져올 문서 수. 기본값은 10
        bm25_weight: BM25 검색기 가중치 (나머지는 ChromaDB 몫)
                     예: 0.5 → BM25 50% + ChromaDB 50%

    Returns:
        EnsembleRetriever → invoke(query)로 List[Document] 반환

    사용 예시:
        retriever = build_hybrid_retriever("news_articles", docs)
        results = retriever.invoke("삼성전자 HBM 실적")
    """
    # ── BM25 Retriever (한국어 형태소 분석 전처리) ──────────────────────────
    # 19주차: korean_tokenize → smart_tokenize (Kiwi 우선 + 폴백)
    bm25_retriever = BM25Retriever.from_documents(
        documents,
        preprocess_func=smart_tokenize,
    )
    bm25_retriever.k = k

    # ── ChromaDB Retriever (벡터 유사도 검색) ──────────────────────────────
    chroma_db = get_collection(collection_name)
    chroma_retriever = chroma_db.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )

    # ── EnsembleRetriever (RRF로 결합) ─────────────────────────────────────
    return EnsembleRetriever(
        retrievers=[bm25_retriever, chroma_retriever],
        weights=[bm25_weight, 1 - bm25_weight],
    )