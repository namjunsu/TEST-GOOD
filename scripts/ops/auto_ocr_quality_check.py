#!/usr/bin/env python3
"""자동 OCR 품질 모니터링

일일 POOR 문서 비율을 체크하고, 임계값 초과 시 알림

사용법:
    python scripts/ops/auto_ocr_quality_check.py
    python scripts/ops/auto_ocr_quality_check.py --threshold 0.20

Cron 설정 예시:
    0 9 * * * cd /home/wnstn4647/AI-CHAT && python scripts/ops/auto_ocr_quality_check.py
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


# 임계값
THRESHOLD_POOR = 100
DEFAULT_ALERT_THRESHOLD = 0.15  # 15% 이상 POOR이면 알림


def check_ocr_quality(db_path: str = "metadata.db",
                      alert_threshold: float = DEFAULT_ALERT_THRESHOLD):
    """OCR 품질 체크 및 알림

    Args:
        db_path: 데이터베이스 경로
        alert_threshold: 알림 임계값 (POOR 비율)

    Returns:
        (total, poor, ratio) 튜플
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 통계 조회
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN LENGTH(text_preview) < ? THEN 1 ELSE 0 END) as poor
        FROM documents
    """, (THRESHOLD_POOR,))

    result = cursor.fetchone()
    total = result[0]
    poor = result[1]
    ratio = poor / total if total > 0 else 0

    conn.close()

    return total, poor, ratio


def send_alert(total: int, poor: int, ratio: float):
    """알림 전송

    Args:
        total: 전체 문서 수
        poor: POOR 문서 수
        ratio: POOR 비율
    """
    message = f"""⚠️ OCR 품질 경고

일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
전체 문서: {total}개
POOR 문서: {poor}개 ({ratio * 100:.1f}%)

조치 필요:
  python scripts/reprocess_ocr_dual_engine.py --quality POOR --batch-size 10
"""

    # 콘솔 출력
    print(message)

    # TODO: Slack 연동 (선택사항)
    # if os.getenv('SLACK_WEBHOOK_URL'):
    #     requests.post(os.getenv('SLACK_WEBHOOK_URL'), json={'text': message})


def main():
    parser = argparse.ArgumentParser(description="자동 OCR 품질 모니터링")
    parser.add_argument("--db-path", type=str, default="metadata.db", help="DB 경로")
    parser.add_argument("--threshold", type=float, default=DEFAULT_ALERT_THRESHOLD,
                       help=f"알림 임계값 (기본: {DEFAULT_ALERT_THRESHOLD})")
    parser.add_argument("--silent", action="store_true", help="정상 시 출력 안 함")

    args = parser.parse_args()

    total, poor, ratio = check_ocr_quality(args.db_path, args.threshold)

    if ratio >= args.threshold:
        print("❌ OCR 품질 저하 감지!")
        send_alert(total, poor, ratio)
        sys.exit(1)  # 비정상 종료 (Cron 알림용)
    else:
        if not args.silent:
            print("✅ OCR 품질 정상")
            print(f"  - 전체: {total}개")
            print(f"  - POOR: {poor}개 ({ratio * 100:.1f}%)")
            print(f"  - 임계값: {args.threshold * 100:.1f}%")
        sys.exit(0)  # 정상 종료


if __name__ == "__main__":
    main()
