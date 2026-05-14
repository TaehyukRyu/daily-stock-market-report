"""
AI 투자 리포트 파이프라인 v2.8

[변경사항]
  v2.1~v2.6: (생략 — 인수인계 문서 참조)
  v2.7: 복원력 추가 (node_with_timeout, 포지션 섹션 복원)
  v2.8: 보안 추가
        - setup_secure_logging(): API 키 로그 마스킹
        - validate_ticker(): 6자리 숫자 검증 + SQL Injection 차단
        - validate_report(): Notion 발행 전 필수 섹션 검증
"""

import asyncio
from langgraph.graph import StateGraph, END
from src.schemas.graph_state import GraphState
from src.schemas.agent_output import AnalysisReport
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)
load_dotenv()

os.environ['LANGCHAIN_TRACING_V2'] = os.getenv("LANGCHAIN_TRACING_V2", 'false')
os.environ['LANGCHAIN_ENDPOINT']   = os.getenv("LANGCHAIN_ENDPOINT", "")
os.environ["LANGCHAIN_API_KEY"]    = os.getenv("LANGCHAIN_API_KEY", "")
os.environ["LANGCHAIN_PROJECT"]    = os.getenv("LANGCHAIN_PROJECT", "")

# ── 보안 초기화 ───────────────────────────────────────────────────────────────
from src.utils.security import (
    setup_secure_logging,
    validate_ticker,
    validate_report,
    set_ticker_whitelist,
    InvalidTickerError,
    InvalidReportError,
)

setup_secure_logging()   # 모든 logger에 API 키 마스킹 필터 자동 적용

# ── 피드백 루프 초기화 ────────────────────────────────────────────────────────
from src.data.prediction_logger import (
    setup_feedback_system,
    log_agent_predictions,
    get_agent_weights,
)
from src.data.position_tracker import (
    setup_position_tracker,
    format_position_section,
)

setup_feedback_system()
setup_position_tracker()


# ──────────────────────────────────────────────────────────
# 노드 Timeout 래퍼 (v2.7)
# ──────────────────────────────────────────────────────────

def node_with_timeout(node_fn, timeout_seconds: float, node_name: str):
    async def wrapper(state: GraphState) -> dict:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await node_fn(state)
        except asyncio.TimeoutError:
            logger.error(f"[NodeTimeout] {node_name} — {timeout_seconds}초 초과")
            print(f"  ⏱️ [{node_name}] {timeout_seconds}초 초과 — 건너뜀")
            return {}
        except Exception as e:
            logger.error(f"[NodeError] {node_name}: {type(e).__name__}: {e}")
            print(f"  ❌ [{node_name}] 예외: {e}")
            return {}
    wrapper.__name__ = node_fn.__name__
    return wrapper


# ──────────────────────────────────────────
# 노드 1: 시장 스냅샷
# ──────────────────────────────────────────

async def data_ingest(state: GraphState) -> dict:
    print(f"\n[1/7] data_ingest — 종목: {state.ticker}")
    try:
        from src.mcp_servers.krx_market.server   import get_stock_price
        from src.mcp_servers.us_market.server    import get_vix
        from src.mcp_servers.news_economy.server import get_exchange_rate

        stock_data    = get_stock_price(state.ticker, days=5)
        vix_data      = get_vix()
        exchange_data = get_exchange_rate(days=5)

        return {"market_data": {
            "ticker":        state.ticker,
            "stock":         stock_data,
            "vix":           vix_data,
            "exchange_rate": exchange_data,
            "source":        "live",
        }}
    except Exception as e:
        print(f"  ⚠️ 스냅샷 수집 실패 (계속 진행): {e}")
        return {"market_data": {"ticker": state.ticker, "source": "fallback"}}


# ──────────────────────────────────────────
# 노드 1.5: 시장 레짐 탐지
# ──────────────────────────────────────────

from src.graph.regime_detector import regime_detector_node


# ──────────────────────────────────────────
# 노드 2: 7개 에이전트 병렬 실행
# ──────────────────────────────────────────

