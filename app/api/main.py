"""FastAPI 백엔드 서버

Health check 및 기타 API 엔드포인트 제공
"""

import sys
import os
import time
import subprocess
import base64
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

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


# ===== 유틸리티 함수 =====

def get_public_base_url(request: Request) -> str:
    """동적으로 공개 기준 URL 생성 (프록시/포워딩 환경 지원)

    우선순위:
    1. 환경변수 PUBLIC_API_BASE (수동 설정)
    2. X-Forwarded-Host / X-Forwarded-Proto 헤더 (프록시 환경)
    3. request.url (기본)

    Args:
        request: FastAPI Request 객체

    Returns:
        str: 공개 기준 URL (예: http://192.168.0.10:7860)
    """
    # 1. 환경변수 우선 (WSL/특수 환경)
    env_base = os.getenv("PUBLIC_API_BASE")
    if env_base:
        return env_base.rstrip("/")

    # 2. 프록시 헤더 확인 (nginx, cloudflare 등)
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")

    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme
        return f"{scheme}://{forwarded_host}"

    # 3. 기본 request.url 사용
    return f"{request.url.scheme}://{request.url.netloc}"


# 파일 접근 로깅 함수
def log_file_access(filename: str, action: str, query: str = ""):
    """파일 접근 로그 기록

    Args:
        filename: 파일명
        action: 액션 타입 (preview|download)
        query: 검색 질의 (선택)
    """
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "file_access.jsonl"
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "action": action,
            "query": query
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"로깅 실패: {e}")


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


@app.get("/files/preview")
def preview_file(ref: str = Query(..., description="base64 encoded file path")):
    """파일 미리보기 (보안: docs 하위만 허용)

    Args:
        ref: base64로 인코딩된 파일 경로

    Returns:
        파일 응답 (PDF/이미지 등)
    """
    try:
        # base64 디코딩
        decoded_path = base64.urlsafe_b64decode(ref).decode()
        file_path = Path(decoded_path)

        # 보안 검증: docs 하위만 허용
        if "docs" not in file_path.parts:
            log_file_access(file_path.name, "preview_denied", "")
            raise HTTPException(
                status_code=403,
                detail="문서 위치가 허용 범위 외입니다. (docs 하위만 허용)"
            )

        # 파일 존재 확인
        if not file_path.exists():
            log_file_access(file_path.name, "preview_not_found", "")
            raise HTTPException(
                status_code=404,
                detail=f"파일을 찾을 수 없습니다: {file_path.name}"
            )

        # 경로 탈출 방지 (resolve로 실제 경로 확인)
        resolved_path = file_path.resolve()
        if "docs" not in resolved_path.parts:
            log_file_access(file_path.name, "preview_denied", "")
            raise HTTPException(
                status_code=403,
                detail="경로 탐색 시도가 감지되었습니다."
            )

        # 로깅
        log_file_access(file_path.name, "preview", "")

        # 파일 반환 (inline 미리보기)
        # RFC 5987: filename*=UTF-8''encoded_name for non-ASCII filenames
        encoded_filename = quote(file_path.name)
        return FileResponse(
            path=str(resolved_path),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"파일 미리보기 실패: {str(e)}"
        )


@app.get("/files/download")
def download_file(ref: str = Query(..., description="base64 encoded file path")):
    """파일 다운로드 (보안: docs 하위만 허용)

    Args:
        ref: base64로 인코딩된 파일 경로

    Returns:
        파일 다운로드 응답
    """
    try:
        # base64 디코딩
        decoded_path = base64.urlsafe_b64decode(ref).decode()
        file_path = Path(decoded_path)

        # 보안 검증: docs 하위만 허용
        if "docs" not in file_path.parts:
            log_file_access(file_path.name, "download_denied", "")
            raise HTTPException(
                status_code=403,
                detail="문서 위치가 허용 범위 외입니다. (docs 하위만 허용)"
            )

        # 파일 존재 확인
        if not file_path.exists():
            log_file_access(file_path.name, "download_not_found", "")
            raise HTTPException(
                status_code=404,
                detail=f"파일을 찾을 수 없습니다: {file_path.name}"
            )

        # 경로 탈출 방지
        resolved_path = file_path.resolve()
        if "docs" not in resolved_path.parts:
            log_file_access(file_path.name, "download_denied", "")
            raise HTTPException(
                status_code=403,
                detail="경로 탐색 시도가 감지되었습니다."
            )

        # 로깅
        log_file_access(file_path.name, "download", "")

        # 파일 반환 (attachment 다운로드)
        # RFC 5987: filename*=UTF-8''encoded_name for non-ASCII filenames
        encoded_filename = quote(file_path.name)
        return FileResponse(
            path=str(resolved_path),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"파일 다운로드 실패: {str(e)}"
        )


@app.get("/")
def root():
    """루트 엔드포인트"""
    return {
        "message": "AI-CHAT API Server",
        "version": "1.0.0",
        "healthcheck": "/_healthz",
        "endpoints": {
            "preview": "/files/preview?ref=<base64>",
            "download": "/files/download?ref=<base64>",
            "config": "/api/config"
        }
    }


@app.get("/api/config")
def get_api_config(request: Request):
    """API 설정 반환 (Streamlit에서 동적 URL을 가져가기 위함)

    Returns:
        dict: {
            "base_url": 공개 기준 URL,
            "preview_endpoint": "/files/preview",
            "download_endpoint": "/files/download"
        }
    """
    base_url = get_public_base_url(request)
    return {
        "base_url": base_url,
        "preview_endpoint": f"{base_url}/files/preview",
        "download_endpoint": f"{base_url}/files/download"
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
