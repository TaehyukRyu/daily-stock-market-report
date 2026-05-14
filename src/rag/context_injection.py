"""
src/rag/context_injection.py

에이전트 ↔ RAG 컨텍스트 주입 모듈
"""

import tiktoken
from typing import Optional

from langchain_core.documents import Document

from src.rag.chroma_store import get_collection
from src.rag.hybrid_retriever import build_hybrid_retriever


# ─────────────────────────────────────────────
# 1. 토큰 예산 상수
# ─────────────────────────────────────────────
TOTAL_TOKEN_BUDGET = 2_000

_ENCODER = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def _truncate_to_budget(text: str, budget: int) -> str:
    tokens = _ENCODER.encode(text)
    if len(tokens) <= budget:
        return text
    return _ENCODER.decode(tokens[:budget]) + "... [토큰 예산 초과로 잘림]"


# ─────────────────────────────────────────────
# 2. ChromaDB 컬렉션에서 전체 문서 꺼내기
# ─────────────────────────────────────────────
def _get_all_documents(collection_name: str) -> list[Document]:
    """ChromaDB 컬렉션의 전체 문서를 LangChain Document 리스트로 반환"""
    try:
        chroma_db = get_collection(collection_name)
        raw = chroma_db._collection.get(include=["documents", "metadatas"])
        texts     = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []

        if not texts:
            return []

        return [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(texts, metadatas)
        ]
    except Exception as e:
        print(f"[RAG 경고] '{collection_name}' 문서 로드 실패: {e}")
        return []


# ─────────────────────────────────────────────
# 3. 에이전트별 RAG 설정
#    primary   : 주력 컬렉션 (많은 토큰 배정)
#    secondary : 보조 컬렉션 (적은 토큰 배정, None이면 생략)
# ─────────────────────────────────────────────
AGENT_RAG_CONFIG: dict[str, dict] = {
    "macro_economist": {
        "primary":   {"collection": "market_reports",    "k": 5, "budget": 1_100},
        "secondary": {"collection": "strategy_outcomes", "k": 3, "budget":   700},
    },
    "kr_market_specialist": {
        "primary":   {"collection": "analyst_reports",   "k": 5, "budget": 1_200},
        "secondary": {"collection": "news_articles",     "k": 3, "budget":   600},
    },
    "us_market_specialist": {
        "primary":   {"collection": "market_reports",    "k": 5, "budget": 1_100},
        "secondary": {"collection": "news_articles",     "k": 2, "budget":   700},
    },
    "technical_analyst": {
        "primary":   {"collection": "analyst_reports",   "k": 3, "budget": 1_700},
        "secondary": None,
    },
    "quant_analyst": {
        "primary":   {"collection": "analyst_reports",   "k": 5, "budget": 1_100},
        "secondary": {"collection": "earnings_data",     "k": 3, "budget":   700},
    },
    "fundamental_analyst": {
        "primary":   {"collection": "analyst_reports",   "k": 5, "budget": 1_200},
        "secondary": {"collection": "market_reports",    "k": 3, "budget":   600},
    },
    "sentiment_analyst": {
        "primary":   {"collection": "news_articles",     "k": 5, "budget": 1_700},
        "secondary": None,
    },
    "informal_intelligence": {  # 향후 분리 예정 — 현재는 sentiment_analyst가 겸임
        "primary":   {"collection": "news_articles",     "k": 5, "budget": 1_700},
        "secondary": None,
    },
    "chief_strategist": {
        "primary":   {"collection": "strategy_outcomes", "k": 5, "budget":   800},
        "secondary": {"collection": "market_reports",    "k": 3, "budget": 1_000},
    },
}


# ─────────────────────────────────────────────
# 4. 에이전트별 쿼리 템플릿
# ─────────────────────────────────────────────
QUERY_TEMPLATES: dict[str, dict[str, str]] = {
    "macro_economist": {
        "primary":   "{date} 금리 통화정책 거시경제 전망 시장 영향",
        "secondary": "{date} {regime} 레짐 거시 전략 결과 수익률",
    },
    "kr_market_specialist": {
        "primary":   "{ticker} 증권사 리포트 투자의견 목표주가 실적",
        "secondary": "{ticker} {date} 수급 뉴스 공시 이슈",
    },
    "us_market_specialist": {
        "primary":   "{date} S&P500 빅테크 섹터 동향 시장 전망",
        "secondary": "{date} 미국 시장 뉴스 연준 금리 반응",
    },
    "technical_analyst": {
        "primary":   "{ticker} 차트 패턴 기술적 분석 지지 저항 매물대",
        "secondary": "",
    },
    "quant_analyst": {
        "primary":   "{ticker} 실적 컨센서스 목표주가 EPS 괴리율",
        "secondary": "{ticker} 분기 실적 매출 영업이익 전망",
    },
    "fundamental_analyst": {
        "primary":   "{ticker} 펀더멘털 PER PBR ROE 재무 밸류에이션",
        "secondary": "{date} 산업 동향 시장 평가 펀더멘털 분석",
    },
    "sentiment_analyst": {
        "primary":   "{date} 시장 공포 탐욕 역발상 감성 뉴스 투자심리",
        "secondary": "",
    },
    "informal_intelligence": {
        "primary":   "{ticker} {date} 커뮤니티 언급량 관심도 급증 이슈",
        "secondary": "",
    },
    "chief_strategist": {
        "primary":   "{regime} 레짐 과거 전략 결과 수익률 성공 패턴",
        "secondary": "{date} {regime} 시장 현황 종합 전략",
    },
}


