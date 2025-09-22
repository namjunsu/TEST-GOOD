# AI-CHAT RAG System

## 🚀 빠른 시작 가이드

### 시스템 시작 (한 줄 실행)
```bash
./start_system.sh
```

이 명령어 하나로 모든 시스템이 자동으로 시작됩니다:
- ✅ 웹 인터페이스 (http://localhost:8501)
- ✅ 자동 문서 인덱싱
- ✅ OCR 자동 처리

### 시스템 중지
```bash
./stop_system.sh
```

### 시스템 상태 확인
```bash
./check_status.sh
```

## 📁 프로젝트 구조

```
AI-CHAT/
├── 📄 핵심 파일
│   ├── web_interface.py        # 메인 웹 인터페이스
│   ├── perfect_rag.py          # RAG 시스템 핵심
│   └── auto_indexer.py         # 자동 문서 인덱싱
│
├── 📂 docs/                    # 문서 폴더 (PDF 파일 여기에 추가)
│   ├── year_2024/              # 연도별 정리
│   ├── year_2025/              # 최신 문서
│   └── ...
│
├── 🔧 시스템 관리
│   ├── start_system.sh         # 시스템 시작
│   ├── stop_system.sh          # 시스템 중지
│   └── check_status.sh         # 상태 확인
│
└── 📚 상세 문서
    ├── OPERATION_GUIDE.md      # 운영 가이드
    └── CLAUDE.md              # 기술 문서

```

## 💡 사용 방법

### 1. 문서 추가
docs/ 폴더에 PDF 파일을 추가하면 자동으로:
- 60초 내 자동 감지
- 텍스트 추출 (스캔 PDF는 OCR 처리)
- 검색 인덱스 업데이트

### 2. 검색하기
웹 브라우저에서 http://localhost:8501 접속 후:
- 질문 입력 (예: "2024년 구매 문서")
- AI가 관련 문서를 찾아 답변 생성

## 📞 문제 발생 시

1. **시스템 상태 확인**: `./check_status.sh`
2. **로그 확인**: `tail -f logs/web_interface.log`
3. **시스템 재시작**: `./restart_system.sh`

더 자세한 내용은 [OPERATION_GUIDE.md](OPERATION_GUIDE.md) 참조