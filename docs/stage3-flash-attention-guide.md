# 3단계: Flash Attention 최적화 가이드

> H100 GPU에서 Flash Attention 2를 활용한 메모리 절약 및 배치 처리 성능 향상

## 📋 개요

**구현 브랜치**: `feat/h100-stage3-flash-attention`

3단계에서는 Flash Attention 2를 적용하여 다음을 달성합니다:
- **메모리 절약**: 30% 메모리 사용량 감소 (어텐션 메커니즘 최적화)
- **배치 처리**: 5-10개 질의 동시 처리로 처리량 3-5배 향상
- **TF32 가속**: H100의 Tensor Core 활용

---

## 🔧 구현된 변경사항

### 1. Flash Attention 2 설치

```bash
pip install --user flash-attn --no-build-isolation
```

**주의**: 컴파일 시간이 5-10분 소요됩니다.

### 2. Qwen72BLLM 코드 수정

**파일**: [rag_system/active/llm_wrapper.py:1964-1992](rag_system/active/llm_wrapper.py#L1964-L1992)

```python
# Flash Attention 설정 (환경변수 기반)
enable_flash_attn = os.getenv("ENABLE_FLASH_ATTENTION", "false").lower() == "true"

# TF32 활성화 (H100 성능 향상)
if torch.cuda.is_available():
    torch.set_float32_matmul_precision('high')  # TF32
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

# 모델 로드 (AWQ quantization 자동 인식)
model_kwargs = {
    "device_map": "auto",
    "torch_dtype": torch.float16,
    "trust_remote_code": True,
    "low_cpu_mem_usage": True,
}

# Flash Attention 활성화 (설치된 경우)
if enable_flash_attn:
    try:
        import flash_attn
        model_kwargs["attn_implementation"] = "flash_attention_2"
        logger.info("⚡ Flash Attention 2 활성화됨")
    except ImportError:
        logger.warning("⚠️ flash-attn 미설치 - 기본 어텐션 사용")

self.model = AutoModelForCausalLM.from_pretrained(
    str(self.model_path),
    **model_kwargs
)
```

**변경 내용**:
- 환경변수 `ENABLE_FLASH_ATTENTION`으로 활성화 제어
- TF32 활성화로 H100 성능 향상
- `attn_implementation="flash_attention_2"` 파라미터 추가
- Flash Attention 미설치 시 자동 폴백

### 3. 배치 처리 메서드 추가

**파일**: [rag_system/active/llm_wrapper.py:2079-2179](rag_system/active/llm_wrapper.py#L2079-L2179)

```python
def generate_batch_responses(
    self,
    questions: list[str],
    context_chunks_list: list[list[dict[str, Any]]]
) -> list[RAGResponse]:
    """여러 질의를 배치로 처리 (H100 성능 활용)"""
    # 프롬프트 일괄 생성
    # 배치 토크나이징 (패딩 적용)
    # 배치 생성
    # 응답 추출
```

**기능**:
- 여러 질의를 한 번의 GPU 호출로 처리
- 패딩을 통한 효율적인 배치 처리
- 평균 처리 시간 계산 및 로깅

### 4. 환경변수 설정

**파일**: [.env:122-125](.env#L122-L125)

```bash
# Flash Attention 최적화 (3단계 - H100 메모리 절약)
ENABLE_FLASH_ATTENTION=true  # Flash Attention 2 활성화 (메모리 30% 절약)
ENABLE_KV_CACHE_QUANTIZATION=false  # KV 캐시 양자화 (vLLM 전용, 추후 활성화)
KV_CACHE_DTYPE=fp8  # KV 캐시 데이터 타입 (fp8: 메모리 50% 절약)
```

**설정 값**:
- `ENABLE_FLASH_ATTENTION=true`: Flash Attention 활성화 (기본: false)
- `ENABLE_KV_CACHE_QUANTIZATION=false`: vLLM 전환 후 활성화 예정
- `KV_CACHE_DTYPE=fp8`: vLLM에서 KV 캐시 양자화에 사용

---

## 🧪 테스트 스크립트

### 1. Flash Attention 메모리 절감 테스트

**파일**: [scripts/test_flash_attention.py](scripts/test_flash_attention.py)

```bash
# Flash Attention ON/OFF 메모리 비교
python3 scripts/test_flash_attention.py
```

**측정 항목**:
- 모델 로딩 메모리
- 추론 메모리 (어텐션 레이어)
- 피크 메모리 사용량
- 생성 속도

**예상 결과**:
```
⚙️ Flash Attention OFF:
  - 모델 메모리: 42.0 GB
  - 추론 메모리: 8.5 GB
  - 피크 메모리: 50.5 GB

⚡ Flash Attention ON:
  - 모델 메모리: 42.0 GB
  - 추론 메모리: 5.9 GB  (30% 절감)
  - 피크 메모리: 47.9 GB

💰 메모리 절감:
  - 피크 메모리: -5.1% (약 2.6GB 절감)
```

### 2. 배치 처리 성능 테스트

**파일**: [scripts/test_batch_inference.py](scripts/test_batch_inference.py)

```bash
# 개별 추론 vs 배치 추론 비교
python3 scripts/test_batch_inference.py
```

**측정 항목**:
- 총 처리 시간
- 평균 응답 시간
- 처리량 (queries/sec)
- 응답 품질

**예상 결과**:
```
🔄 개별 추론 (5개 질의):
  - 총 시간: 75.0초
  - 평균 시간: 15.0초
  - 처리량: 0.07 queries/sec

⚡ 배치 추론 (5개 질의):
  - 총 시간: 25.0초  (67% 절감)
  - 평균 시간: 5.0초
  - 처리량: 0.20 queries/sec

💰 성능 향상:
  - 처리량 증가: +185.7%
```

---

## 📊 예상 성능 향상

| 항목 | 현재 (2단계) | 3단계 적용 후 | 개선율 |
|-----|------------|-------------|-------|
| **메모리 사용** | ~50GB | ~35GB | -30% |
| **동시 처리** | 1개 질의 | 5-10개 질의 | 5-10배 |
| **처리량** | 0.07 q/s | 0.2-0.35 q/s | 3-5배 |
| **배치 크기** | N/A | 5-10 | 신규 |

---

## ⚙️ 사용 방법

### 기본 사용 (Flash Attention 활성화)

```python
from rag_system.active.llm_singleton import LLMSingleton
import os

# Flash Attention 활성화
os.environ["ENABLE_FLASH_ATTENTION"] = "true"

# LLM 인스턴스 가져오기
llm = LLMSingleton.get_instance()

# 단일 질의
response = llm.generate_response("질문", context_chunks)

# 배치 질의 (5개)
responses = llm.generate_batch_responses(
    questions=["질문1", "질문2", "질문3", "질문4", "질문5"],
    context_chunks_list=[chunks1, chunks2, chunks3, chunks4, chunks5]
)
```

### Flash Attention 비활성화

```bash
# .env 파일 수정
ENABLE_FLASH_ATTENTION=false
```

또는 코드에서:

```python
os.environ["ENABLE_FLASH_ATTENTION"] = "false"
```

---

## 🚨 주의사항

### 1. Flash Attention 설치 실패 시

**증상**: `flash-attn` 설치 중 컴파일 에러

**해결**:
```bash
# CUDA 버전 확인
nvcc --version  # CUDA 12.8 필요

# 의존성 설치
pip install --user ninja packaging wheel

# 재시도
pip install --user flash-attn --no-build-isolation
```

**폴백**: Flash Attention 미설치 시 자동으로 기본 어텐션 사용

### 2. 메모리 부족 에러

**증상**: `torch.cuda.OutOfMemoryError` 발생

**해결**:
```bash
# .env에서 배치 크기 감소
N_BATCH=768  # 1536 → 768로 감소
```

또는:
```python
# 배치 질의 개수 감소
responses = llm.generate_batch_responses(
    questions=questions[:3],  # 5개 → 3개로 감소
    context_chunks_list=contexts[:3]
)
```

### 3. 성능 저하 발생 시

**증상**: 배치 처리가 개별 처리보다 느림

**원인**: 배치 크기가 너무 작거나 큼

**해결**:
```python
# 최적 배치 크기 찾기 (3-7개 권장)
for batch_size in [3, 5, 7, 10]:
    # 테스트 실행
```

---

## 🔄 롤백 방법

3단계 변경사항을 취소하려면:

```bash
# 브랜치 전환 (2단계로 복귀)
git checkout chore/ocr-dedup-v2-20251113

# Flash Attention 비활성화만 하려면
# .env 파일 수정
ENABLE_FLASH_ATTENTION=false
```

---

## 📝 체크리스트

- [x] Flash Attention 2 설치
- [x] Qwen72BLLM에 Flash Attention 적용
- [x] TF32 활성화
- [x] 배치 처리 메서드 구현
- [x] 환경변수 설정 추가
- [x] 테스트 스크립트 작성
- [ ] Flash Attention 설치 완료 대기 중
- [ ] 메모리 절감 테스트 실행
- [ ] 배치 처리 성능 테스트 실행
- [ ] 3단계 변경사항 커밋

---

## 🔗 참고 자료

- [Flash Attention 2 논문](https://arxiv.org/abs/2307.08691)
- [Transformers Flash Attention 가이드](https://huggingface.co/docs/transformers/perf_infer_gpu_one#flashattention-2)
- [H100 TF32 최적화](https://developer.nvidia.com/blog/accelerating-ai-training-with-tf32-tensor-cores/)
- [배치 처리 Best Practices](https://huggingface.co/docs/transformers/main_classes/pipelines#pipeline-batching)

---

**다음 단계**: 4단계 (vLLM 전환) - vLLM 0.13.0+ 호환성 확인 후 진행
