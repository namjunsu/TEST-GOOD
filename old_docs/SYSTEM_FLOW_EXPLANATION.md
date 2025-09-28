# 🔄 AI-CHAT 시스템 작동 방식 완전 분석

## 📌 핵심 요약
**이 시스템은 전통적인 RAG(Retrieval-Augmented Generation)이 아닙니다!**
- BM25, Vector Search 등을 사용하지 않음
- 단순한 텍스트 매칭 + LLM 요약 방식
- 문서 검색은 파일명/키워드 매칭으로만 작동

---

## 🎯 질문-답변 플로우 (실제 작동 방식)

### 1단계: 사용자가 질문 입력
```
예시: "2020년 중계차 보수 내용 알려줘"
```

### 2단계: 검색 모드 결정 (`_classify_search_intent`)
```python
def _classify_search_intent(self, query: str) -> str:
    return 'document'  # 항상 document 모드 반환 (Asset 모드 제거됨)
```

### 3단계: 문서 찾기 (`find_best_document`)
**단순 텍스트 매칭 방식**:
```python
def find_best_document(self, query: str) -> Optional[Path]:
    # 1. 연도 추출 (2020)
    # 2. 키워드 추출 (중계차, 보수)
    # 3. 480개 PDF 파일명과 비교
    # 4. 점수 계산:
    #    - 연도 일치: +20점
    #    - 월 일치: +30점
    #    - 키워드 일치: 길이×2점
    #    - 부분 일치: +3점
    # 5. 최고 점수 파일 선택
```

**실제 사용 기술**:
- ❌ BM25 (사용 안함)
- ❌ Vector Embedding (사용 안함)
- ❌ Semantic Search (사용 안함)
- ✅ 파일명 텍스트 매칭
- ✅ 정규식 패턴 매칭
- ✅ 단순 점수 계산

### 4단계: PDF 내용 추출 (`_extract_full_pdf_content`)
```python
# 1. PyPDF2로 텍스트 추출 (최대 50페이지)
# 2. 실패 시 pdfplumber 사용
# 3. 그래도 실패 시 OCR (Tesseract) 사용
```

### 5단계: LLM 요약 생성 (`_generate_llm_summary`)
```python
# 1. PDF에서 추출한 텍스트 (최대 15,000자)
# 2. 프롬프트 생성 (템플릿 방식)
# 3. LLM 호출 (Qwen2.5-7B)
self.llm.generate_response(prompt, context_chunks)
# 4. 응답 포맷팅
```

### 6단계: 응답 반환
```
📄 선택된 문서: 2020-03-17_중계차_보수.pdf

[응답 내용]
• 기안자: 김XX
• 날짜: 2020-03-17
• 주요 내용: 중계차 도어 파손, 발전기 노후화...
• 비용: 2억 5천만원

📎 출처: 2020-03-17_중계차_보수.pdf
```

---

## ❓ 왜 전통적 RAG가 아닌가?

### 전통적 RAG 시스템:
1. **Document Chunking**: 문서를 작은 조각으로 분할
2. **Embedding**: 각 조각을 벡터로 변환
3. **Vector DB**: 벡터 저장 (Faiss, Chroma 등)
4. **Similarity Search**: 질문과 유사한 벡터 검색
5. **Reranking**: 검색 결과 재순위
6. **Context 생성**: 관련 조각들 조합
7. **LLM 생성**: 컨텍스트 기반 답변

### 현재 시스템:
1. **파일명 매칭**: 480개 PDF 파일명과 단순 비교
2. **점수 계산**: 키워드 일치 개수로 점수
3. **최고 점수 선택**: 1개 문서만 선택
4. **전체 추출**: 선택된 PDF 전체 텍스트 추출
5. **LLM 요약**: 전체 내용을 LLM에 전달

---

## 🗂️ 파일 구조와 역할

### 실제 사용 중인 파일:
```
perfect_rag.py (213KB)
├── find_best_document()      # 파일명 매칭
├── _extract_full_pdf_content() # PDF 텍스트 추출
├── _generate_llm_summary()    # LLM 요약
└── answer()                   # 메인 진입점

rag_system/
├── qwen_llm.py               # LLM 인터페이스 ✅
├── llm_singleton.py          # 싱글톤 패턴 ✅
└── enhanced_ocr_processor.py # OCR 처리 ✅
```

### 사용하지 않는 파일 (삭제됨):
```
❌ bm25_store.py         # BM25 검색 엔진
❌ hybrid_search.py      # 하이브리드 검색
❌ korean_vector_store.py # 벡터 저장소
❌ korean_reranker.py    # 재순위 시스템
❌ query_optimizer.py    # 쿼리 최적화
❌ metadata_extractor.py # 메타데이터 추출
... (12개 모듈)
```

---

## 💡 장단점 분석

### 장점:
- ✅ 단순하고 이해하기 쉬움
- ✅ 빠른 구현
- ✅ 벡터 DB 불필요
- ✅ 메모리 효율적

### 단점:
- ❌ 파일명에만 의존 (내용 검색 불가)
- ❌ 유사도 검색 없음
- ❌ 여러 문서 조합 불가
- ❌ 확장성 부족

---

## 🔍 실제 테스트

```python
# 질문: "2020년 중계차"
# 결과: 2020-03-17_[추가비용]_2020년_국회기자실_이전_건.pdf

# 왜?
# - 파일명에 "2020년"이 있음 (+20점)
# - "중계차"는 없지만 다른 2020년 파일보다 점수 높음
# - 실제 중계차 문서가 아닐 수 있음!
```

---

## 📊 결론

**현재 시스템 = 파일명 검색기 + LLM 요약기**

1. **RAG 시스템이라고 부르기 어려움**
   - Retrieval: 파일명 매칭만
   - Augmented: 전체 문서만 제공
   - Generation: LLM이 요약

2. **개선 필요 사항**:
   - 실제 문서 내용 검색
   - 벡터 검색 구현
   - 여러 문서 조합
   - 청킹 및 임베딩

3. **현재 상태**:
   - 간단한 용도로는 작동
   - 복잡한 검색은 불가능
   - 확장성 매우 제한적