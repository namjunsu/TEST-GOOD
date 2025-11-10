"""하이브리드 검색 엔진 (BM25 인덱스 기반)

BM25Store를 사용하여 전체 텍스트 기반 검색 수행
"""

import os
import re
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB
from app.rag.query_parser import QueryParser
from rag_system.bm25_store import BM25Store  # 인덱서와 동일 모듈 사용
from app.rag.parallel_executor import get_parallel_executor
from app.rag.query_expander import get_query_expander

logger = get_logger(__name__)


class HybridRetriever:
    """하이브리드 검색 엔진 (BM25 인덱스 기반)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 BM25Store를 사용해 전체 텍스트 기반 검색을 수행합니다.
    """

    def __init__(self):
        """초기화 - BM25Store 및 MetadataDB 로드"""
        try:
            # 스니펫 길이 설정 (3600자 = ~1200 토큰)
            self.snippet_max_length = int(os.getenv("SNIPPET_MAX_LENGTH", "3600"))

            # 검색 백엔드 설정
            self.use_bm25 = os.getenv("RETRIEVER_BACKEND", "bm25").lower() == "bm25"

            # 병렬 처리 설정
            self.enable_parallel = os.getenv("ENABLE_PARALLEL_SEARCH", "true").lower() == "true"
            if self.enable_parallel:
                self.parallel_executor = get_parallel_executor(max_workers=3)
                logger.info("✅ Parallel search execution enabled")

            # MetadataDB 초기화 (필터링용)
            self.metadata_db = MetadataDB()
            self.known_drafters = self.metadata_db.list_unique_drafters()
            self.parser = QueryParser(self.known_drafters)

            # Query Expander 초기화 (Lazy - 첫 사용 시 초기화)
            self.query_expander = None
            logger.info("✅ Query Expander (Lazy initialization)")

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

    def _find_selected_document(self, selected_filename: str) -> Optional[Dict[str, Any]]:
        """
        선택된 문서를 MetadataDB에서 직접 검색

        Args:
            selected_filename: 검색할 파일명

        Returns:
            변환된 문서 딕셔너리 또는 None
        """
        try:
            all_docs = self.metadata_db.search_documents(limit=500)
            for doc in all_docs:
                if doc.get("filename") == selected_filename:
                    # BM25 result 형식으로 변환
                    return {
                        "doc_id": doc.get("filename", "unknown"),
                        "snippet": doc.get("text_preview") or "",  # 전체 문서 사용
                        "score": 99.9,  # 최우선 스코어
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
            logger.warning(f"⚠️ 선택된 문서를 찾을 수 없음: {selected_filename}")
            return None
        except Exception as e:
            logger.error(f"❌ 선택 문서 검색 실패: {e}")
            return None

    def _search_fts(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """FTS (Full-Text Search) 검색 수행 with Query Expansion

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            변환된 검색 결과 리스트
        """
        try:
            conn = self.metadata_db._get_conn()

            # Lazy initialization: Query Expander 첫 사용 시 초기화
            if self.query_expander is None:
                try:
                    self.query_expander = get_query_expander()
                    logger.info("✅ Query Expander 초기화 완료 (lazy)")
                except Exception as e:
                    logger.warning(f"⚠️ Query Expander 초기화 실패, 기본 검색 사용: {e}")
                    # Expander를 False로 설정 (다음 호출 시 재시도 방지)
                    self.query_expander = False

            # LLM 기반 Query Expansion (초기화 성공한 경우만)
            if self.query_expander and self.query_expander is not False:
                try:
                    expansion_result = self.query_expander.expand_query(query)
                    fts_query = expansion_result["search_query"]
                    logger.info(f"🔍 Query expansion: '{query}' → '{fts_query[:100]}...'")
                    logger.info(f"📊 확장된 키워드: {len(expansion_result['expanded_keywords'])}개")
                except Exception as e:
                    logger.warning(f"⚠️ Query expansion 실패, fallback 사용: {e}")
                    # Fallback: 기본 키워드 분리 (따옴표로 감싸서 리터럴 처리)
                    fts_query = ' OR '.join(f'"{word}"' for word in query.split())
            else:
                # Fallback: 기본 키워드 분리 (따옴표로 감싸서 리터럴 처리)
                fts_query = ' OR '.join(f'"{word}"' for word in query.split())

            cursor = conn.execute("""
                SELECT d.filename, d.title, d.drafter, d.date, d.category, d.text_preview
                FROM documents_fts fts
                JOIN documents d ON fts.rowid = d.rowid
                WHERE documents_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, top_k * 2))  # 여유있게 가져오기

            results = []
            for row in cursor.fetchall():
                filename, title, drafter, date, category, text_preview = row

                results.append({
                    "doc_id": filename,
                    "snippet": text_preview or "",
                    "score": 1.0,  # FTS는 rank만 제공, 임의 스코어
                    "page": 1,
                    "filename": filename,
                    "file_path": None,  # FTS에서는 path 없음
                    "meta": {
                        "filename": filename,
                        "date": date,
                        "drafter": drafter,
                        "category": category,
                    }
                })

            logger.info(f"✅ FTS 검색 완료: {len(results)}개 결과 (원본='{query}', 확장={len(expansion_result['expanded_keywords'])}개)")
            return results[:top_k]

        except Exception as e:
            logger.error(f"❌ FTS 검색 실패: {e}")
            return []

    def _calculate_relevance_score(self, query: str, doc: Dict[str, Any]) -> float:
        """쿼리와 문서 간 relevance 스코어 계산 (BM25 유사) + 파일명 매칭 강화

        Args:
            query: 검색 질의
            doc: 문서 딕셔너리 (filename, text_preview 포함)

        Returns:
            0.0~10.0 범위의 relevance 스코어 (파일명 매칭 시 최대 10점)
        """
        # 쿼리 토큰화 (공백 + 특수문자 제거)
        query_tokens = set(re.findall(r'\w+', query.lower()))
        if not query_tokens:
            return 0.5  # 토큰 없으면 중립 스코어

        # 문서 텍스트 준비 (snippet과 meta에서 추출)
        filename = (doc.get('filename') or '').lower()
        snippet = (doc.get('snippet') or '').lower()  # Fixed: text_preview → snippet
        meta = doc.get('meta', {})
        drafter = (meta.get('drafter') or '').lower()  # Fixed: meta에서 drafter 추출
        doc_text = filename + ' ' + snippet + ' ' + drafter

        # 매칭된 토큰 수 계산
        matched_tokens = sum(1 for token in query_tokens if token in doc_text)

        # 기본 스코어: 매칭률
        match_ratio = matched_tokens / len(query_tokens) if query_tokens else 0.0

        # 보너스 1: 완전 일치하는 구문이 있으면 가산점
        if query.lower() in doc_text:
            match_ratio = min(1.0, match_ratio + 0.3)

        # 페널티: 문서가 너무 짧으면 감점 (신뢰도 저하)
        text_len = len(doc.get('snippet') or '')  # Fixed: text_preview → snippet
        if text_len < 100:
            match_ratio *= 0.7

        # 안전장치: match_ratio가 0일 때 최소 epsilon 값 부여
        if match_ratio == 0.0 and matched_tokens == 0:
            match_ratio = 1e-6  # epsilon to avoid all-zero scores

        # 🎯 파일명 매칭 강화 (CRITICAL: 정확도 향상의 핵심)
        filename_bonus = 0.0
        filename_exact_match_count = 0

        for token in query_tokens:
            # 파일명에 정확히 일치하는 토큰이 있으면 큰 보너스
            if token in filename:
                filename_exact_match_count += 1
                filename_bonus += 2.0  # 토큰당 +2점

        # 파일명에서 연속된 구문 매칭 시 추가 보너스
        if len(query_tokens) >= 2 and query.lower() in filename:
            filename_bonus += 3.0  # 완전 구문 매칭 +3점

        # 최종 스코어: 기본 스코어(0~1) + 파일명 보너스(0~10)
        final_score = match_ratio + filename_bonus

        if filename_bonus > 0:
            logger.debug(f"📊 Scoring '{filename[:50]}': match={match_ratio:.2f}, filename_bonus={filename_bonus:.1f}, final={final_score:.1f}")

        return max(0.0, min(10.0, final_score))

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

            # FTS 우선 검색, BM25 보충 전략
            if self.use_bm25 and self.bm25:
                # DOC_ANCHORED 모드: 넉넉하게 검색 후 필터링
                search_k = 50 if mode.lower() == "doc_anchored" else top_k

                # 1. FTS 먼저 시도 (더 정확함)
                fts_results = self._search_fts(query, top_k=search_k)

                # 2. FTS 결과가 충분하면 FTS만 사용, 부족하면 BM25 보충
                if len(fts_results) >= search_k * 0.5:  # FTS 결과가 목표의 50% 이상이면
                    logger.info(f"✅ FTS 결과 충분 ({len(fts_results)}개), BM25 생략")
                    bm25_results = []  # BM25 생략
                    selected_doc = None
                else:
                    # FTS 결과 부족, BM25로 보충
                    logger.info(f"⚠️ FTS 결과 부족 ({len(fts_results)}개), BM25로 보충")

                    # Parallel execution: BM25 search와 selected doc lookup 동시 실행
                    if self.enable_parallel and selected_filename:
                        # 병렬 실행: BM25 검색 + 선택 문서 검색
                        search_tasks = [
                            {
                                "name": "bm25_search",
                                "func": self.bm25.search,
                                "args": (query,),
                                "kwargs": {"top_k": search_k}
                            },
                            {
                                "name": "selected_doc_lookup",
                                "func": self._find_selected_document,
                                "args": (selected_filename,),
                                "kwargs": {}
                            }
                        ]
                        parallel_results = self.parallel_executor.execute_searches(search_tasks)
                        bm25_results = parallel_results.get("bm25_search", [])
                        selected_doc = parallel_results.get("selected_doc_lookup")
                    else:
                        # 순차 실행 (기본)
                        bm25_results = self.bm25.search(query, top_k=search_k)
                        selected_doc = None

                # FTS + BM25 결과 병합 (중복 제거)
                converted_results = []
                seen_filenames = set()

                # 1. FTS 결과 먼저 추가 (우선순위 높음)
                for result in fts_results:
                    filename = result.get("filename")
                    if filename and filename not in seen_filenames:
                        converted_results.append(result)
                        seen_filenames.add(filename)

                # 2. BM25 결과 추가 (FTS에 없는 것만)
                for result in bm25_results:
                    filename = result.get("filename")
                    if filename and filename not in seen_filenames:
                        converted_results.append({
                            "doc_id": result.get("filename", "unknown"),
                            "snippet": result.get("content", ""),
                            "score": result.get("score", 0.0),
                            "page": 1,
                            "filename": result.get("filename"),
                            "file_path": result.get("path"),
                            "meta": {
                                "filename": result.get("filename"),
                                "date": result.get("date"),
                                "drafter": result.get("drafter"),
                                "category": result.get("category"),
                            }
                        })
                        seen_filenames.add(filename)

                logger.info(f"📊 병합 결과: FTS {len(fts_results)}개 + BM25 {len(bm25_results)}개 = 총 {len(converted_results)}개 (중복 제거)")

                # 🎯 파일명 매칭 기반 재스코어링 (CRITICAL: 정확도 향상)
                if converted_results:
                    for result in converted_results:
                        # 각 문서에 대해 파일명 매칭 보너스 계산
                        enhanced_score = self._calculate_relevance_score(query, result)
                        result["score"] = enhanced_score

                    # 스코어 기준 재정렬 (높은 순)
                    converted_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                    logger.info(f"🔄 파일명 매칭 재스코어링 완료 (top score: {converted_results[0]['score']:.2f})")

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
                    # 병렬 실행에서 이미 가져온 경우 사용, 아니면 검색
                    if self.enable_parallel and 'selected_doc' in locals() and selected_doc:
                        # 이미 병렬로 가져옴
                        logger.info(f"✅ 병렬 검색으로 선택 문서 발견: {selected_filename}")
                    else:
                        # 1. BM25 결과에서 먼저 찾기
                        selected_doc = None
                        for result in converted_results:
                            if result.get("filename") == selected_filename:
                                selected_doc = result.copy()
                                selected_doc["score"] = 99.9
                                break

                        # 2. BM25에 없으면 MetadataDB에서 직접 가져오기
                        if not selected_doc:
                            logger.info(f"🔍 BM25에 없음, MetadataDB에서 직접 검색: {selected_filename}")
                            selected_doc = self._find_selected_document(selected_filename)

                    # 3. 찾았으면 최상위에 강제 추가
                    if selected_doc:
                        # 기존 결과에서 제거 (중복 방지)
                        normalized = [r for r in normalized if r.get("filename") != selected_filename]
                        # 최상위에 강제 추가
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
                    snippet = doc.get('text_preview') or doc.get('content') or ""  # 전체 문서 사용
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

            # ✨ 파일명 매칭 보너스 (쿼리와 파일명이 유사하면 점수 증가)
            if not selected_filename:  # 선택된 문서가 없을 때만 적용
                normalized = self._apply_filename_bonus(query, normalized)
                # 보너스 적용 후 재정렬
                normalized.sort(key=lambda x: x['score'], reverse=True)

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

    def _apply_filename_bonus(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """파일명 유사도에 따라 점수 보너스 적용

        쿼리와 파일명이 매우 유사할 때 검색 순위를 높이기 위한 보정.

        Args:
            query: 사용자 검색 질의
            results: 검색 결과 리스트

        Returns:
            보너스가 적용된 검색 결과 리스트
        """
        import re

        # 쿼리 정규화: 공백, 특수문자 제거 후 토큰화
        query_normalized = re.sub(r'[^\w\s]', ' ', query.lower())
        query_tokens = set(query_normalized.split())

        if not query_tokens:
            return results

        for result in results:
            filename = result.get('filename', '')
            if not filename:
                continue

            # 파일명 정규화
            # 1. 날짜 패턴 제거 (YYYY-MM-DD_)
            filename_clean = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', filename)
            # 2. 확장자 제거
            filename_clean = re.sub(r'\.\w+$', '', filename_clean)
            # 3. 언더스코어를 공백으로 치환
            filename_clean = filename_clean.replace('_', ' ')
            # 4. 특수문자 제거 후 소문자 변환
            filename_clean = re.sub(r'[^\w\s]', ' ', filename_clean.lower())

            # 파일명 토큰화
            filename_tokens = set(filename_clean.split())

            if not filename_tokens:
                continue

            # 토큰 매칭률 계산 (Jaccard similarity)
            intersection = query_tokens & filename_tokens
            union = query_tokens | filename_tokens
            jaccard_score = len(intersection) / len(union) if union else 0.0

            # 쿼리 토큰이 파일명에 모두 포함되었는지 확인
            query_coverage = len(intersection) / len(query_tokens) if query_tokens else 0.0

            # 최종 유사도 점수 (둘 중 높은 값 사용)
            similarity = max(jaccard_score, query_coverage)

            # 보너스 점수 계산 (0~30점 범위)
            # - 80% 이상 유사: +30점
            # - 60~80% 유사: +20점
            # - 40~60% 유사: +10점
            # - 40% 미만: 보너스 없음
            bonus = 0.0
            if similarity >= 0.8:
                bonus = 30.0
            elif similarity >= 0.6:
                bonus = 20.0
            elif similarity >= 0.4:
                bonus = 10.0

            # 보너스 적용
            if bonus > 0:
                original_score = result['score']
                result['score'] += bonus
                logger.info(
                    f"📈 파일명 보너스: {filename[:40]} | "
                    f"유사도={similarity:.2f} | "
                    f"점수 {original_score:.2f} → {result['score']:.2f} (+{bonus:.1f})"
                )

        return results
