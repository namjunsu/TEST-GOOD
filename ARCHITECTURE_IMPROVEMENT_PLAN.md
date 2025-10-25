# AI-CHAT 시스템 아키텍처 개선 계획

**작성일**: 2025-01-24
**전략**: Plan A (하이브리드 접근)
**목표 기한**: 2주 (D0 ~ D14)
**작성자**: System Architecture Review

---

## 🎯 전략 요약

### 핵심 원칙
1. **단기**: 개별 파일 품질 고도화로 리팩토링 안전성 확보
2. **중기**: 아키텍처 재구조화로 중복·운영 리스크 제거
3. **병행**: 무중단 전환, 작은 단위 PR, 측정 가능한 DoD

### 목표
- ✅ 중복 모듈 제거 (로깅 2개→1개, 검색 2개→1개, RAG 엔트리 2개→1개)
- ✅ RAG 파사드 도입 (단일 진입점)
- ✅ DB 동시성 해결 (WAL + 읽기/쓰기 분리)
- ✅ 성능 개선 (워밍업, 메트릭, 회귀 테스트)
- ✅ 운영 안정성 (에러 분류, 헬스체크, 배지)

---

## 📅 2주 로드맵

### D0–D2: 품질 기반 고도화 (3일)

**목표**: 리팩토링 안전성 확보

#### 작업 내용
1. **config.py Pydantic 전환**
   - 현재: frozen dataclass
   - 목표: Pydantic BaseSettings
   - 이유: 환경변수 자동 검증, .env 파일 지원

2. **정적 분석 체인 정립**
   - ruff (linter + formatter)
   - mypy (strict mode)
   - pytest (기본 테스트 프레임워크)

3. **로깅 인터페이스 통일**
   - 모든 모듈에서 `core.logging.get_logger(__name__)` 사용
   - 내부 구현은 아직 기존 유지 (단계적 전환)

#### 산출물
- `pyproject.toml` (ruff + mypy 설정)
- `pytest.ini` (테스트 설정)
- `.pre-commit-config.yaml` (Git hook)
- PR: `feat/config-hardening`
- PR: `chore/linters-tests`

#### DoD (완료 정의)
- ✅ ruff check 0 오류
- ✅ mypy --strict 통과 (점진적 적용)
- ✅ pytest 기본 테스트 통과

---

### D3–D5: 중복 제거 (3일, 무중단)

**목표**: 중복 모듈 통합

#### 작업 내용

##### 1. 로깅 통합
**현재 상황**:
- `utils/logging_utils.py` - UnifiedLogger 래퍼
- `modules/log_system.py` - ChatLogger 기본 구현

**목표**:
- `app/core/logging.py` - 단일 로깅 팩토리

**작업**:
```python
# app/core/logging.py
from logging import getLogger, StreamHandler, Formatter, INFO
import logging, os, sys

_LOGGER = None

def _init():
    global _LOGGER
    if _LOGGER: return _LOGGER
    logger = logging.getLogger("app")
    logger.setLevel(INFO)
    fmt = Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    sh = StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_dir = os.path.join(os.getcwd(), "var", "log")
    os.makedirs(log_dir, exist_ok=True)
    # RotatingFileHandler 추가 가능

    _LOGGER = logger
    return logger

def get_logger(name: str = "app"):
    """단일 로거 팩토리

    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("message")
    """
    logger = _init().getChild(name)
    return logger
```

**이관 순서**:
1. `app/core/logging.py` 생성
2. 모든 모듈에서 `get_logger(__name__)` 사용하도록 변경
3. `utils/logging_utils.py` 삭제
4. `modules/log_system.py` 삭제 (또는 레거시 폴더로 이동)

##### 2. 검색 통합
**현재 상황**:
- `modules/search_module_hybrid.py` - 하이브리드 검색 구현
- `rag_system/hybrid_search.py` - 하이브리드 검색 구현 (중복!)

**목표**:
- `app/rag/retrievers/hybrid.py` - 단일 구현

**작업**:
1. 두 파일 비교, 더 완성도 높은 구현 선택
2. 가중치/파라미터는 config.py로 외부화
3. `modules/search_module_hybrid.py` 삭제
4. `rag_system/hybrid_search.py` → `app/rag/retrievers/hybrid.py`

