"""RAG 파이프라인 (파사드 패턴)

단일 진입점: RAGPipeline.query()
내부 흐름: 검색 → 압축 → LLM 생성

Example:
    >>> pipeline = RAGPipeline()
    >>> response = pipeline.query("질문", top_k=5)
    >>> print(response.answer)
"""

import os
import time
import base64
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from typing import Protocol, List, Optional, Dict, Any

from app.core.logging import get_logger
from app.core.errors import ModelError, SearchError, ErrorCode, ERROR_MESSAGES
from app.rag.query_router import QueryRouter, QueryMode

logger = get_logger(__name__)


def _encode_file_ref(filename: str) -> Optional[str]:
    """파일명을 base64 ref로 인코딩 (docs 하위 경로 찾기)

    Args:
        filename: 파일명

    Returns:
        base64 인코딩된 ref 또는 None
    """
    try:
        # 1. metadata.db에서 경로 찾기 시도
        conn = sqlite3.connect("metadata.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT path FROM documents WHERE filename = ? LIMIT 1",
            (filename,)
        )
        result = cursor.fetchone()
        conn.close()

        if result and result[0]:
            file_path = Path(result[0])
            # docs 하위인지 확인
            if "docs" in file_path.parts and file_path.exists():
                # base64 인코딩
                ref = base64.urlsafe_b64encode(str(file_path).encode()).decode()
                return ref

        # 2. Fallback: docs 폴더에서 파일 검색 (year 폴더 포함)
        import re
        year_match = re.search(r'(\d{4})-', filename)
        if year_match:
            year = year_match.group(1)
            # docs/year_YYYY/ 폴더에서 찾기
            file_path = Path(f"docs/year_{year}") / filename
            if file_path.exists():
                ref = base64.urlsafe_b64encode(str(file_path).encode()).decode()
                return ref

        # 3. Fallback2: docs 폴더 전체 검색
        docs_dir = Path("docs")
        if docs_dir.exists():
            for file_path in docs_dir.rglob(filename):
                if file_path.is_file():
                    ref = base64.urlsafe_b64encode(str(file_path).encode()).decode()
                    return ref

    except Exception as e:
        logger.warning(f"ref 인코딩 실패: {filename} - {e}")

    return None

# 진단 모드 설정
DIAG_RAG = os.getenv("DIAG_RAG", "false").lower() == "true"
DIAG_LOG_LEVEL = os.getenv("DIAG_LOG_LEVEL", "INFO").upper()


# ============================================================================
# Request / Response 데이터 클래스
# ============================================================================


@dataclass
class RAGRequest:
    """RAG 요청 파라미터

    Attributes:
        query: 사용자 질문
        top_k: 검색 결과 개수
        compression_ratio: 컨텍스트 압축 비율 (0.0~1.0)
        use_hyde: HyDE 사용 여부
        temperature: LLM 생성 온도
    """

    query: str
    top_k: int = 5
    compression_ratio: float = 0.7
    use_hyde: bool = False
    temperature: float = 0.1


@dataclass
class RAGResponse:
    """RAG 응답 결과

    Attributes:
        answer: 생성된 답변
        source_docs: 참고 문서 목록 (하위 호환)
        evidence_chunks: Evidence용 정규화 청크 (권장)
        raw_results: 원본 검색 결과 (Evidence 최소 보장용)
        latency: 전체 실행 시간 (초)
        success: 성공 여부
        error: 에러 메시지 (실패 시)
        metrics: 내부 지표 (검색/압축/생성 시간 등)
        diagnostics: 진단 정보 (DIAG_RAG=true일 때만 채워짐)
    """

    answer: str
    source_docs: List[str] = field(default_factory=list)
    evidence_chunks: List[Dict[str, Any]] = field(default_factory=list)
    raw_results: List[Dict[str, Any]] = field(default_factory=list)
    latency: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)  # 진단 정보


# ============================================================================
# 프로토콜 정의 (의존성 역전)
# ============================================================================


class Retriever(Protocol):
    """검색 엔진 인터페이스"""

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """검색 수행 (정규화 스키마 반환)

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict
                }, ...
            ]
        """
        ...


class Compressor(Protocol):
    """컨텍스트 압축기 인터페이스"""

    def compress(
        self, chunks: List[Dict[str, Any]], ratio: float
    ) -> List[Dict[str, Any]]:
        """문서 압축

        Args:
            chunks: 원본 청크 목록 (정규화된 dict)
            ratio: 압축 비율

        Returns:
            압축된 청크 목록 (동일 스키마)
        """
        ...


class Generator(Protocol):
    """LLM 생성기 인터페이스"""

    def generate(self, query: str, context: str, temperature: float) -> str:
        """답변 생성

        Args:
            query: 사용자 질문
            context: 참고 문서
            temperature: 생성 온도

        Returns:
            생성된 답변
        """
        ...


# ============================================================================
# RAG 파이프라인 (파사드)
# ============================================================================


