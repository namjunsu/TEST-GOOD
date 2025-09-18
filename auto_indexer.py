"""
자동 문서 인덱싱 시스템
새로운 PDF/TXT 파일이 docs 폴더에 추가되면 자동으로 인덱싱
"""

import time
import hashlib
from pathlib import Path
from datetime import datetime
import json
import threading
from typing import Dict, Set

class AutoIndexer:
    """자동 인덱싱 클래스"""
    
    def __init__(self, docs_dir: str = "docs", check_interval: int = 30):
        """
        Args:
            docs_dir: 문서 디렉토리 경로
            check_interval: 체크 간격 (초)
        """
        self.docs_dir = Path(docs_dir)
        self.check_interval = check_interval
        self.index_file = Path("rag_system/file_index.json")
        self.index_file.parent.mkdir(exist_ok=True)
        
        # 파일 인덱스 로드
        self.file_index = self._load_index()
        self.is_running = False
        self.thread = None
        
    def _load_index(self) -> Dict:
        """기존 인덱스 로드"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'files': {},
            'last_update': None
        }
    
    def _save_index(self):
        """인덱스 저장"""
        self.file_index['last_update'] = datetime.now().isoformat()
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.file_index, f, indent=2, ensure_ascii=False)
    
    def _get_file_hash(self, file_path: Path) -> str:
        """파일 해시 계산"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _rename_file_with_underscore(self, file_path: Path) -> Path:
        """파일명의 공백을 언더스코어로 변경"""
        if ' ' in file_path.name:
            new_name = file_path.name.replace(' ', '_')
            new_path = file_path.parent / new_name

            # 중복 파일명 체크
            if new_path.exists():
                # 중복되면 번호 추가
                base_name = new_path.stem
                extension = new_path.suffix
                counter = 1
                while new_path.exists():
                    new_path = file_path.parent / f"{base_name}_{counter}{extension}"
                    counter += 1

            try:
                file_path.rename(new_path)
                print(f"📝 파일명 변경: {file_path.name} → {new_path.name}")
                return new_path
            except Exception as e:
                print(f"⚠️ 파일명 변경 실패: {file_path.name} - {e}")
                return file_path
        return file_path

    def check_new_files(self) -> Dict:
        """새 파일 체크"""
        new_files = []
        modified_files = []
        deleted_files = []

        # 현재 파일 목록 (새로운 폴더 구조 포함)
        current_files = {}
        search_paths = [self.docs_dir]

        # 연도별 폴더 추가
        for year in range(2014, 2026):
            year_folder = self.docs_dir / f"year_{year}"
            if year_folder.exists():
                search_paths.append(year_folder)

        # 카테고리별 폴더 추가
        for folder in ['category_purchase', 'category_repair', 'category_review',
                      'category_disposal', 'category_consumables']:
            cat_folder = self.docs_dir / folder
            if cat_folder.exists():
                search_paths.append(cat_folder)

        # 특별 폴더 추가
        for folder in ['recent', 'archive', 'assets']:
            special_folder = self.docs_dir / folder
            if special_folder.exists():
                search_paths.append(special_folder)

        # 모든 경로에서 파일 검색
        for path in search_paths:
            for ext in ['*.pdf', '*.txt']:
                for file_path in path.glob(ext):
                    # 파일명에 공백이 있으면 언더스코어로 변경
                    file_path = self._rename_file_with_underscore(file_path)

                    abs_path = file_path.resolve()
                    if str(abs_path) not in current_files:
                        file_hash = self._get_file_hash(file_path)
                        current_files[str(abs_path)] = {
                            'hash': file_hash,
                            'size': file_path.stat().st_size,
                            'modified': file_path.stat().st_mtime,
                            'added': datetime.now().isoformat()
                        }
        
        # 새 파일 감지
        for file_path, info in current_files.items():
            if file_path not in self.file_index['files']:
                new_files.append(file_path)
                print(f"🆕 새 파일 발견: {Path(file_path).name}")
            elif self.file_index['files'][file_path]['hash'] != info['hash']:
                modified_files.append(file_path)
                print(f"📝 파일 수정됨: {Path(file_path).name}")
        
        # 삭제된 파일 감지
        for file_path in self.file_index['files']:
            if file_path not in current_files:
                deleted_files.append(file_path)
                print(f"🗑️ 파일 삭제됨: {Path(file_path).name}")
        
        # 인덱스 업데이트
        if new_files or modified_files or deleted_files:
            self.file_index['files'] = current_files
            self._save_index()
            
            # 인덱싱 트리거
            if new_files or modified_files:
                self._trigger_indexing(new_files + modified_files)
        
        return {
            'new': new_files,
            'modified': modified_files,
            'deleted': deleted_files,
            'total': len(current_files)
        }
    
    def _trigger_indexing(self, files: list):
        """인덱싱 트리거"""
        print(f"\n🔄 인덱싱 시작: {len(files)}개 파일")
        
        # 여기에 실제 인덱싱 로직 호출
        # perfect_rag의 인덱싱 메서드 호출
        try:
            # Streamlit 세션에서 기존 RAG 인스턴스 가져오기
            try:
                import streamlit as st
                if 'rag' in st.session_state:
                    # 기존 인스턴스의 캐시만 업데이트
                    print("♻️ 기존 RAG 인스턴스 캐시 업데이트")
                    rag = st.session_state.rag
                    # 파일 목록 갱신 (새로운 폴더 구조 포함)
                    rag.pdf_files = []
                    rag.txt_files = []

                    # 루트 폴더
                    rag.pdf_files.extend(list(rag.docs_dir.glob('*.pdf')))
                    rag.txt_files.extend(list(rag.docs_dir.glob('*.txt')))

                    # 연도별 폴더
                    for year in range(2014, 2026):
                        year_folder = rag.docs_dir / f"year_{year}"
                        if year_folder.exists():
                            rag.pdf_files.extend(list(year_folder.glob('*.pdf')))
                            rag.txt_files.extend(list(year_folder.glob('*.txt')))

                    # 카테고리별 폴더
                    for folder in ['category_purchase', 'category_repair', 'category_review',
                                 'category_disposal', 'category_consumables']:
                        cat_folder = rag.docs_dir / folder
                        if cat_folder.exists():
                            rag.pdf_files.extend(list(cat_folder.glob('*.pdf')))
                            rag.txt_files.extend(list(cat_folder.glob('*.txt')))

                    # 특별 폴더
                    for folder in ['recent', 'archive', 'assets']:
                        special_folder = rag.docs_dir / folder
                        if special_folder.exists():
                            rag.pdf_files.extend(list(special_folder.glob('*.pdf')))
                            rag.txt_files.extend(list(special_folder.glob('*.txt')))

                    # 중복 제거
                    rag.pdf_files = list(set(rag.pdf_files))
                    rag.txt_files = list(set(rag.txt_files))
                    rag.all_files = rag.pdf_files + rag.txt_files

                    # 메타데이터 캐시만 재구축
                    rag._build_metadata_cache()
                else:
                    # 세션에 없으면 새로 생성
                    from perfect_rag import PerfectRAG
                    print("🆕 새 RAG 인스턴스 생성")
                    rag = PerfectRAG()
                    st.session_state.rag = rag
            except ImportError:
                # Streamlit 환경이 아닌 경우 (CLI 실행)
                from perfect_rag import PerfectRAG
                print("🆕 새 RAG 인스턴스 생성 (CLI 모드)")
                rag = PerfectRAG()
            
            print(f"✅ 인덱싱 완료!")
            
            # 통계 출력
            stats = self.get_statistics()
            print(f"📊 전체 파일: PDF {stats['pdf_count']}개, TXT {stats['txt_count']}개")
            
        except Exception as e:
            print(f"❌ 인덱싱 실패: {e}")
    
    def get_statistics(self) -> Dict:
        """통계 정보"""
        pdf_count = len([f for f in self.file_index['files'] if f.endswith('.pdf')])
        txt_count = len([f for f in self.file_index['files'] if f.endswith('.txt')])
        
        return {
            'total_files': len(self.file_index['files']),
            'pdf_count': pdf_count,
            'txt_count': txt_count,
            'last_update': self.file_index.get('last_update', 'Never')
        }
    
    def start_monitoring(self):
        """모니터링 시작"""
        if self.is_running:
            print("⚠️ 이미 모니터링 중입니다.")
            return
        
        self.is_running = True
        print(f"🚀 자동 인덱싱 시작 (체크 간격: {self.check_interval}초)")
        
        def run():
            while self.is_running:
                try:
                    result = self.check_new_files()
                    if result['new'] or result['modified']:
                        print(f"📁 변경 감지: 새 파일 {len(result['new'])}개, 수정 {len(result['modified'])}개")
                except Exception as e:
                    print(f"❌ 체크 중 오류: {e}")
                
                time.sleep(self.check_interval)
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("⏹️ 자동 인덱싱 중지")
    
    def force_reindex(self):
        """강제 재인덱싱"""
        print("🔄 강제 재인덱싱 시작...")
        self.file_index = {'files': {}, 'last_update': None}
        result = self.check_new_files()
        print(f"✅ 재인덱싱 완료: {result['total']}개 파일")
        return result


# 독립 실행용
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="자동 문서 인덱싱 시스템")
    parser.add_argument('--interval', type=int, default=30, help='체크 간격 (초)')
    parser.add_argument('--force', action='store_true', help='강제 재인덱싱')
    parser.add_argument('--stats', action='store_true', help='통계 출력')
    
    args = parser.parse_args()
    
    indexer = AutoIndexer(check_interval=args.interval)
    
    if args.stats:
        stats = indexer.get_statistics()
        print("📊 인덱스 통계:")
        print(f"  - 전체 파일: {stats['total_files']}개")
        print(f"  - PDF: {stats['pdf_count']}개")
        print(f"  - TXT: {stats['txt_count']}개")
        print(f"  - 마지막 업데이트: {stats['last_update']}")
    elif args.force:
        indexer.force_reindex()
    else:
        try:
            indexer.start_monitoring()
            print("📌 자동 인덱싱 실행 중... (Ctrl+C로 종료)")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️ 종료 중...")
            indexer.stop_monitoring()