##### 3. RAG 엔트리 정리
**현재 상황**:
- `hybrid_chat_rag_v2.py` - 메인 RAG
- `quick_fix_rag.py` - 패치용/실험용

**목표**:
- `app/rag/pipeline.py` - 단일 파사드
- `experiments/quick_fix.py` - 실험용 (또는 삭제)

**작업**:
1. `quick_fix_rag.py` → `experiments/` 이동
2. 또는 feature flag로 pipeline에 흡수

#### 산출물
- PR: `refactor/logging-unify`
- PR: `refactor/search-unify`
- PR: `feat/rag-facade-prep`

#### DoD
- ✅ 로깅: 단일 엔트리포인트 (`app/core/logging.py`)
- ✅ 검색: 단일 구현 (`app/rag/retrievers/hybrid.py`)
- ✅ 기존 기능 100% 동작 (회귀 없음)
- ✅ 테스트 통과

---

### D6–D10: RAG 파사드 + 폴더 재정렬 (5일)

**목표**: 시스템 아키텍처 확립

#### 최종 폴더 구조

```
/home/wnstn4647/AI-CHAT/
├── app/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic BaseSettings + .env
│   │   ├── logging.py             # 단일 로깅 팩토리
│   │   └── errors.py              # Custom exceptions
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── web_app.py             # 기존 web_interface.py
│   │   ├── components/
│   │   │   ├── sidebar_library.py
│   │   │   ├── chat_interface.py
│   │   │   ├── document_preview.py
│   │   │   └── pdf_viewer.py
│   │   └── assets/
│   │       └── css/
│   │           ├── main.css
│   │           └── sidebar.css
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── pipeline.py            # 🔥 단일 RAG 파사드
│   │   ├── retrievers/
│   │   │   ├── __init__.py
│   │   │   ├── hybrid.py          # BM25 + Vector
│   │   │   ├── bm25_store.py
│   │   │   ├── vector_store.py
│   │   │   ├── query_optimizer.py
│   │   │   └── query_expansion.py
│   │   ├── compressors/
│   │   │   ├── __init__.py
│   │   │   └── compressor.py
│   │   ├── rerankers/
│   │   │   ├── __init__.py
│   │   │   └── korean_reranker.py
│   │   ├── filters/
│   │   │   ├── __init__.py
│   │   │   └── multilevel_filter.py
│   │   └── models/
│   │       ├── __init__.py
│   │       └── llm_qwen.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── loaders.py             # document_loader 통합
│   │   └── metadata/
│   │       ├── __init__.py
│   │       ├── db.py              # 메타DB 단일 엔트리
│   │       └── extractor.py
│   ├── indexer/
│   │   ├── __init__.py
│   │   ├── auto_indexer.py        # 백그라운드 인덱서
│   │   └── cli.py                 # 수동 재색인
│   └── ops/
│       ├── __init__.py
│       ├── system_check.py
│       └── healthcheck.py
├── scripts/
│   ├── start.sh                   # 개선된 시작 스크립트
│   ├── reindex.sh
│   └── bench_rag.py               # 회귀 벤치마크
├── var/
│   ├── db/
│   │   ├── metadata.db
│   │   └── everything_index.db
│   └── log/
│       └── app.log
├── experiments/
│   └── quick_fix.py               # 실험용 코드
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_rag_pipeline.py
│   └── ...
├── pyproject.toml
├── pytest.ini
├── .pre-commit-config.yaml
└── README.md
```

#### 핵심 구현: RAG 파사드

