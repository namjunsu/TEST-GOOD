# RAG 시스템 문제 진단 및 해결 방안

**작성일**: 2025-10-25
**현상**: 질문을 하면 관련 문서가 있는데도 "없다"고 답변이 나옴

---

## 📋 요약

**핵심 문제**: **다단계 필터링 시스템이 검색 결과를 과도하게 필터링**하여 top_k=5를 요청해도 1개만 반환합니다.

**영향도**: 🔴 **심각** - 시스템이 정상 작동하지 않음

---

## 🔍 발견된 문제점

### 1. **다단계 필터링의 과도한 필터링** ⚠️ **가장 심각**

**증상**:
```
검색 요청: top_k=3
실제 반환: 1개

Phase 1: 1 → 1 후보 추출
Phase 2: 1 → 1 키워드 강화
Phase 3: 1 → 1 순위 재조정
Phase 4: 1 → 1 적응형 선택 (simple, k=1)
```

**원인**:
- `rag_system/hybrid_search.py`에서 `use_multilevel_filter=False` 설정이 무시됨
- 다단계 필터링 시스템이 기본적으로 활성화되어 있음
- Phase 4의 "적응형 선택"이 간단한 쿼리를 "simple" 모드로 판단하여 k=1로 강제 변경

**영향**:
- 사용자가 top_k=5를 설정해도 1개만 검색됨
- 관련 문서가 많이 있어도 1개만 반환되므로 LLM이 충분한 context를 받지 못함
- 결과적으로 "관련 문서가 없다"는 답변 생성

**해결 방안**:
```python
# app/rag/retrievers/hybrid.py
HybridRetriever(
    use_reranker=False,
    use_query_expansion=False,
    use_document_compression=False,
    use_multilevel_filter=False  # 🔥 이 옵션이 제대로 적용되도록 수정 필요
)
```

### 2. **snippet 정보 손실** ⚠️ **중요**

**증상**:
```
검색 결과: 1개
  1. doc_4429
     점수: 0.3868
     미리보기: ...  ← 비어있음!
```

**원인**:
- 검색 결과에 snippet 필드가 포함되지 않음
- `hybrid_search.py`에서 snippet을 생성하지 않거나 전달하지 않음

**영향**:
- LLM이 문서 내용을 볼 수 없어서 답변 생성 불가
- Evidence에도 빈 snippet이 표시됨

**해결 방안**:
- 검색 결과에 snippet 생성 로직 추가
- MetadataDB에서 content를 가져와서 snippet으로 사용

### 3. **환경 변수가 로드되지 않음**

**증상**:
```
USE_V2_RETRIEVER: NOT SET
SEARCH_VECTOR_WEIGHT: NOT SET
SEARCH_BM25_WEIGHT: NOT SET
DIAG_RAG: NOT SET
```

**원인**:
- Python 스크립트가 `.env` 파일을 자동으로 로드하지 않음
- `python-dotenv` 패키지가 있지만 `load_dotenv()`를 호출하지 않음

**영향**:
- `.env`에 설정한 값들이 적용되지 않음
- 기본값으로 실행됨

**해결 방안**:
```python
# config.py 또는 main entry point에 추가
from dotenv import load_dotenv
load_dotenv()
```

### 4. **LLM 로드 실패** (부차적)

**증상**:
```
ERROR: llama-cpp-python 패키지가 설치되지 않았습니다.
```

**원인**:
- `llama-cpp-python` 패키지가 설치되지 않았거나 import 실패

**영향**:
- 검색 결과를 그대로 반환 (폴백 모드)
- LLM 요약 없이 검색 결과만 표시

---

## 🎯 근본 원인 분석

### 시스템이 복잡해진 이유:

1. **과도한 최적화 시도**
   - 쿼리 확장, 다단계 필터링, 재랭킹 등 너무 많은 기능 추가
   - 각 기능이 독립적으로 작동하지 않고 서로 간섭

2. **설정 옵션이 적용되지 않음**
   - `use_multilevel_filter=False` 설정이 무시됨
   - 환경 변수가 로드되지 않아서 의도한 설정이 적용되지 않음

3. **디버깅 정보 부족**
   - 검색 결과가 왜 1개만 나오는지 추적하기 어려움
   - snippet이 왜 비어있는지 확인하기 어려움

### 질문 → 답변 플로우 분석:

```
1. 사용자 질문: "카메라 수리"
   ↓
2. RAGPipeline.answer() 호출
   ↓
3. HybridRetriever.search(query="카메라 수리", top_k=3)
   ↓
4. HybridSearch.search() → 다단계 필터링 적용
   ↓
5. Phase 4: 적응형 선택 → k=1로 강제 변경 ⚠️ 문제!
   ↓
6. 1개 결과만 반환 (snippet 비어있음) ⚠️ 문제!
   ↓
7. Generator.generate() → LLM에 빈 context 전달
   ↓
8. LLM: "관련 문서가 없다" 답변 생성 ❌
```

---

## ✅ 해결 방안

### 우선순위 1: **다단계 필터링 비활성화**

**파일**: `rag_system/hybrid_search.py`

