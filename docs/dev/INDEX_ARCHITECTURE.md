# 인덱스 아키텍처 및 doc_id 규격

## 개요

본 시스템의 모든 인덱스 계층(DocStore, BM25, FAISS)은 **단일 원천 doc_id 규격**을 공유합니다.

**최종 업데이트**: 2025-11-19 (P0: 정합성 통합 완료)

---

## doc_id 정식 규격

### 원천 시스템

```text
metadata.db (SQLite)
  └─ documents 테이블
       └─ id INTEGER PRIMARY KEY AUTOINCREMENT
```

### 규칙

1. **정식 doc_id = `str(metadata.db.documents.id)`**
2. 모든 인덱스 계층은 이 값을 **문자열**로 사용
3. `id` 필드가 없는 문서는 **구조적 오류**로 간주

### 예시

```python
# DB
id = 4148  # INTEGER PK

# BM25 / FAISS / 로그
doc_id = "4148"  # str(id)
```

---

## 인덱스 계층별 구현

### 1. DocStore (metadata.db)

- **역할**: 단일 진실 원천 (Single Source of Truth)
- **키**: `id` (INTEGER, AUTO_INCREMENT)
- **저장 내용**: 메타데이터(filename, date, drafter, category 등)

### 2. BM25 인덱스 (var/index/bm25_index.pkl)

- **역할**: 키워드 기반 전문 검색
- **키**: metadata["id"]를 문자열로 변환
- **구현**: `rag_system/active/bm25_store.py::_resolve_doc_id()`

```python
def _resolve_doc_id(metadata: dict, doc_idx: int) -> str:
    """DocStore/BM25/FAISS 공통 doc_id 생성 규칙"""
    db_id = metadata.get("id")
    if db_id is None:
        raise ValueError(f"metadata['id'] 누락 (doc_idx={doc_idx})")
    return str(db_id)
```

### 3. FAISS 벡터 인덱스 (향후 구축 시)

- **역할**: 의미론적 검색 (semantic search)
- **키**: BM25와 동일한 규칙 (`_resolve_doc_id()` 재사용 필수)
- **주의**: FAISS 구축 시 반드시 동일 doc_id 사용

---

## 정합성 검증

### 자동 검증 도구

```bash
python scripts/check_index_consistency.py
```

### 정상 상태 기준

```text
✅ 정합성 점수: 100.00%
✅ DocStore 키 = BM25 키 (완전 일치)
⚠️ FAISS 벡터 수: 0 (구축 전이면 정상)
```

### 정합성 점수 < 100% 시 대응

#### 원인 분류

1. **DocStore에만 있음** -> BM25 재인덱싱 필요
2. **BM25에만 있음** -> DB에서 삭제된 문서, 인덱스 클린업 필요
3. **키 형식 불일치** -> doc_id 생성 로직 점검 (`_resolve_doc_id()` 확인)

#### 대응 절차

```bash
# 1. 인덱스 백업
cp -r var/index var/index_backup_$(date +%Y%m%d_%H%M%S)

# 2. 재인덱싱
python scripts/reindex_atomic.py

# 3. 정합성 재검증
python scripts/check_index_consistency.py

# 4. 점수 확인
cat reports/index_consistency.md
```

---

## 인덱싱 파이프라인

### 전체 흐름

```text
metadata.db (id, filename, ...)
    |
reindex_atomic.py
    | SELECT id, filename, ... FROM documents
    |
BM25Store.add_documents(texts, metadatas)
    | metadatas = [{'id': 4148, 'filename': ...}, ...]
    |
var/index/bm25_index.pkl
    | metadata: [{'id': '4148', ...}, ...]
```

### 핵심 체크포인트

1. **DB 쿼리 시 `id` 필드 포함 필수**

   ```python
   cursor.execute("SELECT id, filename, ... FROM documents")
   ```

2. **metadata 딕셔너리에 `id` 전달**

   ```python
   metadatas.append({
       'id': doc_meta.get('id'),  # DB PK
       'filename': filename,
       ...
   })
   ```

3. **BM25 검색 결과에 doc_id 포함**

   ```python
   result = {
       "rank": 1,
       "score": 2.87,
       **metadata  # id 필드 포함됨
   }
   ```

---

## 디버깅 가이드

### doc_id 추적

