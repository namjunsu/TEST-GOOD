"""문서 핸들러 모듈

DOCUMENT 모드를 처리하는 핸들러.
pipeline.py의 _answer_document를 위임받아 처리.

Strangler Fig 패턴:
    1단계: pipeline.py의 메서드들이 이 핸들러를 호출
    2단계: 점진적으로 로직 이동
    3단계: pipeline.py는 facade만 유지
"""

import re
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.core.errors import DocumentNotFoundError, SearchError
from app.core.logging import get_logger
from app.data.metadata_db import connect_metadata
from config.constants import DocumentHandlerConfig

from .base import BaseHandler

logger = get_logger(__name__)


# ============================================================================
# 상수 정의
# ============================================================================

# 문서 조회용 불용어
DOCUMENT_STOP_WORDS = [
    "이문서", "이 문서", "해당 문서", "내용", "알려줘", "알려",
    "보여줘", "보여", "자세하게", "자세히", "요약", "정리",
]

# 데이터 디렉토리
EXTRACTED_DIR = Path("data/extracted")


# ============================================================================
# 헬퍼 함수
# ============================================================================

def extract_filename_from_query(query: str) -> Optional[str]:
    """쿼리에서 파일명 추출

    지원 패턴:
    1. .pdf 확장자 포함: "2025-08-13_TVLogic_모니터.pdf"
    2. 날짜_제목 형식: "2025-08-13_TVLogic_모니터_구매_검토서"
    3. 날짜_제목 (날짜) 형식: "2025-08-13_TVLogic_모니터_구매_검토서 (2025-08-13)"
    """
    # 1. .pdf 확장자 포함 파일명
    match = re.search(r"(\S+\.pdf)", query, re.IGNORECASE)
    if match:
        return match.group(1)

    # 2. 날짜_제목 패턴: YYYY-MM-DD_제목 (optional: (YYYY-MM-DD))
    # 예: "2025-08-13_TVLogic_모니터_구매_검토서 (2025-08-13) 이문서 내용 요약줘"
    pattern = r"(\d{4}-\d{2}-\d{2}_[^\s\(]+(?:_[^\s\(]+)*)"
    match = re.search(pattern, query)
    if match:
        doc_name = match.group(1)
        # .pdf 확장자 추가하여 반환
        return f"{doc_name}.pdf"

    return None


def extract_keywords_for_document(query: str) -> str:
    """문서 조회용 키워드 추출"""
    keywords = query
    for word in DOCUMENT_STOP_WORDS:
        keywords = keywords.replace(word, " ")
    return " ".join(keywords.split())


def load_document_text(filename: str) -> str:
    """문서 텍스트 로드 (extracted 디렉토리에서)"""
    txt_filename = filename.replace(".pdf", ".txt")
    txt_path = EXTRACTED_DIR / txt_filename

    if txt_path.exists():
        with Path(txt_path).open("r", encoding="utf-8") as f:
            return f.read()
    return ""


# ============================================================================
# DocumentHandler 클래스
# ============================================================================

