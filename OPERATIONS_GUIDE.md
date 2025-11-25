# AI-CHAT 시스템 운영 가이드

이 문서는 AI-CHAT 문서 검색 시스템의 일상 운영을 위한 가이드입니다.

## 목차

1. [시스템 개요](#시스템-개요)
2. [일상 운영](#일상-운영)
3. [문제 해결](#문제-해결)
4. [유지보수 스크립트](#유지보수-스크립트)
5. [주의사항](#주의사항)
6. [모델 업그레이드](#모델-업그레이드)
7. [서버 마이그레이션](#서버-마이그레이션)

---

## 시스템 개요

### 구성 요소
- **웹 서버**: Streamlit (프론트엔드) + Uvicorn (백엔드 API)
- **데이터베이스**: SQLite (`metadata.db`)
- **문서 저장소**: `docs/year_YYYY/` 폴더
- **검색 엔진**: FAISS (벡터 검색) + BM25 (키워드 검색)

### 주요 디렉토리
```
/home/wnstn4647/AI-CHAT/
├── docs/
│   ├── incoming/         # 신규 문서 업로드 폴더
│   ├── year_2014~/       # 연도별 문서 저장소
│   └── rejected/         # 처리 실패 문서
├── scripts/              # 유지보수 스크립트
├── metadata.db           # 문서 메타데이터 DB
└── .venv/                # Python 가상환경
```

---

## 일상 운영

### 1. 시스템 시작

```bash
bash start_ai_chat.sh
```

서버가 정상적으로 시작되면 다음 URL에서 접속 가능:
- Streamlit UI: http://localhost:8501
- API: http://localhost:8000

### 2. 신규 문서 추가

**방법 1: incoming 폴더 사용 (권장)**
```bash
# 1. PDF 파일을 incoming 폴더에 복사
cp /path/to/new_document.pdf docs/incoming/

# 2. 인제스트 스크립트 실행
.venv/bin/python scripts/core/ingest_from_docs.py

# 3. 필요시 인덱스 재구축
.venv/bin/python scripts/quick_rebuild_bm25.py
```

**방법 2: OCR이 필요한 이미지 PDF**
```bash
# OCR 모드로 처리
.venv/bin/python scripts/core/ingest_from_docs.py --ocr-mode force
```

### 3. 일일 헬스체크 (매일 1회 권장)

```bash
.venv/bin/python scripts/ops/healthcheck.py
```

이 스크립트는 다음을 체크합니다:
- DB 연결 상태
- 파일시스템-DB 동기화
- 디스크 공간
- 메타데이터 품질
- 서비스 실행 상태

**문제가 발견되면 권장 조치 명령어가 출력됩니다.**

---

## 문제 해결

### 문제 1: 문서가 웹에서 검색되지 않음

**진단:**
```bash
# 동기화 상태 확인
.venv/bin/python scripts/ops/auto_sync_checker.py --dry-run
```

**해결:**
```bash
# 누락된 문서 자동 복구
.venv/bin/python scripts/ops/auto_sync_checker.py --auto-fix

# OCR이 필요한 경우
.venv/bin/python scripts/ops/auto_sync_checker.py --auto-fix --use-ocr
```

### 문제 2: 메타데이터(기안자 등)가 누락됨

**진단:**
```bash
# DB에서 기안자 누락 확인
sqlite3 metadata.db "SELECT COUNT(*) FROM documents WHERE drafter IS NULL;"
```

**해결:**
```bash
# 메타데이터 재추출
./scripts/reextract_metadata.py

# Dry-run으로 먼저 확인
./scripts/reextract_metadata.py --dry-run
```

### 문제 3: 중복 파일이 쌓임

**진단:**
```bash
# year_정보 없 폴더 확인
ls -la docs/year_정보\ 없/
```

**해결:**
```bash
# 중복 파일 정리 (Dry-run 먼저 권장)
.venv/bin/python scripts/ops/cleanup_duplicates.py --dry-run

# 실제 삭제
.venv/bin/python scripts/ops/cleanup_duplicates.py
```

### 문제 4: OCR 텍스트 추출 불량

**진단:**
```bash
# 텍스트 추출이 부족한 문서 찾기
.venv/bin/python scripts/ops/ocr_reprocess.py --dry-run --char-threshold 100
```

**해결:**
```bash
# OCR 재처리
./scripts/force_ocr_update.py --threshold 100
```

### 문제 5: 웹 서버가 응답하지 않음

**진단:**
```bash
# 프로세스 확인
ps aux | grep -E "(streamlit|uvicorn)"
```

**해결:**
```bash
# 모든 관련 프로세스 종료
pkill -f streamlit
pkill -f uvicorn

# 재시작
bash start_ai_chat.sh
```

---

## 유지보수 스크립트

### 자동화 스크립트 목록

| 스크립트 | 용도 | 실행 주기 |
|---------|------|-----------|
| `healthcheck.py` | 시스템 전체 상태 체크 | 매일 |
| `auto_sync_checker.py` | 파일-DB 동기화 확인 및 복구 | 주 1회 |
| `cleanup_duplicates.py` | 중복 파일 정리 | 월 1회 |
| `reextract_metadata.py` | 메타데이터 재추출 | 필요시 |
| `force_ocr_update.py` | OCR 재처리 | 필요시 |

### Cron 설정 예시

매일 오전 9시에 헬스체크:
```bash
crontab -e

# 추가
0 9 * * * cd /home/wnstn4647/AI-CHAT && ./scripts/healthcheck.py >> /tmp/healthcheck.log 2>&1
```

매주 일요일 오전 3시에 동기화 체크:
```bash
0 3 * * 0 cd /home/wnstn4647/AI-CHAT && ./scripts/auto_sync_checker.py --auto-fix >> /tmp/sync_check.log 2>&1
```

---

## 주의사항

### ⚠️ 절대 하지 말아야 할 것

1. **DB 파일 직접 수정 금지**
   - `metadata.db`를 직접 편집하지 마세요
   - 항상 제공된 스크립트를 사용하세요

2. **venv 외부에서 스크립트 실행 금지**
   - 모든 스크립트는 `.venv/bin/python3`를 사용하도록 설정됨
   - `python3 scripts/xxx.py` 대신 `./scripts/xxx.py` 사용

3. **year_YYYY 폴더의 파일 직접 삭제/이동 금지**
   - DB와 불일치가 발생합니다
   - 반드시 스크립트를 통해 처리하세요

4. **동시 인제스트 금지**
   - 한 번에 하나의 인제스트만 실행하세요
   - DB 락 충돌이 발생할 수 있습니다

### ✅ 권장사항

1. **정기 백업**
   ```bash
   # DB 백업
   cp metadata.db metadata.db.backup_$(date +%Y%m%d)

   # 문서 폴더 백업
   tar -czf docs_backup_$(date +%Y%m%d).tar.gz docs/year_20*
   ```

2. **로그 확인**
   ```bash
   # 최근 로그 확인
   ls -lt rag_system/logs/
   tail -50 rag_system/logs/app_YYYYMMDD.log
   ```

3. **디스크 공간 모니터링**
   ```bash
   df -h .
   ```

---

## 긴급 연락처

시스템 관리 문의:
- 시스템 개발자: [연락처 추가 필요]
- 기술 지원: [연락처 추가 필요]

---

---

## 고급 운영

### 모델 업그레이드
LLM 모델 교체 및 GPU 서버 마이그레이션은 별도 문서를 참조하세요:
📄 **[MODEL_UPGRADE_AND_MIGRATION.md](docs/dev/MODEL_UPGRADE_AND_MIGRATION.md)**

### 보안 정책
시스템 보안 및 접근 제어는 별도 문서를 참조하세요:
📄 **[SECURITY_POLICY.md](docs/dev/SECURITY_POLICY.md)**

---

## 변경 이력

| 날짜 | 변경 내용 | 작성자 |
|------|-----------|--------|
| 2025-11-24 | 최초 작성 | AI Assistant |
| 2025-11-24 | 모델 업그레이드 및 서버 마이그레이션 섹션 추가 | AI Assistant |

