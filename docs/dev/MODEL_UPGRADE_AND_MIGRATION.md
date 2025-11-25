# AI-CHAT 모델 업그레이드 및 서버 마이그레이션 가이드

> LLM 모델 교체 및 GPU 서버 마이그레이션 절차

---

## 목차

1. [현재 모델 정보](#현재-모델-정보)
2. [간단한 업그레이드 (GGUF 양자화)](#간단한-업그레이드-gguf-양자화)
3. [GPU 서버 마이그레이션](#gpu-서버-마이그레이션)
4. [주의사항 및 롤백](#주의사항-및-롤백)

---

## 현재 모델 정보

| 항목 | 값 |
|------|-----|
| **모델 파일** | `ggml-model-Q4_K_M.gguf` |
| **양자화 수준** | 4-bit (경량) |
| **메모리 사용** | ~4GB RAM |
| **추론 속도** | ~5 tokens/s (CPU) |
| **설정 위치** | `.env` 파일의 `MODEL_PATH` |

---

## 간단한 업그레이드 (GGUF 양자화)

더 좋은 PC에서 같은 GGUF 모델의 더 높은 양자화 버전 사용 시:

### 1. Q5_K_M으로 업그레이드 (권장)

```bash
# 1. 새 모델 다운로드 (HuggingFace에서)
# 예: wget https://huggingface.co/모델주소/ggml-model-Q5_K_M.gguf -O models/ggml-model-Q5_K_M.gguf

# 2. .env 파일 수정
MODEL_PATH=./models/ggml-model-Q5_K_M.gguf

# 3. 서버 재시작
pkill -f streamlit
pkill -f uvicorn
bash start_ai_chat.sh
```

**개선 효과**:
- 메모리: 4GB → 6GB
- 성능: +30% 품질 향상

### 2. Q8_0으로 업그레이드 (고성능 PC)

```bash
MODEL_PATH=./models/ggml-model-Q8_0.gguf
```

**개선 효과**:
- 메모리: 4GB → 12GB
- 성능: +50% 품질 향상 (거의 원본 수준)

### 양자화 수준별 비교

| 양자화 | 메모리 | 품질 | 속도 | 권장 환경 |
|--------|--------|------|------|-----------|
| Q4_K_M (현재) | 4GB | 60점 | 빠름 | 일반 PC, CPU |
| Q5_K_M | 6GB | 75점 | 중간 | 좋은 PC |
| Q6_K | 8GB | 85점 | 중간 | 고사양 PC |
| Q8_0 | 12GB | 95점 | 느림 | RTX 4090 등 |
| F16 | 24GB | 100점 | 매우 느림 | GPU 필수 |

---

## GPU 서버 마이그레이션

### 현재 시스템 vs GPU 서버

| 항목 | 현재 (CPU) | GPU 서버 (H100) |
|------|------------|-----------------|
| 모델 형식 | GGUF (양자화) | FP16 (원본) |
| 모델 크기 | 4GB | 140GB |
| 추론 라이브러리 | llama-cpp-python | vLLM |
| 추론 속도 | ~5 tok/s | ~200 tok/s (40배) |
| 답변 품질 | 60점 | 95점 (GPT-4 수준) |
| VRAM | - | 80GB |

---

## 마이그레이션 절차

### 1단계: 현재 시스템 백업

```bash
# 데이터 백업
tar -czf ai-chat-backup-$(date +%Y%m%d).tar.gz \
    docs/ \
    metadata.db \
    .env \
    app/ \
    scripts/

# 백업 파일 이동
scp ai-chat-backup-*.tar.gz user@새서버:/backup/
```

### 2단계: 새 서버에 시스템 복원

```bash
# 새 서버에서
cd /home/user/
tar -xzf /backup/ai-chat-backup-*.tar.gz
cd AI-CHAT
```

### 3단계: GPU 환경 설정

```bash
# CUDA 확인 (H100은 CUDA 12.x 필요)
nvidia-smi

# vLLM 및 PyTorch 설치
pip install vllm==0.5.5
pip install torch==2.3.0+cu121 --index-url https://download.pytorch.org/whl/cu121
pip install transformers==4.40.0
```

### 4단계: 모델 다운로드 (추천 모델)

#### 옵션 A: Qwen2.5-72B-Instruct (최고 추천)

```bash
# HuggingFace CLI 설치
pip install huggingface-hub

# 모델 다운로드 (~145GB, 2-3시간 소요)
huggingface-cli download Qwen/Qwen2.5-72B-Instruct \
    --local-dir ./models/Qwen2.5-72B \
    --local-dir-use-symlinks False
```

**특징**:
- 한국어 성능: ⭐⭐⭐⭐⭐ (GPT-4 수준)
- 문서 분석: 탁월
- 무료: ✅

#### 옵션 B: EEVE-Korean-70B (한국어 특화)

```bash
huggingface-cli download yanolja/EEVE-Korean-Instruct-70B-v1.0 \
    --local-dir ./models/EEVE-70B
```

**특징**:
- 한국어 성능: ⭐⭐⭐⭐⭐ (한국어 최적화)
- 한국 기업 Yanolja 파인튜닝

#### 옵션 C: Llama-3.1-70B

```bash
huggingface-cli download meta-llama/Meta-Llama-3.1-70B-Instruct \
    --local-dir ./models/Llama-3.1-70B
```

**특징**:
- 범용 성능: ⭐⭐⭐⭐⭐
- 한국어: ⭐⭐⭐⭐

---

### 5단계: 코드 변경

**중요**: GPU 서버에서는 `llama-cpp-python` 대신 `vLLM`을 사용해야 합니다.

#### 변경이 필요한 파일

- `app/rag/pipeline.py` - RAG 파이프라인 (LLM 호출 부분)
- `requirements.txt` - 의존성

#### 변경 예시

**기존 (CPU/GGUF)**:
```python
from llama_cpp import Llama

llm = Llama(
    model_path="./models/ggml-model-Q4_K_M.gguf",
    n_ctx=4096,
    n_threads=8
)
```

**변경 후 (GPU/vLLM)**:
```python
from vllm import LLM, SamplingParams

llm = LLM(
    model="./models/Qwen2.5-72B",
    tensor_parallel_size=1,  # H100 1장 사용
    dtype="float16",
    max_model_len=32768,     # 긴 문서 처리
    gpu_memory_utilization=0.9
)

sampling_params = SamplingParams(
    temperature=0.7,
    top_p=0.9,
    max_tokens=2048
)
```

---

### 6단계: 환경 변수 설정

`.env` 파일 수정:

```bash
# 모델 설정
MODEL_PATH=./models/Qwen2.5-72B
MODEL_TYPE=vllm  # 새로 추가

# GPU 설정
TENSOR_PARALLEL_SIZE=1
GPU_MEMORY_UTILIZATION=0.9
MAX_MODEL_LEN=32768

# 기존 설정은 유지
DOCS_DIR=docs
LOG_LEVEL=INFO
```

---

### 7단계: 테스트 및 검증

```bash
# 1. 헬스체크
.venv/bin/python scripts/ops/healthcheck.py

# 2. 간단한 쿼리 테스트
curl -X POST http://localhost:7860/api/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "2024년 방송 장비 현황"}'

# 3. 웹 UI 확인
# http://새서버IP:8501 접속
```

---

### 8단계: 성능 벤치마크

```bash
# 응답 속도 측정
time curl -X POST http://localhost:7860/api/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "기안자가 하승범인 문서를 모두 찾아주세요"}'

# GPU 사용률 모니터링
watch -n 1 nvidia-smi
```

---

## 예상 성능 향상

| 메트릭 | 현재 | GPU 서버 | 개선 |
|--------|------|----------|------|
| 평균 응답 시간 | 10초 | 1-2초 | **5-10배** |
| 토큰 생성 속도 | 5 tok/s | 200 tok/s | **40배** |
| 답변 정확도 | 보통 | 매우 높음 | **GPT-4 수준** |
| 한국어 이해도 | 보통 | 탁월 | **대폭 향상** |
| 동시 사용자 | 1-2명 | 10-20명 | **병렬 처리** |

---

## 주의사항 및 롤백

### 주의사항

1. **모델 다운로드 시간**: 140GB 모델은 2-3시간 소요됩니다.
2. **VRAM 확인**: H100은 80GB VRAM이므로 70B 모델 실행 가능합니다.
3. **코드 호환성**: vLLM 사용 시 코드 변경이 필요하므로 별도 브랜치에서 작업 권장.
4. **데이터 백업**: 마이그레이션 전 반드시 전체 백업.
5. **테스트 기간**: 최소 1주일 테스트 후 프로덕션 전환.

### 롤백 계획

문제 발생 시 현재 CPU 버전으로 롤백:

```bash
# 백업에서 복원
cd /home/user/AI-CHAT
git checkout main  # 또는 안정 브랜치

# CPU 버전 실행
bash start_ai_chat.sh
```

---

## 참고 자료

- vLLM 공식 문서: https://docs.vllm.ai/
- HuggingFace Models: https://huggingface.co/models
- CUDA Toolkit: https://developer.nvidia.com/cuda-toolkit

---

**마지막 업데이트**: 2025-11-25
