# E2E 검증 상태 보고서

**생성일:** 2025-10-27
**브랜치:** feat/docs-intake-20251026
**커밋:** 8c0b4a0

---

## 완료된 단계 (Steps 0-3)

### ✅ Step 0: 환경 고정 확인

- 브랜치: `feat/docs-intake-20251026` ✓
- DB: 812 documents, WAL mode enabled ✓
- 백업: `metadata.db.bak` (2.5M, 2025-10-26 17:08) ✓
- 테스트: 38/48 passing (79.2%) ✓
- 커버리지: 41.07% (목표 40% 초과) ✓

### ✅ Step 1: 코퍼스 실측 스냅샷

**파일 생성:**
- `docs/SNAPSHOT_DB.json` - 데이터베이스 분포 분석
- `docs/SNAPSHOT_FS.json` - 파일시스템 규칙 준수율

**주요 발견사항:**

**DB 분석 (SNAPSHOT_DB.json):**
- 총 문서: 812건
- Doctype 분포: proposal 812건 (100%)
  - ⚠️ 모든 문서가 proposal로 분류됨 (classifier 튜닝 필요)
- 연도 분포: 2014-2025 (최다: 2017년 170건)
- **268개 중복 그룹** (~33% 중복율)
- **25개 빈 스니펫** (대부분 검토서/폐기 문서)
  - 예: 2022-12-21_티비로직_월모니터_고장_수리_검토의_건.pdf (length=0)
  - 예: 2025-01-09_광화문_스튜디오_모니터_&_스탠드_교체_검토서.pdf (length=0)
- Sum 검증: 모두 NULL (표 파싱 미실행)

**FS 분석 (SNAPSHOT_FS.json):**
- 총 PDF: 748건
- 파일명 규칙 준수: 747/748 (99.9%)
- 미준수 1건: `2020-06-15데스크라이트_대체_장비_구매_건.pdf` (언더스코어 누락)
- broken_pdfs 폴더: 268건 (중복 아카이브)

**산출물:**
- docs/SNAPSHOT_DB.json (81 lines)
- docs/SNAPSHOT_FS.json (27 lines)
- Git 추적 완료 ✓

### ✅ Step 2: Config 보강

**파일:** config/document_processing.yaml

**보강 내용:**

1. **노이즈 패턴 확장** (7개 → 완전 커버리지)
   ```yaml
   # 날짜.시간 타임스탬프
   - pattern: "\\b\\d{1,2}\\.\\s*\\d{1,2}\\.\\s*\\d{1,2}\\.\\s*(오전|오후)\\s*\\d{1,2}:\\d{2}\\b"

   # 그룹웨어 URL
   - pattern: "gw\\.channela-mt\\.com/\\S+"
   - pattern: "approval_form_popup\\.php\\S*"

   # 반복 헤더
   - pattern: "^(장비구매/수리\\s*기안서|기안서)\\s*$"

   # 섹션 앵커
   - pattern: "^(개요|내용|신청수량|수령인|비고|수리\\s*내용|발생\\s*비용|구매\\s*내용|비교검토|기술\\s*검토|별도\\s*첨부)\\s*$"
   ```

2. **Doctype 키워드 보강**
   - proposal: "장비구매/수리", "구매 기안", "수리 기안" 추가
   - review: "검토의 건", "비교검토", "적합성" 추가
   - report: "분석결과", "종합의견" 추가
   - minutes: "협의내용" 추가
   - **disposal 유형 신규 추가** (폐기/불용 문서)

3. **표 파싱 헤더 별칭**
   ```yaml
   cost_table_headers:
     item_aliases: [품명, 품목, 내역, 구매품목, 수리항목]
     quantity_aliases: [수량, 개수, ea, EA]
     unit_price_aliases: [단가, 금액, 가격]
     total_aliases: [합계, 총계, 금액합계, 총액, 소계]
     vat_aliases: [VAT, 부가세, 부가가치세]
   sum_tolerance: 1  # ±1원 허용
   ```

**커밋:** 8de0eca - "feat(config): 코퍼스 실측 기반 규칙 보강"

### ✅ Step 3: 혼합 샘플 10건 인입 테스트

**블로커 발견 및 해결:**

**이슈:** `'MetadataExtractor' object has no attribute 'extract'`
- 원인: scripts/ingest_from_docs.py:207에서 잘못된 메서드 호출
- 수정: `extractor.extract()` → `extractor.extract_all(raw_text, filename)`

