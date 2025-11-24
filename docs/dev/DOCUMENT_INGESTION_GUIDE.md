# AI-CHAT 신규 기안서 문서 추가 절차

## 1. 개요

AI-CHAT 시스템에 새로운 기안서 PDF를 추가하여 검색·질의에 활용하기 위한 표준 절차이다.
신규 문서는 `docs/incoming/` 디렉터리에 투입되며, `scripts/ingest_from_docs.py` 스크립트를 통해 자동 처리된다.

## 2. 기본 절차 (간단 버전)

```bash
# 1) 새 기안서 PDF를 incoming 폴더로 복사
cp /경로/새기안서.pdf docs/incoming/

# 2) 문서 처리 스크립트 실행
.venv/bin/python scripts/ingest_from_docs.py
```

## 3. 상세 단계별 절차

### Step 1. PDF 파일 준비

**파일명 형식(권장):**
- `YYYY-MM-DD_제목.pdf`
- 예) `2025-11-20_장비구매신청서.pdf`

**위치:**
- `docs/incoming/` 폴더에 복사

```bash
cp /your/pdf/path/2025-11-20_테스트기안서.pdf docs/incoming/
```

### Step 2. 문서 처리 실행

**기본 실행:**
```bash
.venv/bin/python scripts/ingest_from_docs.py
```

**옵션 활용 예시:**
```bash
# 최대 5개만 처리
.venv/bin/python scripts/ingest_from_docs.py --limit 5

# 2025년 파일만 처리
.venv/bin/python scripts/ingest_from_docs.py --only "2025*"

# 실제 반영 없이 처리 대상·로그만 확인 (테스트용)
.venv/bin/python scripts/ingest_from_docs.py --dry-run

# 스캔본 PDF에 대해 OCR 강제 활성화
.venv/bin/python scripts/ingest_from_docs.py --ocr
```

### Step 3. 스크립트 내부 처리 흐름

`ingest_from_docs.py`는 아래 순서로 문서를 처리한다.

1. **PDF 텍스트 추출** (일반 텍스트 + 필요 시 OCR)
2. **메타데이터 추출** (기안일, 기안자, 금액 등)
3. **문서 유형 분류** (구매·수리·소모품 등)
4. **메타데이터 DB 저장**
5. **처리 완료된 PDF를 `docs/processed/` 폴더로 이동**

> **참고**: 현재 구현에서는 BM25 인덱스와 벡터 인덱스 갱신은 별도 배치 스크립트로 실행된다.
> - BM25: `python scripts/quick_rebuild_bm25.py`
> - FAISS: `python scripts/rebuild_rag_indexes.py`

## 4. 처리 결과 확인

### 4-1. 메타데이터 DB 확인

```bash
.venv/bin/python - << 'EOF'
from app.data.metadata_db import MetadataDB
db = MetadataDB()
latest = db.get_recent_documents(limit=5)
for doc in latest:
    filename = doc.get("filename", "N/A")
    drafter = doc.get("drafter", "N/A")
    amount = doc.get("claimed_total", 0)
    print(f"{filename}: {drafter}, {amount:,}원")
EOF
```

### 4-2. 검색 API 테스트

```bash
curl -X POST "http://127.0.0.1:7860/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "새로 추가한 문서 내용"}'
```

## 5. 인덱스 갱신 (필수)

문서 추가 후에는 반드시 인덱스를 갱신해야 검색이 가능하다.

```bash
# BM25 인덱스 갱신
.venv/bin/python scripts/quick_rebuild_bm25.py

# FAISS 벡터 인덱스 갱신 (선택)
.venv/bin/python scripts/rebuild_rag_indexes.py
```

## 6. 자동화 설정 (선택)

cron을 이용해 매일 새벽 자동 처리:

```bash
# crontab -e
0 2 * * * cd /home/wnstn4647/AI-CHAT \
&& .venv/bin/python scripts/ingest_from_docs.py \
>> logs/ingest_cron.log 2>&1

# BM25 인덱스 자동 갱신 (문서 추가 30분 후)
30 2 * * * cd /home/wnstn4647/AI-CHAT \
&& .venv/bin/python scripts/quick_rebuild_bm25.py \
>> logs/bm25_rebuild_cron.log 2>&1
```

필요 시 `flock` 또는 lock 파일을 사용해 중복 실행 방지 권장

## 7. 운영 시 주의사항

- **파일명**: `YYYY-MM-DD_제목.pdf` 형식 권장 (연도별 정리 및 검색 편의성 향상)
- **중복 처리**: 동일 해시를 가진 파일은 자동으로 스킵 (중복 기안서 방지)
- **오류 처리**: 처리 실패 파일은 `docs/quarantine/` 디렉터리로 이동 → 원인 분석 후 재투입
- **OCR 필요 문서**: 스캔본/이미지 위주 문서는 `--ocr` 옵션 사용 또는 기본 설정에서 OCR 활성화 필요
- **Import 경로**: 실제 코드의 import 경로는 `from app.data.metadata_db import MetadataDB` 형식 사용

## 8. 빠른 테스트 시나리오

```bash
# 1. 테스트 파일 투입
cp /your/pdf/path/2025-11-20_테스트기안서.pdf docs/incoming/

# 2. 드라이런으로 대상만 확인
.venv/bin/python scripts/ingest_from_docs.py --dry-run

# 3. 실제 처리 (1건만)
.venv/bin/python scripts/ingest_from_docs.py --limit 1

# 4. 처리된 파일 확인
ls -la docs/processed/

# 5. BM25 인덱스 갱신
.venv/bin/python scripts/quick_rebuild_bm25.py

# 6. 검색 테스트
curl -X POST "http://127.0.0.1:7860/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "테스트기안서 내용"}'
```

## 9. 트러블슈팅

### 문제: 새로 추가한 문서가 검색되지 않음
- **원인**: 인덱스 미갱신
- **해결**: `python scripts/quick_rebuild_bm25.py` 실행

### 문제: OCR이 필요한 스캔 문서 처리 실패
- **원인**: OCR 라이브러리 미설치
- **해결**:
  ```bash
  pip install pytesseract pdf2image
  sudo apt-get install tesseract-ocr tesseract-ocr-kor
  ```

### 문제: 중복 파일 처리
- **원인**: 동일 파일을 다시 투입
- **해결**: 자동으로 스킵됨 (정상 동작)

## 10. 관련 스크립트

- `scripts/ingest_from_docs.py`: 문서 투입 메인 스크립트
- `scripts/quick_rebuild_bm25.py`: BM25 인덱스 갱신
- `scripts/rebuild_rag_indexes.py`: FAISS 벡터 인덱스 갱신
- `scripts/enhanced_ocr_processor.py`: OCR 전용 처리기

---

*최종 수정: 2025-11-20*
*작성자: AI-CHAT 개발팀*