# =============================================================
# 최적화된 Docker 이미지 (Multi-stage Build)
# 목표: 51GB → 10GB 이하
# =============================================================

# Stage 1: Builder - 의존성 설치
FROM python:3.10-slim AS builder

# 빌드 도구 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Python 의존성 설치 (wheel 파일 생성)
COPY requirements_updated.txt ./
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements_updated.txt

# =============================================================
# Stage 2: Runtime - 최소 실행 환경
# =============================================================
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# 환경 변수
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul \
    PYTHONPATH=/app:$PYTHONPATH \
    PATH=/usr/local/bin:$PATH

# 런타임 패키지만 설치 (최소한으로)
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-distutils \
    python3-pip \
    curl \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    poppler-utils \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && (ln -sf /usr/bin/python3.10 /usr/bin/python3 || true) \
    && (ln -sf /usr/bin/python3.10 /usr/bin/python || true)

# pip 업그레이드
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3

WORKDIR /app

# Builder에서 wheel 파일 복사 및 설치
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels /tmp/wheels/* && \
    rm -rf /tmp/wheels

# 필요한 파일만 복사 (크기 최적화)
COPY web_interface.py perfect_rag.py perfect_rag_v2.py ./
COPY auto_indexer.py config.py log_system.py ./
COPY response_formatter.py smart_search_enhancer.py ./
COPY rag_system/ ./rag_system/
COPY rag_core/ ./rag_core/
COPY .streamlit/ ./.streamlit/

# 디렉토리 생성
RUN mkdir -p models logs cache indexes docs

# 포트 설정
EXPOSE 8501 8502

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 시작 명령
CMD ["streamlit", "run", "web_interface.py", "--server.port=8501", "--server.address=0.0.0.0"]