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

from app.core.errors import DocumentNotFoundError
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

# 섹션 키워드 매핑
SECTION_KEYWORDS = {
    "검토": ["검토", "검토내용", "검토 내용", "검토 세부", "리뷰", "검토의견", "검토 의견"],
    "배경": ["배경", "목적", "배경/목적", "추진배경", "추진 배경", "사유"],
    "개요": ["개요 부분", "개요만", "개요 세부"],
    "비교": ["비교", "대안", "비교대안", "비교 대안", "방안", "옵션"],
    "선정": ["선정", "권고", "추천", "제안", "선정사유"],
    "내역": ["내역", "세부내역", "세부 내역", "상세내역", "상세"],
    "예산": ["예산", "비용", "금액", "합계", "총액"],
}

# 데이터 디렉토리
EXTRACTED_DIR = Path("data/extracted")


# ============================================================================
# 헬퍼 함수
# ============================================================================

def extract_filename_from_query(query: str) -> Optional[str]:
    """쿼리에서 파일명 추출"""
    match = re.search(r"(\S+\.pdf)", query, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_keywords_for_document(query: str) -> str:
    """문서 조회용 키워드 추출"""
    keywords = query
    for word in DOCUMENT_STOP_WORDS:
        keywords = keywords.replace(word, " ")
    return " ".join(keywords.split())


def detect_section(query: str) -> Optional[str]:
    """쿼리에서 섹션 키워드 감지"""
    query_lower = query.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                return section
    return None


def safe_filename(meta: dict = None, doc_path: str = None) -> str:
    """파일명 안전 추출"""
    import os

    meta = meta or {}
    return (
        meta.get("fname")
        or meta.get("filename")
        or meta.get("doc_id")
        or (os.path.basename(doc_path) if doc_path else None)
        or "미상 문서"
    )


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

        except Exception as e:
            logger.error(f"❌ DOCUMENT 모드 처리 실패: {e}", exc_info=True)
            return self._make_error_response(
                f"문서 내용 조회 중 오류가 발생했습니다: {e!s}",
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

        except Exception as e:
            logger.error(f"❌ 메타데이터 조회 실패: {e}")
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
                joined = "\n\n".join(
                    [(ch.get("text") or ch.get("snippet") or ch.get("content") or "")[:DocumentHandlerConfig.CHUNK_SNIPPET_MAX]
                     for ch in chunks],
                )[:DocumentHandlerConfig.CHUNK_CONTEXT_MAX]
                logger.info(f"✅ 청크 {len(chunks)}개 결합 → {len(joined)}자 확보")
                return joined
        except Exception as e:
            logger.warning(f"⚠️ 청크 폴백 실패: {e}")

        return ""

    def _make_chunks_for_doc(self, filename: str, top_k: int = DocumentHandlerConfig.DEFAULT_CHUNK_TOP_K) -> list[dict[str, Any]]:
        """특정 문서의 청크만 로드 (top_k: 최대 청크 수)"""
        try:
            # BM25 인덱스에서 직접 접근
            if hasattr(self.retriever, "bm25") and self.retriever.bm25:
                bm25_store = self.retriever.bm25
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

        except Exception as e:
            logger.error(f"❌ 문서 청크 로드 실패: {e}")
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
        except Exception as e:
            logger.warning(f"⚠️ LLM 응답 생성 실패: {e}", exc_info=True)
            # 모드별 폴백 응답 차별화
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

        # ===== 경로 1: _LLMAdapter.generate_from_context() 사용 (권장) =====
        if hasattr(self.generator, "rag") and self.generator.rag:
            rag = self.generator.rag
            if hasattr(rag, "generate_from_context"):
                logger.info(f"🎯 _LLMAdapter.generate_from_context() 사용 (mode={mode})")
                raw_result = rag.generate_from_context(
                    query=llm_prompt,
                    context=context,
                    temperature=DocumentHandlerConfig.LLM_TEMPERATURE,
                    mode=mode,
                )

                # 에러 응답 체크
                if raw_result.startswith("[E_GENERATE]"):
                    raise RuntimeError(raw_result)

                # 요약 모드 후처리
                if routing.get("needs_summary"):
                    return self._format_summary_output(raw_result, metadata)

                return raw_result.strip()

        # ===== 경로 2: llama_cpp.Llama 직접 접근 (폴백) =====
        llm = None
        if hasattr(self.generator, "rag") and self.generator.rag:
            rag = self.generator.rag
            if hasattr(rag, "llm") and rag.llm:
                llm = rag.llm  # QwenLLM

        if llm is None and hasattr(self.generator, "llm") and self.generator.llm:
            llm = self.generator.llm

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
            logger.info("🔧 llama_cpp.Llama 직접 접근 (폴백)")
            output = llm_instance.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": llm_prompt},
                ],
                max_tokens=max_tokens,
                temperature=DocumentHandlerConfig.LLM_TEMPERATURE,
            )
            raw_result = output["choices"][0]["message"]["content"]

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
            system_msg = "당신은 문서 분석 전문가입니다. 모든 세부사항을 빠짐없이 포함하여 상세하게 답변하세요."

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

        # 요약 모드: 최소 토큰 보장 (불완전 요약 방지)
        if needs_summary:
            return max(DocumentHandlerConfig.SUMMARY_MIN_TOKENS, min(base_max_tokens, content_length // 2))

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

            # JSON 파싱 실패 시 원본 LLM 응답 반환
            if not parsed:
                logger.warning(f"⚠️ JSON 파싱 실패, 원본 응답 사용: {raw_result[:100]}...")
                return raw_result.strip()

            kind = detect_doc_kind(metadata["filename"], "")

            return format_summary_output(
                parsed_json=parsed,
                kind=kind,
                filename=metadata["filename"],
                drafter=metadata.get("drafter"),
                display_date=metadata.get("display_date"),
                claimed_total=None,
            )
        except Exception as e:
            logger.warning(f"⚠️ 요약 포맷팅 실패: {e}")
            return raw_result

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
