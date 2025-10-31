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

### 3.4 보안 설정 (프로덕션 필수)

```bash
# API 인증
API_KEY=your-secret-key-here  # 32자 이상 강력한 키 사용
API_KEY_HEADER=X-API-Key  # 커스텀 헤더명 (선택)

# CORS 허용 도메인 (화이트리스트)
ALLOWED_ORIGINS=https://yourdomain.com,https://internal.company.com

# 레이트 리미트 (요청/분/사용자)
RATE_LIMIT_PER_MINUTE=10
RATE_LIMIT_PER_HOUR=100

# 동시성 제한
MAX_CONCURRENT_REQUESTS=4

# 네트워크 바인딩 (내부 전용)
FASTAPI_HOST=127.0.0.1  # 외부 노출 금지
FASTAPI_PORT=7860
STREAMLIT_HOST=127.0.0.1
STREAMLIT_PORT=8501

# 외부 노출은 Nginx 리버스 프록시 사용 (TLS/SSL)
```

**보안 체크리스트**:
- [ ] API_KEY를 Git에 커밋하지 않음 (.gitignore 확인)
- [ ] ALLOWED_ORIGINS를 실제 도메인으로 제한
- [ ] Nginx에서 TLS 인증서 적용
- [ ] /admin/* 엔드포인트는 별도 인증 적용
- [ ] 로그에 API_KEY/토큰 노출 방지

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

## 12. SLO 및 모니터링 지표

### 12.1 Service Level Objectives (SLO)

| 지표 | 목표 | 경보 임계값 | 측정 방법 |
|------|------|------------|----------|
| **p95 응답시간** | < 5초 | > 8초 | 모든 요청 집계 |
| **RAG 인용률** | > 95% | < 80% | RAG 모드 한정 |
| **RAG 비율** | 30-70% | <10% or >90% | 라우팅 이상 감지 |
| **오류율** | < 1% | > 5% | HTTP 5xx 기준 |
| **GPU 메모리** | < 7.0 GB | > 7.5 GB | RTX 4060 8GB 기준 |
| **가용성** | > 99.5% | < 99% | Uptime 월간 |

### 12.2 Prometheus 지표 (제안)

```yaml
# /metrics 엔드포인트에서 노출
- rag_query_duration_seconds (histogram)
- rag_mode_total{mode="chat|rag"} (counter)
- rag_top_score (histogram)
- rag_citation_rate (gauge)
- rag_errors_total{type="search|llm|timeout"} (counter)
- gpu_memory_used_bytes (gauge)
```

### 12.3 알람 규칙 예시

```yaml
# Prometheus Alert Rules
groups:
  - name: ai_chat
    rules:
      - alert: HighLatency
        expr: histogram_quantile(0.95, rag_query_duration_seconds) > 8
        for: 5m
        annotations:
          summary: "p95 응답시간 초과: {{ $value }}초"

      - alert: LowCitationRate
        expr: rag_citation_rate < 0.80
        for: 10m
        annotations:
          summary: "RAG 인용률 저하: {{ $value }}"

      - alert: AbnormalRAGRatio
        expr: rate(rag_mode_total{mode="rag"}[1h]) / rate(rag_mode_total[1h]) < 0.1 OR > 0.9
        for: 15m
        annotations:
          summary: "RAG 모드 비율 이상: {{ $value }}"

      - alert: HighErrorRate
        expr: rate(rag_errors_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "오류율 상승: {{ $value }}"
          severity: critical
```

---

## 13. 장애 대응 가이드

### 13.1 장애 패턴별 대응

| 증상 | 원인 | 즉시 조치 | 근본 해결 |
|------|------|----------|----------|
| **응답 없음 (타임아웃)** | LLM 로드 실패, GPU OOM | 1) 서비스 재시작<br>2) GPU 메모리 확인 | N_CTX 감소, N_GPU_LAYERS 조정 |
| **인용 누락 (RAG 모드)** | 프롬프트 문제, LLM 불안정 | REQUIRE_CITATIONS=true 확인 | 프롬프트 재작성, MAX_LLM_RETRY 증가 |
| **검색 결과 없음** | 인덱스 손상, DB 락 | 1) 인덱스 재빌드<br>2) SQLite 락 해제 | 인덱스 백업 복원 |
| **RAG 비율 0%** | RAG_MIN_SCORE 너무 높음 | RAG_MIN_SCORE=0.25로 임시 하향 | 검색 품질 개선, 가중치 재조정 |
| **메모리 부족 (OOM)** | 컨텍스트 크기 과다, 동시 요청 | 1) N_CTX=4096으로 복원<br>2) MAX_CONCURRENT_REQUESTS=2 | 배치 크기 감소, GPU 레이어 조정 |
| **느린 응답 (>10초)** | 문서 수 과다, CPU 병목 | DOC_TOPK=2, SEARCH_TOP_K=3 | BM25 인덱스 최적화, GPU 활용 증대 |

### 13.2 긴급 연락 체계

```
1차: 온콜 엔지니어 (Slack DM)
2차: 기술팀장 (전화)
3차: CTO (중대 장애 시)

장애 등급:
- P0 (Critical): 서비스 전체 다운, 즉시 대응
- P1 (High): 기능 일부 불능, 1시간 내 대응
- P2 (Medium): 성능 저하, 4시간 내 대응
- P3 (Low): 경미한 오류, 1일 내 대응
```

### 13.3 복구 명령어 치트시트

```bash
# 서비스 재시작 (systemd)
sudo systemctl restart ai-chat-backend.service
sudo systemctl restart ai-chat-ui.service

# 로그 확인
journalctl -u ai-chat-backend.service -n 100 --no-pager
tail -100 /var/log/ai-chat/app.log

# GPU 메모리 확인
nvidia-smi

# 프로세스 강제 종료
pkill -f "uvicorn"
pkill -f "streamlit"

# 인덱스 재빌드 (비상시)
python scripts/rebuild_indexes.py --force

# 데이터베이스 백업 복원
cp /backup/metadata.db.20251030 ./metadata.db

# 설정 롤백 (.env)
cp .env.backup .env
sudo systemctl restart ai-chat-backend.service
```

---

## 14. 보안 및 운영 필수 10항

### 14.1 인증 및 권한

- **구현**: FastAPI에서 API_KEY 헤더 검증 미들웨어
- **적용 범위**: /rag/*, /admin/*, /metrics (읽기 전용 제외)
- **키 관리**: systemd EnvironmentFile로 로드, Git 미추적

```python
# app/api/auth.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API key")
```

### 14.2 네트워크 보안

- **내부 바인딩**: FastAPI/Streamlit은 127.0.0.1만
- **외부 노출**: Nginx 리버스 프록시 (TLS 1.3)
- **Nginx 설정**:
  ```nginx
  server {
      listen 443 ssl http2;
      server_name yourdomain.com;

      ssl_certificate /etc/ssl/certs/your_cert.pem;
      ssl_certificate_key /etc/ssl/private/your_key.pem;

      client_max_body_size 100M;
      proxy_read_timeout 300s;

      location /api/ {
          proxy_pass http://127.0.0.1:7860/;
          proxy_set_header X-Real-IP $remote_addr;
      }
  }
  ```

### 14.3 비밀정보 관리

- **.env 보호**: 0600 권한, Git 제외 (.gitignore 확인)
- **CI/CD**: GitHub Secrets로 주입, gitleaks 프리커밋 훅
- **감사**: `git log -- .env` 정기 확인

```bash
# .env 권한 설정
chmod 600 .env
chown ai-chat:ai-chat .env

# gitleaks 설치 (프리커밋)
pre-commit install
# .pre-commit-config.yaml에 gitleaks 추가
```

### 14.4 감사 로그

**로그 구조** (JSON):
```json
{
  "timestamp": "2025-10-30T15:30:00Z",
  "user_id": "user123",
  "query_hash": "sha256(query)",
  "mode": "rag",
  "top_score": 0.87,
  "docs_used": ["doc_id_1", "doc_id_2"],
  "latency_ms": 3200,
  "http_status": 200
}
```

**저장 위치**: `/var/log/ai-chat/audit.jsonl`
**보존 기간**: 30일 (logrotate)

### 14.5 개인정보 및 기밀 보호

- **소스 허용 목록**: `docs/`, `internal/` 경로만 허용
- **외부 URL 차단**: 답변에 http:// 패턴 삽입 방지
- **민감 키워드 마스킹**: "주민등록번호", "계좌번호" 등

```python
# app/rag/filters.py
ALLOWED_PATHS = ["/var/docs", "/opt/internal"]
SENSITIVE_PATTERNS = [r"\d{6}-\d{7}", r"\d{3}-\d{2}-\d{5}"]
```

### 14.6 레이트 리미트

- **적용**: slowapi 미들웨어
- **제한**: 10 req/min/IP, 100 req/hour/IP
- **예외**: 내부 IP 대역 (10.0.0.0/8)

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/rag/query")
@limiter.limit("10/minute")
async def query(request: Request, ...):
    ...
```

### 14.7 메트릭 및 알람

- **Prometheus 노출**: /metrics (인증 필요)
- **알람 채널**: Slack #ai-chat-alerts
- **주간 리포트**: p95, 오류율, RAG 비율 Slack 자동 발송

### 14.8 백업 및 복구

**백업 대상**:
- `var/index/` (BM25/FAISS 인덱스)
- `metadata.db` (문서 메타데이터)
- `.env` (설정)
- `models/` (LLM 모델, 선택)

**백업 주기**: 주 1회 (일요일 03:00)
**복구 리허설**: 분기별 1회

```bash
# 백업 스크립트
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf /backup/ai-chat-$DATE.tar.gz var/index/ metadata.db .env

# 복구 테스트
tar -xzf /backup/ai-chat-latest.tar.gz -C /tmp/restore
python scripts/verify_indexes.py --path /tmp/restore/var/index
```

### 14.9 데이터 보존 정책

| 데이터 유형 | 보존 기간 | 처리 방법 |
|------------|----------|----------|
| 질의 로그 | 30일 | 익명화 후 폐기 |
| 감사 로그 | 30일 | 익명화 후 폐기 |
| 시나리오 리포트 | 90일 | 압축 보관 |
| 메트릭 데이터 | 1년 | Prometheus TSDB |

```bash
# logrotate 설정
# /etc/logrotate.d/ai-chat
/var/log/ai-chat/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

### 14.10 CI/CD 회귀 방지

- **PR 게이트**: 8가지 시나리오 테스트 + 라이선스 스캔
- **SBOM 생성**: `pip-licenses --format=json > sbom.json`
- **취약점 스캔**: `pip-audit`

```yaml
# .github/workflows/ci.yml
name: CI
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run scenarios
        run: python scripts/scenario_validation.py
      - name: License check
        run: pip-licenses --fail-on="GPL;AGPL"
      - name: Security scan
        run: pip-audit --fix
```

---

## 15. 운영 컷오버 체크리스트

### 15.1 사전 준비 (D-7)

- [ ] 백업 정책 수립 및 백업 스크립트 테스트
- [ ] Nginx 설정 및 TLS 인증서 적용
- [ ] API_KEY 생성 및 EnvironmentFile 등록
- [ ] Prometheus/Grafana 대시보드 구성
- [ ] Slack 알람 채널 생성 및 테스트
- [ ] 온콜 순번 및 연락처 공유

### 15.2 컷오버 당일 (D-Day)

**13:00 - 준비**
- [ ] 백업 수행 (인덱스/DB/설정)
- [ ] systemd 서비스 배포
- [ ] ./start_ai_chat.sh 로컬 테스트 (8/8 시나리오 통과)

**14:00 - 배포**
- [ ] systemd 서비스 시작
- [ ] /healthz, /version 200 응답 확인
- [ ] Nginx 프록시 경유 테스트

**14:30 - 검증**
- [ ] scripts/scenario_validation.py 8/8 통과
- [ ] 평균 응답 시간 < 5초 확인
- [ ] Prometheus 메트릭 수집 확인

**15:00 - 모니터링**
- [ ] Grafana 대시보드 모니터링 시작
- [ ] 알람 규칙 동작 테스트 (임계값 임시 하향)
- [ ] 사용자 피드백 수집 시작

### 15.3 사후 점검 (D+1)

- [ ] 24시간 안정성 확인 (p95 < 5초, 오류율 < 1%)
- [ ] 감사 로그 생성 확인
- [ ] 백업 자동화 동작 확인
- [ ] 운영 문서 최종 업데이트

---

**마지막 업데이트**: 2025-10-30
**버전**: 2.0.0 (프로덕션 준비 완료)
