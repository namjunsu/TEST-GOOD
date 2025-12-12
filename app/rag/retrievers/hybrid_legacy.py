"""하이브리드 검색 엔진 v2.1 (BM25 + ExactMatch)

2025-11-11 v2.1 변경사항:
- FTS 정렬: ORDER BY bm25(documents_fts) (SQLite FTS5 관련성 정렬)
- expansion_result 안전 초기화 (expanded_kw_count)
- 파일명 보너스 스케일 정규화 (30점 → 4점, 전체 0-10 유지)
- selected_doc 처리 명확화 (locals() 제거)

2025-11-11 v2.0 변경사항:
- Stage 0: ExactMatchRetriever (모델/부품 코드 정확일치 최우선)
- Stage 1: 메타데이터 라우팅 (YEAR + NAME)
- Stage 2: FTS 검색
- Stage 3: BM25 보충

BM25Store를 사용하여 전체 텍스트 기반 검색 수행
"""

import os
import re
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import yaml

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.parallel_executor import ParallelSearchExecutor, get_parallel_executor
from app.rag.query_expander import get_query_expander
from app.rag.query_parser import QueryParser
from app.rag.retrievers.exact_match import ExactMatchRetriever
from config.constants import HybridRetrieverConfig, HybridSearchConfig, ScoringConfig
from rag_system.active.bm25_store import BM25Store  # 인덱서와 동일 모듈 사용

if TYPE_CHECKING:
    from app.rag.query_expander import QueryExpander

logger = get_logger(__name__)


class ResultsWithStats(list):
    """검색 결과 리스트 + 점수 통계 (duck typing용)

    list를 상속하여 일반 리스트처럼 사용 가능하면서,
    score_stats 속성을 통해 점수 통계 정보도 제공합니다.
    """

    def __init__(self, items: list[dict[str, Any]], stats: dict[str, float]):
        super().__init__(items)
        self.score_stats = stats


