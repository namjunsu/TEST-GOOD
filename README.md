# 🌐 Channel A MEDIATECH RAG 시스템

> 채널A 미디어텍 기술관리팀 문서 검색 및 AI 답변 시스템

---

## 📋 프로젝트 정보

- **문서 개수**: 812개 PDF (2014-2025)
- **총 크기**: 235 MB
- **AI 모델**: Qwen2.5-7B-Instruct (로컬 LLM)
- **검색 방식**: Everything-like 검색 + 메타데이터
- **환경**: Python 3.12 + WSL2
- **GPU**: RTX 4060 8GB (활성화됨)

---

## 🚀 시작하기

### 방법 1: Docker로 실행 (추천)
```bash
docker-compose up -d
```

**브라우저 접속**: `http://localhost:8501`

🐳 **상세 가이드**: [DOCKER_사용법.md](DOCKER_사용법.md)

### 방법 2: 직접 실행 (권장)
```bash
bash start_ai_chat.sh
```

**브라우저 접속**:
- 이 PC에서: `http://localhost:8501`
- 다른 PC/모바일: 스크립트 실행 시 자동으로 IP 주소 표시됨

📱 **네트워크 접속 상세**: [네트워크_접속_가이드.md](네트워크_접속_가이드.md)

---

## 📦 설치 및 이전 가이드

- **[🎯_신규PC_설치순서.md](🎯_신규PC_설치순서.md)** - 처음부터 설치
- **[DOCKER_사용법.md](DOCKER_사용법.md)** - Docker로 실행
- **[START_HERE.md](START_HERE.md)** - 백업 파일로 빠른 이전
- **[네트워크_접속_가이드.md](네트워크_접속_가이드.md)** - 다른 PC/모바일 접속
- **[문제해결.md](문제해결.md)** - 트러블슈팅

---

## 🎯 주요 기능

### 1. 빠른 검색
- Everything-like 검색 (0.9초)
- 파일명, 내용, 날짜, 카테고리 검색
- 기안자 검색

### 2. AI 답변
- LLM 기반 상세 답변
- Chain-of-Thought 추론
- 표 구조 보존
- 출처 명시

### 3. 문서 관리
- 812개 PDF 자동 인덱싱
- OCR 캐시 (자동 생성)
- 메타데이터 추출 (날짜, 카테고리, 기안자)

---

## 📂 폴더 구조

```
AI-CHAT/
├── web_interface.py          # 웹 UI (메인)
├── hybrid_chat_rag_v2.py     # AI 답변 생성
├── quick_fix_rag.py          # 빠른 검색
├── config.py                 # 설정
├── modules/                  # 핵심 모듈
│   ├── search_module.py      # 검색
│   ├── metadata_db.py        # 메타데이터
│   └── metadata_extractor.py # 추출
├── docs/                     # PDF 문서 (234 MB)
├── everything_index.db       # 검색 인덱스
├── metadata.db              # 메타데이터
└── .env.production          # 환경 변수
```

---

## 🔧 개발자 정보

### 테스트
```bash
# 시스템 테스트
python3 test_system.py

# AI 답변 테스트
python3 test_ai_answer.py
```

### 재인덱싱
```bash
python3 -c "
from everything_like_search import EverythingLikeSearch
search = EverythingLikeSearch()
search.index_all_files()
"
```

---

## 📈 최근 업데이트 (v3.0)

### ✅ 완료된 개선사항

1. **GPU 가속** (2025-10-22)
   - RTX 4060 활성화 → AI 답변 10배 속도 향상
   - 30-60초 → 3-6초

2. **컨텍스트 확장** (2025-10-22)
   - 8K → 32K 토큰 (4배 증가)
   - 긴 문서 완벽 처리
   - 답변 품질 대폭 향상

3. **성능 최적화** (2025-10-22)
   - CPU 스레드 최적화 (10 → 20)
   - 배치 크기 증가 (512 → 1024)
   - 자동 포트 포워딩

4. **이전 개선사항** (v2.0)
   - Chain-of-Thought 프롬프트
   - 표 구조 보존
   - 812개 PDF 자동 인덱싱

---

## 💡 팁

### 빠른 검색 vs AI 답변
- **빠른 검색**: 단순 키워드 (0.9초)
- **AI 답변**: 복잡한 질문, 분석 (3-6초, GPU 가속)

### 성능 최적화
- 첫 실행: GPU 모델 로딩 (약 10초)
- 이후 실행: GPU 가속으로 빠른 답변
- 32K 컨텍스트: 긴 문서 완벽 처리

### 문제 발생시
[문제해결.md](문제해결.md) 참고

---

## 📞 지원

- **문서 이전**: [START_HERE.md](START_HERE.md)
- **문제 해결**: [문제해결.md](문제해결.md)
- **상세 가이드**: `unused_files/` 폴더 참고

---

**버전**: 3.0 (2025-10-22)
**환경**: WSL2 + Python 3.12 + RTX 4060
**GPU 가속 + 답변 품질 우선** ✅
