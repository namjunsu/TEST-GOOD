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

### WSL2 환경에서 외부 접속 설정

WSL2를 사용하는 경우, Windows에서 포트 프록시를 설정해야 다른 PC/모바일에서 접속할 수 있습니다:

1. **WSL IP 주소 확인** (WSL 터미널에서):
```bash
ip addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'
```

2. **포트 프록시 설정** (Windows PowerShell 관리자 권한으로 실행):
```powershell
# FastAPI 포트 (7860)
netsh interface portproxy add v4tov4 listenport=7860 listenaddress=0.0.0.0 connectaddress=<WSL_IP> connectport=7860

# Streamlit 포트 (8501)
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectaddress=<WSL_IP> connectport=8501
```

3. **포트 프록시 확인**:
```powershell
netsh interface portproxy show all
```

4. **방화벽 규칙 추가** (필요시):
```powershell
New-NetFirewallRule -DisplayName "AI-CHAT FastAPI" -Direction Inbound -LocalPort 7860 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "AI-CHAT Streamlit" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
```

5. **포트 프록시 삭제** (설정 해제 시):
```powershell
netsh interface portproxy delete v4tov4 listenport=7860 listenaddress=0.0.0.0
netsh interface portproxy delete v4tov4 listenport=8501 listenaddress=0.0.0.0
```

**참고**: WSL이 재시작되면 IP가 변경될 수 있으므로, IP 변경 시 포트 프록시를 다시 설정해야 합니다.

---

## 📦 설치 및 이전 가이드

- **[🎯_신규PC_설치순서.md](🎯_신규PC_설치순서.md)** - 처음부터 설치
- **[DOCKER_사용법.md](DOCKER_사용법.md)** - Docker로 실행
- **[START_HERE.md](START_HERE.md)** - 백업 파일로 빠른 이전
- **[네트워크_접속_가이드.md](네트워크_접속_가이드.md)** - 다른 PC/모바일 접속
- **[문제해결.md](문제해결.md)** - 트러블슈팅

### 시스템 요구사항 (Ubuntu/WSL2)

OCR 기능 사용을 위한 추가 패키지:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-kor poppler-utils
```

- **tesseract-ocr**: OCR 엔진 (스캔 PDF 텍스트 인식)
- **tesseract-ocr-kor**: 한국어 언어 데이터
- **poppler-utils**: PDF → 이미지 변환

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

**파일 인덱스 재구축**:
```bash
python3 -c "
from everything_like_search import EverythingLikeSearch
search = EverythingLikeSearch()
search.index_all_files()
"
```

**메타데이터 재추출** (기안자 정보 등):
```bash
source .venv/bin/activate
python3 rebuild_metadata.py
```
- 812개 PDF에서 기안자, 날짜, 금액 등 메타데이터 추출
- metadata.db 재구축
- 기안자 검색 기능 활성화

---

## 📈 최근 업데이트 (v3.3)

### ✅ 완료된 개선사항

1. **기안자 검색 수정 + OCR 지원** (2025-10-22)
   - PDF 내용에서 기안자 정보 추출
   - metadata.db에 **327개** 문서 기안자 정보 저장
   - "남준수" 등 기안자 이름으로 검색 가능
   - PyMuPDF 설치 및 PDF 미리보기 오류 수정
   - **OCR 지원**: 스캔 PDF (163개) 텍스트 인식
   - 2014-2017년 문서에서 추가 8개 기안자 추출

2. **GPU 가속** (2025-10-22)
   - RTX 4060 활성화 → AI 답변 10배 속도 향상
   - 30-60초 → 3-6초

3. **컨텍스트 확장** (2025-10-22)
   - 8K → 32K 토큰 (4배 증가)
   - 긴 문서 완벽 처리
   - 답변 품질 대폭 향상

4. **성능 최적화** (2025-10-22)
   - CPU 스레드 최적화 (10 → 20)
   - 배치 크기 증가 (512 → 1024)
   - 자동 포트 포워딩

5. **이전 개선사항** (v2.0)
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
