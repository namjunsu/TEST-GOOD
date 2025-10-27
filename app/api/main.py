"""FastAPI 백엔드 서버

Health check 및 기타 API 엔드포인트 제공
"""

import sys
import os
import time
import subprocess
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI-CHAT API",
    description="RAG 시스템 백엔드 API",
    version="1.0.0"
)

# CORS 설정 (Streamlit과 통신)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/_healthz")
def health():
    """헬스체크 엔드포인트

    Returns:
        dict: 시스템 상태 정보 (P0-4: LLM 상태 포함)
    """
    # Git commit 정보
    commit = os.getenv("GIT_COMMIT", "unknown")
    if commit == "unknown":
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(__file__),
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except:
            pass

    # LLM 상태 체크
    llm_status = {
        "llm_loaded": False,
        "llm_backend": None,
        "model": None,
        "import_ok": False
    }

    try:
        import llama_cpp
        llm_status["import_ok"] = True
        llm_status["llm_backend"] = "llama.cpp"
        llm_status["llama_cpp_version"] = llama_cpp.__version__

        try:
            from config import QWEN_MODEL_PATH
            from pathlib import Path
            llm_status["model"] = Path(QWEN_MODEL_PATH).name
        except:
            pass
    except:
        pass

    return {
        "status": "healthy",
        "python": sys.executable,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "commit": commit,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(time.time()),
        **llm_status
    }


@app.get("/")
def root():
    """루트 엔드포인트"""
    return {
        "message": "AI-CHAT API Server",
        "version": "1.0.0",
        "healthcheck": "/_healthz"
    }


@app.get("/_debug/llm")
def debug_llm():
    """LLM 로딩 디버그 엔드포인트"""
    import sys
    import traceback

    result = {
        "python_executable": sys.executable,
        "sys_path": sys.path[:5],  # 처음 5개만
        "llama_cpp_import": None,
        "llama_cpp_location": None,
        "llama_cpp_version": None,
        "qwen_llm_import": None,
        "qwen_init": None,
        "error": None,
        "traceback": None
    }

    # 1. llama_cpp 임포트 테스트
    try:
        import llama_cpp
        result["llama_cpp_import"] = "SUCCESS"
        result["llama_cpp_location"] = llama_cpp.__file__
        result["llama_cpp_version"] = llama_cpp.__version__
    except Exception as e:
        result["llama_cpp_import"] = "FAILED"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        return result

    # 2. QwenLLM 임포트 테스트
    try:
        from rag_system.qwen_llm import QwenLLM
        result["qwen_llm_import"] = "SUCCESS"
    except Exception as e:
        result["qwen_llm_import"] = "FAILED"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        return result

    # 3. QwenLLM 초기화 테스트 (실제 모델 로드는 하지 않음)
    try:
        from config import QWEN_MODEL_PATH
        # 초기화만 테스트 (모델 로드는 시간이 오래 걸리므로 건너뜀)
        result["qwen_init"] = f"Model path: {QWEN_MODEL_PATH}"
    except Exception as e:
        result["qwen_init"] = "FAILED"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
