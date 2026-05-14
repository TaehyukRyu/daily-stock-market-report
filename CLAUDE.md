# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run the full pipeline
```bash
python -m src.graph.pipeline          # default ticker 005930 (삼성전자)
python src/graph/pipeline.py          # same, direct execution
```

### Run tests
```bash
pytest tests/ -v                      # all tests
pytest tests/test_quant_analyst.py -v # single test file
python test_quick.py                  # quick ad-hoc agent smoke test
```

### Lint and type-check
```bash
ruff check src/                       # lint
mypy src/                             # type check
```

### Install dependencies (Windows, Python 3.11)
TA-Lib must be installed from the local wheel before the rest:
```bash
pip install TA_Lib-0.4.32-cp311-cp311-win_amd64.whl
pip install -r requirements.txt
```

### Environment variables
Copy `.env.example` to `.env` and fill in:
- `OPENAI_API_KEY` — 7 specialist agents (gpt-4o-mini)
- `ANTHROPIC_API_KEY` — chief_strategist (claude-opus-4-6) + debate (claude-sonnet-4-6)
- `NOTION_TOKEN` + `NOTION_DATABASE_ID` — Notion publishing (fallback: local `data/reports/`)
- `LANGCHAIN_API_KEY` / `LANGCHAIN_TRACING_V2` — LangSmith tracing (optional)
- `DART_API_KEY`, `GOOGLE_API_KEY`, `HUGGINGFACE_API_KEY` — MCP servers / embeddings

## Architecture

### Pipeline flow (`src/graph/pipeline.py`)
LangGraph `StateGraph` with `GraphState` (defined in `src/schemas/graph_state.py`):

```
data_ingest (30s)
  → regime_detector (30s)          # KOSPI MA20/60 + VIX → bull/bear/sideways/volatile/neutral
  → parallel_analysis (180s)       # 7 agents concurrently, semaphore(3) global, semaphore(2) KRX
  → quality_gate (30s)             # confidence≥0.6 AND reasoning≥3 AND data_sources≥2
  → debate (90s)                   # Bull vs Bear only when |BUY_weight - SELL_weight| < 1.0
  → chief_strategist (120s)        # claude-opus-4-6 via tool_use, EMA-weighted synthesis
  → report_formatter (30s)         # Markdown with agent signal table
  → notion_publish (30s)           # Notion API; fallback → data/reports/YYYY-MM-DD_ticker.md
  → log_predictions (30s)          # SQLite: prediction_log, agent_weights, regime_history
```

Each node is wrapped in `node_with_timeout()` — timeout returns `{}` (empty update), never halts the graph.

### LLM model assignment
| Component | Model | How |
|---|---|---|
| 7 specialist agents | `gpt-4o-mini` | `create_structured_agent()` via LangChain `with_structured_output(AnalysisReport)` |
| Debate (Bull/Bear) | `claude-sonnet-4-6` | `create_anthropic_text_agent()` — Anthropic SDK direct |
| Chief Strategist | `claude-opus-4-6` | `run_chief_strategist()` — Anthropic SDK `tool_use` with `submit_final_strategy` schema |

### Common output schema (`src/schemas/agent_output.py`)
Every agent returns `AnalysisReport`:
- `recommendation`: `BUY | SELL | HOLD`
- `confidence`: 0.0–1.0
- `reasoning`: list[str], min 3 items (Chain-of-Thought)
- `data_sources`: list[str], min 2 items
- `prediction_basis`: list[str], min 2 items (quantitative evidence)
- `risk_factors`: list[str], min 1 item

Quality Gate uses these fields directly. Fallback reports have `confidence=0.0` so they're automatically filtered.

### Resilience pattern (`src/agents/base_agent.py`, `src/utils/resilience.py`)
`ResilientChain` wraps every LLM call: CircuitBreaker (pybreaker, fail_max=5, reset=30s) → Timeout → LangChain `with_retry(3)` → `_make_fallback()`.  
Separate breakers: `openai_breaker`, `anthropic_breaker`, `dart_breaker`, `fred_breaker`, `krx_breaker`.

### RAG system (`src/rag/`)
- `chroma_store.py` — ChromaDB persistence
- `context_injection.py` — per-agent RAG config (`AGENT_RAG_CONFIG`): primary + secondary ChromaDB collection, token budget (2000 total), hybrid BM25+dense retriever
- Collections: `market_reports`, `analyst_reports`, `news_articles`, `strategy_outcomes`, `earnings_data`
- Injected into system prompt via `inject_context_into_prompt()`