```python
# app/rag/pipeline.py
"""RAG 파사드 (단일 진입점)

모든 RAG 작업은 이 클래스를 통해서만 수행됩니다.
- 검색 → 재순위화 → 압축 → LLM 생성
- 전략 패턴으로 각 컴포넌트 교체 가능
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from app.core.logging import get_logger
from app.core.config import Config
from app.rag.retrievers.hybrid import HybridRetriever
from app.rag.compressors.compressor import Compressor
from app.rag.rerankers.korean_reranker import KoreanReranker
from app.rag.models.llm_qwen import QwenLLM

logger = get_logger(__name__)


@dataclass
class RAGResponse:
    """RAG 응답"""
    text: str
    evidence: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class RagPipeline:
    """RAG 파사드

    Example:
        >>> from app.rag.pipeline import RagPipeline
        >>> from app.core.config import Config
        >>>
        >>> cfg = Config.get_instance()
        >>> pipeline = RagPipeline(cfg)
        >>> pipeline.warmup()
        >>>
        >>> response = pipeline.answer("2024년 예산은?")
        >>> print(response.text)
        >>> print(response.evidence)
    """

    def __init__(self, config: Config):
        self.config = config
        logger.info("Initializing RAG pipeline...")

        # 전략 패턴: 각 컴포넌트 교체 가능
        self.retriever = HybridRetriever(config)
        self.reranker = KoreanReranker(config)
        self.compressor = Compressor(config)
        self.llm = QwenLLM(config)

        logger.info("RAG pipeline initialized")

    def warmup(self) -> None:
        """시스템 워밍업 (첫 응답 지연 제거)

        - 토크나이저 로드
        - LLM 그래프 컴파일
        - 인덱스 메모리 로드
        """
        logger.info("Starting warmup...")

        self.retriever.warmup()
        self.llm.warmup()

        logger.info("Warmup complete")

    def answer(self, query: str, top_k: int = 5) -> RAGResponse:
        """질문에 답변

        Args:
            query: 사용자 질문
            top_k: 사용할 문서 수

        Returns:
            RAGResponse: 답변 + 근거 문서

        Raises:
            ValueError: 빈 질문
            RuntimeError: 시스템 오류
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        logger.info(f"Processing query: {query[:50]}...")

        try:
            # 1. 검색 (BM25 + Vector → RRF)
            candidates = self.retriever.search(query, top_k=top_k*2)
            logger.debug(f"Retrieved {len(candidates)} candidates")

            # 2. 재순위화
            reranked = self.reranker.rank(query, candidates)
            logger.debug(f"Reranked to {len(reranked)} documents")

            # 3. 압축 (top_k개만)
            context = self.compressor.summarize(query, reranked[:top_k])
            logger.debug(f"Compressed context: {len(context)} chars")

            # 4. LLM 생성
            output = self.llm.generate(query, context)
            logger.debug(f"Generated response: {len(output)} chars")

            # 5. 응답 구성
            evidence = [
                {
                    "doc_id": doc.metadata.get("doc_id"),
                    "page": doc.metadata.get("page"),
                    "title": doc.metadata.get("title"),
                    "score": doc.score,
                }
                for doc in reranked[:top_k]
            ]

            return RAGResponse(
                text=output,
                evidence=evidence,
                metadata={
                    "query": query,
                    "num_candidates": len(candidates),
                    "num_used": top_k,
                }
            )

        except Exception as e:
            logger.error(f"RAG pipeline error: {e}", exc_info=True)
            raise RuntimeError(f"Failed to process query: {e}") from e
```

#### UI 의존성 역전

```python
# app/ui/web_app.py (핵심 부분만)
import streamlit as st
from app.rag.pipeline import RagPipeline
from app.core.config import Config
from app.core.logging import get_logger

logger = get_logger(__name__)

st.set_page_config(page_title="Channel A RAG", layout="wide")

# 설정 로드
cfg = Config.get_instance()

# RAG 파사드 초기화 (한 번만)
if "pipeline" not in st.session_state:
    with st.spinner("시스템 초기화 중..."):
        pipeline = RagPipeline(cfg)
        pipeline.warmup()
        st.session_state["pipeline"] = pipeline
        st.session_state["warmed"] = True
    logger.info("Pipeline initialized and warmed up")

pipeline = st.session_state["pipeline"]

# 상태 배지
if st.session_state.get("warmed"):
    st.success("✅ 시스템 준비 완료")

# 질문 입력
query = st.text_input("💬 무엇을 도와드릴까요?")

if query:
    try:
        with st.spinner("🤔 생각 중..."):
            response = pipeline.answer(query)

        # 답변 표시
        st.write(response.text)

        # 근거 문서
        with st.expander("📄 근거 문서"):
            for ev in response.evidence:
                st.write(f"- {ev['title']} (p.{ev['page']}) - Score: {ev['score']:.3f}")

    except Exception as e:
        st.error(f"❌ 오류: {e}")
        logger.error(f"Query failed: {e}", exc_info=True)
```

#### DB 동시성 정책

