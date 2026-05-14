"""
src/utils/resilience.py
복원력 패턴 모음: Retry, Circuit Breaker, Timeout, Fallback

사용법:
  from src.utils.resilience import with_retry, llm_circuit_breaker, safe_call

설계 원칙:
  - 모든 LLM 호출은 with_retry 데코레이터 사용
  - 외부 MCP/API 서비스는 llm_circuit_breaker 통과
  - 에이전트 전체 실행은 60초 Timeout
  - MCP 실패 시 Fallback으로 캐시/기본값 반환
"""

import asyncio
import logging
import functools
from typing import Any, Callable, Optional, TypeVar

import pybreaker
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 재시도 대상 예외 목록
# LLM/API 에서 발생하는 일시적 오류들
# ──────────────────────────────────────────────
RETRYABLE_EXCEPTIONS = (
    Exception,  # 일단 모든 예외에 retry 적용 (필요시 좁힘)
)

# ──────────────────────────────────────────────
# Retry 데코레이터 (tenacity)
# - 최대 3회 시도
# - 지수 백오프: 1초 → 2초 → 4초 (최대 10초)
# - 재시도 전 로그 출력
# ──────────────────────────────────────────────
def with_retry(func: Callable) -> Callable:
    """
    LLM API 호출 함수에 붙이는 Retry 데코레이터.

    사용 예:
        @with_retry
        async def call_openai(self, prompt):
            ...
    """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,  # 3회 모두 실패 시 원래 예외를 그대로 raise
    )
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


# ──────────────────────────────────────────────
# Circuit Breaker (pybreaker)
# - 5회 연속 실패 시 OPEN
# - 30초 후 HALF-OPEN (1회 시험 호출)
# - 서비스별로 독립 인스턴스 생성
# ──────────────────────────────────────────────
class CircuitBreakerOpenError(Exception):
    """Circuit Breaker가 OPEN 상태일 때 발생하는 예외"""
    pass


def _make_breaker(name: str, fail_max: int = 5, reset_timeout: int = 30) -> pybreaker.CircuitBreaker:
    """
    서비스별 Circuit Breaker 인스턴스 생성.

    Args:
        name: 서비스 이름 (로그용)
        fail_max: OPEN 전환까지 허용하는 연속 실패 횟수
        reset_timeout: OPEN 유지 시간(초), 이후 HALF-OPEN 전환
    """
    return pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        name=name,
    )


# 서비스별 Circuit Breaker 인스턴스
# 각 서비스가 독립적으로 OPEN/CLOSED 상태를 가짐
openai_breaker   = _make_breaker("openai",   fail_max=5, reset_timeout=30)
anthropic_breaker = _make_breaker("anthropic", fail_max=5, reset_timeout=30)
dart_breaker     = _make_breaker("dart_mcp",  fail_max=3, reset_timeout=60)
fred_breaker     = _make_breaker("fred_mcp",  fail_max=3, reset_timeout=60)
krx_breaker      = _make_breaker("krx",       fail_max=3, reset_timeout=60)


def get_breaker_status() -> dict:
    """모든 Circuit Breaker 상태를 딕셔너리로 반환 (모니터링용)"""
    breakers = [openai_breaker, anthropic_breaker, dart_breaker, fred_breaker, krx_breaker]
    return {
        b.name: {
            "state": b.current_state,          # "closed" / "open" / "half-open"
            "fail_count": b.fail_counter,
            "is_open": b.current_state == "open",
        }
        for b in breakers
    }


# ──────────────────────────────────────────────
# Timeout 헬퍼
# asyncio.timeout (Python 3.11+) 사용
# ──────────────────────────────────────────────
async def with_timeout(coro, seconds: float, task_name: str = "task"):
    """
    코루틴에 타임아웃 적용.

    Args:
        coro: 실행할 코루틴
        seconds: 제한 시간(초)
        task_name: 로그에 표시할 이름

    Returns:
        코루틴 결과값

    Raises:
        asyncio.TimeoutError: 시간 초과 시
    """
    try:
        async with asyncio.timeout(seconds):
            return await coro
    except asyncio.TimeoutError:
        logger.error(f"[Timeout] {task_name} exceeded {seconds}s — 강제 종료")
        raise


# ──────────────────────────────────────────────
# safe_call: Retry + CircuitBreaker + Timeout + Fallback 통합
# 에이전트 호출의 최종 진입점
# ──────────────────────────────────────────────
async def safe_call(
    func: Callable,
    *args,
    breaker: Optional[pybreaker.CircuitBreaker] = None,
    timeout_seconds: float = 60.0,
    fallback_value: Any = None,
    task_name: str = "unknown",
    **kwargs,
) -> Any:
    """
    Retry + CircuitBreaker + Timeout + Fallback을 한 번에 처리.

    사용 예:
        result = await safe_call(
            agent.analyze,
            ticker="005930",
            breaker=openai_breaker,
            timeout_seconds=60,
            fallback_value={"error": "분석 실패"},
            task_name="quant_analyst",
        )

    Args:
        func: 호출할 async 함수
        *args: func에 전달할 위치 인수
        breaker: 사용할 Circuit Breaker (None이면 CB 미적용)
        timeout_seconds: 제한 시간
        fallback_value: 모든 시도 실패 시 반환할 기본값
        task_name: 로그용 이름
        **kwargs: func에 전달할 키워드 인수

    Returns:
        func의 반환값, 또는 fallback_value
    """
    @with_retry
    async def _call():
        coro = func(*args, **kwargs)
        return await with_timeout(coro, timeout_seconds, task_name)

    try:
        if breaker is not None:
            # Circuit Breaker가 OPEN이면 pybreaker.CircuitBreakerError 발생
            return await breaker.call_async(_call)
        else:
            return await _call()

    except pybreaker.CircuitBreakerError:
        logger.warning(f"[CircuitBreaker:OPEN] {task_name} — Fallback 반환")
        return fallback_value

    except asyncio.TimeoutError:
        logger.error(f"[Timeout] {task_name} — Fallback 반환")
        return fallback_value

    except Exception as e:
        logger.error(f"[Retry 소진] {task_name}: {type(e).__name__}: {e} — Fallback 반환")
        return fallback_value