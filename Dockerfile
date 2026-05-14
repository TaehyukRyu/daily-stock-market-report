# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ── 환경 변수 ───────────────────────────────────────────────────────────────
ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ── 시스템 패키지 ────────────────────────────────────────────────────────────
# build-essential : kiwipiepy, aiohttp 등 C 확장 컴파일
# wget            : TA-Lib C 라이브러리 소스 다운로드
# curl            : healthcheck, chromadb 연결 확인
# libgomp1        : OpenMP (TA-Lib 런타임 요구)
# libssl-dev      : cryptography, openssl 바인딩
# libffi-dev      : cffi, cryptography 빌드
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    libgomp1 \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ── TA-Lib C 라이브러리 (0.4.0) ─────────────────────────────────────────────
# Windows에서는 .whl 사용. Linux Docker에서는 소스 컴파일 필요.
# Python 래퍼 TA-Lib==0.4.32 는 이 C 라이브러리를 요구함.
RUN wget -q http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib \
    && ./configure --prefix=/usr \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && cd .. \
    && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# ── 의존성 설치 ─────────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements-freeze.txt .

# [DEP-02] requirements-freeze.txt 전처리 후 pip install --no-deps
#
# 전처리 내용:
#   1. UTF-16 LE (Windows pip freeze 기본 인코딩) → UTF-8 변환
#   2. Windows 전용 패키지 제거:
#      - TA-Lib @ file:///C:/...  → Linux에서 로컬 경로 없음, 별도 설치
#      - pywin32                  → Windows COM/win32 API 바인딩
#      - pywin32-ctypes           → Windows 전용
#
# langchain-anthropic는 freeze에 포함돼 있으나 --no-deps 이므로
# langchain-core 다운그레이드 없이 설치됨 (DEP-01 안전).
RUN python3 -c "\
import codecs; \
lines = codecs.open('requirements-freeze.txt', 'r', 'utf-16').read().splitlines(); \
skip = ('ta-lib @ ', 'pywin32==', 'pywin32-ctypes=='); \
filtered = [l for l in lines if l.strip() and not any(l.lower().startswith(p) for p in skip)]; \
open('/tmp/req.txt', 'w', encoding='utf-8').write('\n'.join(filtered))" \
    && pip install --no-deps -r /tmp/req.txt \
    && rm /tmp/req.txt

# TA-Lib Python 래퍼 — C 라이브러리 설치 완료 후 별도 설치
RUN pip install --no-deps TA-Lib==0.4.32

# ── 소스 복사 ───────────────────────────────────────────────────────────────
# .dockerignore에서 .env / data / logs / .venv 제외됨
COPY src/ src/

# ── 런타임 디렉토리 사전 생성 ────────────────────────────────────────────────
# 볼륨 마운트로 덮어쓰이지만, 마운트 없이 단독 실행 시 경로 보장
RUN mkdir -p data/reports data/signals logs

CMD ["python", "-m", "src.scheduler"]
