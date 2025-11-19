# Domain Synonyms Refactoring 완료 보고서

**날짜**: 2025-11-19
**작업자**: Claude Code
**브랜치**: chore/ocr-dedup-v2-20251113

---

## 📋 작업 개요

방송 장비 브랜드/모델명의 한영 매핑을 위한 DOMAIN_SYNONYMS 시스템을 pipeline.py에서 분리하여 YAML 기반 독립 모듈로 리팩토링.

### 목적
- **유지보수성 개선**: YAML 파일 수정만으로 시소러스 관리 가능
- **코드 간결화**: pipeline.py에서 100+ 줄의 하드코딩 제거
- **확장성 향상**: 새 브랜드/모델 추가 시 Python 코드 수정 불필요

---

## 🔧 변경 사항

### 1. 새로 생성된 파일

#### `config/domain_synonyms.yaml` (235줄, 3.3KB)
```yaml
# 방송 장비 브랜드/모델 시소러스
camera_video_brands:
  소니:
    - 소니
    - Sony
    - SONY
    - sony

  티비로직:
    - 티비로직
    - TVLogic
    - TVLOGIC
    - TV Logic
    - tvlogic

# ... (총 70+ 항목)
```

**구조**:
- 카테고리별 분류 (camera_video_brands, audio_brands, monitor_models 등)
- 키: 검색어 (주로 한글 또는 소문자)
- 값: 동의어 리스트 (정확한 표기 포함)

**지원 항목**:
- 카메라 브랜드: 소니, 캐논, 파나소닉, JVC, 샤프
- 믹서/스위처: 블랙매직, 로스, 뉴텍, 데이터비디오, 티비로직
- 오디오: 젠하이저, 슈어, Audio-Technica, Rode, Zoom
- 모델명: PMW-500, LVM-180A, ECO8000, SPG9000 등
- 일반 용어: NVR, SDI, HDMI, UPS, LED, CCU 등

#### `app/rag/domain_synonyms.py` (151줄, 4.6KB)
```python
"""도메인 동의어 관리 모듈

SEARCH_CONTENT_ONLY 모드에서 브랜드/모델명의 한영/대소문자 변형을 처리합니다.
"""

# Lazy loading + Singleton pattern
_SYNONYM_DICT: Dict[str, List[str]] = {}
_LOADED = False

def expand_for_strict_content(query: str) -> str:
    """동의어 확장 메인 함수"""
    # 티비로직 → 티비로직 TVLogic TVLOGIC TV Logic tvlogic
    ...

def get_synonyms(keyword: str) -> List[str]:
    """특정 키워드의 동의어 리스트 반환"""
    ...

def reload_synonyms():
    """강제 재로드 (테스트/디버깅용)"""
    ...
```

**특징**:
- Lazy loading: 첫 호출 시 한 번만 YAML 로드
- 캐싱: 메모리에 flat dict로 저장하여 빠른 조회
- Fail-safe: YAML 로드 실패 시 빈 사전 반환, 시스템 정지 안 함

### 2. 수정된 파일

#### `app/rag/pipeline.py`
**제거**:
- `DOMAIN_SYNONYMS` 딕셔너리 (100+ 줄)
- `expand_for_strict_content()` 함수 정의

**추가**:
```python
from app.rag.domain_synonyms import expand_for_strict_content
```

**결과**: 코드 라인 수 감소, 역할 명확화 (파이프라인 로직에만 집중)

### 3. 테스트 파일

#### `tests/test_domain_synonyms.py` (158줄)
```python
class TestDomainSynonyms:
    """기본 동작 테스트"""
    def test_tvlogic_expansion(self): ...
    def test_sennheiser_expansion(self): ...
    def test_blackmagic_expansion(self): ...
    # ...

class TestGetSynonyms:
    """시소러스 조회 테스트"""
    def test_get_synonyms_tvlogic(self): ...
    def test_get_synonyms_case_insensitive(self): ...
    # ...

class TestEdgeCases:
    """엣지 케이스 테스트"""
    def test_empty_query(self): ...
    def test_no_synonyms_keyword(self): ...
    # ...

class TestYAMLLoading:
    """YAML 로딩 검증"""
    def test_yaml_loads_successfully(self): ...
    def test_known_brands_exist(self): ...
```

**테스트 결과**: 14/14 통과 ✅

---

## 🧪 검증 결과

### 1. 기능 테스트

| 테스트 케이스 | 입력 | 출력 | 상태 |
|-------------|------|------|------|
| 티비로직 확장 | "티비로직 모니터 확인" | "티비로직 TVLogic TVLOGIC TV Logic tvlogic 모니터 확인" | ✅ |
| 젠하이저 확장 | "젠하이저 마이크 문제" | "젠하이저 Sennheiser SENNHEISER sennheiser 마이크 문제" | ✅ |
| 블랙매직 확장 | "블랙매직" | "블랙매직 Blackmagic BlackMagic BLACKMAGIC Black Magic Black-Magic blackmagic" | ✅ |
| PMW-500 확장 | "PMW-500 카메라" | "PMW-500 PMW500 pmw-500 pmw500 카메라" | ✅ |
| ECO8000 확장 | "ECO8000 싱크" | "ECO8000 ECO-8000 eco8000 eco-8000 에코8000 싱크" | ✅ |

### 2. 통합 테스트

```bash
✅ RAGPipeline import 성공
✅ expand_for_strict_content는 domain_synonyms 모듈에서 import됨
✅ SEARCH_CONTENT_ONLY 모드 라우팅 정상 동작
✅ 14개 단위 테스트 모두 통과
```

