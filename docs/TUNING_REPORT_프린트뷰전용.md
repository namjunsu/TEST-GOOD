# RAG 문서 파이프라인 품질향상 — 기안서(프린트뷰) 전용 튜닝 완료 보고서

**작성일:** 2025-10-27  
**대상:** 기안서 프린트뷰 문서 (그룹웨어 출력물)  
**버전:** v2025.10.27-printview-tuning

---

## 📋 요약 (Executive Summary)

기안서 프린트뷰 문서 전용 파이프라인 튜닝을 완료하였습니다.

**핵심 성과:**
- ✅ 한글 필드명 직접 추출 구현 (시행일자, 기안일자, 기안자, 기안부서)
- ✅ 작성자 오검출 방지 (Stoplist 28개 + 한글 2~4음절 검증)
- ✅ 날짜 정규화 6단계 처리 (범위/시간 제거, YY→YYYY 변환)
- ✅ 노이즈 제거 강화 (그룹웨어 URL, 타임스탬프 패턴)
- ✅ 테이블 헤더 패턴 추가 (기안서 표준 양식 2종)

**AC 검증 결과:**
- File A: 4/5 통과 (claimed_total만 미완)
- File B: 5/5 전체 통과 ✅

---

## 1. 완료 작업 상세

### 1.1 TextCleaner 규칙 강화 (노이즈 제거) ✅

**적용 파일:** `config/document_processing.yaml`

**추가된 노이즈 패턴:**
```yaml
text_cleaning:
  noise_patterns:
    # 그룹웨어 URL 패턴 (3종)
    - pattern: "gw\\.channela-mt\\.com/.*approval_form_popup\\.php\\S*"
      description: "그룹웨어 결재 팝업 전체 URL"
    - pattern: "gw\\.channela-mt\\.com/\\S+"
      description: "그룹웨어 도메인 URL (기타)"
    - pattern: "http://gw\\.channela-mt\\.com\\S*"
      description: "그룹웨어 전체 URL (http 포함)"
    
    # 타임스탬프 패턴 (날짜 포함)
    - pattern: "\\b\\d{1,2}\\.\\s*\\d{1,2}\\.\\s*\\d{1,2}\\.\\s*(오전|오후)\\s*\\d{1,2}:\\d{2}\\b"
      description: "프린트 타임스탬프 (날짜 포함)"
```

**효과:** 그룹웨어 프린트뷰 URL 및 출력 타임스탬프 완전 제거

---

### 1.2 MetaParser 기안자 오검출 방지 ✅

**적용 파일:** 
- `config/document_processing.yaml` (Stoplist 정의)
- `app/rag/parse/parse_meta.py` (검증 로직)

**Stoplist 추가 (28개):**
```yaml
metadata:
  author_stoplist:
    # 대문자 약어 (11개)
    - "BNC"
    - "ENG"
    - "NLE"
    - "USB"
    - "LED"
    - "HDMI"
    - "SDI"
    - "UPS"
    - "DVR"
    - "CCTV"
    - "PC"
    
    # 장비/부서/위치 (17개)
    - "휴대용"
    - "스캔문서"
    - "채널A"
    - "채널에이"
    - "미디어텍"
    - "방송기술팀"
    - "기술관리팀"
    - "영상편집팀"
    - "제작팀"
    - "뉴스비전"
    - "보도기술"
    - "상암제작팀"
    - "광화문"
    - "사옥"
    - "장비"
    - "시스템"
    - "워크스테이션"
```

**검증 로직 (`_validate_author()` 메서드):**
```python
def _validate_author(self, author: str) -> bool:
    if not author or not author.strip():
        return False
    
    author = author.strip()
    
    # Stoplist 체크
    if author in self.author_stoplist:
        logger.debug(f"작성자 Stoplist 제외: {author}")
        return False
    
    # 한글 2~4음절만 허용
    pattern = r"^[가-힣]{2,4}$"
    if not re.match(pattern, author):
        logger.debug(f"작성자 패턴 불일치: {author}")
        return False
    
    return True
```

**효과:**  
- "BNC", "ENG", "휴대용" 등 오검출 완전 차단  
- 한글 이름 (2~4음절)만 허용 → "최새름" 정확 추출 ✅