**테스트 파일 (10건):**
1. 2014-07-02_TV-UPACK용_BNC케이블_구매.pdf (빈 PDF)
2. 2019-07-05_영상취재팀_SxS_메모리카드_리더기_구매.pdf
3. 2019-09-25_BNC_Tool_&_전기케이블_구매검토서.pdf (검토서)
4. 2020-10-15_영상취재팀_Wireless_Mic_수리.pdf
5. 2021-10-05_뉴스비전_영상취재팀_ENG카메라관련_수리_기술검토서.pdf (검토서)
6. 2022-12-21_티비로직_월모니터_고장_수리_검토의_건.pdf (검토서)
7. 2023-07-11_광화문_티비로직_방송모니터_수리_구매_검토의_건.pdf (검토서)
8. 2024-08-13_기술관리팀_방송시스템_소모품_구매_검토서.pdf (검토서)
9. 2025-01-09_광화문_스튜디오_모니터_&_스탠드_교체_검토서.pdf (검토서)
10. 2025-01-14_채널A_불용_방송_장비_폐기_요청의_건.pdf (폐기)

**Dry-run 결과:**
- ✅ 성공: 9/10 (90%)
- 🚫 거부: 1/10 (2014-07-02, 빈 PDF - 정상 동작)
- ⏱️ SLA: 0.8초 (60초 기준 통과)

**Actual run 결과:**
- 🔁 중복: 10/10 (100%)
- ⏱️ SLA: 0.0초 (중복 감지 즉시)
- ✅ Dedup 로직 정상 작동 확인

**Doctype 분류 (dry-run 기준):**
- proposal: 8건
- disposal: 1건 (2025-01-14 폐기 문서 - ✅ 정확)
- review: 0건 (검토서 6건이 proposal로 분류됨 - ⚠️ classifier 개선 필요)

**커밋:** 8c0b4a0 - "fix(ingest): MetadataExtractor method name - extract → extract_all"

---

## 보류 단계 (Step 4)

### ⏸️ Step 4: E2E 응답 검증

**목표:**
- 3개 목록 질의: "2025년 문서 보여줘", "보고서 최근 5건", "회의록 3분기"
- 4개 파일 요약: 코퍼스 샘플 PDF
  1. 2025-09-04_방송_프로그램_제작용_건전지_소모품_구매의_건.pdf
  2. 2025-09-11_돌직구쇼_백업_무선마이크_구매_건.pdf
  3. 2019-10-25_데스크라이트_수리.pdf
  4. 2019-11-08_조명_모니터링_시스템_거치대_구매_건.pdf

**AC (검증 항목):**
- 노이즈 0
- 빈 스니펫 0
- 중복 0
- Doctype 라벨 노출

**보류 사유:**
- SearchModuleHybrid API 복잡도 높음
- LLM 비활성화 (llama-cpp-python 미설치)
- Step 5 (테스트 복구) 우선순위 더 높음

**대안:**
- Step 5 완료 후 재시도
- 또는 별도 스모크 테스트로 대체

---

## 다음 단계 (Step 5)

### 🔜 Step 5: 실패 테스트 10건 복구

**현황:**
- 통과: 38/48 (79.2%)
- 실패: 10/48 (20.8%)

**실패 분석:**
- **MetaParser: 4건** - date_priority 변경으로 인한 기대값 불일치
- **TableParser: 6건** - 숫자 정규화 로직, 헤더 별칭 미적용

**목표:** 48/48 (100%) 통과

**작업 계획:**
1. MetaParser 테스트 기대값 수정 (date_priority 반영)
2. TableParser 헤더 별칭 적용 (config YAML 반영)
3. 숫자 정규화 ±1원 허용 오차 적용
4. pytest 전량 재실행 및 검증

---

## 종합 평가

**완료:** Steps 0-3 (4/7)
**보류:** Step 4 (1/7)
**대기:** Steps 5-7 (3/7)

**진행률:** 57% (4/7)

**주요 성과:**
✅ 코퍼스 실측 스냅샷 (268 duplicates, 25 empty snippets 발견)
✅ Config 규칙 보강 (7 noise patterns, disposal doctype, table aliases)
✅ 인입 파이프라인 수정 (MetadataExtractor.extract_all)
✅ Dedup 로직 검증 (10/10 중복 감지 정상)

**주요 이슈:**
⚠️ Doctype classifier 정확도 낮음 (검토서 6건 → proposal 오분류)
⚠️ 25개 빈 스니펫 문서 (대부분 검토서/폐기)
⚠️ LLM 비활성화 (llama-cpp-python 미설치)

**권장 우선순위:**
1. **Step 5 (테스트 복구)** - 100% 통과 필수
2. **Step 6 (CI 도입)** - 회귀 방지
3. **Doctype classifier 개선** - 검토서/폐기 정확 분류
4. **Step 4 재시도** - E2E 검증 완료
5. **Step 7 (산출물 정리)** - 최종 머지 준비

---

**생성:** Claude Code
**검토 필요:** Steps 4-7 실행 전략
