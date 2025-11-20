# system_checker.py 버그 수정 보고서 (v2.0)

**작성일**: 2025-01-18
**대상 파일**: `/home/wnstn4647/AI-CHAT/utils/system_checker.py`
**버전**: CACHE_VERSION 2

---

## 개요

사용자가 지적한 4가지 핵심 버그를 모두 수정하고, 추가로 발견된 JSON 직렬화 버그도 함께 해결했습니다.

---

## 수정된 버그 목록

### 1. 캐시 로드 시 self.result 갱신 누락 ✅

**문제점**:
```python
# Before (잘못된 코드)
def check_all(self) -> CheckResult:
    if self.use_cache:
        cached = self._load_cache()
        if cached:
            return cached  # ❌ self.result는 비어있음
```

캐시를 로드한 후 바로 반환하면, `self.result`는 빈 `CheckResult()` 상태로 남아있습니다.
이로 인해 다음과 같은 시나리오에서 문제 발생:

```bash
result = checker.check_all()  # 캐시 로드
checker.to_json(Path("result.json"))  # ❌ 빈 결과 직렬화
```

**수정 내용**:
```python
# After (수정된 코드)
def check_all(self) -> CheckResult:
    if self.use_cache:
        cached = self._load_cache()
        if cached:
            self.result = cached  # ✅ self.result 갱신
            if self.verbose:
                print("📦 캐시된 결과 사용 (빠른 검증)")
                self._print_results()
            return self.result  # ✅ self.result 반환
```

**검증**:
- `test_cached_result_updates_self_result`: 캐시 로드 후 `self.result` 확인
- `test_to_json_reflects_cached_result`: JSON 출력이 캐시 내용 반영

---

### 2. logger.error(exception=e) 비표준 사용 ✅

**문제점**:
```python
# Before (잘못된 코드)
except Exception as e:
    logger.error(f"{name} 검사 실패", exception=e)  # ❌ 비표준 인터페이스
```

Python의 표준 logging 모듈은 `exception` 키워드 인자를 지원하지 않습니다.
올바른 방법은 `logger.exception()` 또는 `exc_info=True` 사용입니다.

**수정 내용**:
```python
# After (수정된 코드)
except Exception as e:
    logger.exception(f"{name} 검사 실패")  # ✅ 표준 메서드 사용
```

`logger.exception()`은 자동으로 현재 예외의 스택 트레이스를 로깅합니다.

**수정 위치**:
- `_run_parallel_checks()` (line 272)
- `_run_sequential_checks()` (line 294)

**검증**:
- `test_logger_exception_called_on_parallel_check_error`: 병렬 검사 실패 시 확인
- `test_logger_exception_called_on_sequential_check_error`: 순차 검사 실패 시 확인

---

### 3. 캐시 버전 관리 누락 ✅

**문제점**:
```python
# Before (버전 없는 캐시)
def _save_cache(self, result: CheckResult) -> None:
    with open(self.CACHE_FILE, 'wb') as f:
        pickle.dump(result, f)  # ❌ 버전 정보 없음
```

`CheckResult` 구조가 변경되면 이전 캐시를 로드할 때 오류가 발생할 수 있습니다.

**수정 내용**:

#### 3.1 캐시 버전 상수 정의
```python
class SystemChecker:
    CACHE_VERSION: int = 2  # 캐시 구조 변경 시 증가
```

#### 3.2 _save_cache() 수정
```python
def _save_cache(self, result: CheckResult) -> None:
    """캐시 저장 (버전 메타데이터 포함)"""
    try:
        payload = {
            "version": self.CACHE_VERSION,  # ✅ 버전 포함
            "result": result
        }
        with open(self.CACHE_FILE, 'wb') as f:
            pickle.dump(payload, f)
```

#### 3.3 _load_cache() 수정
```python
def _load_cache(self) -> Optional[CheckResult]:
    """캐시 로드 (버전 확인 포함)"""
    try:
        with open(self.CACHE_FILE, 'rb') as f:
            payload = pickle.load(f)

        # ✅ 버전 확인
        if not isinstance(payload, dict) or payload.get("version") != self.CACHE_VERSION:
            logger.debug("캐시 버전 불일치, 재검사 필요")
            return None

        cached_result = payload.get("result")
        return cached_result
```

