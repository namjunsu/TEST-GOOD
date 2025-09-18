#!/usr/bin/env python3
from perfect_rag import PerfectRAG

print('코드블록 사용 확인')
print('='*60)

rag = PerfectRAG()

# 다양한 쿼리 테스트
queries = [
    '광화문',
    '뉴스부조'
]

for query in queries:
    print(f'\n[{query}]')
    result = str(rag.answer(query, mode='asset'))
    
    # 코드블록 확인
    backtick_count = result.count('`')
    if backtick_count > 0:
        print(f'→ 백틱 {backtick_count}개 발견 (코드블록 사용)')
        # 코드블록 부분 찾기
        start = result.find('```')
        if start != -1:
            end = result.find('```', start + 3)
            if end != -1:
                print(f'   코드블록 내용 일부:')
                print(result[start:start+200])
    else:
        print('→ 일반 텍스트 형식')
        print(f'   시작: {result[:100]}')