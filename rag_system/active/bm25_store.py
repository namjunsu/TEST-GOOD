"""
한국어 BM25 검색 구현
kiwipiepy 기반 토크나이저 사용
"""

import logging
import math
import pickle
import re
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.core.logging import get_logger


def _resolve_doc_id(metadata: dict, doc_idx: int) -> str:
    """DocStore/BM25/FAISS 공통 doc_id 생성 규칙

    Args:
        metadata: 문서 메타데이터 (id 필드 필수)
        doc_idx: 문서 인덱스 (폴백용)

    Returns:
        정규화된 doc_id (문자열)

    Raises:
        ValueError: metadata['id']가 없는 경우

    Note:
        - 1순위: metadata["id"] (DB PK) → 문자열 변환
        - metadata.db의 INTEGER PK를 기준으로 통일
        - id 없는 문서는 구조적 문제로 간주하여 에러 발생
    """
    db_id = metadata.get("id")
    if db_id is None:
        raise ValueError(
            f"metadata['id'] 누락 (doc_idx={doc_idx}). "
            f"DocStore 기반 시스템에서 id는 필수입니다. meta={metadata}",
        )
    return str(db_id)


# 한국어 불용어 세트 (방송·기술 문서 특화)
KOREAN_STOPWORDS = {
    # 조사·어미
    "은", "는", "이", "가", "을", "를", "에", "에서", "으로", "로",
    "에게", "께", "와", "과", "및", "또는", "또", "그리고",
    "보다", "부터", "까지", "도", "만", "의", "에는", "으로는",

    # 형식 동사 / 보조 동사 (의미 약함)
    "하다", "된다", "되며", "되어", "위해", "통해", "대해", "대한",
    "있는", "없는", "있다", "없다", "위한", "통한",

    # 보고서 일반 표현
    "관련", "사항", "내용", "부분", "경우", "것으로", "것이다",
    "따라", "따른", "관한", "등", "등의", "등을", "위하여",

    # 일반 대명사·수식어
    "그", "저", "이것", "그것", "여기", "거기", "모든", "각", "매",

    # 기타 (빈출 무의미 토큰)
    "년", "월", "일", "번", "개", "건", "명", "회", "차",
}

# 업무 핵심 키워드 화이트리스트 (절대 불용어로 지정하지 않음)
BUSINESS_KEYWORDS_WHITELIST = {
    # 기술 장비 관련
    "교체", "수리", "고장", "점검", "구매", "설치", "유지보수",
    "모듈", "신호", "장비", "모델", "부품", "소모품",

    # 방송 장비명
    "SPG", "ECO", "DVR", "NLE", "UPS", "LED", "BNC",
    "모니터", "케이블", "카메라", "마이크", "헬리캠", "드론",
    "워크스테이션", "서버", "스위처", "라우터", "컨버터",

    # 장소/팀명
    "광화문", "스튜디오", "부조정실", "편집실", "중계차",
    "영상취재팀", "기술관리팀", "영상편집팀",

    # 문서 형식 (의미있는)
    "검토서", "계약서", "견적서", "사양서", "내역서",
}

# kiwipiepy 토크나이저 (한국어 특화)
try:
    from kiwipiepy import Kiwi
    KIWIPIEPY_AVAILABLE = True
except ImportError:
    KIWIPIEPY_AVAILABLE = False
    get_logger(__name__).warning("kiwipiepy 사용 불가(AVX-VNNI 등), basic tokenizer로 동작")


# 토큰화 캐싱용 별도 함수
@lru_cache(maxsize=2048)
def _cached_basic_tokenize(text: str, pattern: str, min_len: int) -> tuple:
    """기본 토크나이저 (캐시됨)"""
    text = re.sub(pattern, " ", text)
    tokens = [t.lower() for t in text.split() if len(t) >= min_len]
    return tuple(tokens)


