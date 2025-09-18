#!/usr/bin/env python3
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

    print("\nLlama 로딩 시도...")

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