# ─────────────────────────────────────────────
# 5. 쿼리 빌더 — 템플릿 + 변수 치환
# ─────────────────────────────────────────────
def build_rag_query(
    agent_name: str,
    slot: str,
    state_vars: dict,
) -> str:
    template = QUERY_TEMPLATES.get(agent_name, {}).get(slot, "")
    if not template:
        return ""

    filled = template.format(
        ticker=state_vars.get("ticker", "시장전체"),
        date=state_vars.get("date", "최근"),
        regime=state_vars.get("regime", "현재"),
    )
    return filled.strip()


# ─────────────────────────────────────────────
# 6. 단일 컬렉션 검색 → 포맷된 텍스트 반환
# ─────────────────────────────────────────────
def _search_and_format(
    collection: str,
    query: str,
    k: int,
    token_budget: int,
    slot_label: str,
) -> str:
    if not query:
        return ""

    all_docs = _get_all_documents(collection)
    if not all_docs:
        return ""

    try:
        retriever = build_hybrid_retriever(
            collection_name=collection,
            documents=all_docs,
            k=k,
        )
        docs: list[Document] = retriever.invoke(query)
    except Exception as e:
        print(f"[RAG 경고] '{collection}' 하이브리드 검색 실패: {e}")
        return ""

    if not docs:
        return ""

    lines = [f"[{slot_label} — {collection}]"]
    used_tokens = _count_tokens(lines[0])

    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "출처 미상")
        date   = doc.metadata.get("date", "")
        header = f"\n[{i}] {source} {date}".strip()
        body   = doc.page_content.strip()

        chunk        = f"{header}\n{body}"
        chunk_tokens = _count_tokens(chunk)

        if used_tokens + chunk_tokens > token_budget:
            remaining = token_budget - used_tokens
            if remaining > 100:
                lines.append(_truncate_to_budget(chunk, remaining))
            break

        lines.append(chunk)
        used_tokens += chunk_tokens

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 7. 메인 함수 — 에이전트 호출 진입점
# ─────────────────────────────────────────────
def get_context_for_agent(
    agent_name: str,
    state_vars: Optional[dict] = None,
) -> str:
    if state_vars is None:
        state_vars = {}

    config = AGENT_RAG_CONFIG.get(agent_name)
    if config is None:
        print(f"[RAG 경고] '{agent_name}'에 대한 RAG 설정이 없습니다.")
        return ""

    parts: list[str] = []

    # Primary 컬렉션 검색
    primary_cfg   = config["primary"]
    primary_query = build_rag_query(agent_name, "primary", state_vars)
    primary_text  = _search_and_format(
        collection  =primary_cfg["collection"],
        query       =primary_query,
        k           =primary_cfg["k"],
        token_budget=primary_cfg["budget"],
        slot_label  ="주요 참고",
    )
    if primary_text:
        parts.append(primary_text)

    # Secondary 컬렉션 검색
    secondary_cfg = config.get("secondary")
    if secondary_cfg is not None:
        secondary_query = build_rag_query(agent_name, "secondary", state_vars)
        secondary_text  = _search_and_format(
            collection  =secondary_cfg["collection"],
            query       =secondary_query,
            k           =secondary_cfg["k"],
            token_budget=secondary_cfg["budget"],
            slot_label  ="보조 참고",
        )
        if secondary_text:
            parts.append(secondary_text)

    if not parts:
        return ""

    header    = "[참고 컨텍스트]"
    body      = "\n\n".join(parts)
    full_text = f"{header}\n{body}"

    if _count_tokens(full_text) > TOTAL_TOKEN_BUDGET:
        full_text = _truncate_to_budget(full_text, TOTAL_TOKEN_BUDGET)

    return full_text


# ─────────────────────────────────────────────
# 8. 프롬프트 주입 헬퍼 — 에이전트에서 직접 사용
# ─────────────────────────────────────────────
def inject_context_into_prompt(
    system_prompt: str,
    context: str,
) -> str:
    if not context:
        return system_prompt

    return f"{system_prompt}\n\n{context}"