class HybridRetriever:
    """하이브리드 검색 엔진 (BM25 인덱스 기반)

    RAGPipeline의 Retriever 프로토콜을 구현하며,
    내부적으로 BM25Store를 사용해 전체 텍스트 기반 검색을 수행합니다.
    """

    # 클래스 속성 타입 선언
    snippet_max_length: int
    retrieve_topk: int
    display_limit: int
    use_bm25: bool
    enable_parallel: bool
    parallel_executor: Optional[ParallelSearchExecutor]
    metadata_db: MetadataDB
    known_drafters: set[str]
    parser: QueryParser
    exact_match_enabled: bool
    exact_match: Optional[ExactMatchRetriever]
    query_expander: Optional["QueryExpander"]
    bm25: Optional[BM25Store]
    device_pattern: Optional[str]
    deny_pattern: Optional[str]
    _last_index_mtime: float
    _reload_lock: threading.RLock  # race condition 방지용 락

    def __init__(self) -> None:
        """초기화 - BM25Store 및 MetadataDB 로드"""
        try:
            # 스니펫 길이 설정 (3600자 = ~1200 토큰)
            self.snippet_max_length = int(os.getenv("SNIPPET_MAX_LENGTH", str(HybridRetrieverConfig.SNIPPET_MAX_LENGTH)))

            # 검색 후보/표시 수 분리 (2025-11-10)
            self.retrieve_topk = int(os.getenv("RETRIEVE_TOPK", str(HybridRetrieverConfig.RETRIEVE_TOPK)))
            self.display_limit = int(os.getenv("DISPLAY_LIMIT", str(HybridRetrieverConfig.DISPLAY_LIMIT)))

            # 검색 백엔드 설정
            self.use_bm25 = os.getenv("RETRIEVER_BACKEND", "bm25").lower() == "bm25"

            # 병렬 처리 설정
            self.enable_parallel = os.getenv("ENABLE_PARALLEL_SEARCH", "true").lower() == "true"
            self.parallel_executor = None  # 기본값
            if self.enable_parallel:
                self.parallel_executor = get_parallel_executor(max_workers=HybridRetrieverConfig.PARALLEL_MAX_WORKERS)
                logger.info("✅ Parallel search execution enabled")

            # MetadataDB 초기화 (필터링용)
            self.metadata_db = MetadataDB()
            self.known_drafters = self.metadata_db.list_unique_drafters()
            self.parser = QueryParser(self.known_drafters)

            # ExactMatchRetriever 초기화 (Stage 0 - v2.0 추가)
            self.exact_match_enabled = os.getenv("ENABLE_EXACT_MATCH", "true").lower() == "true"
            if self.exact_match_enabled:
                self.exact_match = ExactMatchRetriever(db=self.metadata_db)
                logger.info("✅ ExactMatchRetriever v2.0 enabled (Stage 0)")
            else:
                self.exact_match = None
                logger.info("⚠️ ExactMatchRetriever disabled")

            # Query Expander 초기화 (Lazy - 첫 사용 시 초기화)
            self.query_expander = None
            logger.info("✅ Query Expander (Lazy initialization)")

            # BM25Store 초기화
            self.bm25 = None
            if self.use_bm25:
                index_path = os.getenv("BM25_INDEX_PATH", HybridRetrieverConfig.DEFAULT_BM25_INDEX_PATH)
                logger.info(f"🔍 DEBUG: BM25_INDEX_PATH={index_path} (exists={Path(index_path).exists()})")
                self.bm25 = BM25Store(index_path=index_path)
                logger.info(f"✅ HybridRetriever 초기화 완료 (BM25 백엔드, {len(self.bm25.documents)}개 문서, path={self.bm25.index_path})")
            else:
                logger.info("✅ HybridRetriever 초기화 완료 (MetadataDB 폴백 모드)")

            # 인덱스 파일 mtime 추적 (자동 재로드용)
            self._last_index_mtime = self._get_index_mtime()
            self._reload_lock = threading.RLock()  # race condition 방지

            # DOC_ANCHORED 키워드 로드 (YAML 외부화)
            self._load_router_keywords()

        except Exception as e:
            logger.error(f"❌ HybridRetriever 초기화 실패: {e}")
            raise

    def _load_router_keywords(self) -> None:
        """라우터 키워드 YAML v2 로드 (프로파일 기반 구조)"""
        try:
            config_path = Path("config/router_keywords.yaml")
            if config_path.exists():
                config = yaml.safe_load(config_path.read_text())

                # YAML v2 프로파일 구조 파싱
                doc_cfg = config.get("doc_anchored", {})
                profiles = doc_cfg.get("profiles", {})

                if not profiles:
                    raise ValueError("doc_anchored.profiles 섹션이 비어있음")

                # 모든 프로파일의 allow 패턴 병합
                all_allow_patterns = []
                all_deny_patterns = []

                for _profile_name, profile_data in profiles.items():
                    allow_list = profile_data.get("allow", [])
                    deny_list = profile_data.get("deny", [])

                    # {KBL}/{KBR} 매크로 치환
                    allow_list = [self._expand_macros(p) for p in allow_list]
                    deny_list = [self._expand_macros(p) for p in deny_list]

                    all_allow_patterns.extend(allow_list)
                    all_deny_patterns.extend(deny_list)

                # 병합된 패턴으로 device_pattern 생성
                self.device_pattern = "|".join(all_allow_patterns) if all_allow_patterns else None
                self.deny_pattern = "|".join(all_deny_patterns) if all_deny_patterns else None

                logger.info(
                    f"✅ 라우터 키워드 로드 완료: {len(profiles)}개 프로파일, "
                    f"{len(all_allow_patterns)}개 allow 패턴, {len(all_deny_patterns)}개 deny 패턴",
                )
            else:
                # 폴백: 하드코딩 패턴 사용
                self._set_fallback_patterns()
                logger.warning("⚠️ router_keywords.yaml 없음, 폴백 패턴 사용")
        except Exception as e:
            logger.error(f"❌ 키워드 로드 실패: {e}, 폴백 패턴 사용")
            self._set_fallback_patterns()

    def _expand_macros(self, pattern: str) -> str:
        """YAML 패턴의 {KBL}/{KBR} 매크로를 정규표현식으로 치환"""
        pattern = pattern.replace("{KBL}", r"(?<![가-힣A-Za-z0-9])")
        pattern = pattern.replace("{KBR}", r"(?![가-힣A-Za-z0-9])")
        return pattern

    def _set_fallback_patterns(self) -> None:
        """폴백 패턴 설정 (YAML 로드 실패 시)"""
        self.device_pattern = (
            r"\bHRD[-\s]?\d{3,4}\b|DVR|NVR|"
            r"Hanwha(?:\s+(?:Techwin|Vision))?|"
            r"보존용|녹화용|교체|노후|장비|카메라|모니터"
        )
        self.deny_pattern = None

    def _get_index_mtime(self) -> float:
        """인덱스 파일의 수정 시간 반환"""
        if not self.use_bm25:
            return 0.0
        index_path = os.getenv("BM25_INDEX_PATH", HybridRetrieverConfig.DEFAULT_BM25_INDEX_PATH)
        return os.path.getmtime(index_path) if Path(index_path).exists() else 0.0

    def _reload_if_index_rotated(self) -> None:
        """인덱스 파일이 갱신되면 자동 리로드 (스레드 안전)"""
        if not self.use_bm25:
            return

        current_mtime = self._get_index_mtime()
        if current_mtime > self._last_index_mtime:
            # Double-checked locking: 락 획득 전 빠른 체크로 불필요한 락 방지
            with self._reload_lock:
                # 락 획득 후 재확인 (다른 스레드가 이미 갱신했을 수 있음)
                current_mtime = self._get_index_mtime()
                if current_mtime > self._last_index_mtime:
                    logger.info("🔄 인덱스 파일 갱신 감지, 재로드 중...")
                    index_path = os.getenv("BM25_INDEX_PATH", HybridRetrieverConfig.DEFAULT_BM25_INDEX_PATH)
                    self.bm25 = BM25Store(index_path=index_path)
                    self._last_index_mtime = current_mtime
                    logger.info(f"✅ 인덱스 재로드 완료 ({len(self.bm25.documents)}개 문서)")

    def _find_selected_document(self, selected_filename: str) -> Optional[dict[str, Any]]:
        """
        선택된 문서를 MetadataDB에서 직접 검색 (SQL 레벨 필터링)

        Args:
            selected_filename: 검색할 파일명

        Returns:
            변환된 문서 딕셔너리 또는 None
        """
        try:
            # N+1 쿼리 최적화: get_by_filename()으로 직접 조회
            doc = self.metadata_db.get_by_filename(selected_filename)
            if doc:
                # BM25 result 형식으로 변환
                return {
                    "doc_id": doc.get("filename", "unknown"),
                    "snippet": doc.get("text_preview") or "",
                    "score": HybridSearchConfig.SELECTED_DOC_SCORE,  # 최우선 스코어
                    "page": 1,
                    "filename": doc.get("filename"),
                    "file_path": doc.get("path"),
                    "meta": {
                        "filename": doc.get("filename"),
                        "date": doc.get("date"),
                        "drafter": doc.get("drafter"),
                        "category": doc.get("category"),
                    },
                }
            logger.warning(f"⚠️ 선택된 문서를 찾을 수 없음: {selected_filename}")
            return None
        except Exception as e:
            logger.error(f"❌ 선택 문서 검색 실패: {e}")
            return None

    def _search_fts(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """FTS (Full-Text Search) 검색 수행 with Query Expansion

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            변환된 검색 결과 리스트
        """
        try:
            conn = self.metadata_db._get_conn()

            # 확장 키워드 카운트 (안전 초기화)
            expanded_kw_count = 0

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
                    expanded_kw_count = len(expansion_result.get("expanded_keywords", []))
                    logger.info(f"🔍 Query expansion: '{query}' → '{fts_query[:100]}...'")
                except Exception as e:
                    logger.warning(f"⚠️ Query expansion 실패, fallback 사용: {e}")
                    # Fallback: 기본 키워드 분리 (따옴표로 감싸서 리터럴 처리)
                    fts_query = " OR ".join(f'"{word}"' for word in query.split())
            else:
                # Fallback: 기본 키워드 분리 (따옴표로 감싸서 리터럴 처리)
                fts_query = " OR ".join(f'"{word}"' for word in query.split())

            cursor = conn.execute("""
                SELECT d.filename, d.title, d.drafter, d.date, d.category, d.text_preview, d.path
                FROM documents_fts fts
                JOIN documents d ON fts.rowid = d.rowid
                WHERE documents_fts MATCH ?
                ORDER BY bm25(documents_fts)
                LIMIT ?
            """, (fts_query, top_k * HybridSearchConfig.FTS_OVERSAMPLE_FACTOR))  # 여유있게 가져오기

            results = []
            for row in cursor.fetchall():
                filename, title, drafter, date, category, text_preview, path = row

                results.append({
                    "doc_id": filename,
                    "snippet": text_preview or "",
                    "score": 1.0,  # FTS는 rank만 제공, 임의 스코어
                    "page": 1,
                    "filename": filename,
                    "file_path": path,  # DB에서 path 가져오기
                    "meta": {
                        "filename": filename,
                        "date": date,
                        "drafter": drafter,
                        "category": category,
                    },
                })

            logger.info(f"✅ FTS 검색 완료: {len(results)}개 결과 (원본='{query}', 확장키워드={expanded_kw_count}개)")
            return results[:top_k]

        except Exception as e:
            logger.error(f"❌ FTS 검색 실패: {e}")
            return []

    def _enrich_with_bm25_content(self, fts_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """FTS 결과에 BM25 인덱스의 전체 content 보강 (2025-12-12)

        FTS는 text_preview (500자)만 반환하므로, BM25 인덱스에서
        전체 content를 가져와 snippet을 보강합니다.

        Args:
            fts_results: FTS 검색 결과 리스트

        Returns:
            content가 보강된 결과 리스트
        """
        if not fts_results or not self.bm25:
            return fts_results

        try:
            # BM25 인덱스에서 filename → content 매핑 생성
            # BM25Store 구조: documents는 텍스트 리스트, metadata는 별도 리스트
            bm25_content_map = {}
            for idx, content in enumerate(self.bm25.documents):
                if idx < len(self.bm25.metadata):
                    meta = self.bm25.metadata[idx]
                    filename = meta.get("filename") if isinstance(meta, dict) else None
                    if filename and content:
                        bm25_content_map[filename] = content

            # FTS 결과에 content 보강
            enriched_count = 0
            for result in fts_results:
                filename = result.get("filename")
                if filename and filename in bm25_content_map:
                    bm25_content = bm25_content_map[filename]
                    current_snippet = result.get("snippet", "")

                    # BM25 content가 더 길면 교체
                    if len(bm25_content) > len(current_snippet):
                        result["snippet"] = bm25_content[:self.snippet_max_length]
                        result["content"] = bm25_content  # 전체 content도 추가
                        enriched_count += 1

            if enriched_count > 0:
                logger.info(f"📝 FTS 결과 content 보강: {enriched_count}/{len(fts_results)}개 문서")

            return fts_results

        except Exception as e:
            logger.warning(f"⚠️ FTS content 보강 실패: {e}")
            return fts_results

    def _calculate_relevance_score(self, query: str, doc: dict[str, Any]) -> float:
        """쿼리와 문서 간 relevance 스코어 계산 (BM25 유사) + 파일명 매칭 강화

        Args:
            query: 검색 질의
            doc: 문서 딕셔너리 (filename, text_preview 포함)

        Returns:
            0.0~10.0 범위의 relevance 스코어 (파일명 매칭 시 최대 10점)
        """
        # 쿼리 토큰화 (공백 + 특수문자 제거)
        query_tokens = set(re.findall(r"\w+", query.lower()))
        if not query_tokens:
            return 0.5  # 토큰 없으면 중립 스코어

        # 문서 텍스트 준비 (snippet과 meta에서 추출)
        filename = (doc.get("filename") or "").lower()
        snippet = (doc.get("snippet") or "").lower()  # Fixed: text_preview → snippet
        meta = doc.get("meta", {})
        drafter = (meta.get("drafter") or "").lower()  # Fixed: meta에서 drafter 추출
        doc_text = filename + " " + snippet + " " + drafter

        # 매칭된 토큰 수 계산
        matched_tokens = sum(1 for token in query_tokens if token in doc_text)

        # 기본 스코어: 매칭률
        match_ratio = matched_tokens / len(query_tokens) if query_tokens else 0.0

        # 보너스 1: 완전 일치하는 구문이 있으면 가산점
        if query.lower() in doc_text:
            match_ratio = min(1.0, match_ratio + 0.3)

        # 페널티: 문서가 너무 짧으면 감점 (신뢰도 저하)
        text_len = len(doc.get("snippet") or "")  # Fixed: text_preview → snippet
        if text_len < HybridSearchConfig.RELEVANCE_SHORT_TEXT_THRESHOLD:
            match_ratio *= HybridSearchConfig.RELEVANCE_SHORT_TEXT_PENALTY

        # 안전장치: match_ratio가 0일 때 최소 epsilon 값 부여
        if match_ratio == 0.0 and matched_tokens == 0:
            match_ratio = 1e-6  # epsilon to avoid all-zero scores

        # 🎯 파일명 매칭 강화 (CRITICAL: 정확도 향상의 핵심)
        # v2.1: 스케일 정규화 (보너스 상한 +4.0, 전체 0-10 범위 유지)
        filename_bonus = 0.0
        filename_exact_match_count = 0

        for token in query_tokens:
            # 파일명에 정확히 일치하는 토큰이 있으면 보너스
            if token in filename:
                filename_exact_match_count += 1
                filename_bonus += ScoringConfig.FILENAME_TOKEN_BONUS

        # 파일명에서 연속된 구문 매칭 시 추가 보너스 (n-gram 기반 강화)
        # 1. 전체 쿼리가 파일명에 있으면 최대 보너스
        if len(query_tokens) >= 2 and query.lower() in filename:
            filename_bonus += ScoringConfig.FILENAME_PHRASE_BONUS

        # 2. n-gram 구문 매칭 (2-gram, 3-gram)
        # 예: "광화문 스튜디오 모니터" → ["광화문 스튜디오", "스튜디오 모니터"] 매칭
        query_words = list(query_tokens)  # set → list 변환하여 순서 유지용으로 재생성
        query_words = re.findall(r"\w+", query.lower())  # 순서 유지된 단어 리스트
        filename_clean = re.sub(r"[_\-\.]", " ", filename)  # 구분자 → 공백

        ngram_bonus = 0.0
        for n in [3, 2]:  # 3-gram 우선, 2-gram 다음
            if len(query_words) >= n:
                for i in range(len(query_words) - n + 1):
                    ngram = " ".join(query_words[i:i + n])
                    if ngram in filename_clean:
                        # n이 클수록 높은 보너스 (3-gram: 0.6, 2-gram: 0.3)
                        ngram_bonus += n * 0.2

        # n-gram 보너스 상한 (최대 1.0)
        filename_bonus += min(1.0, ngram_bonus)

        # 텍스트 길이 기반 페널티 (OCR 불량 문서 억제)
        text_len = len(doc.get("snippet") or "")
        if text_len < ScoringConfig.SHORT_TEXT_THRESHOLD:
            filename_bonus *= ScoringConfig.SHORT_TEXT_PENALTY
        elif text_len < ScoringConfig.VERY_SHORT_TEXT_THRESHOLD:
            filename_bonus *= ScoringConfig.VERY_SHORT_TEXT_PENALTY

        # 보너스 상한 제한
        filename_bonus = min(ScoringConfig.FILENAME_BONUS_CAP, filename_bonus)

        # 최종 스코어: 기본 스코어(0~1) * MATCH_RATIO_SCALE + 파일명 보너스
        final_score = (match_ratio * ScoringConfig.MATCH_RATIO_SCALE) + filename_bonus

        if filename_bonus > 0:
            logger.debug(f"📊 Scoring '{filename[:50]}': match={match_ratio:.2f}, filename_bonus={filename_bonus:.1f}, final={final_score:.1f}")

        return max(0.0, min(ScoringConfig.MAX_FINAL_SCORE, final_score))

    def search(self, query: str, top_k: int, mode: str = "chat", selected_filename: Optional[str] = None, strict_content: bool = False) -> list[dict[str, Any]]:
        """검색 수행 v2.1

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과
            mode: 검색 모드 ("chat", "doc_anchored" 등)
            selected_filename: 선택된 문서 파일명 (우선 검색용, 선택사항)
            strict_content: 정밀 내용 검색 모드 (2025-11-19 추가)
                True일 때: QueryExpander/파일명 보너스/메타데이터 라우팅 비활성화,
                BM25-only 검색으로 본문 일치만 반환

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

            # 🔍 STRICT CONTENT MODE: 정밀 내용 검색 (2025-11-19 추가)
            if strict_content:
                logger.info("🎯 STRICT CONTENT MODE 활성화: QueryExpander/파일명보너스/메타라우팅 비활성화")
                if self.use_bm25 and self.bm25:
                    # BM25-only 검색 (넉넉히 가져옴)
                    bm25_results = self.bm25.search(query, top_k=top_k * HybridSearchConfig.STRICT_CONTENT_OVERSAMPLE)

                    # 결과를 표준 형식으로 변환
                    converted_results = []
                    for result in bm25_results:
                        converted_results.append({
                            "doc_id": result.get("filename", "unknown"),
                            "snippet": result.get("content", "")[:self.snippet_max_length],
                            "score": result.get("score", 0.0),
                            "page": 1,
                            "filename": result.get("filename"),
                            "file_path": result.get("path"),
                            "meta": {
                                "filename": result.get("filename"),
                                "date": result.get("date"),
                                "drafter": result.get("drafter"),
                                "category": result.get("category"),
                            },
                        })

                    # 후처리: 실제 content에 query 키워드가 포함된 것만 필터링
                    filtered_results = []
                    # 불용어 제거하여 핵심 키워드 추출
                    stop_words = ["문서", "파일", "기안서", "찾아줘", "찾아", "검색", "관련", "좀", "해줘",
                                  "내용", "본문", "들어간", "포함", "포함된", "있는", "만", "에", "에서", "이", "가"]
                    core_keyword = query
                    for word in stop_words:
                        core_keyword = core_keyword.replace(word, " ")
                    core_keyword = core_keyword.strip()

                    logger.info(f"🔍 핵심 키워드 추출: '{query}' → '{core_keyword}'")

                    # 동의어 확장된 경우 각 variant를 분리 (공백 기준)
                    keyword_variants = core_keyword.split()

                    for doc in converted_results:
                        content = doc.get("snippet", "") or ""
                        # variant 중 하나라도 content에 포함되면 통과
                        matched = False
                        for variant in keyword_variants:
                            if variant and variant in content:
                                matched = True
                                break
                        if matched:
                            filtered_results.append(doc)
                            if len(filtered_results) >= top_k:
                                break

                    logger.info(f"✅ STRICT CONTENT 검색 완료: {len(bm25_results)}개 → 필터링 {len(filtered_results)}개")

                    # 스코어 통계
                    scores = [r["score"] for r in filtered_results]
                    top1 = scores[0] if len(scores) > 0 else 0.0
                    top2 = scores[1] if len(scores) > 1 else 0.0
                    top3 = scores[2] if len(scores) > 2 else 0.0

                    score_stats = {
                        "hits": len(filtered_results),
                        "top1": top1,
                        "top2": top2,
                        "top3": top3,
                        "delta12": max(0.0, top1 - top2),
                        "delta13": max(0.0, top1 - top3),
                    }

                    return ResultsWithStats(filtered_results, score_stats)
                logger.warning("⚠️ BM25 비활성화 상태에서 STRICT CONTENT 모드 요청됨, 빈 결과 반환")
                return []

            # Stage 0: ExactMatch (코드 정확일치 최우선 - v2.0 추가)
            if self.exact_match_enabled and self.exact_match:
                exact_results = self.exact_match.search(query, top_k=top_k)
                if exact_results:
                    logger.info(f"🎯 Stage 0 (ExactMatch): {len(exact_results)}건 반환, 하위 Stage 스킵")
                    return exact_results[:top_k]

            # Stage 1: 메타데이터 기반 검색 라우팅 (YEAR + NAME 패턴)
            year_match = re.search(r"(\d{4})", query)
            name_match = re.search(r"([가-힣]{2,4})", query)

            if year_match and name_match:
                year = year_match.group(1)
                name = name_match.group(1)
                logger.info(f"🎯 메타데이터 검색 라우팅: {year}년 + {name}")

                # MetadataDB에서 직접 검색 (RETRIEVE_TOPK 후보 가져오기)
                metadata_results = self.metadata_db.search_documents(drafter=name, year=year, limit=self.retrieve_topk)

                if metadata_results:
                    logger.info(f"✅ 메타데이터 검색 성공: {len(metadata_results)}개 문서")

                    # 결과를 표준 형식으로 변환
                    converted_results = []
                    for result in metadata_results:
                        converted_results.append({
                            "doc_id": result.get("filename", "unknown"),
                            "snippet": result.get("text_preview", "")[:self.snippet_max_length],
                            "score": HybridSearchConfig.METADATA_MATCH_SCORE,  # 메타데이터 일치는 높은 점수
                            "page": 1,
                            "filename": result.get("filename"),
                            "file_path": result.get("path"),
                            "meta": {
                                "filename": result.get("filename"),
                                "date": result.get("display_date") or result.get("date"),
                                "drafter": result.get("drafter"),
                                "category": result.get("category"),
                                "title": result.get("title", ""),
                            },
                        })

                    # 중복 제거 및 상위 K개 반환
                    seen_filenames = set()
                    deduped_results = []
                    for result in converted_results:
                        filename = result.get("filename")
                        if filename and filename not in seen_filenames:
                            seen_filenames.add(filename)
                            deduped_results.append(result)

                    logger.info(f"📊 메타데이터 검색 결과: {len(metadata_results)}개 → 중복제거 {len(deduped_results)}개")
                    return deduped_results[:top_k]

            # FTS 우선 검색, BM25 보충 전략
            if self.use_bm25 and self.bm25:
                # DOC_ANCHORED 모드: 넉넉하게 검색 후 필터링
                search_k = HybridSearchConfig.DOC_ANCHORED_SEARCH_K if mode.lower() == "doc_anchored" else top_k

                # 1. FTS 먼저 시도 (더 정확함)
                fts_results = self._search_fts(query, top_k=search_k)

                # 2. FTS 결과가 충분하면 FTS만 사용, 부족하면 BM25 보충
                if len(fts_results) >= search_k * HybridSearchConfig.FTS_SUFFICIENT_RATIO:  # FTS 결과가 목표의 50% 이상이면
                    logger.info(f"✅ FTS 결과 충분 ({len(fts_results)}개), BM25 생략")
                    # 🔧 FTS 결과에 재스코어링 적용 (관련도 0.000 문제 해결)
                    for result in fts_results:
                        result["score"] = self._calculate_relevance_score(query, result)
                    summary = [f"{r.get('filename', '?')[:20]}={r.get('score', 0):.2f}" for r in fts_results[:3]]
                    logger.info(f"📊 FTS 재스코어링 완료: {summary}")

                    # 🔧 FTS 결과에 BM25 content 보강 (2025-12-12: text_preview 500자 제한 해결)
                    fts_results = self._enrich_with_bm25_content(fts_results)

                    bm25_results = []  # BM25 검색은 생략하지만 content는 보강됨
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
                                "kwargs": {"top_k": search_k},
                            },
                            {
                                "name": "selected_doc_lookup",
                                "func": self._find_selected_document,
                                "args": (selected_filename,),
                                "kwargs": {},
                            },
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
                            },
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

                    # 필터 결과가 없으면 원본 상위 N*배수 사용 (미탐 방지)
                    if not filtered:
                        logger.warning("⚠️ DOC_ANCHORED 필터링 결과 없음, 원본 상위 사용")
                        normalized = converted_results[:top_k * HybridSearchConfig.DOC_ANCHORED_FALLBACK_MULTIPLIER]
                    else:
                        logger.info(f"🎯 DOC_ANCHORED 필터링: {len(converted_results)}개 → {len(filtered)}개")
                        normalized = filtered[:top_k]
                else:
                    normalized = converted_results

                # 선택된 문서 강제 추가 (사용자 요청 우선 처리)
                if selected_filename:
                    # v2.1: 명확한 selected_doc 처리
                    # 1. 병렬 실행에서 이미 가져온 경우 사용
                    if selected_doc:
                        logger.info(f"✅ 병렬/캐시에서 선택 문서 발견: {selected_filename}")
                    else:
                        # 2. BM25 결과에서 먼저 찾기
                        for result in converted_results:
                            if result.get("filename") == selected_filename:
                                selected_doc = result.copy()
                                selected_doc["score"] = HybridSearchConfig.SELECTED_DOC_SCORE
                                logger.info(f"✅ BM25 결과에서 선택 문서 발견: {selected_filename}")
                                break

                        # 3. BM25에 없으면 MetadataDB에서 직접 가져오기
                        if not selected_doc:
                            logger.info(f"🔍 BM25에 없음, MetadataDB에서 직접 검색: {selected_filename}")
                            selected_doc = self._find_selected_document(selected_filename)

                    # 4. 찾았으면 최상위에 강제 추가
                    if selected_doc:
                        # 기존 결과에서 제거 (중복 방지)
                        normalized = [r for r in normalized if r.get("filename") != selected_filename]
                        # 최상위에 강제 추가
                        selected_doc_priority = selected_doc.copy()
                        selected_doc_priority["score"] = HybridSearchConfig.SELECTED_DOC_SCORE
                        normalized = [selected_doc_priority] + normalized[:top_k - 1]
                        logger.info(f"🎯 선택된 문서 최상위 강제 추가: {selected_filename} (score={HybridSearchConfig.SELECTED_DOC_SCORE})")
                    else:
                        logger.warning(f"⚠️ 선택된 문서 '{selected_filename}'를 찾지 못함 (BM25/MetadataDB 모두)")

            else:
                # Fallback: MetadataDB 기반 (비권장, 500자 제한)
                logger.warning("⚠️ BM25 비활성화, MetadataDB 폴백 모드 (text_preview 500자 제한)")
                filters = self.parser.parse_filters(query)
                year = filters.get("year")
                drafter = filters.get("drafter")

                results = self.metadata_db.search_documents(
                    year=year,
                    drafter=drafter,
                    limit=top_k * 3,
                )

                normalized = []
                for doc in results:
                    snippet = doc.get("text_preview") or doc.get("content") or ""  # 전체 문서 사용
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
                        },
                    })

                normalized.sort(key=lambda x: x["score"], reverse=True)
                normalized = normalized[:top_k]

            # ✨ 파일명 매칭 보너스 (쿼리와 파일명이 유사하면 점수 증가)
            if not selected_filename:  # 선택된 문서가 없을 때만 적용
                normalized = self._apply_filename_bonus(query, normalized)
                # 보너스 적용 후 재정렬
                normalized.sort(key=lambda x: x["score"], reverse=True)

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
                "delta13": max(0.0, top1 - top3),
            }

            results_with_stats = ResultsWithStats(normalized, score_stats)

            backend = "BM25" if (self.use_bm25 and self.bm25) else "MetadataDB"
            logger.info(
                f"🔍 HybridRetriever ({backend}): {len(normalized)}건 검색 완료 "
                f"(top1={top1:.2f}, delta12={score_stats['delta12']:.2f})",
            )

            # 검색 품질 로깅 (Phase 3 추가)
            try:
                from app.rag.monitoring.search_quality_logger import SearchQualityLogger
                quality_logger = SearchQualityLogger()
                quality_logger.log_search(
                    query=query,
                    results=normalized,
                    score_stats=score_stats,
                    metadata={"mode": mode, "backend": backend},
                )
            except Exception as e:
                logger.debug(f"품질 로깅 실패 (무시): {e}")

            return results_with_stats

        except Exception as e:
            logger.error(f"❌ 검색 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _apply_filename_bonus(self, query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        query_normalized = re.sub(r"[^\w\s]", " ", query.lower())
        query_tokens = set(query_normalized.split())

        if not query_tokens:
            return results

        for result in results:
            filename = result.get("filename", "")
            if not filename:
                continue

            # 파일명 정규화
            # 1. 날짜 패턴 제거 (YYYY-MM-DD_)
            filename_clean = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", filename)
            # 2. 확장자 제거
            filename_clean = re.sub(r"\.\w+$", "", filename_clean)
            # 3. 언더스코어를 공백으로 치환
            filename_clean = filename_clean.replace("_", " ")
            # 4. 특수문자 제거 후 소문자 변환
            filename_clean = re.sub(r"[^\w\s]", " ", filename_clean.lower())

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

            # 보너스 점수 계산 (유사도 기반)
            bonus = 0.0
            if similarity >= ScoringConfig.HIGH_SIM_THRESHOLD:
                bonus = ScoringConfig.HIGH_SIM_BONUS
            elif similarity >= ScoringConfig.MED_SIM_THRESHOLD:
                bonus = ScoringConfig.MED_SIM_BONUS
            elif similarity >= ScoringConfig.LOW_SIM_THRESHOLD:
                bonus = ScoringConfig.LOW_SIM_BONUS

            # 보너스 적용
            if bonus > 0:
                original_score = result["score"]
                result["score"] += bonus
                logger.info(
                    f"📈 파일명 보너스: {filename[:40]} | "
                    f"유사도={similarity:.2f} | "
                    f"점수 {original_score:.2f} → {result['score']:.2f} (+{bonus:.1f})",
                )

        return results

    def get_metrics(self) -> dict[str, Any]:
        """검색 엔진 메트릭 조회 (v2.0 추가)

        Returns:
            메트릭 딕셔너리:
            - exact_match: ExactMatchRetriever 메트릭
            - bm25: BM25Store 통계
            - retriever_config: 설정 정보
        """
        metrics = {
            "retriever_config": {
                "use_bm25": self.use_bm25,
                "exact_match_enabled": self.exact_match_enabled,
                "enable_parallel": self.enable_parallel,
                "retrieve_topk": self.retrieve_topk,
                "display_limit": self.display_limit,
                "snippet_max_length": self.snippet_max_length,
            },
        }

        # ExactMatch 메트릭
        if self.exact_match_enabled and self.exact_match:
            metrics["exact_match"] = self.exact_match.get_metrics()

        # BM25 통계
        if self.use_bm25 and self.bm25:
            metrics["bm25"] = {
                "total_documents": len(self.bm25.documents),
                "index_path": str(self.bm25.index_path),
            }

        return metrics
