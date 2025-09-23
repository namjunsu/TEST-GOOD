#!/usr/bin/env python3
"""
FastAPI 기반 고성능 API 서버 V2
=================================

프로덕션 레벨 로깅 및 에러 핸들링 적용
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import asyncio
import uvicorn
import time
import json
from datetime import datetime
from functools import lru_cache
import uuid
from contextlib import asynccontextmanager

# 로깅 시스템 임포트
from logger_config import (
    get_logger,
    api_logger,
    search_logger,
    perf_logger,
    log_exception
)

# 로거 설정
logger = get_logger(__name__)

# ==================== 앱 생명주기 관리 ====================

class APIState:
    """API 서버 상태 관리"""

    def __init__(self):
        self.rag_instance = None
        self.start_time = time.time()
        self.total_requests = 0
        self.cache_hits = 0
        self.response_times = []
        self.active_connections = 0
        self.initialized = False

    async def initialize(self):
        """RAG 시스템 비동기 초기화"""
        if not self.initialized:
            start_time = time.time()
            logger.info("Initializing RAG system...")

            try:
                # Lazy import
                from perfect_rag import PerfectRAG
                self.rag_instance = PerfectRAG()
                self.initialized = True

                load_time = time.time() - start_time
                perf_logger.log_model_loading(
                    model_name="PerfectRAG",
                    load_time_s=load_time,
                    memory_gb=8.0  # 예상 메모리
                )
                logger.info(f"RAG system initialized in {load_time:.2f}s")

            except Exception as e:
                log_exception(logger, e, {'operation': 'initialize_rag'})
                raise

    def get_metrics(self) -> Dict[str, Any]:
        """메트릭 반환"""
        hit_rate = (self.cache_hits / max(1, self.total_requests)) * 100
        avg_time = sum(self.response_times[-100:]) / max(1, len(self.response_times[-100:]))

        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(hit_rate, 2),
            "avg_response_time_ms": round(avg_time * 1000, 2),
            "active_connections": self.active_connections,
            "uptime_seconds": round(time.time() - self.start_time, 2)
        }

# 전역 상태 인스턴스
state = APIState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작
    logger.info("🚀 API Server starting...")
    await state.initialize()
    logger.info("✅ API Server ready!")

    yield

    # 종료
    logger.info("Shutting down API Server...")
    # 정리 작업
    if state.rag_instance:
        logger.info("Cleaning up RAG instance...")

# FastAPI 앱 생성
app = FastAPI(
    title="AI-CHAT RAG API",
    description="프로덕션 레벨 RAG 시스템 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 미들웨어 ====================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """요청/응답 로깅 미들웨어"""
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # 요청 로깅
    api_logger.info(
        f"Request started: {request.method} {request.url.path}",
        extra={'context': {
            'request_id': request_id,
            'client': request.client.host if request.client else None,
            'user_agent': request.headers.get('user-agent'),
        }}
    )

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        # 응답 로깅
        perf_logger.log_api_request(
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=process_time * 1000,
            request_id=request_id
        )

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)
        return response

    except Exception as e:
        process_time = time.time() - start_time
        log_exception(api_logger, e, {
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path
        })
        raise

# ==================== 예외 처리 ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """검증 오류 처리"""
    api_logger.warning(
        f"Validation error: {exc.errors()}",
        extra={'context': {'path': request.url.path}}
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외 처리"""
    api_logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={'context': {'path': request.url.path}}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """전역 예외 처리"""
    request_id = str(uuid.uuid4())
    log_exception(api_logger, exc, {
        'request_id': request_id,
        'path': request.url.path
    })
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
            "message": "An unexpected error occurred. Please try again later."
        }
    )

# ==================== 데이터 모델 ====================

class SearchRequest(BaseModel):
    """검색 요청 모델"""
    query: str = Field(..., description="검색 쿼리", min_length=1, max_length=500)
    mode: str = Field("document", description="검색 모드", pattern="^(document|asset)$")
    top_k: int = Field(5, ge=1, le=20, description="반환할 결과 수")
    use_cache: bool = Field(True, description="캐시 사용 여부")
    stream: bool = Field(False, description="스트리밍 응답 여부")

class SearchResponse(BaseModel):
    """검색 응답 모델"""
    query: str
    response: str
    sources: List[Dict[str, Any]]
    search_time: float
    cached: bool
    timestamp: datetime
    request_id: Optional[str] = None

class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str
    version: str
    uptime: float
    memory_usage_gb: float
    gpu_available: bool
    checks: Dict[str, bool]

# ==================== API 엔드포인트 ====================

