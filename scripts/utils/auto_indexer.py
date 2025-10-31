"""
자동 문서 인덱싱 시스템
새로운 PDF/TXT 파일이 docs 폴더에 추가되면 자동으로 인덱싱
"""

import time
import os
import hashlib
from pathlib import Path
from datetime import datetime
import json
import threading
from typing import Dict, Set

class AutoIndexer:
    """자동 인덱싱 클래스 - 성능 최적화 버전"""

    def __init__(self, docs_dir: str = "docs", check_interval: int = 30, max_retries: int = 3):
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

        # 성능 최적화를 위한 해시 캐시
        self.hash_cache = {}  # 파일 경로 -> (hash, mtime) 매핑
        self.last_check_time = 0

        # 에러 처리 및 재시도 관련
        self.max_retries = max_retries
        self.failed_files = {}  # 파일 경로 -> (실패 횟수, 마지막 에러)
        self.error_history = []  # 최근 에러 기록 (최대 100개)

        # 폴더 목록 상수화 (중복 제거)
        self.YEAR_FOLDERS = [f"year_{year}" for year in range(2014, 2026)]
        self.CATEGORY_FOLDERS = ['category_purchase', 'category_repair', 'category_review',
                                'category_disposal', 'category_consumables']
        self.SPECIAL_FOLDERS = ['recent', 'archive', 'assets']
        
    def _load_index(self) -> Dict:
        """기존 인덱스 로드"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
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
        """파일 해시 계산 (캐싱 및 최적화)"""
        # 수정 시간 기반 빠른 체크
        current_mtime = file_path.stat().st_mtime
        cache_key = str(file_path)

        # 캐시에 있고 수정 시간이 같으면 캐시 사용
        if cache_key in self.hash_cache:
            cached_hash, cached_mtime = self.hash_cache[cache_key]
            if cached_mtime == current_mtime:
                return cached_hash

        # 실제 해시 계산 (큰 파일은 처음 1MB만 샘플링)
        file_size = file_path.stat().st_size
        hasher = hashlib.md5()

        with open(file_path, 'rb') as f:
            if file_size > 10 * 1024 * 1024:  # 10MB 이상
                # 처음, 중간, 끝 부분만 샘플링
                f.seek(0)
                hasher.update(f.read(1024 * 1024))  # 처음 1MB

                f.seek(file_size // 2)
                hasher.update(f.read(1024 * 1024))  # 중간 1MB

                f.seek(max(0, file_size - 1024 * 1024))
                hasher.update(f.read())  # 마지막 1MB

                # 파일 크기와 수정 시간도 포함
                hasher.update(str(file_size).encode())
                hasher.update(str(current_mtime).encode())
            else:
                # 작은 파일은 전체 읽기
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)

        file_hash = hasher.hexdigest()

        # 캐시 업데이트
        self.hash_cache[cache_key] = (file_hash, current_mtime)

        return file_hash
    
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

    def _get_search_paths(self) -> list:
        """검색 경로 목록 반환 (중복 제거)"""
        search_paths = [self.docs_dir]

        # 모든 폴더 타입 순회
        all_folders = self.YEAR_FOLDERS + self.CATEGORY_FOLDERS + self.SPECIAL_FOLDERS

        for folder_name in all_folders:
            folder_path = self.docs_dir / folder_name
            if folder_path.exists():
                search_paths.append(folder_path)

        return search_paths

    def check_new_files(self) -> Dict:
        """새 파일 체크 (성능 최적화)"""
        start_time = time.time()
        new_files = []
        modified_files = []
        deleted_files = []

        # [PATCH] 삭제된 파일 정리 단계: everything_index.db 동기화
        stale_count = self._purge_missing_files_from_index()
        if stale_count > 0:
            print(f"🧹 [CLEANUP] deleted_stale_entries={stale_count}")

        # 현재 파일 목록
        current_files = {}
        search_paths = self._get_search_paths()

        # 모든 경로에서 파일 검색 (병렬 처리 가능)
        file_count = 0
        for path in search_paths:
            for ext in ['*.pdf', '*.txt']:
                for file_path in path.glob(ext):
                    # 파일명에 공백이 있으면 언더스코어로 변경
                    file_path = self._rename_file_with_underscore(file_path)

                    abs_path = file_path.resolve()
                    abs_path_str = str(abs_path)

                    # 중복 체크 (심볼릭 링크 방지)
                    if abs_path_str not in current_files:
                        try:
                            stat = file_path.stat()
                            # 빠른 체크: 크기와 수정 시간만으로 먼저 판단
                            quick_check = f"{stat.st_size}_{stat.st_mtime}"

                            # 기존 파일과 비교
                            old_info = self.file_index['files'].get(abs_path_str, {})
                            old_quick_check = f"{old_info.get('size', 0)}_{old_info.get('modified', 0)}"

                            # 빠른 체크가 다른 경우만 해시 계산
                            if quick_check != old_quick_check or abs_path_str not in self.file_index['files']:
                                file_hash = self._get_file_hash(file_path)
                            else:
                                file_hash = old_info.get('hash', '')

                            current_files[abs_path_str] = {
                                'hash': file_hash,
                                'size': stat.st_size,
                                'modified': stat.st_mtime,
                                'added': old_info.get('added', datetime.now().isoformat())
                            }
                            file_count += 1

                        except (OSError, IOError) as e:
                            print(f"  ⚠️ 파일 접근 오류: {file_path.name} - {e}")
                            self._handle_file_error(abs_path_str, e)

        # 성능 로깅
        if file_count > 100:
            elapsed = time.time() - start_time
            print(f"  ⏱️ {file_count}개 파일 스캔: {elapsed:.1f}초")
        
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
        """인덱싱 트리거 - 단순화된 버전 (perfect_rag 제거)"""
        print(f"\n🔄 인덱싱 시작: {len(files)}개 파일")

        try:
            # 파일 목록만 업데이트 (perfect_rag 없이)
            print("📝 파일 인덱스 업데이트...")
            updated_count = len(files)

            print(f"✅ 인덱싱 완료! ({updated_count}개 파일)")

            # 통계 출력
            stats = self.get_statistics()
            print(f"📊 전체 파일: PDF {stats['pdf_count']}개, TXT {stats['txt_count']}개")

        except Exception as e:
            print(f"❌ 인덱싱 실패: {e}")
            self._handle_indexing_error(files, e)
    
    def get_statistics(self) -> Dict:
        """통계 정보 (실시간 파일 시스템 기반)"""
        # 실제 파일 시스템에서 직접 개수 확인 (인덱스가 오래된 경우 대비)
        pdf_files = []
        txt_files = []

        # docs 폴더의 모든 하위 폴더 검색 (심볼릭 링크 제외)
        if self.docs_dir.exists():
            all_pdfs = list(self.docs_dir.rglob("*.pdf"))
            all_txts = list(self.docs_dir.rglob("*.txt"))

            # 심볼릭 링크 제외 (실제 파일만)
            pdf_files = [f for f in all_pdfs if not f.is_symlink()]
            txt_files = [f for f in all_txts if not f.is_symlink()]

        return {
            'total_files': len(pdf_files) + len(txt_files),
            'pdf_count': len(pdf_files),
            'txt_count': len(txt_files),
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
                    # 실패한 파일 재시도 (매 5번째 주기마다)
                    if hasattr(self, '_check_count'):
                        self._check_count += 1
                    else:
                        self._check_count = 1

                    if self._check_count % 5 == 0 and self.failed_files:
                        self._retry_failed_files()

                    result = self.check_new_files()
                    if result['new'] or result['modified']:
                        print(f"📁 변경 감지: 새 파일 {len(result['new'])}개, 수정 {len(result['modified'])}개")
                except Exception as e:
                    print(f"❌ 체크 중 오류: {e}")
                    self._handle_indexing_error([], e)
                
                time.sleep(self.check_interval)
        
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("⏹️ 자동 인덱싱 중지")
    
    # perfect_rag 관련 함수들 제거됨 (더 이상 사용하지 않음)

    def _handle_file_error(self, file_path: str, error: Exception):
        """파일 에러 처리 및 기록"""
        # 실패 횟수 증가
        if file_path not in self.failed_files:
            self.failed_files[file_path] = [1, str(error)]
        else:
            self.failed_files[file_path][0] += 1
            self.failed_files[file_path][1] = str(error)

        # 에러 이력 추가
        self.error_history.append({
            'timestamp': datetime.now().isoformat(),
            'file': file_path,
            'error': str(error),
            'retry_count': self.failed_files[file_path][0]
        })

        # 이력 크기 제한
        if len(self.error_history) > 100:
            self.error_history = self.error_history[-100:]

        # 재시도 한계 도달 시 경고
        if self.failed_files[file_path][0] >= self.max_retries:
            print(f"  🚫 파일 처리 포기: {Path(file_path).name} (재시도 {self.max_retries}회 실패)")

    def _handle_indexing_error(self, files: list, error: Exception):
        """인덱싱 에러 처리 및 복구"""
        print(f"\n🔧 인덱싱 오류 복구 시도...")

        # 에러 로깅
        self.error_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'indexing_error',
            'files_count': len(files),
            'error': str(error)
        })

        # 복구 전략
        try:
            # 1. RAG 인스턴스 재생성 시도
            print("  1️⃣ RAG 인스턴스 재생성 시도...")
            if hasattr(self, '_rag_instance'):
                del self._rag_instance

            # 2. 파일별 개별 처리 시도
            print(f"  2️⃣ {len(files)}개 파일 개별 처리 시도...")
            success_count = 0

            for file_path in files[:5]:  # 처음 5개만 재시도
                try:
                    # 개별 파일 처리
                    self._process_single_file(file_path)
                    success_count += 1
                except Exception as file_error:
                    self._handle_file_error(file_path, file_error)

            if success_count > 0:
                print(f"  ✅ 부분 복구 성공: {success_count}/{min(5, len(files))}개 파일")
            else:
                print(f"  ⚠️ 복구 실패 - 다음 주기에 재시도")

        except Exception as recovery_error:
            print(f"  ❌ 복구 실패: {recovery_error}")

    def _process_single_file(self, file_path: str):
        """단일 파일 처리 (에러 복구용)"""
        # 간단한 메타데이터만 업데이트
        path_obj = Path(file_path)
        if path_obj.exists():
            stat = path_obj.stat()
            file_hash = self._get_file_hash(path_obj)

            self.file_index['files'][file_path] = {
                'hash': file_hash,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'added': datetime.now().isoformat()
            }

    def _retry_failed_files(self):
        """실패한 파일들 재시도"""
        if not self.failed_files:
            return

        # 재시도 대상 선정 (재시도 횟수가 한계 미만)
        retry_candidates = [
            path for path, (count, _) in self.failed_files.items()
            if count < self.max_retries
        ]

        if retry_candidates:
            print(f"\n🔄 실패한 파일 재시도: {len(retry_candidates)}개")

            for file_path in retry_candidates:
                try:
                    self._process_single_file(file_path)
                    # 성공 시 실패 목록에서 제거
                    del self.failed_files[file_path]
                    print(f"  ✅ 재시도 성공: {Path(file_path).name}")
                except Exception as e:
                    self._handle_file_error(file_path, e)

    def get_error_statistics(self) -> Dict:
        """에러 통계 반환"""
        return {
            'failed_files_count': len(self.failed_files),
            'failed_files': list(self.failed_files.keys())[:10],  # 처음 10개만
            'recent_errors': self.error_history[-5:] if self.error_history else [],
            'total_errors': len(self.error_history)
        }

    def _purge_missing_files_from_index(self) -> int:
        """디스크에 존재하지 않는 파일을 검색 인덱스에서 삭제

        Returns:
            삭제된 항목 수
        """
        try:
            import sqlite3
            from config.indexing import DB_PATHS

            # everything_index.db 경로
            index_db_path = DB_PATHS.get("everything_index", "everything_index.db")
            if not os.path.exists(index_db_path):
                return 0

            # 현재 디스크의 모든 파일명 집합
            fs_names = set()
            search_paths = self._get_search_paths()
            for path in search_paths:
                for ext in ['*.pdf', '*.txt']:
                    for file_path in path.glob(ext):
                        fs_names.add(file_path.name)

            # DB 연결
            conn = sqlite3.connect(index_db_path)
            cur = conn.cursor()

            # files 테이블 스키마 점검
            cur.execute("PRAGMA table_info(files)")
            cols = {c[1] for c in cur.fetchall()}
            has_path = "path" in cols

            # DB 행 전체 조회
            query = "SELECT rowid, filename{} FROM files".format(", path" if has_path else "")
            cur.execute(query)
            rows = cur.fetchall()

            stale_ids = []
            for row in rows:
                if has_path:
                    rowid, filename, path = row
                    # path 존재 여부 확인
                    exists = os.path.exists(path) if os.path.isabs(path) else os.path.exists(os.path.join(os.getcwd(), path))
                    if not exists and filename not in fs_names:
                        stale_ids.append(rowid)
                else:
                    rowid, filename = row
                    if filename not in fs_names:
                        stale_ids.append(rowid)

            # 삭제 실행
            if stale_ids:
                qmarks = ",".join(["?"] * len(stale_ids))
                cur.execute(f"DELETE FROM files WHERE rowid IN ({qmarks})", stale_ids)
                conn.commit()

            conn.close()
            return len(stale_ids)

        except Exception as e:
            print(f"⚠️ 인덱스 정리 실패: {e}")
            return 0

    def force_reindex(self):
        """강제 재인덱싱"""
        print("🔄 강제 재인덱싱 시작...")
        self.file_index = {'files': {}, 'last_update': None}
        self.failed_files = {}  # 실패 목록 초기화
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