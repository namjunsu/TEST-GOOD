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
        try:
            # 1. 문서 식별
            target_filename = self._identify_document(query, selected_filename)

            if not target_filename:
                return self._make_empty_response(
                    "문서를 찾을 수 없습니다. 문서명을 명확히 입력해주세요.",
                )

            # 2. DB에서 메타데이터 조회
            metadata = self._get_document_metadata(target_filename)

            if not metadata:
                return self._make_empty_response(
                    f"'{target_filename}' 문서의 메타데이터를 찾을 수 없습니다.",
                )

            # 3. 문서 텍스트 로드
            full_text = self._load_full_text(metadata["filename"])

            if not full_text or len(full_text.strip()) < DocumentHandlerConfig.MIN_TEXT_LENGTH:
                return self._make_empty_response(
                    f"'{metadata['filename']}' 문서의 텍스트를 확보하지 못했습니다.",
                )

            # 4. 라우팅 결정 (섹션 감지, 요약 여부 등)
            routing = self._route_document_query(query)

            # 5. 응답 생성 (LLM 또는 원문)
            answer_text = self._generate_answer(
                query=query,
                full_text=full_text,
                metadata=metadata,
                routing=routing,
            )

            # 6. Evidence 구성
            evidence = self._build_evidence(metadata, full_text)

            logger.info({
                "mode": "DOCUMENT",
                "filename": metadata["filename"],
                "text_length": len(full_text),
                "routing": routing,
            })

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

    def _load_full_text(self, filename: str) -> str:
        """문서 전체 텍스트 로드"""
        # 1. extracted 디렉토리에서 로드 시도
        full_text = load_document_text(filename)

        if full_text:
            return full_text

        # 2. 인덱스 청크 기반 폴백 (top_k 확대: 요약 품질 개선)
        logger.warning(f"⚠️ extracted txt 없음, 인덱스 청크 폴백 시도: {filename}")
        try:
            # 🔧 top_k를 확대하여 더 많은 컨텍스트 확보
            chunks = self._make_chunks_for_doc(filename, top_k=DocumentHandlerConfig.FALLBACK_CHUNK_TOP_K)
            if chunks:
                max_snippet = DocumentHandlerConfig.CHUNK_SNIPPET_MAX
                joined = "\n\n".join(
                    [(ch.get("text") or ch.get("snippet") or ch.get("content") or "")[:max_snippet]
                     for ch in chunks],
                )[:DocumentHandlerConfig.CHUNK_CONTEXT_MAX]
                logger.info(f"✅ 청크 {len(chunks)}개 결합 → {len(joined)}자 확보")
                return joined
        except (AttributeError, KeyError) as e:
            # 인덱스 구조 문제
            logger.warning(f"⚠️ 청크 폴백 - 인덱스 접근 오류: {e}")

        except Exception as e:
            # 예상치 못한 오류
            logger.warning(f"⚠️ 청크 폴백 실패 ({type(e).__name__}): {e}")

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
        # 프롬프트 생성 (먼저 준비)
        llm_prompt, system_msg = self._build_llm_prompt(
            query=query,
            full_text=full_text,
            metadata=metadata,
            routing=routing,
        )

        # 컨텍스트 준비
        context = full_text[:DocumentHandlerConfig.CONTEXT_WINDOW]

        # 모드 결정
        if routing.get("detailed_mode"):
            mode = "rag"
        elif routing.get("needs_summary"):
            mode = "summarize"
        else:
            mode = "rag"

        # ===== 경로 1: _LLMAdapter.generate_from_context() 사용 (권장, 요약 모드 제외) =====
        # 🔧 요약 모드에서는 경로 1 스킵 → QwenLLM이 별도 시스템 프롬프트를 사용하여 JSON 출력 지시가 무시됨
        # 요약 모드는 경로 2(llama_cpp 직접 접근)로 처리하여 JSON 출력을 보장함
        if not routing.get("needs_summary"):
            rag_adapter = getattr(self.generator, "rag", None)
            if rag_adapter is not None:
                generate_fn = getattr(rag_adapter, "generate_from_context", None)
                if generate_fn is not None:
                    logger.info(f"🎯 _LLMAdapter.generate_from_context() 사용 (mode={mode})")
                    raw_result: str = generate_fn(
                        query=llm_prompt,
                        context=context,
                        temperature=DocumentHandlerConfig.LLM_TEMPERATURE,
                        mode=mode,
                        system_msg=system_msg,  # 🔧 시스템 프롬프트 전달
                    )

                    # 에러 응답 체크
                    if raw_result.startswith("[E_GENERATE]"):
                        raise RuntimeError(raw_result)

                    return raw_result.strip()

        # ===== 경로 2: llama_cpp.Llama 직접 접근 (폴백) =====
        llm: Any = None
        rag_adapter = getattr(self.generator, "rag", None)
        if rag_adapter is not None:
            rag_llm = getattr(rag_adapter, "llm", None)
            if rag_llm is not None:
                llm = rag_llm  # QwenLLM

        if llm is None:
            generator_llm = getattr(self.generator, "llm", None)
            if generator_llm is not None:
                llm = generator_llm

        if llm is None:
            logger.error(f"LLM 접근 실패: generator type={type(self.generator)}")
            raise RuntimeError("LLM 접근 실패")

        # 토큰 제한 조정
        max_tokens = self._calculate_max_tokens(
            content_length=len(full_text),
            routing=routing,
        )

        # llama_cpp.Llama 접근 (QwenLLM.llm)
        from llama_cpp import Llama
        llm_instance = getattr(llm, "llm", llm)
        if isinstance(llm_instance, Llama):
            import time
            llm_start = time.time()
            logger.info(f"🔧 LLM 호출: max_tokens={max_tokens}, prompt_len={len(llm_prompt)}")
            output = llm_instance.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": llm_prompt},
                ],
                max_tokens=max_tokens,
                temperature=DocumentHandlerConfig.LLM_TEMPERATURE,
            )
            # 타입 안전: content가 None일 수 있음
            content = output["choices"][0]["message"]["content"]  # type: ignore[index]
            raw_result: str = str(content) if content else ""
            llm_elapsed = time.time() - llm_start

            # 🔧 LLM 응답 로깅 (핵심 정보 + 미리보기)
            logger.info(f"📤 LLM 응답: {len(raw_result)}자, {llm_elapsed:.2f}초")
            logger.info(f"📤 응답 미리보기: {raw_result[:200].replace(chr(10), ' ')}...")

            if routing.get("needs_summary"):
                return self._format_summary_output(raw_result, metadata)

            return raw_result.strip()

        # ===== 경로 3: generate_response 메서드 사용 (최후 폴백) =====
        if hasattr(llm, "generate_response"):
            logger.info("🔧 LLM generate_response 폴백 사용")
            chunks = [{"snippet": context, "content": context}]
            response = llm.generate_response(llm_prompt, chunks, max_retries=1, mode=mode)
            if hasattr(response, "answer"):
                return response.answer
            return str(response)

        raise RuntimeError(f"LLM 타입 불일치: {type(llm_instance)}")

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
        """토큰 제한 계산"""
        base_max_tokens = routing.get("max_tokens", DocumentHandlerConfig.DEFAULT_MAX_TOKENS)
        detailed_mode = routing.get("detailed_mode", False)
        needs_summary = routing.get("needs_summary", False)

        # 요약 모드: JSON 출력을 위한 최소 토큰 보장 (불완전 요약 방지)
        # 🔧 SUMMARY_MIN_TOKENS(1000)을 base_max_tokens보다 우선하여 JSON 응답이 잘리지 않도록 함
        if needs_summary:
            return max(DocumentHandlerConfig.SUMMARY_MIN_TOKENS, content_length // 3)

        if detailed_mode:
            return min(base_max_tokens, max(DocumentHandlerConfig.DETAILED_MIN_TOKENS, content_length // 3))
        return min(base_max_tokens, max(DocumentHandlerConfig.NORMAL_MIN_TOKENS, content_length // 4))

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
