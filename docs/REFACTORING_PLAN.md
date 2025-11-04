# AI-CHAT 리팩토링 계획서
작성일: 2025-11-04

## 1. 현재 문제점 분석

### 1.1 중복 파일
- `app/rag/summary_templates.py` (532줄) - pipeline.py에서 사용 중 ✅
- `app/rag/render/summary_templates.py` (396줄) - render/__init__.py에서 export

**결론**: render 폴더는 미사용 또는 테스트용으로 보임

### 1.2 테스트 파일 정리 필요
- `test_code_routing.py`
- `test_config_simple.py`
- `experiments/` 폴더의 여러 테스트 파일들

### 1.3 폴더 구조 개선 필요
현재 구조:
```
AI-CHAT/
├── app/
│   ├── rag/
│   │   ├── summary_templates.py ✅ 사용 중
│   │   ├── pipeline.py
│   │   ├── query_router.py
│   │   ├── render/ ❓ 용도 불명
│   │   ├── parse/
│   │   ├── preprocess/
│   │   └── utils/
│   ├── index/
│   ├── extractors/
│   └── config/
├── modules/ ❓ app과 중복?
├── config/ ❓ app/config와 중복?
└── experiments/ 🗑️ 정리 필요
```

## 2. SEARCH 모드 추가 계획

### 2.1 설계

**새로운 QueryMode 추가:**
```python
class QueryMode(Enum):
    QA = "qa"
    SUMMARY = "summary"
    PREVIEW = "preview"
    SEARCH = "search"  # 새로 추가
```

**감지 키워드:**
- "찾아줘", "검색", "찾아", "있어?", "있나요"
- "문서", "기안서", "파일"

**응답 형식:**
```
📄 중계차 카메라 렌즈 관련 문서 (3건)

1. 2024-03-15_중계차_카메라_렌즈_오버홀_수리건.pdf
   📋 기안자: 유인혁 | 📅 2024-03-15
   💰 비용: ₩2,500,000
   📝 Canon HJ40x10B 렌즈 오버홀 작업

2. 2023-11-20_중계차_렌즈_교체_검토서.pdf
   📋 기안자: 남준수 | 📅 2023-11-20
   💰 예산: ₩12,000,000
   📝 노후 렌즈 교체 검토

3. 2023-08-10_중계차_카메라_정기점검_보고서.pdf
   📋 기안자: 최새름 | 📅 2023-08-10
   📝 중계차 장비 정기 점검 결과
```

### 2.2 구현 파일

1. **app/rag/query_router.py**
   - `SEARCH_INTENT_PATTERN` 추가
   - `classify_query()` 메서드에 SEARCH 감지 로직 추가

2. **app/rag/pipeline.py**
   - `_answer_search()` 메서드 추가
   - BM25 검색 결과를 리스트 형식으로 포맷팅

3. **app/rag/summary_templates.py** (선택)
   - 문서 리스트 포맷팅 헬퍼 함수 추가

## 3. 코드 정리 계획

### 3.1 제거할 파일
```
❌ app/rag/render/ (전체 폴더)
❌ experiments/claude/20251026/*.py
❌ test_code_routing.py
❌ test_config_simple.py
```

### 3.2 통합할 파일
```
modules/metadata_db.py → app/modules/metadata_db.py (이미 존재)
config/indexing.py → app/config/settings.py에 통합 검토
```

### 3.3 폴더 정리
```
✅ archive/ - 백업용 유지
✅ backups/ - 백업용 유지
✅ docs/ - 문서 폴더 생성
🗑️ experiments/ - 테스트 파일들 archive로 이동
```

## 4. 문서화 계획

### 4.1 생성할 문서
- `docs/ARCHITECTURE.md` - 시스템 아키텍처 설명
- `docs/API_REFERENCE.md` - API 문서
- `docs/QUERY_MODES.md` - 쿼리 모드별 동작 설명
- `docs/DEVELOPMENT_GUIDE.md` - 개발 가이드

### 4.2 업데이트할 문서
- `README.md` - 최신 기능 반영
- `MAINTENANCE_GUIDE.md` - 유지보수 가이드 보완

## 5. 작업 순서

1. ✅ 분석 완료 (현재)
2. 🔄 SEARCH 모드 구현
3. 🔄 레거시 코드 제거
4. 🔄 폴더 정리
5. 🔄 문서화
6. 🔄 테스트 및 검증
7. 🔄 커밋

## 6. 예상 소요 시간

- SEARCH 모드 구현: 30분
- 레거시 코드 제거: 20분
- 폴더 정리: 15분
- 문서화: 40분
- 테스트 및 검증: 20분

**총 예상 시간**: 약 2시간
