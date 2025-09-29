# 🚀 AI-CHAT RAG 시스템 전면 재설계

## 📊 현재 상황 분석
- **총 문서**: 812개 PDF (중복 포함)
- **실제 고유 문서**: 약 480개
- **문서 유형**: 구매(410개), 수리(261개), 신청서(48개) 등
- **연도 범위**: 2014-2025년 (12년간 문서)
- **부서별**: 카메라(139), 조명(120), 스튜디오(89), 중계(55)

## 🔴 현재 시스템의 근본 문제점

### 1. **가짜 RAG** - 파일명 매칭만 수행
```python
# 현재 방식 (문제점)
if keyword in filename_lower:  # 단순 파일명 매칭
    score += 20
```

### 2. **문서 내용 이해 불가**
- PDF 내용을 전혀 이해하지 못함
- 단순 키워드 존재 여부만 확인
- 문맥과 의미 파악 불가

### 3. **임베딩 없음**
- 텍스트 벡터화 없음
- 의미 기반 검색 불가
- 유사도 계산 불가능

### 4. **청킹 없음**
- 전체 문서를 통째로 처리
- 세부 정보 검색 불가
- 메모리 비효율

## 🎯 진짜 RAG 시스템 아키텍처

### Phase 1: 문서 전처리 및 인덱싱
```
1. PDF 텍스트 추출 (pdfplumber + OCR)
   ↓
2. 문서 청킹 (500토큰 단위)
   ↓
3. 메타데이터 추출
   - 날짜, 부서, 문서유형, 금액
   ↓
4. 임베딩 생성 (sentence-transformers)
   ↓
5. 벡터 DB 저장 (FAISS/ChromaDB)
```

### Phase 2: 하이브리드 검색
```
사용자 쿼리
   ↓
   ├─→ BM25 검색 (키워드)
   ├─→ 벡터 검색 (의미)
   └─→ 메타데이터 필터링
         ↓
      결과 통합 (RRF)
         ↓
      Re-ranking
         ↓
      Top-K 청크 선택
```

### Phase 3: 답변 생성
```
검색된 청크들
   ↓
컨텍스트 구성
   ↓
프롬프트 엔지니어링
   ↓
LLM 답변 생성
   ↓
출처 표시
```

## 📝 구현 계획

### 1단계: 문서 인덱싱 시스템 구축
```python
class DocumentIndexer:
    def __init__(self):
        self.embedder = SentenceTransformer('jhgan/ko-sroberta-multitask')
        self.vector_store = FAISS()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

    def index_document(self, pdf_path):
        # 1. 텍스트 추출
        text = extract_text(pdf_path)

        # 2. 청킹
        chunks = self.text_splitter.split_text(text)

        # 3. 메타데이터
        metadata = extract_metadata(pdf_path, text)

        # 4. 임베딩
        embeddings = self.embedder.encode(chunks)

        # 5. 저장
        self.vector_store.add(embeddings, metadata)
```

### 2단계: 하이브리드 검색 구현
```python
class HybridSearcher:
    def search(self, query, top_k=10):
        # 1. 쿼리 임베딩
        query_embedding = self.embedder.encode(query)

        # 2. 벡터 검색
        vector_results = self.vector_store.search(
            query_embedding, k=top_k*2
        )

        # 3. BM25 검색
        bm25_results = self.bm25.search(query, k=top_k*2)

        # 4. 결과 통합 (Reciprocal Rank Fusion)
        combined = self.rrf_merge(
            vector_results,
            bm25_results,
            k=60
        )

        # 5. Re-ranking
        reranked = self.reranker.rerank(query, combined)

        return reranked[:top_k]
```

### 3단계: 컨텍스트 답변 생성
```python
class AnswerGenerator:
    def generate(self, query, contexts):
        # 컨텍스트 구성
        context_text = self.format_contexts(contexts)

        # 프롬프트
        prompt = f"""
        다음 문서들을 참고하여 질문에 답하세요.

        문서 내용:
        {context_text}

        질문: {query}

        요구사항:
        1. 문서에 있는 정보만 사용
        2. 구체적인 날짜, 금액, 담당자 포함
        3. 출처 명시
        4. 없는 정보는 "문서에 없음" 명시
        """

        # LLM 답변
        answer = self.llm.generate(prompt)

        # 출처 추가
        answer_with_sources = self.add_sources(
            answer, contexts
        )

        return answer_with_sources
```

## 🛠️ 필요한 라이브러리

```bash
# 기본
pip install pdfplumber pytesseract

# 임베딩
pip install sentence-transformers

# 벡터 DB
pip install faiss-gpu chromadb

# 청킹
pip install langchain tiktoken

# BM25
pip install rank-bm25

# 한국어 처리
pip install konlpy kiwipiepy
```

## 📈 예상 성능 개선

| 지표 | 현재 | 목표 |
|------|------|------|
| 검색 정확도 | 20-30% | 85-90% |
| 문서 이해도 | 파일명만 | 전체 내용 |
| 답변 품질 | 단순 나열 | 종합적 분석 |
| 검색 속도 | 5-10초 | 1-2초 |
| 확장성 | 낮음 | 높음 |

## 🔥 핵심 개선 사항

### 1. 의미 기반 검색
- "DVR 관련" → DVR, 녹화장비, 영상보존 등 유사 개념 모두 검색

### 2. 컨텍스트 이해
- 문서 전체 맥락을 이해하고 답변

### 3. 다중 문서 종합
- 여러 문서의 정보를 종합하여 답변

### 4. 시간축 분석
- 연도별 변화, 추이 분석 가능

### 5. 금액 집계
- 특정 기간, 부서별 총액 계산

## 📌 구현 우선순위

1. **긴급** - 문서 청킹 및 임베딩 시스템
2. **높음** - 벡터 DB 구축
3. **높음** - 하이브리드 검색
4. **중간** - Re-ranking 시스템
5. **낮음** - 고급 분석 기능

## 💡 추가 아이디어

1. **문서 자동 분류**
   - ML 모델로 문서 유형 자동 분류

2. **시각화 대시보드**
   - 연도별, 부서별 통계 시각화

3. **알림 시스템**
   - 특정 조건 충족시 알림

4. **문서 요약**
   - 긴 문서 자동 요약

5. **질문 추천**
   - 컨텍스트 기반 추천 질문

---

이 설계를 기반으로 진짜 RAG 시스템을 구현하면
현재의 단순 파일명 매칭에서 벗어나
진정한 문서 이해 및 지능형 검색이 가능합니다.