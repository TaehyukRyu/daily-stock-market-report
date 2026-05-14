from typing import Annotated
import operator
from pydantic import BaseModel, Field
from src.schemas.agent_output import AnalysisReport


class GraphState(BaseModel):

    ticker:           str  = Field(default="005930")
    market_data:      dict = Field(default_factory=dict)

    # operator.add → 노드가 반환할 때마다 리스트에 누적 (replace 불가)
    analysis_reports: Annotated[list[AnalysisReport], operator.add] = Field(default_factory=list)

    # Quality Gate 통과 에이전트만 담는 필드.
    # operator.add 없음 → quality_gate_node가 반환하면 그 값으로 교체(replace).
    # debate_node와 chief_strategist는 이 필드를 우선 사용한다.
    qualified_reports: list[AnalysisReport] = Field(default_factory=list)   # v2.3 신규

    # signal_reconciliation 결과 — 종목별 우선순위 목록
    reconciled_signals: list[dict] = Field(default_factory=list)            # v2.4 신규

    final_strategy:   str  = Field(default='')
    report_content:   str  = Field(default='')
    current_regime:   str  = Field(default='unknown')
    debate_summary:   str  = Field(default='')
    error_log:        list[str] = Field(default_factory=list)