class RAGPipeline:
    """RAG 파이프라인 파사드

    검색 → 압축 → 생성을 단일 인터페이스로 제공.
    내부 구현은 Retriever/Compressor/Generator에 위임.

    Example:
        >>> pipeline = RAGPipeline()
        >>> response = pipeline.query("질문", top_k=5)
        >>> if response.success:
        ...     print(response.answer)
        ...     print(f"참고: {response.source_docs}")
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        compressor: Optional[Compressor] = None,
        generator: Optional[Generator] = None,
    ):
        """RAG 파이프라인 초기화

        Args:
            retriever: 검색 엔진 (None이면 기본 HybridRetriever 사용)
            compressor: 압축기 (None이면 기본 ContextCompressor 사용)
            generator: LLM 생성기 (None이면 기본 LlamaCppGenerator 사용)
        """
        self.retriever = retriever or self._create_default_retriever()
        self.compressor = compressor or self._create_default_compressor()
        self.generator = generator or self._create_default_generator()
        self.query_router = QueryRouter()  # 🎯 모드 라우터 초기화

        # 🔒 Closed-World Validation: 고유 기안자 캐싱
        self.known_drafters = self._load_known_drafters()

        logger.info(f"RAG Pipeline initialized (known_drafters: {len(self.known_drafters)}명)")

    def query(
        self,
        query: str,
        top_k: int = 5,
        compression_ratio: float = 0.7,
        use_hyde: bool = False,
        temperature: float = 0.1,
    ) -> RAGResponse:
        """RAG 질의 (단일 진입점)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수
            compression_ratio: 압축 비율
            use_hyde: HyDE 사용 여부
            temperature: LLM 생성 온도

        Returns:
            RAGResponse: 답변 + 메타데이터
        """

        # 입력 검증
        if not query or not query.strip():
            return RAGResponse(
                answer="",
                success=False,
                error="빈 질문입니다",
            )

        start_time = time.perf_counter()
        metrics = {}
        diagnostics = {}  # 진단 정보 수집

        try:
            # 1. 검색: 정규화된 청크(dict) 리스트 기대
            search_start = time.perf_counter()
            results = self.retriever.search(query, top_k)
            metrics["search_time"] = time.perf_counter() - search_start

            # [DIAG] 검색 결과 진단
            if DIAG_RAG:
                diagnostics["retrieved_k"] = len(results)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(f"[DIAG] 검색 완료: {len(results)}개 문서 검색됨")

            if not results:
                logger.warning(f"No results found for query: {query[:50]}")
                if DIAG_RAG:
                    diagnostics["mode"] = "no_results"
                    diagnostics["generate_path"] = "fallback_no_context"
                return RAGResponse(
                    answer="관련 문서가 검색되지 않았다.",
                    success=True,
                    latency=time.perf_counter() - start_time,
                    metrics=metrics,
                    diagnostics=diagnostics,
                )

            # 2. 압축: 청크 단위 유지(페이지/스니펫/메타 보존)
            compress_start = time.perf_counter()
            compressed = self.compressor.compress(results, compression_ratio)
            metrics["compress_time"] = time.perf_counter() - compress_start

            # [DIAG] 압축 후 진단
            if DIAG_RAG:
                diagnostics["after_compress_k"] = len(compressed)
                diagnostics["compression_ratio"] = compression_ratio
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 압축 완료: {len(results)} → {len(compressed)}개 문서"
                    )

            # 3. 생성: 컨텍스트는 스니펫 집합으로 구성
            gen_start = time.perf_counter()

            # CRITICAL: Inject compressed chunks into generator for proper LLM context
            if hasattr(self.generator, "compressed_chunks"):
                self.generator.compressed_chunks = compressed
                logger.debug(
                    f"Injected {len(compressed)} compressed chunks into generator"
                )

            # 🔥 HOTFIX: Use Context Hydrator instead of simple snippet join
            from app.rag.utils.context_hydrator import hydrate_context
            context, hydrator_metrics = hydrate_context(compressed, max_len=10000)
            logger.info(
                f"LLM_CTX len={len(context)}; "
                f"parts=[chunks:{hydrator_metrics['chunks_used']}, "
                f"pdf_tail:{hydrator_metrics['pdf_tail_pages']}]"
            )

            # [DIAG] 생성 전 컨텍스트 스냅샷
            if DIAG_RAG and DIAG_LOG_LEVEL == "DEBUG":
                for i, c in enumerate(compressed[:3], 1):  # 상위 3개만 로그
                    logger.debug(
                        f"[DIAG] Context[{i}]: doc_id={c.get('doc_id')}, "
                        f"filename={c.get('filename', 'N/A')}, "
                        f"page={c.get('page', 0)}, "
                        f"snippet={c.get('snippet', '')[:120]}..."
                    )

            answer = self.generator.generate(query, context, temperature)
            metrics["generate_time"] = time.perf_counter() - gen_start

            # [DIAG] 생성 완료 진단
            if DIAG_RAG:
                diagnostics["mode"] = "normal"
                diagnostics["generate_path"] = "from_context"
                diagnostics["used_k"] = len(compressed)
                if DIAG_LOG_LEVEL in ["DEBUG", "INFO"]:
                    logger.info(
                        f"[DIAG] 생성 완료: from_context 경로, {len(compressed)}개 문서 사용"
                    )

            total_latency = time.perf_counter() - start_time
            metrics["total_time"] = total_latency

            # 🚨 성능 가드: 슬로 쿼리 임계값 체크
            if total_latency > 10.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>10s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...' | "
                    f"search={metrics['search_time']:.2f}s, "
                    f"generate={metrics['generate_time']:.2f}s"
                )
            elif total_latency > 3.0:
                logger.warning(
                    f"⚠️  SLOW_QUERY (>3s): {total_latency:.2f}s | "
                    f"query='{query[:50]}...'"
                )

            logger.info(
                f"RAG query completed in {total_latency:.2f}s "
                f"(search={metrics['search_time']:.2f}s, "
                f"compress={metrics['compress_time']:.2f}s, "
                f"generate={metrics['generate_time']:.2f}s)"
            )

            return RAGResponse(
                answer=answer,
                source_docs=[c.get("doc_id") for c in results[:3]],
                evidence_chunks=compressed,  # UI용 근거
                raw_results=results,  # Evidence 최소 보장용
                latency=total_latency,
                success=True,
                metrics=metrics,
                diagnostics=diagnostics,
            )

        except SearchError as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_RETRIEVE] 검색 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except ModelError as e:
            logger.error(f"Model inference failed: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_GENERATE] 생성 실패: {e.message}",
                latency=time.perf_counter() - start_time,
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return RAGResponse(
                answer="",
                success=False,
                error=f"[E_UNKNOWN] {str(e)}",
                latency=time.perf_counter() - start_time,
            )

    def _make_response(
        self, text: str, selected: List[Dict[str, Any]], retrieved: List[Dict[str, Any]]
    ) -> dict:
        """표준 응답 구조 생성 (citations 포함)

        Args:
            text: 생성된 답변 텍스트
            selected: 실제 사용된 청크 리스트 (압축 후)
            retrieved: 검색된 원본 결과 리스트

        Returns:
            표준화된 응답 dict (citations 필수)
        """
        citations = []
        for c in selected:
            filename = c.get("filename") or c.get("doc_id") or c.get("title", "")
            ref = _encode_file_ref(filename) if filename else None

            citations.append({
                "doc_id": c.get("doc_id"),
                "filename": filename,
                "title": c.get("title") or filename or c.get("doc_id"),
                "page": c.get("page", 1),
                "snippet": (
                    c.get("text") or c.get("snippet") or c.get("content") or ""
                )[:400],
                "ref": ref,  # 🔴 base64 인코딩된 파일 경로
                "preview_url": c.get("preview_url"),
                "download_url": c.get("download_url"),
            })

        return {
            "text": text,
            "citations": citations,  # 🔴 표준 키 (필수)
            "evidence": citations,  # 하위 호환성 (동일 데이터)
            "status": {
                "retrieved_count": len(retrieved),
                "selected_count": len(selected),
                "found": len(selected) > 0,  # 🔴 유일한 판정 기준
            },
        }

    def answer(self, query: str, top_k: Optional[int] = None) -> dict:
        """답변 생성 (Evidence 포함 구조화된 응답)

        Args:
            query: 사용자 질문
            top_k: 검색 결과 개수 (None이면 기본값 5)

        Returns:
            dict: {
                "text": 답변 텍스트,
                "citations": 참고 문서 목록 (표준 키),
                "evidence": 참고 문서 목록 (하위 호환),
                "status": {
                    "retrieved_count": int,
                    "selected_count": int,
                    "found": bool
                }
            }
        """
        # 🔥 CRITICAL: 기안자/날짜 검색은 QuickFixRAG에 위임 (전문 로직 보유)
        if hasattr(self.generator, "rag"):
            import re
            import sqlite3

            # ✅ 확장된 쿼리에서 실제 질문 추출 (chat_interface.py 대응)
            actual_query = query
            if "현재 질문:" in query:
                parts = query.split("현재 질문:")
                if len(parts) > 1:
                    actual_query = parts[-1].strip()
                    logger.info(f"📝 확장 쿼리에서 추출: '{actual_query[:50]}'")

            # 🎯 모드 라우팅: Q&A 의도 키워드가 있으면 파일명이 있어도 Q&A 모드 우선
            query_mode = self.query_router.classify_mode(actual_query)
            router_reason = self.query_router.get_routing_reason(actual_query)
            logger.info(
                f"🔀 라우팅 결과: mode={query_mode.value}, reason={router_reason}"
            )

            # 💰 COST_SUM 모드: 비용 합계 직접 조회
            if query_mode == QueryMode.COST_SUM:
                return self._answer_cost_sum(actual_query)

            # 📋 LIST 모드: 목록 검색 (2줄 카드 형식)
            if query_mode == QueryMode.LIST:
                return self._answer_list(actual_query)

            # 📝 SUMMARY 모드: 내용 요약 (5줄 섹션)
            if query_mode == QueryMode.SUMMARY:
                return self._answer_summary(actual_query)

            # 👀 PREVIEW 모드: 문서 미리보기 (원문 6-8줄, 가짜 표 금지)
            if query_mode == QueryMode.PREVIEW:
                return self._answer_preview(actual_query)

            # 🔍 디버깅: 실제 pattern matching 대상 로깅
            logger.info(f"🔍 Pattern matching 대상 쿼리: '{actual_query[:100]}'")

            # ✅ P0: 파일명 직접 언급 패턴 감지 (레거시 호환, PREVIEW 모드 외)
            if False:  # 비활성화: PREVIEW 모드로 통합됨
                # 패턴 1: 요약 요청 - "파일명.pdf 내용 요약해줘" / "파일명.pdf 요약"
                file_summary_pattern = (
                    r"(\S+\.pdf)\s*(이\s*)?(문서\s*)?(내용\s*)?(요약|정리)"
                )
                summary_match = re.search(
                    file_summary_pattern, actual_query, re.IGNORECASE
                )

                if summary_match:
                    filename = summary_match.group(1).strip()
                    logger.info(f"🎯 P0: 파일 요약 요청 감지 - {filename}")

                    # PDF 전문 로드 + 메타데이터 조회
                    try:
                        import pdfplumber
                        from pathlib import Path

                        conn = sqlite3.connect("metadata.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT path, filename, drafter, date, category, text_preview
                            FROM documents
                            WHERE filename LIKE ?
                            LIMIT 1
                        """,
                            (f"%{filename}%",),
                        )

                        result = cursor.fetchone()
                        conn.close()

                        if result:
                            pdf_path, fname, drafter, date, category, preview = result

                            # PDF 전문 텍스트 로드
                            full_text = preview or ""
                            if pdf_path and Path(pdf_path).exists():
                                try:
                                    with pdfplumber.open(pdf_path) as pdf:
                                        pages_text = []
                                        for page in pdf.pages[:5]:  # 최대 5페이지
                                            page_text = page.extract_text() or ""
                                            pages_text.append(page_text)
                                            if len("".join(pages_text)) > 5000:
                                                break
                                        full_text = "\n\n".join(pages_text)
                                except Exception as e:
                                    logger.warning(f"PDF 읽기 실패: {e}")

                            # 간단한 요약 생성 (LLM 없이)
                            answer_text = f"**📄 {fname}**\n\n"
                            answer_text += "**📋 문서 정보**\n"
                            answer_text += f"- **기안자:** {drafter or '정보 없음'}\n"
                            answer_text += f"- **날짜:** {date or '정보 없음'}\n"
                            answer_text += (
                                f"- **카테고리:** {category or '정보 없음'}\n"
                            )

                            answer_text += "\n**📝 주요 내용**\n"
                            # 처음 800자 미리보기
                            content_preview = full_text[:800].strip()
                            if content_preview:
                                answer_text += content_preview
                                if len(full_text) > 800:
                                    answer_text += (
                                        "...\n\n*(전체 문서는 더 긴 내용을 포함합니다)*"
                                    )
                            else:
                                answer_text += "*(문서 내용을 읽을 수 없습니다)*"

                            # Evidence 구성
                            evidence = [
                                {
                                    "doc_id": fname,
                                    "page": 1,
                                    "snippet": full_text[:400],  # 500 → 400 (스니펫 일관성)
                                    "meta": {
                                        "filename": fname,
                                        "drafter": drafter,
                                        "date": date,
                                        "category": category,
                                    },
                                }
                            ]

                            return {
                                "text": answer_text,
                                "citations": [fname],
                                "evidence": evidence,
                                "status": {
                                    "retrieved_count": 1,
                                    "selected_count": 1,
                                    "found": True,
                                },
                            }
                        else:
                            logger.warning(f"⚠️ 파일 없음: {filename}")

                    except Exception as e:
                        logger.error(f"❌ 요약 생성 실패: {e}")
                        # 오류 시 일반 검색으로 폴백

                # 패턴 2: 기안자 질의 - "파일명.pdf 기안자가 누구야?"
                # (컬럼 수정 완료: doc_number 제거)
                file_author_pattern = r"(\S+\.pdf)\s*(기안자|작성자).*(누구|알려줘)"
                file_match = re.search(file_author_pattern, actual_query, re.IGNORECASE)

                if file_match:
                    filename = file_match.group(1).strip()
                    logger.info(f"🎯 P0: 파일명 직접 질의 감지 - {filename}")

                    # metadata.db에서 직접 조회
                    try:
                        conn = sqlite3.connect("metadata.db")
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT filename, drafter, date, category
                            FROM documents
                            WHERE filename LIKE ?
                            LIMIT 1
                        """,
                            (f"%{filename}%",),
                        )

                        result = cursor.fetchone()
                        conn.close()

                        if result:
                            fname, drafter, date, category = result
                            answer_text = f"**{fname}**\n\n"
                            answer_text += f"📌 **기안자:** {drafter or '정보 없음'}\n"
                            answer_text += f"📅 **날짜:** {date or '정보 없음'}\n"
                            answer_text += (
                                f"📁 **카테고리:** {category or '정보 없음'}\n"
                            )

                            # Evidence 구성 (정확한 파일 1건)
                            evidence = [
                                {
                                    "doc_id": fname,
                                    "page": 1,
                                    "snippet": f"기안자: {drafter}, 날짜: {date}, 카테고리: {category}",
                                    "meta": {
                                        "filename": fname,
                                        "drafter": drafter,
                                        "date": date,
                                        "category": category,
                                    },
                                }
                            ]

                            return {
                                "text": answer_text,
                                "citations": [fname],
                                "evidence": evidence,
                                "status": {
                                    "retrieved_count": 1,
                                    "selected_count": 1,
                                    "found": True,
                                },
                            }
                        else:
                            logger.warning(f"⚠️ 파일 없음: {filename}")
                            return {
                                "text": f"❌ '{filename}' 파일을 찾을 수 없습니다.",
                                "citations": [],
                                "evidence": [],
                                "status": {
                                    "retrieved_count": 0,
                                    "selected_count": 0,
                                    "found": False,
                                },
                            }

                    except Exception as e:
                        logger.error(f"❌ metadata 조회 실패: {e}")
                        # 오류 시 일반 검색으로 폴백

            # 기안자 검색 패턴 감지 (실제 질문에서만)
            author_patterns = [
                r"([가-힣]{2,4})\s*(문서|기안서|검토서)",
                r"([가-힣]{2,4})가?\s*(작성한|작성안|기안한|쓴|만든)",
                r"(기안자|작성자|제안자)[:\s]+([가-힣]{2,4})",
            ]
            # 날짜 검색 패턴 감지
            year_pattern = r"(\d{4})\s*년"

            is_author_query = any(re.search(p, actual_query) for p in author_patterns)
            is_year_query = re.search(year_pattern, actual_query)

            if is_author_query or is_year_query:
                logger.info(
                    f"🎯 특수 검색 모드 감지: author={is_author_query}, year={is_year_query}"
                )
                # QuickFixRAG.answer()로 직접 처리 (실제 질문 전달)
                answer_text = self.generator.rag.answer(
                    actual_query, use_llm_summary=False
                )

                # 표준 응답 형식으로 변환
                return {
                    "text": answer_text,
                    "citations": [],  # QuickFixRAG 응답에서 추출 어려움
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": "관련 문서" not in answer_text
                        and "없습니다" not in answer_text,
                    },
                }

        # 일반 쿼리는 기존 로직 사용
        response = self.query(query, top_k=top_k or 5)

        if response.success:
            # 검색/압축에서 넘어온 정규화 청크 사용 (실제 page/snippet/meta 노출)
            evidence = [
                {
                    "doc_id": c.get("doc_id"),
                    "page": c.get("page", 1),
                    "snippet": c.get("snippet", ""),
                    "meta": c.get(
                        "meta", {"doc_id": c.get("doc_id"), "page": c.get("page", 1)}
                    ),
                }
                for c in (response.evidence_chunks or [])
            ]

            # CRITICAL: Evidence 최소 보장 (sources_cited가 비어도 검색 결과는 표시)
            evidence_injected = False
            if not evidence and response.raw_results:
                logger.info("Evidence empty, using raw_results[:3] as fallback")
                evidence = [
                    {
                        "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                        "page": 0,  # 검색 결과는 페이지 정보 없음
                        "snippet": r.get("snippet") or r.get("text_preview", "")[:400],  # 500 → 400 (스니펫 일관성)
                        "meta": {
                            "doc_id": r.get("doc_id") or r.get("chunk_id", "unknown"),
                            "filename": r.get("filename", ""),
                            "page": 0,
                        },
                    }
                    for r in response.raw_results[:3]
                ]
                evidence_injected = True

            # [DIAG] Evidence 진단 정보 추가
            if DIAG_RAG and response.diagnostics:
                response.diagnostics["evidence_count"] = len(evidence)
                response.diagnostics["evidence_injected"] = evidence_injected

            # 🔥 CRITICAL: status.found 플래그 - UI 판정 단일 소스
            # retrieved_count: 검색된 원본 결과 수
            # selected_count: 실제 사용된 증거 수 (evidence)
            # found: 검색 성공 여부 (evidence가 1개 이상이면 True)
            status = {
                "retrieved_count": len(response.raw_results or []),
                "selected_count": len(evidence),
                "found": len(evidence) > 0,  # 🔴 유일한 판정 기준
            }

            # 운영 표준 1행 요약 로그 (필수)
            import re

            author_mode = bool(re.search(r"(작성자|기안자|제안자)", query))
            search_ms = int(response.metrics.get("search_time", 0) * 1000)
            generate_ms = int(response.metrics.get("generate_time", 0) * 1000)
            total_ms = int(response.latency * 1000)

            logger.info(
                f'[RAG] query="{query[:50]}..." | '
                f"retrieved={status['retrieved_count']} | "
                f"selected={status['selected_count']} | "
                f"found={status['found']} | "
                f"author_mode={author_mode} | "
                f"backfill={evidence_injected} | "
                f"search_ms={search_ms} | "
                f"generate_ms={generate_ms} | "
                f"total_ms={total_ms}"
            )

            return {
                "text": response.answer,
                "citations": evidence,  # 🔴 표준 키 (필수)
                "evidence": evidence,  # 하위 호환성 (동일 데이터)
                "status": status,  # UI에서 이것만 확인
                "diagnostics": response.diagnostics if DIAG_RAG else {},
            }
        else:
            # 에러 발생 시 (중립 톤, 사과 표현 금지)
            error_msg = ERROR_MESSAGES.get(
                ErrorCode.E_GENERATE, "답변 생성 중 오류가 발생했다."
            )
            if response.error:
                error_msg = f"{error_msg}\n\n상세: {response.error}"

            # 운영 표준 로그 (에러 케이스)
            logger.error(
                f'[RAG] query="{query[:50]}..." | '
                f'status=ERROR | error="{response.error}"'
            )

            return {
                "text": error_msg,
                "citations": [],  # 🔴 표준 키 (필수)
                "evidence": [],  # 하위 호환성
                "status": {"retrieved_count": 0, "selected_count": 0, "found": False},
            }

    def answer_text(self, query: str) -> str:
        """답변 텍스트만 반환 (하위 호환성)

        Args:
            query: 사용자 질문

        Returns:
            str: 생성된 답변 텍스트
        """
        result = self.answer(query)
        return result["text"]

    def _answer_list(self, query: str) -> dict:
        """목록 검색 (2줄 카드 형식) - Closed-World Validation 적용

        Args:
            query: 사용자 질의 (예: "2024년 남준수 문서 찾아줘", "year:2024 drafter:최새름")

        Returns:
            dict: 표준 응답 구조 (2줄 카드 목록)
        """
        from modules.metadata_db import MetadataDB
        from app.rag.query_parser import QueryParser

        try:
            # 🔒 Closed-World Validation: 쿼리 파싱
            parser = QueryParser(self.known_drafters)
            filters = parser.parse_filters(query)

            year = filters['year']
            drafter = filters['drafter']
            source = filters['source']

            # '전부', '전체' 등 명시 시 limit 제거
            if any(keyword in query for keyword in ['전부', '전체', '모든', '모두']):
                limit = None
            else:
                limit = 20  # 기본 페이지 크기

            logger.info(f"📋 목록 검색: year={year}, drafter={drafter}, source={source}, limit={limit}")

            # DB 검색
            db = MetadataDB()
            docs = db.search_documents(drafter=drafter, year=year, limit=limit)

            # 전체 카운트 조회
            total_count = db.count_documents(drafter=drafter, year=year)

            if not docs:
                return {
                    "mode": "LIST",
                    "text": f"검색 결과가 없습니다. (year={year}, drafter={drafter})",
                    "files": [],
                    "count": 0,
                    "total_count": 0,
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 2줄 카드 형식으로 포맷팅 (파일명 기반 핵심 요약)
            cards = []
            for doc in docs:
                filename = doc.get("filename", "알 수 없음")
                doctype = doc.get("doctype", "문서")
                date = doc.get("display_date") or doc.get("date", "날짜 없음")
                drafter_name = doc.get("drafter", "작성자 미상")

                # 파일명에서 핵심 내용 추출 (날짜 제거, 언더스코어를 공백으로)
                import re
                # 날짜 패턴 제거 (YYYY-MM-DD_)
                title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
                # .pdf 확장자 제거
                title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
                # 언더스코어를 공백으로 변환
                title = title.replace('_', ' ')

                # 2줄 카드: 제목 + 메타정보
                card = f"**{title}**\n🏷 {doctype} · 📅 {date} · ✍ {drafter_name}"
                cards.append(card)

            answer_text = "\n\n".join(cards[:10])  # 최대 10개

            # Evidence 구성 (파일명 기반 요약 + 실제 파일 경로)
            evidence = []
            for doc in docs[:10]:
                filename = doc.get("filename", "")

                # 파일명에서 핵심 내용 추출 (답변 텍스트와 동일한 방식)
                import re
                title = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
                title = re.sub(r'\.pdf$', '', title, flags=re.IGNORECASE)
                title = title.replace('_', ' ')

                # snippet을 제목으로 사용 (간결하고 의미 있는 정보)
                snippet = title[:160]

                # 실제 파일 경로 생성 (year 폴더 자동 감지)
                year_match = re.search(r'(\d{4})-', filename)
                if year_match:
                    year = year_match.group(1)
                    file_path_str = f"docs/year_{year}/{filename}"
                else:
                    file_path_str = f"docs/{filename}"

                evidence.append({
                    "doc_id": filename,
                    "filename": filename,
                    "file_path": file_path_str,  # ← 실제 파일 경로 (Streamlit 내장 방식)
                    "page": 1,
                    "snippet": snippet,
                    "ref": None,  # 더 이상 사용하지 않음 (FastAPI 방식 제거)
                    "meta": {
                        "filename": filename,
                        "drafter": doc.get("drafter"),
                        "date": doc.get("display_date") or doc.get("date"),
                        "doctype": doc.get("doctype")
                    }
                })

            # 파일 목록 추출
            file_list = [doc.get("filename") for doc in docs if doc.get("filename")]

            # 품질 방어선 로그 (재현 용이성)
            logger.info({
                "mode": "LIST",
                "files": file_list[:3],
                "count": len(docs),
                "total_count": total_count,
                "llm": os.getenv("LLM_ENABLED", "false").lower() == "true"
            })

            # total_count 정보 추가
            if total_count > len(docs):
                answer_text = f"📊 **전체 {total_count}건 중 {len(docs)}건 표시**\n\n" + answer_text

            return {
                "mode": "LIST",
                "text": answer_text,
                "files": file_list,
                "count": len(docs),
                "total_count": total_count,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": len(docs),
                    "selected_count": min(10, len(docs)),
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ 목록 검색 실패: {e}", exc_info=True)
            return {
                "text": f"목록 검색 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _answer_cost_sum(self, query: str) -> dict:
        """비용 합계 직접 조회 (DB claimed_total 활용)

        Args:
            query: 사용자 질의 (예: "채널에이 중계차 보수 합계 얼마였지?")

        Returns:
            dict: 표준 응답 구조 (text, citations, evidence, status)
        """
        try:
            # 1. 검색으로 후보 문서 찾기
            search_results = self.retriever.search(query, top_k=3)

            if not search_results:
                logger.warning(f"비용 질의 검색 실패: {query}")
                return {
                    "text": "관련 문서를 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            # 2. DB에서 claimed_total 조회
            from modules.metadata_db import MetadataDB
            db = MetadataDB()

            for result in search_results:
                filename = result.get("meta", {}).get("filename") or result.get("doc_id", "")
                if not filename:
                    continue

                doc = db.get_by_filename(filename)
                if doc and doc.get("claimed_total"):
                    claimed_total = doc["claimed_total"]

                    # 3. 답변 포맷팅 (VAT, 검증 배지 포함)
                    # VAT 판단 (text_preview에서 "VAT" 키워드 검색)
                    text_preview = doc.get("text_preview", "")
                    vat_status = "VAT 별도" if "VAT" in text_preview or "부가세" in text_preview else "VAT 포함 추정"

                    # sum_match 검증 배지
                    sum_match = doc.get("sum_match")
                    if sum_match is None:
                        verification = "sum_match=없음"
                    elif sum_match:
                        verification = "sum_match=일치 ✅"
                    else:
                        verification = "sum_match=불일치 ⚠️"

                    answer_text = f"💰 합계: **₩{claimed_total:,}** ({vat_status})\n"
                    answer_text += f"출처: {filename} | 날짜: {doc.get('display_date') or doc.get('date') or '정보 없음'} | 기안자: {doc.get('drafter') or '정보 없음'}\n"
                    answer_text += f"검증: {verification}"

                    # Evidence 구성
                    ref = _encode_file_ref(filename)
                    evidence = [{
                        "doc_id": filename,
                        "filename": filename,
                        "page": 1,
                        "snippet": f"비용 합계: ₩{claimed_total:,}",
                        "ref": ref,  # 🔴 base64 인코딩된 파일 경로
                        "meta": {
                            "filename": filename,
                            "drafter": doc.get("drafter"),
                            "date": doc.get("display_date") or doc.get("date"),
                            "claimed_total": claimed_total
                        }
                    }]

                    logger.info(f"💰 비용 질의 성공: {filename} → ₩{claimed_total:,}")

                    return {
                        "text": answer_text,
                        "citations": evidence,
                        "evidence": evidence,
                        "status": {
                            "retrieved_count": len(search_results),
                            "selected_count": 1,
                            "found": True
                        }
                    }

            # claimed_total 없는 경우
            logger.warning(f"검색된 문서에 비용 정보 없음: {[r.get('doc_id') for r in search_results]}")
            return {
                "text": "검색된 문서에 비용 합계 정보가 없습니다.",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": len(search_results),
                    "selected_count": 0,
                    "found": False
                }
            }

        except Exception as e:
            logger.error(f"❌ 비용 질의 처리 실패: {e}", exc_info=True)
            return {
                "text": f"비용 정보 조회 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _answer_preview(self, query: str) -> dict:
        """문서 미리보기 (원문 인용, 가짜 표 생성 금지)

        Args:
            query: 사용자 질의 (예: "[파일명].pdf 미리보기")

        Returns:
            dict: 표준 응답 구조 (원문 6-8줄)
        """
        import re
        import sqlite3
        from pathlib import Path

        try:
            # 파일명 추출
            filename_match = re.search(r"(\S+\.pdf)", query, re.IGNORECASE)
            if not filename_match:
                return {
                    "text": "파일명을 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            filename = filename_match.group(1)

            # DB에서 문서 조회
            conn = sqlite3.connect("metadata.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT path, filename, drafter, date, display_date, text_preview
                FROM documents
                WHERE filename LIKE ?
                LIMIT 1
            """,
                (f"%{filename}%",),
            )

            result = cursor.fetchone()
            conn.close()

            if not result:
                return {
                    "text": f"'{filename}' 파일을 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            pdf_path, fname, drafter, date, display_date, text_preview = result

            # 원문 6-8줄 추출 (cleaned_text)
            preview_text = text_preview or ""

            # 개행 기준 6-8줄 추출
            lines = [line.strip() for line in preview_text.split('\n') if line.strip()]
            preview_lines = lines[:8]  # 최대 8줄

            if len(preview_lines) == 0:
                preview_content = "(문서 내용을 읽을 수 없습니다)"
            else:
                preview_content = "\n".join(preview_lines)

            # 답변 포맷팅 (가짜 표 생성 절대 금지)
            answer_text = f"**📄 {fname} 미리보기**\n\n"
            answer_text += preview_content

            # Evidence 구성
            ref = _encode_file_ref(fname)
            evidence = [{
                "doc_id": fname,
                "filename": fname,
                "page": 1,
                "snippet": preview_content[:400],
                "ref": ref,  # 🔴 base64 인코딩된 파일 경로
                "meta": {
                    "filename": fname,
                    "drafter": drafter,
                    "date": display_date or date
                }
            }]

            # 품질 방어선 로그
            logger.info({
                "mode": "PREVIEW",
                "files": [fname],
                "lines": len(preview_lines),
                "llm": False  # PREVIEW는 LLM 사용 안 함
            })

            return {
                "text": answer_text,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": 1,
                    "selected_count": 1,
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ 미리보기 생성 실패: {e}", exc_info=True)
            return {
                "text": f"미리보기 생성 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def _safe_fname(self, meta: dict = None, doc_path: str = None) -> str:
        """파일명 안전 추출 (다양한 소스에서 시도)

        Args:
            meta: 메타데이터 딕셔너리
            doc_path: 문서 경로

        Returns:
            안전하게 추출된 파일명 (기본값: '미상 문서')
        """
        import os

        meta = meta or {}

        # 다양한 필드에서 파일명 시도
        fname = (
            meta.get("fname")
            or meta.get("filename")
            or meta.get("doc_id")
            or (os.path.basename(doc_path) if doc_path else None)
            or "미상 문서"
        )

        return fname

    def _make_chunks_for_doc(self, filename: str) -> list:
        """특정 문서의 청크만 로드 (문서 고정 모드용)

        Args:
            filename: 문서 파일명

        Returns:
            해당 문서의 청크 리스트
        """
        try:
            # 전체 검색 인덱스에서 해당 문서만 필터링
            import sqlite3
            conn = sqlite3.connect("rag_system/db/everything_index.db")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT doc_id, page, snippet as text, score
                FROM documents
                WHERE doc_id = ? OR doc_id = ?
                ORDER BY page, score DESC
                LIMIT 20
            """, (filename, filename.replace('.pdf', '')))

            chunks = []
            for row in cursor:
                chunks.append({
                    'doc_id': row['doc_id'],
                    'page': row['page'],
                    'text': row['text'],
                    'score': row['score'],
                    'filename': filename
                })

            conn.close()

            if not chunks:
                logger.warning(f"⚠️ 문서 청크 없음: {filename}")

            return chunks

        except Exception as e:
            logger.error(f"❌ 문서 청크 로드 실패: {e}")
            return []

    def _extract_with_ocr(self, pdf_path: str, start_page: int, total_pages: int) -> str:
        """OCR을 사용하여 PDF에서 텍스트 추출 (pytesseract 우선, paddleocr 폴백)

        Args:
            pdf_path: PDF 파일 경로
            start_page: 시작 페이지 (0-based)
            total_pages: 전체 페이지 수

        Returns:
            추출된 텍스트
        """
        try:
            from pdf2image import convert_from_path
            import pytesseract
            from PIL import Image

            # PDF를 이미지로 변환 (끝 3페이지만)
            images = convert_from_path(
                pdf_path,
                first_page=start_page + 1,  # 1-based
                last_page=total_pages
            )

            text = ""
            for i, img in enumerate(images):
                try:
                    # pytesseract 사용
                    page_text = pytesseract.image_to_string(img, lang='kor+eng')
                    text += page_text + "\n"
                    logger.info(f"✓ OCR (pytesseract) 페이지 {start_page + i + 1}: {len(page_text)}자")
                except Exception as e:
                    logger.warning(f"⚠️ pytesseract 실패 (페이지 {start_page + i + 1}): {e}")

            if len(text.strip()) > 50:
                return text

            # pytesseract 실패 시 paddleocr 시도
            logger.info("🔄 paddleocr 폴백 시도...")
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(use_angle_cls=True, lang='korean')

                text = ""
                for i, img in enumerate(images):
                    # PaddleOCR는 파일 경로 또는 numpy array를 받음
                    import numpy as np
                    img_array = np.array(img)
                    result = ocr.ocr(img_array, cls=True)

                    if result and result[0]:
                        page_text = "\n".join([line[1][0] for line in result[0]])
                        text += page_text + "\n"
                        logger.info(f"✓ OCR (paddleocr) 페이지 {start_page + i + 1}: {len(page_text)}자")

                return text

            except Exception as e:
                logger.warning(f"⚠️ paddleocr 실패: {e}")
                return ""

        except Exception as e:
            logger.error(f"❌ OCR 추출 실패: {e}")
            return ""

    def _gather_summary_context(self, filename: str, pdf_path: str, doc_locked: bool = False) -> str:
        """요약용 컨텍스트 수집 (PDF 끝 + RAG 청크 + 스냅샷)

        Args:
            filename: 파일명
            pdf_path: PDF 파일 경로
            doc_locked: True면 해당 문서 청크만 사용 (다른 문서 검색 금지)

        Returns:
            수집된 컨텍스트 텍스트 (최대 10,000자)
        """
        import pdfplumber
        parts = []

        # 1) PDF 끝 2~3페이지 추출 (결론이 보통 여기 있음)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                start_page = max(0, total_pages - 3)  # 끝 3페이지
                tail = ""
                for page in pdf.pages[start_page:]:
                    tail += (page.extract_text() or "")

                # OCR 폴백 (텍스트가 너무 짧을 경우)
                if len(tail.strip()) < 50:
                    logger.warning(f"⚠️ PDF 텍스트 부족 ({len(tail)}자), OCR 시도...")
                    tail = self._extract_with_ocr(pdf_path, start_page, total_pages)

                if tail.strip():
                    parts.append("=== [문서 결론/말미] ===\n" + tail)
                    logger.info(f"✓ PDF 끝 {total_pages - start_page}페이지 추출: {len(tail)}자")
        except Exception as e:
            logger.warning(f"⚠️ PDF 끝부분 추출 실패: {e}")

        # 2) RAG 상위 청크 (doc_locked=True면 같은 파일만, False면 일반 검색)
        try:
            if doc_locked:
                # 문서 고정 모드: 해당 문서의 청크만 로드
                logger.info(f"🔒 문서 고정 모드: {filename}의 청크만 사용")
                chunks = self._make_chunks_for_doc(filename)

                for i, chunk in enumerate(chunks[:5], 1):
                    chunk_text = chunk.get('text') or chunk.get('snippet') or chunk.get('content') or ""
                    if chunk_text:
                        parts.append(f"=== [문서 청크 {i}] ===\n" + chunk_text[:2000])

                if chunks:
                    logger.info(f"✓ 문서 고정 청크 {len(chunks[:5])}개 추출")
            else:
                # 일반 모드: 키워드 검색 후 같은 파일 필터링
                import re
                search_keywords = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)  # 날짜 제거
                search_keywords = re.sub(r'\.pdf$', '', search_keywords, flags=re.IGNORECASE)
                search_keywords = search_keywords.replace('_', ' ')

                hits = self.retriever.search(search_keywords, top_k=5)
                same_file_hits = [h for h in hits if h.get("filename") == filename][:3]

                for i, h in enumerate(same_file_hits, 1):
                    chunk_text = h.get('text') or h.get('snippet') or h.get('content') or ""
                    if chunk_text:
                        parts.append(f"=== [관련 청크 {i}] ===\n" + chunk_text[:2000])

                if same_file_hits:
                    logger.info(f"✓ RAG 청크 {len(same_file_hits)}개 추출")
        except Exception as e:
            logger.warning(f"⚠️ RAG 청크 추출 실패: {e}")

        # 3) OCR/원문 스냅샷 (있으면 - 현재는 DB text_preview 활용)
        # 향후 확장: full_text 필드가 있으면 활용
        # if hasattr(self, 'get_fulltext'):
        #     full = self.get_fulltext(filename)
        #     if full and len(full) > 1000:
        #         parts.append("=== [원문 스냅샷] ===\n" + full[:3000])

        # 결합 및 길이 제한
        context = "\n\n".join(parts)[:10000]
        logger.info(f"📋 최종 컨텍스트 길이: {len(context)}자")
        return context

    def _answer_summary(self, query: str) -> dict:
        """내용 요약 (문서 타입 자동 감지 + 맞춤 프롬프트)

        Args:
            query: 사용자 질의 (예: "[파일명].pdf 내용 요약해줘" 또는 "미러클랩 카메라 삼각대 기술검토서 이문서 내용 요약헤줘")

        Returns:
            dict: 표준 응답 구조 (JSON 기반 요약)
        """
        import re
        import sqlite3
        import pdfplumber
        from app.rag.summary_templates import (
            detect_doc_kind,
            build_prompt,
            parse_summary_json,
            format_summary_output
        )
        from app.rag.utils.json_utils import (
            parse_summary_json_robust,
            ensure_citations,
            validate_numeric_fields
        )

        try:
            # 0. doc=<파일명> 또는 [DOC]<파일명> 패턴 확인 (정확 참조 토큰)
            doc_ref = None
            doc_locked = False
            doc_exact_match = re.search(r"(?:doc=|DOC])\s*([^\s]+\.pdf)", query, re.IGNORECASE)
            if not doc_exact_match:
                doc_exact_match = re.search(r"\[DOC\]\s*([^\s]+\.pdf)", query, re.IGNORECASE)

            if doc_exact_match:
                doc_ref = doc_exact_match.group(1)
                doc_locked = True
                logger.info(f"🔒 정확 참조 모드: doc={doc_ref}")

            # 1. .pdf 확장자 포함 파일명 추출 시도
            filename_match = re.search(r"(\S+\.pdf)", query, re.IGNORECASE) if not doc_ref else None

            # doc_ref가 있으면 직접 사용
            if doc_ref:
                conn = sqlite3.connect("metadata.db")
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT filename, drafter, date, display_date, category,
                           text_preview, claimed_total, doctype
                    FROM documents
                    WHERE filename = ?
                    LIMIT 1
                """,
                    (doc_ref,),
                )
            # 2. 확장자 없으면 키워드 기반 검색
            elif not filename_match:
                # 불용어 제거 (요약, 이문서, 내용 등)
                stopwords = ["요약", "요약해", "요약헤줘", "정리", "정리해", "이문서", "이 문서", "해당 문서",
                             "내용", "해줘", "헤줘", "알려줘", "알려", "보여줘", "보여"]
                keywords = query
                for word in stopwords:
                    keywords = keywords.replace(word, " ")
                keywords = " ".join(keywords.split())  # 공백 정리

                if not keywords or len(keywords) < 3:
                    return {
                        "text": "문서명이나 키워드를 포함해 다시 질의해주세요.",
                        "citations": [],
                        "evidence": [],
                        "status": {
                            "retrieved_count": 0,
                            "selected_count": 0,
                            "found": False
                        }
                    }

                # 키워드로 문서 검색 (파일명에서 검색)
                # 공백을 % 와일드카드로 변경 (파일명은 언더스코어 사용)
                keywords_wildcard = keywords.replace(' ', '%')
                conn = sqlite3.connect("metadata.db")
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT filename, drafter, date, display_date, category,
                           text_preview, claimed_total, doctype
                    FROM documents
                    WHERE filename LIKE ?
                    ORDER BY date DESC
                    LIMIT 1
                """,
                    (f"%{keywords_wildcard}%",),
                )
            else:
                # 파일명으로 검색
                filename = filename_match.group(1)
                conn = sqlite3.connect("metadata.db")
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT filename, drafter, date, display_date, category,
                           text_preview, claimed_total, doctype
                    FROM documents
                    WHERE filename LIKE ?
                    LIMIT 1
                """,
                    (f"%{filename}%",),
                )

            result = cursor.fetchone()
            conn.close()

            # 🔍 퍼지 매칭 Fallback (정확 매칭 실패 시, doc_locked이 아닌 경우만)
            if not result and not doc_locked:
                from modules.metadata_db import MetadataDB

                search_term = filename if filename_match else keywords
                logger.info(f"🔍 퍼지 매칭 시도: {search_term}")

                # 임시 DB 연결로 퍼지 검색
                db = MetadataDB()
                fuzzy_doc = db.get_by_filename_fuzzy(search_term)
                db.close()

                if fuzzy_doc:
                    logger.info(f"✅ 퍼지 매칭 성공: {fuzzy_doc.get('filename')}")
                    # result 튜플 재구성
                    result = (
                        fuzzy_doc.get('filename'),
                        fuzzy_doc.get('drafter'),
                        fuzzy_doc.get('date'),
                        fuzzy_doc.get('display_date'),
                        fuzzy_doc.get('category'),
                        fuzzy_doc.get('text_preview'),
                        fuzzy_doc.get('claimed_total'),
                        fuzzy_doc.get('doctype', 'proposal')
                    )
                else:
                    logger.warning(f"❌ 퍼지 매칭 실패: {search_term}")
                    return {
                        "text": f"'{search_term}' 관련 문서를 찾을 수 없습니다.",
                        "citations": [],
                        "evidence": [],
                        "status": {
                            "retrieved_count": 0,
                            "selected_count": 0,
                            "found": False
                        }
                    }

            # doc_locked 모드에서 문서를 찾지 못한 경우
            if doc_locked and not result:
                logger.warning(f"❌ 정확 참조 문서 없음: {doc_ref}")
                return {
                    "text": f"'{doc_ref}' 문서를 찾을 수 없습니다.",
                    "citations": [],
                    "evidence": [],
                    "status": {
                        "retrieved_count": 0,
                        "selected_count": 0,
                        "found": False
                    }
                }

            fname, drafter, date, display_date, category, text_preview, claimed_total, doctype = result

            # PDF 경로 확인
            year_match = re.search(r'(\d{4})-', fname)
            if year_match:
                year = year_match.group(1)
                pdf_path = f"docs/year_{year}/{fname}"
            else:
                pdf_path = f"docs/{fname}"

            # 🔥 새 구조: 컨텍스트 수집 (PDF 끝 + RAG + 스냅샷)
            logger.info(f"📋 컨텍스트 수집 시작: {fname} (doc_locked={doc_locked})")
            context_text = self._gather_summary_context(fname, pdf_path, doc_locked=doc_locked)

            # Fallback: 컨텍스트가 비어있으면 text_preview 사용
            if not context_text or len(context_text.strip()) < 100:
                if text_preview:
                    context_text = "=== 문서 내용 ===\n" + text_preview
                    logger.info(f"⚠️ Fallback: text_preview 사용 ({len(text_preview)}자)")

            # 🔥 새 구조: 문서 타입 자동 감지
            if not context_text or len(context_text.strip()) < 100:
                # 컨텍스트 없으면 메타데이터만 표시
                answer_text = f"**📄 {fname}**\n\n"
                answer_text += "문서 내용을 읽을 수 없습니다.\n\n"
                answer_text += f"**📋 문서 정보**\n"
                answer_text += f"- 기안자: {drafter or '정보 없음'}\n"
                answer_text += f"- 날짜: {display_date or date or '정보 없음'}\n"
                if claimed_total:
                    answer_text += f"- 금액: ₩{claimed_total:,}\n"

            else:
                # 문서 종류 자동 감지
                kind = detect_doc_kind(fname, context_text)
                logger.info(f"🎯 문서 타입 감지: {kind}")

                # 타입별 맞춤 프롬프트 생성
                prompt = build_prompt(
                    kind=kind,
                    filename=fname,
                    drafter=drafter or "정보 없음",
                    display_date=display_date or date or "정보 없음",
                    context_text=context_text,
                    claimed_total=claimed_total
                )

                logger.info(f"📝 프롬프트 생성 완료 (kind: {kind})")

                # 🔥 LLM 호출 (JSON 응답 요청)
                max_retries = 2
                parsed_json = None

                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"🤖 LLM 호출 시도 {attempt}/{max_retries}")

                        # LLM 호출
                        llm_response = self.generator.generate(
                            query=prompt,
                            context="",  # 프롬프트에 이미 포함됨
                            temperature=0.2  # 낮은 temperature로 일관성 향상
                        )

                        logger.info(f"✓ LLM 응답 수신: {len(llm_response)}자")

                        # JSON 파싱 시도 (강건한 버전)
                        parsed_json = parse_summary_json_robust(llm_response)

                        if parsed_json:
                            # 인용 보강 (doc_locked 모드에서)
                            if doc_locked:
                                parsed_json = ensure_citations(parsed_json, doc_ref=fname)
                            # 수치 필드 검증 (원문 대조)
                            parsed_json = validate_numeric_fields(parsed_json, context_text)
                            logger.info(f"✓ JSON 파싱 성공 (시도 {attempt}회)")
                            break
                        else:
                            logger.warning(f"⚠️ JSON 파싱 실패 (시도 {attempt}회), 재시도...")
                            if attempt < max_retries:
                                # 재시도 시 리마인드 추가
                                prompt += "\n\n**중요**: 반드시 JSON만 반환하세요. 다른 설명이나 마크다운 블록 없이 순수 JSON 객체만 출력하세요."

                    except Exception as e:
                        logger.error(f"❌ LLM 호출 실패 (시도 {attempt}회): {e}")
                        if attempt >= max_retries:
                            break

                # 🔥 동적 포맷팅 (존재하는 섹션만 렌더)
                if parsed_json:
                    answer_text = format_summary_output(
                        parsed_json=parsed_json,
                        kind=kind,
                        filename=fname,
                        drafter=drafter,
                        display_date=display_date or date,
                        claimed_total=claimed_total
                    )
                    logger.info("✓ 포맷팅된 요약 생성 완료")

                else:
                    # Fallback: JSON 파싱 실패 시 → 자유 요약 생성
                    logger.warning("⚠️ JSON 파싱 실패, 자유 요약으로 대체...")

                    free_form_prompt = f"""다음 문서를 3~5문장으로 자유롭게 요약해주세요.
핵심 내용, 목적, 금액(있으면), 결론 등을 간결하게 포함하세요.
마크다운 형식으로 작성하세요.

**문서명**: {fname}
**기안자**: {drafter or '정보 없음'}
**날짜**: {display_date or '정보 없음'}

[원문]
{context_text[:5000]}
"""

                    try:
                        free_summary = self.generator.generate(
                            query=free_form_prompt,
                            context="",
                            temperature=0.3
                        )

                        # 배너 + 자유 요약
                        answer_text = f"**📄 {fname}**\n\n"
                        answer_text += "⚠️ **구조화 요약 실패(스키마 미일치). 자유 요약으로 대체.**\n\n"
                        answer_text += "---\n\n"
                        answer_text += free_summary.strip() + "\n\n"

                        # 메타데이터 추가
                        answer_text += "---\n**📋 문서 정보**\n"
                        answer_text += f"- 기안자: {drafter or '정보 없음'}\n"
                        answer_text += f"- 날짜: {display_date or date or '정보 없음'}\n"
                        if claimed_total:
                            answer_text += f"- 금액: ₩{claimed_total:,}\n"

                        logger.info("✓ 자유 요약 생성 완료")

                    except Exception as e:
                        logger.error(f"❌ 자유 요약 생성도 실패: {e}")
                        # 최종 폴백: 컨텍스트 일부라도 보여주기
                        answer_text = f"**📄 {fname}**\n\n"
                        answer_text += "⚠️ **요약 생성 실패. 문서 일부 내용을 표시합니다.**\n\n"
                        answer_text += "---\n\n"
                        answer_text += context_text[:1000] + "...\n\n"
                        answer_text += "---\n**📋 문서 정보**\n"
                        answer_text += f"- 기안자: {drafter or '정보 없음'}\n"
                        answer_text += f"- 날짜: {display_date or date or '정보 없음'}\n"
                        if claimed_total:
                            answer_text += f"- 금액: ₩{claimed_total:,}\n"

            # Evidence 구성 (file_path 직접 포함)
            # year 폴더 자동 감지
            year_match = re.search(r'(\d{4})-', fname)
            if year_match:
                year = year_match.group(1)
                file_path_str = f"docs/year_{year}/{fname}"
            else:
                file_path_str = f"docs/{fname}"

            evidence = [{
                "doc_id": fname,
                "filename": fname,
                "file_path": file_path_str,  # 직접 파일 경로 (ref 대신)
                "page": 1,
                "snippet": text_preview[:400] if text_preview else "",
                "ref": None,  # 더 이상 사용하지 않음
                "meta": {
                    "filename": fname,
                    "drafter": drafter,
                    "date": display_date or date,
                    "doctype": doctype,
                    "claimed_total": claimed_total
                }
            }]

            # 품질 방어선 로그 (LLM 사용 여부 정확히 표시)
            used_llm = text_preview and len(text_preview.strip()) > 100
            logger.info({
                "mode": "SUMMARY",
                "files": [fname],
                "llm": used_llm,
                "text_length": len(text_preview) if text_preview else 0
            })

            return {
                "text": answer_text,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": 1,
                    "selected_count": 1,
                    "found": True
                }
            }

        except Exception as e:
            logger.error(f"❌ 요약 생성 실패: {e}", exc_info=True)
            return {
                "text": f"요약 생성 중 오류가 발생했습니다: {str(e)}",
                "citations": [],
                "evidence": [],
                "status": {
                    "retrieved_count": 0,
                    "selected_count": 0,
                    "found": False
                }
            }

    def warmup(self) -> None:
        """워밍업: LLM + 인덱스 사전 로딩

        첫 쿼리 지연 제거를 위해 시작 시 호출.
        """
        logger.info("Warming up RAG pipeline...")
        try:
            # 더미 쿼리 실행
            response = self.query("test warmup query", top_k=1)
            if response.success:
                logger.info(f"Warmup completed in {response.latency:.2f}s")
            else:
                logger.warning(f"Warmup failed: {response.error}")
        except Exception as e:
            logger.error(f"Warmup error: {e}", exc_info=True)

    # ========================================================================
    # 내부 헬퍼: 기본 구현 생성
    # ========================================================================

    def _create_default_retriever(self) -> Retriever:
        """기본 검색 엔진 생성 (v2 또는 v1)

        환경 변수 USE_V2_RETRIEVER로 제어:
        - true: HybridRetrieverV2 사용 (신규 2-layer 아키텍처)
        - false/없음: HybridRetriever 사용 (기존 레거시)
        """
        import os

        use_v2 = os.getenv("USE_V2_RETRIEVER", "false").lower() == "true"

        if use_v2:
            # V2 Retriever는 archive로 이동되었습니다 (20251026)
            # 레거시 코드를 제거하고 v1으로 폴백합니다
            logger.warning(
                "⚠️ USE_V2_RETRIEVER는 더 이상 지원되지 않습니다. v1 Retriever를 사용합니다."
            )
            use_v2 = False
            # try:
            #     from app.rag.retriever_v2 import HybridRetrieverV2
            #     v2_retriever = HybridRetrieverV2()
            #     logger.info("✅ HybridRetrieverV2 (v2 신규 시스템) 생성 완료")
            #
            #     # V2 adapter: fused_results → list 변환
            #     return _V2RetrieverAdapter(v2_retriever)
            # except Exception as e:
            #     logger.error(f"V2 Retriever 생성 실패, v1으로 폴백: {e}")
            #     # 폴백: v1 사용
            #     use_v2 = False

        if not use_v2:
            try:
                from app.rag.retrievers.hybrid import HybridRetriever

                retriever = HybridRetriever()
                logger.info("Default HybridRetriever (v1 레거시) 생성 완료")
                return retriever
            except Exception as e:
                logger.error(f"HybridRetriever 생성 실패: {e}")
                # 폴백: 더미 구현
                return _DummyRetriever()

    def _create_default_compressor(self) -> Compressor:
        """기본 압축기 생성 (현재는 no-op)"""
        logger.info("Default compressor 생성 (no-op)")
        return _NoOpCompressor()

    def _create_default_generator(self) -> Generator:
        """기본 LLM 생성기 생성 (레거시 어댑터 사용)"""
        try:
            # 레거시 구현 어댑터 사용 (점진적 이관 준비)
            legacy_rag = self._create_legacy_adapter()
            logger.info("Default generator 생성 (Legacy Adapter 래핑)")
            return _QuickFixGenerator(legacy_rag)
        except Exception as e:
            logger.error(f"Generator 생성 실패: {e}")
            return _DummyGenerator()

    def _create_legacy_adapter(self):
        """레거시 구현 어댑터 생성 (캡슐화)

        QuickFixRAG를 래핑하여 기존 레거시 시스템과 연결합니다.
        향후 이 메서드만 수정하여 신규 구현으로 점진 전환 가능.

        Returns:
            QuickFixRAG: 레거시 RAG 인스턴스
        """
        # QuickFixRAG 모듈이 제거됨 - None 반환
        logger.warning("⚠️ QuickFixRAG 모듈이 제거됨 - 레거시 어댑터 사용 불가")
        return None

    def _load_known_drafters(self) -> set:
        """메타DB에서 고유 기안자 로드 (Closed-World Validation용)

        Returns:
            set: 고유 기안자 이름 집합
        """
        try:
            from modules.metadata_db import MetadataDB

            db = MetadataDB()
            drafters = db.list_unique_drafters()
            db.close()

            logger.info(f"✅ 고유 기안자 {len(drafters)}명 캐싱 완료")
            return drafters
        except Exception as e:
            logger.error(f"기안자 로드 실패: {e}")
            return set()


