# UI Index Status 패널 통합 가이드

## 개요

`ui/components/index_status_panel.py`는 FastAPI `/metrics` 엔드포인트에서 실시간으로 인덱스 상태를 조회하여 표시하는 Streamlit 컴포넌트입니다.

## 기능

- **실시간 지표 표시**
  - 인덱스 버전 (Index Version)
  - 최근 재색인 시각 (Last Reindex)
  - 문서 수: DB, FAISS, BM25, Unindexed
  - 인제스트 상태 (idle/running/failed)

- **정합성 경고**
  - `unindexed_count > 0`이면 경고 배지 표시 ("동기화 필요")

- **보고서 다운로드**
  - INGEST_DIAG_REPORT.md
  - chunk_stats.csv
  - index_consistency.md
  - ocr_audit.md

- **새로고침 버튼**
  - 실시간 데이터 갱신

## 메인 UI에 통합하는 방법

### 1. 사이드바에 추가

```python
# main.py 또는 app.py

import streamlit as st
from ui.components.index_status_panel import render_index_status_panel

# 사이드바에 Index Status 추가
with st.sidebar:
    st.markdown("---")
    render_index_status_panel(api_base_url="http://localhost:7860")
```

### 2. 별도 탭으로 추가

```python
tab1, tab2, tab3 = st.tabs(["Chat", "Documents", "Index Status"])

with tab1:
    # 기존 Chat UI

with tab2:
    # 기존 Documents UI

with tab3:
    render_index_status_panel(api_base_url="http://localhost:7860")
```

### 3. 별도 페이지로 추가

```python
# pages/index_status.py

import streamlit as st
from ui.components.index_status_panel import render_index_status_panel

st.set_page_config(page_title="Index Status", layout="wide")

st.title("📊 RAG Index Status")
render_index_status_panel(api_base_url="http://localhost:7860")
```

## 의존성

```python
# requirements.txt에 추가 (이미 포함되어 있을 가능성 높음)
streamlit>=1.28.0
requests>=2.31.0
```

## 독립 실행 (테스트)

```bash
streamlit run ui/components/index_status_panel.py
```

브라우저에서 `http://localhost:8501` 접속

## 환경 변수

`api_base_url`을 환경 변수로 설정하려면:

```python
import os

api_base_url = os.getenv("FASTAPI_BASE_URL", "http://localhost:7860")
render_index_status_panel(api_base_url=api_base_url)
```

## 트러블슈팅

### 1. "/metrics 호출 실패" 오류

**원인:** FastAPI 백엔드가 실행되지 않았거나 포트가 다름

**해결:**
```bash
# 백엔드 실행 확인
curl http://localhost:7860/metrics

# 프로세스 확인
ps aux | grep uvicorn
```

### 2. "보고서 파일 없음"

**원인:** 드라이런 또는 재색인이 아직 실행되지 않음

**해결:**
```bash
# 드라이런 실행
make ingest-dryrun

# 정합성 검증 실행
make check-consistency
```

### 3. "unindexed_count > 0" 경고

**원인:** DocStore와 인덱스 간 불일치

**해결:**
```bash
# 재색인 실행
make reindex
```

## API 응답 예시

```json
{
  "docstore_count": 450,
  "faiss_count": 450,
  "bm25_count": 450,
  "unindexed_count": 0,
  "index_version": "v20251030140000_abc123",
  "last_reindex_at": "2025-10-30T14:00:00.123456",
  "ingest_status": "idle"
}
```

## 디자인 커스터마이징

```python
# 배지 색상 변경
if unindexed_count > 0:
    st.error("⚠️ 동기화 필요")  # 빨간색
else:
    st.success("✅ 동기화 완료")  # 초록색

# 상태 아이콘 변경
status_icon = {
    "idle": "🟢",
    "running": "🟡",
    "failed": "🔴"
}.get(ingest_status, "⚪")
```

---

**End of Guide**
