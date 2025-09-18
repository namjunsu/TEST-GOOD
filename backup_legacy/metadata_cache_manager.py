#!/usr/bin/env python3
"""
메타데이터 캐시 관리자
문서 메타데이터를 파일로 저장하여 재시작 시 빠른 로딩 지원
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Any

class MetadataCacheManager:
    def __init__(self, cache_dir: str = "rag_system/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "document_metadata.json"
        self.index_file = self.cache_dir / "document_index.json"

    def get_file_hash(self, file_path: Path) -> str:
        """파일의 해시값 계산 (변경 감지용)"""
        stat = file_path.stat()
        # 파일명, 크기, 수정시간을 조합
        unique_str = f"{file_path.name}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(unique_str.encode()).hexdigest()

    def load_cache(self) -> Dict[str, Any]:
        """캐시 파일 로드"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_cache(self, metadata: Dict[str, Any]):
        """캐시 파일 저장"""
        # Path 객체를 문자열로 변환
        serializable_metadata = {}
        for key, value in metadata.items():
            if isinstance(value, dict):
                serializable_value = {}
                for k, v in value.items():
                    if isinstance(v, Path):
                        serializable_value[k] = str(v)
                    else:
                        serializable_value[k] = v
                serializable_metadata[key] = serializable_value
            else:
                serializable_metadata[key] = value

        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_metadata, f, ensure_ascii=False, indent=2)

    def needs_update(self, file_path: Path, cached_metadata: Dict) -> bool:
        """파일이 업데이트되었는지 확인"""
        if not cached_metadata:
            return True

        current_hash = self.get_file_hash(file_path)
        cached_hash = cached_metadata.get('file_hash')

        return current_hash != cached_hash

    def update_file_metadata(self, file_path: Path, metadata: Dict):
        """단일 파일 메타데이터 업데이트"""
        metadata['file_hash'] = self.get_file_hash(file_path)
        metadata['last_indexed'] = time.time()
        return metadata

    def build_quick_index(self, docs_dir: Path) -> Dict:
        """빠른 인덱스 생성 (파일 목록만)"""
        index = {
            'pdf_files': [],
            'txt_files': [],
            'total_size': 0,
            'last_updated': time.time()
        }

        for pdf in docs_dir.glob('*.pdf'):
            index['pdf_files'].append({
                'name': pdf.name,
                'size': pdf.stat().st_size,
                'modified': pdf.stat().st_mtime
            })
            index['total_size'] += pdf.stat().st_size

        for txt in docs_dir.glob('*.txt'):
            index['txt_files'].append({
                'name': txt.name,
                'size': txt.stat().st_size,
                'modified': txt.stat().st_mtime
            })
            index['total_size'] += txt.stat().st_size

        # 인덱스 저장
        with open(self.index_file, 'w') as f:
            json.dump(index, f, indent=2)

        return index

if __name__ == "__main__":
    # 테스트
    manager = MetadataCacheManager()

    print("📊 캐시 매니저 테스트")
    print("="*50)

    # 빠른 인덱스 생성
    docs_dir = Path("docs")
    index = manager.build_quick_index(docs_dir)

    print(f"✅ PDF 파일: {len(index['pdf_files'])}개")
    print(f"✅ TXT 파일: {len(index['txt_files'])}개")
    print(f"✅ 전체 크기: {index['total_size'] / 1024 / 1024:.1f} MB")
    print(f"✅ 인덱스 파일: {manager.index_file}")