async def parallel_analysis(state: GraphState) -> dict:
    print(f"\n[2/7] parallel_analysis — 7개 에이전트 병렬 실행 (최대 3개 동시)")
    print(f"       현재 레짐: {state.current_regime.upper()}")

    from src.agents.macro_economist      import run_macro_economist
    from src.agents.kr_market_specialist import run_kr_market_specialist
    from src.agents.us_market_specialist import run_us_market_specialist
    from src.agents.quant_analyst        import run_quant_analyst
    from src.agents.technical_analyst    import run_technical_analyst
    from src.agents.sentiment_analyst    import run_sentiment_analyst
    from src.agents.fundamental_analyst  import run_fundamental_analyst

    agent_names = [
        "macro_economist", "kr_market_specialist", "us_market_specialist",
        "quant_analyst", "technical_analyst", "sentiment_analyst", "fundamental_analyst",
    ]

    semaphore     = asyncio.Semaphore(3)
    krx_semaphore = asyncio.Semaphore(2)

    async def run_with_semaphore(coro):
        async with semaphore:
            return await coro

    async def run_krx_agent(coro):
        async with krx_semaphore:
            async with semaphore:
                return await coro

    raw_results = await asyncio.gather(
        run_with_semaphore(run_macro_economist()),
        run_krx_agent(run_kr_market_specialist()),
        run_with_semaphore(run_us_market_specialist()),
        run_krx_agent(run_quant_analyst()),
        run_krx_agent(run_technical_analyst()),
        run_with_semaphore(run_sentiment_analyst()),
        run_krx_agent(run_fundamental_analyst()),
        return_exceptions=True,
    )

    reports = []
    errors  = []

    for name, result in zip(agent_names, raw_results):
        if isinstance(result, Exception):
            print(f"  ❌ {name} 실패: {result}")
            errors.append(f"{name}: {str(result)}")
            reports.append(AnalysisReport(
                agent_name=name,
                confidence=0.0,
                recommendation="HOLD",
                reasoning=[
                    f"에이전트 실행 실패: {str(result)}",
                    "MCP 데이터 수집 또는 LLM 호출 중 오류 발생",
                    "이 보고서는 신뢰할 수 없으므로 chief_strategist 종합 시 제외 권장",
                ],
                data_sources=["error_fallback", "pipeline_fallback"],
                selection_rationale=None,
                prediction_basis=["오류로 인한 대체값", "pipeline_fallback"],
                risk_factors=["에이전트 오류로 분석 불가"],
            ))
        else:
            print(f"  ✅ {name} — {result.recommendation} (신뢰도 {result.confidence})")
            reports.append(result)

    return {"analysis_reports": reports, "error_log": errors}


# ──────────────────────────────────────────
# 노드 2.5: Quality Gate
# ──────────────────────────────────────────

from src.graph.quality_gate import quality_gate_node


# ──────────────────────────────────────────
# 노드 3: Bull vs Bear 토론
# ──────────────────────────────────────────

from src.agents.debate import debate_node as _debate_node_original

async def debate_node(state: GraphState) -> dict:
    reports_for_debate = state.qualified_reports if state.qualified_reports else state.analysis_reports
    modified_state     = state.model_copy(update={"analysis_reports": reports_for_debate})
    return await _debate_node_original(modified_state)


# ──────────────────────────────────────────
# 노드 4: Chief Strategist
# ──────────────────────────────────────────

def _format_agent_weights_for_prompt(regime: str) -> str:
    try:
        weights = get_agent_weights(regime)
    except Exception as e:
        logger.warning(f"[pipeline] agent_weights 조회 실패: {e}")
        return "[에이전트 가중치 조회 실패 — 균등 취급]"

    if not weights:
        return "[에이전트 가중치 없음 — 균등 취급]"

    avg_weight     = sum(weights.values()) / len(weights)
    sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)

    lines = [f"[에이전트 신뢰도 — {regime} 레짐 기준]"]
    for agent_name, w in sorted_weights:
        trend = "↑ 높음" if w > avg_weight * 1.2 else "↓ 낮음" if w < avg_weight * 0.8 else "→ 보통"
        lines.append(f"  - {agent_name:<32} {w:.4f}  {trend}")
    lines.append("")
    lines.append("✅ 신뢰도 높은 에이전트의 의견에 더 큰 비중을 두세요.")
    lines.append("⚠️ 단, 모든 에이전트가 동일 방향을 가리킬 때만 강한 포지션을 취하세요.")

    return "\n".join(lines)