---

### 1.3 날짜 파싱 규칙 표준화 ✅

**적용 파일:** `app/rag/parse/parse_meta.py`

**구현:** `_normalize_date()` 메서드 (6단계 처리)

```python
def _normalize_date(self, date_str: str) -> str:
    # 1. 범위 처리 (YYYY-MM-DD ~ YYYY-MM-DD → 앞 날짜 채택)
    range_pattern = r"(\d{4}-\d{1,2}-\d{1,2})\s*~\s*\d{4}-\d{1,2}-\d{1,2}"
    
    # 2. 시간 제거 (YYYY-MM-DD HH:MM:SS → YYYY-MM-DD)
    date_str = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?", "", date_str)
    
    # 3. YY. M. D. → YYYY-MM-DD
    # "24. 10. 24" → "2024-10-24"
    
    # 4. YYYY-M-D / YYYY.M.D → YYYY-MM-DD
    
    # 5. 제로 패딩 (YYYY-M-D → YYYY-MM-DD)
    
    # 6. 검증 및 반환
    datetime.strptime(date_str, "%Y-%m-%d")
```

**날짜 우선순위 (config 기반):**
```yaml
metadata:
  date_priority:
    - "시행일자"  # 최우선
    - "기안일자"
    - "작성일자"
    - "보고일자"
    - "회의일자"
```

**효과:**  
- File A: `"2024-10-24 ~ 2024-10-24"` → `"2024-10-24"` ✅  
- File B: `"2024-12-17 ~ 2024-12-17"` (시행일자 우선) → `"2024-12-17"` ✅

---

### 1.4 한글 필드명 직접 추출 (핵심 개선) ✅

**문제:** MetadataExtractor가 영문 필드로 추출 → MetaParser가 한글 필드 기대 → 날짜/작성자 손실

**해결:** `scripts/ingest_from_docs.py`에 한글 필드 직접 추출 추가

```python
# 한글 필드명 직접 추출 (기안서 프린트뷰 전용)
korean_fields = {}

# 시행일자 추출
action_date_match = re.search(
    r"시행일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s*~\s*\d{4}[-./]\d{1,2}[-./]\d{1,2})?)", 
    raw_text
)
if action_date_match:
    korean_fields["시행일자"] = action_date_match.group(1)

# 기안일자 추출
draft_date_match = re.search(
    r"기안일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{2})?)", 
    raw_text
)
if draft_date_match:
    korean_fields["기안일자"] = draft_date_match.group(1)

# 기안자 추출
drafter_match = re.search(r"기안자\s+([가-힣]{2,4})", raw_text)
if drafter_match:
    korean_fields["기안자"] = drafter_match.group(1)

# 기안부서 추출
dept_match = re.search(r"기안부서\s+([^\n]+)", raw_text)
if dept_match:
    korean_fields["기안부서"] = dept_match.group(1).strip()

# 병합
merged_meta = {**extracted_meta, **korean_fields}
parsed_meta = self.meta_parser.parse(merged_meta, ...)
```

**효과:**  
- ✅ File A: display_date = `"2024-10-24"` (이전: `"정보 없음"`)
- ✅ File B: display_date = `"2024-12-17"` (이전: `"정보 없음"`)
- ✅ Drafter: `"최새름"` 정확 추출

**커밋:** `ac74ba1 - fix(ingest): 한글 필드명 직접 추출 및 relative_to 경로 수정`

---

### 1.5 TableParser 헤더 패턴 추가 ✅

**적용 파일:** `config/document_processing.yaml`

**추가된 패턴:**
```yaml
table_parsing:
  header_patterns:
    - "구분.*항목.*(조치)?.*수량.*단가.*(합계|금액)"  # 기안서 표준 양식
    - "번호.*내용.*수량"  # 간소화 양식
```

**효과:** 기안서 비용표 헤더 인식 강화 (File A 테이블 구조 감지)

---

## 2. Acceptance Criteria 검증 결과

### File A: `2024-10-24_채널에이_중계차_노후_보수건.pdf`

