#!/usr/bin/env python3
"""
다중 문서 검색 시스템
여러 문서를 통합 검색하고 종합 답변 생성
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import logging

# RAG 모듈 임포트
from rag_system.bm25_store import BM25Store
from rag_system.korean_vector_store import KoreanVectorStore
from rag_system.hybrid_search import HybridSearch
from rag_system.korean_reranker import KoreanReranker
from rag_system.qwen_llm import QwenLLM
from rag_system.llm_singleton import LLMSingleton

# 로깅 설정
logger = logging.getLogger(__name__)

class MultiDocumentSearch:
    """다중 문서 검색 및 통합 답변 생성"""

    def __init__(self):
        self.docs_dir = Path("docs")
        self.index_dir = Path("indexes")
        self.index_dir.mkdir(exist_ok=True)

        # RAG 컴포넌트 초기화
        self.bm25 = BM25Store()
        self.vector_store = KoreanVectorStore()
        self.hybrid_search = HybridSearch()
        self.reranker = KoreanReranker()

        # LLM 초기화 - model_path 필요
        import os
        model_path = os.getenv('MODEL_PATH', 'models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf')
        self.llm = LLMSingleton.get_instance(model_path=model_path)

        # 문서 청크 캐시
        self.chunks_cache = {}

        logger.info("MultiDocumentSearch 초기화 완료")

    def search_multiple_docs(self, query: str, top_k: int = 5) -> List[Dict]:
        """여러 문서에서 관련 내용 검색"""

        # 쿼리 타입 분류
        query_type = self._classify_query_type(query)

        # 하이브리드 검색 수행
        results = self.hybrid_search.search(
            query=query,
            top_k=top_k * 2,  # Reranking을 위해 더 많이 검색
            search_type=query_type
        )

        # Reranking
        if results:
            results = self.reranker.rerank(results, query, top_k)

        return results

    def aggregate_answer(self, query: str, documents: List[Dict]) -> str:
        """여러 문서를 종합한 답변 생성"""

        query_type = self._classify_query_type(query)

        if query_type == "aggregation":
            return self._aggregate_total(query, documents)
        elif query_type == "similarity":
            return self._find_similar_cases(query, documents)
        elif query_type == "timeline":
            return self._create_timeline(query, documents)
        elif query_type == "comparison":
            return self._compare_documents(query, documents)
        else:
            return self._generate_comprehensive_answer(query, documents)

    def _classify_query_type(self, query: str) -> str:
        """쿼리 타입 분류"""
        query_lower = query.lower()

        if any(word in query_lower for word in ["총액", "합계", "총", "모든"]):
            return "aggregation"
        elif any(word in query_lower for word in ["비슷한", "유사한", "같은"]):
            return "similarity"
        elif any(word in query_lower for word in ["연도별", "월별", "기간별", "추이"]):
            return "timeline"
        elif any(word in query_lower for word in ["비교", "차이", "대비"]):
            return "comparison"
        else:
            return "general"

    def _aggregate_total(self, query: str, documents: List[Dict]) -> str:
        """금액 총합 계산"""
        total = 0
        details = []

        for doc in documents:
            # 금액 추출
            amounts = self._extract_amounts(doc['content'])
            if amounts:
                doc_total = sum(amounts)
                total += doc_total
                details.append({
                    'source': doc['metadata']['source'],
                    'amount': doc_total
                })

        # 응답 생성
        response = f"📊 **검색 결과: {len(documents)}개 문서**\n\n"

        for detail in details:
            response += f"• {detail['source']}: {detail['amount']:,}원\n"

        response += f"\n💰 **총액: {total:,}원**"

        return response

    def _find_similar_cases(self, query: str, documents: List[Dict]) -> str:
        """유사 사례 찾기"""
        cases = []

        for doc in documents:
            # 주요 정보 추출
            case_info = {
                'source': doc['metadata']['source'],
                'content': doc['content'][:500],  # 요약
                'score': doc.get('score', 0)
            }
            cases.append(case_info)

        # 응답 생성
        response = f"🔍 **유사 사례 {len(cases)}건 발견**\n\n"

        for i, case in enumerate(cases, 1):
            response += f"**[사례 {i}]** {case['source']}\n"
            response += f"{case['content']}...\n"
            response += f"유사도: {case['score']:.2f}\n\n"

        return response

    def _create_timeline(self, query: str, documents: List[Dict]) -> str:
        """시간순 정렬 및 표시"""
        timeline = defaultdict(list)

        for doc in documents:
            # 날짜 추출
            date = self._extract_date(doc['metadata']['source'])
            if date:
                year = date[:4]
                timeline[year].append({
                    'date': date,
                    'source': doc['metadata']['source'],
                    'summary': doc['content'][:200]
                })

        # 응답 생성
        response = "📅 **시간순 정리**\n\n"

        for year in sorted(timeline.keys()):
            response += f"**{year}년**\n"
            for item in sorted(timeline[year], key=lambda x: x['date']):
                response += f"• {item['date']}: {item['source']}\n"
                response += f"  {item['summary']}...\n\n"

        return response

    def _compare_documents(self, query: str, documents: List[Dict]) -> str:
        """문서 비교"""
        comparison = []

        for doc in documents:
            # 주요 항목 추출
            comparison.append({
                'source': doc['metadata']['source'],
                'key_points': self._extract_key_points(doc['content'])
            })

        # LLM을 사용한 비교 분석
        prompt = f"""
        다음 문서들을 비교 분석해주세요:

        {json.dumps(comparison, ensure_ascii=False, indent=2)}

        질문: {query}

        주요 차이점과 공통점을 정리해주세요.
        """

        response = self.llm.generate_response(prompt)
        return response.answer if hasattr(response, 'answer') else str(response)

    def _generate_comprehensive_answer(self, query: str, documents: List[Dict]) -> str:
        """종합적인 답변 생성"""

        # 모든 문서 내용 통합
        combined_context = "\n\n---\n\n".join([
            f"[{doc['metadata']['source']}]\n{doc['content']}"
            for doc in documents
        ])

        # LLM 프롬프트
        prompt = f"""
        다음 {len(documents)}개 문서를 참고하여 질문에 답변해주세요.

        문서 내용:
        {combined_context[:10000]}  # 토큰 제한

        질문: {query}

        모든 관련 정보를 종합하여 상세히 답변해주세요.
        각 정보의 출처도 명시해주세요.
        """

        response = self.llm.generate_response(prompt)
        answer = response.answer if hasattr(response, 'answer') else str(response)

        # 출처 추가
        answer += "\n\n📚 **참고 문서:**\n"
        for doc in documents:
            answer += f"• {doc['metadata']['source']}\n"

        return answer

    def _extract_amounts(self, text: str) -> List[int]:
        """텍스트에서 금액 추출"""
        amounts = []

        # 금액 패턴 매칭
        patterns = [
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'(\d+)\s*억\s*(?:(\d+)\s*천)?(?:\s*만)?(?:\s*원)?',
            r'(\d+)\s*천\s*(?:만)?(?:\s*원)?',
            r'(\d+)\s*만\s*원'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        # 억 단위 처리
                        if '억' in pattern:
                            amount = int(match[0]) * 100000000
                            if len(match) > 1 and match[1]:
                                amount += int(match[1]) * 10000000
                        # 천만 단위 처리
                        elif '천' in pattern and '만' in pattern:
                            amount = int(match[0]) * 10000000
                        # 만 단위 처리
                        elif '만' in pattern:
                            amount = int(match[0]) * 10000
                        else:
                            amount = int(match[0].replace(',', ''))
                    else:
                        amount = int(match.replace(',', ''))

                    if amount > 0:
                        amounts.append(amount)
                except (ValueError, AttributeError):
                    continue

        return amounts

    def _extract_date(self, filename: str) -> Optional[str]:
        """파일명에서 날짜 추출"""
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if date_match:
            return date_match.group(0)

        year_match = re.search(r'(20\d{2})', filename)
        if year_match:
            return year_match.group(1)

        return None

    def _extract_key_points(self, text: str) -> List[str]:
        """핵심 포인트 추출"""
        points = []

        # 불릿 포인트 찾기
        bullet_patterns = [
            r'[•·▪▫◦‣⁃]\s*(.+)',
            r'\d+\.\s*(.+)',
            r'-\s*(.+)'
        ]

        for pattern in bullet_patterns:
            matches = re.findall(pattern, text)
            points.extend(matches[:5])  # 상위 5개만

        # 없으면 문장 단위로 추출
        if not points:
            sentences = text.split('.')[:5]
            points = [s.strip() for s in sentences if len(s.strip()) > 20]

        return points