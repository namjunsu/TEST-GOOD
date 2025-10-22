# AI-CHAT RAG 프로젝트 구조

> **최종 업데이트**: 2025-10-15
> **정리 완료**: 레거시 코드 제거, 테스트 파일 이동, 캐시 정리

---

## 📁 프로젝트 루트 디렉토리

### 🔧 **핵심 실행 파일**
```
web_interface.py        (69K)  - Streamlit 웹 인터페이스 (메인)
hybrid_chat_rag_v2.py   (12K)  - 통합 RAG 시스템 (AI 자동 선택)
quick_fix_rag.py        (4.7K) - 빠른 검색 전용 RAG
config.py               (9.5K) - 설정 파일
```

### 📚 **시스템 모듈**
```
auto_indexer.py         (21K)  - 자동 문서 인덱싱 시스템
everything_like_search. (16K)  - 초고속 파일 검색 엔진
```

### 📊 **데이터베이스 파일**
```
everything_index.db     (3.6M) - 문서 인덱스 메인 DB
metadata.db             (48K)  - 메타데이터 저장소
```

### 🎨 **로고 & 이미지**
```
channel_a_logo_inverted.png (35K)
logo_inverted.png          (33K)
```

---

## 📂 주요 폴더 구조

### **modules/** - 핵심 모듈
```
modules/
├── search_module.py      - 검색 기능 통합
├── llm_module.py         - LLM 통합
├── metadata_db.py        - 메타데이터 DB 관리
├── metadata_extractor.py - PDF 메타데이터 추출
├── ocr_processor.py      - OCR 처리
├── document_module.py    - 문서 처리
├── intent_module.py      - 질문 의도 분석
├── cache_module.py       - 캐싱 시스템
├── statistics_module.py  - 통계 생성
├── response_formatter.py - 응답 포맷팅
└── log_system.py         - 로깅 시스템
```

### **rag_system/** - RAG 하위 시스템
```
rag_system/
├── qwen_llm.py            - Qwen LLM 래퍼
├── llm_singleton.py       - LLM 싱글톤 관리
├── korean_vector_store.py - 한글 벡터 스토어
├── korean_reranker.py     - 한글 리랭커
├── bm25_store.py          - BM25 검색
├── hybrid_search.py       - 하이브리드 검색
├── query_expansion.py     - 쿼리 확장
├── query_optimizer.py     - 쿼리 최적화
├── multilevel_filter.py   - 다단계 필터링
├── document_compression.py - 문서 압축
├── enhanced_ocr_processor.py - 향상된 OCR
└── metadata_extractor.py  - 메타데이터 추출
```

### **docs/** - 문서 저장소
```
docs/
├── category_purchase/    - 구매 문서 (332개 PDF)
├── category_repair/      - 수리 문서
├── category_consumables/ - 소모품 문서
├── category_disposal/    - 폐기 문서
└── .ocr_cache.json       - OCR 캐시 (284K)
```

### **models/** - AI 모델 저장소
```
models/
├── Llama-3-Gukbap-8B/    - 한국어 LLM (2.7GB)
└── Qwen2.5-7B-Instruct/  - Qwen LLM (5.2GB)
```

### **cache/** - 벡터 인덱스 캐시
```
cache/  (4.0K - 거의 비어있음)
```

### **ocr_cache/** - OCR 결과 캐시
```
ocr_cache/  (284K - 667개 문서 캐시됨)
```

### **logs/** - 로그 파일
```
logs/  (68K - 7일 이상 된 로그 자동 삭제됨)
```

### **indexes/** - 검색 인덱스
```
indexes/  (벡터 인덱스 저장소)
```

### **monitoring/** - 모니터링 데이터
```
monitoring/  (시스템 모니터링)
```

---

## 🗂️ 아카이브된 파일

### **archived/** - 더 이상 사용하지 않는 파일
```
archived/
├── test_ai_answer.py
├── test_system.py
├── test_adaptive_cot.py
├── test_table_extraction.py
├── test_table_integration.py
├── system_analysis.py
├── build_cache.py
└── clean_duplicates.py
```

