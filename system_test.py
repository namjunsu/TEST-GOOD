#!/usr/bin/env python3
"""
AI-CHAT 시스템 종합 테스트
2025-09-30
"""

import time
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_system():
    """시스템 전체 테스트"""
    results = []

    logger.info("="*60)
    logger.info("🔬 AI-CHAT 시스템 종합 테스트 시작")
    logger.info("="*60)

    # 1. 모듈 임포트 테스트
    logger.info("\n📦 1. 모듈 임포트 테스트")
    logger.info("-"*40)

    modules_to_test = [
        ('perfect_rag', 'PerfectRAG', '메인 시스템'),
        ('search_module', 'SearchModule', '검색 모듈'),
        ('document_module', 'DocumentModule', '문서 처리'),
        ('llm_module', 'LLMModule', 'LLM 핸들러'),
        ('cache_module', 'CacheModule', '캐시 관리'),
        ('statistics_module', 'StatisticsModule', '통계'),
        ('intent_module', 'IntentModule', '의도 분석'),
        ('metadata_extractor', 'MetadataExtractor', '메타데이터'),
        ('metadata_db', 'MetadataDB', '메타데이터 DB'),
        ('everything_like_search', 'EverythingLikeSearch', '파일 검색'),
    ]

    import_success = 0
    for module_name, class_name, desc in modules_to_test:
        try:
            module = __import__(module_name)
            if hasattr(module, class_name):
                logger.info(f"✅ {desc:15} ({module_name})")
                import_success += 1
                results.append(f"{module_name}: OK")
            else:
                logger.warning(f"⚠️ {desc:15} - 클래스 없음")
                results.append(f"{module_name}: NO CLASS")
        except ImportError as e:
            logger.error(f"❌ {desc:15} - 임포트 실패: {e}")
            results.append(f"{module_name}: FAILED")

    logger.info(f"\n결과: {import_success}/{len(modules_to_test)} 성공")

    # 2. PerfectRAG 초기화 테스트
    logger.info("\n🚀 2. PerfectRAG 초기화 테스트")
    logger.info("-"*40)

    try:
        from perfect_rag import PerfectRAG
        start_time = time.time()
        rag = PerfectRAG()
        init_time = time.time() - start_time
        logger.info(f"✅ 초기화 성공 (소요시간: {init_time:.2f}초)")

        # 모듈 확인
        modules_loaded = []
        if hasattr(rag, 'search_module') and rag.search_module:
            modules_loaded.append('Search')
        if hasattr(rag, 'document_module') and rag.document_module:
            modules_loaded.append('Document')
        if hasattr(rag, 'llm_module') and rag.llm_module:
            modules_loaded.append('LLM')
        if hasattr(rag, 'cache_module') and rag.cache_module:
            modules_loaded.append('Cache')
        if hasattr(rag, 'statistics_module') and rag.statistics_module:
            modules_loaded.append('Statistics')
        if hasattr(rag, 'intent_module') and rag.intent_module:
            modules_loaded.append('Intent')

        logger.info(f"✅ 로드된 모듈: {', '.join(modules_loaded)} ({len(modules_loaded)}/6)")

    except Exception as e:
        logger.error(f"❌ 초기화 실패: {e}")
        return False

    # 3. 문서 확인
    logger.info("\n📄 3. 문서 확인")
    logger.info("-"*40)

    docs_dir = Path('docs')
    if docs_dir.exists():
        pdf_files = list(docs_dir.glob('**/*.pdf'))
        txt_files = list(docs_dir.glob('**/*.txt'))
        logger.info(f"✅ PDF 파일: {len(pdf_files)}개")
        logger.info(f"✅ TXT 파일: {len(txt_files)}개")
    else:
        logger.error("❌ docs 디렉토리 없음")

    # 4. 기본 기능 테스트
    logger.info("\n⚡ 4. 기본 기능 테스트")
    logger.info("-"*40)

    test_queries = [
        ("간단한 테스트", "basic"),
        ("문서 찾아줘", "search"),
        ("2024년 구매 내역", "filter"),
        ("통계 보여줘", "stats"),
    ]

    for query, query_type in test_queries:
        try:
            logger.info(f"\n테스트: '{query}' ({query_type})")
            start_time = time.time()
            response = rag.answer(query)
            response_time = time.time() - start_time

            if response:
                logger.info(f"✅ 응답 성공 ({response_time:.2f}초)")
                logger.info(f"   응답 길이: {len(response)}자")
                results.append(f"{query_type}: {response_time:.2f}s")
            else:
                logger.warning(f"⚠️ 빈 응답")
                results.append(f"{query_type}: EMPTY")

        except Exception as e:
            logger.error(f"❌ 오류: {e}")
            results.append(f"{query_type}: ERROR")

    # 5. 캐시 테스트
    logger.info("\n💾 5. 캐시 시스템 테스트")
    logger.info("-"*40)

    if hasattr(rag, 'cache_module') and rag.cache_module:
        try:
            stats = rag.cache_module.get_cache_stats()
            logger.info(f"✅ 캐시 크기: {stats.get('total_size', 0)}개")
            logger.info(f"✅ 문서 캐시: {stats.get('documents', 0)}개")
            logger.info(f"✅ 응답 캐시: {stats.get('responses', 0)}개")
        except Exception as e:
            logger.warning(f"⚠️ 캐시 통계 실패: {e}")

    # 6. 메모리 사용량
    logger.info("\n💻 6. 시스템 리소스")
    logger.info("-"*40)

    import psutil
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    logger.info(f"✅ 메모리 사용량: {memory_mb:.1f} MB")

    # 최종 결과
    logger.info("\n" + "="*60)
    logger.info("📊 테스트 결과 요약")
    logger.info("="*60)

    for result in results:
        logger.info(f"  • {result}")

    logger.info("\n✨ 테스트 완료!")
    return True

if __name__ == "__main__":
    success = test_system()
    sys.exit(0 if success else 1)