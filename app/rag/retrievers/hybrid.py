"""하이브리드 검색 엔진 (BM25 인덱스 기반)

BM25Store를 사용하여 전체 텍스트 기반 검색 수행
"""

import os
import re
import yaml
from pathlib import Path
from typing import List, Dict, Any
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB
from app.rag.query_parser import QueryParser
from rag_system.bm25_store import BM25Store  # 인덱서와 동일 모듈 사용

logger = get_logger(__name__)


class HybridRetriever:
    """하이브리드 검색 엔진 (BM25 인덱스 기반)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 BM25Store를 사용해 전체 텍스트 기반 검색을 수행합니다.
    """

    def __init__(self):
        """초기화 - BM25Store 및 MetadataDB 로드"""
        try:
            # 검색 백엔드 설정
            self.use_bm25 = os.getenv("RETRIEVER_BACKEND", "bm25").lower() == "bm25"

            # MetadataDB 초기화 (필터링용)
            self.metadata_db = MetadataDB()
            self.known_drafters = self.metadata_db.list_unique_drafters()
            self.parser = QueryParser(self.known_drafters)

            # BM25Store 초기화
            self.bm25 = None
            if self.use_bm25:
                index_path = os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
                logger.info(f"🔍 DEBUG: BM25_INDEX_PATH={index_path} (exists={os.path.exists(index_path)})")
                self.bm25 = BM25Store(index_path=index_path)
                logger.info(f"✅ HybridRetriever 초기화 완료 (BM25 백엔드, {len(self.bm25.documents)}개 문서, path={self.bm25.index_path})")
            else:
                logger.info("✅ HybridRetriever 초기화 완료 (MetadataDB 폴백 모드)")

            # 인덱스 파일 mtime 추적 (자동 재로드용)
            self._last_index_mtime = self._get_index_mtime()

            # DOC_ANCHORED 키워드 로드 (YAML 외부화)
            self._load_router_keywords()

        except Exception as e:
            logger.error(f"❌ HybridRetriever 초기화 실패: {e}")
            raise

    def _load_router_keywords(self):
        """라우터 키워드 YAML 로드 (운영 중 수정 가능)"""
        try:
            config_path = Path("config/router_keywords.yaml")
            if config_path.exists():
                config = yaml.safe_load(config_path.read_text())
                allow_patterns = config["doc_anchored"]["allow"]
                self.device_pattern = "|".join(allow_patterns)
                logger.info(f"✅ DOC_ANCHORED 키워드 로드 완료 ({len(allow_patterns)}개 패턴)")
            else:
                # 폴백: 하드코딩 패턴 사용
                self.device_pattern = (
                    r"\bHRD[-\s]?\d{3,4}\b|DVR|NVR|"
                    r"Hanwha(?:\s+(?:Techwin|Vision))?|"
                    r"보존용|녹화용|교체|노후|장비|카메라|모니터"
                )
                logger.warning("⚠️ router_keywords.yaml 없음, 폴백 패턴 사용")
        except Exception as e:
            logger.error(f"❌ 키워드 로드 실패: {e}, 폴백 패턴 사용")
            self.device_pattern = (
                r"\bHRD[-\s]?\d{3,4}\b|DVR|NVR|"
                r"Hanwha(?:\s+(?:Techwin|Vision))?|"
                r"보존용|녹화용|교체|노후|장비|카메라|모니터"
            )

    def _get_index_mtime(self) -> float:
        """인덱스 파일의 수정 시간 반환"""
        if not self.use_bm25:
            return 0.0
        index_path = os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
        return os.path.getmtime(index_path) if os.path.exists(index_path) else 0.0

    def _reload_if_index_rotated(self):
        """인덱스 파일이 갱신되면 자동 리로드"""
        if not self.use_bm25:
            return

        current_mtime = self._get_index_mtime()
        if current_mtime > self._last_index_mtime:
            logger.info("🔄 인덱스 파일 갱신 감지, 재로드 중...")
            index_path = os.getenv("BM25_INDEX_PATH", "var/index/bm25_index.pkl")
            self.bm25 = BM25Store(index_path=index_path)
            self._last_index_mtime = current_mtime
            logger.info(f"✅ 인덱스 재로드 완료 ({len(self.bm25.documents)}개 문서)")

    def _calculate_relevance_score(self, query: str, doc: Dict[str, Any]) -> float:
        """쿼리와 문서 간 relevance 스코어 계산 (BM25 유사)

        Args:
            query: 검색 질의
            doc: 문서 딕셔너리 (filename, text_preview 포함)

        Returns:
            0.0~1.0 범위의 relevance 스코어
        """
        # 쿼리 토큰화 (공백 + 특수문자 제거)
        query_tokens = set(re.findall(r'\w+', query.lower()))
        if not query_tokens:
            return 0.5  # 토큰 없으면 중립 스코어

        # 문서 텍스트 준비 (filename + text_preview)
        doc_text = (
            (doc.get('filename') or '') + ' ' +
            (doc.get('text_preview') or '') + ' ' +
            (doc.get('drafter') or '')
        ).lower()

        # 매칭된 토큰 수 계산
        matched_tokens = sum(1 for token in query_tokens if token in doc_text)

        # 기본 스코어: 매칭률
        match_ratio = matched_tokens / len(query_tokens)

        # 보너스: 완전 일치하는 구문이 있으면 가산점
        if query.lower() in doc_text:
            match_ratio = min(1.0, match_ratio + 0.3)

        # 페널티: 문서가 너무 짧으면 감점 (신뢰도 저하)
        text_len = len(doc.get('text_preview') or '')
        if text_len < 100:
            match_ratio *= 0.7

        return max(0.0, min(1.0, match_ratio))

    def search(self, query: str, top_k: int, mode: str = "chat", selected_filename: Optional[str] = None) -> List[Dict[str, Any]]:
        """검색 수행

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            mode: 검색 모드 ("chat", "doc_anchored" 등)
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)

        Returns:
            정규화된 검색 결과 리스트 (score_stats 속성 포함):
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict
                }, ...
            ]
        """
        try:
            # 인덱스 갱신 체크
            self._reload_if_index_rotated()

            # BM25 백엔드 사용
            if self.use_bm25 and self.bm25:
                # DOC_ANCHORED 모드: 넉넉하게 검색 후 필터링
                search_k = 50 if mode.lower() == "doc_anchored" else top_k

                # BM25Store에서 직접 검색
                bm25_results = self.bm25.search(query, top_k=search_k)

                # BM25 결과를 RAGPipeline 형식으로 변환 (doc_id, snippet 필드 추가)
                converted_results = []
                for result in bm25_results:
                    converted_results.append({
                        "doc_id": result.get("filename", "unknown"),
                        "snippet": result.get("content", "")[:800],  # content -> snippet
                        "score": result.get("score", 0.0),
                        "page": 1,
                        "filename": result.get("filename"),  # 원본 filename 유지
                        "file_path": result.get("path"),  # path -> file_path
                        "meta": {
                            "filename": result.get("filename"),
                            "date": result.get("date"),
                            "drafter": result.get("drafter"),
                            "category": result.get("category"),
                        }
                    })

                # DOC_ANCHORED 필터링: 장비 관련 키워드만 통과
                if mode.lower() == "doc_anchored":
                    filtered = []
                    for result in converted_results:
                        text = result.get("snippet", "") + " " + result.get("doc_id", "")
                        if re.search(self.device_pattern, text, re.IGNORECASE):
                            filtered.append(result)

                    # 필터 결과가 없으면 원본 상위 N*3 사용 (미탐 방지)
                    if not filtered:
                        logger.warning("⚠️ DOC_ANCHORED 필터링 결과 없음, 원본 상위 사용")
                        normalized = converted_results[:top_k * 3]
                    else:
                        logger.info(f"🎯 DOC_ANCHORED 필터링: {len(converted_results)}개 → {len(filtered)}개")
                        normalized = filtered[:top_k]
                else:
                    normalized = converted_results

                # 선택된 문서 강제 추가 (사용자 요청 우선 처리)
                if selected_filename:
                    selected_doc = None
                    # 1. BM25 결과에서 먼저 찾기
                    for result in converted_results:
                        if result.get("filename") == selected_filename:
                            selected_doc = result
                            break

                    # 2. BM25에 없으면 MetadataDB에서 직접 가져오기
                    if not selected_doc:
                        logger.info(f"🔍 BM25에 없음, MetadataDB에서 직접 검색: {selected_filename}")
                        all_docs = self.metadata_db.search_documents(limit=500)
                        for doc in all_docs:
                            if doc.get("filename") == selected_filename:
                                # BM25 result 형식으로 변환
                                selected_doc = {
                                    "doc_id": doc.get("filename", "unknown"),
                                    "snippet": (doc.get("text_preview") or "")[:800],
                                    "score": 0.0,
                                    "page": 1,
                                    "filename": doc.get("filename"),
                                    "file_path": doc.get("path"),
                                    "meta": {
                                        "filename": doc.get("filename"),
                                        "date": doc.get("date"),
                                        "drafter": doc.get("drafter"),
                                        "category": doc.get("category"),
                                    }
                                }
                                logger.info(f"✅ MetadataDB에서 발견: {selected_filename}")
                                break

                    # 3. 찾았으면 최상위에 강제 추가
                    if selected_doc:
                        # 기존 결과에서 제거 (중복 방지)
                        normalized = [r for r in normalized if r.get("filename") != selected_filename]
                        # 최상위에 강제 추가 (score=99.9로 최우선)
                        selected_doc_priority = selected_doc.copy()
                        selected_doc_priority["score"] = 99.9
                        normalized = [selected_doc_priority] + normalized[:top_k-1]
                        logger.info(f"🎯 선택된 문서 최상위 강제 추가: {selected_filename} (score=99.9)")
                    else:
                        logger.warning(f"⚠️ 선택된 문서 '{selected_filename}'를 찾지 못함 (BM25/MetadataDB 모두)")

            else:
                # Fallback: MetadataDB 기반 (비권장, 500자 제한)
                logger.warning("⚠️ BM25 비활성화, MetadataDB 폴백 모드 (text_preview 500자 제한)")
                filters = self.parser.parse_filters(query)
                year = filters.get('year')
                drafter = filters.get('drafter')

                results = self.metadata_db.search_documents(
                    year=year,
                    drafter=drafter,
                    limit=top_k * 3
                )

                normalized = []
                for doc in results:
                    snippet = (doc.get('text_preview') or doc.get('content') or "")[:800]
                    if not snippet:
                        snippet = f"[{doc.get('filename', 'unknown')}]"

                    relevance_score = self._calculate_relevance_score(query, doc)

                    normalized.append({
                        "doc_id": doc.get("filename", "unknown"),
                        "page": 1,
                        "score": relevance_score,
                        "snippet": snippet,
                        "meta": {
                            "filename": doc.get("filename", ""),
                            "drafter": doc.get("drafter", ""),
                            "date": doc.get("date", ""),
                            "category": doc.get("category", "pdf"),
                            "doc_id": doc.get("filename", "unknown"),
                        }
                    })

                normalized.sort(key=lambda x: x['score'], reverse=True)
                normalized = normalized[:top_k]

            # 스코어 분포 통계 계산 (low-confidence 가드레일용)
            scores = [r["score"] for r in normalized]
            top1 = scores[0] if len(scores) > 0 else 0.0
            top2 = scores[1] if len(scores) > 1 else 0.0
            top3 = scores[2] if len(scores) > 2 else 0.0

            score_stats = {
                "hits": len(normalized),
                "top1": top1,
                "top2": top2,
                "top3": top3,
                "delta12": max(0.0, top1 - top2),
                "delta13": max(0.0, top1 - top3)
            }

            # 결과 리스트에 score_stats 속성 추가 (duck typing)
            class ResultsWithStats(list):
                def __init__(self, items, stats):
                    super().__init__(items)
                    self.score_stats = stats

            results_with_stats = ResultsWithStats(normalized, score_stats)

            backend = "BM25" if (self.use_bm25 and self.bm25) else "MetadataDB"
            logger.info(
                f"🔍 HybridRetriever ({backend}): {len(normalized)}건 검색 완료 "
                f"(top1={top1:.2f}, delta12={score_stats['delta12']:.2f})"
            )
            return results_with_stats

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
