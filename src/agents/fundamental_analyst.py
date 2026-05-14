"""
Fundamental Analyst Agent
담당: 기업 펀더멘털 분석 (재무/컨센서스/공시)
소비 MCP: krx_market (get_financials, get_consensus_estimates, get_dart_disclosure)

[v2 변경]
  FUNDAMENTAL_TICKERS 하드코딩 → load_universe() 교체
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


# ─────────────────────────────────────────────────────────
# 분석 대상 종목 — 유니버스에서 동적 로드
# ─────────────────────────────────────────────────────────

def _get_tickers(n: int = 10) -> list[str]:
    return load_universe()[:n]


FUNDAMENTAL_SYSTEM_PROMPT = "[REDACTED] Proprietary prompt engineering"


# ─────────────────────────────────────────────────────────
# Step 1: 데이터 수집
# ─────────────────────────────────────────────────────────

async def _collect_fundamental_data() -> dict:
    """재무/컨센서스/공시 데이터를 병렬 수집합니다."""
    tickers = _get_tickers()

    async with Client("src/mcp_servers/krx_market/server.py") as krx_client:
        financials_tasks = [
            krx_client.call_tool("get_financials",          {"ticker": t})
            for t in tickers
        ]
        consensus_tasks = [
            krx_client.call_tool("get_consensus_estimates", {"ticker": t})
            for t in tickers
        ]
        dart_tasks = [
            krx_client.call_tool("get_dart_disclosure",     {"ticker": t, "days": 30})
            for t in tickers
        ]
        results = await asyncio.gather(*financials_tasks, *consensus_tasks, *dart_tasks)

    n               = len(tickers)
    financials_raws = results[:n]
    consensus_raws  = results[n:n*2]
    dart_raws       = results[n*2:]

    def parse(raw) -> dict:
        if hasattr(raw, "structured_content") and raw.structured_content:
            return raw.structured_content
        if hasattr(raw, "content") and raw.content:
            return json.loads(raw.content[0].text)
        return {}

    ticker_data = {}
    for i, ticker in enumerate(tickers):
        ticker_data[ticker] = {
            "financials": parse(financials_raws[i]),
            "consensus":  parse(consensus_raws[i]),
            "disclosure": parse(dart_raws[i]),
        }

    return ticker_data


# ─────────────────────────────────────────────────────────
# Step 2: 프롬프트 포맷팅
# ─────────────────────────────────────────────────────────

def _format_prompt(ticker_data: dict) -> str:
    # [REDACTED] Proprietary data formatting logic
    return ""


# ─────────────────────────────────────────────────────────
# Step 3: 에이전트 실행
# ─────────────────────────────────────────────────────────

async def run_fundamental_analyst() -> AnalysisReport:
    """Fundamental Analyst 에이전트 실행 진입점."""
    data      = await _collect_fundamental_data()
    formatted = _format_prompt(data)

    rag_context = get_context_for_agent(
        agent_name="fundamental_analyst",
        state_vars={
            "ticker": _get_tickers()[0],
            "date":   datetime.now().strftime("%Y-%m-%d"),
        },
    )
    system_content = inject_context_into_prompt(FUNDAMENTAL_SYSTEM_PROMPT, rag_context)

    agent = create_structured_agent(model="gpt-4o-mini")
    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=formatted),
    ]
    report: AnalysisReport = await agent.ainvoke(messages)
    report.agent_name = "fundamental_analyst"
    return report