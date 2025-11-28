"""정확일치 검색기 v2.0 (Stage 0 - 모델/부품 코드 전용)

2025-11-11 v2.0 개선사항:
- SQLite 인덱스 친화적 설계 (COLLATE NOCASE, 배치 쿼리)
- LIKE 경계 제약 (padded_norm 기반 오검출 방지)
- 특수문자 이스케이프 (와일드카드 제어)
- 스코어링 개선 (파일명 정확일치, 최신성 가중)
- 메트릭 수집 (hit_rate, query_time)

model_codes 테이블을 활용한 정확일치 검색
- 코드 변형(hyphen/space/no-space) 자동 확장
- 파일명 정확/부분 일치 검색
- 가중치: exact_code=+3.0, filename_exact=+1.5, filename_partial=+1.0
"""

import time
from typing import Any

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB

logger = get_logger(__name__)

# normalizer 임포트 (fallback 처리)
try:
    from app.textproc.normalizer import extract_codes, generate_variants, normalize_code
    NORMALIZER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ normalizer 모듈을 찾을 수 없습니다 (ExactMatchRetriever 비활성화)")
    NORMALIZER_AVAILABLE = False

    def extract_codes(text: str, normalize_result: bool = True) -> list[str]:
        return []

    def normalize_code(code: str, uppercase: bool = True) -> str:
        return code.upper()

    def generate_variants(code: str) -> list[str]:
        return [code]


