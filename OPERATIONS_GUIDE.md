# AI-CHAT 시스템 운영 가이드

이 문서는 AI-CHAT 문서 검색 시스템의 일상 운영을 위한 가이드입니다.

## 목차

1. [시스템 개요](#시스템-개요)
2. [일상 운영](#일상-운영)
3. [문제 해결](#문제-해결)
4. [유지보수 스크립트](#유지보수-스크립트)
5. [주의사항](#주의사항)
6. [모델 업그레이드](#모델-업그레이드)
7. [서버 마이그레이션](#서버-마이그레이션)

---

## 시스템 개요

### 구성 요소
- **웹 서버**: Streamlit (프론트엔드) + Uvicorn (백엔드 API)
- **데이터베이스**: SQLite (`metadata.db`)
- **문서 저장소**: `docs/year_YYYY/` 폴더
- **검색 엔진**: FAISS (벡터 검색) + BM25 (키워드 검색)

### 주요 디렉토리
```
/home/wnstn4647/AI-CHAT/
├── docs/
│   ├── incoming/         # 신규 문서 업로드 폴더
│   ├── year_2014~/       # 연도별 문서 저장소
│   └── rejected/         # 처리 실패 문서
├── scripts/              # 유지보수 스크립트
├── metadata.db           # 문서 메타데이터 DB
└── .venv/                # Python 가상환경
```

---

## 일상 운영

### 1. 시스템 시작

```bash
bash start_ai_chat.sh
```

서버가 정상적으로 시작되면 다음 URL에서 접속 가능:
- Streamlit UI: http://localhost:8501
- API: http://localhost:8000

### 2. 신규 문서 추가

**방법 1: incoming 폴더 사용 (권장)**
```bash
# 1. PDF 파일을 incoming 폴더에 복사
cp /path/to/new_document.pdf docs/incoming/

# 2. 인제스트 스크립트 실행
./scripts/ingest_from_docs.py

# 3. 필요시 인덱스 재구축
./scripts/rebuild_rag_indexes.py
```

**방법 2: OCR이 필요한 이미지 PDF**
```bash
# OCR 모드로 처리
./scripts/ingest_from_docs.py --ocr-mode force
```

### 3. 일일 헬스체크 (매일 1회 권장)

```bash
./scripts/healthcheck.py
```

이 스크립트는 다음을 체크합니다:
- DB 연결 상태
- 파일시스템-DB 동기화
- 디스크 공간
- 메타데이터 품질
- 서비스 실행 상태

**문제가 발견되면 권장 조치 명령어가 출력됩니다.**

---

## 문제 해결

### 문제 1: 문서가 웹에서 검색되지 않음

**진단:**
```bash
# 동기화 상태 확인
./scripts/auto_sync_checker.py --dry-run
```

**해결:**
```bash
# 누락된 문서 자동 복구
./scripts/auto_sync_checker.py --auto-fix

# OCR이 필요한 경우
./scripts/auto_sync_checker.py --auto-fix --use-ocr
```

### 문제 2: 메타데이터(기안자 등)가 누락됨

**진단:**
```bash
# DB에서 기안자 누락 확인
sqlite3 metadata.db "SELECT COUNT(*) FROM documents WHERE drafter IS NULL;"
```

**해결:**
```bash
# 메타데이터 재추출
./scripts/reextract_metadata.py

# Dry-run으로 먼저 확인
./scripts/reextract_metadata.py --dry-run
```

### 문제 3: 중복 파일이 쌓임

**진단:**
```bash
# year_정보 없 폴더 확인
ls -la docs/year_정보\ 없/
```

**해결:**
```bash
# 중복 파일 정리 (Dry-run 먼저 권장)
./scripts/cleanup_duplicates.py --dry-run

# 실제 삭제
./scripts/cleanup_duplicates.py
```

### 문제 4: OCR 텍스트 추출 불량

**진단:**
```bash
# 텍스트 추출이 부족한 문서 찾기
./scripts/force_ocr_update.py --dry-run --threshold 100
```

**해결:**
```bash
# OCR 재처리
./scripts/force_ocr_update.py --threshold 100
```

### 문제 5: 웹 서버가 응답하지 않음

**진단:**
```bash
# 프로세스 확인
ps aux | grep -E "(streamlit|uvicorn)"
```

**해결:**
```bash
# 모든 관련 프로세스 종료
pkill -f streamlit
pkill -f uvicorn

# 재시작
bash start_ai_chat.sh
```

---

## 유지보수 스크립트

### 자동화 스크립트 목록

| 스크립트 | 용도 | 실행 주기 |
|---------|------|-----------|
| `healthcheck.py` | 시스템 전체 상태 체크 | 매일 |
| `auto_sync_checker.py` | 파일-DB 동기화 확인 및 복구 | 주 1회 |
| `cleanup_duplicates.py` | 중복 파일 정리 | 월 1회 |
| `reextract_metadata.py` | 메타데이터 재추출 | 필요시 |
| `force_ocr_update.py` | OCR 재처리 | 필요시 |

### Cron 설정 예시

매일 오전 9시에 헬스체크:
```bash
crontab -e

# 추가
0 9 * * * cd /home/wnstn4647/AI-CHAT && ./scripts/healthcheck.py >> /tmp/healthcheck.log 2>&1
```

매주 일요일 오전 3시에 동기화 체크:
```bash
0 3 * * 0 cd /home/wnstn4647/AI-CHAT && ./scripts/auto_sync_checker.py --auto-fix >> /tmp/sync_check.log 2>&1
```

---

## 주의사항

### ⚠️ 절대 하지 말아야 할 것

1. **DB 파일 직접 수정 금지**
   - `metadata.db`를 직접 편집하지 마세요
   - 항상 제공된 스크립트를 사용하세요

2. **venv 외부에서 스크립트 실행 금지**
   - 모든 스크립트는 `.venv/bin/python3`를 사용하도록 설정됨
   - `python3 scripts/xxx.py` 대신 `./scripts/xxx.py` 사용

3. **year_YYYY 폴더의 파일 직접 삭제/이동 금지**
   - DB와 불일치가 발생합니다
   - 반드시 스크립트를 통해 처리하세요

4. **동시 인제스트 금지**
   - 한 번에 하나의 인제스트만 실행하세요
   - DB 락 충돌이 발생할 수 있습니다

### ✅ 권장사항

1. **정기 백업**
   ```bash
   # DB 백업
   cp metadata.db metadata.db.backup_$(date +%Y%m%d)

   # 문서 폴더 백업
   tar -czf docs_backup_$(date +%Y%m%d).tar.gz docs/year_20*
   ```

2. **로그 확인**
   ```bash
   # 최근 로그 확인
   ls -lt rag_system/logs/
   tail -50 rag_system/logs/app_YYYYMMDD.log
   ```

3. **디스크 공간 모니터링**
   ```bash
   df -h .
   ```

---

## 긴급 연락처

시스템 관리 문의:
- 시스템 개발자: [연락처 추가 필요]
- 기술 지원: [연락처 추가 필요]

---

---

## 모델 업그레이드

### 현재 모델 정보
- **모델 파일**: `ggml-model-Q4_K_M.gguf`
- **양자화 수준**: 4-bit (경량)
- **메모리 사용**: ~4GB RAM
- **추론 속도**: ~5 tokens/s (CPU)
- **설정 위치**: `.env` 파일의 `MODEL_PATH`

### 간단한 업그레이드 (같은 모델, 더 높은 품질)

더 좋은 PC에서 같은 GGUF 모델의 더 높은 양자화 버전 사용 시:

**1. Q5_K_M으로 업그레이드 (권장)**
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
- 메모리: 4GB → 6GB
- 성능: +30% 품질 향상

**2. Q8_0으로 업그레이드 (고성능 PC)**
```bash
MODEL_PATH=./models/ggml-model-Q8_0.gguf
```
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

## 서버 마이그레이션

### GPU 서버급 워크스테이션 이전 (NVIDIA H100 등)

**예정일**: 2025년 12월 중순

### 현재 시스템 vs GPU 서버

| 항목 | 현재 (CPU) | GPU 서버 (H100) |
|------|------------|-----------------|
| 모델 형식 | GGUF (양자화) | FP16 (원본) |
| 모델 크기 | 4GB | 140GB |
| 추론 라이브러리 | llama-cpp-python | vLLM |
| 추론 속도 | ~5 tok/s | ~200 tok/s (40배) |
| 답변 품질 | 60점 | 95점 (GPT-4 수준) |
| VRAM | - | 80GB |

### 마이그레이션 절차

#### 1단계: 현재 시스템 백업
```bash
# 데이터 백업
tar -czf ai-chat-backup-$(date +%Y%m%d).tar.gz \
    docs/ \
    metadata.db \
    .env \
    rag_system/

# 백업 파일 이동
scp ai-chat-backup-*.tar.gz user@새서버:/backup/
```

#### 2단계: 새 서버에 시스템 복원
```bash
# 새 서버에서
cd /home/user/
tar -xzf /backup/ai-chat-backup-*.tar.gz
cd AI-CHAT
```

#### 3단계: GPU 환경 설정
```bash
# CUDA 확인 (H100은 CUDA 12.x 필요)
nvidia-smi

# vLLM 및 PyTorch 설치
pip install vllm==0.5.5
pip install torch==2.3.0+cu121 --index-url https://download.pytorch.org/whl/cu121
pip install transformers==4.40.0
```

#### 4단계: 모델 다운로드 (추천 모델)

**옵션 A: Qwen2.5-72B-Instruct (최고 추천)**
```bash
# HuggingFace CLI 설치
pip install huggingface-hub

# 모델 다운로드 (~145GB, 2-3시간 소요)
huggingface-cli download Qwen/Qwen2.5-72B-Instruct \
    --local-dir ./models/Qwen2.5-72B \
    --local-dir-use-symlinks False
```
- 한국어 성능: ⭐⭐⭐⭐⭐ (GPT-4 수준)
- 문서 분석: 탁월
- 무료: ✅

**옵션 B: EEVE-Korean-70B (한국어 특화)**
```bash
huggingface-cli download yanolja/EEVE-Korean-Instruct-70B-v1.0 \
    --local-dir ./models/EEVE-70B
```
- 한국어 성능: ⭐⭐⭐⭐⭐ (한국어 최적화)
- 한국 기업 Yanolja 파인튜닝

**옵션 C: Llama-3.1-70B**
```bash
huggingface-cli download meta-llama/Meta-Llama-3.1-70B-Instruct \
    --local-dir ./models/Llama-3.1-70B
```
- 범용 성능: ⭐⭐⭐⭐⭐
- 한국어: ⭐⭐⭐⭐

#### 5단계: 코드 변경

**중요**: GPU 서버에서는 `llama-cpp-python` 대신 `vLLM`을 사용해야 합니다.

변경이 필요한 파일:
- `rag_system/active/llm_wrapper.py` - LLM 초기화 및 호출 로직
- `rag_system/active/llm_singleton.py` - 싱글톤 패턴
- `app/rag/pipeline.py` - RAG 파이프라인
- `requirements.txt` - 의존성

**변경 예시** (`llm_wrapper.py`):
```python
# 기존 (CPU/GGUF)
from llama_cpp import Llama

llm = Llama(
    model_path="./models/ggml-model-Q4_K_M.gguf",
    n_ctx=4096,
    n_threads=8
)

# 변경 후 (GPU/vLLM)
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

#### 6단계: 환경 변수 설정

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

#### 7단계: 테스트 및 검증
```bash
# 1. 헬스체크
./scripts/healthcheck.py

# 2. 간단한 쿼리 테스트
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "2024년 방송 장비 현황"}'

# 3. 웹 UI 확인
# http://새서버IP:8501 접속
```

#### 8단계: 성능 벤치마크
```bash
# 응답 속도 측정
time curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "기안자가 하승범인 문서를 모두 찾아주세요"}'

# GPU 사용률 모니터링
watch -n 1 nvidia-smi
```

### 예상 성능 향상

| 메트릭 | 현재 | GPU 서버 | 개선 |
|--------|------|----------|------|
| 평균 응답 시간 | 10초 | 1-2초 | **5-10배** |
| 토큰 생성 속도 | 5 tok/s | 200 tok/s | **40배** |
| 답변 정확도 | 보통 | 매우 높음 | **GPT-4 수준** |
| 한국어 이해도 | 보통 | 탁월 | **대폭 향상** |
| 동시 사용자 | 1-2명 | 10-20명 | **병렬 처리** |

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

## 변경 이력

| 날짜 | 변경 내용 | 작성자 |
|------|-----------|--------|
| 2025-11-24 | 최초 작성 | AI Assistant |
| 2025-11-24 | 모델 업그레이드 및 서버 마이그레이션 섹션 추가 | AI Assistant |

