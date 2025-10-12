#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('everything_index.db')
cursor = conn.cursor()

print('🗑️  중복 레코드 정리')
print('='*60)

# 각 파일명마다 절대 경로 버전만 유지
cursor.execute('''
    SELECT filename, GROUP_CONCAT(id || ':' || path, '|||') as id_paths
    FROM files
    GROUP BY filename
    HAVING COUNT(*) > 1
''')

to_delete = []
for filename, id_paths in cursor.fetchall():
    entries = id_paths.split('|||')

    # 절대 경로 우선 (더 긴 경로)
    longest_id = None
    longest_len = 0

    for entry in entries:
        file_id, path = entry.split(':', 1)
        if len(path) > longest_len:
            longest_len = len(path)
            longest_id = int(file_id)

    # 절대 경로 아닌 것들 삭제
    for entry in entries:
        file_id, path = entry.split(':', 1)
        file_id = int(file_id)
        if file_id != longest_id:
            to_delete.append(file_id)

print(f'삭제할 중복 레코드: {len(to_delete)}개')

if to_delete:
    cursor.executemany('DELETE FROM files WHERE id=?', [(i,) for i in to_delete])
    conn.commit()
    print(f'✅ {len(to_delete)}개 삭제 완료')

# 결과 확인
cursor.execute('SELECT COUNT(*) FROM files')
total = cursor.fetchone()[0]
cursor.execute('SELECT COUNT(DISTINCT filename) FROM files')
unique = cursor.fetchone()[0]

print(f'\n📊 정리 후:')
print(f'  총 레코드: {total}개')
print(f'  고유 파일: {unique}개')
print(f'  중복: {total - unique}개')

conn.close()
print('='*60)