class KoreanTokenizer:
    """한국어 토크나이저"""

    # 토크나이저 상수
    MIN_TOKEN_LENGTH = 1
    VALID_POS_TAGS = ["N", "V", "A", "M"]  # 명사, 동사, 형용사, 수식언
    TOKEN_PATTERN = r"[^\w\s가-힣]"  # 한글, 영문, 숫자 외 제거
    CACHE_SIZE = 2048  # 토큰 캐시 크기

    # 클래스 속성 타입 선언
    logger: logging.Logger
    _compiled_token_pattern: re.Pattern[str]
    tokenize_count: int
    cache_hits: int
    kiwi: Optional[Any]  # kiwipiepy.Kiwi
    use_kiwi: bool

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

        # 패턴 컴파일
        self._compiled_token_pattern = re.compile(self.TOKEN_PATTERN)

        # 성능 통계
        self.tokenize_count = 0
        self.cache_hits = 0

        if KIWIPIEPY_AVAILABLE:
            try:
                # AVX-VNNI 문제 해결을 위해 num_workers=0으로 설정
                self.kiwi = Kiwi(num_workers=0)
                self.use_kiwi = True
                self.logger.info("Kiwi 한국어 토크나이저 로드 완료")
            except Exception as e:
                self.logger.warning(f"Kiwi 초기화 실패, 기본 토크나이저 사용: {e}")
                self.use_kiwi = False
        else:
            self.use_kiwi = False

    def tokenize(self, text: str) -> list[str]:
        """텍스트를 토큰으로 분할"""
        self.tokenize_count += 1

        if not text or not text.strip():
            return []

        try:
            if self.use_kiwi:
                # Kiwi로 형태소 분석
                result = self.kiwi.analyze(text)
                tokens = []
                for token, pos, _, _ in result[0][0]:  # 첫 번째 분석 결과 사용
                    # 의미있는 품사만 선택
                    if pos[0] in self.VALID_POS_TAGS:
                        tokens.append(token.lower())
                return tokens
            else:
                # 기본 토크나이저: 캐시된 함수 사용
                tokens = list(_cached_basic_tokenize(
                    text,
                    self.TOKEN_PATTERN,
                    self.MIN_TOKEN_LENGTH,
                ))
                return tokens

        except Exception as e:
            self.logger.error(f"토큰화 실패: {e}")
            # fallback
            text = self._compiled_token_pattern.sub(" ", text)
            return [t.lower() for t in text.split() if len(t) > self.MIN_TOKEN_LENGTH]


def build_dynamic_stopwords(doc_freqs: dict[str, int], n_docs: int,
                           df_threshold: float = 0.75, max_token_len: int = 3,
                           whitelist: set = None) -> set:
    """문서 빈도 기반 동적 불용어 도출

    Args:
        doc_freqs: 토큰별 문서 빈도
        n_docs: 전체 문서 수
        df_threshold: 불용어로 간주할 문서 빈도 비율 (기본 0.75 = 75%, 기존 0.85에서 강화)
        max_token_len: 불용어 후보로 고려할 최대 토큰 길이 (기본 3, 기존 2에서 확장)
        whitelist: 절대 불용어로 지정하지 않을 키워드 세트

    Returns:
        동적 불용어 세트
    """
    stopwords = set()
    whitelist = whitelist or set()

    for token, df in doc_freqs.items():
        # 화이트리스트에 있으면 스킵
        if token in whitelist or token.upper() in whitelist:
            continue

        df_ratio = df / n_docs

        # 높은 문서 빈도 + 짧은 토큰 → 불용어 후보
        if df_ratio >= df_threshold and 1 <= len(token) <= max_token_len:
            stopwords.add(token)

    return stopwords


