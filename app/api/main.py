"""FastAPI 백엔드 서버

Health check 및 기타 API 엔드포인트 제공
"""

import sys
import os
import time
import subprocess
import base64
import json
import ipaddress
import binascii
import mimetypes
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, StreamingResponse

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(override=True)  # .env 파일이 환경 변수를 override하도록 설정

# 중앙 설정 임포트
from app.config.settings import settings

# 로깅 설정 임포트
from app.logging.config import setup_logging, get_logger, RequestContext

# 로깅 초기화 (환경변수 기반)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_JSON = os.getenv("LOG_JSON", "false").lower() == "true"
setup_logging(
    log_dir=str(settings.LOG_DIR),
    log_level=LOG_LEVEL,
    structured=LOG_JSON
)
log = get_logger("app.api")

app = FastAPI(
    title="AI-CHAT API",
    description="RAG 시스템 백엔드 API",
    version="1.0.0"
)

# CORS 설정 (Streamlit과 통신)
# allow_origins=["*"]와 allow_credentials=True 동시 사용 시 브라우저가 쿠키/인증 헤더 차단
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# GZip 압축 (1KB 이상 응답에 적용)
app.add_middleware(GZipMiddleware, minimum_size=1024)


# Startup 이벤트
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 로그 기록"""
    log.info(
        "FastAPI server starting",
        extra={
            "version": "1.0.0",
            "log_level": LOG_LEVEL,
            "structured_logging": LOG_JSON,
            "docs_dir": str(settings.DOCS_DIR),
        }
    )


# 요청 로깅 미들웨어 (contextvars 기반 req_id/trace_id 자동 전파)
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """모든 HTTP 요청에 req_id/trace_id 자동 주입 및 로깅

    - contextvars를 통해 하위 모든 로그에 자동 전파
    - 응답 헤더에 X-Request-ID, X-Trace-ID 추가 (디버깅용)
    - 요청/응답 시작/종료 로깅 with 레이턴시
    """
    with RequestContext() as ctx:
        start = time.time()

        log.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown",
            }
        )

        try:
            response = await call_next(request)

            latency_ms = int((time.time() - start) * 1000)
            log.info(
                "Request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                }
            )

            # 응답 헤더에 req_id/trace_id 추가 (프론트엔드 디버깅용)
            response.headers["X-Request-ID"] = ctx.req_id
            response.headers["X-Trace-ID"] = ctx.trace_id

            return response

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            log.error(
                "Request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "latency_ms": latency_ms,
                },
                exc_info=True
            )
            raise


# 보안 응답 헤더 미들웨어
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """보안 응답 헤더 추가

    - X-Content-Type-Options: nosniff (MIME 스니핑 방지)
    - Referrer-Policy: no-referrer (리퍼러 정보 노출 방지)
    - X-Frame-Options: DENY (클릭재킹 방지)
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


# ===== 유틸리티 함수 =====

# 프록시 헤더 신뢰 경계 설정
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
ALLOWED_PROXY_IPS = []
proxy_ips_str = os.getenv("ALLOWED_PROXY_IPS", "")
if proxy_ips_str:
    for cidr in proxy_ips_str.split(","):
        try:
            ALLOWED_PROXY_IPS.append(ipaddress.ip_network(cidr.strip()))
        except ValueError:
            print(f"Invalid CIDR notation: {cidr}")

# 중앙 설정에서 경로 가져오기
DOCS_DIR = settings.DOCS_DIR
BM25_CANDIDATES = settings.BM25_CANDIDATES
FAISS_CANDIDATES = settings.FAISS_CANDIDATES


def _first_existing(paths: list) -> Path | None:
    """경로 리스트에서 첫 번째 존재하는 파일 반환

    Args:
        paths: 경로 리스트

    Returns:
        Path | None: 존재하는 첫 번째 경로, 없으면 None
    """
    for p in paths:
        if p and p.exists():
            return p
    return None


def _client_ip_ok(request: Request) -> bool:
    """클라이언트 IP가 허용된 프록시 IP 범위에 포함되는지 확인"""
    if not ALLOWED_PROXY_IPS:
        return False
    try:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            ip_str = forwarded_for.split(",")[0].strip()
        elif request.client:
            ip_str = request.client.host
        else:
            return False
        client_ip = ipaddress.ip_address(ip_str)
        return any(client_ip in net for net in ALLOWED_PROXY_IPS)
    except Exception:
        return False


