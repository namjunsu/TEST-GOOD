#!/usr/bin/env python3
"""
초고속 초기화 스크립트
OCR 완전 생략, 메타데이터만 추출
"""

import time
import logging
from pathlib import Path
import pickle
import json
from concurrent.futures import ThreadPoolExecutor
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def extract_fast_metadata(pdf_path):
    """빠른 메타데이터 추출 (OCR 없이)"""
    try:
        filename = pdf_path.name

        # 날짜 패턴 추출
        date_pattern = r'(\d{4})[_-](\d{2})[_-](\d{2})'
        date_match = re.search(date_pattern, filename)
        date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else "unknown"

        # 카테고리 추출
        if any(k in filename.lower() for k in ['구매', 'buy', 'purchase']):
            category = "구매"
        elif any(k in filename.lower() for k in ['수리', 'repair', 'fix']):
            category = "수리"
        elif any(k in filename.lower() for k in ['보고', 'report']):
            category = "보고서"
        elif any(k in filename.lower() for k in ['검토', 'review']):
            category = "검토"
        else:
            category = "기타"

        # 제목 추출 (파일명에서)
        title = filename.replace('.pdf', '').replace('_', ' ')

        return {
            'filename': filename,
            'path': str(pdf_path),
            'date': date,
            'category': category,
            'title': title,
            'content': '',  # OCR 없이 빈 내용
            'size': pdf_path.stat().st_size
        }
    except Exception as e:
        logger.error(f"Error processing {pdf_path.name}: {e}")
        return None

def build_fast_cache():
    """초고속 캐시 구축"""
    logger.info("⚡ 초고속 캐시 구축 시작")
    logger.info("=" * 60)

    start_time = time.time()

    # PDF 파일 찾기
    pdf_dir = Path("docs")
    pdf_files = list(pdf_dir.glob("**/*.pdf"))
    logger.info(f"📄 {len(pdf_files)}개 PDF 발견")

    # 캐시 디렉토리 생성
    cache_dir = Path("config/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 병렬 처리로 메타데이터 추출
    logger.info("🚀 병렬 메타데이터 추출 중...")
    metadata_cache = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for pdf_file in pdf_files:
            future = executor.submit(extract_fast_metadata, pdf_file)
            futures.append((pdf_file.name, future))

        completed = 0
        for filename, future in futures:
            result = future.result()
            if result:
                metadata_cache[filename] = result
                completed += 1
                if completed % 50 == 0:
                    logger.info(f"  처리: {completed}/{len(pdf_files)}")

    # 캐시 저장
    cache_file = cache_dir / "metadata_cache.pkl"
    with open(cache_file, 'wb') as f:
        pickle.dump(metadata_cache, f)

    # JSON 버전도 저장 (디버깅용)
    json_file = cache_dir / "metadata_cache.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(metadata_cache, f, ensure_ascii=False, indent=2, default=str)

    elapsed = time.time() - start_time

    # 결과 출력
    logger.info("=" * 60)
    logger.info(f"✅ 캐시 구축 완료!")
    logger.info(f"  • 처리 시간: {elapsed:.1f}초")
    logger.info(f"  • 처리된 문서: {len(metadata_cache)}개")
    logger.info(f"  • 캐시 파일: {cache_file}")
    logger.info(f"  • 캐시 크기: {cache_file.stat().st_size / 1024 / 1024:.1f} MB")
    logger.info("=" * 60)

    return True

if __name__ == "__main__":
    build_fast_cache()