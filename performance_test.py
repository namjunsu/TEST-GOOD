#!/usr/bin/env python3
"""
RAG 파이프라인 성능 분석 스크립트
각 단계별 병목 지점 식별
"""

import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def test_search_speed():
    """1단계: 검색 속도 테스트"""
    logger.info("🔍 1단계: 문서 검색 속도 테스트")

    try:
        from everything_like_search import FastDocumentRAG

        start_time = time.time()
        rag = FastDocumentRAG()
        init_time = time.time() - start_time
        logger.info(f"   초기화 시간: {init_time:.3f}초")

        # 검색 테스트
        test_queries = ["DVR", "카메라 구매", "중계차"]

        for query in test_queries:
            start = time.time()
            results = rag.find_documents(query)
            search_time = time.time() - start
            logger.info(f"   {query}: {search_time*1000:.1f}ms ({len(results)}개)")

    except Exception as e:
        logger.error(f"검색 테스트 실패: {e}")

def test_content_extraction():
    """2단계: PDF 내용 추출 속도 테스트"""
    logger.info("📄 2단계: PDF 내용 추출 속도 테스트")

    try:
        from everything_like_search import EverythingLikeSearch

        search = EverythingLikeSearch()

        # 첫 번째 PDF 파일 찾기
        results = search.search("DVR", limit=3)

        for result in results[:3]:
            start = time.time()
            content = search.get_document_content(result['path'])
            extract_time = time.time() - start

            if 'error' not in content:
                logger.info(f"   {result['filename']}: {extract_time:.3f}초 ({content['length']:,}자)")
            else:
                logger.info(f"   {result['filename']}: 추출 실패 - {content['error']}")

    except Exception as e:
        logger.error(f"내용 추출 테스트 실패: {e}")

def test_llm_response():
    """3단계: LLM 응답 속도 테스트"""
    logger.info("🤖 3단계: LLM 응답 속도 테스트")

    try:
        from perfect_rag import PerfectRAG

        start_time = time.time()
        rag = PerfectRAG()
        init_time = time.time() - start_time
        logger.info(f"   PerfectRAG 초기화: {init_time:.3f}초")

        # 간단한 질문 테스트
        test_questions = [
            "DVR 관련 문서가 몇 개야?",
            "카메라 구매 문서 있어?"
        ]

        for question in test_questions:
            start = time.time()

            # 검색만 테스트 (LLM 호출 전)
            search_start = time.time()
            # rag 객체에서 검색 메서드가 있는지 확인 필요
            if hasattr(rag, 'search'):
                search_results = rag.search(question)
                search_time = time.time() - search_start
                logger.info(f"   검색 단계 ({question}): {search_time:.3f}초")

            # 전체 응답 테스트
            response = rag.answer(question)
            total_time = time.time() - start

            response_preview = response[:100] if response else "빈 응답"
            logger.info(f"   전체 응답 ({question}): {total_time:.3f}초")
            logger.info(f"   응답 미리보기: {response_preview}...")

    except Exception as e:
        logger.error(f"LLM 테스트 실패: {e}")

def main():
    """성능 분석 실행"""
    logger.info("🚀 RAG 파이프라인 성능 분석 시작")
    logger.info("=" * 60)

    # 각 단계별 테스트
    test_search_speed()
    print()
    test_content_extraction()
    print()
    test_llm_response()

    logger.info("=" * 60)
    logger.info("✅ 성능 분석 완료")

if __name__ == "__main__":
    main()