### MCP Servers (`src/mcp_servers/`)
Three FastMCP servers; agents call tool functions directly (not via MCP protocol in pipeline):
- `krx_market/server.py` — pykrx: stock price, market cap
- `us_market/server.py` — US market data, VIX
- `news_economy/server.py` — exchange rate, economic news

### Feedback loop (`src/data/`)
SQLite at `data/mentions.db` — three tables:
- `prediction_log` — every agent's daily BUY/SELL/HOLD + price
- `agent_weights` — EMA accuracy weights per agent per regime
- `regime_history` — daily regime log for dynamic α

`feedback_evaluator.py` runs D+1: fetches actual price, scores prediction, updates EMA weight.  
Dynamic α: Volatile regime or regime transition within 5 days → α=0.5; stable → base_alpha (Bull=0.1, Bear=0.3, Sideways=0.2).  
Warm-up: 10 samples per agent before weights are passed to Chief Strategist.

### Signal reconciliation (`src/graph/signal_reconciliation.py`)
After Chief Strategist: at most 5 BUY signals/day, at most 2 per sector. Registry persisted to `data/signals/signals_YYYY-MM-DD.json`.

### Universe builder (`src/universe/universe_builder.py`)
KOSPI top-100 + KOSDAQ top-20 → 2-stage filter → deduplicated ticker universe.  
Config: `src/config/universe_config.json`.  
Run standalone: `python -m src.universe.universe_builder`

### Security (`src/utils/security.py`)
- `setup_secure_logging()` — masks API keys in all log output
- `validate_ticker()` — 6-digit numeric check + SQL injection guard
- `validate_report()` — required sections check before Notion publish




# CLAUDE.md

This file provides guidance to Claude Code (claude.com/code) when working with code in this repository.

---

## 프로젝트 개요

**AI Agent 협업 기반 데일리 투자 리포트 시스템 (v5.4 / 20주차)**

8명의 AI 애널리스트가 매일 시장을 분석하고, Bull/Bear 토론을 거쳐 종합 전략을 도출한 후 Notion에 자동 발행하는 시스템. 다음 날 실제 결과와 비교하여 예측 정확도를 자체 평가하고, 피드백으로 에이전트 가중치를 자동 조정한다.

- **대상 투자자**: 중단기 매매자 (7일~1개월 포지션)
- **개발 방법론**: Walking Skeleton — 전체 파이프라인의 얇은 흐름 먼저 완성 후 단계적으로 컴포넌트 세부화
- **현재 상태**: 20주차 완료 (233 passed, 0 failed). 배포 준비 완료.

---

## 7-Layer 아키텍처

```
L0 Infrastructure       : Pydantic, .env, (배포 직전 Docker/Redis 추가 예정)
L1 Data Ingestion       : 3개 MCP 서버 (KRX / News & Economy / US Market)
                          MCP 도구 20+ 종, Universe Builder, APScheduler
L2 Knowledge & Memory   : ChromaDB 6개 컬렉션 + BM25 하이브리드 RAG (Kiwi 형태소 분석)
                          SQLite: daily_mention_stats, prediction_log, agent_weights,
                                 regime_history, positions, mentions
L3 Agent Ensemble       : 8개 전문가 에이전트 + Debate + Quality Gate
L4 Orchestration        : LangGraph StateGraph, Chief Strategist, 레짐 탐지,
                          포지션 추적 노드, mention_tracker 노드
L5 Report & Publishing  : Report Formatter v4.0 (5섹션 구조), Notion v4.0 블록 빌더
L6 Monitoring           : LangSmith, 일일/주간 피드백 루프, 4계층 테스트
```

---

## 8개 에이전트

| 에이전트 | 역할 | 모델 |
|---------|------|------|
| macro_economist | 거시경제 (금리/환율/원자재/DXY) | gpt-4o-mini |
| kr_market_specialist | 한국 시장 (수급/대주주매매) | gpt-4o-mini |
| us_market_specialist | 미국 시장 (S&P500/VIX/Treasury) | gpt-4o-mini |
| quant_analyst | 정량 분석 (PER/PBR/모멘텀) | gpt-4o-mini |
| technical_analyst | 기술적 분석 (MA/RSI/MACD/볼린저/일목균형표) | gpt-4o-mini |
| sentiment_analyst | 뉴스 감성 (3-class 분류) | gpt-4o-mini |
| fundamental_analyst | 펀더멘털 (실적/컨센서스) | gpt-4o-mini |
| **chief_strategist** | 8개 에이전트 의견 종합 → 최종 전략 | claude-opus-4-6 |
| debate (Bull/Bear) | 토론 메커니즘 | claude-sonnet-4-6 |