# ============================================================================
# 폴백 구현 (기본 동작 보장)
# ============================================================================


class _DummyRetriever:
    """더미 검색기 (폴백용)"""

    def search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        logger.warning("Dummy retriever: 빈 결과 반환")
        return []


class _NoOpCompressor:
    """No-op 압축기 (압축하지 않음)"""

    def compress(
        self, chunks: List[Dict[str, Any]], ratio: float
    ) -> List[Dict[str, Any]]:
        logger.debug("No-op compressor: 압축 스킵")
        return chunks


class _QuickFixGenerator:
    """QuickFixRAG 래퍼 (기존 구현 활용)"""

    def __init__(self, rag):
        self.rag = rag
        self.compressed_chunks = None  # Store chunks for LLM

    def generate(self, query: str, context: str, temperature: float) -> str:
        # 재검색 금지. 컨텍스트 기반 생성으로 우선 시도.
        try:
            # 1) QuickFixRAG에 전용 메서드가 있으면 사용
            if hasattr(self.rag, "generate_from_context"):
                return self.rag.generate_from_context(
                    query, context, temperature=temperature
                )

            # 2) 내부 LLM 직접 접근 경로가 있으면 사용
            # 🔥 CRITICAL: LLM lazy loading - ensure LLM is loaded before checking
            if hasattr(self.rag, "_ensure_llm_loaded"):
                self.rag._ensure_llm_loaded()

            if hasattr(self.rag, "llm") and hasattr(self.rag.llm, "generate_response"):
                # CRITICAL: generate_response expects List[Dict], not str
                # Convert context string back to chunks format
                if self.compressed_chunks:
                    # Use stored compressed chunks (preferred)
                    logger.debug(
                        f"Using {len(self.compressed_chunks)} compressed chunks for generation"
                    )
                    response = self.rag.llm.generate_response(
                        query, self.compressed_chunks, max_retries=1
                    )
                else:
                    # Fallback: convert context string to minimal chunks
                    logger.warning(
                        "No compressed_chunks available, converting context string"
                    )
                    snippets = context.split("\n\n")
                    chunks = [
                        {"snippet": s, "content": s} for s in snippets if s.strip()
                    ]
                    response = self.rag.llm.generate_response(
                        query, chunks, max_retries=1
                    )

                # Extract answer from RAGResponse object
                if hasattr(response, "answer"):
                    return response.answer
                return str(response)

            # 3) 폴백: 재검색이 포함된 answer는 최후 수단으로만
            logger.warning("generate_from_context 미지원 → 폴백(answer) 사용")
            if self.rag is None:
                logger.error("LegacyAdapter: QuickFixRAG가 없어 답변 생성 불가")
                return "죄송합니다. 현재 답변 생성 기능이 비활성화되어 있습니다."
            return self.rag.answer(query, use_llm_summary=True)
        except Exception as e:
            logger.error(f"Generation 실패: {e}", exc_info=True)
            return f"[E_GENERATE] {str(e)}"


