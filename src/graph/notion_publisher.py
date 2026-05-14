"""
src/graph/notion_publisher.py

Notion 발행 모듈 v4.0 — L5 Report & Publishing

v4.0 변경:
  - build_v4_blocks(): 구조화된 Notion 블록 빌더
      섹션 1: 🎯 Action Now — callout (BUY 시 거래 파라미터)
      섹션 2: 📊 에이전트 신호 요약 — bulleted list
      섹션 3: 🌐 시장 컨텍스트 — paragraph + toggle(debate)
      섹션 4: 📋 에이전트별 분석 — toggle (접기)
      섹션 5: 📎 부록 — paragraph
  - publish_to_notion() 시그니처 확장:
      chief_report, qualified_reports, all_reports,
      market_data, debate_summary, error_log (선택적)
  - 구조화 데이터 없으면 _markdown_to_blocks() fallback

[Notion API 제약]
  - rich_text content 최대 2000자 → 초과 시 자동 분할
  - children 한 번에 최대 100블록 → 초과 시 append_block_children으로 추가
  - toggle 블록 children은 pages.create에서 인라인 전달 가능
"""

import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from notion_client import Client, APIResponseError
from dotenv import load_dotenv

from src.schemas.agent_output import AnalysisReport

load_dotenv()


# ─────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────

NOTION_API_KEY     = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

FALLBACK_DIR       = Path("data/reports")
MAX_TEXT_LENGTH    = 2000
MAX_BLOCKS_PER_REQ = 100

KST          = timezone(timedelta(hours=9))
SIGNAL_EMOJI = {"BUY": "🟢 BUY", "SELL": "🔴 SELL", "HOLD": "🟡 HOLD"}
SORT_ORDER   = {"SELL": 0, "HOLD": 1, "BUY": 2}


# ─────────────────────────────────────────────────────────
# 1. rich_text 유틸
# ─────────────────────────────────────────────────────────

def _rich_text(content: str, bold: bool = False) -> list[dict]:
    if not content:
        return [{"type": "text", "text": {"content": ""}, "annotations": {"bold": False}}]
    chunks = [content[i: i + MAX_TEXT_LENGTH] for i in range(0, len(content), MAX_TEXT_LENGTH)]
    return [
        {"type": "text", "text": {"content": c}, "annotations": {"bold": bold}}
        for c in chunks
    ]


def _parse_bold(text: str) -> list[dict]:
    parts  = re.split(r"\*\*(.+?)\*\*", text)
    result = []
    for i, part in enumerate(parts):
        if not part:
            continue
        result.extend(_rich_text(part, bold=(i % 2 == 1)))
    return result if result else _rich_text(text)


# ─────────────────────────────────────────────────────────
# 2. Block 생성 유틸
# ─────────────────────────────────────────────────────────

def _block(block_type: str, rich_text: list[dict]) -> dict:
    return {"object": "block", "type": block_type, block_type: {"rich_text": rich_text}}