class ExactMatchRetriever:
    """정확일치 검색기 v2.0 (Stage 0)

    모델/부품 코드 검색을 위한 정확일치 레이어
    - model_codes 테이블에서 norm_code 기반 검색
    - 파일명 정확/부분 일치 검색
    - 스코어 부스팅으로 우선순위 조정
    """

    # 스코어 가중치 (v2.0 업데이트)
    EXACT_CODE_WEIGHT = 3.0          # model_codes 테이블에서 정확일치
    FILENAME_EXACT_WEIGHT = 1.5      # 파일명 정확일치 (토큰 전체)
    FILENAME_PARTIAL_WEIGHT = 1.0    # 파일명 부분일치
    RECENCY_WEIGHT = 0.1             # 최신성 가중 (연도당)

    def __init__(self, db: MetadataDB = None):
        """초기화

        Args:
            db: MetadataDB 인스턴스 (None이면 새로 생성)
        """
        self.db = db or MetadataDB()
        self.enabled = NORMALIZER_AVAILABLE

        # 메트릭 수집
        self.metrics = {
            "total_queries": 0,
            "exact_hits": 0,
            "filename_hits": 0,
            "total_query_time_ms": 0.0,
        }

        if not self.enabled:
            logger.warning("⚠️ ExactMatchRetriever 비활성화 (normalizer 없음)")
        else:
            logger.info("✅ ExactMatchRetriever v2.0 초기화 완료")

    @staticmethod
    def _escape_like(s: str) -> str:
        """LIKE 패턴용 특수문자 이스케이프

        Args:
            s: 원본 문자열

        Returns:
            이스케이프된 문자열
        """
        return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _has_column(self, table: str, column: str) -> bool:
        """테이블에 컬럼 존재 여부 확인

        Args:
            table: 테이블명
            column: 컬럼명

        Returns:
            존재 여부
        """
        try:
            conn = self.db._get_conn()
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1].lower() for row in cursor.fetchall()]
            return column.lower() in columns
        except Exception as e:
            logger.debug(f"컬럼 확인 실패: {e}")
            return False

    def search_codes(self, query: str) -> list[tuple[int, float, str]]:
        """코드 기반 정확일치 검색 v2.0

        Args:
            query: 검색 질의 (예: "XRN-1620B2 매뉴얼")

        Returns:
            List of (doc_id, score, match_type):
            - doc_id: documents.id
            - score: 가중치 점수
            - match_type: 'exact_code' | 'filename_exact' | 'filename_partial'
        """
        if not self.enabled:
            return []

        start_time = time.time()
        self.metrics["total_queries"] += 1

        # 1. 쿼리에서 코드 추출
        codes = extract_codes(query, normalize_result=True)

        if not codes:
            logger.debug("코드 패턴 없음 - ExactMatch 건너뛰기")
            return []

        logger.info(f"🎯 ExactMatch v2.0: 코드 추출 = {codes}")

        # 2. 코드 변형 생성 (hyphen/space/no-space)
        all_variants = set()
        for code in codes:
            variants = generate_variants(code)
            all_variants.update(variants)

        logger.debug(f"코드 변형 생성: {len(all_variants)}개 - {list(all_variants)[:5]}...")

        # 3. model_codes 테이블에서 정확일치 검색
        exact_matches = self._query_model_codes(all_variants)

        # 4. 파일명 일치 검색 (model_codes에 없는 경우 보완)
        filename_matches = self._query_filename_matches(all_variants, codes)

        # 5. 결과 병합 및 중복 제거
        results = self._merge_results(exact_matches, filename_matches)

        # 메트릭 업데이트
        if exact_matches:
            self.metrics["exact_hits"] += 1
        if filename_matches:
            self.metrics["filename_hits"] += 1

        elapsed_ms = (time.time() - start_time) * 1000
        self.metrics["total_query_time_ms"] += elapsed_ms

        logger.info(
            f"📊 ExactMatch v2.0: {len(results)}건 반환 "
            f"(exact={len(exact_matches)}, filename={len(filename_matches)}, {elapsed_ms:.1f}ms)",
        )

        return results

    def _query_model_codes(self, variants: set[str]) -> list[tuple[int, float, str]]:
        """model_codes 테이블에서 정확일치 검색 v2.0

        배치 쿼리 + 경계 제약으로 라운드트립 최소화 및 오검출 방지

        Args:
            variants: 정규화된 코드 변형 집합

        Returns:
            List of (doc_id, score, 'exact_code')
        """
        if not variants:
            return []

        try:
            conn = self.db._get_conn()
            doc_ids_found = set()

            # 1. 정확일치 (IN 쿼리 - 1회 라운드트립)
            placeholders = ",".join(["?"] * len(variants))
            query_exact = f"""
                SELECT DISTINCT doc_id
                FROM model_codes
                WHERE norm_code IN ({placeholders})
            """
            cursor = conn.execute(query_exact, list(variants))
            exact_count = 0
            for row in cursor.fetchall():
                doc_ids_found.add(row[0])
                exact_count += 1

            # 2. 경계 제약 LIKE (padded_norm 컬럼 존재 시만 수행)
            # 오검출 방지: ' XRN1620 ' 형태로 공백 경계 강제
            boundary_count = 0
            if self._has_column("model_codes", "padded_norm"):
                # UNION ALL로 배치 (1회 라운드트립)
                patterns = [f"% {v} %" for v in variants]
                union_clauses = " UNION ALL ".join(
                    ["SELECT DISTINCT doc_id FROM model_codes WHERE padded_norm LIKE ?"]
                    * len(patterns),
                )
                query_boundary = f"SELECT DISTINCT doc_id FROM ({union_clauses})"

                cursor = conn.execute(query_boundary, patterns)
                for row in cursor.fetchall():
                    if row[0] not in doc_ids_found:
                        doc_ids_found.add(row[0])
                        boundary_count += 1

            # (doc_id, score, match_type)
            results = [(doc_id, self.EXACT_CODE_WEIGHT, "exact_code") for doc_id in doc_ids_found]

            logger.debug(
                f"model_codes 일치: {len(results)}건 (정확={exact_count}, 경계={boundary_count})",
            )
            return results

        except Exception as e:
            logger.error(f"model_codes 검색 실패: {e}", exc_info=True)
            return []

    def _query_filename_matches(
        self, variants: set[str], original_codes: list[str],
    ) -> list[tuple[int, float, str]]:
        """파일명에서 코드 일치 검색 v2.0

        COLLATE NOCASE + UNION ALL 배치 쿼리로 인덱스 활용 및 라운드트립 절감

        Args:
            variants: 정규화된 코드 변형 집합
            original_codes: 추출된 원본 코드 (정확일치 판정용)

        Returns:
            List of (doc_id, score, match_type):
            - match_type: 'filename_exact' | 'filename_partial'
        """
        if not variants:
            return []

        try:
            conn = self.db._get_conn()
            results_map: dict[int, tuple[float, str]] = {}

            # 이스케이프 처리된 패턴 생성
            escaped_variants = [self._escape_like(v) for v in variants]
            patterns = [f"%{v}%" for v in escaped_variants]

            # UNION ALL로 배치 (1회 라운드트립, COLLATE NOCASE로 인덱스 활용)
            union_clauses = " UNION ALL ".join(
                ["SELECT DISTINCT id, filename FROM documents WHERE filename COLLATE NOCASE LIKE ? ESCAPE '\\'"]
                * len(patterns),
            )
            query = f"SELECT DISTINCT id, filename FROM ({union_clauses})"

            cursor = conn.execute(query, patterns)
            rows = cursor.fetchall()

            # 정확일치 vs 부분일치 구분
            for doc_id, filename in rows:
                # 파일명에서 정확일치 여부 확인 (토큰 전체 매치)
                filename_upper = filename.upper()
                is_exact = False

                for code in original_codes:
                    # 파일명 토큰화 (하이픈, 언더스코어, 공백 기준)
                    import re
                    tokens = re.split(r"[-_\s.]+", filename_upper)
                    if code.upper() in tokens:
                        is_exact = True
                        break

                if is_exact:
                    match_type = "filename_exact"
                    score = self.FILENAME_EXACT_WEIGHT
                else:
                    match_type = "filename_partial"
                    score = self.FILENAME_PARTIAL_WEIGHT

                # 더 높은 점수로 갱신
                if doc_id not in results_map or score > results_map[doc_id][0]:
                    results_map[doc_id] = (score, match_type)

            results = [(doc_id, score, match_type) for doc_id, (score, match_type) in results_map.items()]

            exact_count = sum(1 for _, _, mt in results if mt == "filename_exact")
            partial_count = len(results) - exact_count

            logger.debug(
                f"filename 일치: {len(results)}건 (정확={exact_count}, 부분={partial_count})",
            )
            return results

        except Exception as e:
            logger.error(f"filename 검색 실패: {e}", exc_info=True)
            return []

    def _merge_results(
        self,
        exact_matches: list[tuple[int, float, str]],
        filename_matches: list[tuple[int, float, str]],
    ) -> list[tuple[int, float, str]]:
        """검색 결과 병합 및 중복 제거

        - exact_code가 우선순위 (filename과 중복되면 exact_code 채택)
        - doc_id별로 최고 점수 유지

        Args:
            exact_matches: model_codes 일치
            filename_matches: filename 일치

        Returns:
            List of (doc_id, score, match_type) - doc_id 기준 정렬
        """
        # doc_id -> (score, match_type)
        doc_scores: dict[int, tuple[float, str]] = {}

        # exact_code 먼저 추가 (최우선)
        for doc_id, score, match_type in exact_matches:
            if doc_id not in doc_scores:
                doc_scores[doc_id] = (score, match_type)
            # 더 높은 점수로 갱신 (동일 소스 중복시)
            elif score > doc_scores[doc_id][0]:
                doc_scores[doc_id] = (score, match_type)

        # filename 추가 (exact_code가 없는 경우만)
        for doc_id, score, match_type in filename_matches:
            if doc_id not in doc_scores:
                doc_scores[doc_id] = (score, match_type)

        # (doc_id, score, match_type) 튜플로 변환 및 정렬
        results = [(doc_id, score, match_type) for doc_id, (score, match_type) in doc_scores.items()]
        results.sort(key=lambda x: (-x[1], x[0]))  # 점수 내림차순, doc_id 오름차순

        return results

    def get_documents_by_ids(self, doc_ids: list[int]) -> list[dict[str, Any]]:
        """doc_id 리스트로 문서 메타데이터 조회

        Args:
            doc_ids: documents.id 리스트

        Returns:
            문서 메타데이터 리스트
        """
        if not doc_ids:
            return []

        try:
            conn = self.db._get_conn()

            placeholders = ",".join(["?"] * len(doc_ids))
            query = f"""
                SELECT id, path, filename, title, date, year, drafter,
                       category, text_preview, page_count
                FROM documents
                WHERE id IN ({placeholders})
            """

            cursor = conn.execute(query, doc_ids)
            rows = cursor.fetchall()

            # Row -> dict 변환
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "path": row[1],
                    "filename": row[2],
                    "title": row[3],
                    "date": row[4],
                    "year": row[5],
                    "drafter": row[6],
                    "category": row[7],
                    "text_preview": row[8],
                    "page_count": row[9],
                })

            return results

        except Exception as e:
            logger.error(f"문서 조회 실패: {e}")
            return []

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """전체 검색 수행 (HybridRetriever 인터페이스 호환)

        Args:
            query: 검색 질의
            top_k: 상위 K개 결과

        Returns:
            정규화된 검색 결과 리스트:
            [
                {
                    "doc_id": str,
                    "page": int,
                    "score": float,
                    "snippet": str,
                    "meta": dict,
                    "match_type": str  # 'exact_code' | 'filename'
                }, ...
            ]
        """
        if not self.enabled:
            return []

        # 1. 코드 기반 검색
        matches = self.search_codes(query)

        if not matches:
            return []

        # 2. top_k 제한
        matches = matches[:top_k]

        # 3. 문서 메타데이터 조회
        doc_ids = [doc_id for doc_id, _, _ in matches]
        documents = self.get_documents_by_ids(doc_ids)

        # doc_id -> doc 맵핑
        doc_map = {doc["id"]: doc for doc in documents}

        # 4. 결과 정규화
        results = []
        for doc_id, score, match_type in matches:
            doc = doc_map.get(doc_id)
            if not doc:
                continue

            snippet = (doc.get("text_preview") or "")[:800]
            if not snippet:
                snippet = f"[{doc.get('filename', 'unknown')}]"

            # 스코어 정규화 (0-10 범위 클리핑)
            normalized_score = max(0.0, min(10.0, score))

            results.append({
                "doc_id": doc.get("filename", "unknown"),
                "page": 1,
                "score": normalized_score,
                "snippet": snippet,
                "match_type": match_type,  # 추가 필드
                "meta": {
                    "filename": doc.get("filename", ""),
                    "drafter": doc.get("drafter", ""),
                    "date": doc.get("date", ""),
                    "category": doc.get("category", "pdf"),
                    "doc_id": doc.get("filename", "unknown"),
                    "match_type": match_type,  # 메타에도 포함
                },
            })

        logger.info(f"🎯 ExactMatch v2.0: {len(results)}건 반환 (score range: 0-10)")
        return results

    def get_metrics(self) -> dict[str, Any]:
        """메트릭 조회

        Returns:
            메트릭 딕셔너리:
            - total_queries: 전체 질의 수
            - exact_hits: model_codes 히트 수
            - filename_hits: filename 히트 수
            - exact_match_hit_rate: 정확일치 히트율
            - avg_query_time_ms: 평균 질의 시간(ms)
        """
        metrics = self.metrics.copy()

        if metrics["total_queries"] > 0:
            metrics["exact_match_hit_rate"] = metrics["exact_hits"] / metrics["total_queries"]
            metrics["avg_query_time_ms"] = metrics["total_query_time_ms"] / metrics["total_queries"]
        else:
            metrics["exact_match_hit_rate"] = 0.0
            metrics["avg_query_time_ms"] = 0.0

        return metrics