```python
# app/data/metadata/db.py
"""메타데이터 DB 접근 (동시성 안전)

- WAL 모드
- busy_timeout 5초
- 읽기/쓰기 분리
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

DB_PATH = Path(os.getcwd()) / "var" / "db" / "metadata.db"


def connect(read_only: bool = True, timeout: float = 5.0) -> sqlite3.Connection:
    """DB 연결 생성 (동시성 안전)

    Args:
        read_only: True면 읽기 전용 연결
        timeout: busy_timeout (초)

    Returns:
        Connection

    Example:
        # 읽기 (UI, 검색 등)
        conn = connect(read_only=True)

        # 쓰기 (인덱서만)
        conn = connect(read_only=False)
    """
    # 디렉터리 생성
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # URI 모드로 읽기 전용 제어
    mode = "ro" if read_only else "rwc"
    uri = f"file:{DB_PATH}?mode={mode}"

    conn = sqlite3.connect(
        uri,
        uri=True,
        check_same_thread=False,
        timeout=timeout
    )

    # WAL 모드 (동시 읽기/쓰기 허용)
    conn.execute("PRAGMA journal_mode=WAL;")

    # 동기화 수준 (성능 vs 안전성 균형)
    conn.execute("PRAGMA synchronous=NORMAL;")

    # busy_timeout (밀리초)
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)};")

    logger.debug(f"DB connected: read_only={read_only}")

    return conn


def ensure_schema():
    """스키마 초기화 (앱 시작 시 1회 실행)"""
    conn = connect(read_only=False)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                doc_id TEXT UNIQUE,
                title TEXT,
                category TEXT,
                year INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Schema ensured")
    finally:
        conn.close()
```

#### 산출물
- PR: `feat/rag-facade`
- PR: `refactor/folder-restructure`
- PR: `ops/db-concurrency`

#### DoD
- ✅ `app/rag/pipeline.py` 작동
- ✅ UI는 파사드만 호출
- ✅ DB WAL 모드 활성화
- ✅ 읽기/쓰기 분리 완료
- ✅ 기존 기능 100% 동작

---

### D11–D14: 성능·운영 지표 + 워밍업 (4일)

**목표**: 운영 안정성 확보

#### 작업 내용

##### 1. Warm-up 구현

```python
# app/rag/pipeline.py에 추가
def warmup(self) -> None:
    """시스템 워밍업

    - 토크나이저 로드
    - LLM 그래프 컴파일
    - 더미 추론 실행 (첫 토큰 생성 지연 제거)
    - 인덱스 메모리 로드
    """
    logger.info("Starting warmup...")

    # 1. 검색 인덱스 프리로드
    self.retriever.warmup()

    # 2. LLM 워밍업
    dummy_query = "안녕하세요"
    dummy_context = "테스트 문서입니다."
    _ = self.llm.generate(dummy_query, dummy_context)

    logger.info("Warmup complete")
```

##### 2. 메트릭 수집

```python
# app/rag/metrics.py (신규)
"""성능 메트릭 수집

- Hit@k
- P50/P95 latency
- 실패율
- 토큰 사용량
"""

import time
from typing import List, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict
import json
from pathlib import Path

@dataclass
class Metrics:
    """메트릭 컨테이너"""
    queries: List[str] = field(default_factory=list)
    latencies: List[float] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    total_tokens: int = 0

    def record_query(self, query: str, latency: float, success: bool, tokens: int = 0):
        """쿼리 기록"""
        self.queries.append(query)
        self.latencies.append(latency)
        if success:
            self.successes += 1
        else:
            self.failures += 1
        self.total_tokens += tokens

    def summary(self) -> Dict[str, Any]:
        """메트릭 요약"""
        if not self.latencies:
            return {}

        sorted_lat = sorted(self.latencies)
        n = len(sorted_lat)

        return {
            "total_queries": len(self.queries),
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": self.successes / (self.successes + self.failures) if (self.successes + self.failures) > 0 else 0,
            "latency_p50": sorted_lat[int(n * 0.5)],
            "latency_p95": sorted_lat[int(n * 0.95)],
            "latency_mean": sum(sorted_lat) / n,
            "total_tokens": self.total_tokens,
        }

    def save(self, filepath: Path):
        """CSV로 저장"""
        with open(filepath, 'w') as f:
            json.dump(self.summary(), f, indent=2)


# RagPipeline에 통합
class RagPipeline:
    def __init__(self, config: Config):
        # ...
        self.metrics = Metrics()

    def answer(self, query: str, top_k: int = 5) -> RAGResponse:
        start = time.time()
        success = False
        tokens = 0

        try:
            # 기존 로직...
            result = RAGResponse(...)
            success = True
            tokens = len(result.text.split())  # 간단한 토큰 추정
            return result
        finally:
            latency = time.time() - start
            self.metrics.record_query(query, latency, success, tokens)
```

