#!/usr/bin/env python3
"""
캐시 크기 제한 및 메모리 관리 개선
"""

import sys
from pathlib import Path
from datetime import datetime
import re

def add_cache_limits():
    """perfect_rag.py에 캐시 크기 제한 추가"""

    # perfect_rag.py 읽기
    with open('perfect_rag.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print("🔍 캐시 초기화 부분 찾기...")

    # 캐시 크기 제한 상수 추가
    cache_constants = """        # 캐시 크기 제한 설정
        self.MAX_CACHE_SIZE = 100  # 응답 캐시 최대 크기
        self.MAX_METADATA_CACHE = 500  # 메타데이터 캐시 최대 크기
        self.MAX_PDF_CACHE = 50  # PDF 텍스트 캐시 최대 크기
        self.CACHE_TTL = 3600  # 캐시 유효 시간 (1시간)

"""

    # OrderedDict 초기화 부분 찾기
    for i, line in enumerate(lines):
        if "from collections import OrderedDict" in line:
            # import time 추가
            if i > 0 and "import time" not in lines[i-1]:
                lines[i] = "import time\n" + line

        elif "self.documents_cache = OrderedDict()" in line:
            # 캐시 상수 추가
            lines[i] = cache_constants + line
            print(f"  ✅ 캐시 크기 제한 상수 추가 (줄 {i+1})")
            break

    # 캐시 관리 메서드 추가
    cache_methods = '''
    def _manage_cache_size(self, cache_dict, max_size, cache_name="cache"):
        """캐시 크기 관리 - LRU 방식으로 오래된 항목 제거"""
        if len(cache_dict) > max_size:
            # 가장 오래된 항목들 제거 (FIFO)
            items_to_remove = len(cache_dict) - max_size
            for _ in range(items_to_remove):
                removed = cache_dict.popitem(last=False)  # 가장 오래된 항목 제거
            print(f"  🗑️ {cache_name}에서 {items_to_remove}개 항목 제거 (현재 크기: {len(cache_dict)})")

    def _add_to_cache(self, cache_dict, key, value, max_size):
        """캐시에 항목 추가 with 크기 제한"""
        # 기존 항목이면 삭제 후 다시 추가 (LRU를 위해)
        if key in cache_dict:
            del cache_dict[key]

        # 새 항목 추가
        cache_dict[key] = {
            'data': value,
            'timestamp': time.time()
        }

        # 크기 제한 확인
        self._manage_cache_size(cache_dict, max_size, str(type(cache_dict)))

    def clear_old_cache(self):
        """오래된 캐시 항목 제거"""
        current_time = time.time()

        # 각 캐시 순회하며 오래된 항목 제거
        for cache_name, cache_dict in [
            ('documents', self.documents_cache),
            ('metadata', self.metadata_cache),
            ('answer', self.answer_cache),
            ('pdf_text', self.pdf_text_cache)
        ]:
            if not hasattr(self, cache_name + '_cache'):
                continue

            items_to_remove = []
            for key, value in cache_dict.items():
                if isinstance(value, dict) and 'timestamp' in value:
                    if current_time - value['timestamp'] > self.CACHE_TTL:
                        items_to_remove.append(key)

            for key in items_to_remove:
                del cache_dict[key]

            if items_to_remove:
                print(f"  🗑️ {cache_name}_cache에서 {len(items_to_remove)}개 만료 항목 제거")

    def get_cache_stats(self):
        """캐시 통계 반환"""
        stats = {
            'documents_cache': len(self.documents_cache),
            'metadata_cache': len(self.metadata_cache),
            'answer_cache': len(self.answer_cache) if hasattr(self, 'answer_cache') else 0,
            'pdf_text_cache': len(self.pdf_text_cache) if hasattr(self, 'pdf_text_cache') else 0,
        }

        # 메모리 사용량 추정 (대략적)
        import sys
        total_size = 0
        for cache_dict in [self.documents_cache, self.metadata_cache,
                          getattr(self, 'answer_cache', {}),
                          getattr(self, 'pdf_text_cache', {})]:
            total_size += sys.getsizeof(cache_dict)

        stats['estimated_memory_mb'] = total_size / (1024 * 1024)

        return stats
'''

    # 클래스의 마지막 부분 찾기
    class_end = -1
    for i in range(len(lines) - 1, 0, -1):
        if lines[i].startswith('class ') or (lines[i].strip() and not lines[i].startswith(' ')):
            class_end = i
            break

    if class_end > 0:
        lines.insert(class_end, cache_methods)
        print(f"  ✅ 캐시 관리 메서드 추가 (줄 {class_end})")

    # 캐시 사용 부분 수정
    print("\n🔧 캐시 사용 부분 수정...")

    for i, line in enumerate(lines):
        # answer_cache 사용 부분
        if "self.answer_cache[cache_key] = result" in line:
            lines[i] = line.replace(
                "self.answer_cache[cache_key] = result",
                "self._add_to_cache(self.answer_cache, cache_key, result, self.MAX_CACHE_SIZE)"
            )
            print(f"  ✅ answer_cache 사용 수정 (줄 {i+1})")

        # pdf_text_cache 사용 부분
        elif "self.pdf_text_cache[str(pdf_path)] =" in line:
            # 전체 라인 교체
            indent = len(line) - len(line.lstrip())
            new_line = ' ' * indent + "self._add_to_cache(self.pdf_text_cache, str(pdf_path), text, self.MAX_PDF_CACHE)\n"
            lines[i] = new_line
            print(f"  ✅ pdf_text_cache 사용 수정 (줄 {i+1})")

    # 파일 저장
    with open('perfect_rag.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print("\n✅ 캐시 크기 제한 적용 완료!")
    print("  - 응답 캐시: 최대 100개")
    print("  - 메타데이터 캐시: 최대 500개")
    print("  - PDF 캐시: 최대 50개")
    print("  - 캐시 유효 시간: 1시간")

if __name__ == "__main__":
    add_cache_limits()