def _heading(level: int, text: str) -> dict:
    t = f"heading_{level}"
    return {"object": "block", "type": t, t: {"rich_text": _rich_text(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _parse_bold(text)}}


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout(text: str, emoji: str = "⚠️", color: str = "yellow_background") -> dict:
    return {
        "object": "block",
        "type":   "callout",
        "callout": {
            "rich_text": _rich_text(text),
            "icon":      {"type": "emoji", "emoji": emoji},
            "color":     color,
        },
    }


def _toggle(title: str, children: list[dict]) -> dict:
    return {
        "object": "block",
        "type":   "toggle",
        "toggle": {
            "rich_text": _rich_text(title),
            "children":  children,
        },
    }


# ─────────────────────────────────────────────────────────
# 3. v4.0 블록 빌더
# ─────────────────────────────────────────────────────────

def _build_action_now_blocks(chief_report: Optional[AnalysisReport]) -> list[dict]:
    """섹션 1: 최종 판단 (Action Now)."""
    blocks: list[dict] = [_heading(2, "🎯 최종 판단 (Action Now)")]

    if chief_report is None:
        blocks.append(_block("paragraph", _rich_text("Chief Strategist 분석 결과 없음")))
        return blocks

    rec  = chief_report.recommendation
    conf = chief_report.confidence
    sig  = SIGNAL_EMOJI.get(rec, rec)

    if rec == "BUY" and chief_report.entry_price is not None:
        ep     = chief_report.entry_price
        sl     = chief_report.stop_loss
        sl_pct = chief_report.stop_loss_pct
        tp1    = chief_report.take_profit_1
        tp2    = chief_report.take_profit_2
        rr     = chief_report.rr_ratio
        pos    = chief_report.position_size_pct
        wks    = chief_report.holding_period_weeks
        ent    = chief_report.entry_strategy

        lines = [f"{sig}  신뢰도 {conf:.0%}"]
        lines.append(f"진입가: {ep:,.0f}원")
        if sl is not None and sl_pct is not None:
            lines.append(f"손절가: {sl:,.0f}원 ({sl_pct:+.1f}%)")
        if tp1 is not None:
            lines.append(f"1차 익절: {tp1:,.0f}원")
        if tp2 is not None:
            lines.append(f"2차 익절: {tp2:,.0f}원")
        if rr is not None:
            lines.append(f"R:R: {rr:.1f}")
        if pos is not None:
            lines.append(f"포지션: {pos:.0f}%")
        if wks is not None:
            lines.append(f"보유: {wks}주")
        if ent is not None:
            lines.append(f"전략: {ent}")

        blocks.append(_callout("\n".join(lines), emoji="🎯", color="green_background"))

    elif rec == "HOLD":
        blocks.append(_callout(f"{sig}  신뢰도 {conf:.0%}\n현재 포지션 유지 / 관망 권장",
                               emoji="🟡", color="yellow_background"))
    else:
        blocks.append(_callout(f"{sig}  신뢰도 {conf:.0%}\n매도 / 리스크 축소 권장",
                               emoji="🔴", color="red_background"))

    return blocks


def _build_signal_summary_blocks(
    agents: list[AnalysisReport],
    chief_report: Optional[AnalysisReport],
    qualified_names: set[str],
) -> list[dict]:
    """섹션 2: 에이전트 신호 요약."""
    blocks: list[dict] = [_heading(2, "📊 에이전트 신호 요약")]

    for r in sorted(agents, key=lambda x: SORT_ORDER.get(x.recommendation, 1)):
        sig      = SIGNAL_EMOJI.get(r.recommendation, r.recommendation)
        qg       = "✅" if r.agent_name in qualified_names else "⚠️ 폴백"
        conf_bar = "█" * int(r.confidence * 10) + "░" * (10 - int(r.confidence * 10))
        blocks.append(_bullet(f"**{r.agent_name}** — {sig}  신뢰도 {r.confidence:.2f} `{conf_bar}`  {qg}"))

    if chief_report:
        sig      = SIGNAL_EMOJI.get(chief_report.recommendation, chief_report.recommendation)
        conf_bar = "█" * int(chief_report.confidence * 10) + "░" * (10 - int(chief_report.confidence * 10))
        blocks.append(_bullet(
            f"**chief_strategist** — **{sig}**  신뢰도 **{chief_report.confidence:.2f}** `{conf_bar}`"
        ))

    return blocks


def _build_context_blocks(regime: str, debate_summary: str) -> list[dict]:
    """섹션 3: 시장 컨텍스트."""
    blocks: list[dict] = [
        _heading(2, "🌐 시장 컨텍스트"),
        _block("paragraph", _parse_bold(f"**현재 레짐:** {regime.upper()}")),
    ]

    if debate_summary:
        debate_children = [
            _block("paragraph", _rich_text(line))
            for line in debate_summary.split("\n")
            if line.strip()
        ]
        blocks.append(_toggle("⚔️ Bull vs Bear 토론 요약 (클릭하여 펼치기)", debate_children))

    return blocks


def _build_rationale_toggle(
    agents: list[AnalysisReport],
    chief_report: Optional[AnalysisReport],
    qualified_names: set[str],
) -> dict:
    """섹션 4: 에이전트별 분석 (toggle 접기)."""
    children: list[dict] = []

    for r in sorted(agents, key=lambda x: SORT_ORDER.get(x.recommendation, 1)):
        gate = "✅" if r.agent_name in qualified_names else "⚠️ (QG 폴백)"
        sig  = SIGNAL_EMOJI.get(r.recommendation, r.recommendation)
        children.append(_heading(3, f"{gate} [{r.agent_name}] {sig} (신뢰도: {r.confidence:.2f})"))
        for reason in r.reasoning:
            children.append(_bullet(reason))
        if r.prediction_basis:
            children.append(_block("paragraph", _rich_text("근거:")))
            for basis in r.prediction_basis:
                children.append(_bullet(basis))
        if r.risk_factors:
            children.append(_callout("리스크: " + " / ".join(r.risk_factors), emoji="⚠️"))
        children.append(_divider())

    if chief_report:
        children.append(_heading(3, "🎯 [chief_strategist] 종합 판단"))
        for reason in chief_report.reasoning:
            children.append(_bullet(reason))
        if chief_report.selection_rationale:
            children.append(_block("paragraph", _parse_bold(f"**선정 종목:** {chief_report.selection_rationale}")))

    return _toggle("📋 에이전트별 분석 (클릭하여 펼치기)", children)


def _build_appendix_blocks(
    agents:    list[AnalysisReport],
    chief_report: Optional[AnalysisReport],
    error_log: list[str],
) -> list[dict]:
    """섹션 5: 부록."""
    now    = datetime.now(KST)
    blocks = [
        _heading(2, "📎 부록"),
        _block("paragraph", _rich_text(f"생성 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} KST")),
    ]

    seen_src: set[str] = set()
    for r in agents + ([chief_report] if chief_report else []):
        for src in r.data_sources:
            if src not in seen_src:
                seen_src.add(src)
                blocks.append(_bullet(src))

    seen_risk: set[str] = set()
    unique_risks: list[str] = []
    for r in agents + ([chief_report] if chief_report else []):
        for risk in r.risk_factors:
            if risk not in seen_risk:
                seen_risk.add(risk)
                unique_risks.append(risk)
    if unique_risks:
        blocks.append(_heading(3, "⚠️ 통합 리스크"))
        for i, risk in enumerate(unique_risks[:8], 1):
            blocks.append(_bullet(f"{i}. {risk}"))

    if error_log:
        blocks.append(_heading(3, "🔧 오류 로그"))
        for err in error_log:
            blocks.append(_bullet(err))

    return blocks


def build_v4_blocks(
    ticker:            str,
    regime:            str,
    strategy:          str,
    chief_report:      Optional[AnalysisReport]       = None,
    qualified_reports: Optional[list[AnalysisReport]] = None,
    all_reports:       Optional[list[AnalysisReport]] = None,
    debate_summary:    str                             = "",
    error_log:         Optional[list[str]]            = None,
) -> list[dict]:
    """
    v4.0 Notion 블록 리스트 생성.
    toggle 블록(섹션 4)은 단일 블록으로 포함되며 children을 인라인으로 담는다.
    """
    agents          = [r for r in (all_reports or []) if r.agent_name != "chief_strategist"]
    qualified_names = {r.agent_name for r in (qualified_reports or [])}
    error_log       = error_log or []

    blocks: list[dict] = []

    # 헤더 callout
    now     = datetime.now(KST)
    weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    blocks.append(_callout(
        f"AI 투자 리포트 {now.strftime('%Y.%m.%d')} ({weekday}) "
        f"{now.strftime('%H:%M')} KST  |  {ticker}  |  레짐: {regime.upper()}  |  전략: {strategy}",
        emoji="📈",
        color="blue_background",
    ))
    blocks.append(_divider())

    # 섹션 1: Action Now
    blocks += _build_action_now_blocks(chief_report)
    blocks.append(_divider())

    # 섹션 2: 신호 요약
    blocks += _build_signal_summary_blocks(agents, chief_report, qualified_names)
    blocks.append(_divider())

    # 섹션 3: 시장 컨텍스트
    blocks += _build_context_blocks(regime, debate_summary)
    blocks.append(_divider())

    # 섹션 4: 분석 근거 (toggle)
    if agents or chief_report:
        blocks.append(_build_rationale_toggle(agents, chief_report, qualified_names))
        blocks.append(_divider())

    # 섹션 5: 부록
    blocks += _build_appendix_blocks(agents, chief_report, error_log)

    return blocks


# ─────────────────────────────────────────────────────────
# 4. 마크다운 → Block fallback (v3.0 호환)
# ─────────────────────────────────────────────────────────

_DIVIDER_RE = re.compile(r"^[─\-=]{3,}$")


def _markdown_to_blocks(text: str) -> list[dict]:
    blocks   = []
    lines    = text.split("\n")
    prev_emp = False

    for line in lines:
        s = line.strip()
        if not s:
            if not prev_emp:
                blocks.append(_block("paragraph", _rich_text("")))
            prev_emp = True
            continue
        prev_emp = False

        if s.startswith("# ") and not s.startswith("## "):
            blocks.append(_heading(1, s[2:].strip()))
        elif s.startswith("## ") and not s.startswith("### "):
            blocks.append(_heading(2, s[3:].strip()))
        elif s.startswith("### "):
            blocks.append(_heading(3, s[4:].strip()))
        elif s.startswith("- "):
            blocks.append(_bullet(s[2:].strip()))
        elif _DIVIDER_RE.match(s):
            blocks.append(_divider())
        elif s.startswith("⚠️"):
            blocks.append(_callout(s, emoji="⚠️"))
        else:
            blocks.append(_block("paragraph", _parse_bold(s)))

    return blocks


# ─────────────────────────────────────────────────────────
# 5. 로컬 Fallback 저장
# ─────────────────────────────────────────────────────────

def _save_local_fallback(content: str, date_str: str, ticker: str) -> str:
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    filepath = FALLBACK_DIR / f"report_{date_str}_{ticker}.md"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


# ─────────────────────────────────────────────────────────
# 6. Notion 발행 메인 함수
# ─────────────────────────────────────────────────────────

async def publish_to_notion(
    report_content:    str,
    ticker:            str,
    regime:            str,
    strategy:          str,
    chief_report:      Optional[AnalysisReport]       = None,
    qualified_reports: Optional[list[AnalysisReport]] = None,
    all_reports:       Optional[list[AnalysisReport]] = None,
    market_data:       Optional[dict]                 = None,
    debate_summary:    str                             = "",
    error_log:         Optional[list[str]]            = None,
) -> dict:
    """
    리포트를 Notion Database에 새 페이지로 발행합니다.

    structured data(chief_report 등)가 있으면 v4.0 블록 빌더 사용.
    없으면 report_content(마크다운) → _markdown_to_blocks() fallback.

    Returns:
        성공: {"success": True,  "url": page_url}
        실패: {"success": False, "fallback_path": str, "error": str}
    """
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    title    = f"[{strategy}] 데일리 리포트 — {date_str} | {ticker} | {regime.upper()}"

    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        fallback = _save_local_fallback(report_content, date_str, ticker)
        return {
            "success":       False,
            "fallback_path": fallback,
            "error":         "NOTION_API_KEY 또는 NOTION_DATABASE_ID 미설정",
        }

    try:
        notion = Client(auth=NOTION_API_KEY)

        # v4.0 구조화 블록 우선, fallback은 마크다운 파싱
        if chief_report is not None or all_reports:
            blocks = build_v4_blocks(
                ticker            = ticker,
                regime            = regime,
                strategy          = strategy,
                chief_report      = chief_report,
                qualified_reports = qualified_reports,
                all_reports       = all_reports,
                debate_summary    = debate_summary,
                error_log         = error_log,
            )
        else:
            blocks = _markdown_to_blocks(report_content)

        # 면책조항
        blocks.append(_divider())
        blocks.append(_callout(
            "본 리포트는 AI 생성 분석으로 투자 조언이 아닙니다. "
            "모든 투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다. "
            "과거 성과가 미래 수익을 보장하지 않습니다.",
            emoji="⚠️",
        ))

        # DB title 속성 자동 탐지
        db_meta         = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
        title_prop_name = "Name"
        for prop_name, prop_meta in db_meta.get("properties", {}).items():
            if prop_meta.get("type") == "title":
                title_prop_name = prop_name
                break
        print(f"  → DB title 속성명: '{title_prop_name}'")

        # 페이지 생성 (첫 100블록)
        first_chunk = blocks[:MAX_BLOCKS_PER_REQ]
        page = notion.pages.create(
            parent     = {"database_id": NOTION_DATABASE_ID},
            properties = {title_prop_name: {"title": [{"text": {"content": title}}]}},
            children   = first_chunk,
        )

        page_id  = page["id"]
        page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

        # 100블록 초과분 append
        remaining = blocks[MAX_BLOCKS_PER_REQ:]
        while remaining:
            chunk     = remaining[:MAX_BLOCKS_PER_REQ]
            remaining = remaining[MAX_BLOCKS_PER_REQ:]
            notion.blocks.children.append(block_id=page_id, children=chunk)

        print(f"  ✅ Notion 발행 완료: {page_url}")
        return {"success": True, "url": page_url}

    except APIResponseError as e:
        error_msg = f"Notion API 오류: {e.status} {e.code} — {e}"
        print(f"  ⚠️ {error_msg}")
        fallback = _save_local_fallback(report_content, date_str, ticker)
        print(f"  → 로컬 Fallback 저장: {fallback}")
        return {"success": False, "fallback_path": fallback, "error": error_msg}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"  ⚠️ Notion 발행 실패: {error_msg}")
        fallback = _save_local_fallback(report_content, date_str, ticker)
        print(f"  → 로컬 Fallback 저장: {fallback}")
        return {"success": False, "fallback_path": fallback, "error": error_msg}