**동작 방식**:
1. 버전 2 캐시 저장: `{"version": 2, "result": CheckResult(...)}`
2. 버전 1 캐시 로드 시: 버전 불일치 감지 → `None` 반환 → 재검사 실행
3. 잘못된 구조 캐시: 안전하게 무시하고 재검사

**검증**:
- `test_old_cache_version_ignored`: 구 버전 캐시 무시 확인
- `test_cache_version_in_saved_payload`: 저장된 캐시에 버전 포함 확인
- `test_invalid_cache_structure_handled`: 잘못된 구조 안전 처리 확인

---

### 4. config.py 필수 여부 정책 과도하게 엄격 ✅

**문제점**:
```python
# Before (FAIL 상태)
def check_config_files(self) -> None:
    if not config_file.exists():
        self.result.add_item(CheckItem(
            status=CheckStatus.FAIL,  # ❌ 너무 엄격
            message="config.py 파일 없음",
        ))
        return  # ❌ 검사 중단
```

실제로는 `app.config.settings` 모듈이 있으면 루트 `config.py` 없이도 동작 가능합니다.
FAIL로 처리하면 불필요한 경고가 발생합니다.

**수정 내용**:
```python
# After (WARN 상태 + 계속 진행)
def check_config_files(self) -> None:
    if not config_file.exists():
        self.result.add_item(CheckItem(
            status=CheckStatus.WARN,  # ✅ 경고로 완화
            message="config.py 파일 없음 (app.config.settings 사용 가능)",
            action="필요시 config.py 파일을 생성하세요"
        ))
        # ✅ config.py가 없어도 app.config.settings로 동작 가능하므로 계속 진행

    try:
        # app.config.settings 모듈 검증 계속 수행
        import app.config.settings as settings
        ...
```

**변경 사항**:
- `CheckStatus.FAIL` → `CheckStatus.WARN`
- `return` 제거 (검사 계속 진행)
- 메시지에 "app.config.settings 사용 가능" 추가
- action 문구를 "필요시" 같은 선택적 표현으로 변경

**검증**:
- `test_missing_config_py_is_warn_not_fail`: WARN 상태 확인
- `test_config_check_continues_without_config_py`: 검사 계속 진행 확인

---

### 5. JSON 직렬화 버그 (추가 발견) ✅

**문제점**:
테스트 중 발견된 버그입니다.

```python
# Before
def to_dict(self) -> Dict[str, Any]:
    return {
        'errors': [asdict(item) for item in self.errors],  # ❌ CheckStatus Enum 직렬화 안 됨
        ...
    }
```

`asdict()`는 `CheckStatus` Enum을 문자열로 변환하지 않아서 JSON 직렬화 실패:
```
TypeError: Object of type CheckStatus is not JSON serializable
```

**수정 내용**:

#### 5.1 CheckItem에 to_dict() 메서드 추가
```python
@dataclass
class CheckItem:
    ...

    def to_dict(self) -> Dict[str, Any]:
        """JSON 직렬화 가능한 딕셔너리로 변환"""
        return {
            'name': self.name,
            'status': self.status.name,  # ✅ Enum을 문자열로 변환 (PASS, WARN, FAIL 등)
            'message': self.message,
            'details': self.details,
            'action': self.action
        }
```

#### 5.2 CheckResult.to_dict() 수정
```python
def to_dict(self) -> Dict[str, Any]:
    """딕셔너리로 변환 (JSON 직렬화 가능)"""
    return {
        'success': self.is_success(),
        'has_warnings': self.has_warnings(),
        'errors': [item.to_dict() for item in self.errors],  # ✅ asdict 대신 to_dict
        'warnings': [item.to_dict() for item in self.warnings],
        'passed': [item.to_dict() for item in self.passed],
        'metrics': self.metrics,
        'timestamp': self.timestamp,
        'duration': self.duration
    }
```

#### 5.3 미사용 import 제거
```python
# Before
from dataclasses import dataclass, field, asdict

# After
from dataclasses import dataclass, field  # ✅ asdict 제거
```

