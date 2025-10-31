"""정확일치 검색기 (Stage 0 - 모델/부품 코드 전용)

model_codes 테이블을 활용한 정확일치 검색
- 코드 변형(hyphen/space/no-space) 자동 확장
- 파일명 정확/부분 일치 검색
- 가중치: exact_code=+3.0, filename_hit=+1.0
"""

from typing import List, Dict, Any, Tuple, Set
from app.core.logging import get_logger
from modules.metadata_db import MetadataDB

logger = get_logger(__name__)

# normalizer 임포트 (fallback 처리)
try:
    from app.textproc.normalizer import extract_codes, normalize_code, generate_variants
    NORMALIZER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ normalizer 모듈을 찾을 수 없습니다 (ExactMatchRetriever 비활성화)")
    NORMALIZER_AVAILABLE = False

    def extract_codes(text: str, normalize_result: bool = True) -> List[str]:
        return []

    def normalize_code(code: str, uppercase: bool = True) -> str:
        return code.upper()

    def generate_variants(code: str) -> List[str]:
        return [code]


class ExactMatchRetriever:
    """정확일치 검색기 (Stage 0)

    모델/부품 코드 검색을 위한 정확일치 레이어
    - model_codes 테이블에서 norm_code 기반 검색
    - 파일명 정확/부분 일치 검색
    - 스코어 부스팅으로 우선순위 조정
    """

    # 스코어 가중치
    EXACT_CODE_WEIGHT = 3.0      # model_codes 테이블에서 정확일치
    FILENAME_HIT_WEIGHT = 1.0    # 파일명에 코드 포함

    def __init__(self, db: MetadataDB = None):
        """초기화

        Args:
            db: MetadataDB 인스턴스 (None이면 새로 생성)
        """
        self.db = db or MetadataDB()
        self.enabled = NORMALIZER_AVAILABLE

        if not self.enabled:
            logger.warning("⚠️ ExactMatchRetriever 비활성화 (normalizer 없음)")
        else:
            logger.info("✅ ExactMatchRetriever 초기화 완료")

    def search_codes(self, query: str) -> List[Tuple[int, float, str]]:
        """코드 기반 정확일치 검색

        Args:
            query: 검색 질의 (예: "XRN-1620B2 매뉴얼")

        Returns:
            List of (doc_id, score, match_type):
            - doc_id: documents.id
            - score: 가중치 점수
            - match_type: 'exact_code' | 'filename'
        """
        if not self.enabled:
            return []

        # 1. 쿼리에서 코드 추출
        codes = extract_codes(query, normalize_result=True)

        if not codes:
            logger.debug("코드 패턴 없음 - ExactMatch 건너뛰기")
            return []

        logger.info(f"🎯 ExactMatch: 코드 추출 = {codes}")

        # 2. 코드 변형 생성 (hyphen/space/no-space)
        all_variants = set()
        for code in codes:
            variants = generate_variants(code)
            all_variants.update(variants)

        logger.debug(f"코드 변형 생성: {all_variants}")

        # 3. model_codes 테이블에서 정확일치 검색
        exact_matches = self._query_model_codes(all_variants)

        # 4. 파일명 일치 검색 (model_codes에 없는 경우 보완)
        filename_matches = self._query_filename_matches(all_variants)

        # 5. 결과 병합 및 중복 제거
        results = self._merge_results(exact_matches, filename_matches)

        logger.info(f"📊 ExactMatch: {len(results)}건 (exact={len(exact_matches)}, filename={len(filename_matches)})")

        return results

    def _query_model_codes(self, variants: Set[str]) -> List[Tuple[int, float, str]]:
        """model_codes 테이블에서 정확일치 검색 (Patch B: LIKE 확장 추가)

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

            # 1. 정확일치 (IN 쿼리)
            placeholders = ','.join(['?'] * len(variants))
            query_exact = f"""
                SELECT DISTINCT doc_id
                FROM model_codes
                WHERE norm_code IN ({placeholders})
            """
            cursor = conn.execute(query_exact, list(variants))
            rows = cursor.fetchall()

            for row in rows:
                doc_ids_found.add(row[0])

            # 2. LIKE 확장 (Patch B: 부분 일치로 재현율 증대)
            for variant in variants:
                query_like = """
                    SELECT DISTINCT doc_id
                    FROM model_codes
                    WHERE norm_code LIKE ?
                """
                cursor = conn.execute(query_like, (f'%{variant}%',))
                rows = cursor.fetchall()

                for row in rows:
                    doc_ids_found.add(row[0])

            # (doc_id, score, match_type)
            results = [(doc_id, self.EXACT_CODE_WEIGHT, 'exact_code') for doc_id in doc_ids_found]

            logger.debug(f"model_codes 일치: {len(results)}건 (exact + LIKE 확장)")
            return results

        except Exception as e:
            logger.error(f"model_codes 검색 실패: {e}")
            return []

    def _query_filename_matches(self, variants: Set[str]) -> List[Tuple[int, float, str]]:
        """파일명에서 코드 일치 검색

        Args:
            variants: 정규화된 코드 변형 집합

        Returns:
            List of (doc_id, score, 'filename')
        """
        if not variants:
            return []

        try:
            conn = self.db._get_conn()
            results = []

            # 각 변형에 대해 LIKE 검색 (대소문자 무시)
            for variant in variants:
                query = """
                    SELECT DISTINCT id
                    FROM documents
                    WHERE UPPER(filename) LIKE ?
                """

                # 변형의 대소문자 버전들 모두 시도
                patterns = [
                    f"%{variant}%",
                    f"%{variant.lower()}%",
                    f"%{variant.upper()}%"
                ]

                for pattern in patterns:
                    cursor = conn.execute(query, (pattern,))
                    rows = cursor.fetchall()

                    for row in rows:
                        results.append((row[0], self.FILENAME_HIT_WEIGHT, 'filename'))

            logger.debug(f"filename 일치: {len(results)}건")
            return results

        except Exception as e:
            logger.error(f"filename 검색 실패: {e}")
            return []

    def _merge_results(
        self,
        exact_matches: List[Tuple[int, float, str]],
        filename_matches: List[Tuple[int, float, str]]
    ) -> List[Tuple[int, float, str]]:
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
        doc_scores: Dict[int, Tuple[float, str]] = {}

        # exact_code 먼저 추가 (최우선)
        for doc_id, score, match_type in exact_matches:
            if doc_id not in doc_scores:
                doc_scores[doc_id] = (score, match_type)
            else:
                # 더 높은 점수로 갱신 (동일 소스 중복시)
                if score > doc_scores[doc_id][0]:
                    doc_scores[doc_id] = (score, match_type)

        # filename 추가 (exact_code가 없는 경우만)
        for doc_id, score, match_type in filename_matches:
            if doc_id not in doc_scores:
                doc_scores[doc_id] = (score, match_type)

        # (doc_id, score, match_type) 튜플로 변환 및 정렬
        results = [(doc_id, score, match_type) for doc_id, (score, match_type) in doc_scores.items()]
        results.sort(key=lambda x: (-x[1], x[0]))  # 점수 내림차순, doc_id 오름차순

        return results

    def get_documents_by_ids(self, doc_ids: List[int]) -> List[Dict[str, Any]]:
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

            placeholders = ','.join(['?'] * len(doc_ids))
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
                    'id': row[0],
                    'path': row[1],
                    'filename': row[2],
                    'title': row[3],
                    'date': row[4],
                    'year': row[5],
                    'drafter': row[6],
                    'category': row[7],
                    'text_preview': row[8],
                    'page_count': row[9]
                })

            return results

        except Exception as e:
            logger.error(f"문서 조회 실패: {e}")
            return []

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
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
        doc_map = {doc['id']: doc for doc in documents}

        # 4. 결과 정규화
        results = []
        for doc_id, score, match_type in matches:
            doc = doc_map.get(doc_id)
            if not doc:
                continue

            snippet = (doc.get('text_preview') or "")[:800]
            if not snippet:
                snippet = f"[{doc.get('filename', 'unknown')}]"

            results.append({
                "doc_id": doc.get("filename", "unknown"),
                "page": 1,
                "score": score,
                "snippet": snippet,
                "match_type": match_type,  # 추가 필드
                "meta": {
                    "filename": doc.get("filename", ""),
                    "drafter": doc.get("drafter", ""),
                    "date": doc.get("date", ""),
                    "category": doc.get("category", "pdf"),
                    "doc_id": doc.get("filename", "unknown"),
                    "match_type": match_type  # 메타에도 포함
                }
            })

        logger.info(f"🎯 ExactMatch: {len(results)}건 반환")
        return results
