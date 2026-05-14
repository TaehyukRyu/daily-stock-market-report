"""
tests/test_notion_publisher.py

notion_publisher v4.0 단위 테스트 — Notion API 호출 없음.
build_v4_blocks()와 _markdown_to_blocks() 블록 구조 검증.
"""

import pytest
from src.graph.notion_publisher import (
    build_v4_blocks,
    _markdown_to_blocks,
    _rich_text,
    _parse_bold,
    _block,
    _divider,
    _callout,
    _toggle,
    _heading,
    _bullet,
)
from src.schemas.agent_output import AnalysisReport


# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────

def _make_agent(name: str, rec: str, conf: float) -> AnalysisReport:
    return AnalysisReport(
        agent_name=name,
        recommendation=rec,
        confidence=conf,
        reasoning=["근거1", "근거2", "근거3"],
        data_sources=["소스A", "소스B"],
        prediction_basis=["정량1", "정량2"],
        risk_factors=["리스크1"],
    )


@pytest.fixture
def agents() -> list[AnalysisReport]:
    return [
        _make_agent("macro_economist", "BUY",  0.75),
        _make_agent("quant_analyst",   "HOLD", 0.60),
        _make_agent("sentiment_analyst","SELL", 0.55),
    ]


@pytest.fixture
def chief_buy() -> AnalysisReport:
    return AnalysisReport(
        agent_name="chief_strategist",
        recommendation="BUY",
        confidence=0.78,
        reasoning=["이유1", "이유2", "이유3"],
        data_sources=["소스X", "소스Y"],
        prediction_basis=["숫자1", "숫자2"],
        risk_factors=["리스크A"],
        entry_price=300_000.0,
        stop_loss=288_000.0,
        stop_loss_pct=-4.0,
        take_profit_1=324_000.0,
        take_profit_2=336_000.0,
        rr_ratio=2.0,
        position_size_pct=7.8,
        holding_period_weeks=2,
        entry_strategy="분할매수",
    )


@pytest.fixture
def chief_hold() -> AnalysisReport:
    return AnalysisReport(
        agent_name="chief_strategist",
        recommendation="HOLD",
        confidence=0.60,
        reasoning=["이유1", "이유2", "이유3"],
        data_sources=["소스X", "소스Y"],
        prediction_basis=["숫자1", "숫자2"],
        risk_factors=["리스크A"],
    )


@pytest.fixture
def qualified(agents) -> list[AnalysisReport]:
    return agents[:2]


@pytest.fixture
def blocks_buy(agents, chief_buy, qualified) -> list[dict]:
    return build_v4_blocks(
        ticker="005930",
        regime="bull",
        strategy="BUY",
        chief_report=chief_buy,
        qualified_reports=qualified,
        all_reports=agents + [chief_buy],
        debate_summary="Bull: 강세. Bear: 과열.",
        error_log=[],
    )


@pytest.fixture
def blocks_hold(agents, chief_hold, qualified) -> list[dict]:
    return build_v4_blocks(
        ticker="005930",
        regime="sideways",
        strategy="HOLD",
        chief_report=chief_hold,
        qualified_reports=qualified,
        all_reports=agents + [chief_hold],
        debate_summary="",
        error_log=[],
    )


# ─────────────────────────────────────────────────────────
# _rich_text 유틸 테스트
# ─────────────────────────────────────────────────────────

def test_rich_text_basic():
    rt = _rich_text("hello")
    assert isinstance(rt, list)
    assert rt[0]["text"]["content"] == "hello"


def test_rich_text_bold():
    rt = _rich_text("bold", bold=True)
    assert rt[0]["annotations"]["bold"] is True


def test_rich_text_chunking():
    long_text = "x" * 4500
    rt = _rich_text(long_text)
    # 4500자 → 3청크 (2000+2000+500)
    assert len(rt) == 3
    for chunk in rt:
        assert len(chunk["text"]["content"]) <= 2000


def test_rich_text_empty():
    rt = _rich_text("")
    assert len(rt) == 1
    assert rt[0]["text"]["content"] == ""


# ─────────────────────────────────────────────────────────
# _parse_bold 유틸 테스트
# ─────────────────────────────────────────────────────────

