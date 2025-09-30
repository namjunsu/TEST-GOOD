# 🤖 AI-CHAT RAG System

고성능 PDF 문서 검색 및 질의응답 시스템

## 📁 프로젝트 구조

```
AI-CHAT/
├── 📄 perfect_rag.py         # 메인 RAG 시스템
├── 🌐 web_interface.py       # Streamlit 웹 UI
├── 🔍 everything_like_search.py  # 고속 검색 엔진
├── ⚙️ config.py              # 시스템 설정
├── 📦 modules/               # 핵심 모듈들
│   ├── metadata_db.py
│   ├── cache_module.py
│   ├── llm_module.py
│   └── ...
├── 🧪 tests/                 # 테스트 파일
├── 🛠️ utils/                 # 유틸리티
│   ├── build_cache.py
│   └── fast_init.py
├── 📚 docs/                  # PDF 문서 (480개)
└── 📂 config/                # 설정 파일
    ├── performance.yaml
    └── cache/
```

## 🚀 빠른 시작

### 1. 초기 설정
```bash
# 가상환경 활성화
source venv/bin/activate

# 빠른 캐시 구축 (처음 한 번만)
python3 fast_init.py
```

### 2. 웹 인터페이스 실행
```bash
streamlit run web_interface.py
```

### 3. 시스템 테스트
```bash
python3 tests/simple_test.py
```

## ⚡ 성능

- **시작 시간**: 2.35초 (캐시 사용시)
- **문서 수**: 480개 PDF
- **응답 속도**: 평균 3-5초
- **메모리 사용**: ~2GB

## 🔧 주요 기능

- ✅ PDF 문서 자동 인덱싱
- ✅ 한국어 질의응답
- ✅ 멀티모달 검색 (텍스트 + 메타데이터)
- ✅ 웹 기반 UI
- ✅ 캐싱 시스템
- ✅ GPU 가속 지원

## 📝 설정

`config/performance.yaml`에서 성능 튜닝 가능:
- 병렬 처리 워커 수
- 캐시 크기
- GPU 사용 여부

## 🤝 기여

문제 발견시 Issue를 생성해주세요.

---
*Powered by Qwen 2.5 7B & Claude Code*