@app.get("/", response_model=dict)
async def root():
    """루트 엔드포인트"""
    return {
        "message": "AI-CHAT RAG API V2",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스체크"""
    import psutil
    import torch

    memory = psutil.virtual_memory()
    uptime = time.time() - state.start_time

    # 상태 체크
    checks = {
        "rag_initialized": state.initialized,
        "model_loaded": state.rag_instance is not None,
        "cache_available": True,
        "database": True  # TODO: 실제 DB 체크
    }

    return HealthResponse(
        status="healthy" if all(checks.values()) else "degraded",
        version="2.0.0",
        uptime=uptime,
        memory_usage_gb=memory.used / (1024**3),
        gpu_available=torch.cuda.is_available(),
        checks=checks
    )

@app.get("/health/ready")
async def readiness_check():
    """준비 상태 체크"""
    if not state.initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )
    return {"status": "ready"}

@app.get("/health/live")
async def liveness_check():
    """생존 체크"""
    return {"status": "alive"}

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, req: Request):
    """검색 API"""

    # 초기화 확인
    if not state.initialized:
        await state.initialize()

    request_id = req.headers.get("X-Request-ID", str(uuid.uuid4()))
    state.total_requests += 1
    state.active_connections += 1

    search_logger.info(
        f"Search request: mode={request.mode}, top_k={request.top_k}",
        extra={'context': {
            'request_id': request_id,
            'query_length': len(request.query)
        }}
    )

    try:
        start_time = time.time()

        # 동기 함수를 비동기로 실행
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            state.rag_instance.search_and_generate,
            request.query,
            request.mode,
            request.top_k,
            request.use_cache
        )

        search_time = time.time() - start_time
        state.response_times.append(search_time)

        # 캐시 히트 확인
        cached = search_time < 0.5
        if cached:
            state.cache_hits += 1

        # 성능 로깅
        perf_logger.log_search_performance(
            query=request.query,
            mode=request.mode,
            results=request.top_k,
            duration_ms=search_time * 1000,
            cached=cached
        )

        # 응답 생성
        result = SearchResponse(
            query=request.query,
            response=response,
            sources=[],  # TODO: 실제 소스 추가
            search_time=search_time,
            cached=cached,
            timestamp=datetime.now(),
            request_id=request_id
        )

        return result

    except Exception as e:
        log_exception(search_logger, e, {
            'request_id': request_id,
            'query': request.query
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )

    finally:
        state.active_connections -= 1

@app.post("/search/stream")
async def search_stream(request: SearchRequest):
    """스트리밍 검색 API"""

    async def generate():
        """스트리밍 제너레이터"""
        request_id = str(uuid.uuid4())

        try:
            # 초기 응답
            yield json.dumps({
                "status": "searching",
                "request_id": request_id
            }) + "\n"

            # 검색 수행
            response = await search(request, Request(
                {"type": "http", "headers": [(b"x-request-id", request_id.encode())]}
            ))

            # 청크 단위로 스트리밍
            chunks = response.response.split(". ")
            for i, chunk in enumerate(chunks):
                data = {
                    "chunk": chunk + ".",
                    "progress": (i + 1) / len(chunks),
                    "done": i == len(chunks) - 1,
                    "request_id": request_id
                }
                yield json.dumps(data) + "\n"
                await asyncio.sleep(0.05)  # 스트리밍 효과

        except Exception as e:
            error_data = {
                "error": str(e),
                "request_id": request_id
            }
            yield json.dumps(error_data) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson"
    )

@app.get("/metrics")
async def get_metrics():
    """메트릭 조회"""
    return state.get_metrics()

@app.post("/cache/clear")
async def clear_cache():
    """캐시 초기화"""
    if state.rag_instance:
        state.rag_instance.clear_cache()
        state.cache_hits = 0
        logger.info("Cache cleared successfully")
        return {"message": "Cache cleared successfully"}
    return {"message": "System not initialized"}

# ==================== WebSocket 지원 ====================

from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트"""
    await websocket.accept()
    connection_id = str(uuid.uuid4())

    logger.info(f"WebSocket connection established: {connection_id}")

    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            request = json.loads(data)

            # 검색 수행
            search_req = SearchRequest(**request)
            response = await search(
                search_req,
                Request({"type": "websocket", "headers": []})
            )

            # 응답 전송
            await websocket.send_json(response.dict())

    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed: {connection_id}")
    except Exception as e:
        log_exception(logger, e, {'connection_id': connection_id})
        await websocket.close()

# ==================== 실행 ====================

def run_server(host="0.0.0.0", port=8000, reload=False):
    """API 서버 실행"""
    logger.info(f"Starting API server on {host}:{port}")

    uvicorn.run(
        "api_server_v2:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=False  # 커스텀 로깅 사용
    )

if __name__ == "__main__":
    print("="*60)
    print("🚀 AI-CHAT RAG API Server V2")
    print("프로덕션 레벨 로깅 시스템 적용")
    print("="*60)
    print()
    print("📌 Endpoints:")
    print("   • Docs: http://localhost:8000/docs")
    print("   • Health: http://localhost:8000/health")
    print("   • Metrics: http://localhost:8000/metrics")
    print()
    print("="*60)

    run_server()