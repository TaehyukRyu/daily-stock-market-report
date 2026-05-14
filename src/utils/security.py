"""
src/utils/security.py

보안 유틸리티 모음: API 키 마스킹 + 입력 검증 + 리포트 검증

사용법:
  from src.utils.security import setup_secure_logging, validate_ticker, validate_report
"""

import re
import logging
from typing import Any


# ──────────────────────────────────────────────────────────
# 1. API 키 마스킹 로그 필터
# ──────────────────────────────────────────────────────────

# 로그에서 탐지·치환할 패턴 목록
# 패턴: (정규식, 치환문자열)
_MASK_PATTERNS = [
    # sk-로 시작하는 OpenAI 키
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-****"),
    # Anthropic 키
    (re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"), "sk-ant-****"),
    # Notion 토큰 (secret_ 고정 접두사)
    (re.compile(r"(secret_)[A-Za-z0-9]{10,}"), r"\1****"),
    # NOTION 토큰
    (re.compile(r"secret_[A-Za-z0-9]{40,}"), "secret_****"),
    # 딕셔너리/JSON 안의 키 값 패턴: "api_key": "실제값"
    (re.compile(r'(?i)(api[-_]?key|token|secret|password)["\s:=]+["\']?([A-Za-z0-9\-_]{16,})["\']?'),
     r'\1=****'),
]


class _ApiKeyMaskFilter(logging.Filter):
    """
    로그 레코드를 가로채서 API 키 패턴을 ****로 치환.

    Python logging 필터 체계에 맞게 Filter를 상속.
    filter() 메서드가 False를 반환하면 해당 레코드는 출력 안 됨.
    여기서는 항상 True 반환 (출력은 허용, 내용만 수정).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._mask(str(record.msg))
        record.args = self._mask_args(record.args)
        return True

    def _mask(self, text: str) -> str:
        for pattern, replacement in _MASK_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _mask_args(self, args: Any) -> Any:
        if args is None:
            return args
        if isinstance(args, tuple):
            return tuple(self._mask(str(a)) if isinstance(a, str) else a for a in args)
        if isinstance(args, str):
            return self._mask(args)
        return args


def setup_secure_logging(level: int = logging.INFO) -> None:
    """
    루트 로거에 API 키 마스킹 필터를 설치.

    main() 또는 pipeline 진입점에서 1회 호출하면 됨.
    이후 모든 logger.info / logger.error 등에 자동 적용.

    사용법:
        from src.utils.security import setup_secure_logging
        setup_secure_logging()
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 이미 핸들러가 있으면 필터만 추가 (중복 방지)
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        root_logger.addHandler(handler)

    mask_filter = _ApiKeyMaskFilter()
    for handler in root_logger.handlers:
        # 같은 필터 중복 추가 방지
        if not any(isinstance(f, _ApiKeyMaskFilter) for f in handler.filters):
            handler.addFilter(mask_filter)


# ──────────────────────────────────────────────────────────
# 2. Ticker 입력 검증
# ──────────────────────────────────────────────────────────

# 한국 종목 코드: 6자리 숫자만 허용
# 근거: KRX 종목 코드 규격 (https://www.krx.co.kr)
_TICKER_PATTERN = re.compile(r"^\d{6}$")

# 허용 종목 화이트리스트 (universe_builder.py의 유니버스와 동기화 권장)
# None이면 패턴 검사만 수행, 리스트가 있으면 화이트리스트 검사 추가
_TICKER_WHITELIST: list[str] | None = None


class InvalidTickerError(ValueError):
    """유효하지 않은 종목 코드가 입력됐을 때 발생"""
    pass


def validate_ticker(ticker: Any) -> str:
    """
    종목 코드 유효성 검증.

    검증 순서:
      1. 타입 확인 (str이어야 함)
      2. 6자리 숫자 패턴 확인
      3. 화이트리스트 확인 (설정된 경우)

    Args:
        ticker: 검증할 종목 코드

    Returns:
        검증된 ticker 문자열

    Raises:
        InvalidTickerError: 유효하지 않은 입력

    사용 예:
        ticker = validate_ticker(user_input)  # "005930" → "005930"
        ticker = validate_ticker("005930; DROP TABLE positions;")  # → InvalidTickerError
        ticker = validate_ticker("../../etc")  # → InvalidTickerError
    """
    if not isinstance(ticker, str):
        raise InvalidTickerError(
            f"ticker는 문자열이어야 합니다. 받은 타입: {type(ticker).__name__}"
        )

    ticker = ticker.strip()

    if not _TICKER_PATTERN.match(ticker):
        raise InvalidTickerError(
            f"유효하지 않은 ticker 형식: '{ticker}' "
            f"(6자리 숫자만 허용, 예: '005930')"
        )

    if _TICKER_WHITELIST is not None and ticker not in _TICKER_WHITELIST:
        raise InvalidTickerError(
            f"허용되지 않은 ticker: '{ticker}' (유니버스에 없는 종목)"
        )

    return ticker


def set_ticker_whitelist(tickers: list[str]) -> None:
    """
    허용 종목 화이트리스트 설정.
    universe_builder.py 로드 후 호출하면 유니버스 외 종목 차단.

    사용 예:
        from src.universe.universe_builder import load_universe
        from src.utils.security import set_ticker_whitelist
        set_ticker_whitelist(load_universe())
    """
    global _TICKER_WHITELIST
    _TICKER_WHITELIST = list(tickers)


# ──────────────────────────────────────────────────────────
# 3. 리포트 발행 전 검증
# ──────────────────────────────────────────────────────────

class InvalidReportError(ValueError):
    """발행 불가능한 리포트일 때 발생"""
    pass


def validate_report(report_content: Any) -> str:
    """
    Notion 발행 전 리포트 내용 검증.

    검증 항목:
      1. 문자열인지 확인
      2. 최소 길이 (100자 이상) — 너무 짧으면 에이전트 전부 실패한 것
      3. None 포함 여부 — 포맷팅 버그로 None이 문자열에 섞이면 차단
      4. 필수 섹션 존재 여부 — '최종 판단' 또는 '에이전트별 분석' 중 하나

    Args:
        report_content: 검증할 리포트 문자열

    Returns:
        검증된 report_content

    Raises:
        InvalidReportError: 발행 불가 리포트
    """
    if not isinstance(report_content, str):
        raise InvalidReportError(
            f"report_content가 문자열이 아닙니다: {type(report_content).__name__}"
        )

    if len(report_content.strip()) < 100:
        raise InvalidReportError(
            f"리포트가 너무 짧습니다 ({len(report_content)}자). "
            f"에이전트 전체 실패 가능성 있음."
        )

    # "None"이 단독으로 줄에 있으면 포맷팅 버그 징후
    none_lines = [
        line for line in report_content.splitlines()
        if line.strip() in ("None", "null", "undefined")
    ]
    if none_lines:
        raise InvalidReportError(
            f"리포트에 None 값이 포함됨 ({len(none_lines)}줄). "
            f"포맷팅 오류 가능성 있음."
        )

    required_sections = ["최종 판단", "에이전트별 분석"]
    missing = [s for s in required_sections if s not in report_content]
    if len(missing) == len(required_sections):
        raise InvalidReportError(
            f"필수 섹션 누락: {missing}. 리포트 생성 실패 가능성 있음."
        )

    return report_content