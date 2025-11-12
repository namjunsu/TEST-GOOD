#!/usr/bin/env python3
"""
DB 백업 및 이상치 탐지 스크립트
- metadata.db 백업 생성
- 금액 이상치 탐지 (amount=0, NULL, >= 100M, < 1000)
- 재인덱싱 대상 목록 생성
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# 경로 설정
DB_PATH = Path("/home/wnstn4647/AI-CHAT/metadata.db")
BACKUP_DIR = Path("/home/wnstn4647/AI-CHAT/backups")
REPORTS_DIR = Path("/home/wnstn4647/AI-CHAT/reports")

def backup_database() -> Path:
    """metadata.db 백업 생성"""
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"metadata_backup_{timestamp}.db"

    print(f"📦 Creating backup: {backup_path}")
    shutil.copy2(DB_PATH, backup_path)

    # 백업 검증
    backup_size = backup_path.stat().st_size
    original_size = DB_PATH.stat().st_size

    if backup_size == original_size:
        print(f"✓ Backup successful: {backup_size:,} bytes")
        return backup_path
    else:
        raise RuntimeError(f"Backup size mismatch: {backup_size} != {original_size}")


def detect_amount_anomalies() -> Dict[str, List[Dict[str, Any]]]:
    """금액 이상치 탐지"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    anomalies = {
        'amount_zero_or_null': [],
        'amount_too_high': [],      # >= 100M
        'amount_too_low': [],        # 1 <= amount < 1000
        'total': 0
    }

    # 1) amount=0 또는 NULL
    print("\n🔍 Detecting amount=0 or NULL...")
    cur.execute("""
        SELECT id, filename, path, drafter, date, amount
        FROM documents
        WHERE amount IS NULL OR amount = 0
        ORDER BY date DESC
    """)
    for row in cur.fetchall():
        anomalies['amount_zero_or_null'].append(dict(row))

    # 2) amount >= 100M (억 단위 이상)
    print("🔍 Detecting amount >= 100M...")
    cur.execute("""
        SELECT id, filename, path, drafter, date, amount
        FROM documents
        WHERE amount >= 100000000
        ORDER BY amount DESC
    """)
    for row in cur.fetchall():
        anomalies['amount_too_high'].append(dict(row))

    # 3) 1 <= amount < 1000 (비정상적으로 낮은 금액)
    print("🔍 Detecting 1 <= amount < 1000...")
    cur.execute("""
        SELECT id, filename, path, drafter, date, amount
        FROM documents
        WHERE amount >= 1 AND amount < 1000
        ORDER BY amount ASC
    """)
    for row in cur.fetchall():
        anomalies['amount_too_low'].append(dict(row))

    # 전체 문서 수
    cur.execute("SELECT COUNT(*) as cnt FROM documents")
    total_docs = cur.fetchone()['cnt']

    conn.close()

    anomalies['total'] = (
        len(anomalies['amount_zero_or_null']) +
        len(anomalies['amount_too_high']) +
        len(anomalies['amount_too_low'])
    )

    # 결과 출력
    print("\n" + "="*80)
    print("📊 ANOMALY DETECTION RESULTS")
    print("="*80)
    print(f"Total documents in DB: {total_docs:,}")
    print(f"Total anomalies found: {anomalies['total']:,}")
    print(f"  - amount=0 or NULL: {len(anomalies['amount_zero_or_null']):,}")
    print(f"  - amount >= 100M: {len(anomalies['amount_too_high']):,}")
    print(f"  - amount < 1000: {len(anomalies['amount_too_low']):,}")
    print("="*80)

    return anomalies


def save_anomaly_report(anomalies: Dict[str, List[Dict[str, Any]]]) -> Path:
    """이상치 리포트를 파일로 저장"""
    REPORTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"anomaly_report_{timestamp}.txt"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("금액 이상치 탐지 리포트\n")
        f.write(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

        # 1) amount=0 or NULL
        f.write(f"[1] amount=0 or NULL ({len(anomalies['amount_zero_or_null'])} 건)\n")
        f.write("-"*80 + "\n")
        for i, doc in enumerate(anomalies['amount_zero_or_null'][:20], 1):  # 최대 20건만
            amt = doc['amount'] if doc['amount'] is not None else 'NULL'
            f.write(f"{i:3d}. ID={doc['id']} | {doc['filename']}\n")
            f.write(f"     path: {doc['path']}\n")
            f.write(f"     drafter: {doc['drafter'] or 'N/A'}, date: {doc['date'] or 'N/A'}\n")
            f.write(f"     amount: {amt}\n\n")

        if len(anomalies['amount_zero_or_null']) > 20:
            f.write(f"     ... and {len(anomalies['amount_zero_or_null']) - 20} more\n\n")

        # 2) amount >= 100M
        f.write(f"\n[2] amount >= 100M ({len(anomalies['amount_too_high'])} 건)\n")
        f.write("-"*80 + "\n")
        for i, doc in enumerate(anomalies['amount_too_high'], 1):
            f.write(f"{i:3d}. ID={doc['id']} | {doc['filename']}\n")
            f.write(f"     path: {doc['path']}\n")
            f.write(f"     drafter: {doc['drafter'] or 'N/A'}, date: {doc['date'] or 'N/A'}\n")
            f.write(f"     amount: ₩{doc['amount']:,} (INVALID)\n\n")

        # 3) amount < 1000
        f.write(f"\n[3] 1 <= amount < 1000 ({len(anomalies['amount_too_low'])} 건)\n")
        f.write("-"*80 + "\n")
        for i, doc in enumerate(anomalies['amount_too_low'], 1):
            f.write(f"{i:3d}. ID={doc['id']} | {doc['filename']}\n")
            f.write(f"     path: {doc['path']}\n")
            f.write(f"     drafter: {doc['drafter'] or 'N/A'}, date: {doc['date'] or 'N/A'}\n")
            f.write(f"     amount: ₩{doc['amount']:,} (TOO LOW)\n\n")

        f.write("\n" + "="*80 + "\n")
        f.write(f"총 이상치: {anomalies['total']} 건\n")
        f.write("="*80 + "\n")

    print(f"\n✓ Report saved: {report_path}")
    return report_path


def main():
    """메인 실행"""
    print("="*80)
    print("DB 백업 및 이상치 탐지 시작")
    print("="*80)

    try:
        # 1) DB 백업
        backup_path = backup_database()
        print(f"✓ Backup saved: {backup_path}\n")

        # 2) 이상치 탐지
        anomalies = detect_amount_anomalies()

        # 3) 리포트 저장
        report_path = save_anomaly_report(anomalies)

        # 4) 요약
        print("\n" + "="*80)
        print("완료 요약")
        print("="*80)
        print(f"Backup: {backup_path}")
        print(f"Report: {report_path}")
        print(f"Total anomalies: {anomalies['total']}")
        print("="*80)

        # 5) 재인덱싱 대상 ID 목록 저장
        if anomalies['total'] > 0:
            reindex_list_path = REPORTS_DIR / f"reindex_targets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(reindex_list_path, 'w', encoding='utf-8') as f:
                for doc in anomalies['amount_zero_or_null']:
                    f.write(f"{doc['id']}\t{doc['path']}\n")
                for doc in anomalies['amount_too_high']:
                    f.write(f"{doc['id']}\t{doc['path']}\n")
                for doc in anomalies['amount_too_low']:
                    f.write(f"{doc['id']}\t{doc['path']}\n")
            print(f"\n📋 Reindex targets saved: {reindex_list_path}")

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