### 3. 예외 처리 검증

| 예외 상황 | 처리 방식 | 로그 레벨 |
|----------|----------|----------|
| YAML 파일 없음 | 빈 사전 반환 + 경고 | WARNING |
| YAML 파싱 에러 | 빈 사전 반환 + 에러 로그 | ERROR |
| 파일 읽기 에러 | 빈 사전 반환 + 에러 로그 | ERROR |
| 빈 YAML 파일 | 빈 사전 반환 + 경고 | WARNING |
| 잘못된 구조 | 해당 항목 건너뛰기 + 경고 | WARNING |
| 정상 로드 | 로드 완료 메시지 | INFO |

**결과**: 모든 경우에 시스템 정지 없이 안전하게 처리 ✅

---

## 📊 성능 영향

- **로딩 시간**: 최초 1회만 YAML 로드 (lazy loading)
- **조회 시간**: O(1) dict lookup (기존과 동일)
- **메모리**: 74개 키 × 평균 4개 동의어 ≈ 수 KB (미미한 수준)
- **파일 크기**: pipeline.py 3.3KB 감소

**결론**: 성능 영향 없음, 오히려 구조적으로 최적화에 유리

---

## 🔄 운영 가이드

### 시소러스 추가/수정 방법

1. `config/domain_synonyms.yaml` 편집
2. 해당 카테고리에 항목 추가:
   ```yaml
   audio_brands:
     새브랜드:
       - 새브랜드
       - NewBrand
       - NEWBRAND
       - newbrand
   ```
3. 저장 후 서비스 재시작 (자동 로드)

**Python 코드 수정 불필요!** ✅

### 테스트 방법

```bash
# 단위 테스트
PYTHONPATH=/home/wnstn4647/AI-CHAT \
.venv/bin/pytest tests/test_domain_synonyms.py -v

# 수동 테스트
python3 -c "
from app.rag.domain_synonyms import expand_for_strict_content
print(expand_for_strict_content('새브랜드 테스트'))
"
```

### 모니터링 포인트

1. **YAML 로드 실패 감지**:
   ```bash
   grep "동의어 사전 로드 실패" logs/*.log
   ```

2. **시소러스 사용 빈도** (향후 추가 가능):
   - 어떤 브랜드가 자주 검색되는지
   - 미등록 브랜드 발견 시 YAML에 추가

---

## 📝 Git Commit Log

### Commit 1: 리팩토링 (3a95d13)
```
refactor: extract domain synonyms to YAML-backed module

- Extract DOMAIN_SYNONYMS from pipeline.py to config/domain_synonyms.yaml
- Create app/rag/domain_synonyms.py with lazy-loading pattern
- Remove 100+ lines of hardcoded synonyms from pipeline.py
- Improve maintainability: YAML editing vs Python dict editing
- Support 70+ brand/model variants (TVLogic, Sennheiser, Blackmagic, etc.)
```

### Commit 2: 테스트 및 예외 처리 개선 (d88f3fc)
```
test: add unit tests for domain synonyms module

- Add 14 comprehensive tests covering:
  - Brand name expansion (티비로직→TVLogic, 젠하이저→Sennheiser, etc.)
  - Model name variants (PMW-500, ECO8000)
  - Case-insensitive synonym lookup
  - Edge cases (empty query, whitespace, non-existent keywords)
  - YAML loading validation
  - Known brands verification

- Enhance exception handling in domain_synonyms.py:
  - Specific error types: yaml.YAMLError, IOError, generic Exception
  - Detailed warning logs for malformed YAML structure
  - Fail-safe behavior: return empty dict, never crash the system

All 14 tests passing ✅
```

---

## 🎯 향후 개선 방향

### 1. 시소러스 범위 확장 (선택적)
현재는 SEARCH_CONTENT_ONLY 모드에서만 사용. 필요 시 다른 모드에도 적용 가능:
```yaml
# 모드별 시소러스 분리 예시
strict_only:
  티비로직: [...]

all_modes:
  dvr: [...]
```

### 2. 동작 모니터링 (선택적)
```python
# domain_synonyms.py에 추가 가능
def expand_for_strict_content(query: str) -> str:
    # ... 기존 코드

    # 사용 통계 기록 (optional)
    if expanded_tokens != tokens:
        logger.debug(f"시소러스 사용: {query} → {result}")
```

### 3. 자동 발견 (선택적)
문서에서 자주 등장하지만 시소러스에 없는 브랜드를 자동 감지하여 추천.

---

## ✅ 최종 체크리스트

- [x] YAML 파일 생성 및 70+ 항목 등록
- [x] domain_synonyms.py 모듈 생성 (lazy loading + caching)
- [x] pipeline.py에서 하드코딩 제거 및 import 추가
- [x] 14개 단위 테스트 작성 및 통과
- [x] 예외 처리 강화 (YAML 파싱 에러, 파일 읽기 에러 등)
- [x] 기능 검증 (티비로직, 젠하이저, 블랙매직 등 5개 케이스)
- [x] 통합 테스트 (RAGPipeline import, 라우팅 동작)
- [x] Git 커밋 (2개 커밋, 명확한 메시지)
- [x] 문서화 (본 보고서)

**상태**: 운영 투입 준비 완료 ✅

---

## 📞 문의

리팩토링 관련 문의 또는 추가 시소러스 등록 요청:
- GitHub Issues 또는 기술관리팀 내부 채널 활용
- YAML 파일 직접 수정 후 PR 제출도 가능
