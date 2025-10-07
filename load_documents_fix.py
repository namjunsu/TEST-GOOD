#!/usr/bin/env python3
"""
Complete load_documents function implementation
"""

import sqlite3
import pandas as pd

def load_documents(_rag_instance):
    """초고속 문서 메타데이터 로드 - DB에서 직접 조회"""
    print("🚀 초고속 문서 로드 시작 (DB 직접 조회)")

    try:
        # SQLite DB 연결
        conn = sqlite3.connect('everything_index.db')
        cursor = conn.cursor()

        # 모든 문서 정보 조회
        cursor.execute("""
            SELECT filename, path, date, year, category, department, keywords
            FROM files
            ORDER BY year DESC, filename ASC
        """)

        rows = cursor.fetchall()
        documents = []

        print(f"📊 DB에서 {len(rows)}개 문서 로드됨")

        for filename, path, date, year, category, department, keywords in rows:
            # 카테고리 분류
            if '구매' in filename:
                doc_category = "구매"
            elif '수리' in filename:
                doc_category = "수리"
            elif '교체' in filename:
                doc_category = "교체"
            elif '검토' in filename:
                doc_category = "검토"
            elif '폐기' in filename:
                doc_category = "폐기"
            else:
                doc_category = category or "기타"

            # 기안자 정보 (이미 DB에 동기화됨)
            drafter = department if department and department not in ['영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출'] else "미확인"

            # 문서 정보 구성
            documents.append({
                'filename': filename,
                'title': filename.replace('.pdf', '').replace('_', ' '),
                'date': date or '날짜없음',
                'year': year or '연도없음',
                'category': doc_category,
                'drafter': drafter,
                'size': '알 수 없음',
                'path': path,
                'keywords': keywords or ''
            })

        conn.close()
        print(f"✅ {len(documents)}개 문서 초고속 로드 완료!")

        # DataFrame으로 변환 후 반환
        df = pd.DataFrame(documents)
        if not df.empty:
            # 연도와 파일명으로 정렬
            df = df.sort_values(['year', 'filename'], ascending=[False, True])

        # 통계 출력
        drafter_count = len(df[df['drafter'] != '미확인']) if not df.empty else 0
        print(f"📈 기안자 통계:")
        print(f"  - 기안자 확인: {drafter_count}개 ({drafter_count*100//max(len(documents), 1)}%)")
        print(f"  - 기안자 미확인: {len(documents) - drafter_count}개")

        return df

    except Exception as e:
        print(f"❌ 초고속 로드 실패: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    # 테스트
    df = load_documents(None)
    print(f"결과: {len(df)}개 문서")