### **unused_files/** - 레거시 코드 (1.3M)
```
unused_files/
├── benchmarks/          - 성능 벤치마크
├── old_scripts/         - 구버전 스크립트
├── old_utils/           - 구버전 유틸리티
├── tests/               - 구버전 테스트 (23개 파일)
├── utils/               - 구버전 유틸
├── web_backups/         - 웹 인터페이스 백업 (7개 버전)
├── perfect_rag.py       - 구버전 RAG
└── quick_fix_rag_old.py - 구버전 QuickFix
```

---

## 📖 문서 파일

### **설치 & 설정 가이드**
```
START_HERE.md           (1.7K)  - 빠른 시작 가이드
README.md               (3.7K)  - 프로젝트 소개
SETUP_NEW_PC.sh         (6.5K)  - 신규 PC 자동 설치 스크립트
새PC_완벽설치.md        (11K)   - 완벽 설치 가이드
🎯_신규PC_설치순서.md    (8.3K)  - 설치 순서 가이드
WSL_설치_가이드.md      (8.6K)  - WSL 설치 가이드
```

### **운영 가이드**
```
네트워크_접속_가이드.md  (6.3K)  - 네트워크 접속 방법
문제해결.md             (1.4K)  - 트러블슈팅
FOLDER_GUIDE.md         (2.5K)  - 폴더 구조 설명
QUALITY_STATUS.md       (4.5K)  - 품질 상태
```

### **실행 스크립트**
```
start_ai_chat.sh        (1.6K)  - AI 채팅 시작
QUICK_MIGRATION.sh      (1.9K)  - 빠른 마이그레이션
```

### **설치 스크립트 (Windows→WSL)**
```
1_WSL_설치.ps1          (3.9K)  - PowerShell WSL 설치
2_WSL_환경설정.sh        (4.3K)  - WSL 환경 설정
3_프로젝트_설치.sh       (4.9K)  - 프로젝트 설치
```

---

## 🎯 주요 개선사항 (2025-10-15)

### ✅ **완료된 작업**
1. ✅ `web_interface.py`에서 레거시 코드 260줄 삭제
2. ✅ 테스트 파일 5개를 `archived/` 폴더로 이동
3. ✅ 불필요한 캐시 폴더 삭제 (`.cache`, `.pids`)
4. ✅ 7일 이상 된 로그 파일 자동 삭제
5. ✅ 프로젝트 구조 문서화 (본 파일)

### 📦 **절약된 공간**
- `.cache` 삭제: 40K
- `.pids` 삭제: 16K
- 레거시 코드: 260줄 (8K 추정)
- **총 절약**: ~64K + 코드 간소화

### 🎨 **개선된 폴더 구조**
- 루트 디렉토리 정리: 69개 → 30개 파일
- 테스트 파일 분리: 개발용과 실행용 명확히 구분
- 아카이브 체계화: 안 쓰는 파일 백업 보관

---

## 🚀 빠른 시작

### **1. 웹 인터페이스 실행**
```bash
streamlit run web_interface.py --server.port 8501
```

### **2. 네트워크 접속**
- 이 PC: `http://localhost:8501`
- 다른 PC: `http://172.31.188.45:8501`

### **3. 자동 인덱싱**
- 60초마다 자동으로 새 파일 감지
- 수동 재인덱싱: 웹 UI에서 "새로고침" 버튼

---

## 📌 참고사항

### **주의사항**
- `unused_files/` 폴더는 삭제하지 마세요 (백업용)
- `archived/` 폴더도 보관 (필요시 복원)
- DB 파일 (`*.db`)는 절대 수동 수정 금지

### **시스템 요구사항**
- Python 3.12+
- WSL2 (Ubuntu 22.04+)
- 8GB RAM 이상 권장
- 20GB 이상 저장 공간

### **주요 의존성**
- Streamlit
- PyMuPDF (PDF 처리)
- llama-cpp-python (LLM)
- pdfplumber (PDF 텍스트 추출)
- Tesseract OCR (이미지 문서)

---

## 🔍 추가 정보

더 자세한 내용은 다음 문서를 참고하세요:
- [START_HERE.md](START_HERE.md) - 빠른 시작
- [README.md](README.md) - 프로젝트 소개
- [네트워크_접속_가이드.md](네트워크_접속_가이드.md) - 네트워크 설정
- [문제해결.md](문제해결.md) - 트러블슈팅
