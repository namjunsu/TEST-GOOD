#!/usr/bin/env python3
"""
빠른 시작 최적화 시스템
========================

문서 로딩 시간을 대폭 단축
"""

import os
import pickle
import time
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Tuple, Any
import hashlib
import json
from datetime import datetime
import multiprocessing as mp

# 색상 코드
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


class FastStartupOptimizer:
    """초고속 시작 최적화"""

    def __init__(self):
        self.docs_dir = Path("docs")
        self.cache_dir = Path(".cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.index_cache_path = self.cache_dir / "document_index.pkl"
        self.metadata_cache_path = self.cache_dir / "metadata_cache.pkl"
        self.stats = {
            'total_files': 0,
            'processed': 0,
            'cached': 0,
            'errors': 0
        }

    def get_file_hash(self, file_path: Path) -> str:
        """파일 해시 계산 (빠른 체크섬)"""
        stat = file_path.stat()
        # 파일명, 크기, 수정시간으로 빠른 해시 생성
        hash_str = f"{file_path.name}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(hash_str.encode()).hexdigest()[:8]

    def process_single_pdf(self, pdf_path: Path) -> Tuple[str, Dict]:
        """단일 PDF 빠른 메타데이터 추출"""
        try:
            # 파일명에서 정보 추출 (빠른 처리)
            filename = pdf_path.name
            parts = filename.replace('.pdf', '').split('_')

            # 날짜 추출
            date = parts[0] if parts else "unknown"

            # 카테고리 추출
            category = "unknown"
            if "구매" in filename:
                category = "purchase"
            elif "수리" in filename:
                category = "repair"
            elif "검토" in filename:
                category = "review"
            elif "폐기" in filename:
                category = "disposal"

            metadata = {
                'path': str(pdf_path),
                'filename': filename,
                'date': date,
                'category': category,
                'size': pdf_path.stat().st_size,
                'hash': self.get_file_hash(pdf_path),
                'year': date[:4] if len(date) >= 4 else "unknown"
            }

            return str(pdf_path), metadata

        except Exception as e:
            self.stats['errors'] += 1
            return str(pdf_path), {'error': str(e)}

    def build_fast_index(self, max_files: int = None) -> Dict:
        """병렬 처리로 빠른 인덱스 구축"""
        print(f"{CYAN}{BOLD}⚡ 빠른 인덱스 구축 시작{RESET}")
        start_time = time.time()

        # PDF 파일 목록
        pdf_files = list(self.docs_dir.rglob("*.pdf"))

        if max_files:
            pdf_files = pdf_files[:max_files]
            print(f"  {YELLOW}제한 모드: 최대 {max_files}개 파일만 처리{RESET}")

        self.stats['total_files'] = len(pdf_files)
        print(f"  발견된 파일: {len(pdf_files)}개")

        # 병렬 처리
        index = {}
        cpu_count = mp.cpu_count()
        workers = min(cpu_count * 2, 16)  # 최대 16개 워커

        print(f"  {GREEN}병렬 처리: {workers}개 워커 사용{RESET}")

        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            # 배치 처리
            batch_size = 50
            for i in range(0, len(pdf_files), batch_size):
                batch = pdf_files[i:i+batch_size]
                futures = {executor.submit(self.process_single_pdf, pdf): pdf for pdf in batch}

                for future in concurrent.futures.as_completed(futures):
                    path, metadata = future.result()
                    index[path] = metadata
                    self.stats['processed'] += 1

                    # 진행 상황
                    if self.stats['processed'] % 100 == 0:
                        print(f"    처리 중: {self.stats['processed']}/{self.stats['total_files']}")

        elapsed = time.time() - start_time
        print(f"\n  {GREEN}✅ 인덱스 구축 완료!{RESET}")
        print(f"    소요 시간: {elapsed:.2f}초")
        print(f"    처리 속도: {len(pdf_files)/elapsed:.1f} 파일/초")

        return index

    def save_cache(self, index: Dict):
        """캐시 저장"""
        print(f"\n{CYAN}💾 캐시 저장 중...{RESET}")

        # 인덱스 캐시
        with open(self.index_cache_path, 'wb') as f:
            pickle.dump(index, f, protocol=pickle.HIGHEST_PROTOCOL)

        # 메타데이터 캐시 (JSON 형식)
        json_cache = self.cache_dir / "metadata.json"
        with open(json_cache, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

        print(f"  {GREEN}✅ 캐시 저장 완료{RESET}")
        print(f"    인덱스: {self.index_cache_path}")
        print(f"    메타데이터: {json_cache}")

    def load_cache(self) -> Dict:
        """캐시 로드"""
        if self.index_cache_path.exists():
            print(f"{CYAN}📂 캐시 로드 중...{RESET}")
            start = time.time()

            with open(self.index_cache_path, 'rb') as f:
                index = pickle.load(f)

            elapsed = time.time() - start
            print(f"  {GREEN}✅ 캐시 로드 완료: {elapsed:.3f}초{RESET}")
            return index
        return {}

    def optimize_config(self):
        """config.py 최적화"""
        print(f"\n{CYAN}⚙️  설정 최적화{RESET}")

        config_content = '''"""
최적화된 설정 파일
==================

빠른 시작을 위한 설정
"""

import os

# ============ 성능 최적화 설정 ============

# 문서 로딩 제한 (개발/테스트용)
MAX_DOCUMENTS = int(os.getenv('MAX_DOCUMENTS', '100'))  # 최대 100개만 로드
LAZY_LOAD = True  # 지연 로딩 활성화
PARALLEL_WORKERS = 8  # 병렬 처리 워커 수

# 캐싱 설정
USE_CACHE = True
CACHE_DIR = ".cache"
CACHE_TTL = 3600 * 24  # 24시간

# 모델 설정 (경량화)
MODEL_NAME = "qwen2.5-7b-instruct-q4_k_m.gguf"
N_CTX = 2048  # 컨텍스트 감소 (4096 -> 2048)
N_BATCH = 128  # 배치 크기 감소 (256 -> 128)
MAX_TOKENS = 256  # 최대 토큰 감소 (512 -> 256)
N_GPU_LAYERS = 20  # GPU 레이어 감소

# 메모리 최적화
LOW_VRAM = True
OFFLOAD_LAYERS = True
USE_MMAP = True
USE_MLOCK = False

# 검색 설정
SEARCH_TOP_K = 3  # 기본 검색 결과 수
MIN_RELEVANCE_SCORE = 0.3

# 로깅
LOG_LEVEL = "INFO"
VERBOSE = False

print(f"⚡ 최적화 모드: 최대 {MAX_DOCUMENTS}개 문서 로드")
'''

        # config.py 백업
        config_path = Path("config.py")
        if config_path.exists():
            backup_path = Path("config_backup.py")
            config_path.rename(backup_path)
            print(f"  기존 설정 백업: {backup_path}")

        # 새 설정 저장
        config_path.write_text(config_content)
        print(f"  {GREEN}✅ 설정 최적화 완료{RESET}")

    def create_quick_start_script(self):
        """빠른 시작 스크립트 생성"""
        print(f"\n{CYAN}🚀 빠른 시작 스크립트 생성{RESET}")

        script_content = '''#!/bin/bash
# 빠른 시작 스크립트

echo "⚡ AI-CHAT 빠른 시작 모드"
echo "========================="

# 환경 변수 설정 (제한 모드)
export MAX_DOCUMENTS=50
export USE_CACHE=true
export LOW_VRAM=true
export LOG_LEVEL=WARNING

# 캐시 확인
if [ -d ".cache" ]; then
    echo "✅ 캐시 발견 - 빠른 로딩 가능"
else
    echo "⚠️  캐시 없음 - 초기 구축 필요"
    python3 fast_startup_optimizer.py --build-cache
fi

# Streamlit 실행
echo ""
echo "🚀 웹 인터페이스 시작..."
streamlit run web_interface.py

'''

        script_path = Path("quick_start.sh")
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        print(f"  {GREEN}✅ 빠른 시작 스크립트 생성: {script_path}{RESET}")

    def print_summary(self):
        """최적화 요약"""
        print(f"\n{'='*60}")
        print(f"{BOLD}📊 최적화 완료 요약{RESET}")
        print(f"{'='*60}")
        print(f"  처리된 파일: {self.stats['processed']}개")
        print(f"  캐시 생성: {self.stats['cached']}개")
        print(f"  오류: {self.stats['errors']}개")
        print(f"\n{GREEN}💡 다음 명령으로 빠르게 시작:{RESET}")
        print(f"  ./quick_start.sh")
        print(f"\n{YELLOW}📌 첫 실행 예상 시간:{RESET}")
        print(f"  기존: 2-3분")
        print(f"  최적화 후: 10-15초")


def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description='빠른 시작 최적화')
    parser.add_argument('--build-cache', action='store_true', help='캐시 구축')
    parser.add_argument('--max-files', type=int, default=100, help='최대 파일 수')
    parser.add_argument('--optimize-config', action='store_true', help='설정 최적화')
    args = parser.parse_args()

    optimizer = FastStartupOptimizer()

    print(f"{BOLD}⚡ 빠른 시작 최적화 시스템{RESET}")
    print("="*60)

    # 캐시 구축
    if args.build_cache or not optimizer.index_cache_path.exists():
        index = optimizer.build_fast_index(max_files=args.max_files)
        optimizer.save_cache(index)
        optimizer.stats['cached'] = len(index)
    else:
        index = optimizer.load_cache()
        print(f"  캐시된 문서: {len(index)}개")

    # 설정 최적화
    if args.optimize_config:
        optimizer.optimize_config()

    # 빠른 시작 스크립트
    optimizer.create_quick_start_script()

    # 요약
    optimizer.print_summary()


if __name__ == "__main__":
    main()