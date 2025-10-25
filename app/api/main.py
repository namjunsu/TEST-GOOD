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
        dict: 시스템 상태 정보
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

    return {
        "status": "healthy",
        "python": sys.executable,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "commit": commit,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(time.time()),
    }


@app.get("/")
def root():
    """루트 엔드포인트"""
    return {
        "message": "AI-CHAT API Server",
        "version": "1.0.0",
        "healthcheck": "/_healthz"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
