# 🤖 Channel A MEDIATECH RAG System

방송국 기술관리팀 문서 검색 및 AI 질의응답 시스템

## 📁 프로젝트 구조

```
AI-CHAT/
├── 🌐 web_interface.py              # Streamlit 웹 UI (메인)
├── 🤖 hybrid_chat_rag_v2.py         # 통합 RAG (자동 모드 선택)
├── ⚡ quick_fix_rag.py              # 빠른 검색 엔진
├── 📄 perfect_rag.py                # 완전 RAG 시스템
├── 🔍 everything_like_search.py    # SQLite 기반 초고속 검색
├── ⚙️ config.py                     # 시스템 설정
│
├── 📦 modules/                      # 핵심 모듈
│   ├── search_module.py            # 검색 기능 (OCR 캐시 통합)
│   ├── metadata_db.py              # 메타데이터 DB
│   ├── metadata_extractor.py       # 문서 메타데이터 추출
│   └── cache_module.py             # 캐싱 시스템
│
├── 🧠 rag_system/                   # RAG 핵심 로직
│   └── qwen_llm.py                 # Qwen 2.5 LLM 통합
│
├── 📚 docs/                         # PDF 문서 (812개)
│   ├── year_2018/
│   ├── year_2019/
│   ├── ...
│   └── year_2025/
│
├── 💾 config/                       # 설정 및 DB
│   ├── metadata.db                 # 문서 메타데이터
│   └── everything_index.db         # 검색 인덱스
│
└── 🗂️ unused_files/                # 백업/구버전 보관
    ├── web_backups/                # 구 웹 인터페이스
    ├── tests/                      # 테스트 스크립트
    └── old_scripts/                # 사용 안하는 스크립트
```

## 🚀 빠른 시작

### 1. 웹 인터페이스 실행
```bash
# 가상환경 활성화
source venv/bin/activate

# Streamlit 실행
streamlit run web_interface.py
```

### 2. 또는 간단한 스크립트로
```bash
./start_ai_chat.sh
```

## 🎯 주요 기능

### 1️⃣ **자동 모드 선택**
- 간단한 질문 → 빠른 검색 (0.5초)
- 복잡한 질문 → AI 분석 (30-90초)
- 키워드 기반 자동 판단

### 2️⃣ **이미지 기반 PDF 지원**
- OCR 캐시 통합 (.ocr_cache.json)
- pdfplumber 실패시 자동 폴백
- 최대 5페이지, 5000자 추출

### 3️⃣ **실무 정보 추출**
- 금액, 업체명, 장비명, 모델명
- 날짜, 기안자, 카테고리
- 표 형식 정리

### 4️⃣ **웹 기반 UI**
- Channel A 브랜드 디자인
- AI 채팅 (메인 화면)
- 문서 검색 (사이드바)
- 연도별/월별/카테고리별 필터

## ⚡ 성능

- **시작 시간**: ~3초 (Everything 검색 초기화)
- **문서 수**: 812개 PDF (2018-2025)
- **검색 속도**: 0.3-0.5초 (빠른 검색)
- **AI 분석**: 30-90초 (Qwen 2.5 7B)
- **메모리 사용**: ~4GB (LLM 로드시)

## 📊 검색 모드 비교

| 모드 | 속도 | 정확도 | 사용 케이스 |
|------|------|--------|------------|
| 빠른 검색 | ⚡ 0.5초 | ⭐⭐⭐ | 파일명, 날짜, 간단 조회 |
| AI 분석 | 🐌 30-90초 | ⭐⭐⭐⭐⭐ | 요약, 비교, 상세 분석 |

## 🔧 기술 스택

- **프론트엔드**: Streamlit
- **검색 엔진**: SQLite FTS5
- **LLM**: Qwen 2.5 7B (llama.cpp)
- **OCR**: Tesseract (캐시 사용)
- **메타데이터**: pdfplumber
- **DB**: SQLite

## 🛠️ 주요 파일 설명

| 파일 | 설명 |
|------|------|
| `web_interface.py` | 메인 웹 UI (Streamlit) |
| `hybrid_chat_rag_v2.py` | 통합 RAG 시스템 (자동 모드) |
| `quick_fix_rag.py` | 빠른 검색 (0.5초) |
| `perfect_rag.py` | 완전 RAG (전체 기능) |
| `everything_like_search.py` | SQLite 기반 초고속 검색 |
| `modules/search_module.py` | 검색 + OCR 캐시 통합 |
| `rag_system/qwen_llm.py` | Qwen LLM 통합 |

## 📝 최근 개선 사항

### v1.3 (2025-10-08)
- ✅ OCR 캐시 통합 - 이미지 기반 PDF 지원
- ✅ 전체 텍스트 추출 (5페이지, 5000자)
- ✅ AI 환각 방지 프롬프트 개선
- ✅ 자동 모드 선택 (빠른/AI 자동)
- ✅ 프로젝트 파일 정리 (14개 → 8개)

### v1.2 (2025-09-29)
- ✅ UI 재구조화 (AI 채팅 메인화면)
- ✅ 중복 코드 제거
- ✅ 응답 품질 개선 (실무 정보 포함)

## 🤝 기여

문제 발견시 Issue를 생성해주세요.

---

**Powered by Qwen 2.5 7B & Claude Code**
