#!/usr/bin/env python3
from perfect_rag import PerfectRAG

print('실제 출력 형식 비교')
print('='*60)

rag = PerfectRAG()

# 두 가지 위치 비교
locations = ['중계차', '광화문 스튜디오', '대형스튜디오']

for location in locations:
    query = f'{location}'
    print(f'\n[{location}]')
    print('-'*60)
    
    result = str(rag.answer(query, mode='asset'))
    
    # 처음 800자 출력
    print(result[:800])
    
    # 코드블록 확인
    if '```' in result:
        print(f'\n→ 코드블록 사용됨 (검은 배경) - 백틱 {result.count("```")}개')
    else:
        print('\n→ 일반 텍스트 형식')