# 답변 부족 문제 조사 보고서

## 🔍 조사 요청
사용자가 "광화문 스튜디오 모니터 & 스탠드 교체 검토서" 문서 요약을 요청했으나, 답변이 너무 간단하고 내용이 부족한 문제 발생.

## 📊 조사 결과 (파이프라인 전체 검증)

### 1단계: 원본 TXT 파일 확인
**파일**: `data/extracted/2025-01-09_광화문_스튜디오_모니터_&_스탠드_교체_검토서.txt`

- ✅ **157 줄**의 상세한 내용 포함
- ✅ 개요, 요약, 현황표, 교체 계획, 비용 명세, LG vs 삼성 비교 검토 등 전체 내용 완전 추출
- ✅ OCR 및 텍스트 추출 단계는 **정상 작동**

### 2단계: BM25 인덱스 확인
**파일**: `var/index/bm25_index.pkl` (Index 227)

- ✅ **4,099 자**로 전체 문서 인덱싱 완료
- ✅ **157 줄** 모두 인덱스에 저장됨
- ✅ 인덱싱 단계는 **정상 작동**

### 3단계: 검색 결과 확인 (❌ 문제 발견!)
**테스트**: `test_retrieval_llm.py`

- ❌ **검색 결과 스니펫이 800자로 잘림**
- 원본: 4,099자 → 검색 반환: 800자 (80% 손실!)
- 문제 위치: `app/rag/retrievers/hybrid.py` 3곳에 하드코딩된 `[:800]`

**코드 상 문제**:
```python
# Line 126, 243, 324 - 하드코딩된 800자 제한
"snippet": (doc.get("text_preview") or "")[:800]  # ❌
"snippet": result.get("content", "")[:800]          # ❌
snippet = (doc.get('text_preview') or "")[:800]     # ❌
```

### 4단계: LLM 설정 확인
- `.env` 파일에서 `LLM_MAX_TOKENS=3072`, `RAG_MAX_TOKENS=3072`로 이미 증가됨
- 그러나 검색 단계에서 800자로 잘리기 때문에 LLM이 전체 내용을 받지 못함

## 🔧 적용된 해결책

### 1. 스니펫 길이 설정 추가 (`.env`)
```bash
SNIPPET_MAX_LENGTH=3600  # 3600자 = ~1200 토큰, 4.5배 증가
```

### 2. 하드코딩 제거 및 동적 설정 (`hybrid.py`)
```python
# __init__ 메서드에 추가
self.snippet_max_length = int(os.getenv("SNIPPET_MAX_LENGTH", "3600"))

# 3곳 모두 수정
"snippet": (doc.get("text_preview") or "")[:self.snippet_max_length]  # ✅
"snippet": result.get("content", "")[:self.snippet_max_length]        # ✅
snippet = (doc.get('text_preview') or "")[:self.snippet_max_length]   # ✅
```

## 📈 예상 효과

### 이전 (Before)
- 검색 스니펫: **800자**
- LLM이 받는 컨텍스트: **800자** (20% 내용)
- 답변 품질: **매우 부족** (핵심 정보 대부분 누락)

### 수정 후 (After)
- 검색 스니펫: **3,600자**
- LLM이 받는 컨텍스트: **3,600자** (88% 내용)
- 답변 품질: **상세하고 완전** (개요, 현황, 교체 계획, 비용, 제품 비교 등 모두 포함)
- **4.5배 증가** (800 → 3,600자)

## ⚠️ 주의사항
서버 재시작 필요:
```bash
pkill -f "uvicorn|streamlit"
bash start_ai_chat.sh
```

재시작 후 `SNIPPET_MAX_LENGTH=3600` 설정이 적용되어 답변 품질이 대폭 개선될 것입니다.

## 📋 결론
**근본 원인**: 검색 단계에서 하드코딩된 800자 제한이 병목 지점
**해결 방법**: 스니펫 길이를 3,600자로 증가 (4.5배), 환경 변수로 동적 설정
**예상 결과**: 답변이 훨씬 상세하고 완전해짐 (20% → 88% 내용 포함)
