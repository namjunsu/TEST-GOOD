# 메타데이터 동기화 관리 가이드

**작성일**: 2025-11-20
**대상**: 시스템 관리자, 개발팀

---

## 📋 개요

AI-CHAT 시스템의 메타데이터 품질과 DB-인덱스 동기화 상태를 관리하는 가이드입니다.

---

## 🔍 현재 상태 (2025-11-20)

### 메타데이터 품질
- **전체 문서**: 473개
- **기안자 누락**: 71개 (15.0%)
  - 2017년 문서: 45/80개 누락 (56.2%)
  - 2015년 문서: 9/23개 누락 (39.1%)
  - 대부분 OCR 품질 문제 또는 원본 문서에 기안자 정보 없음
- **카테고리 누락**: 299개 (63.2%)
- **날짜 형식 문제**: 0개

### 동기화 상태
- ✅ DB-BM25 인덱스 완전 동기화 (473개 일치)
- ✅ 검색 결과 일관성 확보

---

## 🛠️ 정기 점검 프로세스

### 1. 일일 점검 (자동화 가능)

```bash
# 간단한 동기화 체크
python scripts/validate_metadata.py | grep "동기화 상태"
```

### 2. 주간 점검

```bash
# 1. 전체 메타데이터 검증
python scripts/validate_metadata.py

# 2. 보고서 확인
cat reports/metadata/latest.json | jq '.summary'

# 3. 권장사항이 있으면 실행
if [ $(jq '.recommendations | length' reports/metadata/latest.json) -gt 0 ]; then
    echo "⚠️ 권장사항 있음. 보고서 확인 필요"
fi
```

### 3. 월간 정밀 점검

```bash
# 1. 누락된 기안자 복구 시도
python scripts/fix_missing_drafters.py

# 2. 인덱스 재생성 (필요시)
python scripts/reindex_atomic.py

# 3. 실패 패턴 분석
python scripts/analyze_failed_extractions.py > reports/failed_patterns_$(date +%Y%m).txt
```

---

## 📊 모니터링 지표

### 핵심 지표 (KPI)

| 지표 | 목표 | 현재 | 상태 |
|-----|------|------|------|
| 기안자 누락률 | < 5% | 15.0% | ⚠️ |
| DB-인덱스 불일치 | 0개 | 0개 | ✅ |
| 카테고리 누락률 | < 20% | 63.2% | ❌ |

### 알림 임계값

- **긴급**: DB-인덱스 불일치 > 10개
- **경고**: 기안자 누락률 > 20%
- **주의**: 신규 문서 메타데이터 누락

---

## 🔧 문제 해결 가이드

### Case 1: 기안자 대량 누락

```bash
# 1. 자동 복구 시도
echo "y" | python scripts/fix_missing_drafters.py

# 2. 복구 실패 문서 분석
python scripts/analyze_failed_extractions.py

# 3. 수동 업데이트 (필요시)
sqlite3 metadata.db "
UPDATE documents
SET drafter = '기안자명'
WHERE filename = '파일명.pdf';
"
```

### Case 2: DB-인덱스 불일치

```bash
# 1. 불일치 확인
python scripts/validate_metadata.py | grep "불일치"

# 2. 인덱스 재생성
python scripts/reindex_atomic.py

# 3. 검증
python scripts/validate_metadata.py
```

### Case 3: 검색 결과 불일치

```bash
# 1. 특정 기안자 검증 (예: 하승범)
sqlite3 metadata.db "SELECT COUNT(*) FROM documents WHERE drafter = '하승범';"

# 2. BM25 인덱스 확인
python3 -c "
import pickle
with open('var/index/bm25_index.pkl', 'rb') as f:
    idx = pickle.load(f)
    docs = idx['documents']
    count = sum(1 for doc in docs if '하승범' in str(doc))
    print(f'BM25 인덱스: {count}개')
"

# 3. 불일치 시 재인덱싱
python scripts/reindex_atomic.py
```

---

## 📈 개선 로드맵

### Phase 1: 즉시 실행 (1주)
- [x] 메타데이터 검증 스크립트 생성
- [x] 자동 복구 스크립트 구현
- [x] 하승범 외 193개 문서 기안자 복구

### Phase 2: 단기 개선 (1개월)
- [ ] 2017년 문서 OCR 재처리
- [ ] 카테고리 자동 분류 시스템 구현
- [ ] 일일 자동 검증 크론잡 설정

### Phase 3: 장기 개선 (3개월)
- [ ] ML 기반 메타데이터 추출 개선
- [ ] 실시간 동기화 모니터링 대시보드
- [ ] 이상 감지 알림 시스템

---

## 📝 스크립트 목록

| 스크립트 | 용도 | 실행 주기 |
|---------|------|----------|
| `scripts/validate_metadata.py` | 메타데이터 품질 검증 | 일일 |
| `scripts/fix_missing_drafters.py` | 누락 기안자 자동 복구 | 주간 |
| `scripts/reindex_atomic.py` | BM25 인덱스 재생성 | 필요시 |
| `scripts/analyze_failed_extractions.py` | 실패 패턴 분석 | 월간 |

---

## 🚨 알려진 이슈

### 1. 2017년 문서 기안자 누락 (56.2%)
- **원인**: OCR 품질 저하 또는 문서 형식 변경
- **영향**: 45개 문서
- **해결**: OCR 재처리 필요

### 2. 카테고리 대량 누락 (63.2%)
- **원인**: 초기 데이터 마이그레이션 시 누락
- **영향**: 299개 문서
- **해결**: 자동 분류 시스템 구현 필요

### 3. 특정 패턴 추출 실패
- `기안자 | ESS` → ESS는 시스템명으로 실제 기안자 아님
- 빈 기안자 필드
- OCR 깨짐으로 인한 인식 불가

---

## 📞 지원

메타데이터 관련 문의:
- 스크립트 오류: GitHub Issues 등록
- 데이터 품질 문의: 기술관리팀 내부 채널
- 긴급 복구: `scripts/reindex_atomic.py` 실행

---

## 🔄 변경 이력

- 2025-11-20: 초기 가이드 작성, 하승범 문서 15개 복구
- 2025-11-20: 자동 검증 스크립트 추가, 193개 기안자 복구