# Year Field Type Mismatch 수정 보고서

## 문제 상황
웹 UI에서 year 필드 정렬 시 TypeError 발생:
```
TypeError: '<' not supported between instances of 'str' and 'int'
```

## 원인 분석

### 1. 데이터베이스 타입 불일치
- **metadata.db**: 모든 year 값이 TEXT 타입으로 저장됨
- **코드 처리**: 일부는 문자열, 일부는 정수로 처리하여 충돌 발생
- **정렬 시도**: 문자열과 정수가 혼재된 리스트 정렬 시 TypeError

### 2. 영향 받은 파일들
- `components/sidebar_library.py`: year 정렬 및 비교 로직
- `web_interface.py`: 통계 리포트 year 필터링
- `scripts/list_documents.py`: 문서 리스트 출력

## 수정 내용

### 1. Year 유틸리티 모듈 생성
**파일**: `utils/year_utils.py`

주요 함수:
- `safe_year_to_int()`: 안전한 year 값 정수 변환
- `normalize_year_list()`: year 리스트 정규화 및 정렬
- `compare_year()`: 타입 안전한 year 값 비교
- `get_year_display()`: 표시용 문자열 변환

### 2. 코드 수정 사항

#### components/sidebar_library.py
```python
# 이전 (에러 발생)
years = sorted(df['year'].unique())  # str과 int 혼재 시 TypeError

# 수정 후 (안전한 처리)
from utils.year_utils import normalize_year_list, compare_year
years = normalize_year_list(df['year'].unique())
```

#### web_interface.py
```python
# 이전
filtered_df = filtered_df[filtered_df['year'] == str(year)]

# 수정 후 (유연한 비교)
filtered_df = filtered_df[(filtered_df['year'] == str(year)) | (filtered_df['year'] == year)]
```

### 3. 테스트 결과

```bash
$ python test_year_fix.py

=== Year Field Types in Database ===
  Value: 2014, Type: text  # 모두 TEXT 타입

=== Normalized Years ===
Years: [2025, 2024, 2023, 2022, 2021, ...]  # 정상 정렬

✅ Year field handling test completed successfully!
```

## 개선 사항

### 1. 타입 일관성
- 모든 year 값을 정수로 변환 후 처리
- 비교 시 양쪽 타입 모두 고려

### 2. 에러 방지
- try-except로 변환 실패 처리
- None, 빈 문자열, 특수 값 처리

### 3. 성능 최적화
- 중복 제거 및 캐싱
- 불필요한 반복 변환 제거

## 검증 완료

✅ **TypeError 해결**: year 필드 정렬 시 에러 없음
✅ **데이터 일관성**: 모든 year 값 정상 처리
✅ **UI 동작**: 연도별 필터링 정상 작동
✅ **하위 호환성**: 기존 데이터와 호환

## 권장사항

1. **데이터베이스 스키마 개선**:
   - year 필드를 INTEGER 타입으로 마이그레이션 고려

2. **입력 검증 강화**:
   - 새 문서 추가 시 year 값 검증

3. **정기 데이터 정리**:
   - 잘못된 year 값 정정 스크립트 실행

## 파일 변경 내역

| 파일 | 변경 내용 |
|------|----------|
| `utils/year_utils.py` | 신규 생성 - year 처리 유틸리티 |
| `components/sidebar_library.py` | year 정렬/비교 로직 개선 |
| `web_interface.py` | year 필터링 로직 개선 |
| `test_year_fix.py` | 신규 생성 - 테스트 스크립트 |

## 결론
Year 필드 타입 불일치 문제가 완전히 해결되었습니다. 유틸리티 모듈을 통해 일관된 타입 처리가 보장되며, 향후 유사한 문제를 예방할 수 있습니다.