```python
# 1. DB에서 확인
sqlite3 metadata.db "SELECT id, filename FROM documents WHERE id=4148"

# 2. BM25 인덱스에서 확인
python3 -c "
import pickle
with open('var/index/bm25_index.pkl', 'rb') as f:
    data = pickle.load(f)
    match = [m for m in data['metadata'] if m.get('id') == '4148']
    print(match)
"

# 3. 검색 결과에서 확인
# → result['id'] == '4148' 인지 체크
```

### 로그 분석

모든 계층에서 동일 doc_id가 출력되어야 함:

```text
[INFO] metadata.db 조회: id=4148
[INFO] BM25 인덱싱: doc_id=4148
[INFO] 검색 결과: doc_id=4148, score=2.87
```

---

## 핵심 원칙

### doc_id 단일 원천 원칙

```text
doc_id는 외부에서 임의로 생성·가공하지 않는다.
반드시 DocStore(metadata.db)에서 온 값을 _resolve_doc_id()로 통일한다.
```

**이유**:

- 모든 인덱스 계층(BM25, FAISS, 로그)이 동일 키로 문서 추적 가능
- 디버깅 시 단일 doc_id로 전체 파이프라인 트레이싱 가능
- 향후 인덱스 추가 시에도 정합성 보장

## 주의사항

### 절대 금지

1. **doc_id 생성 로직 임의 변경 금지**
   - `_resolve_doc_id()` 함수 수정 시 전체 재인덱싱 필요
   - 변경 전 반드시 아키텍처 리뷰 필요

2. **다른 ID 체계 혼용 금지**
   - `f"doc_{idx}"` 같은 순서 기반 ID 금지
   - filename을 doc_id로 사용 금지
   - metadata.db PK만 사용
   - 새 인덱스 추가 시 `_resolve_doc_id()` 재사용

3. **FAISS 구축 시 별도 ID 사용 금지**
   - 반드시 `_resolve_doc_id()` 재사용
   - BM25와 다른 ID 사용 시 하이브리드 검색 불가

### 권장 사항

1. **새 인덱스 추가 시**
   - `_resolve_doc_id()` 함수 공용으로 사용
   - 정합성 검증 스크립트에 해당 인덱스 추가

2. **리팩토링 시**
   - 회귀 테스트로 doc_id 일관성 확인
   - 정합성 점수 100% 유지 확인

---

## 히스토리

### v2025-11-19 (P0 완료)

- **문제**: DocStore와 BM25 키 형식 불일치 (정합성 33.33%)
  - DocStore: 숫자 ID (4148, 4149, ...)
  - BM25: doc_ 접두사 (doc_1, doc_2, ...)
- **해결**:
  - `_resolve_doc_id()` 함수 도입
  - reindex_atomic.py 수정 (DB PK 전달)
  - 정합성 100% 달성
- **영향**:
  - 디버깅 난이도 감소
  - FAISS 도입 준비 완료
  - 정합성 리포트 신뢰도 확보

### 향후 계획 / 확장 시 주의사항

#### P1: 텍스트 품질 개선

- **작업**: 누락/저품질 문서 OCR 재처리 -> 재인덱싱
- **doc_id 영향**: **없음**
  - 같은 문서의 텍스트만 교체되므로 doc_id 불변
  - 재인덱싱 후에도 정합성 100% 유지됨

#### P2: FAISS 벡터 인덱스 구축

- **작업**: 의미론적 검색을 위한 임베딩 인덱스 추가
- **doc_id 규칙**: 동일 규격 필수

  ```python
  # FAISS 인덱싱 시
  for doc_meta in documents:
      doc_id = _resolve_doc_id(doc_meta, idx)  # 반드시 재사용
      embedding = embed(doc_meta['text'])
      faiss_index.add_with_ids(embedding, [int(doc_id)])
  ```

- **정합성**: DocStore <-> BM25 <-> FAISS 3-way 일치 필요

#### 운영 모니터링

- **정합성 점수 자동 검증**
  - 재인덱싱 후 자동으로 `scripts/check_index_consistency.py` 실행
  - 점수 < 100% 시 경고 발생
  - CI/CD 파이프라인에 통합 권장

- **정합성 점수 해석**
  - 100%: 정상
  - < 100%: 인덱스 계층 간 불일치 발생 -> 재인덱싱 필요
  - 0%: 심각한 구조적 문제 -> 즉시 점검
