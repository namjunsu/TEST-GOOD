# AI-CHAT 실행 흐름 가이드

## `bash start_ai_chat.sh` 실행 시 호출되는 파일들

---

## 📊 전체 실행 흐름도

```
bash start_ai_chat.sh
    │
    ├─► 1. 시스템 검증
    │   └─► utils/system_checker.py
    │       ├─► config.py (설정 검증)
    │       └─► 디렉토리/파일 체크
    │
    ├─► 2. 포트 포워딩 설정 (PowerShell)
    │
    └─► 3. Streamlit 웹 서버 시작
        └─► web_interface.py (메인 엔트리포인트)
            │
            ├─► config.py (설정 로드)
            │
            ├─► hybrid_chat_rag_v2.py (통합 RAG)
            │   │
            │   ├─► quick_fix_rag.py (빠른 검색)
            │   │   │
            │   │   ├─► modules/search_module.py
            │   │   ├─► everything_index.db (문서 DB)
            │   │   └─► metadata.db (메타데이터)
            │   │
            │   ├─► rag_system/qwen_llm.py (AI 모델)
            │   │   └─► models/*.gguf (AI 모델 파일)
            │   │
            │   └─► utils/logging_utils.py (로깅)
            │       ├─► modules/log_system.py
            │       └─► utils/error_handler.py
            │
            ├─► auto_indexer.py (자동 인덱싱)
            │   └─► everything_like_search.py
            │
            └─► 기타 유틸리티들
                ├─► utils/error_handler.py
                ├─► utils/css_loader.py
                └─► modules/*.py
```

---

## 🔢 단계별 상세 설명

### **1단계: start_ai_chat.sh**
```bash
#!/bin/bash
# 역할: 시스템 시작 및 검증 오케스트레이션
```

**실행 내용:**
- 중복 실행 체크 (`pgrep -f streamlit`)
- 가상환경 활성화 (`.venv/bin/activate`)
- 시스템 검증 실행
- 포트 포워딩 설정
- Streamlit 웹 서버 시작

**호출하는 파일:**
1. `utils/system_checker.py`
2. `web_interface.py`

---

### **2단계: utils/system_checker.py**
```python
# 역할: 시스템 상태 검증
```

**검증 항목:**
- ✅ Python 버전 (3.8 이상)
- ✅ 필수 패키지 설치 확인
- ✅ 디렉토리 구조
- ✅ 설정 파일 유효성
- ✅ 모델 파일 존재
- ✅ 데이터베이스 파일
- ✅ 파일 권한

**호출하는 파일:**
- `config.py`

**결과:**
- 성공 → 계속 진행
- 경고 → 사용자에게 알림 후 계속
- 에러 → 중단

---

### **3단계: web_interface.py** (메인 엔트리포인트)
```python
# 역할: Streamlit 웹 인터페이스
```

**주요 기능:**
- 웹 UI 렌더링
- 사용자 입력 처리
- 채팅 인터페이스
- 문서 미리보기
- 사이드바 (문서 목록)

**직접 import하는 파일:**
```python
import config                          # 설정
from hybrid_chat_rag_v2 import UnifiedRAG  # RAG 시스템
from auto_indexer import AutoIndexer   # 자동 인덱싱
```

**간접적으로 로드되는 파일:** (import 체인)
- `modules/log_system.py`
- `utils/error_handler.py`
- `utils/css_loader.py`

---

### **4단계: hybrid_chat_rag_v2.py** (통합 RAG 시스템)
```python
# 역할: 질문에 따라 빠른 검색 또는 AI 분석 선택
```

**주요 로직:**
```python
def answer(query):
    if needs_ai_analysis(query):
        return ai_answer(query)    # AI 분석
    else:
        return quick_answer(query) # 빠른 검색
```

**직접 import하는 파일:**
```python
from quick_fix_rag import QuickFixRAG           # 빠른 검색
from rag_system.qwen_llm import QwenLLM         # AI 모델
from utils.logging_utils import get_unified_logger  # 로깅
from utils.error_handler import handle_errors   # 에러 처리
import config                                   # 설정
```

---

### **5단계: quick_fix_rag.py** (빠른 검색)
```python
# 역할: 데이터베이스 기반 빠른 문서 검색
```

**직접 import하는 파일:**
```python
from modules.search_module import SearchModule
from everything_like_search import EverythingLikeSearch
import config
```

**사용하는 데이터베이스:**
- `everything_index.db` - 문서 인덱스
- `metadata.db` - 메타데이터

---

### **6단계: rag_system/qwen_llm.py** (AI 모델)
```python
# 역할: Qwen LLM 모델 로드 및 추론
```

**사용하는 파일:**
- `models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf`

**직접 import하는 파일:**
```python
from llama_cpp import Llama  # LLM 라이브러리
import config
```

