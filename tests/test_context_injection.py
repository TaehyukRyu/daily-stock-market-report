"""
tests/test_context_injection.py

에이전트 RAG 연결 검증 테스트
실행: .\.venv\Scripts\python -m pytest tests/test_context_injection.py -v
"""

import pytest
from src.rag.context_injection import (
    build_rag_query,
    get_context_for_agent,
    inject_context_into_prompt,
    AGENT_RAG_CONFIG,
    QUERY_TEMPLATES,
    _count_tokens,
    TOTAL_TOKEN_BUDGET,
)


# ─────────────────────────────────────────────
# Step 0: 설정 테이블 무결성 검증
# ─────────────────────────────────────────────
def test_all_agents_have_config():
    """8개 에이전트 모두 AGENT_RAG_CONFIG에 등록되어 있는지"""
    expected_agents = [
        "macro_economist", "kr_market_specialist", "us_market_specialist",
        "technical_analyst", "quant_analyst", "sentiment_analyst",
        "fundamental_analyst", "chief_strategist",
    ]
    for agent in expected_agents:
        assert agent in AGENT_RAG_CONFIG, f"{agent} 설정 누락"
        assert agent in QUERY_TEMPLATES, f"{agent} 쿼리 템플릿 누락"


def test_budget_sum_within_total():
    """primary + secondary 예산 합이 TOTAL_TOKEN_BUDGET(2000) 이하인지"""
    for agent, config in AGENT_RAG_CONFIG.items():
        total = config["primary"]["budget"]
        if config.get("secondary"):
            total += config["secondary"]["budget"]
        assert total <= TOTAL_TOKEN_BUDGET, (
            f"{agent}: 예산 합계 {total} > {TOTAL_TOKEN_BUDGET}"
        )


# ─────────────────────────────────────────────
# Step 1: 쿼리 템플릿 치환 테스트
# ─────────────────────────────────────────────
def test_query_template_substitution():
    """ticker/date/regime 변수가 정상 치환되는지"""
    state_vars = {"ticker": "005930", "date": "2025-05-08", "regime": "BULL"}

    query = build_rag_query("sentiment_analyst", "primary", state_vars)
    assert "2025-05-08" in query, f"date 치환 실패: {query}"

    query = build_rag_query("kr_market_specialist", "primary", state_vars)
    assert "005930" in query, f"ticker 치환 실패: {query}"

    query = build_rag_query("chief_strategist", "primary", state_vars)
    assert "BULL" in query, f"regime 치환 실패: {query}"


def test_query_template_missing_vars():
    """state_vars가 비어있어도 KeyError 없이 기본값으로 치환되는지"""
    query = build_rag_query("macro_economist", "primary", {})
    assert query != "", "빈 state_vars에서 빈 쿼리 반환됨"
    assert "{ticker}" not in query, "변수 미치환 — 포맷 실패"
    assert "{date}" not in query


def test_secondary_none_returns_empty():
    """secondary 없는 에이전트의 secondary 쿼리는 빈 문자열 반환"""
    query = build_rag_query("sentiment_analyst", "secondary", {"ticker": "005930"})
    assert query == "", f"secondary 없는 에이전트에서 쿼리 반환됨: {query}"


# ─────────────────────────────────────────────
# Step 2: 빈 컬렉션에서 get_context_for_agent 동작
# ─────────────────────────────────────────────
def test_empty_collection_returns_empty_string():
    """ChromaDB 컬렉션이 비어있으면 빈 문자열 반환"""
    context = get_context_for_agent(
        agent_name="chief_strategist",
        state_vars={"ticker": "시장전체", "date": "2025-05-08", "regime": "RISK_OFF"},
    )
    assert isinstance(context, str), "str이 아닌 타입 반환됨"


def test_unknown_agent_returns_empty_string():
    """등록되지 않은 에이전트 이름 → 빈 문자열 반환 (예외 없음)"""
    context = get_context_for_agent(agent_name="존재하지않는에이전트", state_vars={})
    assert context == ""


# ─────────────────────────────────────────────
# Step 3: 토큰 예산 검증
# ─────────────────────────────────────────────
def test_token_budget_not_exceeded():
    """반환 컨텍스트 토큰이 TOTAL_TOKEN_BUDGET 이하인지"""
    context = get_context_for_agent(
        agent_name="sentiment_analyst",
        state_vars={"date": "2025-05-08"},
    )
    if context:
        token_count = _count_tokens(context)
        assert token_count <= TOTAL_TOKEN_BUDGET, (
            f"토큰 예산 초과: {token_count} > {TOTAL_TOKEN_BUDGET}"
        )


# ─────────────────────────────────────────────
# Step 4: 프롬프트 주입 헬퍼 테스트
# ─────────────────────────────────────────────
def test_inject_context_into_prompt_with_context():
    """컨텍스트가 있으면 시스템 프롬프트 뒤에 붙는지"""
    base = "당신은 감성 분석 전문가입니다."
    ctx  = "[참고 컨텍스트]\n[주요 참고 — news_articles]\n[1] 삼성전자 뉴스..."
    result = inject_context_into_prompt(base, ctx)
    assert base in result
    assert ctx in result
    assert result.index(base) < result.index(ctx), "컨텍스트가 프롬프트 앞에 옴"


def test_inject_context_into_prompt_empty_context():
    """컨텍스트가 빈 문자열이면 원본 프롬프트 그대로 반환"""
    base = "당신은 감성 분석 전문가입니다."
    result = inject_context_into_prompt(base, "")
    assert result == base, "빈 컨텍스트인데 프롬프트가 변경됨"