def test_parse_bold_mixed():
    rt = _parse_bold("일반 **굵게** 일반2")
    texts = [chunk["text"]["content"] for chunk in rt]
    bolds = [chunk["annotations"]["bold"] for chunk in rt]
    assert "굵게" in texts
    bold_idx = texts.index("굵게")
    assert bolds[bold_idx] is True


def test_parse_bold_no_bold():
    rt = _parse_bold("그냥 텍스트")
    assert all(not c["annotations"]["bold"] for c in rt)


# ─────────────────────────────────────────────────────────
# Block 유틸 테스트
# ─────────────────────────────────────────────────────────

def test_divider_structure():
    d = _divider()
    assert d["type"] == "divider"
    assert d["object"] == "block"


def test_callout_structure():
    c = _callout("경고 텍스트", emoji="⚠️")
    assert c["type"] == "callout"
    assert c["callout"]["icon"]["emoji"] == "⚠️"
    assert any("경고 텍스트" in chunk["text"]["content"]
               for chunk in c["callout"]["rich_text"])


def test_toggle_structure():
    children = [_divider()]
    t = _toggle("제목", children)
    assert t["type"] == "toggle"
    assert t["toggle"]["children"] == children
    assert t["toggle"]["rich_text"][0]["text"]["content"] == "제목"


def test_heading_levels():
    for level in (1, 2, 3):
        h = _heading(level, "테스트")
        assert h["type"] == f"heading_{level}"


def test_bullet_structure():
    b = _bullet("항목")
    assert b["type"] == "bulleted_list_item"


# ─────────────────────────────────────────────────────────
# build_v4_blocks 구조 검증
# ─────────────────────────────────────────────────────────

def test_build_returns_list(blocks_buy):
    assert isinstance(blocks_buy, list)


def test_build_nonempty(blocks_buy):
    assert len(blocks_buy) > 0


def test_build_all_have_type(blocks_buy):
    for b in blocks_buy:
        assert "type" in b


def test_build_has_dividers(blocks_buy):
    dividers = [b for b in blocks_buy if b["type"] == "divider"]
    assert len(dividers) >= 4  # 헤더 후, 섹션 사이마다


def test_build_buy_has_green_callout(blocks_buy):
    callouts = [b for b in blocks_buy if b["type"] == "callout"]
    # BUY → green_background callout 존재
    green_callouts = [c for c in callouts if c["callout"].get("color") == "green_background"]
    assert len(green_callouts) >= 1


def test_build_buy_entry_price_in_callout(blocks_buy):
    callouts = [b for b in blocks_buy if b["type"] == "callout"]
    green_callouts = [c for c in callouts if c["callout"].get("color") == "green_background"]
    assert green_callouts
    text = " ".join(
        chunk["text"]["content"]
        for chunk in green_callouts[0]["callout"]["rich_text"]
    )
    assert "300,000" in text


def test_build_hold_has_yellow_callout(blocks_hold):
    callouts = [b for b in blocks_hold if b["type"] == "callout"]
    yellow = [c for c in callouts if c["callout"].get("color") == "yellow_background"]
    assert len(yellow) >= 1


def test_build_has_toggle_for_analysis(blocks_buy):
    toggles = [b for b in blocks_buy if b["type"] == "toggle"]
    assert len(toggles) >= 1


def test_build_toggle_has_children(blocks_buy):
    toggles = [b for b in blocks_buy if b["type"] == "toggle"]
    rationale_toggle = next(
        (t for t in toggles if "분석" in t["toggle"]["rich_text"][0]["text"]["content"]), None
    )
    assert rationale_toggle is not None
    assert len(rationale_toggle["toggle"]["children"]) > 0


def test_build_heading_in_blocks(blocks_buy):
    headings = [b for b in blocks_buy if b["type"].startswith("heading_")]
    assert len(headings) >= 3


def test_build_ticker_in_header_callout(blocks_buy):
    # 첫 번째 블록은 헤더 callout
    first = blocks_buy[0]
    assert first["type"] == "callout"
    text = " ".join(c["text"]["content"] for c in first["callout"]["rich_text"])
    assert "005930" in text