---

## 파이프라인 흐름 (v2.8)

```
data_ingest (30s)
    ↓
regime_detector (30s, yfinance ^KS11 + ^VIX)
    ↓
parallel_analysis (180s, 7개 에이전트 병렬, Semaphore 3)
    ↓
quality_gate (30s, confidence ≥ 0.6 필터)
    ↓
debate_node (90s, claude-sonnet-4-6)
    ↓
chief_strategist_node (120s, claude-opus-4-6 + tool_use)
    ↓
report_formatter (30s, v4.0 — src/graph/report_formatter.py, 5섹션 구조)
    ↓
notion_publish (30s, validate_report 검증 후 발행, v4.0 Notion 블록)
    ↓
log_predictions_node (30s, prediction_log + regime_history)
```

모든 노드는 `node_with_timeout()` 래퍼로 timeout 적용.

---

## ⚠️ 절대 지킬 규칙

### [DEP-01] langchain-anthropic 설치 금지

```
설치 시 langchain-core 1.3.3 → 0.3.86 자동 다운그레이드 발생
→ 시스템 전체 동작 깨짐
```

**Anthropic 모델은 `anthropic` SDK 직접 사용 (AsyncAnthropic)**
- `src/agents/base_agent.py`의 `ResilientChain`이 이를 처리
- `chief_strategist`, `debate`도 동일 패턴

### [DEP-02] langchain-core 1.3.3 고정

requirements-freeze.txt에 1.3.3으로 고정. pip resolver가 충돌을 보고하므로
새 환경 구축 시 반드시 `pip install --no-deps -r requirements-freeze.txt` 사용.

### [DEP-03] pybreaker는 async 함수에 `.call_async()` 사용

`pybreaker.call()`은 동기 함수 전용. async 함수에서는 반드시 `.call_async()` 호출.
잘못 쓰면 Circuit Breaker가 OPEN으로 전환되지 않는 버그 발생.

### [SEC-01] API 키 로그 마스킹

`src/utils/security.py`의 `setup_secure_logging()`이 진입점에서 호출됨.
OpenAI/Anthropic/Notion 키가 로그에 노출되지 않도록 자동 마스킹.

### [SEC-02] ticker 입력 검증

`run_pipeline()`에서 `validate_ticker()` 호출. 6자리 숫자 + 화이트리스트 검증.
SQL Injection 차단.

### [SEC-03] 리포트 발행 전 검증

`notion_publish` 노드에서 `validate_report()` 호출.
None 포함/빈 리포트/필수 섹션 누락 시 발행 차단.

---

## 환경 설정

### Python
- **Python 3.11.9** (정확한 버전)
- 가상환경: `.venv/` (영문 경로 필수: `C:\projects\investment-report`)

### 주요 라이브러리
```
fastmcp 3.2.4, openai 1.75.0, langchain 0.3.25, langgraph 0.4.1
chromadb 1.5.9, langchain-chroma 1.1.0, langchain-core 1.3.3 (고정)
pykrx 1.2.7, yfinance 1.3.0, anthropic 0.50.0
tenacity 9.1.4, pybreaker 1.4.1
kiwipiepy 0.23.1 (한글 형태소 분석, BM25 검색용)
notion-client 2.3.0, aiohttp 3.11.18
pytest 8.3.5, pytest-asyncio 0.26.0
```

### .env 필수 키
```
OPENAI_API_KEY            # 8개 에이전트 + nano 스코어링
ANTHROPIC_API_KEY         # chief_strategist + debate
FRED_API_KEY              # 거시경제 데이터
BOK_ECOS_API_KEY          # 한국 기준금리
NAVER_CLIENT_ID, NAVER_CLIENT_SECRET   # 뉴스/감성
KRX_OpenAPI, KRX_ID, KRX_PW            # 한국 시장 데이터
DART_API_KEY              # 공시 (주주변동/CB·BW/실적)
NOTION_API_KEY, NOTION_DATABASE_ID     # 리포트 발행
LANGCHAIN_API_KEY (선택)  # LangSmith Observability
```

---

## 디렉토리 구조

