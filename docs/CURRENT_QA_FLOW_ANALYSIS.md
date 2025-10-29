# 현재 질문-답변 흐름 분석

## 전체 흐름도

```
사용자 질문 입력
    ↓
web_interface.py
    ↓
components/chat_interface.py
    └─ render_chat_interface()
        ├─ 1. 입력 검증 (_validate_input)
        ├─ 2. 대화 맥락 구성 (_build_conversation_context)
        ├─ 3. 향상된 쿼리 생성 (_create_enhanced_query)
        └─ 4. AI 응답 생성 (_generate_ai_response)
            ↓
        unified_rag_instance.answer(query)
            ↓
app/rag/pipeline.py
    └─ RAGPipeline.answer()
        ├─ 1. 확장 쿼리에서 실제 질문 추출
        ├─ 2. 쿼리 라우팅 (query_router.classify_mode)
        │   ↓
        │  app/rag/query_router.py
        │   └─ QueryRouter.classify_mode()
        │       ├─ COST_SUM: 비용 합계 질의
        │       ├─ PREVIEW: 문서 미리보기
        │       ├─ LIST: 목록 검색
        │       ├─ SUMMARY: 내용 요약
        │       └─ QA: 일반 질의응답 (기본)
        │
        └─ 3. 모드별 메소드 호출
            ├─ COST_SUM → _answer_cost_sum()
            ├─ LIST → _answer_list()
            ├─ SUMMARY → _answer_summary()
            ├─ PREVIEW → _answer_preview()
            └─ QA → (일반 검색 + LLM 답변)
```

## 단계별 상세 설명

### 1단계: 사용자 입력 (web_interface.py)
```python
# Streamlit 채팅 입력
if prompt := st.chat_input("질문을 입력하세요"):
    # chat_interface로 전달
```

### 2단계: 채팅 인터페이스 (components/chat_interface.py)

#### A. 입력 검증
```python
is_valid, error_msg = _validate_input(prompt)
# - 빈 문자열 체크
# - 최소/최대 길이 검증
```

#### B. 대화 맥락 구성
```python
context = _build_conversation_context(messages)
# - 최근 3개 대화 추출
# - "이전 대화 맥락" 형태로 구성
```

#### C. 향상된 쿼리 생성
```python
enhanced_query = _create_enhanced_query(context, prompt)
# 형식:
# """
# 이전 대화 맥락:
# - 사용자: ...
# - AI: ...
#
# 현재 질문: {prompt}
# """
```

#### D. AI 응답 생성
```python
response = _generate_ai_response(enhanced_query, unified_rag_instance, ...)
# → rag_instance.answer(query) 호출
```

### 3단계: RAG 파이프라인 (app/rag/pipeline.py)

#### A. 실제 질문 추출
```python
actual_query = query
if "현재 질문:" in query:
    # 확장 쿼리에서 실제 질문만 추출
    actual_query = query.split("현재 질문:")[-1].strip()
```

#### B. 쿼리 라우팅
```python
query_mode = self.query_router.classify_mode(actual_query)
# 반환값: QueryMode (COST_SUM, PREVIEW, LIST, SUMMARY, QA)
```

### 4단계: 쿼리 라우터 (app/rag/query_router.py)

#### 모드 분류 우선순위:
1. **COST_SUM** (비용 합계) - 최우선
   - 패턴: "총 비용", "합계", "얼마" + "비용/금액"

2. **PREVIEW** (문서 미리보기)
   - 조건: 파일명 + ("미리보기" or "보여줘" or "알려줘")

3. **LIST** (목록 검색)
   - 조건: ("찾아줘" or "검색" or "목록") + 요약 의도 없음

4. **SUMMARY** (내용 요약)
   - 조건: (파일명 or "이 문서") + ("요약" or "정리")

5. **QA** (일반 질의응답) - 기본값
   - 조건: 위 모드에 해당하지 않는 모든 질문

### 5단계: 모드별 답변 생성

#### A. COST_SUM 모드
```python
_answer_cost_sum(query)
# 1. 쿼리 파싱 (기안자, 연도, 부서 등)
# 2. metadata.db 직접 조회
# 3. SUM(claimed_total) 계산
# 4. 마크다운 표 형식 반환
```

#### B. LIST 모드
```python
_answer_list(query)
# 1. 기안자/연도/부서 파싱
# 2. MetadataDB.search_documents()
# 3. 2줄 카드 형식으로 포매팅
# 4. 최대 20개 제한
```

#### C. SUMMARY 모드
```python
_answer_summary(query)
# 1. 파일명 또는 doc= 패턴 추출
# 2. 문서 고정 모드로 청크 검색
# 3. LLM으로 요약 생성 (5줄 섹션)
# 4. 원본 소스 표시
```

#### D. PREVIEW 모드
```python
_answer_preview(query)
# 1. 파일명 추출
# 2. PDF 전문 텍스트 로드
# 3. 원문 6-8줄 표시
# 4. "전체 문서는 미리보기 탭에서" 안내
```

#### E. QA 모드 (기본)
```python
# 일반 RAG 파이프라인:
# 1. 임베딩 기반 문서 검색
# 2. Top-K 청크 선택
# 3. LLM으로 답변 생성
# 4. Evidence(출처) 포함
```

## 문제 진단 포인트

### ❌ 문제 발생 가능 지점

1. **라우팅 오류**
   - 의도한 모드가 아닌 다른 모드로 분류됨
   - 예: "요약" 요청이 QA 모드로 처리됨

2. **문서 검색 실패**
   - 파일명 fuzzy matching 실패
   - 메타데이터 DB 조회 실패
   - 청크가 검색되지 않음

3. **LLM 생성 실패**
   - 모델 로드 에러
   - 컨텍스트 길이 초과
   - 응답 포맷 오류

4. **응답 정규화 실패**
   - RAGResponse 객체 → dict 변환 오류
   - text 필드 누락

## 다음 단계: 진단 도구 필요

현재 어떤 답변이 나오고 있는지 확인하려면:
1. 쿼리 라우팅 로그 확인
2. 각 모드별 실행 경로 추적
3. 에러 메시지 수집
4. 실제 응답 내용 분석