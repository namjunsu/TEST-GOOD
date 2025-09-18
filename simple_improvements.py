#!/usr/bin/env python3
"""
간단한 개선사항 적용
"""

from pathlib import Path
import re

def apply_simple_improvements():
    """최소한의 개선사항만 적용"""

    # 1. perfect_rag.py에 에러 캐싱 방지 추가
    perfect_rag = Path("perfect_rag.py")
    content = perfect_rag.read_text()

    # answer 메서드에서 에러 응답 캐싱 방지
    # 에러 메시지가 포함된 응답은 캐싱하지 않도록 수정
    old_pattern = r"self\._manage_cache\(self\.answer_cache, cache_key, answer\)"
    new_code = """# 에러 응답은 캐싱하지 않음
            if answer and len(answer) > 50 and '❌' not in answer and 'Model path does not exist' not in answer:
                self._manage_cache(self.answer_cache, cache_key, answer)"""

    content = re.sub(old_pattern, new_code, content)

    # 모델 경로 수정
    content = content.replace(
        'models/qwen2.5-7b-instruct-q5_k_m.gguf',
        'models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'
    )

    perfect_rag.write_text(content)
    print("✅ perfect_rag.py 개선 완료")

    # 2. config.py가 있다면 수정
    config_py = Path("config.py")
    if config_py.exists():
        content = config_py.read_text()
        content = content.replace(
            'qwen2.5-7b-instruct-q5_k_m.gguf',
            'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf'
        )
        config_py.write_text(content)
        print("✅ config.py 수정 완료")

    return True


if __name__ == "__main__":
    if apply_simple_improvements():
        print("\n✅ 개선사항 적용 완료!")
        print("테스트: python3 test_answer_quality.py")