```
src/
├── agents/                  # 8개 에이전트 + base_agent (ResilientChain)
│   ├── base_agent.py        # langchain_anthropic 제거, anthropic SDK 직접 사용
│   ├── chief_strategist.py  # claude-opus-4-6 + tool_use + weight_context
│   ├── debate.py            # claude-sonnet-4-6 Bull/Bear 토론
│   └── ...
├── data/
│   ├── mention_tracker.py   # NAVER 뉴스 크롤러 (Retry + CB + 캐시 Fallback)
│   ├── prediction_logger.py # prediction_log + agent_weights + regime_history
│   ├── feedback_evaluator.py # D+1 채점 + 동적 EMA
│   ├── position_tracker.py  # 포지션 CRUD + CLI
│   └── ...
├── graph/
│   ├── pipeline.py          # v2.8 (보안 + Timeout + 리포트 검증)
│   ├── report_formatter.py  # v4.0 (5섹션 구조 — 2025-05 신규 분리)
│   ├── notion_publisher.py  # v4.0 (build_v4_blocks, toggle/callout)
│   ├── signal_reconciliation.py
│   ├── quality_gate.py
│   └── regime_detector.py
├── mcp_servers/
│   ├── krx_market/server.py        # 14개 도구 (가격/공시/실적/CB·BW/52주/실적캘린더)
│   ├── news_economy/server.py      # 10개 도구 (뉴스/환율/금리/DXY/금통위/입법예고/토론방/CLI)
│   └── us_market/server.py         # 8개 도구 (US 주식/지수/VIX/Treasury/원자재/FedWatch/중국)
├── rag/
│   ├── chroma_store.py
│   ├── hybrid_retriever.py  # Kiwi → smart_tokenize → korean_tokenize 폴백
│   └── context_injection.py
├── schemas/
│   ├── graph_state.py
│   └── agent_output.py      # AnalysisReport Pydantic 스키마
├── universe/
│   ├── universe_builder.py
│   └── filters.py
└── utils/
    ├── resilience.py        # Retry + CircuitBreaker + Timeout + Fallback
    └── security.py          # 키 마스킹 + ticker/report 검증

tests/                       # 233 passed, 0 failed (20주차 기준)
├── test_pipeline.py         # 파이프라인 통합 (ainvoke 사용)
├── test_report_formatter.py # report_formatter v4.0 (36 tests)
├── test_notion_publisher.py # notion_publisher v4.0 (37 tests)
├── test_rag.py              # Kiwi 토크나이저 + 하이브리드 검색
└── test_*.py                # 에이전트별 + MCP별

data/mentions.db (SQLite — 모든 테이블 단일 파일)
data/chroma_db/             # ChromaDB 6개 컬렉션
data/reports/               # 일일 리포트 markdown 백업
```

---

## 자주 쓰는 명령어 (PowerShell)

```powershell
# 파이프라인 전체 실행
.\.venv\Scripts\python -m src.graph.pipeline

# 전체 테스트
.\.venv\Scripts\python -m pytest tests/ -v

# 특정 테스트만
.\.venv\Scripts\python -m pytest tests\test_pipeline.py -v

# 빠른 요약
.\.venv\Scripts\python -m pytest tests/ --tb=no -q

# 피드백 시스템 상태 확인
.\.venv\Scripts\python -m src.data.prediction_logger

# D+1 채점 실행 (장 마감 후)
.\.venv\Scripts\python -m src.data.feedback_evaluator

# 포지션 현황 조회
.\.venv\Scripts\python -m src.data.position_tracker list

# Circuit Breaker 상태
.\.venv\Scripts\python -c "from src.utils.resilience import get_breaker_status; import json; print(json.dumps(get_breaker_status(), indent=2, ensure_ascii=False))"

# DB 테이블 카운트
.\.venv\Scripts\python -c "import sqlite3; conn = sqlite3.connect('data/mentions.db'); conn.row_factory = sqlite3.Row; tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall(); print('테이블 목록:', [t['name'] for t in tables])"
```

---

## 코드 작성 컨벤션

### Async 패턴

**모든 노드와 에이전트는 `async def`**
- 동기 호출 필요 시 `pipeline.ainvoke()`, `agent.ainvoke()` 사용
- `pipeline.invoke()` 또는 `agent.invoke()`는 작동하지 않음

### Resilience 적용 패턴

새 외부 API 호출 추가 시:
```python
from src.utils.resilience import safe_call, get_breaker

breaker = get_breaker("service_name")

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
async def call_api(...):
    ...

# 사용
result = await safe_call(breaker, call_api, fallback_value=...)
```

### MCP 도구 추가 패턴

