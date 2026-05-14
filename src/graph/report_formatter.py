"""
src/graph/report_formatter.py

리포트 포맷터 v4.0

5섹션 구조:
  1. 🎯 최종 판단 (Action Now) — BUY 시 거래 파라미터 카드
  2. 📊 에이전트 신호 요약 (SELL→HOLD→BUY 정렬)
  3. 🌐 시장 컨텍스트 (레짐 + debate_summary)
  4. 📋 에이전트별 분석 (접기용 상세 내용)
  5. 📎 부록 (생성 시각 KST + 통합 리스크 + 데이터 소스)

[validate_report 호환]
  security.py validate_report()는 "최종 판단" OR "에이전트별 분석" 존재 여부 확인.
  섹션 1 제목("🎯 최종 판단"), 섹션 4 제목("📋 에이전트별 분석") 양쪽 모두 포함됨.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.schemas.agent_output import AnalysisReport

logger = logging.getLogger(__name__)

KST          = timezone(timedelta(hours=9))
WEEKDAY_KR   = ["월", "화", "수", "목", "금", "토", "일"]
SIGNAL_EMOJI = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "🟡 HOLD"}
SORT_ORDER   = {"SELL": 0, "HOLD": 1, "BUY": 2}


# ─────────────────────────────────────────────────────────────────────────────
# 섹션 생성 함수
# ─────────────────────────────────────────────────────────────────────────────

def _header(ticker: str, regime: str, strategy: str) -> list[str]:
    now     = datetime.now(KST)
    weekday = WEEKDAY_KR[now.weekday()]
    return [
        f"# AI 투자 리포트 {now.strftime('%Y.%m.%d')} ({weekday}) {now.strftime('%H:%M')} KST",
        "",
        f"> 종목: **{ticker}** | 시장 레짐: **{regime.upper()}** | 최종 전략: **{strategy}**",
        "",
        "---",
        "",
    ]


def _action_now_section(final: Optional[AnalysisReport]) -> list[str]:
    """섹션 1: 최종 판단 (Action Now) — BUY 시 거래 파라미터 테이블 포함."""
    lines = ["## 🎯 최종 판단 (Action Now)", ""]

    if final is None:
        lines += ["*Chief Strategist 분석 결과 없음*", "", "---", ""]
        return lines

    rec  = final.recommendation
    conf = final.confidence
    lines.append(f"**{SIGNAL_EMOJI.get(rec, rec)}** (신뢰도: {conf:.0%})")
    lines.append("")

    if rec == "BUY" and final.entry_price is not None:
        ep      = final.entry_price
        sl      = final.stop_loss
        sl_pct  = final.stop_loss_pct
        tp1     = final.take_profit_1
        tp2     = final.take_profit_2
        rr      = final.rr_ratio
        pos     = final.position_size_pct
        wks     = final.holding_period_weeks
        ent     = final.entry_strategy

        lines += [
            "| 항목 | 값 |",
            "|------|-----|",
            f"| 진입가 | {ep:,.0f}원 |",
        ]
        if sl is not None and sl_pct is not None:
            lines.append(f"| 손절가 | {sl:,.0f}원 ({sl_pct:+.1f}%) |")
        if tp1 is not None:
            lines.append(f"| 1차 익절 | {tp1:,.0f}원 |")
        if tp2 is not None:
            lines.append(f"| 2차 익절 | {tp2:,.0f}원 |")
        if rr is not None:
            lines.append(f"| R:R 비율 | {rr:.1f} |")
        if pos is not None:
            lines.append(f"| 포지션 비중 | {pos:.0f}% |")
        if wks is not None:
            lines.append(f"| 예상 보유 | {wks}주 |")
        if ent is not None:
            lines.append(f"| 진입 전략 | {ent} |")
        lines.append("")

    elif rec == "HOLD":
        lines += ["현재 포지션 유지 또는 관망 권장", ""]
    elif rec == "SELL":
        lines += ["매도 또는 리스크 축소 권장", ""]

    lines += ["---", ""]
    return lines


def _signal_summary_section(
    agents: list[AnalysisReport],
    final:  Optional[AnalysisReport],
    qualified_names: set[str],
) -> list[str]:
    """섹션 2: 에이전트 신호 요약 테이블."""
    lines = ["## 📊 에이전트 신호 요약", ""]
    lines += [
        "| 에이전트 | 신호 | 신뢰도 | QG |",
        "|----------|------|--------|----|",
    ]

    for r in sorted(agents, key=lambda x: SORT_ORDER.get(x.recommendation, 1)):
        sig      = SIGNAL_EMOJI.get(r.recommendation, r.recommendation)
        qg       = "✅" if r.agent_name in qualified_names else "⚠️"
        conf_bar = "█" * int(r.confidence * 10) + "░" * (10 - int(r.confidence * 10))
        lines.append(f"| {r.agent_name} | {sig} | {r.confidence:.2f} `{conf_bar}` | {qg} |")

    if final:
        sig      = SIGNAL_EMOJI.get(final.recommendation, final.recommendation)
        conf_bar = "█" * int(final.confidence * 10) + "░" * (10 - int(final.confidence * 10))
        lines.append(
            f"| **chief_strategist** | **{sig}** | **{final.confidence:.2f}** `{conf_bar}` | — |"
        )

    lines += ["", "---", ""]
    return lines


def _market_context_section(regime: str, debate_summary: str) -> list[str]:
    """섹션 3: 시장 컨텍스트."""
    lines = ["## 🌐 시장 컨텍스트", "", f"**현재 레짐:** {regime.upper()}", ""]

    if debate_summary:
        lines += ["### ⚔️ Bull vs Bear 토론 요약", "", debate_summary, ""]

    lines += ["---", ""]
    return lines


def _analysis_rationale_section(
    agents: list[AnalysisReport],
    final:  Optional[AnalysisReport],
    qualified_names: set[str],
) -> list[str]:
    """섹션 4: 에이전트별 분석 (상세 근거)."""
    lines = ["## 📋 에이전트별 분석", ""]

    for r in sorted(agents, key=lambda x: SORT_ORDER.get(x.recommendation, 1)):
        gate = "✅" if r.agent_name in qualified_names else "⚠️ (QG 폴백)"
        sig  = SIGNAL_EMOJI.get(r.recommendation, r.recommendation)
        lines.append(f"### {gate} [{r.agent_name}] {sig} (신뢰도: {r.confidence:.2f})")
        for reason in r.reasoning:
            lines.append(f"- {reason}")
        if r.prediction_basis:
            lines += ["", "**근거:**"]
            for basis in r.prediction_basis:
                lines.append(f"- {basis}")
        if r.risk_factors:
            lines += ["", f"> ⚠️ 리스크: {' / '.join(r.risk_factors)}"]
        lines.append("")

    if final:
        lines.append("### 🎯 [chief_strategist] 종합 판단")
        for reason in final.reasoning:
            lines.append(f"- {reason}")
        if final.selection_rationale:
            lines += ["", f"**선정 종목:** {final.selection_rationale}"]
        lines.append("")

    lines += ["---", ""]
    return lines


def _appendix_section(
    agents:    list[AnalysisReport],
    final:     Optional[AnalysisReport],
    error_log: list[str],
) -> list[str]:
    """섹션 5: 부록 (생성 시각 + 데이터 소스 + 통합 리스크)."""
    now   = datetime.now(KST)
    lines = ["## 📎 부록", "", f"**생성 시각:** {now.strftime('%Y-%m-%d %H:%M:%S')} KST", ""]

    # 데이터 소스 중복 제거
    seen_src: set[str] = set()
    unique_sources: list[str] = []
    for r in agents + ([final] if final else []):
        for src in r.data_sources:
            if src not in seen_src:
                seen_src.add(src)
                unique_sources.append(src)
    if unique_sources:
        lines.append("**데이터 소스:**")
        for src in unique_sources:
            lines.append(f"- {src}")
        lines.append("")

    # 통합 리스크 (중복 제거, 최대 8개)
    seen_risk: set[str] = set()
    unique_risks: list[str] = []
    for r in agents + ([final] if final else []):
        for risk in r.risk_factors:
            if risk not in seen_risk:
                seen_risk.add(risk)
                unique_risks.append(risk)
    if unique_risks:
        lines.append("**통합 리스크 요약:**")
        for i, risk in enumerate(unique_risks[:8], 1):
            lines.append(f"{i}. {risk}")
        lines.append("")

    if error_log:
        lines.append("**오류 로그:**")
        for err in error_log:
            lines.append(f"- {err}")
        lines.append("")

    return lines


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def format_report_v4(
    ticker:             str,
    regime:             str,
    strategy:           str,
    final:              Optional[AnalysisReport],
    agents:             list[AnalysisReport],
    qualified_reports:  list[AnalysisReport],
    debate_summary:     str        = "",
    reconciled_signals: list[dict] | None = None,
    error_log:          list[str]  | None = None,
) -> str:
    """5섹션 v4.0 마크다운 리포트 생성."""
    qualified_names = {r.agent_name for r in (qualified_reports or [])}
    error_log       = error_log or []

    lines: list[str] = []
    lines += _header(ticker, regime, strategy)
    lines += _action_now_section(final)
    lines += _signal_summary_section(agents, final, qualified_names)
    lines += _market_context_section(regime, debate_summary)
    lines += _analysis_rationale_section(agents, final, qualified_names)
    lines += _appendix_section(agents, final, error_log)

    return "\n".join(lines)


async def report_formatter_node(state) -> dict:
    """파이프라인 노드 — v4.0 포맷터."""
    print(f"\n[5/7] report_formatter v4.0")

    final  = next((r for r in state.analysis_reports if r.agent_name == "chief_strategist"), None)
    agents = [r for r in state.analysis_reports if r.agent_name != "chief_strategist"]

    report_content = format_report_v4(
        ticker             = state.ticker,
        regime             = state.current_regime,
        strategy           = state.final_strategy,
        final              = final,
        agents             = agents,
        qualified_reports  = state.qualified_reports or [],
        debate_summary     = state.debate_summary or "",
        reconciled_signals = state.reconciled_signals or [],
        error_log          = state.error_log or [],
    )

    try:
        now = datetime.now(KST)
        os.makedirs("data/reports", exist_ok=True)
        path = f"data/reports/report_{now.strftime('%Y-%m-%d_%H%M%S')}_{state.ticker}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"  ✅ 리포트 저장: {path}")
    except Exception as e:
        logger.warning(f"[report_formatter] 저장 실패: {e}")

    return {"report_content": report_content}