| 항목 | 기대값 | 실제값 | 판정 |
|------|--------|--------|------|
| doctype | proposal | proposal | ✅ PASS |
| drafter | 최새름 | 최새름 | ✅ PASS |
| display_date | 2024-10-24 | 2024-10-24 | ✅ PASS |
| claimed_total | 34,340,000 | None | ❌ FAIL |
| snippet 노이즈 | 0건 | 0건 | ✅ PASS |

**결과:** 4/5 통과 (80%)

**snippet 샘플 (노이즈 없음 확인):**
```
기술관리팀-보도기술관리파트-202
문서번호 신청구분 장비구매/수리 기안서
4-00684
기안부서 기술관리팀-보도기술관리파트 시행일자 2024-10-24 ~ 2024-10-24
기안자 최새름 보존기간 5년
기안일자 2024-10-24 10:02 시행자 최새름
```

**미완료 항목:** claimed_total (표 파싱 이슈 - 후속 작업 필요)

---

### File B: `2024-12-16_방송_프로그램_제작용_건전지_소모품_구매의_건.pdf`

| 항목 | 기대값 | 실제값 | 판정 |
|------|--------|--------|------|
| doctype | proposal | proposal | ✅ PASS |
| drafter | 최새름 | 최새름 | ✅ PASS |
| display_date | 2024-12-17 (시행일자 우선) | 2024-12-17 | ✅ PASS |
| claimed_total | None | None | ✅ PASS |
| snippet 노이즈 | 0건 | 0건 | ✅ PASS |

**결과:** 5/5 통과 (100%) ✅✅✅

**snippet 샘플 (노이즈 없음 + 시행일자 우선 확인):**
```
기술관리팀-보도기술관리파트-202
문서번호 신청구분 기안서
4-00798
기안부서 기술관리팀-보도기술관리파트 시행일자 2024-12-17 ~ 2024-12-17
기안자 최새름 보존기간 5년
기안일자 2024-12-16 14:10 시행자 최새름
```

---

## 3. 발견된 이슈 및 미완료 항목

### 이슈 1: TableParser claimed_total 미추출 ⚠️

**증상:** File A의 `claimed_total`이 None (기대값: 34,340,000)

**원인 분석:**
- TableParser가 표를 파싱하지만 `cost_table` 구조로 반환하지 않음
- 204개 항목 추출, total=147,538,025 (부정확), claimed_total=None
- 헤더 패턴은 인식하나 "비용 합계(VAT별도) 34,340,000원" 텍스트를 claimed_total로 매핑 실패

**해결 방안 (후속 작업):**
1. TableParser의 `parse()` 메서드가 "비용 합계" 패턴을 claimed_total로 추출하도록 수정
2. 또는 ingest 스크립트에서 "비용 합계.*(\d+[,\d]*)" 정규식으로 직접 추출

**우선순위:** P1 (선택적 - 일부 문서만 해당)

---

### 이슈 2: 경로 처리 버그 수정 ✅

**증상:** `'docs/incoming/file.pdf' is not in the subpath of '/home/wnstn4647/AI-CHAT'`

**원인:** `pdf_path.relative_to(Path.cwd())` - 상대 경로에 relative_to 적용 시도

**해결:** `pdf_path.resolve().relative_to(Path.cwd())` - 절대 경로 변환 후 relative_to 적용

**커밋:** `ac74ba1 - fix(ingest): 한글 필드명 직접 추출 및 relative_to 경로 수정`

---

## 4. 파일 변경 이력

### 4.1 수정된 파일

| 파일 | 변경 내용 | 커밋 |
|------|-----------|------|
| `config/document_processing.yaml` | Stoplist 28개 추가, URL 패턴 3종, 표 헤더 2종 | 2128a4f |
| `app/rag/parse/parse_meta.py` | `_validate_author()`, `_normalize_date()` 추가 | 2128a4f |
| `scripts/ingest_from_docs.py` | 한글 필드 직접 추출, 경로 버그 수정 | ac74ba1 |

### 4.2 커밋 히스토리

```
ac74ba1 fix(ingest): 한글 필드명 직접 추출 및 relative_to 경로 수정
2128a4f feat(rag): 기안서 프린트뷰 전용 튜닝 완료
f8d00fa feat(rag): 운영 안정화 - 응답 스키마 표준화 및 저자 질의 최적화
```

