# 파일 사용 현황 분석 (2025-01-18)

## ✅ 핵심 파일 (현재 사용 중)

### 필수 시스템 파일
- **web_interface.py** - 메인 Streamlit 웹 인터페이스 ⭐
- **perfect_rag.py** - RAG 시스템 핵심 엔진 ⭐
- **auto_indexer.py** - 자동 문서 인덱싱 시스템
- **config.py** - 시스템 설정 파일
- **log_system.py** - 로깅 시스템
- **response_formatter.py** - 응답 포맷팅
- **smart_search_enhancer.py** - 검색 개선 시스템

## 🔧 테스트 파일 (개발용)
- **quick_test.py** - 빠른 테스트
- **test_equipment_search.py** - 장비 검색 테스트
- **test_auto_rename.py** - 자동 이름변경 테스트
- **test_answer_quality.py**
- **test_real_quality.py**
- **test_response_quality.py**
- **test_improvements.py**
- **test_model_loading.py**
- **comprehensive_test.py**
- **quick_real_test.py**
- **real_test.py**

## 🛠️ 유틸리티 파일 (보조 기능)
- **memory_optimizer.py** - 메모리 최적화 도구
- **lazy_loader.py** - 지연 로딩 시스템
- **preload_cache.py** - 캐시 사전 구축
- **performance_optimizer.py** - 성능 최적화
- **performance_validation_test.py** - 성능 검증
- **parallel_search_optimizer.py** - 병렬 검색 최적화

## 🚫 사용하지 않는 파일 (삭제 가능)

### 레거시/중복 파일
- **advanced_cache_system.py** - 사용 안함
- **advanced_model_loader.py** - 사용 안함
- **analyze_equipment.py** - 자산 기능 제거됨
- **asset_llm_enhancer.py** - 자산 기능 제거됨
- **cache_improvements.py** - 레거시
- **document_speed_optimizer.py** - 레거시
- **enhanced_indexing_system.py** - 레거시
- **lightweight_document_manager.py** - 레거시
- **metadata_cache_manager.py** - 레거시
- **document_metadata_cache.py** - 레거시

### 초기 설정/일회성 파일
- **install_llm_model.py** - 초기 설치용
- **fix_load_documents.py** - 일회성 수정
- **fix_model_loading.py** - 일회성 수정
- **fix_symlinks.py** - 일회성 수정
- **pdf_extraction_fix.py** - 일회성 수정
- **organize_docs.py** - 완료된 작업
- **reorganize_docs.py** - 완료된 작업
- **recreate_categories.py** - 완료된 작업
- **preindex_documents.py** - 일회성 작업

### 기타 미사용 파일
- **improve_answer_generation.py** - 레거시
- **simple_improvements.py** - 레거시
- **optimize_perfect_rag.py** - 레거시
- **improved_sidebar.py** - 레거시
- **simple_sidebar.py** - 레거시
- **config_manager.py** - 사용 안함
- **error_handler.py** - 사용 안함
- **pdf_parallel_processor.py** - 사용 안함

## 📦 정리 계획

### 1단계: 즉시 삭제 가능 (30개 파일)
- 모든 레거시/일회성 파일
- 자산 관련 파일 (asset_*, analyze_equipment.py)
- fix_* 파일들
- 중복 기능 파일

### 2단계: archive 폴더로 이동 (12개 파일)
- 테스트 파일들 (test_*.py)
- comprehensive_test.py, real_test.py 등

### 최종 구조 (필수 파일만)
```
AI-CHAT/
├── web_interface.py        # 메인 웹 UI
├── perfect_rag.py          # RAG 엔진
├── auto_indexer.py         # 자동 인덱싱
├── config.py              # 설정
├── log_system.py          # 로깅
├── response_formatter.py   # 포매팅
├── smart_search_enhancer.py # 검색 개선
├── rag_system/            # RAG 모듈
├── docs/                  # 문서
└── archive/               # 보관 파일
    └── test_files/        # 테스트 파일
```