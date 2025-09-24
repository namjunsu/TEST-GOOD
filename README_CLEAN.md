# 🎯 AI-CHAT RAG 시스템

## 📁 깔끔한 프로젝트 구조

### ✅ 핵심 파일 (꼭 필요한 것만)
```
AI-CHAT/
├── 🎯 web_interface.py       # 메인 웹 인터페이스
├── 🔧 perfect_rag.py         # RAG 검색 엔진
├── 📊 auto_indexer.py        # 자동 인덱싱
├── ⚙️  config.py              # 설정 파일
├── 📝 log_system.py          # 로깅
├── 🎨 response_formatter.py  # 응답 포맷
└── 🔍 smart_search_enhancer.py # 검색 개선
```

### 📂 폴더 구조
```
├── docs/               # PDF 문서들 (1000+개)
├── rag_system/         # RAG 모듈들
├── models/             # AI 모델 파일
├── logs/              # 로그 파일
├── archive/           # 보관된 파일들
│   ├── backups/       # 백업
│   ├── test_scripts/  # 테스트
│   ├── improvements/  # 개선 시도
│   └── docs/         # 오래된 문서
└── config/           # 설정 파일
```

## 🚀 실행 방법

### 1️⃣ 웹 인터페이스 실행
```bash
streamlit run web_interface.py
```
브라우저에서 http://localhost:8501 접속

### 2️⃣ Docker로 실행 (권장)
```bash
docker compose up
```

## 💡 주요 기능

### 현재 작동하는 기능:
- ✅ **PDF 문서 검색** - 1000개+ PDF 검색
- ✅ **하이브리드 검색** - BM25 + Vector 결합
- ✅ **Qwen2.5 LLM** - 한국어 최적화
- ✅ **자동 인덱싱** - 60초마다 새 문서 감지
- ✅ **스마트 캐싱** - 빠른 응답

### 제거된 기능:
- ❌ Asset/장비 검색 (제거됨)
- ❌ 복잡한 추가 시스템들

## 📊 시스템 상태

- **문서**: 480개 고유 PDF
- **초기 로딩**: 2-3분 (첫 실행 시)
- **이후 로딩**: 1-2초 (캐시 사용)
- **코드 크기**: 4,852줄 (최적화됨)

## 🔧 문제 해결

### 오류 발생 시:
1. Docker 재시작: `docker compose restart`
2. 브라우저 새로고침: F5
3. 캐시 클리어: 사이드바에서 "캐시 초기화"

## 📝 파일 설명

| 파일 | 용도 | 필수 |
|-----|------|-----|
| web_interface.py | 웹 UI | ✅ |
| perfect_rag.py | 검색 엔진 | ✅ |
| auto_indexer.py | 자동 인덱싱 | ✅ |
| config.py | 설정 | ✅ |
| log_system.py | 로깅 | ✅ |
| response_formatter.py | 포맷팅 | ✅ |
| smart_search_enhancer.py | 검색 개선 | ✅ |

## 🎯 간단 요약

**이 시스템은 PDF 문서를 검색하고 AI로 답변하는 RAG 시스템입니다.**

- 복잡한 기능 제거 ✅
- 핵심 기능만 유지 ✅
- 안정적 작동 보장 ✅

---
*최종 업데이트: 2025-01-24*