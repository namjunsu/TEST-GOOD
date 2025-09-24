# =============================================================
# 초경량 Docker 이미지 (목표: 10GB 이하)
# =============================================================

# Stage 1: Python 패키지 빌드
FROM python:3.10-slim AS builder

RUN apt-get update && apt-get install -y \
    build-essential gcc g++ cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# requirements를 최소화된 버전으로 분리
COPY requirements_updated.txt ./
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir=/wheels \
    torch==2.1.0+cu121 --index-url https://download.pytorch.org/whl/cu121 && \
    pip wheel --no-cache-dir --wheel-dir=/wheels \
    -r requirements_updated.txt

# =============================================================
# Stage 2: 최소 실행 환경 (CUDA base만 사용)
# =============================================================
FROM nvidia/cuda:12.1.0-base-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Seoul \
    PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false \
    CUDA_MODULE_LOADING=LAZY

# 최소 런타임 패키지만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10-minimal \
    python3-pip \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-kor \
    poppler-utils \
    curl ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && ln -s /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# wheel 파일 복사 및 설치
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl && \
    rm -rf /wheels /root/.cache/pip

# 앱 파일만 복사 (최소한으로)
COPY web_interface.py perfect_rag.py ./
COPY config.py log_system.py response_formatter.py ./
COPY smart_search_enhancer.py auto_indexer.py ./
# 새로 추가된 다중 문서 검색 파일
COPY multi_doc_search.py index_builder.py ./
COPY rag_system/ ./rag_system/
COPY .streamlit/ ./.streamlit/

# 디렉토리 생성 (모델은 마운트로만)
RUN mkdir -p logs cache indexes && \
    chmod 755 /app

# 모델과 문서는 볼륨으로만 마운트
VOLUME ["/app/models", "/app/docs"]

EXPOSE 8501

# 메모리 제한 설정
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 최적화된 시작 명령
CMD ["python", "-O", "web_interface.py"]