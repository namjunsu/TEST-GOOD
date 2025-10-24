# AI-CHAT 유지보수 가이드

## 🎯 개요

이 문서는 AI-CHAT 시스템의 유지보수 및 문제 해결을 위한 가이드입니다.

## 📋 목차

1. [시스템 구조](#시스템-구조)
2. [로그 시스템](#로그-시스템)
3. [에러 처리](#에러-처리)
4. [일반적인 문제 해결](#일반적인-문제-해결)
5. [성능 모니터링](#성능-모니터링)
6. [유지보수 작업](#유지보수-작업)

---

## 시스템 구조

```
AI-CHAT/
├── config.py                    # 중앙 설정 파일
├── web_interface.py             # 웹 인터페이스 (Streamlit)
├── hybrid_chat_rag_v2.py        # 통합 RAG 시스템
├── quick_fix_rag.py             # 빠른 검색 모듈
├── modules/                     # 핵심 모듈들
│   ├── log_system.py           # 로깅 시스템
│   ├── search_module.py        # 검색 모듈
│   └── ...
├── utils/                       # 유틸리티
│   ├── logging_utils.py        # 통합 로깅 래퍼
│   ├── error_handler.py        # 에러 처리기
│   └── system_checker.py       # 시스템 검증
├── rag_system/                  # RAG 엔진
│   ├── qwen_llm.py             # LLM 모듈
│   └── ...
└── logs/                        # 로그 파일 저장소
    ├── queries.log             # 질문/답변 로그
    ├── errors.log              # 에러 로그
    ├── performance.log         # 성능 로그
    └── system.log              # 시스템 로그
```

---

## 로그 시스템

### 로그 파일 위치

모든 로그는 `logs/` 디렉토리에 저장됩니다:

- **queries.log**: 사용자 질문과 시스템 응답
- **errors.log**: 에러 및 예외 상황
- **performance.log**: 성능 측정 데이터
- **system.log**: 일반적인 시스템 이벤트

### 로그 확인 방법

```bash
# 최근 50줄 확인
tail -50 logs/system.log

# 실시간 모니터링
tail -f logs/system.log

# 에러만 확인
tail -100 logs/errors.log

# 특정 날짜 검색
grep "2025-10-24" logs/queries.log
```

### 로그 분석

```python
# Python에서 로그 분석
from modules.log_system import get_logger

logger = get_logger()

# 통계 확인
stats = logger.get_statistics()
print(stats)

# 최근 쿼리 확인
recent = logger.analyze_recent_queries(10)
for query in recent:
    print(f"{query['timestamp']}: {query['query']}")
```

---

## 에러 처리

### 에러 처리 방식

시스템은 통합 에러 핸들러(`utils/error_handler.py`)를 사용합니다:

```python
from utils.error_handler import ErrorHandler, handle_errors

# 데코레이터 방식
@handle_errors(context="PDF 처리")
def process_pdf(file_path):
    # 작업 수행
    pass

# 직접 호출 방식
try:
    # 위험한 작업
    pass
except Exception as e:
    ErrorHandler.handle(e, context="작업 설명")
```

### 에러 타입별 대응

| 에러 타입 | 원인 | 해결 방법 |
|----------|------|----------|
| `FileNotFoundError` | 파일 없음 | 파일 경로 확인, 재인덱싱 |
| `PermissionError` | 권한 없음 | 파일 권한 변경 또는 프로세스 종료 |
| `MemoryError` | 메모리 부족 | 파일 크기 줄이기, 시스템 재시작 |
| `DatabaseError` | DB 손상 | 재인덱싱 (`♻️ 전체재인덱싱` 버튼) |
| `OCR_ERROR` | OCR 실패 | Tesseract 설치 확인 |

---

## 일반적인 문제 해결

### 1. 시스템이 시작되지 않음

**증상**: `start_ai_chat.sh` 실행 시 오류 발생

**해결**:
```bash
# 1. 시스템 검증 실행
python3 utils/system_checker.py

# 2. 가상환경 재활성화
source .venv/bin/activate

# 3. 패키지 재설치
pip install -r requirements.txt

# 4. 권한 확인
chmod +x start_ai_chat.sh
```

### 2. 검색 결과가 없음

**증상**: 문서가 있는데 검색되지 않음

**해결**:
1. 사이드바에서 `♻️ 전체재인덱싱` 클릭
2. 데이터베이스 파일 확인:
   ```bash
   ls -lh everything_index.db metadata.db
   ```
3. 파일이 없으면 재생성:
   ```bash
   python3 auto_indexer.py
   ```

### 3. AI 분석이 작동하지 않음

**증상**: "AI 모델 로드 실패" 메시지

**해결**:
1. 모델 파일 확인:
   ```bash
   ls -lh models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
   ```
2. config.py에서 경로 확인
3. GPU 메모리 확인 (NVIDIA만):
   ```bash
   nvidia-smi
   ```

### 4. 성능이 느림

**증상**: 검색이나 응답이 너무 느림

**해결**:
1. 로그 확인:
   ```bash
   tail -50 logs/performance.log
   ```
2. 캐시 정리:
   ```bash
   rm -rf rag_system/cache/*
   ```
3. DB 최적화:
   ```bash
   python3 rebuild_rag_indexes.py
   ```

### 5. 메모리 부족

**증상**: MemoryError 또는 시스템 응답 없음

**해결**:
1. 실행 중인 프로세스 확인:
   ```bash
   ps aux | grep python | grep streamlit
   ```
2. 중복 실행 종료:
   ```bash
   pkill -f streamlit
   ```
3. config.py 설정 조정:
   ```python
   MAX_DOCUMENTS_TO_PROCESS = 10  # 기본 20에서 줄이기
   N_CTX = 8192  # 기본 16384에서 줄이기
   ```

---

## 성능 모니터링

### 실시간 모니터링

```bash
# 시스템 리소스 모니터링
htop

# GPU 모니터링 (NVIDIA)
watch -n 1 nvidia-smi

# 로그 실시간 확인
tail -f logs/performance.log
```

### 성능 통계 확인

웹 인터페이스에서:
1. 사이드바 하단의 "시스템 정보" 확인
2. 평균 응답 시간 확인
3. 캐시 효율 확인

Python에서:
```python
from modules.log_system import get_logger

logger = get_logger()
perf = logger.get_performance_summary()
print(perf)
```

---

## 유지보수 작업

### 일일 작업

- [ ] 로그 파일 확인 (`tail -50 logs/errors.log`)
- [ ] 시스템 상태 확인 (`python3 utils/system_checker.py`)

### 주간 작업

- [ ] 로그 파일 정리 (7일 이상된 파일 삭제)
- [ ] 데이터베이스 최적화 (`python3 rebuild_rag_indexes.py`)
- [ ] 새 문서 인덱싱 확인

### 월간 작업

- [ ] 전체 시스템 백업
- [ ] 성능 보고서 작성
- [ ] 설정 최적화 검토

### 수동 작업

```bash
# 로그 파일 정리 (7일 이상)
find logs/ -name "*.log.*" -mtime +7 -delete

# 캐시 정리
rm -rf rag_system/cache/*

# 임시 파일 정리
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +

# 백업 생성
tar -czf backup_$(date +%Y%m%d).tar.gz \
    everything_index.db metadata.db docs/ config.py
```

---

## 설정 관리

### 주요 설정 파일: config.py

```python
# 성능 튜닝
VECTOR_WEIGHT = 0.2          # 벡터 검색 가중치
BM25_WEIGHT = 0.8            # BM25 검색 가중치
MAX_TOKENS = 512             # AI 응답 최대 토큰
N_CTX = 16384                # 컨텍스트 크기

# GPU 설정
N_GPU_LAYERS = -1            # -1 = 모든 레이어 GPU 사용
MAIN_GPU = 0                 # 사용할 GPU ID

# 성능 설정
PARALLEL_WORKERS = 12        # 병렬 처리 워커 수
BATCH_SIZE = 10              # 배치 크기
```

### 환경 변수로 설정 변경

```bash
# 임시 변경 (한 세션만)
export VECTOR_WEIGHT=0.3
export BM25_WEIGHT=0.7

# 영구 변경 (~/.bashrc에 추가)
echo 'export VECTOR_WEIGHT=0.3' >> ~/.bashrc
source ~/.bashrc
```

---

## 문제 발생 시 체크리스트

1. ✅ 로그 파일 확인 (`logs/errors.log`)
2. ✅ 시스템 검증 실행 (`python3 utils/system_checker.py`)
3. ✅ 프로세스 상태 확인 (`ps aux | grep streamlit`)
4. ✅ 디스크 공간 확인 (`df -h`)
5. ✅ 메모리 사용량 확인 (`free -h`)
6. ✅ 데이터베이스 파일 확인 (`ls -lh *.db`)

---

## 연락처 및 지원

- **로그 위치**: `/home/wnstn4647/AI-CHAT/logs/`
- **설정 파일**: `/home/wnstn4647/AI-CHAT/config.py`
- **GitHub Issues**: 문제 보고 및 기능 요청

---

## 변경 이력

### 2025-10-24
- 통합 로깅 시스템 구축
- 에러 처리 개선
- 시스템 검증 도구 추가
- 유지보수 가이드 작성