async def chief_strategist_node(state: GraphState) -> dict:
    reports    = state.qualified_reports if state.qualified_reports else state.analysis_reports
    has_debate = bool(state.debate_summary)
    regime     = state.current_regime

    print(f"\n[4/7] chief_strategist — {len(reports)}개 보고서 종합")
    print(f"       레짐: {regime.upper()}")
    print(f"       토론: {'포함' if has_debate else '생략 (한쪽 우세)'}")

    weight_context = _format_agent_weights_for_prompt(regime)

    from src.data.prediction_logger import WARMUP_SAMPLE_COUNT, get_weight_summary, _normalize_regime
    normalized_regime = _normalize_regime(regime)
    summary = get_weight_summary()
    warmup_agents = [
        r["agent_name"] for r in summary
        if r["regime"] == normalized_regime and r["sample_count"] < WARMUP_SAMPLE_COUNT
    ]
    if warmup_agents:
        print(f"       ⏳ 워밍업 중 ({len(warmup_agents)}개 에이전트)")
    else:
        print(f"       ✅ EMA 가중치 적용 중")

    from src.agents.chief_strategist import run_chief_strategist

    current_price = float(
        (state.market_data.get("stock") or {}).get("latest_close") or 0
    )

    final: AnalysisReport = await run_chief_strategist(
        reports        = reports,
        regime         = regime,
        debate_summary = state.debate_summary,
        weight_context = weight_context,
        current_price  = current_price,
    )
    print(f"  → 최종: {final.recommendation} (신뢰도 {final.confidence})")

    from src.graph.signal_reconciliation import run_signal_reconciliation, MAX_BUY_SIGNALS

    print(f"\n[4.5/7] signal_reconciliation")
    recon = run_signal_reconciliation(
        ticker         = state.ticker,
        recommendation = final.recommendation,
        confidence     = final.confidence,
    )

    current = recon["current"]
    if current and current.get("included"):
        print(f"  ✅ {state.ticker} → 매수 후보 {current['rank']}위")
    elif final.recommendation == "BUY":
        reason = current.get("exclusion_reason") if current else "미분류"
        print(f"  ⚠️ {state.ticker} BUY → 미선정 ({reason})")
    else:
        print(f"  → {state.ticker} {final.recommendation}")

    print(f"  → 오늘 매수 후보: {recon['buy_count']}/{MAX_BUY_SIGNALS}종목")

    return {
        "analysis_reports":   [final],
        "final_strategy":     final.recommendation,
        "reconciled_signals": recon["all_signals"],
    }


# ──────────────────────────────────────────
# 노드 5: 리포트 포맷팅 (v4.0 — src/graph/report_formatter.py)
# ──────────────────────────────────────────

from src.graph.report_formatter import report_formatter_node as report_formatter


# ──────────────────────────────────────────
# 노드 6: Notion 발행 (v2.8: 발행 전 검증 추가)
# ──────────────────────────────────────────

async def notion_publish(state: GraphState) -> dict:
    print(f"\n[6/7] notion_publish")

    # ── 발행 전 리포트 검증 ───────────────────────────────────────────────
    # 빈 리포트, None 포함, 필수 섹션 누락 시 발행 차단
    try:
        validate_report(state.report_content)
    except InvalidReportError as e:
        print(f"  ❌ 리포트 검증 실패 — 발행 차단: {e}")
        return {"error_log": list(state.error_log or []) + [f"리포트 검증 실패: {e}"]}

    from src.graph.notion_publisher import publish_to_notion

    chief_report = next(
        (r for r in state.analysis_reports if r.agent_name == "chief_strategist"), None
    )
    all_reports  = list(state.analysis_reports)

    result = await publish_to_notion(
        report_content    = state.report_content,
        ticker            = state.ticker,
        regime            = state.current_regime,
        strategy          = state.final_strategy,
        chief_report      = chief_report,
        qualified_reports = list(state.qualified_reports or []),
        all_reports       = all_reports,
        debate_summary    = state.debate_summary or "",
        error_log         = list(state.error_log or []),
    )

    if result["success"]:
        print(f"  ✅ 발행 완료: {result['url']}")
    else:
        print(f"  ⚠️ 발행 실패 — 로컬 저장됨: {result.get('fallback_path')}")

    print("─" * 60)
    print(state.report_content[:500], "..." if len(state.report_content) > 500 else "")
    print("─" * 60)
    return {}


