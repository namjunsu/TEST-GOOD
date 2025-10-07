#!/usr/bin/env python3
"""
캐시 사전 구축 스크립트
목적: 812개 PDF 메타데이터를 미리 처리하여 시작 시간 단축
"""

import time
import logging
from pathlib import Path
import pickle
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def build_cache():
    """캐시 파일 사전 구축"""
    logger.info("🚀 캐시 구축 시작")
    logger.info("=" * 60)

    # 캐시 디렉토리 확인
    cache_dir = Path("config/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_file = cache_dir / "metadata_cache.pkl"

    # 이미 캐시가 있는지 확인
    if cache_file.exists():
        size_mb = cache_file.stat().st_size / 1024 / 1024
        logger.info(f"⚠️  기존 캐시 파일 발견: {size_mb:.1f} MB")
        response = input("덮어쓰시겠습니까? (y/n): ")
        if response.lower() != 'y':
            logger.info("취소됨")
            return

    try:
        # PerfectRAG 초기화 (캐시 구축)
        logger.info("📦 시스템 초기화 중...")
        start_time = time.time()

        # 로그 레벨 조정하여 불필요한 출력 줄이기
        import warnings
        warnings.filterwarnings('ignore')

        # 병렬 처리 활성화 설정
        import os
        os.environ['USE_PARALLEL'] = 'true'
        os.environ['PARALLEL_WORKERS'] = '4'

        from perfect_rag import PerfectRAG
        logger.info("📄 PDF 문서 처리 중... (시간이 걸립니다)")

        # 진행 표시를 위한 간단한 스피너
        import threading
        stop_spinner = False

        def spinner():
            chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            i = 0
            while not stop_spinner:
                sys.stdout.write(f'\r처리 중... {chars[i % len(chars)]}')
                sys.stdout.flush()
                time.sleep(0.1)
                i += 1
            sys.stdout.write('\r' + ' ' * 20 + '\r')
            sys.stdout.flush()

        spinner_thread = threading.Thread(target=spinner)
        spinner_thread.start()

        try:
            rag = PerfectRAG()
            stop_spinner = True
            spinner_thread.join()

            elapsed = time.time() - start_time
            logger.info(f"✅ 초기화 완료 ({elapsed:.1f}초)")

            # 캐시 정보 확인
            if cache_file.exists():
                size_mb = cache_file.stat().st_size / 1024 / 1024
                logger.info(f"✅ 캐시 파일 생성: {size_mb:.1f} MB")

                # 캐시 내용 확인
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    logger.info(f"✅ 캐시된 문서: {len(cache_data)}개")

            # 테스트 쿼리
            logger.info("\n📝 테스트 쿼리 실행...")
            test_start = time.time()
            response = rag.answer("시스템 테스트")
            test_time = time.time() - test_start

            if response:
                logger.info(f"✅ 응답 성공 ({test_time:.2f}초)")
            else:
                logger.warning("⚠️  빈 응답")

        except Exception as e:
            stop_spinner = True
            spinner_thread.join()
            raise e

    except Exception as e:
        logger.error(f"❌ 캐시 구축 실패: {e}")
        return False

    logger.info("\n" + "=" * 60)
    logger.info("✨ 캐시 구축 완료!")
    logger.info("이제 시스템이 훨씬 빠르게 시작됩니다.")
    logger.info("=" * 60)

    return True

def check_cache_status():
    """캐시 상태 확인"""
    cache_file = Path("config/cache/metadata_cache.pkl")

    if cache_file.exists():
        size_mb = cache_file.stat().st_size / 1024 / 1024
        modified = cache_file.stat().st_mtime
        from datetime import datetime
        mod_time = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')

        logger.info("📊 캐시 상태:")
        logger.info(f"  • 파일 크기: {size_mb:.1f} MB")
        logger.info(f"  • 수정 시간: {mod_time}")

        # 캐시 내용 확인
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                logger.info(f"  • 캐시된 문서: {len(cache_data)}개")
        except:
            logger.warning("  • 캐시 파일 읽기 실패")
    else:
        logger.info("❌ 캐시 파일 없음")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='캐시 관리 도구')
    parser.add_argument('--check', action='store_true', help='캐시 상태 확인')
    parser.add_argument('--build', action='store_true', help='캐시 구축')

    args = parser.parse_args()

    if args.check:
        check_cache_status()
    else:
        build_cache()