class DocumentHandler(BaseHandler):
    """문서 내용 조회 핸들러

    DOCUMENT 모드를 처리합니다.
    문서 전체 내용을 반환하거나 LLM을 통해 요약/Q&A를 제공합니다.

    Modes:
        - DOCUMENT: 문서 전체 내용 조회 (PREVIEW + SUMMARY 통합)
    """

    mode = "DOCUMENT"

    def handle(
        self,
        query: str,
        selected_filename: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """DOCUMENT 모드 쿼리 처리

        Args:
            query: 사용자 쿼리
            selected_filename: 미리 선택된 문서 파일명 (선택사항)
            **kwargs: 추가 파라미터

        Returns:
            표준 응답 딕셔너리
        """
        import time
        overall_start = time.perf_counter()
        timings = {}

        try:
            # 1. 문서 식별
            t_start = time.perf_counter()
            target_filename = self._identify_document(query, selected_filename)
            timings["1_identify_document"] = time.perf_counter() - t_start

            if not target_filename:
                return self._make_empty_response(
                    "문서를 찾을 수 없습니다. 문서명을 명확히 입력해주세요.",
                )

            # 2. DB에서 메타데이터 조회
            t_start = time.perf_counter()
            metadata = self._get_document_metadata(target_filename)
            timings["2_get_metadata"] = time.perf_counter() - t_start

            if not metadata:
                return self._make_empty_response(
                    f"'{target_filename}' 문서의 메타데이터를 찾을 수 없습니다.",
                )

            # 3. 라우팅 결정 (섹션 감지, 요약 여부 등) - 텍스트 로드 전에 수행
            t_start = time.perf_counter()
            routing = self._route_document_query(query)
            timings["3_route_query"] = time.perf_counter() - t_start

            # 4. 문서 텍스트 로드 (routing 정보 활용)
            t_start = time.perf_counter()
            full_text = self._load_full_text(metadata["filename"], routing)
            timings["4_load_text"] = time.perf_counter() - t_start

            if not full_text or len(full_text.strip()) < DocumentHandlerConfig.MIN_TEXT_LENGTH:
                return self._make_empty_response(
                    f"'{metadata['filename']}' 문서의 텍스트를 확보하지 못했습니다.",
                )

            # 5. 응답 생성 (LLM 또는 원문)
            t_start = time.perf_counter()
            answer_text = self._generate_answer(
                query=query,
                full_text=full_text,
                metadata=metadata,
                routing=routing,
            )
            timings["5_generate_answer"] = time.perf_counter() - t_start

            # 6. Evidence 구성
            t_start = time.perf_counter()
            evidence = self._build_evidence(metadata, full_text)
            timings["6_build_evidence"] = time.perf_counter() - t_start

            # 전체 실행 시간 및 단계별 시간 기록
            timings["total_time"] = time.perf_counter() - overall_start

            logger.info({
                "mode": "DOCUMENT",
                "filename": metadata["filename"],
                "text_length": len(full_text),
                "routing": routing,
                "timings_seconds": timings,
            })

            # 성능 분석 로그 (5초 이상 걸린 경우만)
            if timings["total_time"] > 5.0:
                logger.warning(
                    f"⏱️ PERFORMANCE: Document mode took {timings['total_time']:.2f}s\n"
                    f"  - Identify: {timings['1_identify_document']:.2f}s\n"
                    f"  - Metadata: {timings['2_get_metadata']:.2f}s\n"
                    f"  - Routing: {timings['3_route_query']:.2f}s\n"
                    f"  - Load Text: {timings['4_load_text']:.2f}s\n"
                    f"  - Generate Answer: {timings['5_generate_answer']:.2f}s\n"
                    f"  - Build Evidence: {timings['6_build_evidence']:.2f}s"
                )

            return {
                "mode": self.mode,
                "text": answer_text,
                "files": [metadata["filename"]],
                "count": 1,
                "citations": evidence,
                "evidence": evidence,
                "status": {
                    "retrieved_count": 1,
                    "selected_count": 1,
                    "found": True,
                },
            }

        except DocumentNotFoundError as e:
            logger.warning(f"⚠️ 문서 없음: {e}")
            return self._make_error_response(
                "요청하신 문서를 찾을 수 없습니다.",
            )

        except sqlite3.Error as e:
            logger.error(f"❌ DB 오류: {e}", exc_info=True)
            return self._make_error_response(
                "문서 조회 중 데이터베이스 오류가 발생했습니다.",
            )

        except SearchError:
            # SearchError는 이미 적절히 처리됨, 재발생
            raise

        except (OSError, IOError) as e:
            # 파일 시스템 오류 (인덱스 파일 접근 불가 등)
            logger.error(f"❌ 파일 시스템 오류: {e}", exc_info=True)
            return self._make_error_response(
                "문서 파일 접근 중 오류가 발생했습니다. 관리자에게 문의하세요.",
            )

        except (RuntimeError, ValueError) as e:
            # LLM 또는 내부 로직 오류
            logger.error(f"❌ 내부 처리 오류: {e}", exc_info=True)
            return self._make_error_response(
                "문서 처리 중 내부 오류가 발생했습니다.",
            )

        except Exception as e:
            # 예상치 못한 오류 - 스택트레이스 전체 기록
            logger.exception(f"❌ DOCUMENT 모드 예상치 못한 오류: {type(e).__name__}")
            return self._make_error_response(
                f"문서 내용 조회 중 예상치 못한 오류가 발생했습니다: {type(e).__name__}",
            )

    # ========================================================================
    # Private 헬퍼 메서드
    # ========================================================================

    def _identify_document(
        self,
        query: str,
        selected_filename: Optional[str],
    ) -> Optional[str]:
        """문서 식별"""
        # 1. 미리 선택된 파일명 우선
        if selected_filename:
            logger.info(f"🎯 선택된 문서 우선 처리: {selected_filename}")
            return selected_filename

        # 2. 쿼리에서 .pdf 파일명 추출 시도
        filename_from_query = extract_filename_from_query(query)
        if filename_from_query:
            logger.info(f"📄 쿼리에서 파일명 추출: {filename_from_query}")
            return filename_from_query

        # 3. 키워드 기반 검색
        keywords = extract_keywords_for_document(query)
        logger.info(f"🔍 키워드로 문서 검색: {keywords}")

        search_results = self.retriever.search(keywords, top_k=DocumentHandlerConfig.IDENTIFY_SEARCH_TOP_K)
        if search_results:
            result = search_results[0]
            filename = result.get("meta", {}).get("filename") or result.get("doc_id", "")
            logger.info(f"✅ 검색으로 문서 발견: {filename}")
            return filename

        return None

    def _get_document_metadata(self, filename: str) -> Optional[dict[str, Any]]:
        """DB에서 문서 메타데이터 조회"""
        try:
            with connect_metadata() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT filename, drafter, date, display_date, category, doctype
                    FROM documents
                    WHERE filename = ? OR filename LIKE ?
                    LIMIT 1
                    """,
                    (filename, f"%{filename}%"),
                )
                result = cursor.fetchone()

            if result:
                return {
                    "filename": result[0],
                    "drafter": result[1],
                    "date": result[2],
                    "display_date": result[3],
                    "category": result[4],
                    "doctype": result[5],
                }
            return None

        except sqlite3.OperationalError as e:
            # DB 락 또는 연결 문제 - 재시도 가능
            logger.warning(f"⚠️ DB 일시 오류 (메타데이터): {e}")
            return None

        except sqlite3.Error as e:
            # 기타 DB 오류
            logger.error(f"❌ 메타데이터 조회 DB 오류: {e}")
            return None

        except Exception as e:
            # 예상치 못한 오류
            logger.exception(f"❌ 메타데이터 조회 예상치 못한 오류: {type(e).__name__}")
            return None

    def _load_full_text(self, filename: str, routing: dict[str, Any] | None = None) -> str:
        """문서 텍스트 로드 (청크 기반 우선)

        Args:
            filename: 문서 파일명
            routing: 라우팅 정보 (detail_level 등)

        Returns:
            문서 텍스트
        """
        import time
        start = time.perf_counter()

        # 1. PRIMARY: 청크 기반 로드 (빠르고 효율적)
        try:
            chunks = self._make_chunks_for_doc(filename, top_k=DocumentHandlerConfig.FALLBACK_CHUNK_TOP_K)
            if chunks:
                # detail_level에 따라 컨텍스트 크기 조정
                max_chars = DocumentHandlerConfig.CHUNK_CONTEXT_MAX
                if routing:
                    detail_level = routing.get("detail_level", "normal")
                    max_chars = {
                        "brief": 6000,
                        "normal": 12000,
                        "detailed": 24000
                    }.get(detail_level, 12000)

                context = self._assemble_context_from_chunks(chunks, max_chars=max_chars)
                duration = time.perf_counter() - start
                logger.info(f"⏱️ 청크 기반 로딩: {filename} ({duration:.2f}s, {len(context)} chars)")
                return context

        except (AttributeError, KeyError) as e:
            # 인덱스 구조 문제
            logger.warning(f"⚠️ 청크 기반 로드 실패 - 인덱스 접근 오류: {e}")

        except Exception as e:
            # 예상치 못한 오류
            logger.warning(f"⚠️ 청크 기반 로드 실패 ({type(e).__name__}): {e}")

        # 2. FALLBACK: 전체 파일 로드 (BM25 없을 때만)
        logger.warning(f"⚠️ BM25 청크 없음, 전체 파일 로드 시도: {filename}")
        full_text = load_document_text(filename)

        if full_text:
            duration = time.perf_counter() - start
            if duration > 1.0:
                logger.warning(f"⏱️ 전체 파일 로딩 지연: {filename} ({duration:.2f}s, {len(full_text)} chars)")
            else:
                logger.debug(f"⏱️ 전체 파일 로딩: {filename} ({duration:.3f}s, {len(full_text)} chars)")
            return full_text

        return ""

    def _make_chunks_for_doc(
        self, filename: str, top_k: int = DocumentHandlerConfig.DEFAULT_CHUNK_TOP_K,
    ) -> list[dict[str, Any]]:
        """특정 문서의 청크만 로드 (top_k: 최대 청크 수)"""
        try:
            # BM25 인덱스에서 직접 접근 (동적 속성)
            bm25_store = getattr(self.retriever, "bm25", None)
            if bm25_store is not None:
                chunks = []

                for i, meta in enumerate(bm25_store.metadata):
                    if meta.get("filename") == filename:
                        content = bm25_store.documents[i]
                        if content and len(content.strip()) > 0:
                            chunks.append({
                                "doc_id": filename,
                                "page": 1,
                                "text": content,
                                "score": 1.0,
                                "filename": filename,
                            })

                if chunks:
                    logger.info(f"✓ BM25에서 {len(chunks)}개 청크 로드")
                    return chunks

            # BM25 사용 불가 시 검색 폴백
            logger.warning("⚠️ BM25 직접 접근 불가, 검색으로 폴백")
            search_query = filename.replace(".pdf", "").replace("_", " ")
            results = self.retriever.search(search_query, top_k=DocumentHandlerConfig.SEARCH_FALLBACK_TOP_K)

            chunks = []
            for result in results:
                doc_id = result.get("doc_id", "")
                meta_filename = result.get("meta", {}).get("filename", "")

                if filename in doc_id or filename in meta_filename:
                    chunks.append({
                        "doc_id": result.get("doc_id", filename),
                        "page": result.get("page", 1),
                        "text": result.get("snippet", result.get("text", "")),
                        "score": result.get("score", 0.0),
                        "filename": filename,
                    })

            return chunks

        except (AttributeError, KeyError) as e:
            # BM25 인덱스 구조 문제
            logger.warning(f"⚠️ BM25 인덱스 접근 오류: {e}")
            return []

        except Exception as e:
            # 예상치 못한 오류
            logger.exception(f"❌ 문서 청크 로드 예상치 못한 오류: {type(e).__name__}")
            return []

    def _assemble_context_from_chunks(
        self,
        chunks: list[dict[str, Any]],
        max_chars: int = 24000
    ) -> str:
        """청크들을 컨텍스트로 조립

        Args:
            chunks: BM25 검색으로 가져온 청크 리스트
            max_chars: 최대 컨텍스트 길이

        Returns:
            조립된 컨텍스트 문자열
        """
        parts = []
        total_len = 0

        for chunk in chunks:
            text = (
                chunk.get("text") or
                chunk.get("content") or
                chunk.get("snippet") or ""
            )

            if total_len + len(text) > max_chars:
                # 제한 초과 시 자르기
                remaining = max_chars - total_len
                if remaining > 0:
                    parts.append(text[:remaining])
                break

            parts.append(text)
            total_len += len(text)

        result = "\n\n".join(parts)
        logger.info(f"✅ 청크 {len(parts)}개 결합 → {len(result)}자 확보")
        return result

    def _route_document_query(self, query: str) -> dict[str, Any]:
        """문서 질의 라우팅 결정"""
        from app.rag.query_routing import route_query
        routing = route_query(query)
        return {
            "detailed_mode": routing.get("detailed_mode", False),
            "detected_section": routing.get("detected_section"),
            "needs_summary": routing.get("needs_summary", False),
            "max_tokens": routing.get("max_tokens", DocumentHandlerConfig.DEFAULT_MAX_TOKENS),
        }

    def _generate_answer(
        self,
        query: str,
        full_text: str,
        metadata: dict[str, Any],
        routing: dict[str, Any],
    ) -> str:
        """응답 생성 (LLM 또는 원문)"""
        # 짧은 문서는 원문 그대로 반환
        if len(full_text) <= DocumentHandlerConfig.SHORT_TEXT_THRESHOLD:
            return full_text

        # LLM을 통한 응답 생성
        try:
            return self._generate_llm_answer(
                query=query,
                full_text=full_text,
                metadata=metadata,
                routing=routing,
            )
        except (RuntimeError, ValueError) as e:
            # LLM 내부 오류 (모델 로드 실패, 토큰 제한 등)
            logger.warning(f"⚠️ LLM 응답 생성 실패 (내부 오류): {e}", exc_info=True)

        except (TimeoutError, ConnectionError) as e:
            # 네트워크/타임아웃 오류 (외부 API 사용 시)
            logger.warning(f"⚠️ LLM 응답 생성 실패 (연결 오류): {e}")

        except Exception as e:
            # 예상치 못한 오류
            logger.warning(f"⚠️ LLM 응답 생성 실패 ({type(e).__name__}): {e}", exc_info=True)

        # 모든 예외 발생 시 폴백 응답
        return self._build_fallback_response(full_text, metadata, routing)

    def _generate_llm_answer(
        self,
        query: str,
        full_text: str,
        metadata: dict[str, Any],
        routing: dict[str, Any],
    ) -> str:
        """LLM을 통한 응답 생성"""
        import time

        # 프롬프트 생성 (먼저 준비)
        t_prompt_start = time.perf_counter()
        llm_prompt, system_msg = self._build_llm_prompt(
            query=query,
            full_text=full_text,
            metadata=metadata,
            routing=routing,
        )
        t_prompt = time.perf_counter() - t_prompt_start

        # 모드 결정
        if routing.get("detailed_mode"):
            mode = "detailed"  # 자세히 모드: 별도 토큰 예산
        elif routing.get("needs_summary"):
            mode = "summarize"
        else:
            mode = "rag"

        # 컨텍스트 준비 (속도 최적화)
        # 2026-01-10: 컨텍스트 대폭 축소 (24K → 12K)
        # vLLM: 긴 프롬프트는 속도 저하의 주범 (8K+ 토큰 시 20배 느림)
        if mode == "detailed":
            context_limit = min(len(full_text), 12000)  # 자세히: 최대 12K자 (24K → 12K, 50% 감소)
        else:
            context_limit = DocumentHandlerConfig.CONTEXT_WINDOW  # 기본: 6K자
        context = full_text[:context_limit]

        # 🔧 2025-12-23: 동적 max_tokens 계산 (문서 길이에 따라)
        calculated_max_tokens = self._calculate_max_tokens(len(full_text), routing)
        logger.info(
            f"📊 LLM 설정: mode={mode}, context_len={len(context)}, "
            f"full_text_len={len(full_text)}, max_tokens={calculated_max_tokens}, "
            f"prompt_build_time={t_prompt:.3f}s"
        )

        # ===== 경로 1: _LLMAdapter.generate_from_context() 사용 (vLLM/llama_cpp 자동 분기) =====
        # 2025-12-23: vLLM 전환으로 모든 모드에서 이 경로 사용 (llama_cpp 레거시 제거)
        rag_adapter = getattr(self.generator, "rag", None)
        if rag_adapter is not None:
            generate_fn = getattr(rag_adapter, "generate_from_context", None)
            if generate_fn is not None:
                logger.info(f"🎯 _LLMAdapter.generate_from_context() 사용 (mode={mode}, max_tokens={calculated_max_tokens})")

                t_llm_start = time.perf_counter()
                raw_result: str = generate_fn(
                    query=llm_prompt,
                    context=context,
                    temperature=DocumentHandlerConfig.LLM_TEMPERATURE,
                    mode=mode,
                    system_msg=system_msg,
                    max_tokens=calculated_max_tokens,  # 동적 토큰 전달
                )
                t_llm = time.perf_counter() - t_llm_start

                logger.info(f"⏱️ LLM 생성 완료: {t_llm:.2f}s (응답 길이: {len(raw_result)} chars)")

                # 에러 응답 체크
                if raw_result.startswith("[E_GENERATE]"):
                    raise RuntimeError(raw_result)

                # 요약 모드: JSON 포맷팅
                if routing.get("needs_summary"):
                    t_format_start = time.perf_counter()
                    formatted = self._format_summary_output(raw_result, metadata)
                    t_format = time.perf_counter() - t_format_start
                    logger.info(f"⏱️ 요약 포맷팅: {t_format:.3f}s")
                    return formatted

                return raw_result.strip()

        # ===== 경로 2: LLM generate_response 직접 호출 (폴백) =====
        llm: Any = None
        if rag_adapter is not None:
            rag_llm = getattr(rag_adapter, "llm", None)
            if rag_llm is not None:
                llm = rag_llm

        if llm is None:
            generator_llm = getattr(self.generator, "llm", None)
            if generator_llm is not None:
                llm = generator_llm

        if llm is None:
            logger.error(f"LLM 접근 실패: generator type={type(self.generator)}")
            raise RuntimeError("LLM 접근 실패")

        if hasattr(llm, "generate_response"):
            logger.info("🔧 LLM generate_response 폴백 사용")
            chunks = [{"snippet": context, "content": context}]
            response = llm.generate_response(llm_prompt, chunks)
            if hasattr(response, "answer"):
                raw_result = response.answer
            else:
                raw_result = str(response)

            if routing.get("needs_summary"):
                return self._format_summary_output(raw_result, metadata)

            return raw_result.strip() if isinstance(raw_result, str) else str(raw_result)

        raise RuntimeError(f"LLM 접근 불가: {type(llm)}")

    def _build_llm_prompt(
        self,
        query: str,
        full_text: str,
        metadata: dict[str, Any],
        routing: dict[str, Any],
    ) -> tuple:
        """LLM 프롬프트 및 시스템 메시지 생성"""
        # 🔧 컨텍스트 윈도우: 요약 품질 개선
        context = full_text[:DocumentHandlerConfig.CONTEXT_WINDOW]
        filename = metadata["filename"]
        drafter = metadata.get("drafter", "")
        date = metadata.get("display_date") or metadata.get("date", "")

        detailed_mode = routing.get("detailed_mode", False)
        needs_summary = routing.get("needs_summary", False)
        detected_section = routing.get("detected_section")

        # 프롬프트 빌더 import 시도
        try:
            from app.prompts.document_prompts import build_detailed_prompt, build_qa_prompt, build_section_prompt
        except ImportError:
            # 폴백 프롬프트
            return (
                f"문서: {filename}\n기안자: {drafter}\n날짜: {date}\n\n"
                f"문서 내용:\n{context}\n\n질문: {query}\n\n위 문서 내용을 바탕으로 답변해주세요.",
                "당신은 문서 분석 전문가입니다.",
            )

        # 우선순위: detailed > summary > section > QA
        if detailed_mode:
            prompt = build_detailed_prompt(
                context=context, filename=filename,
                drafter=drafter, date=date,
            )
            # 🔧 DETAILED 모드: 요약 형식 금지, 상세 서술 강제
            system_msg = (
                "당신은 문서 분석 전문가입니다. "
                "모든 세부사항을 빠짐없이 포함하여 **상세하게 서술**하세요. "
                "절대 요약하거나 목록 형식으로 줄이지 마세요. "
                "배경, 목적, 검토 내용, 비교 대안, 선정 사유, 예산 등 모든 섹션을 충분히 설명하세요."
            )

        elif needs_summary:
            from app.rag.summary_templates import build_prompt, detect_doc_kind
            kind = detect_doc_kind(filename, full_text)
            prompt = build_prompt(
                kind=kind, filename=filename, drafter=drafter,
                display_date=date, context_text=context, claimed_total=None,
            )
            system_msg = "당신은 문서 요약 전문가입니다. JSON 형식으로만 응답하세요."

        elif detected_section:
            prompt = build_section_prompt(
                context=context, section=detected_section,
                filename=filename, drafter=drafter, date=date,
            )
            system_msg = f"당신은 문서 분석 전문가입니다. '{detected_section}' 섹션만 정확하게 추출하여 답변하세요."

        else:
            prompt = build_qa_prompt(
                context=context, query=query,
                filename=filename, drafter=drafter, date=date,
            )
            system_msg = "당신은 문서 분석 전문가입니다. 문서 내용을 기반으로 정확하게 답변하세요."

        return prompt, system_msg

    def _calculate_max_tokens(
        self,
        content_length: int,
        routing: dict[str, Any],
    ) -> int:
        """토큰 제한 계산 (속도 최적화 기반)

        2026-01-10: vLLM 커뮤니티 검증 기반 최적화
        - 목표: 생성 토큰↓ = 응답 속도↑↑
        - 긴 응답(8192토큰)은 속도 저하의 주범
        - 실용적 범위: 512-2048 토큰으로 충분한 품질 확보
        - 예상 효과: 681초 → 200-300초 (2-3배 속도 향상)
        """
        base_max_tokens = routing.get("max_tokens", DocumentHandlerConfig.DEFAULT_MAX_TOKENS)
        detailed_mode = routing.get("detailed_mode", False)
        needs_summary = routing.get("needs_summary", False)

        # 🚀 2026-01-10: detailed_mode 대폭 축소 (8192 → 2048)
        # vLLM 커뮤니티: 2048 토큰이 속도/품질 균형점
        if detailed_mode:
            dynamic_cap = 2048  # 자세히 모드: 최대 토큰 (8192 → 2048, 75% 감소)
            calculated = max(DocumentHandlerConfig.DETAILED_MIN_TOKENS, content_length // 6)
            return min(dynamic_cap, calculated)

        # 문서 길이에 따른 상한 조정 (대폭 축소)
        if content_length > 30000:
            dynamic_cap = 2048  # 긴 문서 (6144 → 2048, 67% 감소)
        elif content_length > 10000:
            dynamic_cap = 1536  # 중간 문서 (4096 → 1536, 63% 감소)
        else:
            dynamic_cap = base_max_tokens  # 짧은 문서는 기본값

        # 요약 모드: JSON 출력을 위한 최소 토큰 보장
        if needs_summary:
            calculated = max(DocumentHandlerConfig.SUMMARY_MIN_TOKENS, content_length // 6)
            return min(dynamic_cap, calculated)

        # 일반 모드: 더 보수적으로 계산
        calculated = max(DocumentHandlerConfig.NORMAL_MIN_TOKENS, content_length // 8)
        return min(dynamic_cap, calculated)

    def _format_summary_output(
        self,
        raw_result: str,
        metadata: dict[str, Any],
    ) -> str:
        """요약 결과 포맷팅"""
        try:
            from app.rag.summary_templates import detect_doc_kind, format_summary_output, parse_summary_json

            parsed = parse_summary_json(raw_result)
            kind = detect_doc_kind(metadata["filename"], "")

            # 🔧 파싱 결과 상세 로깅
            if parsed:
                has_summary = bool(parsed.get("요약"))
                logger.info(f"📊 JSON 파싱 성공: kind={kind}, keys={list(parsed.keys())}, has_요약={has_summary}")
                # 요약 필드 내용 미리보기
                if has_summary:
                    logger.info(f"📝 요약 내용: {str(parsed.get('요약', ''))[:100]}...")
            else:
                logger.warning(f"⚠️ JSON 파싱 실패: {raw_result[:200]}...")
                return raw_result.strip()

            return format_summary_output(
                parsed_json=parsed,
                kind=kind,
                filename=metadata["filename"],
                drafter=metadata.get("drafter") or "",
                display_date=metadata.get("display_date") or "",
                claimed_total=None,
            )
        except (KeyError, TypeError) as e:
            # JSON 구조 불일치
            logger.warning(f"⚠️ 요약 포맷팅 실패 (데이터 구조 오류): {e}")
            return raw_result

        except Exception as e:
            # 예상치 못한 오류
            logger.warning(f"⚠️ 요약 포맷팅 실패 ({type(e).__name__}): {e}")
            return raw_result

    def _build_fallback_response(
        self,
        full_text: str,
        metadata: dict[str, Any],
        routing: dict[str, Any],
    ) -> str:
        """LLM 실패 시 폴백 응답 생성"""
        filename = metadata.get("filename", "알 수 없음")
        drafter = metadata.get("drafter") or "정보 없음"
        date = metadata.get("display_date") or metadata.get("date") or "정보 없음"

        if routing.get("detailed_mode"):
            # 자세히 모드: 더 긴 원본 제공
            preview = full_text[:DocumentHandlerConfig.DETAILED_PREVIEW_LEN].strip()
            return (
                f"**문서명**: {filename}\n"
                f"**기안자**: {drafter} | **날짜**: {date}\n\n"
                f"---\n\n"
                f"**원본 내용**:\n\n{preview}..."
            )
        # 일반 모드: 짧은 미리보기 + 안내
        preview = full_text[:DocumentHandlerConfig.NORMAL_PREVIEW_LEN].strip()
        return (
            f"**문서명**: {filename}\n"
            f"**기안자**: {drafter} | **날짜**: {date}\n\n"
            f"---\n\n"
            f"**내용 미리보기**:\n\n{preview}...\n\n"
            f"전체 내용은 '자세히 알려줘'로 요청하세요."
        )

    def _build_evidence(
        self,
        metadata: dict[str, Any],
        full_text: str,
    ) -> list[dict[str, Any]]:
        """Evidence 구성"""
        filename = metadata["filename"]

        # 파일 경로 생성
        year_match = re.search(r"(\d{4})-", filename)
        if year_match:
            file_path = f"docs/year_{year_match.group(1)}/{filename}"
        else:
            file_path = f"docs/{filename}"

        return [{
            "doc_id": filename,
            "filename": filename,
            "file_path": file_path,
            "page": 1,
            "snippet": full_text[:DocumentHandlerConfig.EVIDENCE_SNIPPET_LEN],
            "ref": None,
            "meta": {
                "filename": filename,
                "drafter": metadata.get("drafter"),
                "date": metadata.get("display_date") or metadata.get("date"),
                "category": metadata.get("category"),
                "doctype": metadata.get("doctype"),
            },
        }]
