#!/usr/bin/env python3
"""
개선된 빠른 검색 RAG - LLM 요약 + 출처 인용 강제
"""

from modules.search_module_hybrid import SearchModuleHybrid
import time
import re

from app.core.logging import get_logger

logger = get_logger(__name__)

class QuickFixRAG:
    """빠른 검색 + LLM 요약 - 하이브리드 모드"""

    def __init__(self, use_hybrid: bool = True):
        """
        Args:
            use_hybrid: 하이브리드 검색 사용 여부 (기본값: True)
        """
        try:
            # 하이브리드 검색 모듈 사용 시도
            self.search_module = SearchModuleHybrid(use_hybrid=use_hybrid)
            logger.info(f"✅ SearchModuleHybrid 초기화 성공 (hybrid={use_hybrid})")
        except Exception as e:
            logger.warning(f"⚠️ SearchModuleHybrid 초기화 실패, 기본 SearchModule 사용: {e}")
            from modules.search_module import SearchModule
            self.search_module = SearchModule()

        # LLM (지연 로딩)
        self.llm = None
        self.llm_loaded = False

    def answer(self, query: str, use_llm_summary: bool = True) -> str:
        """
        검색 + LLM 요약 반환

        Args:
            query: 사용자 질문
            use_llm_summary: LLM 요약 사용 여부 (기본: True)
        """

        try:
            # 1. 기안자 및 연도 패턴 추출
            drafter_name = self._extract_author_name(query)
            year_match = re.search(r'(\d{4})\s*년', query)
            year = year_match.group(1) if year_match else None

            # 2. 조합 검색: 연도 + 기안자 (우선순위 최상위)
            if year and drafter_name:
                logger.info(f"✅ 조합 검색 모드: {year}년 + 기안자={drafter_name}")
                search_results = self._search_by_year_and_drafter(year, drafter_name)
                if search_results:
                    logger.info(f"✅ {year}년 {drafter_name} 문서 {len(search_results)}개 발견")
                    return self._format_drafter_results(query, f"{year}년 {drafter_name}", search_results)
                else:
                    logger.warning(f"⚠️  {year}년 {drafter_name} 문서 없음")
                    return f"❌ {year}년에 {drafter_name}이(가) 작성한 문서를 찾을 수 없습니다."

            # 3. 기안자만 검색
            if drafter_name:
                logger.info(f"✅ 기안자 검색 모드: {drafter_name}")
                search_results = self.search_module.search_by_drafter(drafter_name, top_k=200)
                if search_results:
                    logger.info(f"✅ 기안자 '{drafter_name}' 문서 {len(search_results)}개 발견")
                    return self._format_drafter_results(query, drafter_name, search_results)
                else:
                    logger.warning(f"⚠️  기안자 '{drafter_name}' 문서 없음")

            # 4. 연도만 검색
            if year:
                logger.info(f"✅ 연도 검색 모드: {year}년")
                search_results = self._search_by_year(year)
                if search_results:
                    logger.info(f"✅ {year}년 문서 {len(search_results)}개 발견")
                    return self._format_search_results(f"{year}년 문서", search_results[:20])

            # 5. 일반 검색
            search_results = self.search_module.search_by_content(query, top_k=5)

            if not search_results:
                return "❌ 관련 문서를 찾을 수 없습니다."

            # 3. LLM 요약 사용 여부 결정
            if use_llm_summary and self._ensure_llm_loaded():
                return self._answer_with_llm_summary(query, search_results)
            else:
                # LLM 없이 검색 결과만 반환 (출처 포함)
                return self._format_search_results(query, search_results)

        except Exception as e:
            logger.error(f"❌ 검색 오류: {e}")
            return f"❌ 오류: {str(e)}"

    def _answer_with_llm_summary(self, query: str, search_results: list) -> str:
        """LLM으로 검색 결과 요약 (핵심만 추출)"""

        try:
            # 상위 3개 문서만 사용
            top_docs = search_results[:3]

            # 컨텍스트 구성 (금액/품목 정보 포함하도록 충분한 길이)
            context_chunks = []
            for doc in top_docs:
                context_chunks.append({
                    'source': doc['filename'],
                    'content': doc.get('content', '')[:3000],  # 3000자로 확장 (금액/품목 정보 포함)
                    'score': doc.get('score', 0.8),
                    'metadata': {
                        '날짜': doc.get('date', ''),
                        '카테고리': doc.get('category', ''),
                        '기안자': doc.get('department', '')
                    }
                })

            # LLM에게 핵심만 요약 요청
            response = self.llm.generate_response(query, context_chunks, max_retries=1)

            # 답변 추출
            if hasattr(response, 'answer'):
                summary = response.answer
            else:
                summary = str(response)

            # 출처 강제 추가 (LLM이 인용 안했을 경우)
            if '[' not in summary or '.pdf]' not in summary:
                # LLM이 출처를 안 달았으면 강제로 추가
                sources = [f"[{doc['filename']}]" for doc in top_docs[:2]]
                summary += f"\n\n출처: {', '.join(sources)}"

            return summary

        except Exception as e:
            logger.error(f"❌ LLM 요약 실패: {e}, 검색 결과로 대체")
            return self._format_search_results(query, search_results)

    def _is_valid_drafter_name(self, drafter: str) -> bool:
        """기안자 이름 유효성 검증 (잘못된 키워드 필터링)

        Args:
            drafter: 기안자 이름

        Returns:
            유효한 이름이면 True, 잘못된 키워드면 False
        """
        if not drafter or drafter == '미상':
            return False

        # 🔥 잘못된 키워드 필터 (파일명에서 추출된 단어들)
        invalid_keywords = [
            'DVR', 'dvr', 'CAMERA', 'camera', '카메라', 'TV', 'tv',
            '스튜디오', 'studio', 'STUDIO', '방송', '장비', '모니터',
            '워크스테이션', '컴퓨터', 'PC', 'pc', '수리', '구매', '교체'
        ]

        return drafter not in invalid_keywords

    def _format_search_results(self, query: str, search_results: list) -> str:
        """검색 결과 포매팅 (출처 강제 포함)"""
        total_count = len(search_results)

        answer = f"**{query}** 검색 결과\n\n"
        answer += f"📊 **총 {total_count}개 문서** 발견\n\n"

        for i, doc in enumerate(search_results, 1):
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"

            # 기안자 정보 우선 표시 (유효한 이름만)
            drafter = doc.get('department', '')
            if self._is_valid_drafter_name(drafter):
                answer += f"   - 기안자: {drafter}\n"

            # 내용 미리보기 (짧게)
            content_preview = (doc.get('content', '')[:150] + "..."
                               if len(doc.get('content', '')) > 150
                               else doc.get('content', ''))
            answer += f"   - 내용: {content_preview}\n"

            # ✅ 출처 강제 추가
            answer += f"   - 📎 출처: [{doc['filename']}]\n\n"

        return answer

    def _format_drafter_results(self, query: str, drafter_name: str, search_results: list) -> str:
        """기안자 검색 결과 포매팅 (출처 포함)"""
        total_count = len(search_results)
        display_count = min(100, total_count)  # 최대 100개 표시

        answer = f"**기안자: {drafter_name}** 검색 결과\n\n"
        answer += f"📊 **총 {total_count}개 문서** 발견 ({display_count}개 표시)\n\n"

        # 날짜별로 정렬 (최신순)
        sorted_results = sorted(search_results,
                                key=lambda x: x.get('date', ''),
                                reverse=True)

        for i, doc in enumerate(sorted_results[:display_count], 1):
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"

            # 내용 미리보기
            content_preview = (doc.get('content', '')[:150] + "..."
                               if len(doc.get('content', '')) > 150
                               else doc.get('content', ''))
            answer += f"   - 내용: {content_preview}\n"

            # ✅ 출처 강제 추가
            answer += f"   - 📎 출처: [{doc['filename']}]\n\n"

        # 남은 문서 안내
        remaining = total_count - display_count
        if remaining > 0:
            answer += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            answer += f"📌 **{remaining}개 문서 더 있습니다**\n"
            answer += f"💡 카테고리나 기간으로 좁혀보세요\n"

        return answer

    def _search_by_year_and_drafter(self, year: str, drafter: str) -> list:
        """연도 + 기안자 조합 검색 (metadata.db 사용, 중복 제거)

        Args:
            year: 연도 (예: "2025")
            drafter: 기안자 이름 (예: "최새름")

        Returns:
            해당 연도 + 기안자의 문서 리스트 (중복 제거됨)
        """
        try:
            import sqlite3
            import pdfplumber
            from pathlib import Path

            conn = sqlite3.connect('metadata.db')
            cursor = conn.cursor()

            # year 필드와 drafter 필드로 필터 (metadata.db)
            cursor.execute("""
                SELECT path, filename, date, category, drafter, text_preview
                FROM documents
                WHERE year = ? AND drafter LIKE ?
                ORDER BY date DESC
                LIMIT 200
            """, (year, f'%{drafter}%'))

            results = []
            seen_filenames = set()  # 중복 제거용

            for path, filename, date, category, drafter_val, text_preview in cursor.fetchall():
                # 중복 제거: 파일명 기준
                if filename in seen_filenames:
                    continue
                seen_filenames.add(filename)

                result = {
                    'filename': filename,
                    'path': path,
                    'date': date or '',
                    'category': category or '',
                    'department': drafter_val or '',
                    'content': text_preview or '',
                    'score': 1.5
                }

                # PDF 전체 텍스트 로드 (처음 5개만)
                if len(results) < 5 and path:
                    try:
                        pdf_path = Path(path)
                        if pdf_path.exists() and pdf_path.suffix.lower() == '.pdf':
                            with pdfplumber.open(pdf_path) as pdf:
                                full_text = ""
                                for page in pdf.pages[:3]:  # 최대 3페이지
                                    page_text = page.extract_text() or ""
                                    full_text += page_text + "\n\n"
                                    if len(full_text) > 5000:
                                        break
                                result['content'] = full_text
                    except Exception as e:
                        logger.warning(f"PDF 읽기 실패 ({filename}): {e}")

                results.append(result)

            conn.close()
            logger.info(f"✅ 조합 검색 완료: {len(results)}건 (중복 제거 후)")
            return results

        except Exception as e:
            logger.error(f"❌ 조합 검색 실패: {e}")
            return []

    def _search_by_year(self, year: str) -> list:
        """연도별 문서 검색 (metadata.db 사용)

        Args:
            year: 연도 (예: "2025")

        Returns:
            해당 연도의 문서 리스트
        """
        try:
            import sqlite3
            import pdfplumber
            from pathlib import Path

            conn = sqlite3.connect('metadata.db')
            cursor = conn.cursor()

            # year 필드에서 검색 (metadata.db)
            cursor.execute("""
                SELECT path, filename, date, category, drafter, text_preview
                FROM documents
                WHERE year = ?
                ORDER BY date DESC
                LIMIT 200
            """, (year,))

            results = []
            for path, filename, date, category, drafter, text_preview in cursor.fetchall():
                result = {
                    'filename': filename,
                    'path': path,
                    'date': date or '',
                    'category': category or '',
                    'department': drafter or '',
                    'content': text_preview or '',
                    'score': 1.5
                }

                # PDF 전체 텍스트 로드 (처음 5개만)
                if len(results) < 5 and path:
                    try:
                        pdf_path = Path(path)
                        if pdf_path.exists() and pdf_path.suffix.lower() == '.pdf':
                            with pdfplumber.open(pdf_path) as pdf:
                                full_text = ""
                                for page in pdf.pages[:3]:  # 최대 3페이지
                                    page_text = page.extract_text() or ""
                                    full_text += page_text + "\n\n"
                                    if len(full_text) > 5000:
                                        break
                                result['content'] = full_text
                    except Exception as e:
                        logger.warning(f"PDF 읽기 실패 ({filename}): {e}")

                results.append(result)

            conn.close()
            return results

        except Exception as e:
            logger.error(f"❌ 연도 검색 실패: {e}")
            return []

    def _extract_author_name(self, query: str) -> str:
        """질문에서 기안자/작성자 이름 추출 (다양한 패턴 지원)

        지원 패턴:
        - "남준수 문서"
        - "남준수가 작성한"
        - "남준수가 작성안" (오타)
        - "기안자 남준수"
        - "작성자: 남준수"
        - "남준수 기안서"
        """
        # 패턴 1: "기안자 XXX", "작성자 XXX"
        match = re.search(r'(기안자|작성자|제안자)[:\s]+([가-힣]{2,4})', query)
        if match:
            return match.group(2)

        # 패턴 2: "XXX가 작성한", "XXX가 작성안"
        match = re.search(r'([가-힣]{2,4})가?\s*(작성한|작성안|기안한|쓴|만든)', query)
        if match:
            return match.group(1)

        # 패턴 3: "XXX 문서", "XXX 기안서" (2-4글자 한글 이름)
        match = re.search(r'([가-힣]{2,4})\s*(문서|기안서|기안|검토서)', query)
        if match:
            name = match.group(1)
            # 일반 명사가 아닌 경우만 (예: "구매 문서"는 제외)
            if name not in ['구매', '수리', '장비', '카메라', '최근', '최신', '전체']:
                return name

        return None

    def _ensure_llm_loaded(self) -> bool:
        """LLM 로딩 (지연 로딩)"""
        if self.llm_loaded:
            return True

        try:
            from rag_system.qwen_llm import QwenLLM
            from config import QWEN_MODEL_PATH

            logger.info("🤖 LLM 로딩 중 (빠른 검색 요약용)...")
            self.llm = QwenLLM(model_path=QWEN_MODEL_PATH)
            self.llm_loaded = True
            logger.info("✅ LLM 로드 완료")
            return True

        except Exception as e:
            logger.warning(f"⚠️ LLM 로드 실패 (검색 결과만 반환): {e}")
            return False


if __name__ == "__main__":
    # 빠른 테스트
    print("🚀 QuickFixRAG v3 (LLM 요약 + 출처 강제)")
    print("=" * 60)

    start = time.time()
    rag = QuickFixRAG()
    init_time = time.time() - start

    print(f"⏱️  초기화 시간: {init_time:.4f}초")
    print()

    # 테스트 쿼리
    test_queries = [
        "카메라 수리",
        "HP Z8 워크스테이션 얼마"
    ]

    for query in test_queries:
        print(f"\n📝 질문: {query}")
        print("-" * 60)

        start = time.time()
        answer = rag.answer(query)
        elapsed = time.time() - start

        print(answer[:500])
        if len(answer) > 500:
            print(f"... (총 {len(answer)}자)")
        print(f"\n⏱️  응답 시간: {elapsed:.4f}초")
        print("=" * 60)
