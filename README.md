<div align="center">

# Daily-Stock-Market-Report

**8명의 AI 애널리스트가 매일 시장을 토론하는 자율 운영 멀티 에이전트 시스템**

*LangGraph · MCP · ChromaDB · Anthropic · OpenAI · Docker · GitHub Actions*

[![Tests](https://img.shields.io/badge/tests-233%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11-blue)]()
[![License](https://img.shields.io/badge/license-portfolio-lightgrey)]()
[![Status](https://img.shields.io/badge/status-deployment%20ready-success)]()

</div>

---

## TL;DR

> 매일 새벽, 8명의 전문가 페르소나를 가진 LLM 에이전트가 30+ 개의 데이터 소스를 분석하고, Bull/Bear로 갈라져 토론하며, 종합 전략가가 거래 파라미터까지 산출해 Notion에 발행한다. 모두 사람 개입 없이.

이 프로젝트는 **LLM을 단일 호출이 아닌 협업 시스템으로 설계**했을 때 무엇이 달라지는지를 탐구한 결과물이다.

- 단일 GPT 호출 → 8개 전문가 협업 + 토론 + 종합
- 정적 프롬프트 → 시장 레짐 동적 적응 (Bull/Bear/Sideways/Volatile)
- 일회성 응답 → D+1 채점 → EMA 가중치 자동 조정
- 수동 보고서 → MCP 도구 호출 → 자동 발행 파이프라인

---

## 시스템 아키텍처

### 7-Layer 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│  L6  Monitoring          LangSmith Tracing │ Daily/Weekly Feedback Loop │
├─────────────────────────────────────────────────────────────────────────┤
│  L5  Report & Publishing       Markdown v4.0 → Notion API (Toggle/Card) │
├─────────────────────────────────────────────────────────────────────────┤
│  L4  Orchestration          LangGraph StateGraph │ Chief Strategist     │
│                             Regime Detector │ Position Tracker          │
├─────────────────────────────────────────────────────────────────────────┤
│  L3  Agent Ensemble        8 Specialist Agents + Bull/Bear Debate       │
│                            Quality Gate (confidence ≥ 0.6)              │
├─────────────────────────────────────────────────────────────────────────┤
│  L2  Knowledge & Memory     ChromaDB (6 collections) + BM25 Hybrid RAG  │
│                             Kiwi Korean Tokenizer │ SQLite (5 tables)   │
├─────────────────────────────────────────────────────────────────────────┤
│  L1  Data Ingestion          3× MCP Servers (KRX │ News │ US Market)    │
│                              30+ Tools │ Universe Builder │ APScheduler │
├─────────────────────────────────────────────────────────────────────────┤
│  L0  Infrastructure       Pydantic │ Docker Compose │ GitHub Actions    │
│                           Circuit Breaker │ Retry │ Timeout │ Fallback  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 데이터 흐름

```
                ┌──────────────────────────────────────┐
                │   3× MCP Servers (FastMCP)           │
                │   ─────────────────────              │
                │   • KRX Market    (14 tools)         │
                │   • News & Macro  (10 tools)         │
                │   • US Market     ( 8 tools)         │
                └─────────────────┬────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Regime Detector             │
                  │   (Bull/Bear/Sideways/Vol.)   │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
        ┌────────────────────────────────────────────────────┐
        │   Parallel Analysis (asyncio Semaphore: 3)         │
        │   ───────────────────────────────────────          │
        │   ① Macro Economist        ② KR Market Specialist  │
        │   ③ US Market Specialist   ④ Quant Analyst         │
        │   ⑤ Technical Analyst      ⑥ Fundamental Analyst   │
        │   ⑦ Sentiment Analyst                              │
        │                                                    │
        │   Each: gpt-4o-mini + Hybrid RAG (BM25 + Dense)    │
        └─────────────────────────┬──────────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Quality Gate                │
                  │   confidence ≥ 0.6            │
                  │   reasoning ≥ 3 steps         │
                  │   data_sources ≥ 2            │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Bull vs Bear Debate         │
                  │   (claude-sonnet-4-6)         │
                  │   triggered when consensus    │
                  │   is split                    │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Chief Strategist            │
                  │   (claude-opus-4-6 + tool_use)│
                  │   • EMA-weighted synthesis    │
                  │   • Trade params (entry/SL/TP)│
                  │   • R:R, position size, ...   │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Report Formatter v4.0       │
                  │   (Action Now Card, Toggles)  │
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Notion Publishing           │
                  │   (Local fallback if API fail)│
                  └───────────────┬───────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   D+1 Feedback Loop           │
                  │   • Score predictions         │
                  │   • Update EMA weights        │
                  │   • Adjust α by regime        │
                  └───────────────────────────────┘
```

---

## 핵심 기술 의사결정

### 1. 왜 단일 호출이 아닌 8 에이전트 + Debate인가?

**문제:** 단일 LLM 호출은 *"어떤 관점으로 분석했는가"*를 추적할 수 없다. 거시·기술·펀더멘털이 한 응답에 뒤섞이면 어디서 틀렸는지도 알 수 없다.

**선택:** 각 에이전트에게 명확한 *역할 / 시스템 프롬프트 / 데이터 소스 / 출력 스키마*를 부여하고, 결과를 정량 비교한다.
- **수직 분리:** 7개 전문가는 동일한 `AnalysisReport` 스키마를 사용해 결과를 직접 비교 가능
- **수평 검증:** Bull/Bear Debate는 합의가 갈릴 때만 트리거 — 컨센서스를 강화하지 않고 *반대 의견*을 강제 노출
- **메타 종합:** Chief Strategist가 모든 의견 + 가중치 + 토론 요약을 받아 최종 결정

**효과:** 각 에이전트의 신뢰도(confidence)가 D+1 채점으로 EMA 업데이트되어, 시간이 지날수록 *맞는 에이전트의 의견에 가중치가 더 실리는* 자기 교정 시스템이 된다.

### 2. 왜 MCP(Model Context Protocol)인가?

**문제:** LangChain `Tool` 데코레이터는 LLM 종속적이다. 도구를 추가하면 모든 에이전트의 시스템 프롬프트를 다시 짜야 한다.

**선택:** Anthropic 표준 MCP를 채택해 *도구 정의를 LLM과 분리*했다.
- 30+ 개의 도구가 3개 FastMCP 서버로 분리됨 (KRX / News & Macro / US Market)
- 각 도구는 독립적으로 테스트 가능하고, LLM 교체에 영향받지 않음
- 도구의 docstring이 곧 LLM 호출 매뉴얼 (별도 프롬프트 엔지니어링 불필요)

### 3. LLM 비용 최적화 — 3-Tier 전략

| 계층 | 모델 | 용도 | 호출 빈도 |
|------|------|------|----------|
| **Heavy** | claude-opus-4-6 | Chief Strategist (종합 + 거래 파라미터) | 1회/일 |
| **Mid** | claude-sonnet-4-6 | Bull vs Bear Debate | 0~1회/일 |
| **Light** | gpt-4o-mini | 7개 전문가 분석, RAG 스코어링 | 7~10회/일 |

**원칙:** 가장 무거운 추론(종합·전략 도출)에만 Opus를 쓰고, 정형화 가능한 분석은 mini로 한다. **하루 평균 비용을 일정 수준 이하로 유지**하면서도 최종 단계의 추론 품질은 타협하지 않는다.

### 4. 왜 ChromaDB + BM25 하이브리드 RAG인가?

**문제:** 한국어 임베딩만으로는 *고유명사 검색*(예: "삼성전자 24Q3 영업이익")이 약하다. BM25만으로는 *의미적 유사성*을 놓친다.

**선택:** 두 검색기를 결합한 하이브리드 리트리버
- **Dense (ChromaDB):** 의미적 유사성 — "반도체 경기" → "메모리 가격 회복" 매칭
- **Sparse (BM25 + Kiwi 형태소):** 정확한 한글 키워드 매칭 — 한국어 어절을 형태소로 분리해 종목명/지표명 검색 정확도 향상
- **에이전트별 컬렉션 분리:** 거시 에이전트는 `market_reports` + `news_articles`, 기술 분석가는 `analyst_reports` + `earnings_data` — 토큰 예산 2000개를 의미 있게 배분

### 5. Walking Skeleton 개발 방법론

**문제:** "에이전트 1개를 완벽하게 만든 후 다음으로" 식 접근은 통합 단계에서 항상 깨진다.

**선택:** 12주차 동안 매주 "전체 흐름이 끝까지 도는 얇은 버전"을 유지하면서 컴포넌트만 점진적으로 강화했다. 1주차에 이미 *MCP → 1개 에이전트 → Notion*까지 일관 동작하는 파이프라인을 만들었고, 매주 폭만 넓혔다.

---

## 해결한 기술적 도전

### 도전 1 — LLM 비결정성 vs 배포 가능성

**문제:** 같은 데이터를 입력해도 LLM은 다른 결과를 낼 수 있다. 이게 *수용 가능한 흔들림*인지 *시스템 불안정*인지 어떻게 구분하나?

**해결:**
- **실험 A** — Mock 데이터로 동일 입력을 N회 실행, LLM 노이즈만 분리 측정
- **실험 B** — 실제 데이터로 60초 간격 2회 실행, 외부 데이터 변동 + LLM 노이즈 종합 측정
- **판정 기준** — 최종 전략 일치, confidence 분산, 에이전트 신호 일치율
- **결과** — 두 실험 모두 임계 기준 통과 → `determinism_baseline.json`에 baseline 보존

### 도전 2 — 폴백 스키마가 Pydantic 검증을 깨뜨리는 버그

**문제:** Circuit Breaker가 OPEN되면 폴백 `AnalysisReport`를 반환해야 하는데, 폴백 코드가 *옛날 스키마 필드*(signal, key_factors, risk_level)를 사용하고 있어 Pydantic 검증에서 매번 예외가 발생.

**해결:** 폴백 객체도 똑같이 `min_length` 등 모든 제약을 만족하도록 재작성. `confidence=0.0`을 명시해 Quality Gate에서 자동 필터링되게 했다. *외부 API 실패가 파이프라인 전체를 멈추지 않는다*는 핵심 원칙 보존.

### 도전 3 — async 노드의 동기 I/O가 timeout을 무력화

**문제:** `regime_detector_node`가 `async def`인데 내부에서 `yfinance.download()`(동기 블로킹 호출)를 실행. `asyncio.timeout()` 컨텍스트가 동기 호출은 인터럽트할 수 없어, 30초 타임아웃이 작동하지 않음.

**해결:** `await asyncio.to_thread(_fetch_market_indicators)`로 감싸 별도 스레드에서 실행. 이제 timeout이 정상 동작하고 이벤트 루프도 막히지 않음.

### 도전 4 — LangSmith Trace가 조용히 실패

**문제:** 파이프라인은 정상 동작하는데 LangSmith 대시보드에 trace가 안 올라옴. 에러 로그도 없음.

**원인 추적:** pykrx의 `df.to_dict(orient="index")`가 `pandas.Timestamp` 객체를 dict 키로 사용 → LangSmith의 `LangChainTracer.on_chain_end`가 결과를 JSON 직렬화하려다 실패 → trace 전송 실패가 silent하게 처리됨.

**해결:** `{k.strftime("%Y-%m-%d"): v for k, v in df.to_dict(orient="index").items()}` — Timestamp 키를 ISO 문자열로 변환. 1줄 수정으로 trace 정상화.

---

## 기술 스택

**LLM Orchestration**
![LangGraph](https://img.shields.io/badge/LangGraph-0.4-1C3C3C?logo=langchain)
![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?logo=langchain)
![Anthropic](https://img.shields.io/badge/Anthropic-Opus%2FSonnet-D4A373)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991?logo=openai)

**Tooling & Protocol**
![MCP](https://img.shields.io/badge/MCP-FastMCP%203.2-FF6B6B)
![Pydantic](https://img.shields.io/badge/Pydantic-2.13-E92063?logo=pydantic)

**RAG & Storage**
![ChromaDB](https://img.shields.io/badge/ChromaDB-1.5-FFCD00)
![Kiwi](https://img.shields.io/badge/Kiwi-Korean%20NLP-blue)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite)

**Resilience**
![Tenacity](https://img.shields.io/badge/Tenacity-Retry-green)
![PyBreaker](https://img.shields.io/badge/PyBreaker-Circuit%20Breaker-red)

**Deployment**
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Cron-2088FF?logo=githubactions)
![APScheduler](https://img.shields.io/badge/APScheduler-3.11-orange)

**Observability**
![LangSmith](https://img.shields.io/badge/LangSmith-Tracing-1C3C3C)

---

## 핵심 수치

<div align="center">

| Metric | Value |
|--------|------:|
| AI Agents | **8** |
| Data Sources | **30+** |
| MCP Tools | **32** |
| ChromaDB Collections | **6** |
| SQLite Tables | **5** |
| Test Coverage | **233 passed, 0 failed** |
| Pipeline Latency | **< 5 min** end-to-end |
| Automation | **Daily 06:10 KST** weekday cron |
| Resilience Layers | **4** (Retry → CB → Timeout → Fallback) |

</div>

---

## 시스템 구조 설명

### 8명의 페르소나, 하나의 출력 스키마

모든 에이전트는 동일한 `AnalysisReport` 스키마를 반환한다. 추천(BUY/SELL/HOLD), 신뢰도(0~1), 사고 흐름 최소 3단계, 데이터 소스 최소 2개, 정량 근거, 리스크 요인. **이 강제 구조 덕분에 8개의 다른 관점을 수치로 비교할 수 있다.**

### 4계층 복원력

| Layer | Mechanism | Purpose |
|-------|-----------|---------|
| 1 | Tenacity Retry × 3 | 일시적 네트워크 오류 복구 |
| 2 | PyBreaker Circuit Breaker | 연속 실패 감지 → 30초 차단 |
| 3 | asyncio.timeout | 노드별 시간 제한 (30~180초) |
| 4 | Pydantic Fallback | confidence=0.0 더미로 Quality Gate에서 자동 제외 |

한 도구가 죽어도, 한 에이전트가 실패해도, 한 외부 API가 다운돼도 파이프라인은 *끝까지 돈다*.

### 동적 EMA 피드백 루프

D+1에 실제 가격을 가져와 어제 예측을 채점한다. 정확하면 그 에이전트의 가중치가 올라간다. 시장 레짐이 바뀌면 학습률(α)이 자동 증가해 새 환경에 빠르게 적응한다. *워밍업 10일 동안은 균등 가중치를 유지해 초기 노이즈를 차단*.

### Notion v4.0 리포트 구조

마크다운 → Notion 블록 빌더 → 5섹션 발행:
1. **Action Now** (callout) — 거래 파라미터 카드 (BUY 시)
2. **Agent Signal Summary** (table) — 8개 에이전트 신호 한눈에
3. **Market Context** (paragraph + toggle) — 레짐 + Bull/Bear 토론 요약
4. **Analysis Rationale** (toggle) — 에이전트별 상세 (접기)
5. **Appendix** (bulleted list) — 데이터 소스 + 통합 리스크 + 생성 시각

---

## 개발 여정 (12주)

```
Week 1-2   │ Walking Skeleton
           │ MCP 1개 + 에이전트 1개 + Notion 발행 — 끝까지 한 번 도는 시스템
           ▼
Week 3-4   │ Agent Ensemble
           │ 7개 전문가 페르소나 + 공통 스키마 + Quality Gate
           ▼
Week 5-6   │ Resilience
           │ ResilientChain (Retry + CB + Timeout + Fallback)
           │ 폴백이 파이프라인을 막지 않도록 설계
           ▼
Week 7-8   │ Knowledge Layer
           │ ChromaDB 6 컬렉션 + Kiwi 형태소 + BM25 하이브리드 RAG
           │ 에이전트별 컨텍스트 주입
           ▼
Week 9-10  │ Synthesis & Debate
           │ Bull vs Bear Debate (claude-sonnet)
           │ Chief Strategist (claude-opus + tool_use)
           │ EMA 가중치 피드백 루프
           ▼
Week 11    │ Report v3.0 → v4.0 + 결정론 검증 실험 + 버그 3종 수정
           ▼
Week 12    │ Deployment Ready
           │ Docker Compose + APScheduler + GitHub Actions
           │ 233 passed, 0 failed
```

---

## 디스클레이머

이 시스템은 **AI Agent 협업 아키텍처를 검증하는 엔지니어링 프로젝트**입니다.
- 실제 매매 신호나 수익률은 본 README에서 다루지 않습니다.
- 생성된 분석은 투자 자문이 아니며, 어떠한 매매 결정의 근거로도 사용되어서는 안 됩니다.
- 본 프로젝트의 가치는 *멀티 에이전트 시스템 설계 / LLM 비용 최적화 / 복원력 패턴 / 자율 운영 파이프라인*에 있습니다.

---

<div align="center">

**Built as a portfolio of AI Agent Engineering — not financial advice.**

</div>