# ──────────────────────────────────────────
# 노드 7: 예측 저장
# ──────────────────────────────────────────

async def log_predictions_node(state: GraphState) -> dict:
    print(f"\n[7/7] log_predictions — 오늘의 예측 저장")

    try:
        qualified_reports = state.qualified_reports or state.analysis_reports
        regime            = state.current_regime or "Neutral"

        if not qualified_reports:
            print("  ⚠️ 저장할 qualified_reports 없음 — 건너뜀")
            return {}

        saved_count = log_agent_predictions(
            qualified_reports = qualified_reports,
            regime            = regime,
        )

        from src.data.prediction_logger import record_regime, _normalize_regime
        record_regime(regime)

        print(f"  ✅ {saved_count}개 예측 저장 (레짐={_normalize_regime(regime)})")

    except Exception as e:
        logger.error(f"[pipeline] log_predictions_node 실패: {e}", exc_info=True)
        return {"error_log": list(state.error_log or []) + [f"prediction_logger 실패: {e}"]}

    return {}


# ──────────────────────────────────────────
# 그래프 조립
# ──────────────────────────────────────────

def build_pipeline() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("data_ingest",       node_with_timeout(data_ingest,            30,  "data_ingest"))
    graph.add_node("regime_detector",   node_with_timeout(regime_detector_node,   30,  "regime_detector"))
    graph.add_node("parallel_analysis", node_with_timeout(parallel_analysis,     180,  "parallel_analysis"))
    graph.add_node("quality_gate",      node_with_timeout(quality_gate_node,      30,  "quality_gate"))
    graph.add_node("debate",            node_with_timeout(debate_node,            90,  "debate"))
    graph.add_node("chief_strategist",  node_with_timeout(chief_strategist_node, 120,  "chief_strategist"))
    graph.add_node("report_formatter",  node_with_timeout(report_formatter,       30,  "report_formatter"))
    graph.add_node("notion_publish",    node_with_timeout(notion_publish,         30,  "notion_publish"))
    graph.add_node("log_predictions",   node_with_timeout(log_predictions_node,   30,  "log_predictions"))

    graph.set_entry_point("data_ingest")
    graph.add_edge("data_ingest",       "regime_detector")
    graph.add_edge("regime_detector",   "parallel_analysis")
    graph.add_edge("parallel_analysis", "quality_gate")
    graph.add_edge("quality_gate",      "debate")
    graph.add_edge("debate",            "chief_strategist")
    graph.add_edge("chief_strategist",  "report_formatter")
    graph.add_edge("report_formatter",  "notion_publish")
    graph.add_edge("notion_publish",    "log_predictions")
    graph.add_edge("log_predictions",   END)

    return graph.compile()


# ──────────────────────────────────────────
# 실행
# ──────────────────────────────────────────

async def run_pipeline(ticker: str = "005930"):
    # ── ticker 검증 (v2.8) ────────────────────────────────────────────────
    try:
        ticker = validate_ticker(ticker)
    except InvalidTickerError as e:
        print(f"❌ 유효하지 않은 ticker: {e}")
        return {}

    print("=" * 60)
    print(f"AI 투자 리포트 파이프라인 v2.8 — {ticker}")
    print("=" * 60)

    pipeline = build_pipeline()

    initial_state = {
        "ticker":             ticker,
        "market_data":        {},
        "analysis_reports":   [],
        "qualified_reports":  [],
        "reconciled_signals": [],
        "final_strategy":     "",
        "report_content":     "",
        "current_regime":     "unknown",
        "debate_summary":     "",
        "error_log":          [],
    }

    result = await pipeline.ainvoke(initial_state)
    print("\n✅ 파이프라인 완료")
    return result


if __name__ == "__main__":
    asyncio.run(run_pipeline("005930"))