**수정 위치**:
```python
# rag_system/hybrid_search.py (라인 60-70 부근)
class HybridSearch:
    def __init__(self, ..., use_multilevel_filter=False):
        # ...
        # 🔥 이 부분을 강제로 False로 설정
        self.use_multilevel_filter = False  # 항상 비활성화

        # 또는 초기화 부분에서 필터 객체를 생성하지 않음
        if use_multilevel_filter:
            self.multilevel_filter = MultilevelFilter()
        else:
            self.multilevel_filter = None  # 🔥 None으로 설정
```

**검증 방법**:
```bash
python3 diagnose_rag.py
# 검색 결과가 3개 이상 나와야 함
```

### 우선순위 2: **snippet 생성 추가**

**파일**: `rag_system/hybrid_search.py` 또는 `app/rag/retrievers/hybrid.py`

**수정 위치**:
```python
# app/rag/retrievers/hybrid.py의 search() 메서드
def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    # ...
    for r in results:
        # 기존 코드
        normalized.append({
            "doc_id": r.get("doc_id", "unknown"),
            "page": r.get("page", 1),
            "score": r.get("score", 0.0),
            "snippet": r.get("snippet", r.get("content", "")[:200]),  # 🔥 이미 있음
            # ...
        })

    # 🔥 snippet이 비어있으면 DB에서 content 가져오기
    for item in normalized:
        if not item["snippet"] or item["snippet"] == "":
            # MetadataDB에서 content 가져오기
            content = self.db.get_content(item["doc_id"])
            item["snippet"] = content[:500] if content else "(내용 없음)"
```

### 우선순위 3: **환경 변수 로딩**

**파일**: `config.py` 또는 진입점 파일들

**추가 코드**:
```python
# config.py 최상단에 추가
from dotenv import load_dotenv
load_dotenv()  # .env 파일 로드
```

### 우선순위 4: **HybridRetriever 설정 강제 적용**

**파일**: `app/rag/pipeline.py`

**수정 위치**:
```python
# app/rag/pipeline.py의 _create_default_retriever()
def _create_default_retriever(self) -> Retriever:
    from app.rag.retrievers.hybrid import HybridRetriever
    retriever = HybridRetriever(
        use_reranker=False,              # 재랭킹 비활성화
        use_query_expansion=False,        # 쿼리 확장 비활성화
        use_document_compression=False,   # 문서 압축 비활성화
        # 🔥 추가: 다단계 필터링도 명시적으로 비활성화
        use_multilevel_filter=False,
    )
    return retriever
```

---

## 🧪 테스트 계획

### 1. 검색 결과 개수 확인
```bash
python3 -c "
from app.rag.pipeline import RAGPipeline
p = RAGPipeline()
results = p.retriever.search('카메라', top_k=5)
print(f'검색 결과: {len(results)}개')
assert len(results) >= 3, '검색 결과가 3개 미만!'
"
```

### 2. snippet 확인
```bash
python3 -c "
from app.rag.pipeline import RAGPipeline
p = RAGPipeline()
results = p.retriever.search('카메라', top_k=5)
for r in results[:3]:
    print(f'{r[\"doc_id\"]}: {len(r.get(\"snippet\", \"\"))} 글자')
    assert len(r.get('snippet', '')) > 0, 'snippet이 비어있음!'
"
```

### 3. 전체 RAG 테스트
```bash
python3 -c "
from app.rag.pipeline import RAGPipeline
p = RAGPipeline()
result = p.answer('카메라 수리', top_k=5)
print(result['text'][:200])
assert '관련 문서' not in result['text'] or '찾을 수 없' not in result['text']
"
```

---

## 📊 기대 효과

수정 후 예상 동작:

```
사용자 질문: "카메라 수리"
  ↓
검색: 5개 문서 검색 (다단계 필터링 비활성화)
  ↓
snippet: 각 문서에서 500자 추출
  ↓
LLM: 5개 문서 context 기반 답변 생성
  ↓
답변: "카메라 수리 관련 문서가 5개 발견되었습니다.
       2023-12-28 오픈스튜디오 카메라 케이블 수리 건은..."
```

---

## 🚀 다음 단계

1. ✅ 문제 진단 완료
2. ⏳ **다단계 필터링 비활성화 수정**
3. ⏳ **snippet 생성 로직 추가**
4. ⏳ 환경 변수 로딩 추가
5. ⏳ 테스트 및 검증
6. ⏳ 시스템 단순화 (장기 과제)

---

## 💡 장기적 개선 방안

### 시스템 단순화:

1. **불필요한 기능 제거**
   - 다단계 필터링 완전 제거
   - 쿼리 확장 선택적 활성화
   - 재랭킹 선택적 활성화

2. **명확한 설정 관리**
   - 모든 설정을 `.env`로 통합
   - 설정 우선순위 명확화
   - 설정 검증 로직 추가

3. **디버깅 개선**
   - 검색 결과 로깅 강화
   - snippet 생성 과정 로깅
   - 필터링 단계별 로깅

4. **테스트 추가**
   - 검색 결과 개수 테스트
   - snippet 생성 테스트
   - E2E RAG 테스트
