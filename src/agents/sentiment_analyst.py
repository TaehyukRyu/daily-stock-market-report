"""
Sentiment / Informal Intelligence Agent

[현재 버전 v2]
  - 뉴스 카테고리별 감성 분석 (기존 유지)
  - 종목별 언급량 추세 데이터 추가 (mention_tracker 연동)
  - 언급량 급증 시 선행/후행 여부 경고 포함

[v1 → v2 변경]
  - _collect_sentiment_data()에 언급량 크롤링 추가
  - _format_prompt()에 언급량 컨텍스트 섹션 추가
  - 시스템 프롬프트에 언급량 해석 지침 추가

[v5.2 예정 추가 도구]
  search_naver_stock_board, search_daum_stock_board 추가 시
  _collect_sentiment_data()에서 함께 수집
"""

import asyncio
import json
from datetime import datetime
from fastmcp import Client
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.base_agent import create_structured_agent
from src.schemas.agent_output import AnalysisReport
from src.rag.context_injection import get_context_for_agent, inject_context_into_prompt
from src.universe.universe_builder import load_universe


SENTIMENT_SYSTEM_PROMPT = "[REDACTED] Proprietary prompt engineering"


# ─────────────────────────────────────────────────
# 종목 리스트 (언급량 크롤링 대상)
# ─────────────────────────────────────────────────

def _get_tickers(n: int = 10) -> list[str]:
    """유니버스 상위 N개 종목 코드 반환."""
    try:
        return load_universe()[:n]
    except Exception:
        # 유니버스 로드 실패 시 대표 종목 폴백
        return ["005930", "000660", "005380", "373220", "034020"]


# ─────────────────────────────────────────────────
# 데이터 수집
# ─────────────────────────────────────────────────

async def _collect_sentiment_data() -> dict:
    """
    두 가지 데이터를 수집합니다:
    1. 뉴스 카테고리별 헤드라인 (MCP 서버)
    2. 종목별 언급량 추세 (mention_tracker)
    """
    # ── 1. 뉴스 카테고리 데이터 (기존 방식 유지) ──
    news_data = {}
    try:
        async with Client("src/mcp_servers/news_economy/server.py") as news_client:
            news_raw = await news_client.call_tool("search_news", {
                "categories":        ["economy", "finance", "politics", "international", "industry"],
                "max_per_category":  20,
                "min_relevance_score": 0.5,
            })

        def parse(raw) -> dict:
            if hasattr(raw, "structured_content") and raw.structured_content:
                return raw.structured_content
            if hasattr(raw, "content") and raw.content:
                return json.loads(raw.content[0].text)
            return {}

        news_data = parse(news_raw)
    except Exception as e:
        print(f"  ⚠️ 뉴스 수집 실패: {e}")

    # ── 2. 종목별 언급량 추세 (mention_tracker) ──
    mention_context = ""
    try:
        from src.data.mention_tracker import crawl_tickers
        from src.data.daily_mention_stats import format_mention_context
        from src.data.mention_db import init_db

        tickers = _get_tickers(n=10)
        today   = datetime.now().strftime("%Y-%m-%d")

        # DB 초기화 (없으면 생성)
        init_db()

        # 오늘 아직 크롤링 안 된 종목만 크롤링
        print("  → 종목별 언급량 크롤링 중...")
        await crawl_tickers(tickers, today=today, max_concurrent=3)

        # 언급량 컨텍스트 포맷팅
        mention_context = format_mention_context(tickers, today=today)

    except Exception as e:
        print(f"  ⚠️ 언급량 데이터 수집 실패 (뉴스 분석만으로 진행): {e}")

    return {"news": news_data, "mention_context": mention_context}


# ─────────────────────────────────────────────────
# 프롬프트 포맷팅
# ─────────────────────────────────────────────────

def _format_prompt(data: dict) -> str:
    # [REDACTED] Proprietary data formatting logic
    return ""


# ─────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────

async def run_sentiment_analyst() -> AnalysisReport:
    """Sentiment Analyst 에이전트 실행 진입점."""

    data      = await _collect_sentiment_data()
    formatted = _format_prompt(data)

    # RAG 컨텍스트 주입
    rag_context = get_context_for_agent(
        agent_name="sentiment_analyst",
        state_vars={
            "date": datetime.now().strftime("%Y-%m-%d"),
        },
    )
    system_content = inject_context_into_prompt(SENTIMENT_SYSTEM_PROMPT, rag_context)

    agent = create_structured_agent(model="gpt-4o-mini")
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=formatted),
    ]
    report: AnalysisReport = await agent.ainvoke(messages)

    report.agent_name = "sentiment_analyst"

    return report