```python
@mcp.tool()
def new_tool(param: str) -> dict:
    """도구 설명 (LLM이 이 docstring을 보고 호출 결정)"""
    try:
        # 구현
        return {"result": ...}
    except Exception as e:
        return {"error": str(e)}  # 절대 raise 하지 말 것 (파이프라인 중단 방지)
```

### 에이전트 추가 패턴

`src/agents/`에 추가 → `parallel_analysis` 노드의 `agent_names`에 등록 →
`prediction_logger`의 가중치 테이블에 자동 등록.

---

## 알려진 이슈 (Known Issues)

| ID | 내용 | 영향 |
|----|------|------|
| ~~KNOWN-ISSUE-PIPELINE-01~~ | ~~LangSmith Timestamp 직렬화 경고~~ | **수정됨** — krx_market/server.py DatetimeIndex 키 str 변환 |
| KNOWN-ISSUE-MACRO-01 | macro_economist 간헐적 Quality Gate 탈락 (confidence 0.4) | 소프트 폴백으로 처리 중 |
| KNOWN-ISSUE-RAG-02 | strategy_outcomes 컬렉션 비어있음 | 피드백 루프 데이터 누적 후 자동 해결 |
| KNOWN-ISSUE-FEEDBACK-01 | 워밍업 기간 (10거래일 미만) | 균등 가중치(0.1429) 유지 중 |
| KNOWN-ISSUE-COMMUNITY-01 | Daum 토론방 React SPA로 크롤링 제한적 | search_naver_stock_board 권장 |

---

## 결정론(Determinism)에 대해

**같은 데이터로 다른 결과가 나올 수 있음.** 의도된 동작.

원인 3가지:
1. LLM은 완벽한 결정론 아님 (temperature=0이어도 GPU 부동소수점 차이)
2. 시간이 다르면 외부 데이터 다름 (pykrx, yfinance는 호출 시점 데이터)
3. DB 상태가 누적됨 (agent_weights, prediction_log 매일 갱신)

→ "매일 새로운 시장 정보로 판단하는 시스템"이므로 비결정성이 의도된 동작.
→ 테스트는 L4 골든 파일로 부분 대응.

---

## 19주차 작업 완료 현황

```
✅ 영문 경로 이전 + Kiwi RAG 통합
✅ v5.2/5.3/5.4 누락 기능 (DXY, FedWatch, 금통위, 입법예고, 실적캘린더,
                            볼린저밴드, 일목균형표, search_news 카테고리)
✅ 커뮤니티 데이터 소스 (네이버 토론방, 다음 토론방, OECD CLI)
✅ 리포트 양식 v3.0 (신호 요약 테이블, 정렬, 통합 리스크)
✅ Known Issues 정리 (149 passed, 0 failed)
```

## 20주차 작업 완료 현황

```
✅ BUG-01: regime_detector_node — asyncio.to_thread()로 sync yfinance I/O 분리
✅ BUG-02: base_agent.py 폴백 AnalysisReport — Pydantic 스키마 위반 필드 수정
✅ BUG-03: LangSmith Timestamp 직렬화 — krx_market DatetimeIndex 키를 str 변환
✅ 결정론 실험 A·B 완료 — experiments/results/determinism_baseline.json, 판정: 배포 가능
✅ APScheduler 스케줄러 구현 — src/scheduler.py (KST 4개 job, --test dry-run 모드)
✅ 리포트 v4.0 Stage 1 — AnalysisReport 거래 파라미터 9개 필드 확장
✅ 리포트 v4.0 Stage 2 — report_formatter.py 분리, notion_publisher v4.0 재작성
                          (toggle 접기, callout Action Now 카드, 5섹션 구조)
✅ pytest asyncio 경고 제거 — pyproject.toml asyncio_default_fixture_loop_scope 설정
✅ 배포 전 최종 코드 점검 완료 (233 passed, 0 failed)
⬜ 배포 (Docker Compose + GitHub Actions cron)
```

---

## 개발 원칙

1. **정확성 최우선**: 추측 금지, 검증 가능한 사실만 코드로 작성
2. **Walking Skeleton**: 전체 흐름 동작이 완벽한 부분 구현보다 우선
3. **실패 격리**: 한 에이전트/도구 실패가 전체 파이프라인 중단 방지
4. **Fallback 필수**: 모든 외부 API는 캐시/기본값/에러 dict로 안전 반환
5. **타입 검증**: Pydantic 스키마(AnalysisReport)로 LLM 출력 강제 구조화

---