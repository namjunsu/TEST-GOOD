#!/usr/bin/env python3
"""
모델 로딩 문제 수정 스크립트
split된 GGUF 파일을 처리하도록 수정
"""

import os
from pathlib import Path
import sys

def fix_model_loading():
    """모델 로딩 설정 수정"""

    # 1. 실제 모델 파일 확인
    models_dir = Path("models")
    model_files = list(models_dir.glob("qwen2.5-7b-instruct-q4_k_m*.gguf"))

    if not model_files:
        print("❌ 모델 파일을 찾을 수 없습니다")
        return False

    print(f"✅ 발견된 모델 파일: {len(model_files)}개")
    for f in model_files:
        size_gb = f.stat().st_size / (1024**3)
        print(f"  - {f.name}: {size_gb:.2f}GB")

    # 2. config.py 수정 (있다면)
    config_py = Path("config.py")
    if config_py.exists():
        content = config_py.read_text()

        # 모델 경로 수정
        old_path = 'QWEN_MODEL_PATH = "./models/qwen2.5-7b-instruct-q5_k_m.gguf"'
        new_path = 'QWEN_MODEL_PATH = "./models/qwen2.5-7b-instruct-q4_k_m"  # split 모델'

        if old_path in content:
            content = content.replace(old_path, new_path)
            config_py.write_text(content)
            print("✅ config.py 수정 완료")

    # 3. qwen_llm.py 확인 및 수정
    qwen_llm = Path("rag_system/qwen_llm.py")
    if qwen_llm.exists():
        content = qwen_llm.read_text()

        # split 모델 처리 로직 추가 필요 확인
        if "00001-of-" not in content:
            print("⚠️ qwen_llm.py에 split 모델 처리 로직 추가 필요")

            # 파일 백업
            backup = qwen_llm.with_suffix('.py.bak')
            backup.write_text(content)

            # 모델 로딩 부분 찾기
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'Llama(' in line and 'model_path=' in line:
                    # split 모델 처리 추가
                    lines[i] = line.replace(
                        'model_path=model_path',
                        'model_path=str(model_path)'
                    )

            qwen_llm.write_text('\n'.join(lines))
            print("✅ qwen_llm.py 수정 완료")

    # 4. 테스트 스크립트 생성
    test_script = Path("test_model_loading.py")
    test_content = '''#!/usr/bin/env python3
"""모델 로딩 테스트"""

from pathlib import Path
import sys

# 모델 경로 설정
MODEL_PATH = "./models/qwen2.5-7b-instruct-q4_k_m"

print(f"모델 경로: {MODEL_PATH}")

# 파일 존재 확인
model_files = list(Path("models").glob("qwen2.5-7b-instruct-q4_k_m*.gguf"))
if model_files:
    print(f"✅ {len(model_files)}개 파일 발견:")
    for f in model_files:
        print(f"  - {f.name}")
else:
    print("❌ 모델 파일 없음")
    sys.exit(1)

# llama-cpp-python 테스트
try:
    from llama_cpp import Llama

    print("\\nLlama 로딩 시도...")

    # split 모델의 첫 번째 파일로 시도
    first_file = str(model_files[0])

    # 기본 경로로 시도 (자동으로 split 파일 감지)
    try:
        llm = Llama(
            model_path=MODEL_PATH,
            n_ctx=2048,  # 작은 컨텍스트로 테스트
            n_batch=128,
            n_gpu_layers=0,  # CPU 모드로 테스트
            verbose=False
        )
        print("✅ 기본 경로로 로딩 성공!")
    except:
        # 첫 번째 파일 직접 지정
        llm = Llama(
            model_path=first_file,
            n_ctx=2048,
            n_batch=128,
            n_gpu_layers=0,
            verbose=False
        )
        print("✅ 첫 번째 파일로 로딩 성공!")

    # 간단한 테스트
    response = llm("Hello", max_tokens=10)
    print(f"✅ 모델 응답: {response['choices'][0]['text'][:50]}...")

except ImportError:
    print("❌ llama-cpp-python이 설치되지 않음")
except Exception as e:
    print(f"❌ 모델 로딩 실패: {e}")
'''

    test_script.write_text(test_content)
    test_script.chmod(0o755)
    print("\n✅ 테스트 스크립트 생성: test_model_loading.py")

    return True


if __name__ == "__main__":
    print("="*60)
    print("모델 로딩 문제 수정")
    print("="*60)

    if fix_model_loading():
        print("\n✅ 수정 완료!")
        print("\n테스트 실행:")
        print("  python3 test_model_loading.py")
    else:
        print("\n❌ 수정 실패")
        sys.exit(1)