##### 3. 회귀 벤치마크

```python
# scripts/bench_rag.py (신규)
"""RAG 회귀 벤치마크

골든 셋 기반으로 성능 측정:
- Hit@k
- MRR
- Latency
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import Config
from app.rag.pipeline import RagPipeline
import json

# 골든 셋 (실제 질문/정답 쌍)
GOLDEN_SET = [
    {"query": "2024년 예산은?", "expected_docs": ["budget_2024.pdf"]},
    {"query": "신규 채용 계획", "expected_docs": ["hr_plan_2024.pdf"]},
    # ... 30~50개
]

def bench():
    cfg = Config.get_instance()
    pipeline = RagPipeline(cfg)
    pipeline.warmup()

    hits = 0
    total = len(GOLDEN_SET)

    for item in GOLDEN_SET:
        query = item["query"]
        expected = set(item["expected_docs"])

        response = pipeline.answer(query, top_k=5)
        retrieved = set(ev["doc_id"] for ev in response.evidence)

        if expected & retrieved:  # Hit@5
            hits += 1

    hit_rate = hits / total
    print(f"Hit@5: {hit_rate:.2%}")

    # 메트릭 저장
    metrics = pipeline.metrics.summary()
    print(f"P50 latency: {metrics['latency_p50']:.2f}s")
    print(f"P95 latency: {metrics['latency_p95']:.2f}s")

    pipeline.metrics.save(Path("var/log/bench_metrics.json"))

if __name__ == "__main__":
    bench()
```

##### 4. 시작 스크립트 개선

```bash
#!/usr/bin/env bash
# scripts/start.sh

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "🚀 AI-CHAT 시작 중..."

# 1. venv 확인
if [ ! -d .venv ]; then
    echo "❌ 가상환경이 없습니다. 'python3 -m venv .venv' 실행 후 다시 시도하세요."
    exit 1
fi

source .venv/bin/activate

# 2. Python 버전 확인
python -c "import sys; assert sys.version_info[:2] >= (3, 11), 'Python 3.11+ required'"

# 3. 디렉터리 생성
mkdir -p var/log var/db

# 4. 시스템 점검
echo "🔍 시스템 점검 중..."
python -m app.ops.system_check

# 5. DB 초기화 (WAL 설정)
echo "💾 데이터베이스 설정 중..."
python -c "from app.data.metadata.db import ensure_schema; ensure_schema()"

# 6. 워밍업
echo "🔥 시스템 워밍업 중..."
python -c "
from app.core.config import Config
from app.rag.pipeline import RagPipeline
cfg = Config.get_instance()
pipeline = RagPipeline(cfg)
pipeline.warmup()
print('✅ 워밍업 완료')
"

# 7. Streamlit 실행
echo "🌐 웹 서버 시작 중..."
exec streamlit run app/ui/web_app.py --server.port=8501
```

#### 산출물
- PR: `perf/warmup-metrics`
- `scripts/bench_rag.py`
- `scripts/start.sh` (개선)

#### DoD
- ✅ 워밍업 구현 완료
- ✅ 메트릭 수집 작동
- ✅ 벤치마크 실행 가능
- ✅ 첫 질문 응답 P50 ≤ 2.5s

---

## 📋 모듈 이관표

