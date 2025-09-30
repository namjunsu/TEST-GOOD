# 🧹 AI-CHAT 시스템 정리 계획

## 현재 상황
- 총 15개 Python 파일이 루트에 혼재
- 실제 사용: 5개 핵심 + 4개 보조
- 미사용/중복: 6개 이상

## 정리 방안

### 1. 폴더 구조 개선
```
AI-CHAT/
├── core/                   # 핵심 모듈
│   ├── web_interface.py   # 메인 UI
│   ├── perfect_rag.py     # RAG 시스템
│   └── everything_like_search.py
│
├── utils/                  # 유틸리티
│   ├── config.py
│   ├── log_system.py
│   ├── response_formatter.py
│   └── metadata_db.py
│
├── experimental/           # 실험적 기능 (새로 만든 것들)
│   ├── ocr_processor.py
│   ├── enhanced_cache.py
│   ├── metadata_extractor.py
│   └── improved_search.py
│
├── tests/                  # 테스트
│   ├── test_performance.py
│   └── test_other_queries.py
│
├── docs/                   # PDF 문서들 (현재 위치)
├── archive/                # 보관 (이미 있음)
└── README.md              # 사용 설명서
```

### 2. 실제 사용 중인 파일만 남기기

#### 필수 파일 (그대로 유지)
- web_interface.py
- perfect_rag.py
- everything_like_search.py
- config.py
- metadata_db.py

#### 선택적 유지
- log_system.py
- response_formatter.py
- auto_indexer.py

#### 이동/삭제 대상
- improved_search.py → experimental/
- ocr_processor.py → experimental/
- enhanced_cache.py → experimental/
- metadata_extractor.py → experimental/
- quick_index.py → 삭제 (임시 스크립트)
- test_*.py → tests/

### 3. 실행 명령 단순화
```bash
# 현재
streamlit run web_interface.py

# 개선 후 (start.sh 생성)
./start.sh
```

### 4. 중복 제거
- multi_doc_search.py (삭제됨) ✓
- content_search.py (삭제됨) ✓
- index_builder.py (삭제됨) ✓

## 실행 순서

1. **백업 먼저**
   ```bash
   cp -r . ../AI-CHAT-backup-$(date +%Y%m%d)
   ```

2. **폴더 생성**
   ```bash
   mkdir -p core utils experimental tests
   ```

3. **파일 이동**
   ```bash
   # 핵심 파일
   mv perfect_rag.py everything_like_search.py core/

   # 유틸리티
   mv config.py log_system.py response_formatter.py metadata_db.py utils/

   # 실험적
   mv improved_search.py ocr_processor.py enhanced_cache.py metadata_extractor.py experimental/

   # 테스트
   mv test_*.py tests/
   ```

4. **import 경로 수정**
   - web_interface.py에서 import 경로 업데이트
   - perfect_rag.py에서 import 경로 업데이트

5. **불필요한 파일 삭제**
   ```bash
   rm quick_index.py
   rm -rf __pycache__
   ```

## 효과
- ✅ 명확한 구조
- ✅ 쉬운 유지보수
- ✅ 빠른 파일 찾기
- ✅ 깔끔한 프로젝트