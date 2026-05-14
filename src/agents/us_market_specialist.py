import asyncio
import json
from datetime import datetime
from fastmcp import Client
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.base_agent import create_structured_agent
from src.schemas.agent_output import AnalysisReport
from src.rag.context_injection import get_context_for_agent, inject_context_into_prompt


US_MARKET_SYSTEM_PROMPT = "[REDACTED] Proprietary prompt engineering"

BIGTECH_TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META"]


def parse(raw) -> dict:
    if hasattr(raw, "structured_content") and raw.structured_content:
        return raw.structured_content
    if hasattr(raw, "content") and raw.content:
        return json.loads(raw.content[0].text)
    return {}


async def _collect_us_market_data() -> dict:
    async with Client("src/mcp_servers/us_market/server.py") as client:
        sp500_task    = client.call_tool("get_sp500_data",       {"days": 30})
        vix_task      = client.call_tool("get_vix",              {})           # ✅ Fix: days 파라미터 제거
        treasury_task = client.call_tool("get_treasury_yields",  {})           # ✅ Fix: days 파라미터 제거
        stock_tasks   = [
            client.call_tool("get_us_stock", {"symbol": t})                   # ✅ Fix: ticker→symbol, days 제거
            for t in BIGTECH_TICKERS
        ]

        results = await asyncio.gather(
            sp500_task, vix_task, treasury_task, *stock_tasks,
            return_exceptions=True
        )

    sp500_raw, vix_raw, treasury_raw = results[0], results[1], results[2]
    stock_raws = results[3:]

    sp500    = parse(sp500_raw)    if not isinstance(sp500_raw, Exception)    else {}
    vix      = parse(vix_raw)      if not isinstance(vix_raw, Exception)      else {}
    treasury = parse(treasury_raw) if not isinstance(treasury_raw, Exception) else {}

    stocks = {}
    for ticker, raw in zip(BIGTECH_TICKERS, stock_raws):
        stocks[ticker] = parse(raw) if not isinstance(raw, Exception) else {}

    return {
        "sp500":   sp500,
        "vix":     vix,
        "treasury": treasury,
        "bigtech": stocks,
    }


def _format_prompt(data: dict) -> str:
    # [REDACTED] Proprietary data formatting logic
    return ""


async def run_us_market_specialist() -> AnalysisReport:
    data      = await _collect_us_market_data()
    formatted = _format_prompt(data)

    # ── RAG 컨텍스트 주입 (market_reports + news_articles 컬렉션)
    rag_context    = get_context_for_agent(
        agent_name="us_market_specialist",
        state_vars={"date": datetime.now().strftime("%Y-%m-%d")},
    )
    system_content = inject_context_into_prompt(US_MARKET_SYSTEM_PROMPT, rag_context)

    agent = create_structured_agent(model="gpt-4o-mini")

    report: AnalysisReport = await agent.ainvoke([
        SystemMessage(content=system_content),
        HumanMessage(content=formatted),
    ])

    report.agent_name = "us_market_specialist"

    return report