| 기존 | 조치 | 신규 경로 |
|------|------|-----------|
| `utils/logging_utils.py` | 삭제/흡수 | `app/core/logging.py` |
| `modules/log_system.py` | 통합 | `app/core/logging.py` |
| `modules/search_module_hybrid.py` | 삭제 | `app/rag/retrievers/hybrid.py` |
| `rag_system/hybrid_search.py` | 정리 후 이동 | `app/rag/retrievers/hybrid.py` |
| `hybrid_chat_rag_v2.py` | 파사드로 이관 | `app/rag/pipeline.py` |
| `quick_fix_rag.py` | 실험 분리 | `experiments/quick_fix.py` |
| `utils/system_checker.py` | ops 이동 | `app/ops/system_check.py` |
| `modules/metadata_db.py` | data 이동 | `app/data/metadata/db.py` |
| `utils/document_loader.py` | data 이동 | `app/data/loaders.py` |
| `web_interface.py` | ui 이동 | `app/ui/web_app.py` |

---

## ✅ DoD (완료 정의)

### 필수 조건
1. ✅ **중복 제거**: 로깅·검색·RAG 엔트리 각 1개로 통합
2. ✅ **RAG 파사드**: `app/rag/pipeline.py` 작동
3. ✅ **DB 동시성**: WAL + busy_timeout + 읽기/쓰기 분리
4. ✅ **워밍업**: 첫 질문 P50 ≤ 2.5s, P95 ≤ 5s
5. ✅ **메트릭**: Hit@5, latency, 실패율 수집
6. ✅ **정적 분석**: ruff + mypy 통과
7. ✅ **테스트**: pytest 기본 커버리지 40%+
8. ✅ **회귀 없음**: 기존 기능 100% 동작

### 성능 목표 (로컬 RTX 4000 16GB 기준)
- P50 latency ≤ 2.5s
- P95 latency ≤ 5s
- 실패율 < 1%
- Hit@5 ≥ 기준선 또는 +5%

---

## 🔧 즉시 실행 체크리스트

### Week 1 (D0-D5)
- [ ] `pyproject.toml` 작성 (ruff + mypy)
- [ ] `pytest.ini` 작성
- [ ] config.py Pydantic 전환
- [ ] `app/core/logging.py` 생성
- [ ] 모든 모듈에서 `get_logger()` 사용
- [ ] `utils/logging_utils.py` 삭제
- [ ] `modules/log_system.py` 삭제
- [ ] `modules/search_module_hybrid.py` 삭제
- [ ] `quick_fix_rag.py` → `experiments/`

### Week 2 (D6-D14)
- [ ] 폴더 구조 재정렬 (`/app` 기준)
- [ ] `app/rag/pipeline.py` 구현
- [ ] `app/ui/web_app.py` 의존성 역전
- [ ] `app/data/metadata/db.py` WAL 설정
- [ ] 워밍업 구현
- [ ] 메트릭 수집 구현
- [ ] `scripts/bench_rag.py` 작성
- [ ] `scripts/start.sh` 개선
- [ ] DoD 검증

---

## 📊 리스크 관리

### 높은 리스크
1. **폴더 재구조화 시 import 깨짐**
   - 완화: 단계적 이동, 각 단계 테스트
   - 백업: 브랜치 단위 작업

2. **DB 동시성 충돌**
   - 완화: WAL + busy_timeout
   - 모니터링: 에러 로그 수집

3. **성능 저하**
   - 완화: 워밍업 + 프로파일링
   - 롤백: 성능 기준 미달 시 이전 버전 유지

### 낮은 리스크
- 로깅 통합 (기존 API 유지)
- 검색 통합 (가중치만 외부화)

---

## 🎯 성공 지표

### 개발 효율성
- PR 크기: 평균 < 500 LOC
- 리뷰 시간: < 1일
- CI 통과율: 100%

### 시스템 품질
- 테스트 커버리지: ≥ 40%
- 정적 분석: ruff 0 오류, mypy strict 통과
- 실패율: < 1%

### 사용자 경험
- 첫 질문 응답: P50 ≤ 2.5s
- 시스템 시작: < 30s
- 에러 메시지: 명확한 원인 + 해결책

---

## 📚 참고 자료

- Clean Architecture (Robert C. Martin)
- Pydantic Documentation: https://docs.pydantic.dev/
- SQLite WAL Mode: https://www.sqlite.org/wal.html
- Ruff: https://docs.astral.sh/ruff/
- mypy: https://mypy.readthedocs.io/

---

**다음 단계**:
1. Phase 0 완료 (이 문서 작성 ✅)
2. D0 시작: `pyproject.toml` + `pytest.ini` 작성
3. config.py Pydantic 전환

준비되면 "D0 시작"이라고 말씀해주세요!
