# 📂 프로젝트 구조 및 파일 분류
> 최종 업데이트: 2025-09-28

## ✅ **현재 사용 중인 파일 (Core Files)**

### 🎯 메인 시스템
| 파일명 | 용도 | 상태 |
|--------|------|------|
| `web_interface.py` | Streamlit 웹 인터페이스 | ✅ 활성 |
| `perfect_rag.py` | RAG 시스템 (Everything 통합) | ✅ 활성 |
| `everything_like_search.py` | 초고속 검색 엔진 | 🆕 신규 |
| `auto_indexer.py` | 자동 인덱싱 시스템 | ✅ 활성 |

### 🔧 유틸리티
| 파일명 | 용도 | 상태 |
|--------|------|------|
| `config.py` | 시스템 설정 | ✅ 활성 |
| `log_system.py` | 로깅 시스템 | ✅ 활성 |
| `response_formatter.py` | 응답 포매팅 | ✅ 활성 |
| `metadata_db.py` | 메타데이터 DB | ✅ 활성 |

### 📁 디렉토리
```
rag_system/               # RAG 시스템 모듈
├── qwen_llm.py          # LLM 인터페이스
├── hybrid_search.py     # 하이브리드 검색
├── bm25_store.py        # BM25 검색
├── korean_vector_store.py # 한국어 벡터 저장소
└── ...

docs/                    # 문서 저장소 (480개 PDF)
models/                  # AI 모델
logs/                    # 로그 파일
config/                  # 설정 파일
```

## 🗂️ **보관된 파일 (Archived)**

### 📅 2025-09-28 작업
```
archive/2025-09-28_everything_search/
└── analyze_documents.py         # 812개 PDF 분석 스크립트

archive/old_rag_attempts/        # 실패한 RAG 시도들
├── real_rag_indexer.py
├── real_rag_searcher.py
├── rebuild_rag_index.py
└── test_existing_rag.py

archive/test_files_28/           # 테스트 파일들
├── test_dvr_fix.py
├── test_generic_search.py
├── test_content_search.py
├── test_everything_integration.py
└── final_integration_test.py
```

### 📅 이전 작업들
```
archive/test_files/              # 기존 테스트 파일들
archive/old_docs/                # 구 문서들
```

## 🗑️ **삭제 예정 (Deprecated)**

| 파일명 | 이유 | 대체 |
|--------|------|------|
| `content_search.py` | 기능 중복 | `everything_like_search.py` |
| `index_builder.py` | 기능 중복 | `everything_like_search.py` |
| `multi_doc_search.py` | 기능 중복 | `everything_like_search.py` |

## 📊 **시스템 성능**

### Everything-like 검색 성능
- **인덱싱**: 480개 파일 → 0.02초
- **검색**: 0.3-0.5ms (밀리초)
- **메모리**: On-demand PDF 추출로 효율화

### 검색 결과
| 쿼리 | 이전 | 현재 | 개선 |
|------|------|------|------|
| DVR 관련 | 1개 | 3개+ | 300% |
| 2020년 구매 | 0개 | 20개 | ✅ |
| 중계차 수리 | 0개 | 20개 | ✅ |

## 📝 **데이터베이스 파일**

| 파일 | 용도 |
|------|------|
| `everything_index.db` | SQLite 검색 인덱스 |
| `config/metadata.db` | 메타데이터 DB |
| `rag_system/db/*` | RAG 시스템 DB |

## 🔧 **환경 설정**

| 파일 | 용도 |
|------|------|
| `.env` | 환경 변수 |
| `requirements_updated.txt` | Python 패키지 |
| `.streamlit/` | Streamlit 설정 |

## 📋 **문서**

| 파일 | 내용 |
|------|------|
| `WORK_LOG_2025-09-28.md` | 오늘 작업 로그 |
| `PROJECT_STRUCTURE.md` | 이 파일 |
| `RAG_SYSTEM_REDESIGN.md` | RAG 재설계 문서 |

## 💡 **사용 방법**

```bash
# 웹 인터페이스 실행
streamlit run web_interface.py

# 테스트
python3 everything_like_search.py
```

---
*이 문서는 프로젝트 구조를 명확히 하고 파일 관리를 체계화하기 위해 작성되었습니다.*