class _V2RetrieverAdapter:
    """V2 Retriever Adapter

    HybridRetrieverV2의 결과 형식 {"fused_results": [...]}를
    v1 인터페이스 형식 [...] 으로 변환.

    v2 results 구조:
        {
            "fused_results": [
                {"id": "doc_4094", "score": 0.123, "filename": "...", ...},
                ...
            ]
        }

    v1 expected 구조:
        [
            {"doc_id": "doc_4094", "snippet": "...", "page": 1, ...},
            ...
        ]
    """

    def __init__(self, v2_retriever):
        """
        Args:
            v2_retriever: HybridRetrieverV2 instance
        """
        self.v2_retriever = v2_retriever
        self.db = v2_retriever.db  # MetadataDB for content fetching

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search using v2 retriever, convert to v1 format

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of dicts in v1 format with keys:
            - doc_id: Document ID
            - snippet: Text snippet
            - page: Page number (default 1)
            - score: Relevance score
            - meta: Metadata dict
        """
        try:
            # Call v2 retriever
            v2_result = self.v2_retriever.search(query, top_k=top_k)
            fused_results = v2_result.get("fused_results", [])

            # Convert to v1 format
            v1_results = []
            for doc in fused_results:
                doc_id = doc.get("id", "unknown")

                # 🔥 CRITICAL: snippet 우선순위
                # 1) 검색 결과에 직접 포함된 snippet/content
                # 2) DB 조회 (get_content)
                # 3) 제목/파일명 기반 폴백

                snippet = ""

                # Priority 1: fused_results에 이미 포함된 데이터
                if "snippet" in doc:
                    snippet = doc["snippet"]
                elif "content" in doc:
                    snippet = doc["content"][:500]

                # Priority 2: DB 조회 (app/rag/db.MetadataDB.get_content)
                if not snippet or len(snippet) < 50:
                    content = self.db.get_content(doc_id)
                    if content and len(content) >= 50:
                        snippet = content[:500]

                # Priority 3: 메타데이터 폴백
                if not snippet or len(snippet) < 50:
                    fallback_parts = []
                    if doc.get("title"):
                        fallback_parts.append(f"제목: {doc['title']}")
                    if doc.get("filename"):
                        fallback_parts.append(f"파일: {doc['filename']}")
                    if doc.get("date"):
                        fallback_parts.append(f"날짜: {doc['date']}")

                    snippet = (
                        " | ".join(fallback_parts)
                        if fallback_parts
                        else f"문서 ID: {doc_id}"
                    )
                    logger.warning(
                        f"V2 Adapter: doc_id={doc_id} snippet 결손, 메타데이터 폴백 사용"
                    )

                v1_results.append(
                    {
                        "doc_id": doc_id,
                        "snippet": snippet,
                        "page": 1,  # v2에서는 page 정보 없음, 기본 1
                        "score": doc.get("score", 0.0),
                        "meta": {
                            "doc_id": doc_id,
                            "filename": doc.get("filename", ""),
                            "title": doc.get("title", ""),
                            "date": doc.get("date", ""),
                            "page": 1,
                        },
                    }
                )

            logger.info(f"V2 Adapter: {len(v1_results)} results converted")
            return v1_results

        except Exception as e:
            logger.error(f"V2 Adapter search failed: {e}", exc_info=True)
            return []

    def warmup(self):
        """워밍업 (v2는 필요 시 자동 로드)"""
        logger.info("V2 Adapter warmup (no-op)")


class _DummyGenerator:
    """더미 생성기 (폴백용)"""

    def generate(self, query: str, context: str, temperature: float) -> str:
        logger.warning("Dummy generator: 기본 응답 반환")
        return "죄송합니다. 답변을 생성할 수 없습니다."
