# 질문-답변 문제 진단 결과

## 🔴 문제 발견!

### 테스트 케이스
```
질문: "2024년 문서 찾아줘"
```

### 실행 결과
```
📋 목록 검색: year=2024, drafter=문서, limit=20
응답: 검색 결과가 없습니다. (year=2024, drafter=문서)
```

## 🎯 문제 원인

### 1. 잘못된 파싱
**파일**: `app/rag/pipeline.py` → `_answer_list()` 메소드

쿼리 파싱 로직이 "문서"를 **기안자(drafter)**로 잘못 인식:
- 입력: "2024년 문서 찾아줘"
- 파싱 결과:
  - year=2024 ✅ (정상)
  - drafter=**문서** ❌ (오류!)

### 2. 검색 실패
```python
# 실제 실행된 쿼리
db.search_documents(year=2024, drafter="문서", limit=20)
# → 결과: 0개 (당연히 "문서"라는 이름의 기안자는 없음)
```

### 3. 기대 동작
```python
# 올바른 쿼리
db.search_documents(year=2024, drafter=None, limit=20)
# → 결과: 2024년의 모든 문서
```

## 🔍 코드 분석

### 문제 코드 위치
`app/rag/pipeline.py` - `_answer_list()` 메소드

```python
def _answer_list(self, query: str) -> dict:
    # 쿼리 파싱
    # ⚠️ 문제: "문서", "자료" 같은 일반 명사를 기안자로 인식
    drafter = self._parse_drafter(query)  # ← 여기서 "문서" 추출
    year = self._parse_year(query)
```

### 파싱 로직의 문제점
"문서", "자료", "파일" 같은 일반 키워드를 기안자 이름으로 잘못 인식할 가능성:
- "2024년 문서 찾아줘" → drafter="문서"
- "김철수 자료 찾아줘" → drafter="자료"? or "김철수"?
- "보고서 검색해줘" → drafter="보고서"?

## 💡 해결 방안

### 방안 1: 불용어 필터링 (추천)
일반 명사를 기안자에서 제외:

```python
# 기안자로 인식하지 말아야 할 단어들
STOPWORDS = {
    "문서", "자료", "파일", "보고서", "데이터",
    "리스트", "목록", "검색", "찾기", "조회"
}

def _parse_drafter(self, query: str) -> Optional[str]:
    # ... 기존 로직 ...
    if drafter in STOPWORDS:
        return None
    return drafter
```

### 방안 2: 패턴 우선순위 조정
명시적 패턴만 인식:
```python
# 명확한 패턴만 인식
DRAFTER_PATTERNS = [
    r"(.+?)가\s*작성",  # "김철수가 작성"
    r"(.+?)님\s*문서",  # "김철수님 문서"
    r"작성자[:\s]+(.+)",  # "작성자: 김철수"
]
```

### 방안 3: 메타데이터 검증
파싱된 기안자가 실제 DB에 존재하는지 확인:

```python
def _parse_drafter(self, query: str) -> Optional[str]:
    drafter = self._extract_drafter(query)

    # DB에 실제 존재하는 기안자인지 확인
    if drafter:
        exists = self.metadata_db.drafter_exists(drafter)
        if not exists:
            logger.warning(f"기안자 '{drafter}'가 DB에 없음 - 무시")
            return None

    return drafter
```

## 🔧 즉시 수정 필요 사항

### 1. _parse_drafter 함수 수정
**위치**: `app/rag/pipeline.py`

현재 로직을 보고 불용어 필터 추가

### 2. 테스트 케이스 추가
```python
# 테스트해야 할 쿼리들
test_queries = [
    ("2024년 문서 찾아줘", {"year": 2024, "drafter": None}),
    ("김철수가 작성한 문서", {"year": None, "drafter": "김철수"}),
    ("2023년 보고서 검색", {"year": 2023, "drafter": None}),
]
```

### 3. 로깅 개선
파싱 결과를 명확히 로깅:
```python
logger.info(f"📋 파싱 결과: year={year}, drafter={drafter} (쿼리: '{query}')")
```

## 📊 영향 범위

### 영향 받는 기능
- LIST 모드 (목록 검색)
- 연도별 문서 검색
- 기안자별 문서 검색

### 정상 작동하는 기능
- COST_SUM 모드 (비용 합계)
- SUMMARY 모드 (요약)
- PREVIEW 모드 (미리보기)
- QA 모드 (일반 질의응답)

## 🎯 다음 단계

1. **즉시 수정**: `_parse_drafter()` 함수에 불용어 필터 추가
2. **테스트**: 다양한 쿼리 패턴으로 검증
3. **모니터링**: 실제 사용자 쿼리에서 파싱 오류 추적

## 검증 명령어

```bash
# 라우팅 테스트
python diagnose_qa_flow.py "2024년 문서 찾아줘" --route-only

# 전체 테스트
python diagnose_qa_flow.py "2024년 문서 찾아줘"

# 다양한 패턴 테스트
python diagnose_qa_flow.py "김철수 문서"
python diagnose_qa_flow.py "2023년 보고서"
python diagnose_qa_flow.py "박영희가 작성한 자료"
```