**검증**:
- 모든 테스트에서 `to_json()` 호출 성공 확인

---

## 테스트 결과

```bash
$ .venv/bin/python3 -m pytest tests/test_system_checker_fixes.py -v --no-cov

tests/test_system_checker_fixes.py::TestCacheResultSync::test_cached_result_updates_self_result PASSED
tests/test_system_checker_fixes.py::TestCacheResultSync::test_to_json_reflects_cached_result PASSED
tests/test_system_checker_fixes.py::TestLoggerExceptionUsage::test_logger_exception_called_on_parallel_check_error PASSED
tests/test_system_checker_fixes.py::TestLoggerExceptionUsage::test_logger_exception_called_on_sequential_check_error PASSED
tests/test_system_checker_fixes.py::TestCacheVersionManagement::test_old_cache_version_ignored PASSED
tests/test_system_checker_fixes.py::TestCacheVersionManagement::test_cache_version_in_saved_payload PASSED
tests/test_system_checker_fixes.py::TestCacheVersionManagement::test_invalid_cache_structure_handled PASSED
tests/test_system_checker_fixes.py::TestConfigCheckPolicy::test_missing_config_py_is_warn_not_fail PASSED
tests/test_system_checker_fixes.py::TestConfigCheckPolicy::test_config_check_continues_without_config_py PASSED
tests/test_system_checker_fixes.py::TestIntegrationAllFixes::test_full_workflow_with_cache PASSED

============================== 10 passed in 0.81s ==============================
```

**10/10 테스트 통과** ✅

---

## 영향 범위

### 변경된 메서드
1. `SystemChecker.check_all()` - self.result 갱신 추가
2. `SystemChecker._run_parallel_checks()` - logger.exception() 사용
3. `SystemChecker._run_sequential_checks()` - logger.exception() 사용
4. `SystemChecker._load_cache()` - 버전 확인 로직 추가
5. `SystemChecker._save_cache()` - 버전 메타데이터 포함
6. `SystemChecker.check_config_files()` - WARN으로 완화
7. `CheckItem.to_dict()` - 신규 추가
8. `CheckResult.to_dict()` - JSON 직렬화 수정

### 추가된 상수
- `SystemChecker.CACHE_VERSION = 2`

### 제거된 import
- `dataclasses.asdict`

### 하위 호환성
- **캐시**: 구 버전 캐시는 자동으로 무시되고 재검사 실행 (데이터 손실 없음)
- **API**: 모든 공개 메서드 시그니처 동일 (하위 호환)
- **JSON 출력**: 형식 개선되었지만 기존 필드 유지

---

## 운영 가이드

### 캐시 버전 업그레이드 시
```python
# CheckResult 구조 변경 시 버전 증가
class SystemChecker:
    CACHE_VERSION: int = 3  # 2 → 3으로 증가
```

### 캐시 삭제
```bash
# 수동 캐시 초기화
rm -f .system_check_cache.pkl

# 또는 --no-cache 옵션 사용
python utils/system_checker.py --no-cache
```

### 로그 확인
```python
# 캐시 관련 디버그 로그 확인
[DEBUG] 캐시된 결과 로드 성공 (v2)
[DEBUG] 캐시 버전 불일치, 재검사 필요
[DEBUG] 검사 결과 캐시 저장 완료 (v2)
```

---

## 참고 자료

- **테스트 파일**: `/home/wnstn4647/AI-CHAT/tests/test_system_checker_fixes.py`
- **원본 파일**: `/home/wnstn4647/AI-CHAT/utils/system_checker.py`
- **Python logging 문서**: https://docs.python.org/3/library/logging.html#logging.Logger.exception
- **Pickle 프로토콜**: https://docs.python.org/3/library/pickle.html

---

## 요약

✅ **4가지 핵심 버그 모두 수정 완료**
✅ **추가 버그 1건 발견 및 수정**
✅ **10개 검증 테스트 모두 통과**
✅ **하위 호환성 유지**
✅ **운영 환경 배포 준비 완료**

방송 기술관리팀 시스템 검증 유틸리티가 이제 프로덕션 환경에서 안정적으로 동작할 수 있습니다.
