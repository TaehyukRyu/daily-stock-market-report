# AI 주식 투자 리포트 자동 생성 시스템 v2.8

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python) ![LangGraph](https://img.shields.io/badge/LangGraph-0.4-purple) ![LangChain](https://img.shields.io/badge/LangChain-0.3-green) ![Anthropic](https://img.shields.io/badge/Anthropic-Claude_Opus/Sonnet/Haiku-orange) ![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-black) ![FastMCP](https://img.shields.io/badge/FastMCP-3.2-red) ![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-teal) ![GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-181717?logo=github)

> **단일 LLM의 편향 문제를 "역할 분담 → 토론 → 종합 → 사후 채점 학습" 구조로 해결한다.**
> 매 거래일 06:10(KST), 무인 환경에서 한국 주식 110종목을 스크리닝하고 7개 전문가 AI 에이전트가 분석·토론·종합한 투자 리포트를 Notion에 자동 발행하는 자율 파이프라인입니다.

---

## 📋 목차

1. [프로젝트 개요](#-프로젝트-개요)
2. [주요 특징](#-주요-특징)
3. [시스템 아키텍처](#-시스템-아키텍처)
4. [데이터 파이프라인](#-데이터-파이프라인)
5. [운영 결과](#-운영-결과)
6. [설치 및 실행](#-설치-및-실행)
7. [기술 스택](#-기술-스택)
8. [프로젝트 구조](#-프로젝트-구조)
9. [제한사항 및 향후 과제](#-제한사항-및-향후-과제)
10. [문의](#-문의)

---

## 🎯 프로젝트 개요

### 배경 및 필요성

단일 LLM에 투자 분석을 일임하면 그 모델의 **학습 편향과 환각**이 결과에 그대로 노출됩니다. 근거 추적이 어렵고, 잘못된 판단을 사후에 교정할 **폐루프(closed-loop) 학습 구조**도 없습니다. 개인 투자자가 매일 거시·기술·심리·펀더멘털을 모두 점검하는 것은 시간상 불가능에 가깝습니다.

본 시스템은 이를 다음과 같이 해결합니다.

| Before — Single LLM | After — 7 Agents + Debate + Feedback |
|---|---|
| 한 모델의 편향이 결과 전체에 노출 | ① **역할 분담** — 거시·시장·정량·심리·기술·펀더멘털 7 도메인 |
| 근거 추적 어려움 | ② **토론** — 경합 시 Bull vs Bear 2라운드 |
| 잘못된 판단 교정 메커니즘 부재 | ③ **종합** — `chief_strategist` 최종 판단 |
| 외부 API 장애 시 전체 중단 | ④ **폐루프 학습** — D+1 채점 → EMA 가중치 갱신 |

### 프로젝트 목표

- **무인 자동화**: 사람의 개입 없이 매 거래일 일일 투자 리포트를 자동 생성·발행
- **다중 에이전트 편향 완화**: 도메인별로 역할이 분담된 7개 전문가 에이전트 + 토론 + 종합
- **자기 개선 폐루프**: D+1 종가 채점으로 에이전트별·레짐별 EMA 가중치를 점진 학습
- **장애 복원력 내장**: Circuit Breaker / Retry / Timeout / Fallback의 다층 방어
- **저비용 운영**: 모델 역할 분담으로 LLM 비용 일평균 $0.07 수준 유지

### 프로젝트 정보

| 항목 | 내용 |
|---|---|
| 시스템 버전 | v2.8 |
| 실행 환경 | Python 3.11 / Ubuntu (CI) / Windows (개발) |
| 자동화 | GitHub Actions (cron 평일) / APScheduler (상주 모드) |
| 발행 채널 | Notion (실패 시 로컬 `.md` 파일 폴백) |
| 분석 유니버스 | 한국 주식 110종목 (`universe_config.json`, 분기 자동 갱신) |

---

## 🌟 주요 특징

### 1. 다중 LLM 역할 분담 (Multi-Model Architecture)

비용·성능·역할을 분리해 모델을 배치했습니다. 구조화 출력은 Pydantic `AnalysisReport` 스키마로 **강제**됩니다.

| 역할 | 모델 | 이유 |
|---|---|---|
| 전문가 7종 | `gpt-4o-mini` | 7병렬 호출, 비용 우선 |
| 최종 종합 (`chief_strategist`) | `claude-opus-4-6` | 추론력 우선, tool_use 강제 호출 |
| Bull/Bear 토론 (`debate`) | `claude-sonnet-4-6` | 균형 성능 |
| 뉴스 스크리닝 (`stage1c_news`) | `claude-haiku-4-5` | 30→15 종목 1회 추출, 초저비용 |

### 2. 4단계 종목 스크리닝 (Screening Pipeline)

유니버스 110종목을 4단계로 통과시켜 분석 대상 후보를 추립니다. **각 Stage는 try/except로 격리**되어 한 단계가 실패해도 전체가 중단되지 않습니다.

| Stage | 모듈 | 신호 | 점수 기여 |
|---|---|---|---|
| **1-A** 정량 | `stage1a_quant.py` | 5일 가격변화 · 거래량 · MA 돌파 · 골든크로스 | 0~2점 |
| **1-B** 언급량 | `stage1b_mention.py` | spike · buildup · 감성 가속 · 미디어-가격 괴리 | 0~5점 |
| **1-C** 뉴스 LLM | `stage1c_news.py` | claude-haiku 1회 호출 (30→15 종목) | 0~1점 |
| **2** 스코어링 | `stage2_scorer.py` | 합산 → confirmed(≥2) / optional(≥1) / excluded | 최대 8점 |

> **최소 보장**: confirmed + optional이 5개 미만이면 점수>0 종목을 상위순으로 optional에 승격합니다. mention DB가 비어 있는 초기 환경에서도 분석 대상이 0개가 되지 않도록 한 안전장치입니다.

### 3. LangGraph StateGraph 파이프라인 (9 nodes)

종목별로 순차 실행되는 9개 노드로 구성됩니다. 각 노드는 **개별 타임아웃**을 가지며 초과 시 빈 결과를 반환하고 다음 노드로 진행합니다.

```
data_ingest → regime_detector → parallel_analysis → quality_gate
   ↓                                                      ↓
log_predictions ← report_formatter ← signal_reconciliation ← chief_strategist ← debate
```

| 노드 | 타임아웃 | 역할 |
|---|---|---|
| `data_ingest` | 30s | KOSPI·VIX·환율·국채·WTI 6 소스 병렬 수집 |
| `regime_detector` | 30s | Bull / Bear / Sideways / Volatile / Neutral 분류 |
| `parallel_analysis` | 360s | 7 에이전트 병렬 (전역 Semaphore 3 / KRX 2) |
| `quality_gate` | 30s | confidence≥0.6 ∧ reasoning≥3 ∧ sources≥2 |
| `debate` | 90s | BUY-SELL 가중합 차 <1.0 경합 시 2라운드 토론 |
| `chief_strategist` | 120s | tool_use 강제 호출 + 거래 파라미터 9종 산출 |
| `signal_reconciliation` | — | BUY 신호 우선순위화 (한도 5 / 섹터 2) |
| `report_formatter` | 30s | 마크다운 7섹션 리포트 조립 |
| `log_predictions` | 30s | `prediction_log` 저장 (피드백 루프 진입점) |

### 4. 7개 전문가 에이전트 (Multi-Perspective Analysis)

모든 에이전트는 공통 스키마 `AnalysisReport`(recommendation · confidence · reasoning · data_sources · prediction_basis · risk_factors)를 출력합니다.

| 에이전트 | 분석 도메인 | 주 데이터 소스 |
|---|---|---|
| `macro_economist` | 거시경제 · 금리 · 통화정책 | FRED · BOK ECOS |
| `kr_market_specialist` | 한국 시장 · 수급 · 공시 | KRX MCP · DART |
| `us_market_specialist` | 미국 시장 · 연준 · 빅테크 | yfinance · US 지표 |
| `quant_analyst` | 모멘텀 · 목표주가 괴리율 | KRX MCP |
| `technical_analyst` | 차트 패턴 · 지지/저항 | OHLCV · TA-Lib |
| `sentiment_analyst` | 투자심리 · 역발상 | NAVER 언급량 DB |
| `fundamental_analyst` | PER/PBR/ROE · 밸류에이션 | KRX MCP · 재무 데이터 |

### 5. 하이브리드 RAG (BM25 + Vector + RRF)

한국어 형태소 기반 BM25와 벡터 검색을 **앙상블(Reciprocal Rank Fusion)** 로 결합하여 정확도와 재현율을 동시에 확보합니다.

```
query ─┬─ BM25 (rank-bm25 + Kiwi)
       └─ ChromaDB (text-embedding-3-small)
              ↓
       EnsembleRetriever (RRF) → context (TOTAL_TOKEN_BUDGET = 2,000)
```

- **컬렉션 6종**: `news_articles` · `analyst_reports` · `market_reports` · `earnings_data` · `strategy_outcomes` · `economic_indicators`
- **에이전트별 primary/secondary 컬렉션 배분** — 거시는 `market_reports`, 한국증시는 `news_articles` 등 도메인에 맞게 분리

### 6. MCP 서버 직접 구현 (FastMCP 3.2.4)

데이터 수집 계층을 **3개 MCP 서버 + 30+ tools**로 직접 구축했습니다. 실패 시 예외 대신 `{"error": ...}` 반환으로 호출자를 격리합니다.

| MCP 서버 | 제공 도구 (예시) |
|---|---|
| `krx_market` | `get_stock_price` · `get_investor_trends` · `get_analyst_reports` · `get_financials` · `get_convertible_bonds` · `get_equity_events` · `get_earnings_calendar` |
| `us_market` | `get_vix` · `get_treasury_yields` · `get_commodity_prices` |
| `news_economy` | `get_exchange_rate` |

### 7. 폐루프 피드백 학습 (Closed-Loop Feedback)

매일의 예측이 다음 날 종가로 채점되고, **레짐별 EMA 가중치**가 자동 갱신됩니다. 이 가중치는 다음 거래일 `chief_strategist` 프롬프트에 주입되어 신뢰도 높은 에이전트의 의견에 더 큰 비중이 부여됩니다.

```
D    예측 저장 → SCORED_AGENTS 7종 · evaluated=0
D+1  15:30  종가 ±1% 기준 채점 (1.0 / 0.5 / 0.0)
D+1  EMA 갱신 (동적 α · ±30% clip · MIN_WEIGHT=0.05)
D+2  weight_context 주입 → chief_strategist 입력
```

**동적 α 규칙** (`get_dynamic_alpha`):

| 조건 | α 값 | 의도 |
|---|---|---|
| Volatile 레짐 | 0.5 | 즉시 적응 |
| 최근 5거래일 내 레짐 전환 감지 | 0.5 | 빠른 전환 추종 |
| 5거래일 연속 동일 레짐 (안정) | base_alpha (Bull 0.1, Bear 0.3, Sideways 0.2, Neutral 0.1) | 노이즈 억제 |
| 워밍업 (샘플 < 10) | 가중치 미변경, 샘플만 누적 | 초기 변동 방지 |

### 8. 다층 복원력 (Resilience by Design)

외부 API의 일시 장애가 전체 파이프라인을 멈추지 않도록 **4계층 방어**가 모든 외부 호출 경계에 적용됩니다.

| 계층 | 패턴 | 도구 |
|---|---|---|
| ① 파이프라인 노드 | 노드별 asyncio 타임아웃, 실패 시 `{}` 반환 | `node_with_timeout` |
| ② 에이전트 호출 | 실패 시 `confidence=0.0` 폴백 보고서 | `ResilientChain` |
| ③ LLM API | Circuit Breaker (5회/30s) + Retry (3회) + SDK 타임아웃 | `pybreaker` · `tenacity` |
| ④ 동기 라이브러리 | ThreadPoolExecutor 타임아웃 | `pykrx` · `yfinance` |

> **설계 원칙**: *"실패는 격리하고 폴백으로 흡수하되, 신뢰할 수 없는 산출물은 `confidence=0.0`으로 표시해 하류(Quality Gate)에서 자동 제외한다."*

---

## 🏛 시스템 아키텍처

### 5계층 구조 (Layered Architecture)

```
┌─────────────────────────────────────────────────────────────────┐
│  L5  피드백 / 학습                                                │
│      prediction_logger · feedback_evaluator · position_tracker    │
├─────────────────────────────────────────────────────────────────┤
│  L4  오케스트레이션                                                │
│      scheduler · daily_runner · pipeline (LangGraph StateGraph)   │
├─────────────────────────────────────────────────────────────────┤
│  L3  에이전트 / 추론                                               │
│      base_agent · 7 전문가 · debate · chief_strategist            │
│      RAG: context_injection · hybrid_retriever · chroma_store     │
├─────────────────────────────────────────────────────────────────┤
│  L2  스크리닝 / 신호                                               │
│      screener · stage1a/1b/1c · stage2_scorer                     │
│      regime_detector · quality_gate · signal_reconciliation       │
├─────────────────────────────────────────────────────────────────┤
│  L1  데이터 / 인프라                                               │
│      MCP 서버 3종 · mention_db · ohlcv_cache · notion_publisher   │
├─────────────────────────────────────────────────────────────────┤
│  공통 횡단: resilience · security · graph_state · agent_output    │
└─────────────────────────────────────────────────────────────────┘
```

### 배포 구조 — Serverless (GitHub Actions)

코드가 GitHub에 있고, 매일 아침 GitHub Actions가 코드를 실행해 외부 데이터를 수집·분석한 뒤 결과를 Notion에 발행합니다.

- **Runner**: ubuntu-latest · 평일 06:10 KST · 최대 120분
- **Secrets**: API 키 8종 암호화 · 환경변수 주입
- **Cache**: `mentions.db` 누적 — 다음 실행에 복원
- **Artifacts**: 리포트·로그 7일 보존 · 발행 실패 시 백업

---

## 🔄 데이터 파이프라인

```
외부 소스 → 수집 (MCP + 크롤러) → SQLite 캐시 → 4단계 스크리닝 → ChromaDB (RAG) → AI 에이전트 분석
                                       ↑                                              ↓
                                       └──────────  D+1 채점 피드백  ←──── prediction_log
```

### 데이터 소스

| 소스 | 용도 |
|---|---|
| pykrx (KRX) | 종목 OHLCV · 시총 · 영업일 |
| yfinance | KOSPI(^KS11) · VIX(^VIX) · 글로벌 지수 |
| NAVER 금융 / 검색 API | 헤드라인 · PER/PBR · 종목 언급량 |
| 한경 컨센서스 | 애널리스트 리포트 · 목표주가 |
| DART OpenAPI | 지분공시 · CB/BW · 유상증자 · 실적 캘린더 |
| FRED · BOK ECOS | 거시지표 (금리 등) |

### 저장 구조

| 저장소 | 형태 | 내용 |
|---|---|---|
| `data/mentions.db` | SQLite (6 tables) | `ohlcv_cache` · `mentions` · `prediction_log` · `agent_weights` · `regime_history` · `positions` |
| `data/chroma_db/` | ChromaDB (6 collections) | RAG 지식 문서 임베딩 |
| `data/signals/signals_*.json` | JSON | 일별 신호 레지스트리 |
| `data/reports/` | Markdown | Notion 발행 실패 시 백업 |

---

## 📈 운영 결과

### LangSmith 7일 누적 모니터링

| 지표 | 값 | 해석 |
|---|---|---|
| 총 LLM 호출 | **335** | 7일 누적 |
| 오류율 | **4 %** | 초기 1일차 외부 API 장애 → Circuit Breaker 격리 후 사실상 0% |
| Latency P50 | **5.15s** | 절반의 호출이 이 시간 이내 |
| Latency P99 | **201s** | parallel_analysis + debate + chief_strategist 누적 (360s 예산 내 통제) |
| 토큰 사용량 | **3.53 M** | 7일 누적 |
| LLM 비용 | **$ 0.52** | 일평균 **$ 0.07** — 모델 역할 분담의 효과 |

### 안정성 / 자동화

- **무인 자동 실행**: cron 트리거 · 평일 KST 06:10 · 사용자 개입 없음
- **자동 발행률 KPI**: > 95% 유지 (소프트 폴백 · 시장 개관 리포트 대체 · Notion 실패 시 로컬 백업)
- **종목별 분석 예산**: 600초 (10분) 이내

### 출력 예시

| 발행 채널 | 형태 |
|---|---|
| Notion DB `Daily Stock Market Report` | `YYYYMMDD_종목_..._BUY` 형식의 페이지 |
| 통합 리포트 | 7섹션 마크다운 (요약 · 거시 · 종목별 분석 · 토론 · 최종 전략 · 거래 파라미터 · 포지션 현황) |
| 거래 파라미터 (BUY 시) | 진입가 · 손절가 · 익절가 1/2 · R:R · 포지션 비중 · 보유기간 · 진입전략 |

---

## 🚀 설치 및 실행

### 환경 요구사항

- **Python 3.11** (`asyncio.timeout` 사용)
- **TA-Lib C 라이브러리** (선행 설치 필요)
  - Ubuntu: `sudo apt-get install -y libta-lib-dev`
  - macOS: `brew install ta-lib`
- **API 키**: OpenAI · Anthropic · Notion · FRED · BOK ECOS · DART · NAVER 검색

### 1. 클론 및 가상환경

```bash
git clone <REPO_URL>
cd <REPO_NAME>

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 2. 의존성 설치

```bash
# 전체 (개발 + 테스트 포함)
pip install -r requirements.txt

# CI / 운영 전용 (테스트 및 UI 제외)
pip install -r requirements-ci.txt
```

> **참고**: `langchain==0.3.x` + `langchain-core==1.3.3` 조합은 pip 의존성 해석으로는 설치 불가하여 CI 환경에서는 `--no-deps` 옵션을 사용합니다 (`ci.yml` 참조).

### 3. 환경변수 설정

`.env` 파일을 생성하거나 GitHub Secrets에 등록합니다.

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
NOTION_TOKEN=secret_...
NOTION_DATABASE_ID=...
FRED_API_KEY=...
BOK_ECOS_API_KEY=...
DART_API_KEY=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

### 4. 실행 방법

```bash
# (A) 전체 일일 파이프라인 (스크리닝 + 종목별 분석 + 통합 발행)
python -m daily_runner

# (B) APScheduler 상주 모드 (06:00 크롤 / 06:10 분석 / 15:30 채점)
python -m scheduler

# (C) 단일 종목 디버그 실행
python -m pipeline       # 또는 코드 내 run_pipeline("005930")

# (D) 분기 유니버스 재생성
python -m universe_builder

# (E) 포지션 수동 관리 (CLI)
python -m position_tracker add 005930 67000 100
python -m position_tracker close 005930 71000
python -m position_tracker list

# (F) D+1 피드백 채점 (수동 트리거)
python -m feedback_evaluator
```

### 5. GitHub Actions 자동 실행

`ci.yml`이 평일 cron으로 자동 트리거됩니다. Secrets에 위 환경변수를 등록한 뒤 push하면 즉시 동작합니다.

---

## 🛠 기술 스택

### Core

| 분류 | 기술 | 용도 |
|---|---|---|
| 언어 / 런타임 | **Python 3.11** | `asyncio.timeout` 사용 |
| 워크플로우 | **LangGraph 0.4.1** (`StateGraph`) | 9개 노드 선언적 파이프라인 |
| LLM 프레임워크 | **LangChain 0.3.x** · **Anthropic SDK** · **OpenAI SDK** | 구조화 출력 강제 (`with_structured_output`) |
| 검증 / 스키마 | **Pydantic 2.13** | `GraphState` · `AnalysisReport` |

### LLM

| 모델 | 사용처 |
|---|---|
| `gpt-4o-mini` | 7개 전문가 에이전트 |
| `claude-opus-4-6` | chief_strategist (최종 종합) |
| `claude-sonnet-4-6` | debate (Bull/Bear 토론) |
| `claude-haiku-4-5` | stage1c_news (뉴스 스크리닝) |

### Data / RAG

| 기술 | 용도 |
|---|---|
| **FastMCP 3.2.4** | 데이터 수집 MCP 서버 (3개 · 30+ tools) |
| **ChromaDB 1.5.9** | 벡터 검색 (6 컬렉션) |
| **rank-bm25** | 키워드 검색 |
| **kiwipiepy 0.23** | 한국어 형태소 분석 |
| **tiktoken** | 토큰 카운팅 (예산 2,000) |
| **pykrx · yfinance** | 시장 데이터 |
| **TA-Lib · ta** | 기술적 지표 |

### Infra / Ops

| 기술 | 용도 |
|---|---|
| **APScheduler 3.11** | 평일 cron 스케줄링 |
| **GitHub Actions** | 서버리스 무인 실행 |
| **SQLite** | `mentions.db` (6 tables) |
| **pybreaker** | Circuit Breaker |
| **tenacity** | Exponential Retry |
| **notion-client 2.3** | 리포트 발행 |
| **LangSmith** | LLM 호출 모니터링 / 비용 추적 |

---

## 📁 프로젝트 구조

```
ai-investment-report/
│
├── docs/                                # 📚 설계 문서 및 발표 자료
│   ├── 01_요구분석명세서.md             # SRS (47 모듈 역공학 분석)
│   ├── 02_기본설계서.md                 # 5계층 아키텍처 · 모듈 카탈로그
│   ├── 03_상세설계서.md                 # 알고리즘 · 결함 분석 · 수정안
│   ├── 01_AI_Agent_Workflow.pdf         # 전체 워크플로우 다이어그램
│   ├── 02_Data_Pipeline.pdf             # 수집~RAG 주입 흐름
│   ├── 03_System_Architecture.pdf       # 컴포넌트 구성 · 통신
│   └── AI_주식_투자_리포트_자동_생성_시스템.pdf   # 프로젝트 소개 발표 자료
│
├── src/
│   ├── graph/                           # L4 오케스트레이션
│   │   ├── pipeline.py                  # LangGraph StateGraph 정의 · 실행
│   │   ├── graph_state.py               # 공유 상태 (Pydantic)
│   │   ├── quality_gate.py              # 보고서 품질 필터
│   │   └── signal_reconciliation.py     # BUY 신호 우선순위화
│   │
│   ├── agents/                          # L3 에이전트
│   │   ├── base_agent.py                # 팩토리 + ResilientChain
│   │   ├── macro_economist.py           # 거시경제 전문가
│   │   ├── kr_market_specialist.py      # 한국증시 전문가
│   │   ├── us_market_specialist.py      # 미국증시 전문가
│   │   ├── quant_analyst.py             # 퀀트 분석가
│   │   ├── technical_analyst.py         # 기술적 분석가
│   │   ├── sentiment_analyst.py         # 투자심리 분석가
│   │   ├── fundamental_analyst.py       # 펀더멘털 분석가
│   │   ├── debate.py                    # Bull vs Bear 토론
│   │   └── chief_strategist.py          # 최종 전략 종합
│   │
│   ├── rag/                             # L3 RAG
│   │   ├── context_injection.py         # 컨텍스트 조립·주입 (토큰 예산 2000)
│   │   ├── hybrid_retriever.py          # BM25 + Vector 앙상블 (RRF)
│   │   └── chroma_store.py              # ChromaDB 컬렉션 접근
│   │
│   ├── screening/                       # L2 스크리닝
│   │   ├── screener.py                  # 4단계 통합 진입점
│   │   ├── stage1a_quant.py             # 정량 모멘텀 4신호
│   │   ├── stage1b_mention.py           # 언급량 이상 탐지
│   │   ├── stage1c_news.py              # 뉴스 LLM 스크린
│   │   ├── stage2_scorer.py             # 점수 합산 · 분류
│   │   └── regime_detector.py           # 시장 레짐 분류
│   │
│   ├── schemas/                         # 공통 스키마
│   │   └── agent_output.py              # AnalysisReport (Pydantic)
│   │
│   ├── mcp_servers/                     # L1 MCP 서버 (FastMCP)
│   │   ├── krx_market/server.py         # 한국 시장 데이터 (8 tools)
│   │   ├── us_market/server.py          # 미국 시장 데이터
│   │   └── news_economy/server.py       # 환율·거시 뉴스
│   │
│   ├── data/                            # L1 데이터 인프라
│   │   ├── universe_builder.py          # 종목 유니버스 구성·로드
│   │   ├── universe_config.json         # 110종목 설정
│   │   ├── mention_db.py                # 언급량 SQLite I/O
│   │   ├── mention_tracker.py           # NAVER 언급량 크롤러
│   │   ├── daily_mention_stats.py       # 일별 집계
│   │   ├── sentiment_classifier.py      # 헤드라인 감성 분류
│   │   ├── ohlcv_cache.py               # OHLCV 캐시 SQLite I/O
│   │   ├── prediction_logger.py         # L5 예측 원장 + 가중치 + 레짐 이력
│   │   ├── feedback_evaluator.py        # L5 D+1 채점 + 동적 EMA
│   │   └── position_tracker.py          # L5 포지션 추적
│   │
│   ├── reporting/                       # L1 발행
│   │   ├── report_formatter.py          # 마크다운 리포트 조립
│   │   └── notion_publisher.py          # Notion 발행 (실패 시 로컬 폴백)
│   │
│   ├── core/                            # 공통 횡단
│   │   ├── resilience.py                # Circuit Breaker + Retry + Timeout
│   │   ├── security.py                  # API 키 마스킹 + 입력 검증
│   │   └── filters.py                   # 종목 필터 (작전주/바이오 등)
│   │
│   ├── daily_runner.py                  # L4 일일 총괄 (Step 0→1→2→3)
│   └── scheduler.py                     # L4 APScheduler 진입점
│
├── data/                                # (런타임 생성)
│   ├── mentions.db                      # SQLite — 6 tables
│   ├── chroma_db/                       # ChromaDB — 6 collections
│   ├── signals/                         # 일별 신호 JSON
│   └── reports/                         # 발행 실패 시 백업
│
├── logs/
│   └── scheduler.log                    # 로테이팅 로그
│
├── requirements.txt                     # 전체 의존성
├── requirements-ci.txt                  # CI / 운영 전용
├── requirements-freeze.txt              # 잠금 버전
├── ci.yml                               # GitHub Actions 워크플로우
└── README.md
```

---

## 📌 제한사항 및 향후 과제

### 현재 제한사항

#### 1. 실제 매매 미지원 (설계상 명시)
- 시스템은 **분석·추적만** 담당하며, 실제 증권사 주문 API 연동은 없음
- 진입 / 청산은 사용자가 직접 수행, 시스템은 `positions` 테이블로 기록만 유지

#### 2. 코드 분석으로 식별된 결함 (`03_상세설계서.md` §6 참조)

| ID | 심각도 | 내용 |
|---|---|---|
| **DEF-1** | 🔴 높음 | `AnalysisReport`에 `ticker` 필드 부재 → `prediction_logger`가 빈 ticker 저장 → **피드백 채점이 사실상 수행되지 않을 수 있음** |
| DEF-2 | 🟠 중간 | `GraphState.error_log`에 `operator.add` 리듀서 부재 → 노드 간 에러 누적 미동작 |
| DEF-3 | 🟡 낮음 | `set_ticker_whitelist` import만 되고 호출 안 됨 → 화이트리스트 기능 비활성 |
| DEF-6 | 🟡 낮음 | `SECTOR_MAP`에서 `271560`(오리온)이 "자동차"로 잘못 분류 |
| DEF-8 | 🟡 낮음 | `scheduler.py` (단일 종목 고정)와 `daily_runner.py` (전체 스크리닝) 이중 진입점 공존 |

#### 3. 운영상 제약

- **단일 종목 순차 처리**: 종목별 600초 예산 × N개 → 종목 수 증가 시 GitHub Actions 120분 한도 압박
- **공유 Circuit Breaker**: `openai_breaker`가 7개 에이전트에 공유 → 한 에이전트의 연속 실패가 전체 차단 유발 가능
- **NAVER API 한도**: 일 25,000건 제한 (`mention_tracker`)
- **임계값 1% 채점**: BUY/SELL의 0.5(부분정답)가 거의 발생하지 않아 사실상 이분 채점에 가까움

### 향후 개선 방향

#### 1. 피드백 루프 신뢰성 확보 (최우선)
- **DEF-1 수정**: `AnalysisReport`에 `ticker` 필드 추가 + `prediction_log`에 분석 시점 `price_at_pred` 즉시 저장
- 채점 임계값(현 1%) 튜닝 검토

#### 2. 병렬화 / 확장성
- 종목별 분석 병렬화 (현재 순차 처리)
- 에이전트별 Circuit Breaker 분리
- `parallel_analysis` 타임아웃 420s 또는 Semaphore 4로 상향 검토

#### 3. 데이터 품질
- `universe_config.json`에 `sector` 필드 동적 로드 (SECTOR_MAP 오류 해소)
- 거래일 판단 유틸 일원화 (`server.py` vs `stage1a_quant` 불일치 해소)

#### 4. 운영 일관성
- `scheduler.py`가 `daily_runner.run_daily()`를 호출하도록 통일 (이중 진입점 정리)
- `signals` JSON 레지스트리에 파일 락 추가 (병렬화 대비)

---

## 📮 문의

| 항목 | 내용 |
|---|---|
| 📧 Email | `<your-email@example.com>` |
| 🐙 GitHub | `https://github.com/<username>/<repo>` |

---