---

### **7단계: modules/search_module.py** (검색 엔진)
```python
# 역할: 문서 검색 (벡터 + BM25)
```

**직접 import하는 파일:**
```python
from sentence_transformers import SentenceTransformer
from modules.metadata_db import MetadataDB
import config
```

---

### **8단계: utils/logging_utils.py** (로깅 시스템)
```python
# 역할: 통합 로깅 인터페이스
```

**직접 import하는 파일:**
```python
from modules.log_system import get_logger, ChatLogger
from utils.error_handler import ErrorHandler
```

**생성하는 로그 파일:**
- `logs/queries.log` - 질문/답변
- `logs/errors.log` - 에러
- `logs/performance.log` - 성능
- `logs/system.log` - 시스템

---

## 📁 전체 파일 목록

### 직접 실행되는 파일 (9개)

1. **start_ai_chat.sh** - 시작 스크립트
2. **utils/system_checker.py** - 시스템 검증
3. **web_interface.py** - 웹 인터페이스
4. **hybrid_chat_rag_v2.py** - 통합 RAG
5. **quick_fix_rag.py** - 빠른 검색
6. **auto_indexer.py** - 자동 인덱싱
7. **config.py** - 설정
8. **rag_system/qwen_llm.py** - AI 모델 (AI 사용 시)
9. **modules/search_module.py** - 검색 엔진

### 유틸리티 파일 (항상 로드)

10. **utils/logging_utils.py** - 로깅 래퍼
11. **utils/error_handler.py** - 에러 처리
12. **modules/log_system.py** - 로깅 시스템
13. **modules/metadata_db.py** - 메타데이터 DB

### 조건부 로드 파일

14. **everything_like_search.py** - Everything 검색
15. **rag_system/korean_vector_store.py** - 벡터 DB
16. **rag_system/hybrid_search.py** - 하이브리드 검색
17. **modules/ocr_processor.py** - OCR 처리 (스캔 문서 시)

---

## 🔍 실행 추적 방법

### 방법 1: 로그 파일 확인
```bash
tail -f logs/system.log
```

### 방법 2: Streamlit 디버그 모드
```bash
streamlit run web_interface.py --server.port 8501 --logger.level=debug
```

### 방법 3: Python 코드로 추적
```python
import sys
print("Loaded modules:")
for module in sorted(sys.modules.keys()):
    if 'AI-CHAT' in str(sys.modules[module]):
        print(f"  - {module}")
```

---

## 📊 메모리 사용량

| 파일/모듈 | 메모리 사용 | 로드 시간 |
|----------|------------|----------|
| web_interface.py | ~50MB | 1-2초 |
| hybrid_chat_rag_v2.py | ~20MB | <1초 |
| quick_fix_rag.py | ~30MB | <1초 |
| qwen_llm.py (AI 모델) | ~4GB | 5-10초 |
| search_module.py | ~100MB | 2-3초 |

**총 메모리 (AI 미사용 시)**: ~500MB
**총 메모리 (AI 사용 시)**: ~4.5GB

---

## 🚀 성능 최적화

### 느린 부분
1. **AI 모델 로드** (5-10초) - 첫 AI 질문 시에만
2. **대용량 PDF 처리** (3-5초) - 미리보기 시
3. **전체 인덱스 재구축** (30-60초) - 수동 실행 시

### 빠른 부분
1. **빠른 검색** (<0.5초)
2. **문서 목록** (<0.2초)
3. **설정 로드** (<0.1초)

---

## 🛠️ 디버깅 팁

### 특정 모듈만 테스트
```python
# hybrid_chat_rag_v2.py만 테스트
python3 hybrid_chat_rag_v2.py

# quick_fix_rag.py만 테스트
python3 quick_fix_rag.py
```

### import 에러 추적
```python
import sys
sys.path.insert(0, '/home/wnstn4647/AI-CHAT')

try:
    import hybrid_chat_rag_v2
except Exception as e:
    import traceback
    traceback.print_exc()
```

---

## 📝 요약

**bash start_ai_chat.sh 실행 시:**

1. ✅ 시스템 검증 (`utils/system_checker.py`)
2. 🚀 웹 서버 시작 (`web_interface.py`)
3. 🤖 RAG 시스템 로드 (`hybrid_chat_rag_v2.py`)
4. 🔍 검색 엔진 준비 (`quick_fix_rag.py`, `modules/search_module.py`)
5. 📊 로깅 시스템 활성화 (`utils/logging_utils.py`)
6. 🗂️ 데이터베이스 연결 (`everything_index.db`, `metadata.db`)
7. 💬 사용자 질문 대기...

**최소 실행 파일**: 약 10개
**전체 시스템**: 약 30개 파일 (모듈 포함)
