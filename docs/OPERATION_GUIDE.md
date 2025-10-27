# RAG 문서 인입 시스템 운영 가이드

**버전:** v2025.10.27-intake-stable
**작성일:** 2025-10-27
**대상:** 운영 담당자

---

## 🚀 빠른 시작 (Quick Start)

### 신규 문서 투입

```bash
# 1. PDF 파일을 incoming 폴더에 복사
cp /path/to/*.pdf docs/incoming/

# 2. 실행 (OCR 자동 처리)
python scripts/ingest_from_docs.py --ocr
```

**결과:**
- ✅ 성공: `docs/processed/<연도>/` 자동 정리
- 🔁 중복: 건너뛰고 로그에 기록
- ❌ 실패: `docs/rejected/` 또는 `docs/quarantine/` 이동

---

## 📁 파일 구조

```
docs/
├── incoming/          # 📥 신규 PDF 투입 위치
├── processed/         # ✅ 처리 완료 (연도별 자동 정리)
│   ├── 2025/
│   ├── 2024/
│   └── ...
├── rejected/          # ❌ 처리 실패 (복구 불가)
└── quarantine/        # ⚠️ 보류 (수동 검토 필요)
```

---

## 🛠️ 사용 방법

### 기본 명령어

```bash
# 사전 점검 (Dry-run - 권장)
python scripts/ingest_from_docs.py --ocr --dry-run

# 실제 반영
python scripts/ingest_from_docs.py --ocr

# 특정 파일만 처리
python scripts/ingest_from_docs.py --ocr --only "2025-*.pdf"

# 개수 제한 (테스트용)
python scripts/ingest_from_docs.py --ocr --limit 10
```

### OCR 옵션

**옵션 A: 파이프라인 OCR (기본 - 권장)**
```bash
python scripts/ingest_from_docs.py --ocr
```
- 자동 OCR 폴백 (이미지 PDF 감지 시)
- 단일 명령으로 완료
- 처리 시간: ~1.3초/파일

**옵션 B: 사전 OCR (대량 처리용)**
```bash
# 1. 사전 OCR 처리
ocrmypdf --force-ocr --language kor+eng input.pdf output_ocr.pdf

# 2. incoming 폴더로 이동
mv output_ocr.pdf docs/incoming/

# 3. 일반 인입
python scripts/ingest_from_docs.py
```

---

## 📝 파일명 권장 규칙

```
YYYY-MM-DD_제목_부가정보.pdf
```

**예시:**
- ✅ `2025-10-27_장비구매_기안서.pdf`
- ✅ `2025-08-15_회의록_기술검토.pdf`
- ⚠️ `장비구매.pdf` (날짜 없음 - 자동 분류 정확도 낮음)

---

## 🔍 로그 확인

### 실행 로그
```bash
# 최근 실행 로그 확인
cat logs/ingest_$(date +%Y%m%d)*.json

# 실시간 모니터링
tail -f logs/ingest.log
```

### 로그 내용
- 처리 시간 (ms/파일)
- 성공/실패/중복 건수
- SLA 준수 여부 (60초/10건)
- 에러 메시지 (실패 시)

---

## ✅ 헬스체크 (운영 후)

### A. 혼합 샘플 재투입
```bash
# docs/incoming/에 테스트 파일 10건 준비 후
python scripts/ingest_from_docs.py --ocr --dry-run
```
**기대 결과:**
- 성공률 ≥ 90%
- SLA ≤ 60초/10건
- 거부/실패 0건

### B. 목록 질의 테스트
UI 또는 API에서 다음 질의 실행:
1. "2025년 문서 보여줘"
2. "기안서 최신 5건"
3. "<정확한 파일명>.pdf 요약"

**기대 결과:**
- 응답 시간 < 3초
- 문서 목록 정상 표시
- Doctype 라벨 표시 (기안서/검토서/폐기 등)

### C. DB 분포 확인
```bash
# Doctype 분포 조회
python -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cur = conn.cursor()
cur.execute('SELECT doctype, COUNT(*) FROM documents GROUP BY doctype')
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]}건')
conn.close()
"
```

**기대 결과:**
- review, disposal, unknown이 0이 아님
- proposal이 대부분 (95%+는 정상)

---

## 🔧 문제 해결 (Troubleshooting)

### 문제 1: OCR 실패
**증상:** "OCR 라이브러리 미설치" 에러
**해결:**
```bash
pip install pytesseract pdf2image
sudo apt-get install tesseract-ocr tesseract-ocr-kor
```

### 문제 2: 중복 계속 발생
**증상:** 같은 파일이 계속 중복 처리됨
**해결:**
```bash
# DB에서 중복 확인
python -c "
import sqlite3
conn = sqlite3.connect('metadata.db')
cur = conn.cursor()
cur.execute('SELECT filename, COUNT(*) FROM documents GROUP BY filename HAVING COUNT(*) > 1')
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]}번 중복')
conn.close()
"

# 중복 제거 (수동)
# TODO: 중복 제거 스크립트 작성 필요
```

### 문제 3: 처리 속도 느림
**증상:** SLA 초과 (> 60초/10건)
**해결:**
- 배치 크기 조정: `--limit 5` (10건 → 5건)
- 또는 사전 OCR 방식 사용 (옵션 B)

### 문제 4: Doctype 오분류
**증상:** 검토서가 기안서로 분류됨
**해결:**
```bash
# 재분류 스크립트 실행
python scripts/reclassify_doctype.py --dry-run
python scripts/reclassify_doctype.py
```

---

## 🔙 롤백 (문제 발생 시)

### 전체 롤백
```bash
# 1. Git 복귀
git checkout master
git revert v2025.10.27-intake-stable

# 2. DB 복원
cp metadata.db.bak_20251027_143103 metadata.db

# 3. 재시작
bash start_ai_chat.sh
```

### 부분 비활성화 (Doctype만)
```yaml
# config/document_processing.yaml
enable_doctype_classification: false
```

---

## 📊 모니터링 지표

### P0 (즉시 확인)
- **성공률:** ≥ 90%
- **SLA:** ≤ 60초/10건
- **빈 스니펫:** 0건

### P1 (주간 확인)
- **Doctype 분포:** proposal/review/disposal/unknown
- **Unknown 비율:** < 5% (현재 2.0%)
- **중복 문서 발생률:** < 1%

### P2 (월간 확인)
- **평균 처리 시간 추이**
- **OCR 사용 빈도**
- **거부 사유 분석**

---

## 📞 문의 및 지원

**문제 보고:**
- GitHub Issues: [링크 삽입]
- 담당자: @wnstn4647

**로그 제출 시:**
1. `logs/ingest_*.json` 첨부
2. 실패한 PDF 파일명 목록
3. 에러 메시지 전문

---

## 📚 관련 문서

- [E2E 검증 보고서](E2E_RESPONSES.md)
- [Doctype 재분류 보고서](RECLASSIFY_REPORT.md)
- [머지 제안서](MERGE_PROPOSAL.md)

---

**버전:** v2025.10.27-intake-stable
**최종 업데이트:** 2025-10-27
**운영 준비 완료** ✅