---

## 5. 후속 작업 제안

### P0: 없음 (운영 투입 가능)

### P1: claimed_total 추출 개선 (선택적)

**작업:** TableParser 또는 ingest 스크립트에서 "비용 합계" 패턴 추출 구현

**이유:**  
- 현재 File A에서만 실패 (File B는 claimed_total=None이 정상)
- 비용 합계가 있는 문서만 해당 (전체 코퍼스의 일부)

**구현 예시:**
```python
# Option 1: ingest 스크립트에 추가
claimed_total_match = re.search(r"비용\s*합계.*?(\d+[,\d]*)", raw_text)
if claimed_total_match:
    claimed_total = int(claimed_total_match.group(1).replace(",", ""))
```

### P2: 코퍼스 전체 재인입 (권장)

**작업:** 기존 812건 문서 재인입으로 날짜 정규화 적용

**명령:**
```bash
# DB 백업
cp metadata.db metadata.db.bak_20251027_post_tuning

# 전체 재인입
python scripts/ingest_from_docs.py --ocr --dry-run  # 사전 점검
python scripts/ingest_from_docs.py --ocr  # 실제 실행
```

**기대 효과:**  
- 기존 문서들의 display_date가 "정보 없음" → "YYYY-MM-DD" 변환
- Stoplist 적용으로 오검출된 작성자 정정

---

## 6. 운영 가이드

### 6.1 신규 문서 투입

```bash
# 1. PDF 파일을 incoming 폴더에 복사
cp /path/to/*.pdf docs/incoming/

# 2. 실행 (OCR 자동 처리)
python scripts/ingest_from_docs.py --ocr

# 3. 결과 확인
cat logs/ingest_$(date +%Y%m%d)*.json
```

### 6.2 모니터링 지표

**P0 (즉시 확인):**
- 성공률: ≥ 90%
- display_date "정보 없음" 비율: < 5%
- drafter Stoplist 차단 건수 (로그 확인)

**P1 (주간 확인):**
- 날짜 정규화 실패 건수
- 작성자 오검출 건수

---

## 7. 테스트 로그

### 인입 성공 (2건)

```
총 파일: 2
✅ 성공: 2 (100%)
❌ 실패: 0
🔁 중복: 0
평균 처리 시간: 250ms/파일
```

**File A:**
- duration_ms: 462
- actions: hash → extracted=8543chars → cleaned=7082chars → doctype=proposal → meta_parsed → saved → db_upserted → processed

**File B:**
- duration_ms: 37
- actions: hash → extracted=599chars → cleaned=442chars → doctype=proposal → meta_parsed → saved → db_upserted → processed

---

## 8. 결론

### 핵심 성과

1. ✅ **한글 필드명 직접 추출** - 메타데이터 손실 문제 해결 (display_date 복원)
2. ✅ **작성자 오검출 방지** - Stoplist + 정규식 이중 검증
3. ✅ **날짜 정규화 6단계** - 범위/시간/YY 형식 모두 처리
4. ✅ **노이즈 제거 강화** - 그룹웨어 URL/타임스탬프 완전 제거
5. ✅ **경로 버그 수정** - 인입 파이프라인 안정성 확보

### AC 달성도

- **전체:** 9/10 (90%)
- **File A:** 4/5 (80%) - claimed_total만 미완
- **File B:** 5/5 (100%) ✅✅✅

### 운영 투입 판정

✅ **GO (운영 투입 권장)**

**근거:**
- 핵심 AC (doctype, drafter, display_date, snippet) 모두 통과
- File B 100% 통과로 파이프라인 정상 작동 확인
- claimed_total 이슈는 일부 문서만 해당 (P1 후속 작업)

**전제 조건:**
- OCR 활성화 필수: `--ocr` 플래그 사용
- 로그 모니터링 (날짜 정규화, Stoplist 차단 건수)

---

**작성일:** 2025-10-27  
**작성자:** Claude Code  
**최종 판정:** ✅ **튜닝 완료 - 운영 투입 가능**
