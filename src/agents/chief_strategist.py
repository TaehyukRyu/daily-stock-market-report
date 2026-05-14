"""
Chief Strategist Agent v4.0

[변경사항]
  v3.0: AsyncAnthropic(claude-opus-4-6) + tool_use 직접 호출
  v3.1: weight_context 파라미터 추가 (피드백 루프 연결)
  v4.0: 거래 파라미터 출력 추가 (리포트 v4.0 1단계)
        - current_price 파라미터 추가 (pipeline에서 최근 종가 주입)
        - tool_use 스키마에 entry_price / stop_loss / take_profit 등 9개 필드 추가
        - 시스템 프롬프트에 손절·익절 계산 규칙 주입
        - AnalysisReport 생성 시 거래 파라미터 매핑

[v4 거래 파라미터]
  BUY 판단 시에만 채워짐 (HOLD/SELL 시 None):
  - entry_price, stop_loss, stop_loss_pct
  - take_profit_1 (R:R 1:2), take_profit_2 (R:R 1:3)
  - rr_ratio, position_size_pct, holding_period_weeks, entry_strategy
"""

import os
from datetime import datetime
from anthropic import AsyncAnthropic

from src.schemas.agent_output import AnalysisReport
from src.rag.context_injection import get_context_for_agent, inject_context_into_prompt


# ─────────────────────────────────────────────────────────
# 설정 상수
# ─────────────────────────────────────────────────────────

CHIEF_MODEL = "claude-opus-4-6"
MAX_TOKENS  = 2048


# ─────────────────────────────────────────────────────────
# 시스템 프롬프트 (v3.0과 동일)
# ─────────────────────────────────────────────────────────

CHIEF_SYSTEM_PROMPT = "[REDACTED] Proprietary prompt engineering"


# ─────────────────────────────────────────────────────────
# tool_use 스키마 정의 (v3.0과 동일)
# ─────────────────────────────────────────────────────────

CHIEF_TOOLS = [
    {
        "name": "submit_final_strategy",
        "description": (
            "7명 애널리스트 분석과 토론 결과를 종합한 최종 투자 전략을 제출합니다. "
            "분석이 완료되면 반드시 이 도구를 호출하여 결과를 제출해야 합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recommendation": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD"],
                    "description": "confidence 가중 투표 결과",
                },
                "confidence": {
                    "type": "number",
                    "description": "최종 확신도 (0.0~1.0). 에이전트 간 충돌이 클수록 낮게.",
                },
                "reasoning": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "투표 집계 → 토론 핵심 쟁점 → 결론 순서로 3개 이상",
                },
                "data_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "인용한 에이전트 이름 목록 (2개 이상)",
                },
                "prediction_basis": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "가장 강한 신호 2개 이상 (에이전트명 + 수치 포함)",
                },
                "risk_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "반대 의견의 핵심 논거 1개 이상",
                },
                "selection_rationale": {
                    "type": "string",
                    "description": "최종 주목 종목 1~2개와 그 이유",
                },
                "entry_price": {
                    "type": "number",
                    "description": "BUY 시 추천 진입가. 현재가 기준. HOLD/SELL 시 생략.",
                },
                "stop_loss": {
                    "type": "number",
                    "description": "BUY 시 손절가. entry_price × (1 + stop_loss_pct/100).",
                },
                "stop_loss_pct": {
                    "type": "number",
                    "description": "BUY 시 손절 비율(%). 음수, -3 ~ -6 범위. 예: -4.0",
                },
                "take_profit_1": {
                    "type": "number",
                    "description": "BUY 시 1차 익절가. R:R 1:2 기준 (손절폭 × 2).",
                },
                "take_profit_2": {
                    "type": "number",
                    "description": "BUY 시 2차 익절가. R:R 1:3 기준 (손절폭 × 3).",
                },
                "rr_ratio": {
                    "type": "number",
                    "description": "Risk:Reward 비율. (take_profit_1 - entry_price) / (entry_price - stop_loss).",
                },
                "position_size_pct": {
                    "type": "number",
                    "description": "BUY 시 포지션 사이즈 (시드 대비 %). confidence × 10, 최대 15.",
                },
                "holding_period_weeks": {
                    "type": "integer",
                    "description": "BUY 시 예상 보유 기간 (주). 단기 1~2, 중기 3~4, 장기 6~8.",
                },
                "entry_strategy": {
                    "type": "string",
                    "enum": ["시장가", "분할매수", "지정가대기"],
                    "description": "BUY 시 진입 전략.",
                },
            },
            "required": [
                "recommendation",
                "confidence",
                "reasoning",
                "data_sources",
                "prediction_basis",
                "risk_factors",
                "selection_rationale",
            ],
        },
    }
]


