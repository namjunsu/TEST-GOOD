# AI-CHAT 시스템 맵 (2025-09-30)

## 🎯 시스템 목적
한국어 문서(PDF/TXT) 검색 및 질의응답 RAG 시스템

## 📊 현재 상태
- **문서**: 480개 PDF 파일 (docs/ 폴더)
- **모델**: Qwen 2.5 7B
- **인터페이스**: Streamlit 웹 UI

## 🏗 시스템 구조

### 1. 핵심 실행 파일
```
perfect_rag.py (2004줄) - 메인 RAG 엔진
├── 6개 핵심 모듈 통합
├── 문서 검색/응답 처리
└── 메타데이터 캐싱

web_interface.py - Streamlit 웹 UI
├── 채팅 인터페이스
├── 문서 검색 UI
└── 통계 대시보드
```

### 2. 핵심 모듈 (Phase 13 리팩토링 결과)
```
search_module.py - 검색 엔진
├── 콘텐츠 기반 검색
├── 메타데이터 검색
└── Everything-like 파일 검색

document_module.py - 문서 처리
├── PDF 텍스트 추출
├── OCR 처리
└── 컨텍스트 최적화

llm_module.py - LLM 핸들러
├── Qwen 모델 관리
├── 프롬프트 생성
└── 응답 생성

cache_module.py - 캐시 관리
├── LRU 캐시
├── TTL 관리
└── 디스크 저장

statistics_module.py - 통계/보고서
├── 연도별/월별 통계
├── 카테고리 분석
└── 리포트 생성

intent_module.py - 의도 분석
├── 사용자 의도 파악
├── 쿼리 분류
└── 응답 전략 결정
```

### 3. 지원 모듈
```
metadata_extractor.py - PDF 메타데이터 추출
metadata_db.py - SQLite 메타데이터 DB
everything_like_search.py - 파일 시스템 검색
config.py - 시스템 설정
```

### 4. 조건부/선택적 모듈
```
auto_indexer.py - 자동 인덱싱 (web_interface에서 사용)
enhanced_cache.py - 고급 캐싱 (옵션)
response_formatter.py - 응답 포맷팅
ocr_processor.py - OCR 처리 (스캔 문서용)
log_system.py - 로깅 시스템
```

## 🔄 실행 흐름

1. **초기화**
   - PerfectRAG 인스턴스 생성
   - 6개 핵심 모듈 로드
   - 메타데이터 캐시 구축 (480개 PDF)

2. **질의 처리**
   ```
   사용자 질문 → intent_module (의도 분석)
                → search_module (문서 검색)
                → document_module (텍스트 추출)
                → llm_module (응답 생성)
                → cache_module (결과 캐싱)
   ```

3. **웹 인터페이스**
   - Streamlit 서버 실행
   - 채팅/검색 UI 제공
   - 실시간 응답 스트리밍

## 📂 디렉토리 구조
```
AI-CHAT/
├── docs/          # PDF 문서 (480개)
├── config/        # 설정 및 메타데이터 DB
├── cache/         # 캐시 데이터
├── models/        # Qwen 2.5 모델
├── logs/          # 시스템 로그
├── tests/         # 테스트 파일
└── rag_system/    # RAG 시스템 코어
```

## 🚀 실행 방법
```bash
# RAG 시스템 직접 실행
python3 perfect_rag.py

# 웹 인터페이스 실행
streamlit run web_interface.py

# 또는 스크립트 사용
./start_ai_chat.sh
```

## ✅ 필수 파일
1. perfect_rag.py
2. web_interface.py
3. 6개 핵심 모듈 (search, document, llm, cache, statistics, intent)
4. metadata_extractor.py
5. metadata_db.py
6. everything_like_search.py
7. config.py

## ⚠️ 선택적 파일
- auto_indexer.py (웹 UI에서 사용)
- enhanced_cache.py (고급 기능)
- response_formatter.py (포맷팅)
- ocr_processor.py (OCR 필요시)
- log_system.py (로깅)

## 🗑 삭제 가능
- cleanup_system.py (독립 스크립트)

---
마지막 업데이트: 2025-09-30