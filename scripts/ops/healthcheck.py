#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
시스템 헬스체크 스크립트

시스템의 전반적인 상태를 체크하고 문제를 보고합니다.
"""

import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger

logger = get_logger(__name__)

class HealthChecker:
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.ok_items = []

    def check_database(self):
        """DB 상태 체크"""
        try:
            conn = sqlite3.connect("metadata.db", timeout=5)
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            doc_count = cursor.fetchone()[0]
            conn.close()

            self.ok_items.append(f"✅ DB 연결 정상 ({doc_count}개 문서)")

            # DB 크기 체크
            db_path = Path("metadata.db")
            if db_path.exists():
                db_size_mb = db_path.stat().st_size / (1024 * 1024)
                if db_size_mb > 1000:  # 1GB 이상
                    self.warnings.append(f"⚠️ DB 크기가 큼: {db_size_mb:.1f}MB")
                else:
                    self.ok_items.append(f"✅ DB 크기 정상: {db_size_mb:.1f}MB")

        except Exception as e:
            self.issues.append(f"❌ DB 연결 실패: {e}")

    def check_sync_status(self):
        """파일시스템-DB 동기화 체크"""
        try:
            # year 폴더의 PDF 개수
            year_dirs = list(Path("docs").glob("year_20*"))
            total_pdfs = sum(len(list(d.glob("*.pdf"))) for d in year_dirs)

            # DB 문서 개수
            conn = sqlite3.connect("metadata.db")
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            db_count = cursor.fetchone()[0]
            conn.close()

            diff = abs(total_pdfs - db_count)
            if diff == 0:
                self.ok_items.append(f"✅ 동기화 완벽: {total_pdfs}개 파일 = {db_count}개 DB 레코드")
            elif diff <= 5:
                self.warnings.append(
                    f"⚠️ 동기화 약간 불일치: {total_pdfs}개 파일 vs {db_count}개 DB ({diff}개 차이)"
                )
            else:
                self.issues.append(
                    f"❌ 동기화 심각한 불일치: {total_pdfs}개 파일 vs {db_count}개 DB ({diff}개 차이)"
                )

        except Exception as e:
            self.issues.append(f"❌ 동기화 체크 실패: {e}")

    def check_disk_space(self):
        """디스크 공간 체크"""
        try:
            result = subprocess.run(
                ["df", "-h", "."], capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                use_percent = int(parts[4].rstrip("%"))

                if use_percent >= 90:
                    self.issues.append(f"❌ 디스크 공간 부족: {use_percent}% 사용")
                elif use_percent >= 75:
                    self.warnings.append(f"⚠️ 디스크 공간 주의: {use_percent}% 사용")
                else:
                    self.ok_items.append(f"✅ 디스크 공간 충분: {use_percent}% 사용")

        except Exception as e:
            self.warnings.append(f"⚠️ 디스크 체크 실패: {e}")

    def check_metadata_quality(self):
        """메타데이터 품질 체크"""
        try:
            conn = sqlite3.connect("metadata.db")

            # 기안자 추출률
            cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE drafter IS NOT NULL")
            drafter_count = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            total_count = cursor.fetchone()[0]

            drafter_rate = (drafter_count / total_count * 100) if total_count > 0 else 0

            if drafter_rate >= 80:
                self.ok_items.append(f"✅ 기안자 추출률 양호: {drafter_rate:.1f}%")
            elif drafter_rate >= 60:
                self.warnings.append(f"⚠️ 기안자 추출률 보통: {drafter_rate:.1f}%")
            else:
                self.issues.append(f"❌ 기안자 추출률 낮음: {drafter_rate:.1f}%")

            # 텍스트 추출 품질
            cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE length(text_preview) < 100"
            )
            poor_count = cursor.fetchone()[0]

            if poor_count == 0:
                self.ok_items.append("✅ 텍스트 추출 품질 완벽")
            elif poor_count <= 10:
                self.warnings.append(f"⚠️ 텍스트 추출 불량: {poor_count}개 문서")
            else:
                self.issues.append(f"❌ 텍스트 추출 심각: {poor_count}개 문서")

            conn.close()

        except Exception as e:
            self.warnings.append(f"⚠️ 메타데이터 품질 체크 실패: {e}")

    def check_duplicate_folders(self):
        """중복 폴더 체크"""
        dup_folder = Path("docs/year_정보 없")
        if dup_folder.exists():
            dup_count = len(list(dup_folder.glob("*.pdf")))
            if dup_count > 0:
                self.warnings.append(
                    f"⚠️ year_정보 없 폴더에 {dup_count}개 파일 (정리 권장)"
                )
            else:
                self.ok_items.append("✅ 중복 폴더 없음")
        else:
            self.ok_items.append("✅ 중복 폴더 없음")

    def check_backup_files(self):
        """백업 파일 존재 여부 체크"""
        backup_dir = Path("backups/db")
        if not backup_dir.exists():
            self.warnings.append("⚠️ 백업 디렉터리 없음 (backups/db)")
            return

        backups = list(backup_dir.glob("metadata.db.*.bak"))
        if not backups:
            self.warnings.append("⚠️ DB 백업 파일 없음 (backups/db)")
        else:
            # 최신 백업 파일 확인
            latest_backup = max(backups, key=lambda p: p.stat().st_mtime)
            backup_age_hours = (time.time() - latest_backup.stat().st_mtime) / 3600

            if backup_age_hours > 48:  # 48시간 이상 오래됨
                self.warnings.append(
                    f"⚠️ 최신 백업이 오래됨: {backup_age_hours:.1f}시간 전 ({latest_backup.name})"
                )
            else:
                self.ok_items.append(
                    f"✅ DB 백업 정상: {len(backups)}개 파일, 최신 {backup_age_hours:.1f}시간 전"
                )

    def check_services(self):
        """서비스 프로세스 체크"""
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=10
            )
            output = result.stdout

            streamlit_running = "streamlit" in output
            uvicorn_running = "uvicorn" in output

            if streamlit_running and uvicorn_running:
                self.ok_items.append("✅ 웹 서비스 실행 중 (Streamlit + Uvicorn)")
            elif streamlit_running:
                self.warnings.append("⚠️ Streamlit만 실행 중 (Uvicorn 중지됨)")
            elif uvicorn_running:
                self.warnings.append("⚠️ Uvicorn만 실행 중 (Streamlit 중지됨)")
            else:
                self.issues.append("❌ 웹 서비스 중지됨")

        except Exception as e:
            self.warnings.append(f"⚠️ 서비스 체크 실패: {e}")

    def run_all_checks(self):
        """모든 체크 실행"""
        print("🏥 시스템 헬스체크 시작...")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        self.check_database()
        self.check_sync_status()
        self.check_disk_space()
        self.check_metadata_quality()
        self.check_duplicate_folders()
        self.check_backup_files()
        self.check_services()

        # 결과 출력
        print("\n" + "=" * 80)
        print("📊 헬스체크 결과")
        print("=" * 80)

        if self.issues:
            print(f"\n🚨 심각한 문제 ({len(self.issues)}개):")
            for issue in self.issues:
                print(f"  {issue}")

        if self.warnings:
            print(f"\n⚠️  경고 ({len(self.warnings)}개):")
            for warning in self.warnings:
                print(f"  {warning}")

        if self.ok_items:
            print(f"\n✅ 정상 ({len(self.ok_items)}개):")
            for ok_item in self.ok_items:
                print(f"  {ok_item}")

        print("\n" + "=" * 80)

        # 전체 상태
        if self.issues:
            print("🔴 시스템 상태: 문제 있음 (즉시 조치 필요)")
            return 2
        elif self.warnings:
            print("🟡 시스템 상태: 주의 필요")
            return 1
        else:
            print("🟢 시스템 상태: 정상")
            return 0


def main():
    checker = HealthChecker()
    exit_code = checker.run_all_checks()

    # 권장 조치
    if exit_code > 0:
        print("\n💡 권장 조치:")
        if any("동기화" in issue for issue in checker.issues + checker.warnings):
            print("   - python scripts/auto_sync_checker.py --auto-fix")
        if any("중복" in warning for warning in checker.warnings):
            print("   - python scripts/cleanup_duplicates.py")
        if any("텍스트" in issue for issue in checker.issues):
            print("   - python scripts/force_ocr_update.py --threshold 100")
        if any("웹 서비스" in issue for issue in checker.issues):
            print("   - bash start_ai_chat.sh")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