# ─────────────────────────────────────────────────────────
# 프롬프트 포맷터
# [v3.1 변경] weight_context 파라미터 추가
# ─────────────────────────────────────────────────────────

def _format_reports_as_prompt(
    reports: list[AnalysisReport],
    regime: str,
    debate_summary: str,
    weight_context: str = "",
    current_price: float = 0.0,        # ← v4.0 추가
) -> str:
    lines = [
        f"=== 현재 시장 레짐: {regime.upper()} ===\n",
    ]

    if current_price > 0:
        lines.append(f"[현재가] {current_price:,.0f}원 (거래 파라미터 계산 기준)\n")

    # ── v3.1: 에이전트 신뢰도 섹션 (weight_context가 있을 때만 삽입) ──────────
    # weight_context 예시:
    #   [에이전트 신뢰도 — Bull 레짐 기준 최근 예측 정확도]
    #     - kr_market_specialist   0.2134  ↑ 높음
    #     - quant_analyst          0.1205  ↓ 낮음
    #   ✅ 신뢰도 높은 에이전트의 의견에 더 큰 비중을 두세요.
    #
    # 삽입 위치: 레짐 정보 직후, 투표 집계 직전
    # → 모델이 투표 집계를 읽기 전에 "어떤 에이전트를 더 신뢰해야 하는지"
    #   컨텍스트를 먼저 파악하게 하기 위함.
    #
    # 워밍업 기간(sample_count < 10)에는 pipeline.py에서 빈 문자열("")을 전달하므로
    # 이 섹션이 생략됨 → v3.0과 완전히 동일한 동작.
    if weight_context:
        lines.append(weight_context)
        lines.append("")

    lines.append(f"=== 전문가 애널리스트 {len(reports)}명의 분석 결과 ===\n")

    buy_weight  = sum(r.confidence for r in reports if r.recommendation == "BUY")
    sell_weight = sum(r.confidence for r in reports if r.recommendation == "SELL")
    hold_weight = sum(r.confidence for r in reports if r.recommendation == "HOLD")

    lines.append("[투표 집계 (confidence 가중합)]")
    lines.append(f"  BUY:  {buy_weight:.2f}")
    lines.append(f"  SELL: {sell_weight:.2f}")
    lines.append(f"  HOLD: {hold_weight:.2f}")
    lines.append("")

    for r in reports:
        lines.append(f"─── {r.agent_name} ───")
        lines.append(f"  판단: {r.recommendation} (확신도: {r.confidence:.2f})")
        lines.append("  추론:")
        for step in r.reasoning:
            lines.append(f"    • {step}")
        lines.append("  수치 근거:")
        for basis in r.prediction_basis:
            lines.append(f"    • {basis}")
        lines.append("  리스크:")
        for risk in r.risk_factors:
            lines.append(f"    • {risk}")
        if r.selection_rationale:
            lines.append(f"  주목 종목: {r.selection_rationale}")
        lines.append("")

    if debate_summary:
        lines.append("=" * 50)
        lines.append(debate_summary)
        lines.append("=" * 50)
        lines.append("")
        lines.append("=== 위 분석들과 토론 결과를 종합하여 최종 투자 전략을 도출해주세요 ===")
    else:
        lines.append(
            "=== 위 분석들을 종합하여 최종 투자 전략을 도출해주세요 ==="
            " (이번 라운드는 한쪽이 명확히 우세하여 토론 생략됨)"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
# tool_use 응답 파싱 (v3.0과 동일)
# ─────────────────────────────────────────────────────────

def _parse_tool_use_response(response) -> dict:
    """
    Anthropic tool_use 응답에서 submit_final_strategy 호출 인자를 추출.

    응답 content 블록 구조:
      [{"type": "tool_use", "name": "submit_final_strategy", "input": {...}}, ...]
    """
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_final_strategy":
            return block.input

    raise ValueError(
        f"tool_use 블록 없음. stop_reason={response.stop_reason}, "
        f"content={response.content}"
    )


# ─────────────────────────────────────────────────────────
# 메인 함수
# [v3.1 변경] weight_context 파라미터 추가
# ─────────────────────────────────────────────────────────

async def run_chief_strategist(
    reports: list[AnalysisReport],
    regime: str = "neutral",
    debate_summary: str = "",
    weight_context: str = "",
    current_price: float = 0.0,        # ← v4.0 추가 (pipeline에서 최근 종가 주입)
) -> AnalysisReport:
    if not reports:
        raise ValueError("Chief Strategist에 전달할 에이전트 결과가 없습니다.")

    # 1. 프롬프트 구성 (v4.0: current_price 추가)
    formatted = _format_reports_as_prompt(
        reports        = reports,
        regime         = regime,
        debate_summary = debate_summary,
        weight_context = weight_context,
        current_price  = current_price,    # ← v4.0 추가
    )

    # 2. RAG 컨텍스트 주입 (v3.0과 동일)
    rag_context = get_context_for_agent(
        agent_name="chief_strategist",
        state_vars={
            "regime": regime,
            "date":   datetime.now().strftime("%Y-%m-%d"),
        },
    )
    system_content = inject_context_into_prompt(CHIEF_SYSTEM_PROMPT, rag_context)

    # 3. Anthropic API 직접 호출 (v3.0과 동일)
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model       = CHIEF_MODEL,
        max_tokens  = MAX_TOKENS,
        system      = system_content,
        tools       = CHIEF_TOOLS,
        tool_choice = {"type": "tool", "name": "submit_final_strategy"},
        messages    = [{"role": "user", "content": formatted}],
    )

    # 4. tool_use 응답 → dict 파싱 (v3.0과 동일)
    result_dict = _parse_tool_use_response(response)

    # 5. AnalysisReport 객체 생성 (v4.0: 거래 파라미터 매핑 추가)
    report = AnalysisReport(
        agent_name          = "chief_strategist",
        recommendation      = result_dict["recommendation"],
        confidence          = float(result_dict["confidence"]),
        reasoning           = result_dict["reasoning"],
        data_sources        = result_dict["data_sources"],
        prediction_basis    = result_dict["prediction_basis"],
        risk_factors        = result_dict["risk_factors"],
        selection_rationale = result_dict.get("selection_rationale", ""),
        # 거래 파라미터 (BUY 시 LLM이 채워줌, HOLD/SELL 시 None)
        entry_price          = result_dict.get("entry_price"),
        stop_loss            = result_dict.get("stop_loss"),
        stop_loss_pct        = result_dict.get("stop_loss_pct"),
        take_profit_1        = result_dict.get("take_profit_1"),
        take_profit_2        = result_dict.get("take_profit_2"),
        rr_ratio             = result_dict.get("rr_ratio"),
        position_size_pct    = result_dict.get("position_size_pct"),
        holding_period_weeks = result_dict.get("holding_period_weeks"),
        entry_strategy       = result_dict.get("entry_strategy"),
    )

    return report