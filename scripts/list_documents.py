#!/usr/bin/env python3
"""
문서 목록 조회 스크립트
metadata.db에 인덱싱된 문서 정보를 깔끔하게 출력합니다.
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def format_size(size_bytes):
    """파일 크기를 읽기 좋게 포맷"""
    if size_bytes is None:
        return "N/A"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"


def list_documents(db_path="metadata.db", limit=None, show_details=False):
    """문서 목록 조회 및 출력

    Args:
        db_path: DB 파일 경로
        limit: 최대 출력 개수 (None이면 전체)
        show_details: 상세 정보 출력 여부
    """
    if not Path(db_path).exists():
        print(f"❌ DB 파일이 없습니다: {db_path}")
        return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 문서 통계
        cursor.execute("SELECT COUNT(*) as total FROM documents")
        total = cursor.fetchone()['total']

        print("=" * 80)
        print(f"📚 문서 라이브러리 (총 {total}개 문서)")
        print("=" * 80)

        if total == 0:
            print("\n⚠️  인덱싱된 문서가 없습니다.")
            print("   docs/ 폴더에 PDF 파일을 추가한 후 재인덱싱하세요.\n")
            return []

        # 문서 목록 조회
        query = """
            SELECT
                id,
                filename,
                title,
                date,
                year,
                category,
                drafter,
                page_count,
                file_size,
                keywords,
                created_at
            FROM documents
            ORDER BY created_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = cursor.fetchall()

        documents = []

        if show_details:
            # 상세 출력
            for i, row in enumerate(rows, 1):
                doc_id = row['id']
                filename = row['filename']
                title = row['title'] or "(제목 없음)"
                date = row['date'] or "날짜 없음"
                year = row['year'] or "연도 없음"
                category = row['category'] or "분류 없음"
                drafter = row['drafter'] or "기안자 없음"
                page_count = row['page_count'] or 0
                file_size = format_size(row['file_size'])
                keywords = row['keywords'] or "[]"
                created_at = row['created_at']

                print(f"\n[{i}] 문서 ID: {doc_id}")
                print(f"    파일명: {filename}")
                print(f"    제목: {title}")
                print(f"    날짜: {date} (연도: {year})")
                print(f"    분류: {category}")
                print(f"    기안자: {drafter}")
                print(f"    페이지: {page_count}p")
                print(f"    크기: {file_size}")
                print(f"    키워드: {keywords}")
                print(f"    인덱싱: {created_at}")
                print("-" * 80)

                documents.append({
                    'id': doc_id,
                    'filename': filename,
                    'title': title,
                    'date': date,
                    'year': year,
                    'category': category,
                    'drafter': drafter,
                    'page_count': page_count,
                    'keywords': keywords
                })
        else:
            # 간단한 테이블 형태
            print(f"\n{'ID':<5} {'파일명':<30} {'제목':<40} {'페이지':<8} {'연도':<6}")
            print("-" * 80)

            for row in rows:
                doc_id = row['id']
                filename = row['filename'][:28] + ".." if len(row['filename']) > 30 else row['filename']
                title = (row['title'] or "(제목 없음)")[:38] + ".." if row['title'] and len(row['title']) > 40 else (row['title'] or "(제목 없음)")
                page_count = row['page_count'] or 0
                year = row['year'] or "N/A"

                print(f"{doc_id:<5} {filename:<30} {title:<40} {page_count:<8} {year:<6}")

                documents.append({
                    'id': doc_id,
                    'filename': row['filename'],
                    'title': row['title'],
                    'date': row['date'],
                    'year': row['year'],
                    'category': row['category'],
                    'drafter': row['drafter'],
                    'page_count': row['page_count'],
                    'keywords': row['keywords']
                })

        print("\n" + "=" * 80)

        # 연도별 통계
        cursor.execute("""
            SELECT year, COUNT(*) as count
            FROM documents
            WHERE year IS NOT NULL AND year != ''
            GROUP BY year
            ORDER BY year DESC
        """)
        year_stats = cursor.fetchall()

        if year_stats:
            print("\n📊 연도별 분포:")
            for stat in year_stats:
                year = stat['year']
                count = stat['count']
                print(f"   {year}년: {count}개")

        # 분류별 통계
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM documents
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY count DESC
            LIMIT 5
        """)
        category_stats = cursor.fetchall()

        if category_stats:
            print("\n📂 주요 분류 (상위 5개):")
            for stat in category_stats:
                category = stat['category']
                count = stat['count']
                print(f"   {category}: {count}개")

        print()

        conn.close()
        return documents

    except sqlite3.Error as e:
        print(f"❌ DB 오류: {e}")
        return []


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="문서 목록 조회")
    parser.add_argument("--db", default="metadata.db", help="DB 파일 경로")
    parser.add_argument("--limit", type=int, help="최대 출력 개수")
    parser.add_argument("--details", action="store_true", help="상세 정보 출력")

    args = parser.parse_args()

    documents = list_documents(
        db_path=args.db,
        limit=args.limit,
        show_details=args.details
    )

    return 0 if documents else 1


if __name__ == "__main__":
    sys.exit(main())
