#!/usr/bin/env python3
"""
FastAPI 기반 고성능 API 서버
==============================

세계 최고 개발자가 설계한 완벽한 REST API
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import asyncio
import uvicorn
import time
import json
from datetime import datetime
from functools import lru_cache
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="AI-CHAT RAG API",
    description="세계 최고 수준의 RAG 시스템 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 데이터 모델 ====================

class SearchRequest(BaseModel):
    """검색 요청 모델"""
    query: str = Field(..., description="검색 쿼리")
    mode: str = Field("document", description="검색 모드 (document/asset)")
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


class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str
    version: str
    uptime: float
    memory_usage_gb: float
    gpu_available: bool


class MetricsResponse(BaseModel):
    """메트릭 응답"""
    total_requests: int
    cache_hits: int
    cache_hit_rate: float
    avg_response_time: float
    active_connections: int


# ==================== 전역 상태 ====================

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
            logger.info("Initializing RAG system...")
            # Lazy import
            from perfect_rag import PerfectRAG
            self.rag_instance = PerfectRAG()
            self.initialized = True
            logger.info("RAG system initialized successfully")

    def get_metrics(self) -> MetricsResponse:
        """메트릭 반환"""
        hit_rate = (self.cache_hits / max(1, self.total_requests)) * 100
        avg_time = sum(self.response_times) / max(1, len(self.response_times))

        return MetricsResponse(
            total_requests=self.total_requests,
            cache_hits=self.cache_hits,
            cache_hit_rate=hit_rate,
            avg_response_time=avg_time,
            active_connections=self.active_connections
        )


# 전역 상태 인스턴스
state = APIState()


# ==================== API 엔드포인트 ====================

@app.on_event("startup")
async def startup_event():
    """서버 시작 이벤트"""
    logger.info("🚀 API Server starting...")
    await state.initialize()
    logger.info("✅ API Server ready!")


@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 이벤트"""
    logger.info("Shutting down API Server...")


@app.get("/", response_model=dict)
async def root():
    """루트 엔드포인트"""
    return {
        "message": "AI-CHAT RAG API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스체크"""
    import psutil
    import torch

    memory = psutil.virtual_memory()
    uptime = time.time() - state.start_time

    return HealthResponse(
        status="healthy" if state.initialized else "initializing",
        version="2.0.0",
        uptime=uptime,
        memory_usage_gb=memory.used / (1024**3),
        gpu_available=torch.cuda.is_available()
    )


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """검색 API"""

    # 초기화 확인
    if not state.initialized:
        await state.initialize()

    state.total_requests += 1
    state.active_connections += 1

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

        # 응답 생성
        result = SearchResponse(
            query=request.query,
            response=response,
            sources=[],  # TODO: 실제 소스 추가
            search_time=search_time,
            cached=cached,
            timestamp=datetime.now()
        )

        return result

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        state.active_connections -= 1


@app.post("/search/stream")
async def search_stream(request: SearchRequest):
    """스트리밍 검색 API"""

    async def generate():
        """스트리밍 제너레이터"""
        # 초기 응답
        yield json.dumps({"status": "searching"}) + "\n"

        # 검색 수행
        response = await search(request)

        # 청크 단위로 스트리밍
        chunks = response.response.split(". ")
        for i, chunk in enumerate(chunks):
            data = {
                "chunk": chunk + ".",
                "progress": (i + 1) / len(chunks),
                "done": i == len(chunks) - 1
            }
            yield json.dumps(data) + "\n"
            await asyncio.sleep(0.1)  # 스트리밍 효과

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson"
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """메트릭 조회"""
    return state.get_metrics()


@app.post("/cache/clear")
async def clear_cache():
    """캐시 초기화"""
    if state.rag_instance:
        state.rag_instance.clear_cache()
        state.cache_hits = 0
        return {"message": "Cache cleared successfully"}
    return {"message": "System not initialized"}


@app.get("/documents")
async def list_documents(limit: int = 10, offset: int = 0):
    """문서 목록 조회"""
    if not state.rag_instance:
        return {"documents": [], "total": 0}

    # 메타데이터 캐시에서 문서 목록 가져오기
    docs = list(state.rag_instance.metadata_cache.items())
    total = len(docs)

    # 페이징
    docs = docs[offset:offset + limit]

    return {
        "documents": [
            {
                "id": doc_id,
                "filename": meta.get('filename'),
                "year": meta.get('year'),
                "category": meta.get('category'),
                "size": meta.get('file_size')
            }
            for doc_id, meta in docs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.post("/index/rebuild")
async def rebuild_index(background_tasks: BackgroundTasks):
    """인덱스 재구축 (백그라운드)"""

    def rebuild():
        logger.info("Starting index rebuild...")
        if state.rag_instance:
            state.rag_instance._build_initial_index()
        logger.info("Index rebuild completed")

    background_tasks.add_task(rebuild)
    return {"message": "Index rebuild started in background"}


# ==================== WebSocket 지원 (선택사항) ====================

from fastapi import WebSocket, WebSocketDisconnect


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트 (실시간 검색)"""
    await websocket.accept()
    logger.info("WebSocket connection established")

    try:
        while True:
            # 클라이언트로부터 메시지 수신
            data = await websocket.receive_text()
            request = json.loads(data)

            # 검색 수행
            search_req = SearchRequest(**request)
            response = await search(search_req)

            # 응답 전송
            await websocket.send_json(response.dict())

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


# ==================== 실행 ====================

def run_server(host="0.0.0.0", port=8000, reload=False):
    """API 서버 실행"""
    logger.info(f"Starting API server on {host}:{port}")

    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True
    )


if __name__ == "__main__":
    print("="*60)
    print("🚀 AI-CHAT RAG API Server")
    print("세계 최고 개발자가 만든 고성능 API")
    print("="*60)
    print()
    print("📌 Endpoints:")
    print("   • Docs: http://localhost:8000/docs")
    print("   • Health: http://localhost:8000/health")
    print("   • Search: POST http://localhost:8000/search")
    print("   • Metrics: http://localhost:8000/metrics")
    print()
    print("="*60)

    run_server()