class BM25Store:
    """BM25 키워드 검색 구현"""

    # BM25 파라미터 기본값
    DEFAULT_K1 = 1.2  # 용어 빈도 포화 매개변수
    DEFAULT_B = 0.75  # 문서 길이 정규화 매개변수
    DEFAULT_INDEX_PATH = "var/index/bm25_index.pkl"

    # 클래스 속성 타입 선언
    index_path: Path
    k1: float
    b: float
    idf_mode: str
    stopwords: set[str]
    logger: logging.Logger
    tokenizer: KoreanTokenizer
    documents: list[str]
    metadata: list[dict[str, Any]]
    term_freqs: list[dict[str, int]]
    doc_freqs: defaultdict[str, int]
    doc_lens: list[int]
    avg_doc_len: float
    vocab: set[str]
    search_count: int
    total_search_time: float
    index_time: float

    def __init__(
        self,
        index_path: Optional[str] = None,
        k1: Optional[float] = None,
        b: Optional[float] = None,
        idf_mode: str = "clipped",  # "rsj" | "log1p" | "clipped"
        stopwords: Optional[set[str]] = None,
    ) -> None:
        self.index_path = Path(index_path) if index_path else Path(self.DEFAULT_INDEX_PATH)
        self.k1 = k1 if k1 is not None else self.DEFAULT_K1
        self.b = b if b is not None else self.DEFAULT_B
        self.idf_mode = idf_mode
        self.stopwords = stopwords or set()

        self.logger = get_logger(__name__)
        self.tokenizer = KoreanTokenizer()

        # BM25 인덱스
        self.documents = []  # 원본 문서들
        self.metadata = []   # 문서 메타데이터
        self.term_freqs = []  # 각 문서별 용어 빈도
        self.doc_freqs = defaultdict(int)  # 용어별 문서 빈도
        self.doc_lens = []   # 각 문서의 길이
        self.avg_doc_len = 0.0  # 평균 문서 길이
        self.vocab = set()   # 전체 어휘

        # 성능 통계
        self.search_count = 0
        self.total_search_time = 0.0
        self.index_time = 0.0

        self._load_or_create_index()

    def _compute_idf(self, token: str, n_docs: int) -> float:
        """토큰별 IDF 계산 (모드별 분기)"""
        df = self.doc_freqs.get(token, 0)
        if df == 0:
            return 0.0

        # Robertson-Spärck Jones 기본형
        rsj = math.log((n_docs - df + 0.5) / (df + 0.5))

        if self.idf_mode == "rsj":
            return rsj
        elif self.idf_mode == "log1p":
            # 항상 양수, 극단적 DF에 덜 민감
            return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        elif self.idf_mode == "adaptive":
            # 적응형 IDF: 고빈도 토큰에 페널티 적용
            df_ratio = df / n_docs
            if df_ratio > 0.8:  # 80% 이상 문서 등장 → 불용어 (0점)
                return 0.0
            elif df_ratio > 0.5:  # 50-80% → 절반 페널티
                return max(0.0, rsj) * 0.5
            else:
                return max(0.0, rsj)
        elif self.idf_mode == "clipped":
            # 음수 IDF는 0으로 클리핑 (불용어 효과)
            return max(0.0, rsj)
        else:
            # 알 수 없는 모드는 기본값으로 클리핑
            self.logger.warning(f"Unknown IDF mode: {self.idf_mode}, using clipped")
            return max(0.0, rsj)

    def _filter_tokens(self, tokens: list[str]) -> list[str]:
        """불용어 필터링"""
        if not self.stopwords:
            return tokens
        return [t for t in tokens if t not in self.stopwords]

    def _get_token_weight(self, token: str) -> float:
        """토큰 유형별 가중치 반환

        Args:
            token: 토큰 문자열

        Returns:
            1.0~3.0 범위의 가중치
        """
        import re

        # 장비명/모델명 패턴: 3.0배 (예: PMW-500, HRD-1800)
        if re.match(r"[A-Z]{2,}[-\d]+", token):
            return 3.0

        token_lower = token.lower()

        # 핵심 키워드 (3.0배) - 특정 주제를 명확히 식별하는 단어
        CORE_KEYWORDS = {
            "재난방송", "재난", "dvr", "nvr", "spg", "헬리캠", "드론",
            "disaster", "emergency", "긴급",
        }
        if token_lower in CORE_KEYWORDS:
            return 3.0

        # 전문 키워드 (2.0배) - 방송 장비 관련 특화 단어
        SPECIALIZED_KEYWORDS = {
            "카메라", "렌즈", "마이크", "음향", "영상", "촬영",
            "스튜디오", "방송", "업그레이드", "중계차", "부조정실",
        }
        if token_lower in SPECIALIZED_KEYWORDS:
            return 2.0

        # 일반 키워드 (1.2배) - 너무 흔해서 낮은 가중치
        COMMON_KEYWORDS = {
            "시스템", "구매", "검토", "교체", "수리", "설치",
            "장비", "소모품", "유지보수", "점검",
        }
        if token_lower in COMMON_KEYWORDS:
            return 1.2

        # 기본 키워드: 1.0배
        return 1.0

    def _load_or_create_index(self):
        """기존 인덱스 로드 또는 새 인덱스 생성"""
        if self.index_path.exists():
            try:
                self.load_index()
                self.logger.info(f"BM25 인덱스 로드 완료: {len(self.documents)}개 문서")
            except Exception as e:
                self.logger.error(f"BM25 인덱스 로드 실패: {e}")
                self._create_new_index()
        else:
            self._create_new_index()

    def _create_new_index(self):
        """새 인덱스 초기화"""
        self.documents = []
        self.metadata = []
        self.term_freqs = []
        self.doc_freqs = defaultdict(int)
        self.doc_lens = []
        self.avg_doc_len = 0.0
        self.vocab = set()
        self.logger.info("새 BM25 인덱스 생성")

    def save_index(self):
        """인덱스 저장"""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)

            index_data = {
                "documents": self.documents,
                "metadata": self.metadata,
                "term_freqs": self.term_freqs,
                "doc_freqs": dict(self.doc_freqs),
                "doc_lens": self.doc_lens,
                "avg_doc_len": self.avg_doc_len,
                "vocab": list(self.vocab),
                "k1": self.k1,
                "b": self.b,
            }

            with Path(self.index_path).open("wb") as f:
                pickle.dump(index_data, f)

            self.logger.info(f"BM25 인덱스 저장 완료: {self.index_path}")

        except Exception as e:
            self.logger.error(f"BM25 인덱스 저장 실패: {e}")
            raise

    def load_index(self):
        """저장된 인덱스 로드"""
        try:
            with Path(self.index_path).open("rb") as f:
                index_data = pickle.load(f)

            self.documents = index_data["documents"]
            self.metadata = index_data["metadata"]
            self.term_freqs = index_data["term_freqs"]
            self.doc_freqs = defaultdict(int, index_data["doc_freqs"])
            self.doc_lens = index_data["doc_lens"]
            self.avg_doc_len = index_data["avg_doc_len"]
            self.vocab = set(index_data["vocab"])
            self.k1 = index_data.get("k1", 1.2)
            self.b = index_data.get("b", 0.75)

            # 메타데이터 길이 보정 (IndexError 방지)
            n = len(self.documents)
            if len(self.metadata) < n:
                self.metadata += [{} for _ in range(n - len(self.metadata))]
                self.logger.warning(f"메타데이터 부족분 패딩: {n - len(self.metadata)}개")
            elif len(self.metadata) > n:
                self.metadata = self.metadata[:n]
                self.logger.warning(f"메타데이터 초과분 절단: {len(self.metadata) - n}개")

        except Exception as e:
            self.logger.error(f"BM25 인덱스 로드 실패: {e}")
            raise

    def add_documents(self, texts: list[str], metadatas: list[dict[str, Any]], batch_size: int = 100) -> None:
        """문서들을 인덱스에 추가 (배치 처리 최적화)"""
        if len(texts) != len(metadatas):
            raise ValueError("텍스트와 메타데이터 개수가 일치하지 않습니다")

        start_time = time.time()
        total_docs = len(texts)

        try:
            # 배치 처리 (메모리 효율성)
            for batch_start in range(0, total_docs, batch_size):
                batch_end = min(batch_start + batch_size, total_docs)
                batch_texts = texts[batch_start:batch_end]
                batch_metadatas = metadatas[batch_start:batch_end]

                for _doc_idx, (text, metadata) in enumerate(zip(batch_texts, batch_metadatas), start=len(self.documents)):
                    # 토큰화 및 불용어 필터링
                    tokens = self.tokenizer.tokenize(text)
                    tokens = self._filter_tokens(tokens)

                    # doc_id 정규화 (DB PK → 문자열)
                    # 원본 metadata를 변경하지 않고 복사본 생성
                    normalized_metadata = dict(metadata)
                    if "id" in normalized_metadata and not isinstance(normalized_metadata["id"], str):
                        normalized_metadata["id"] = str(normalized_metadata["id"])

                    # 문서 추가
                    self.documents.append(text)
                    self.metadata.append(normalized_metadata)

                    # 용어 빈도 계산
                    term_freq = defaultdict(int)
                    for token in tokens:
                        term_freq[token] += 1
                        self.vocab.add(token)

                    self.term_freqs.append(dict(term_freq))
                    self.doc_lens.append(len(tokens))

                    # 문서 빈도 업데이트
                    for token in set(tokens):
                        self.doc_freqs[token] += 1

                # 배치 로깅
                if (batch_end - batch_start) >= 10:
                    self.logger.debug(f"BM25 인덱싱 진행: {batch_end}/{total_docs}")

            # 평균 문서 길이 재계산 (0 방어)
            if self.doc_lens:
                self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens)
            else:
                self.avg_doc_len = 1.0  # 최소값 1로 고정

            # 인덱싱 시간 기록
            self.index_time += time.time() - start_time

            self.logger.info(f"{total_docs}개 문서 BM25 인덱싱 완료 (총 {len(self.documents)}개, {time.time() - start_time:.2f}초)")

        except Exception as e:
            self.logger.error(f"BM25 문서 추가 실패: {e}")
            raise

    def search(self, query: str, top_k: int = 5, snippet_max: int = 5000, **kwargs) -> list[dict[str, Any]]:
        """BM25 스코어로 문서 검색 (성능 추적 포함)

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            snippet_max: 스니펫 최대 길이 (기본: 5000자)
            **kwargs: 추가 옵션
        """
        if not self.documents:
            return []

        start_time = time.time()
        self.search_count += 1

        try:
            # 쿼리 토큰화 및 불용어 필터링 (빈 쿼리 방어)
            query_tokens = self.tokenizer.tokenize(query)
            query_tokens = self._filter_tokens(query_tokens)
            if not query_tokens:
                return []

            # 각 문서별 BM25 스코어 계산
            scores = []
            n = len(self.documents)  # 총 문서 수

            for doc_idx in range(n):
                score = 0.0
                doc_len = self.doc_lens[doc_idx]

                for token in query_tokens:
                    if token in self.term_freqs[doc_idx]:
                        # 용어 빈도 (TF)
                        tf = self.term_freqs[doc_idx][token]

                        # 문서 빈도 (DF)
                        df = self.doc_freqs.get(token, 0)
                        if df == 0:
                            continue

                        # IDF 계산 (모드별 처리)
                        idf = self._compute_idf(token, n)
                        if idf <= 0.0:
                            continue

                        # BM25 스코어 계산 (avg_doc_len 0 방어)
                        numerator = tf * (self.k1 + 1)
                        avgdl = self.avg_doc_len if self.avg_doc_len > 0 else 1.0
                        denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / avgdl))

                        # 토큰 가중치 적용 (중요 키워드 부스팅)
                        token_weight = self._get_token_weight(token)
                        score += idf * (numerator / denominator) * token_weight

                scores.append((score, doc_idx))

            # 스코어 기준 정렬
            scores.sort(key=lambda x: x[0], reverse=True)

            # 결과 구성 (중복 제거 추가)
            results = []
            seen_ids = set()  # 중복 제거용 세트

            for score, doc_idx in scores:
                if score <= 0:  # 음수 또는 0 스코어 스킵
                    continue

                # 메타데이터 안전 접근 (IndexError 방지)
                metadata = self.metadata[doc_idx] if doc_idx < len(self.metadata) else {}

                # 중복 체크 (doc_id 기준 - DB PK 사용)
                try:
                    doc_id = _resolve_doc_id(metadata, doc_idx)
                except ValueError as e:
                    self.logger.warning(f"doc_id 생성 실패, 건너뜀: {e}")
                    continue

                if doc_id in seen_ids:
                    continue  # 이미 추가된 문서면 스킵
                seen_ids.add(doc_id)

                # top_k 개수 체크
                if len(results) >= top_k:
                    break

                # 스니펫 길이 제한 적용
                content = self.documents[doc_idx]
                snippet = content[:snippet_max] if snippet_max > 0 else content

                result = {
                    "rank": len(results) + 1,
                    "score": float(score),
                    "content": snippet,
                    "query_tokens": query_tokens,
                    **metadata,
                }
                results.append(result)

            # 검색 시간 기록
            search_time = time.time() - start_time
            self.total_search_time += search_time

            if self.search_count % 100 == 0:
                self.logger.info(f"BM25 검색 통계: {self.search_count}회, 평균 {self.total_search_time / self.search_count:.3f}초")

            return results

        except Exception as e:
            self.logger.error(f"BM25 검색 실패: {e}")
            return []

    def generate_dynamic_stopwords(self, df_threshold: float = 0.75, max_token_len: int = 3) -> set:
        """현재 인덱스에서 동적 불용어 생성

        Args:
            df_threshold: 불용어로 간주할 문서 빈도 비율 (기본 0.75 = 75%, 기존 0.85에서 강화)
            max_token_len: 불용어 후보로 고려할 최대 토큰 길이

        Returns:
            동적 불용어 세트
        """
        n_docs = len(self.documents)
        if n_docs == 0:
            return set()

        dynamic_stopwords = build_dynamic_stopwords(
            self.doc_freqs, n_docs, df_threshold, max_token_len,
            whitelist=BUSINESS_KEYWORDS_WHITELIST,
        )

        self.logger.info(
            f"동적 불용어 {len(dynamic_stopwords)}개 생성 "
            f"(DF threshold: {df_threshold}, max len: {max_token_len})",
        )

        # 로그에 상위 20개 출력
        if dynamic_stopwords:
            sorted_stopwords = sorted(dynamic_stopwords, key=lambda x: self.doc_freqs[x], reverse=True)[:20]
            self.logger.info(f"상위 동적 불용어: {sorted_stopwords}")

        return dynamic_stopwords

    def get_stats(self) -> dict[str, Any]:
        """BM25 인덱스 통계 (확장된 메트릭)"""
        tokenizer_stats = {
            "type": "kiwipiepy" if self.tokenizer.use_kiwi else "basic",
            "tokenize_count": self.tokenizer.tokenize_count,
            "cache_hits": self.tokenizer.cache_hits,
            "cache_hit_rate": self.tokenizer.cache_hits / self.tokenizer.tokenize_count * 100 if self.tokenizer.tokenize_count > 0 else 0,
        }

        return {
            "total_documents": len(self.documents),
            "vocab_size": len(self.vocab),
            "avg_doc_length": self.avg_doc_len,
            "avgdl": self.avg_doc_len,  # 호환성 alias
            "index_path": str(self.index_path),
            "bm25_index_path": str(self.index_path),  # 호환성 alias
            "bm25_index_docs": len(self.documents),  # 호환성 alias
            "has_tf": bool(self.term_freqs),
            "has_df": bool(self.doc_freqs),
            "parameters": {
                "k1": self.k1,
                "b": self.b,
            },
            "tokenizer": tokenizer_stats,
            "performance": {
                "total_index_time": self.index_time,
                "search_count": self.search_count,
                "total_search_time": self.total_search_time,
                "avg_search_time": self.total_search_time / self.search_count if self.search_count > 0 else 0,
            },
        }


