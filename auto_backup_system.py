#!/usr/bin/env python3
"""
자동 백업 시스템
================
데이터 자동 백업 및 복구 시스템
"""

import os
import shutil
import tarfile
import gzip
import json
import hashlib
import schedule
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3
import pickle

class AutoBackupSystem:
    """자동 백업 시스템"""

    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # 백업 설정
        self.config = {
            'max_backups': 10,  # 최대 백업 수
            'compression': 'gzip',  # 압축 방식
            'incremental': True,  # 증분 백업 사용
            'schedule': {
                'full_backup': 'daily',  # 전체 백업 주기
                'incremental_backup': 'hourly',  # 증분 백업 주기
                'cleanup': 'weekly'  # 정리 주기
            }
        }

        # 백업 대상
        self.backup_targets = {
            'database': [
                '.cache/faiss_index',
                'rag_system/indexes',
                'logs/queries.db'
            ],
            'config': [
                'config.py',
                'config_optimized.py',
                '.env'
            ],
            'cache': [
                '.cache',
                '__pycache__'
            ],
            'logs': [
                'logs/*.log',
                'logs/*.json'
            ]
        }

        # 백업 히스토리
        self.backup_history = []
        self.load_backup_history()

        # 스케줄러
        self.scheduler_thread = None
        self.running = False

    def start_scheduler(self):
        """백업 스케줄러 시작"""
        if not self.running:
            self.running = True

            # 스케줄 설정
            schedule.every().hour.do(self.incremental_backup)
            schedule.every().day.at("03:00").do(self.full_backup)
            schedule.every().week.do(self.cleanup_old_backups)

            # 스케줄러 스레드 시작
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.scheduler_thread.start()

            print("⏰ 자동 백업 스케줄러 시작")

    def stop_scheduler(self):
        """백업 스케줄러 중지"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        print("⏹️  자동 백업 스케줄러 중지")

    def _run_scheduler(self):
        """스케줄러 실행"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크

    def full_backup(self) -> Dict[str, Any]:
        """전체 백업"""
        print("🔄 전체 백업 시작...")
        start_time = time.time()

        # 백업 ID 생성
        backup_id = f"full_{datetime.now():%Y%m%d_%H%M%S}"
        backup_path = self.backup_dir / backup_id

        try:
            # 백업 디렉토리 생성
            backup_path.mkdir(parents=True, exist_ok=True)

            # 메타데이터
            metadata = {
                'id': backup_id,
                'type': 'full',
                'timestamp': datetime.now().isoformat(),
                'targets': {}
            }

            # 각 대상 백업
            for target_name, paths in self.backup_targets.items():
                target_backup_path = backup_path / target_name
                target_backup_path.mkdir(exist_ok=True)

                backed_up_files = []
                for path_pattern in paths:
                    for path in Path('.').glob(path_pattern):
                        if path.exists():
                            dest = target_backup_path / path.name

                            if path.is_dir():
                                shutil.copytree(path, dest, dirs_exist_ok=True)
                            else:
                                shutil.copy2(path, dest)

                            backed_up_files.append(str(path))

                metadata['targets'][target_name] = backed_up_files

            # 압축
            archive_path = self._compress_backup(backup_path, backup_id)

            # 검증
            checksum = self._calculate_checksum(archive_path)

            # 메타데이터 업데이트
            metadata.update({
                'archive_path': str(archive_path),
                'size_mb': archive_path.stat().st_size / (1024**2),
                'checksum': checksum,
                'duration': time.time() - start_time
            })

            # 메타데이터 저장
            with open(self.backup_dir / f"{backup_id}.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            # 히스토리 업데이트
            self.backup_history.append(metadata)
            self.save_backup_history()

            # 임시 디렉토리 정리
            shutil.rmtree(backup_path)

            print(f"✅ 전체 백업 완료: {archive_path.name} ({metadata['size_mb']:.2f} MB)")
            return metadata

        except Exception as e:
            print(f"❌ 백업 실패: {e}")
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            return None

    def incremental_backup(self) -> Dict[str, Any]:
        """증분 백업 (변경된 파일만)"""
        print("🔄 증분 백업 시작...")

        # 마지막 백업 이후 변경된 파일 찾기
        last_backup = self._get_last_backup()
        if not last_backup:
            # 첫 백업은 전체 백업
            return self.full_backup()

        last_backup_time = datetime.fromisoformat(last_backup['timestamp'])
        backup_id = f"inc_{datetime.now():%Y%m%d_%H%M%S}"
        backup_path = self.backup_dir / backup_id

        try:
            backup_path.mkdir(parents=True, exist_ok=True)

            metadata = {
                'id': backup_id,
                'type': 'incremental',
                'base_backup': last_backup['id'],
                'timestamp': datetime.now().isoformat(),
                'targets': {}
            }

            # 변경된 파일만 백업
            backed_up_count = 0
            for target_name, paths in self.backup_targets.items():
                target_backup_path = backup_path / target_name
                changed_files = []

                for path_pattern in paths:
                    for path in Path('.').glob(path_pattern):
                        if path.exists():
                            # 수정 시간 확인
                            mtime = datetime.fromtimestamp(path.stat().st_mtime)
                            if mtime > last_backup_time:
                                target_backup_path.mkdir(parents=True, exist_ok=True)
                                dest = target_backup_path / path.name

                                if path.is_dir():
                                    shutil.copytree(path, dest, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(path, dest)

                                changed_files.append(str(path))
                                backed_up_count += 1

                if changed_files:
                    metadata['targets'][target_name] = changed_files

            if backed_up_count == 0:
                print("ℹ️  변경된 파일 없음")
                shutil.rmtree(backup_path)
                return None

            # 압축
            archive_path = self._compress_backup(backup_path, backup_id)

            # 메타데이터 업데이트
            metadata.update({
                'archive_path': str(archive_path),
                'size_mb': archive_path.stat().st_size / (1024**2),
                'checksum': self._calculate_checksum(archive_path),
                'files_count': backed_up_count
            })

            # 저장
            with open(self.backup_dir / f"{backup_id}.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            self.backup_history.append(metadata)
            self.save_backup_history()

            # 정리
            shutil.rmtree(backup_path)

            print(f"✅ 증분 백업 완료: {backed_up_count}개 파일 ({metadata['size_mb']:.2f} MB)")
            return metadata

        except Exception as e:
            print(f"❌ 증분 백업 실패: {e}")
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            return None

    def restore_backup(self, backup_id: str, target_dir: str = ".") -> bool:
        """백업 복원"""
        print(f"🔄 백업 복원 시작: {backup_id}")

        # 메타데이터 로드
        metadata_file = self.backup_dir / f"{backup_id}.json"
        if not metadata_file.exists():
            print(f"❌ 백업을 찾을 수 없음: {backup_id}")
            return False

        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            archive_path = Path(metadata['archive_path'])
            if not archive_path.exists():
                print(f"❌ 백업 아카이브를 찾을 수 없음: {archive_path}")
                return False

            # 체크섬 검증
            if self._calculate_checksum(archive_path) != metadata['checksum']:
                print("❌ 백업 파일 손상 감지")
                return False

            # 압축 해제
            temp_dir = self.backup_dir / f"restore_{backup_id}"
            self._decompress_backup(archive_path, temp_dir)

            # 파일 복원
            target_path = Path(target_dir)
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    src = Path(root) / file
                    rel_path = src.relative_to(temp_dir)
                    dest = target_path / rel_path

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

            # 정리
            shutil.rmtree(temp_dir)

            print(f"✅ 백업 복원 완료: {backup_id}")
            return True

        except Exception as e:
            print(f"❌ 복원 실패: {e}")
            return False

    def _compress_backup(self, source_dir: Path, backup_id: str) -> Path:
        """백업 압축"""
        archive_path = self.backup_dir / f"{backup_id}.tar.gz"

        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(source_dir, arcname=backup_id)

        return archive_path

    def _decompress_backup(self, archive_path: Path, target_dir: Path):
        """백업 압축 해제"""
        target_dir.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(target_dir)

    def _calculate_checksum(self, file_path: Path) -> str:
        """체크섬 계산"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def cleanup_old_backups(self):
        """오래된 백업 정리"""
        print("🧹 오래된 백업 정리...")

        # 백업 목록 정렬 (날짜순)
        self.backup_history.sort(key=lambda x: x['timestamp'])

        # 전체 백업 유지
        full_backups = [b for b in self.backup_history if b['type'] == 'full']
        if len(full_backups) > self.config['max_backups']:
            to_delete = full_backups[:-self.config['max_backups']]

            for backup in to_delete:
                self._delete_backup(backup)

        # 7일 이상된 증분 백업 삭제
        cutoff_date = datetime.now() - timedelta(days=7)
        inc_backups = [b for b in self.backup_history if b['type'] == 'incremental']

        for backup in inc_backups:
            if datetime.fromisoformat(backup['timestamp']) < cutoff_date:
                self._delete_backup(backup)

        self.save_backup_history()
        print(f"✅ 정리 완료: {len(self.backup_history)}개 백업 유지")

    def _delete_backup(self, backup: Dict):
        """백업 삭제"""
        try:
            # 아카이브 삭제
            archive_path = Path(backup['archive_path'])
            if archive_path.exists():
                archive_path.unlink()

            # 메타데이터 삭제
            metadata_file = self.backup_dir / f"{backup['id']}.json"
            if metadata_file.exists():
                metadata_file.unlink()

            # 히스토리에서 제거
            self.backup_history.remove(backup)

            print(f"🗑️  백업 삭제: {backup['id']}")

        except Exception as e:
            print(f"❌ 백업 삭제 실패: {e}")

    def _get_last_backup(self) -> Optional[Dict]:
        """마지막 백업 정보"""
        if not self.backup_history:
            return None
        return max(self.backup_history, key=lambda x: x['timestamp'])

    def load_backup_history(self):
        """백업 히스토리 로드"""
        history_file = self.backup_dir / "backup_history.pkl"
        if history_file.exists():
            try:
                with open(history_file, 'rb') as f:
                    self.backup_history = pickle.load(f)
            except:
                self.backup_history = []

    def save_backup_history(self):
        """백업 히스토리 저장"""
        history_file = self.backup_dir / "backup_history.pkl"
        with open(history_file, 'wb') as f:
            pickle.dump(self.backup_history, f)

    def get_backup_status(self) -> Dict:
        """백업 상태 조회"""
        if not self.backup_history:
            return {
                'status': 'no_backups',
                'last_backup': None,
                'total_backups': 0,
                'total_size_mb': 0
            }

        last_backup = self._get_last_backup()
        total_size = sum(b.get('size_mb', 0) for b in self.backup_history)

        return {
            'status': 'healthy',
            'last_backup': {
                'id': last_backup['id'],
                'type': last_backup['type'],
                'timestamp': last_backup['timestamp'],
                'size_mb': last_backup.get('size_mb', 0)
            },
            'total_backups': len(self.backup_history),
            'total_size_mb': total_size,
            'full_backups': len([b for b in self.backup_history if b['type'] == 'full']),
            'incremental_backups': len([b for b in self.backup_history if b['type'] == 'incremental'])
        }


# 전역 인스턴스
backup_system = AutoBackupSystem()


# 사용 예제
if __name__ == "__main__":
    print("🎯 자동 백업 시스템 테스트")

    # 백업 시스템 초기화
    backup = AutoBackupSystem()

    # 스케줄러 시작
    backup.start_scheduler()

    # 즉시 전체 백업
    full_backup = backup.full_backup()
    if full_backup:
        print(f"전체 백업 ID: {full_backup['id']}")

    # 파일 수정 시뮬레이션
    time.sleep(2)
    test_file = Path("test_backup.txt")
    test_file.write_text(f"테스트 파일 - {datetime.now()}")

    # 증분 백업
    inc_backup = backup.incremental_backup()
    if inc_backup:
        print(f"증분 백업 ID: {inc_backup['id']}")

    # 백업 상태
    status = backup.get_backup_status()
    print(f"\n📊 백업 상태:")
    print(json.dumps(status, indent=2, ensure_ascii=False))

    # 테스트 파일 정리
    if test_file.exists():
        test_file.unlink()

    # 스케줄러 중지
    backup.stop_scheduler()