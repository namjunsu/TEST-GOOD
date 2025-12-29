"""종합 리포트 핸들러

여러 문서를 종합 분석하여 표/리포트 생성
"현황 표로 정리", "종합해서 보여줘" 같은 요청 처리

2025-12-26: 초기 구현
"""

import re
from typing import Any

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from config.constants import HandlerConfig

from .base import BaseHandler

logger = get_logger(__name__)


class ComprehensiveReportHandler(BaseHandler):
    """종합 리포트 핸들러

    여러 문서의 정보를 종합하여 구조화된 표/리포트를 생성합니다.

    특징:
    - 관련 문서 최대한 많이 검색 (top_k=20)
    - 구조화된 정보 추출 (모델명, 수량, 위치, 날짜 등)
    - 중복 제거 및 최신 정보 우선
    - 실무에 사용 가능한 품질의 표 생성
    """

    mode = "COMPREHENSIVE_REPORT"

    def __init__(self, pipeline):
        super().__init__(pipeline)
        self._db = MetadataDB()

    def handle(self, query: str, **kwargs) -> dict[str, Any]:
        """종합 리포트 생성

        Args:
            query: 사용자 쿼리
            **kwargs: 추가 파라미터

        Returns:
            표준 응답 딕셔너리
        """
        try:
            # 1. 키워드 추출
            keywords = self._extract_keywords(query)
            logger.info(f"📊 종합 리포트 생성: 키워드='{keywords}'")

            # 2. 관련 문서 최대한 많이 검색
            search_results = self.retriever.search(
                keywords,
                top_k=HandlerConfig.COMPREHENSIVE_REPORT_TOP_K,  # 20개
            )

            if not search_results:
                return self._make_empty_response(f"'{keywords}' 관련 문서를 찾지 못했습니다.")

            # 3. 파일명 추출
            filenames = self._extract_unique_filenames(search_results)
            logger.info(f"📄 검색된 문서: {len(filenames)}개")

            # 4. 문서 전체 내용 로드 (text_preview가 아닌 전체 텍스트)
            documents_data = self._load_full_documents(filenames)

            # 5. LLM에게 종합 분석 요청
            report = self._generate_comprehensive_report(
                query=query,
                keywords=keywords,
                documents_data=documents_data,
            )

            # 6. 응답 생성
            return {
                "mode": self.mode,
                "text": report,
                "files": filenames,
                "count": len(filenames),
                "citations": self._build_citations(documents_data),
                "evidence": self._build_citations(documents_data),
                "status": {
                    "retrieved_count": len(filenames),
                    "selected_count": len(documents_data),
                    "found": True,
                },
            }

        except Exception as e:
            logger.error(f"❌ 종합 리포트 생성 실패: {e}", exc_info=True)
            return self._make_error_response(f"종합 리포트 생성 중 오류: {e}")

    def _extract_keywords(self, query: str) -> str:
        """쿼리에서 핵심 키워드 추출"""
        # 불용어 제거
        stop_words = ["현황", "표", "정리", "종합", "알려", "보여", "줘", "해줘", "해"]

        keywords = query
        for word in stop_words:
            keywords = keywords.replace(word, " ")

        keywords = re.sub(r"\s+", " ", keywords).strip()
        return keywords

    def _extract_unique_filenames(self, search_results: list[dict]) -> list[str]:
        """검색 결과에서 고유 파일명 추출"""
        filenames = []
        seen = set()
        for result in search_results:
            filename = result.get("filename") or result.get("doc_id")
            if filename and filename not in seen:
                filenames.append(filename)
                seen.add(filename)
        return filenames

    def _load_full_documents(self, filenames: list[str]) -> list[dict[str, Any]]:
        """문서 전체 내용 로드 (text_preview가 아닌 전체 텍스트)"""
        from pathlib import Path

        documents_data = []
        extracted_dir = Path("data/extracted")

        for filename in filenames[:HandlerConfig.COMPREHENSIVE_REPORT_MAX_DOCS]:
            # DB에서 메타데이터 조회
            conn = self._db._get_conn()
            cursor = conn.execute(
                "SELECT * FROM documents WHERE filename = ?",
                (filename,),
            )
            row = cursor.fetchone()

            if not row:
                continue

            doc_meta = dict(row)

            # 전체 텍스트 로드
            base_name = filename.replace(".pdf", "")
            txt_path = extracted_dir / f"{base_name}.txt"

            full_text = ""
            if txt_path.exists():
                try:
                    full_text = txt_path.read_text(encoding="utf-8")
                    # 너무 긴 문서는 앞부분만 (메모리 절약)
                    if len(full_text) > 10000:
                        full_text = full_text[:10000] + "\n... (이하 생략)"
                except Exception as e:
                    logger.warning(f"⚠️ 텍스트 로드 실패 ({filename}): {e}")
                    full_text = doc_meta.get("text_preview", "")
            else:
                full_text = doc_meta.get("text_preview", "")

            documents_data.append({
                "filename": filename,
                "date": doc_meta.get("date") or doc_meta.get("display_date", "날짜 없음"),
                "drafter": doc_meta.get("drafter", "작성자 미상"),
                "title": doc_meta.get("title", filename),
                "full_text": full_text,
            })

        logger.info(f"✅ {len(documents_data)}개 문서 전체 내용 로드 완료")
        return documents_data

    def _generate_comprehensive_report(
        self,
        query: str,
        keywords: str,
        documents_data: list[dict[str, Any]],
    ) -> str:
        """LLM을 사용하여 종합 리포트 생성"""

        # 컨텍스트 구성
        context_parts = []
        for i, doc in enumerate(documents_data, 1):
            context_parts.append(
                f"## 문서 {i}: {doc['title']}\n"
                f"날짜: {doc['date']} | 기안자: {doc['drafter']}\n\n"
                f"{doc['full_text']}\n"
                f"{'=' * 80}\n"
            )

        context = "\n".join(context_parts)

        # 프롬프트 생성
        prompt = f"""아래 {len(documents_data)}개 문서를 종합하여 '{keywords}' 현황을 **실무에 사용 가능한 품질의 표**로 정리하라.

[중요 지시사항]
1. **모든 문서의 정보를 빠짐없이 통합**할 것
   - 각 문서에서 관련 정보(모델명, 수량, 위치, 날짜, 상태 등)를 추출
   - 중복 항목은 최신 정보 우선

2. **표 구조 (실무 표준)**:
   | 위치/실 | 모델명 | 수량 | 설치/교체일 | 상태 | 출처 문서 |

3. **추가 정보**:
   - 표 상단: 전체 개요 (총 대수, 주요 현황 등)
   - 표 하단: 특이사항, 주의사항
   - 참고한 문서 목록

4. **정확성**:
   - 문서에 없는 정보는 추측하지 말 것
   - 숫자/날짜는 원본 그대로 사용
   - 불확실한 정보는 "확인 필요" 표시

사용자 질문: {query}

답변 (표 형식):"""

        # LLM 호출
        try:
            answer = self.generator.generate(
                query=prompt,
                context=context,
                temperature=0.1,  # 정확성 최우선
                mode="comprehensive_report",
            )

            return answer

        except Exception as e:
            logger.error(f"❌ LLM 호출 실패: {e}")
            return f"종합 리포트 생성 중 오류가 발생했습니다: {e}"

    def _build_citations(self, documents_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Citations 생성"""
        citations = []
        for doc in documents_data:
            citations.append({
                "doc_id": doc["filename"],
                "filename": doc["filename"],
                "page": 1,
                "snippet": doc["full_text"][:200] + "..." if len(doc["full_text"]) > 200 else doc["full_text"],
                "meta": {
                    "filename": doc["filename"],
                    "date": doc["date"],
                    "drafter": doc["drafter"],
                    "title": doc["title"],
                },
            })
        return citations