def _decode_ref(ref: str) -> Path:
    """Base64 인코딩된 파일 경로를 안전하게 디코딩 및 검증

    Args:
        ref: urlsafe base64 인코딩된 파일 경로

    Returns:
        Path: 검증된 파일 경로 (DOCS_DIR 하위)

    Raises:
        HTTPException: 잘못된 형식이거나 허용되지 않은 경로
    """
    try:
        # urlsafe_b64의 패딩 보정 + 검증
        missing = (-len(ref)) % 4
        decoded = base64.urlsafe_b64decode(ref + ("=" * missing)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail="ref 파라미터 형식 오류") from e

    file_path = Path(decoded).resolve()

    # 경로 탈출/심볼릭 링크 방지: DOCS_DIR 하위만 허용
    try:
        if not str(file_path).startswith(str(DOCS_DIR) + os.sep):
            raise HTTPException(status_code=403, detail="허용되지 않은 경로")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=403, detail="허용되지 않은 경로") from e

    return file_path


def _guess_mime(path: Path, default: str = "application/octet-stream") -> str:
    """파일 확장자로부터 MIME 타입 자동 추측

    Args:
        path: 파일 경로
        default: 기본 MIME 타입

    Returns:
        str: MIME 타입
    """
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or default


def get_public_base_url(request: Request) -> str:
    """동적으로 공개 기준 URL 생성 (프록시/포워딩 환경 지원)

    우선순위:
    1. 환경변수 PUBLIC_API_BASE (수동 설정)
    2. X-Forwarded-Host / X-Forwarded-Proto 헤더 (프록시 환경, 신뢰 조건 필요)
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

    # 2. 프록시 헤더 확인 (신뢰 조건: TRUST_PROXY=true && 클라이언트 IP 검증)
    if TRUST_PROXY and _client_ip_ok(request):
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_host:
            forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
            return f"{forwarded_proto}://{forwarded_host}"

    # 3. 기본 request.url 사용
    return f"{request.url.scheme}://{request.url.netloc}"


# 파일 접근 로깅 함수
def log_file_access(filename: str, action: str, query: str = ""):
    """파일 접근 로그 기록 (자동 로테이션: 10MB 임계치)

    Args:
        filename: 파일명
        action: 액션 타입 (preview|download)
        query: 검색 질의 (선택)
    """
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / "file_access.jsonl"

        # 로그 로테이션: 10MB 초과 시 타임스탬프 파일로 백업
        if log_file.exists() and log_file.stat().st_size > 10 * 1024 * 1024:
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            log_file.rename(log_dir / f"file_access.{ts}.jsonl")

        entry = {
            "timestamp": datetime.now().isoformat(),
            "filename": filename,
            "action": action,
            "query": query
        }

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"로깅 실패: {e}")


@app.get("/_healthz")
def health():
    """헬스체크 엔드포인트

    Returns:
        dict: 시스템 상태 정보 (P0-4: LLM 상태 포함)
    """
    log.debug("Health check requested")

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
    """파일 미리보기 (보안: DOCS_DIR 하위만 허용)

    Args:
        ref: base64로 인코딩된 파일 경로

    Returns:
        파일 응답 (PDF/이미지 등)
    """
    file_path = _decode_ref(ref)

    if not file_path.exists():
        log.warning("File not found for preview", extra={"filename": file_path.name})
        log_file_access(file_path.name, "preview_not_found", "")
        raise HTTPException(status_code=404, detail=f"파일 없음: {file_path.name}")

    log.info("File preview requested", extra={"filename": file_path.name})
    log_file_access(file_path.name, "preview", "")

    mime_type = _guess_mime(file_path, default="application/pdf")
    encoded_filename = quote(file_path.name)

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"}
    )


@app.get("/files/download")
def download_file(ref: str = Query(..., description="base64 encoded file path")):
    """파일 다운로드 (보안: DOCS_DIR 하위만 허용)

    Args:
        ref: base64로 인코딩된 파일 경로

    Returns:
        파일 다운로드 응답
    """
    file_path = _decode_ref(ref)

    if not file_path.exists():
        log.warning("File not found for download", extra={"filename": file_path.name})
        log_file_access(file_path.name, "download_not_found", "")
        raise HTTPException(status_code=404, detail=f"파일 없음: {file_path.name}")

    log.info("File download requested", extra={"filename": file_path.name})
    log_file_access(file_path.name, "download", "")

    mime_type = _guess_mime(file_path, default="application/pdf")
    encoded_filename = quote(file_path.name)

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
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


@app.get("/metrics")
def get_metrics():
    """RAG 인덱스 메트릭 엔드포인트 (단일 진실원, SoT)

    Returns:
        dict: {
            "docstore_count": int,  # metadata.db 문서 수
            "faiss_count": int,     # FAISS 벡터 수
            "bm25_count": int,      # BM25 문서 수
            "unindexed_count": int, # docstore - max(faiss, bm25)
            "index_version": str,   # 예: "v20251030_abc123"
            "last_reindex_at": str, # ISO8601
            "ingest_status": str    # idle|running|failed
        }
    """
    log.debug("Metrics requested")

    import sqlite3
    import pickle
    import hashlib

    metrics = {
        "docstore_count": 0,
        "faiss_count": 0,
        "bm25_count": 0,
        "unindexed_count": 0,
        "index_version": "unknown",
        "last_reindex_at": "unknown",
        "ingest_status": "idle"
    }

    # 1. DocStore 카운트 (metadata.db)
    try:
        db_path = Path("metadata.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            metrics["docstore_count"] = cursor.fetchone()[0]
            conn.close()
    except Exception as e:
        print(f"DocStore 카운트 실패: {e}")

    # 2. FAISS 카운트 (다중 후보 경로 지원)
    try:
        faiss_path = _first_existing(FAISS_CANDIDATES)
        if faiss_path:
            import faiss
            index = faiss.read_index(str(faiss_path))
            metrics["faiss_count"] = index.ntotal
    except Exception as e:
        print(f"FAISS 카운트 실패: {e}")

    # 3. BM25 카운트 (다중 후보 경로 지원)
    try:
        bm25_path = _first_existing(BM25_CANDIDATES)
        if bm25_path:
            with open(bm25_path, 'rb') as f:
                bm25_data = pickle.load(f)

            if isinstance(bm25_data, dict):
                metadata = bm25_data.get('metadata', [])
            else:
                metadata = getattr(bm25_data, 'metadata', [])

            metrics["bm25_count"] = len(metadata)
    except Exception as e:
        print(f"BM25 카운트 실패: {e}")

    # 4. Unindexed 카운트 (docstore - max(faiss, bm25))
    indexed_max = max(metrics["faiss_count"], metrics["bm25_count"])
    metrics["unindexed_count"] = max(0, metrics["docstore_count"] - indexed_max)

    # 5. 인덱스 버전 (파일 수정 시각 기반)
    try:
        version_file = Path("var/index_version.txt")
        if version_file.exists():
            metrics["index_version"] = version_file.read_text().strip()
        else:
            # 버전 파일 없으면 BM25 수정 시각 기반으로 생성
            bm25_path = _first_existing(BM25_CANDIDATES)
            if bm25_path:
                mtime = bm25_path.stat().st_mtime
                timestamp = datetime.fromtimestamp(mtime).strftime("%Y%m%d%H%M%S")

                # cfg_hash (간이 버전)
                cfg_str = f"{metrics['docstore_count']}_{metrics['bm25_count']}"
                cfg_hash = hashlib.md5(cfg_str.encode()).hexdigest()[:6]

                metrics["index_version"] = f"v{timestamp}_{cfg_hash}"
    except Exception as e:
        print(f"인덱스 버전 확인 실패: {e}")

    # 6. 최근 재색인 시각
    try:
        reindex_log = Path("var/last_reindex.txt")
        if reindex_log.exists():
            metrics["last_reindex_at"] = reindex_log.read_text().strip()
        else:
            # 로그 없으면 BM25 수정 시각 사용
            bm25_path = _first_existing(BM25_CANDIDATES)
            if bm25_path:
                mtime = bm25_path.stat().st_mtime
                metrics["last_reindex_at"] = datetime.fromtimestamp(mtime).isoformat()
    except Exception as e:
        print(f"재색인 시각 확인 실패: {e}")

    # 7. 인제스트 상태
    try:
        status_file = Path("var/ingest_status.txt")
        if status_file.exists():
            status = status_file.read_text().strip()
            if status in ["idle", "running", "failed"]:
                metrics["ingest_status"] = status
    except Exception as e:
        print(f"인제스트 상태 확인 실패: {e}")

    # 8. 코드 인덱스 통계 (model_codes 테이블)
    try:
        db_path = Path("metadata.db")
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 전체 레코드 수
            cursor.execute("SELECT COUNT(*) FROM model_codes")
            metrics["code_index_total"] = cursor.fetchone()[0]

            # 고유 norm_code 수
            cursor.execute("SELECT COUNT(DISTINCT norm_code) FROM model_codes")
            metrics["code_index_unique"] = cursor.fetchone()[0]

            conn.close()
    except Exception as e:
        print(f"코드 인덱스 통계 실패: {e}")
        metrics["code_index_total"] = 0
        metrics["code_index_unique"] = 0

    # 8-1. [PATCH 2] 인덱스 위생 메트릭
    try:
        # 물리 파일 수 (fs_file_count)
        fs_count = 0
        docs_path = settings.DOCS_DIR
        if docs_path.exists():
            for root, _, files in os.walk(docs_path):
                fs_count += sum(1 for f in files if f.lower().endswith(('.pdf', '.txt')))

        metrics["fs_file_count"] = fs_count

        # 검색 인덱스 파일 수 (index_file_count)
        index_count = 0
        stale_count = 0
        index_db_path = Path("everything_index.db")
        if index_db_path.exists():
            conn = sqlite3.connect(str(index_db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM files")
            index_count = cursor.fetchone()[0]

            # stale 항목 계산: 인덱스에는 있지만 디스크에는 없는 파일
            cursor.execute("SELECT filename, path FROM files")
            rows = cursor.fetchall()
            fs_names = set()
            for root, _, files in os.walk(docs_path):
                for f in files:
                    if f.lower().endswith(('.pdf', '.txt')):
                        fs_names.add(f)

            for filename, path in rows:
                exists = os.path.exists(path) if path and os.path.isabs(path) else (filename in fs_names)
                if not exists:
                    stale_count += 1

            conn.close()

        metrics["index_file_count"] = index_count
        metrics["stale_index_entries"] = stale_count

        # 마지막 전체 재색인 타임스탬프
        last_reindex_file = Path("var/last_full_reindex.txt")
        if last_reindex_file.exists():
            metrics["last_full_reindex_ts"] = last_reindex_file.read_text().strip()
        else:
            metrics["last_full_reindex_ts"] = "unknown"

    except Exception as e:
        print(f"인덱스 위생 메트릭 실패: {e}")
        metrics["fs_file_count"] = 0
        metrics["index_file_count"] = 0
        metrics["stale_index_entries"] = 0
        metrics["last_full_reindex_ts"] = "unknown"

    # 8-2. [ALERTS] 인덱스 위생 임계치 평가
    try:
        from app.alerts import send_warning

        threshold_gap = 5
        fs_count = metrics.get("fs_file_count", 0)
        idx_count = metrics.get("index_file_count", 0)
        stale = metrics.get("stale_index_entries", 0)

        # 임계치 초과 시 알림
        if stale > 0 or abs(fs_count - idx_count) > threshold_gap:
            send_warning("인덱스 정합성 경고", {
                "fs_file_count": fs_count,
                "index_file_count": idx_count,
                "stale_index_entries": stale,
                "threshold_gap": threshold_gap
            })
    except Exception as e:
        print(f"알림 전송 실패: {e}")

    # 9. 코드 검색 메트릭 (런타임)
    try:
        from app.rag.metrics_collector import get_metrics_collector
        code_metrics = get_metrics_collector().get_metrics()
        metrics.update(code_metrics)
    except Exception as e:
        print(f"코드 검색 메트릭 조회 실패: {e}")
        # 기본값 설정
        metrics.update({
            "code_queries_total": 0,
            "exact_match_hits_total": 0,
            "exact_match_hit_rate": 0.0,
            "stage0_candidates_last": 0,
            "stage1_candidates_last": 0,
            "rrf_fusion_used_total": 0,
            "retrieval_latency_ms_p50": 0,
            "retrieval_latency_ms_p95": 0,
        })

    # 10. Retriever 실시간 메트릭 (v2.0 추가)
    try:
        # rag_pipeline이 글로벌 변수로 있는지 확인
        import sys
        if 'rag_pipeline' in globals():
            pipeline = globals()['rag_pipeline']
            if hasattr(pipeline, 'retriever') and hasattr(pipeline.retriever, 'get_metrics'):
                retriever_metrics = pipeline.retriever.get_metrics()
                metrics["retriever_runtime"] = retriever_metrics
                log.debug(f"Retriever metrics added: {retriever_metrics}")
    except Exception as e:
        print(f"Retriever 메트릭 조회 실패: {e}")

    return metrics


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
