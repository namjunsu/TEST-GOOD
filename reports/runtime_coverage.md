
# Runtime Coverage Report

## Summary
- Total Scenarios: 20
- Passed: 15
- Failed: 5
- Success Rate: 75.0%

## Detailed Results

### Scenario 1: ✅
- Query: `2024년 문서 목록`
- Expected Mode: LIST
- Actual Mode: list
- Filters: {'year': '2024', 'drafter': None, 'source': None}
- Time: 0.009s

### Scenario 2: ❌
- Query: `2023년 최새름이 작성한 문서`
- Expected Mode: LIST
- Actual Mode: None
- Filters: None
- Time: 0.000s
- Error: 'NoneType' object has no attribute 'answer'

### Scenario 3: ✅
- Query: `year:2024 drafter:남준수`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': '2024', 'drafter': '남준수', 'source': 'token'}
- Time: 0.010s

### Scenario 4: ✅
- Query: `비용 합계 알려줘`
- Expected Mode: COST_SUM
- Actual Mode: cost_sum
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.008s

### Scenario 5: ✅
- Query: `문서 찾아줘`
- Expected Mode: LIST
- Actual Mode: list
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.009s

### Scenario 6: ❌
- Query: `2024년 11월 이후 작성된 보고서`
- Expected Mode: LIST
- Actual Mode: None
- Filters: None
- Time: 0.000s
- Error: 'NoneType' object has no attribute 'answer'

### Scenario 7: ✅
- Query: `방송 장비 관련 문서 검색`
- Expected Mode: QA
- Actual Mode: list
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.009s

### Scenario 8: ❌
- Query: `최근 3개월 문서 요약`
- Expected Mode: SUMMARY
- Actual Mode: None
- Filters: None
- Time: 0.000s
- Error: 'NoneType' object has no attribute 'answer'

### Scenario 9: ✅
- Query: `2024-12-16_방송_프로그램_제작용_건전지_소모품_구매의_건.pdf 내용`
- Expected Mode: PREVIEW
- Actual Mode: preview
- Filters: {'year': '2024', 'drafter': None, 'source': None}
- Time: 0.008s

### Scenario 10: ❌
- Query: `김철수가 작성한 문서`
- Expected Mode: LIST
- Actual Mode: None
- Filters: None
- Time: 0.000s
- Error: 'NoneType' object has no attribute 'answer'

### Scenario 11: ✅
- Query: ``
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.007s

### Scenario 12: ✅
- Query: `year:9999`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': '9999', 'drafter': None, 'source': 'token'}
- Time: 0.007s

### Scenario 13: ✅
- Query: `drafter:!!!@@@`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.007s

### Scenario 14: ✅
- Query: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.010s

### Scenario 15: ✅
- Query: `SELECT * FROM documents`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.007s

### Scenario 16: ✅
- Query: `문서`
- Expected Mode: LIST
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.008s

### Scenario 17: ❌
- Query: `2020년 문서`
- Expected Mode: LIST
- Actual Mode: None
- Filters: None
- Time: 0.000s
- Error: 'NoneType' object has no attribute 'answer'

### Scenario 18: ✅
- Query: `년`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.008s

### Scenario 19: ✅
- Query: `최 새 름`
- Expected Mode: LIST
- Actual Mode: qa
- Filters: {'year': None, 'drafter': None, 'source': None}
- Time: 0.007s

### Scenario 20: ✅
- Query: `YEAR:2024 DRAFTER:남준수`
- Expected Mode: QA
- Actual Mode: qa
- Filters: {'year': '2024', 'drafter': '남준수', 'source': 'token'}
- Time: 0.008s