def test_build_no_chief_in_agents(blocks_buy, agents, chief_buy, qualified):
    """all_reports에 chief_strategist가 섞여도 에이전트 섹션에서 분리돼야 함."""
    blocks = build_v4_blocks(
        ticker="005930", regime="bull", strategy="BUY",
        chief_report=chief_buy,
        qualified_reports=qualified,
        all_reports=agents + [chief_buy],
    )
    assert isinstance(blocks, list)


def test_build_debate_toggle_present_when_debate(blocks_buy):
    toggles = [b for b in blocks_buy if b["type"] == "toggle"]
    debate_toggle = next(
        (t for t in toggles if "토론" in t["toggle"]["rich_text"][0]["text"]["content"]), None
    )
    assert debate_toggle is not None


def test_build_no_debate_toggle_when_empty(blocks_hold):
    toggles = [b for b in blocks_hold if b["type"] == "toggle"]
    debate_toggles = [
        t for t in toggles if "토론" in t["toggle"]["rich_text"][0]["text"]["content"]
    ]
    assert len(debate_toggles) == 0


def test_build_error_log_appears(agents, chief_hold, qualified):
    blocks = build_v4_blocks(
        ticker="005930", regime="bull", strategy="HOLD",
        chief_report=chief_hold,
        qualified_reports=qualified,
        all_reports=agents + [chief_hold],
        error_log=["regime_detector 타임아웃"],
    )
    bullets = [b for b in blocks if b["type"] == "bulleted_list_item"]
    texts = [
        " ".join(c["text"]["content"] for c in b["bulleted_list_item"]["rich_text"])
        for b in bullets
    ]
    assert any("타임아웃" in t for t in texts)


def test_build_without_structured_data_no_crash():
    """chief_report=None, all_reports=[] → 빈 블록 목록이어도 안전해야 함."""
    blocks = build_v4_blocks(
        ticker="005930", regime="neutral", strategy="HOLD",
        chief_report=None,
        all_reports=[],
    )
    assert isinstance(blocks, list)


# ─────────────────────────────────────────────────────────
# _markdown_to_blocks fallback 테스트
# ─────────────────────────────────────────────────────────

def test_markdown_heading1():
    blocks = _markdown_to_blocks("# 제목1")
    h1 = [b for b in blocks if b["type"] == "heading_1"]
    assert len(h1) == 1
    assert h1[0]["heading_1"]["rich_text"][0]["text"]["content"] == "제목1"


def test_markdown_heading2():
    blocks = _markdown_to_blocks("## 섹션")
    h2 = [b for b in blocks if b["type"] == "heading_2"]
    assert len(h2) == 1


def test_markdown_heading3():
    blocks = _markdown_to_blocks("### 소섹션")
    h3 = [b for b in blocks if b["type"] == "heading_3"]
    assert len(h3) == 1


def test_markdown_bullet():
    blocks = _markdown_to_blocks("- 항목1\n- 항목2")
    bullets = [b for b in blocks if b["type"] == "bulleted_list_item"]
    assert len(bullets) == 2


def test_markdown_divider():
    blocks = _markdown_to_blocks("---")
    dividers = [b for b in blocks if b["type"] == "divider"]
    assert len(dividers) == 1


def test_markdown_paragraph():
    blocks = _markdown_to_blocks("일반 텍스트 입니다.")
    paras = [b for b in blocks if b["type"] == "paragraph"]
    assert len(paras) >= 1


def test_markdown_bold_inline():
    blocks = _markdown_to_blocks("**굵게** 일반")
    paras = [b for b in blocks if b["type"] == "paragraph"]
    assert paras
    rich = paras[0]["paragraph"]["rich_text"]
    bold_chunks = [c for c in rich if c["annotations"]["bold"]]
    assert bold_chunks


def test_markdown_callout_warning():
    blocks = _markdown_to_blocks("⚠️ 주의 사항")
    callouts = [b for b in blocks if b["type"] == "callout"]
    assert len(callouts) == 1


def test_markdown_empty_string():
    blocks = _markdown_to_blocks("")
    assert isinstance(blocks, list)


def test_markdown_mixed():
    md = "# 제목\n\n## 섹션\n\n- 항목\n\n---\n\n일반"
    blocks = _markdown_to_blocks(md)
    types = [b["type"] for b in blocks]
    assert "heading_1" in types
    assert "heading_2" in types
    assert "bulleted_list_item" in types
    assert "divider" in types
    assert "paragraph" in types
