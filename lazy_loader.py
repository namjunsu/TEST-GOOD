#!/usr/bin/env python3
"""
Lazy Loading System - 지연 로딩으로 초기 속도 개선
필요한 문서만 그때그때 로드
"""
from pathlib import Path
from typing import Dict, List, Optional
import json
import time

class LazyDocumentLoader:
    """지연 문서 로더"""

    def __init__(self, docs_dir: Path):
        self.docs_dir = docs_dir
        self.file_list = []  # 파일 목록만 저장
        self.loaded_docs = {}  # 실제 로드된 문서
        self.metadata_index = {}  # 간단한 메타데이터만

    def quick_scan(self) -> int:
        """빠른 파일 스캔 (내용 로드 없이)"""
        start_time = time.time()

        # 모든 폴더 스캔 (내용은 읽지 않음)
        search_paths = [self.docs_dir]

        # 연도별 폴더
        for year in range(2014, 2026):
            year_folder = self.docs_dir / f"year_{year}"
            if year_folder.exists():
                search_paths.append(year_folder)

        # 카테고리 폴더
        for folder in ['category_purchase', 'category_repair', 'category_review',
                      'category_disposal', 'category_consumables', 'recent', 'archive', 'assets']:
            cat_folder = self.docs_dir / folder
            if cat_folder.exists():
                search_paths.append(cat_folder)

        # 파일 목록만 수집 (내용 로드 X)
        for path in search_paths:
            for ext in ['*.pdf', '*.txt']:
                for file_path in path.glob(ext):
                    self.file_list.append({
                        'path': str(file_path),
                        'name': file_path.name,
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })

        elapsed = time.time() - start_time
        print(f"⚡ {len(self.file_list)}개 파일 스캔 완료 ({elapsed:.2f}초)")
        return len(self.file_list)

    def load_document(self, filename: str) -> Optional[Dict]:
        """필요할 때만 문서 로드"""
        if filename in self.loaded_docs:
            return self.loaded_docs[filename]

        # 처음 요청된 문서만 로드
        for file_info in self.file_list:
            if file_info['name'] == filename:
                # 실제 로드 (여기서만 시간 소요)
                doc_data = self._load_single_document(Path(file_info['path']))
                self.loaded_docs[filename] = doc_data
                return doc_data

        return None

    def _load_single_document(self, file_path: Path) -> Dict:
        """단일 문서 로드"""
        # 여기서 실제 PDF/TXT 처리
        # 필요할 때만 실행됨
        return {
            'path': str(file_path),
            'loaded_at': time.time(),
            # 실제 텍스트 추출은 여기서
        }

    def get_file_list(self) -> List[str]:
        """파일명 목록만 빠르게 반환"""
        return [f['name'] for f in self.file_list]

if __name__ == "__main__":
    # 테스트
    loader = LazyDocumentLoader(Path("docs"))

    print("🚀 빠른 시작 테스트")
    start = time.time()
    count = loader.quick_scan()
    print(f"✅ 초기 스캔: {time.time() - start:.2f}초")

    print(f"\n📋 파일 목록 (처음 10개):")
    for name in loader.get_file_list()[:10]:
        print(f"   - {name}")