# AI-CHAT 운영 가이드 (RUNBOOK)

**최종 업데이트**: 2025-10-30
**시스템**: 하이브리드 검색 + RAG 파이프라인 + LLaMA v2 (Q4_K_M)
**기능**: 일반 대화 + 문서근거 RAG 자동 전환

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [운용 모드](#2-운용-모드)
3. [환경 설정](#3-환경-설정)
4. [프롬프트 구성](#4-프롬프트-구성)
5. [기능 점검](#5-기능-점검)
6. [API 엔드포인트](#6-api-엔드포인트)
7. [품질 가드](#7-품질-가드)
8. [모니터링 & 로깅](#8-모니터링--로깅)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. 시스템 개요

### 1.1 아키텍처

```
사용자 질의
    ↓
Query Router (의도 분석)
    ↓
┌─────────────┬─────────────┐
│ 일반 대화   │ 문서근거 RAG │
│ (Chat Mode) │ (RAG Mode)   │
└─────────────┴─────────────┘
    ↓
LLaMA v2 Model (10.8B, Q4_K_M)
    ↓
응답 생성 + 출처 인용
```

### 1.2 핵심 기능

- **일반 대화**: 상식/계산/인사 등 문서 없이 답변
- **문서근거 RAG**: 사내 DB 검색 → 재랭크 → 인용 답변
- **자동 전환**: 검색 점수에 따라 모드 자동 전환
- **출처 보장**: REQUIRE_CITATIONS=true일 때 출처 강제

---

## 2. 운용 모드

### 2.1 MODE 설정

| MODE | 설명 | 사용 사례 |
|------|------|----------|
| **AUTO** (권장) | 점수 기반 자동 전환 | 일반 사용자 대면 |
| **SUMMARIZE** | 문서 요약 전용 | 특정 문서 분석 |
| **CHAT** | 일반 대화 전용 | 테스트/데모 |

### 2.2 AUTO 모드 동작

```python
# 검색 수행
top_score = max(search_results.scores)

if top_score >= RAG_MIN_SCORE:
    mode = "RAG"  # 문서근거 모드
    # → 출처 인용 필수
else:
    if ALLOW_UNGROUNDED_CHAT:
        mode = "CHAT"  # 일반 대화 모드
    else:
        return "근거 없음"  # 답변 거부
```

### 2.3 임계값 가이드

| RAG_MIN_SCORE | 효과 |
|---------------|------|
| 0.25 | 매우 관대 (약한 연관성도 RAG) |
| **0.35 (권장)** | 균형 (중간 연관성 이상 RAG) |
| 0.50 | 엄격 (강한 연관성만 RAG) |

---

## 3. 환경 설정

### 3.1 필수 환경변수 (.env)

```bash
# ============================================================================
# 운용 모드 설정
# ============================================================================
MODE=AUTO
RAG_MIN_SCORE=0.35
DOC_TOPK=3
REQUIRE_CITATIONS=true
ALLOW_UNGROUNDED_CHAT=true

# Chat format (모델 호환성)
CHAT_FORMAT=auto  # GGUF 메타데이터 자동 사용

# 컨텍스트 크기
N_CTX=4096  # 기본 4K, 필요시 8192 (rope-scaling 필요)

# GPU 설정
N_GPU_LAYERS=-1  # 전체 레이어 GPU 사용
MAIN_GPU=0

# LLM 생성 파라미터
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=2048
MAX_LLM_RETRY=1
```

### 3.2 품질 가드

```bash
# 점수 게이팅 (모든 문서 점수 미달 시 문서근거 차단)
ENABLE_SCORE_GATING=true

# 환각 감지 (출처 없는 사실 주장 탐지)
ENABLE_HALLUCINATION_CHECK=true

# 질의 분석 로깅
LOG_QUERY_ANALYTICS=true
```

### 3.3 검색 설정

```bash
# BM25 위주 검색 (OCR 텍스트는 키워드 기반이 정확)
SEARCH_BM25_WEIGHT=0.99
SEARCH_VECTOR_WEIGHT=0.01

# 검색 결과 개수
SEARCH_TOP_K=5
SEARCH_BM25_TOP_K=20
SEARCH_VEC_TOP_K=20
```

---

## 4. 프롬프트 구성

### 4.1 일반 대화 프롬프트

```python
CHAT_SYSTEM_PROMPT = """
당신은 친절한 AI 어시스턴트입니다.

규칙:
1. 일반 상식 질문은 자연어로 간결히 답변
2. 사내 문서 인용은 하지 않음
3. 불확실한 정보는 "잘 모르겠습니다"
"""
```

### 4.2 문서근거 프롬프트

```python
RAG_SYSTEM_PROMPT = """
당신은 사내 문서 전문 AI 어시스턴트입니다.

[규칙]
1) 제공된 컨텍스트 내 근거만 사용
2) 답변 말미에 [출처] 섹션으로 파일명/일자 나열
3) 근거 부족 시 '근거 없음(추가 키워드 제시)'로 종료

[출력 형식]
- 요약/결론 (3~5문장)
- 핵심 항목 (불릿)
- [출처]: 문서명(일자), 섹션/페이지
"""
```

### 4.3 프롬프트 최적화 팁

- **한국어 명시**: "반드시 한국어로 답변" 강조
- **출처 강제**: REQUIRE_CITATIONS=true일 때 "출처 누락 시 재시도"
- **길이 제한**: 4K 컨텍스트 기준, 8K 필요 시 rope-scaling 적용

---

## 5. 기능 점검

### 5.1 8가지 시나리오 테스트

```bash
# 전체 시나리오 실행
python test_8_scenarios.py

# 특정 시나리오만 실행
python test_8_scenarios.py --scenario 1
```

### 5.2 시나리오 목록

| # | 시나리오 | 질의 예시 | 예상 모드 | 예상 출처 |
|---|----------|----------|-----------|----------|
| 1 | 일반 대화 | "1+1은?" | CHAT | 없음 |
| 2 | 회사 문서 검색 | "2024-08-14 방송시스템 소모품 검토서 요약" | RAG | 있음 |
| 3 | 정책 질의 | "NVR 저장용량 산정 기준은?" | RAG | 있음 |
| 4 | 인프라 구성 | "Tri-Level Sync 신호 분배 구성" | RAG | 있음 |
| 5 | 사례 비교 | "지미집 Control Box 수리 원인/조치" | RAG | 있음 |
| 6 | 필터 검색 | "기안자=남준수, 2024년 문서만" | RAG | 있음 |
| 7 | 무근거 방지 | "APEX 중계 동시통역 라우팅 도면?" | CHAT | 없음 (근거 없음) |
| 8 | 긴 문서 요약 | "방송시스템 소모품 3문장 TL;DR" | RAG | 있음 |

### 5.3 성공 기준

- **모드 정확도**: 예상 모드와 실제 모드 일치
- **출처 정확도**: 예상 출처 여부와 실제 일치
- **응답 시간**: 평균 < 5초
- **성공률**: 8/8 (100%)

---

## 6. API 엔드포인트

### 6.1 일반 대화

```bash
POST /chat
Content-Type: application/json

{
  "query": "안녕하세요",
  "mode": "chat"
}
```

**Response:**
```json
{
  "answer": "안녕하세요! 무엇을 도와드릴까요?",
  "mode": "chat",
  "sources": [],
  "score": 0.0,
  "latency": 0.5
}
```

### 6.2 RAG 질의

```bash
POST /rag/query
Content-Type: application/json

{
  "q": "NVR 저장용량은?",
  "top_k": 3,
  "filters": {
    "year": "2024"
  }
}
```

**Response:**
```json
{
  "answer": "NVR 저장용량은 7일 기준 10TB입니다. [출처: 2024-05-20_NVR설치계획서.pdf]",
  "mode": "rag",
  "sources": ["2024-05-20_NVR설치계획서.pdf"],
  "score": 0.87,
  "latency": 3.2
}
```

### 6.3 문서 요약

```bash
POST /rag/summarize
Content-Type: application/json

{
  "doc_id": "2024-08-14_방송시스템소모품구매검토서.pdf",
  "section": "full"
}
```

---

## 7. 품질 가드

### 7.1 점수 게이팅

```python
# 상위 문서 점수 모두 RAG_MIN_SCORE 미만 → 문서근거 차단
if ENABLE_SCORE_GATING:
    if max(scores) < RAG_MIN_SCORE:
        if ALLOW_UNGROUNDED_CHAT:
            return chat_response()
        else:
            return "근거 없음"
```

### 7.2 출처 강제

```python
# REQUIRE_CITATIONS=true일 때 출처 누락 시 재시도
if REQUIRE_CITATIONS:
    if not has_citations(answer):
        answer = retry_with_citation_prompt()
```

### 7.3 환각 억제

- **사실 주장 탐지**: "~입니다", "~합니다" 패턴 검출
- **출처 교차 검증**: 주장한 사실이 인용 문서에 있는지 확인
- **신뢰도 하향**: 환각 의심 시 신뢰도 30% 감소

### 7.4 길이 제한

- **N_CTX=4096** (기본): 대부분의 질의 처리 가능
- **N_CTX=8192** (확장): 긴 문서 요약 시 필요
  - ⚠️ rope-scaling 적용 필요 (config.py)
  - 메모리 사용량 2배 증가

---

## 8. 모니터링 & 로깅

### 8.1 질의 분석 로그

```json
// reports/query_analytics_{date}.json
{
  "timestamp": "2025-10-30T15:30:00",
  "query": "NVR 저장용량은?",
  "mode": "rag",
  "top_score": 0.87,
  "latency": 3.2,
  "answer_length": 156,
  "sources_count": 2
}
```

### 8.2 모니터링 지표

| 지표 | 목표 | 경고 |
|------|------|------|
| 평균 응답 시간 | < 3초 | > 5초 |
| RAG 모드 비율 | 30-70% | < 10% or > 90% |
| 출처 인용률 | > 95% (RAG 모드) | < 80% |
| 에러율 | < 1% | > 5% |

### 8.3 로그 위치

```bash
# 애플리케이션 로그
./rag_system/logs/app.log

# 질의 분석 로그
./reports/query_analytics_YYYYMMDD.json

# 시나리오 테스트 결과
./reports/scenario_test_YYYYMMDD_HHMMSS.json
```

---

## 9. 트러블슈팅

### 9.1 일반 대화가 너무 많이 발생

**증상**: RAG 모드 비율 < 10%

**해결**:
```bash
# RAG_MIN_SCORE 낮추기
RAG_MIN_SCORE=0.25  # 기본 0.35 → 0.25
```

### 9.2 문서근거가 너무 많이 발생

**증상**: RAG 모드 비율 > 90%, 관련 없는 문서 인용

**해결**:
```bash
# RAG_MIN_SCORE 높이기
RAG_MIN_SCORE=0.50  # 기본 0.35 → 0.50

# 또는 BM25 가중치 조정
SEARCH_BM25_WEIGHT=0.95  # 기본 0.99 → 0.95
SEARCH_VECTOR_WEIGHT=0.05  # 기본 0.01 → 0.05
```

### 9.3 출처 인용이 누락됨

**증상**: RAG 모드인데 출처 없음

**해결**:
```bash
# 출처 강제 활성화
REQUIRE_CITATIONS=true

# LLM 재시도 횟수 증가
MAX_LLM_RETRY=2  # 기본 1 → 2
```

### 9.4 응답 시간이 느림

**증상**: 평균 응답 시간 > 5초

**해결**:
```bash
# 검색 결과 개수 감소
SEARCH_TOP_K=3  # 기본 5 → 3
DOC_TOPK=2  # 기본 3 → 2

# LLM max_tokens 감소
LLM_MAX_TOKENS=1024  # 기본 2048 → 1024

# GPU 레이어 확인
N_GPU_LAYERS=-1  # 전체 레이어 GPU 사용 확인
```

### 9.5 GPU 메모리 부족

**증상**: CUDA out of memory

**해결**:
```bash
# 컨텍스트 크기 감소
N_CTX=4096  # 8192 → 4096

# 배치 크기 감소
N_BATCH=512  # 1024 → 512

# 또는 GPU 레이어 감소
N_GPU_LAYERS=20  # -1 → 20 (부분 GPU 사용)
```

---

## 10. 모델 교체 절차

### 10.1 기존 Qwen 모델로 복귀

```bash
# .env 파일 수정
MODEL_PATH=./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
CHAT_FORMAT=qwen  # 또는 auto
```

### 10.2 다른 LLaMA 모델 사용

```bash
# 1. 모델 파일 배치
cp your-llama-model.gguf ./models/

# 2. .env 파일 수정
MODEL_PATH=./models/your-llama-model.gguf
CHAT_FORMAT=auto  # 자동 감지 권장

# 3. 모델 검증
python test_qa_simple.py

# 4. 시나리오 테스트
python test_8_scenarios.py
```

### 10.3 Chat Format 설정 가이드

| 모델 계열 | CHAT_FORMAT | 설명 |
|----------|-------------|------|
| LLaMA v2 | `auto` 또는 `llama-2` | 기본 LLaMA 템플릿 |
| Qwen 2.x | `auto` 또는 `qwen` | Qwen ChatML 템플릿 |
| Mistral | `auto` 또는 `chatml` | ChatML 템플릿 |
| Zephyr | `auto` 또는 `zephyr` | Zephyr 템플릿 |
| 기타 | `auto` | GGUF 메타데이터 사용 |

---

## 11. 부록

### 11.1 참고 문서

- [CHANGELOG.md](./CHANGELOG.md): 변경 이력
- [README.md](./README.md): 프로젝트 개요
- [test_8_scenarios.py](./test_8_scenarios.py): 시나리오 테스트 스크립트

### 11.2 연락처

- **기술 담당**: AI-CHAT 개발팀
- **이슈 보고**: GitHub Issues

---

**마지막 업데이트**: 2025-10-30
**버전**: 1.0.0