# 테스트 함수
def test_bm25_store():
    """BM25 스토어 테스트"""
    print("🔍 BM25 스토어 테스트 시작")

    # 테스트 데이터
    test_texts = [
        "핀마이크 모델 ECM-77BC를 구매 검토합니다. 가격은 336,000원입니다.",
        "영상편집팀 워크스테이션 교체 비용은 179,300,000원입니다. HP Z8 모델입니다.",
        "광화문 스튜디오 모니터 교체 총액은 9,760,000원입니다. LG 모니터 3대입니다.",
        "카메라 장비 구매를 위한 예산 검토서입니다. 총 예산은 50,000,000원입니다.",
        "스튜디오 조명 시설 교체에 대한 기안서입니다. 필립스 LED 조명 20대를 구매합니다.",
    ]

    test_metadatas = [
        {
            "doc_id": "doc1",
            "chunk_id": "chunk1_1",
            "filename": "2021-05-13_핀마이크_구매검토.pdf",
            "content": test_texts[0],
            "metadata": {"doc_type": "기안서", "amount": 336000},
        },
        {
            "doc_id": "doc2",
            "chunk_id": "chunk2_1",
            "filename": "2022-02-03_워크스테이션_교체검토.pdf",
            "content": test_texts[1],
            "metadata": {"doc_type": "검토서", "amount": 179300000},
        },
        {
            "doc_id": "doc3",
            "chunk_id": "chunk3_1",
            "filename": "2025-01-09_모니터_교체검토.pdf",
            "content": test_texts[2],
            "metadata": {"doc_type": "기안서", "amount": 9760000},
        },
        {
            "doc_id": "doc4",
            "chunk_id": "chunk4_1",
            "filename": "2023-07-15_카메라장비_예산검토.pdf",
            "content": test_texts[3],
            "metadata": {"doc_type": "예산서", "amount": 50000000},
        },
        {
            "doc_id": "doc5",
            "chunk_id": "chunk5_1",
            "filename": "2024-03-20_조명시설_교체기안.pdf",
            "content": test_texts[4],
            "metadata": {"doc_type": "기안서", "amount": 0},  # 금액 미상
        },
    ]

    try:
        # BM25 스토어 생성
        bm25 = BM25Store(index_path="var/index/test_bm25_index.pkl")

        # 문서 추가
        print("📝 테스트 문서 추가 중...")
        bm25.add_documents(test_texts, test_metadatas)

        # 인덱스 저장
        bm25.save_index()

        # 검색 테스트
        test_queries = [
            "핀마이크 가격은 얼마인가요?",
            "워크스테이션 모델명은?",
            "모니터 개수는 몇 개인가요?",
            "카메라 예산",
            "조명 교체",
        ]

        for query in test_queries:
            print(f"\n🔍 BM25 검색: '{query}'")
            results = bm25.search(query, top_k=3)

            for result in results:
                print(f"  순위 {result['rank']}: {result['filename']}")
                print(f"    BM25 스코어: {result['score']:.3f}")
                print(f"    쿼리 토큰: {result['query_tokens']}")
                print(f"    내용: {result['content'][:50]}...")

        # 통계 출력
        stats = bm25.get_stats()
        print("\n📊 BM25 인덱스 통계:")
        print(f"  총 문서 수: {stats['total_documents']}")
        print(f"  어휘 크기: {stats['vocab_size']}")
        print(f"  평균 문서 길이: {stats['avg_doc_length']:.1f}")
        print(f"  토크나이저: {stats['tokenizer']['type']}")
        print(f"  토큰 캐시 히트율: {stats['tokenizer']['cache_hit_rate']:.1f}%")
        print(f"  파라미터: k1={stats['parameters']['k1']}, b={stats['parameters']['b']}")
        print(f"  평균 검색 시간: {stats['performance']['avg_search_time']:.3f}초")

        print("✅ BM25 스토어 테스트 완료")
        return True

    except Exception as e:
        print(f"❌ BM25 스토어 테스트 실패: {e}")
        return False


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    test_bm25_store()
