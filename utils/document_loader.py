"""
Document Loader Module
메타데이터 DB에서 문서 정보를 로드하고 처리

Version: 2.0
- 경로 버그 수정 (self.metadata_db 일관성)
- everything_index.db 미사용 코드 제거
- 중복 DB 조회 제거 (단일 패스 처리)
- logging 시스템 전환
- 타입 안전성 강화
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# 로깅 설정
logger = logging.getLogger(__name__)


@dataclass
class DocumentInfo:
    """문서 정보 구조"""
    filename: str
    title: str
    date: str
    year: Optional[int]  # 숫자형으로 변경
    category: str
    drafter: str
    size: str
    path: str
    keywords: str


class DocumentLoader:
    """문서 메타데이터 로더

    metadata.db에서 문서 정보를 조회하고 기안자 정보를 추출
    """

    # 카테고리 분류 키워드
    CATEGORY_KEYWORDS = {
        "구매": "구매",
        "수리": "수리",
        "교체": "교체",
        "검토": "검토",
        "폐기": "폐기",
    }

    # 기안자 이름 추출 시 제외할 키워드
    EXCLUDED_KEYWORDS = [
        # 장비/기술 용어
        "영상", "카메라", "조명", "중계", "DVR", "스튜디오", "송출",
        "포터블", "모니터", "마이크", "믹서", "스위처", "인코더",
        # 업무 분류
        "구매", "수리", "교체", "검토", "폐기", "설치", "이전",
        # 부서명
        "방송기술팀", "영상취재팀", "영상제작팀", "기술관리팀",
        "그래픽디자인파트",
        # 회사/지명 (잘못 추출되는 케이스)
        "광화문", "채널에이", "방송", "뉴스", "제작",
    ]

    def __init__(self, metadata_db: str = "metadata.db"):
        """
        Args:
            metadata_db: 메타데이터 DB 경로
        """
        self.metadata_db = Path(metadata_db)

    def _classify_category(self, filename: str, db_category: Optional[str]) -> str:
        """파일명을 기반으로 카테고리 분류

        Args:
            filename: 파일명
            db_category: DB의 기존 카테고리

        Returns:
            분류된 카테고리
        """
        for keyword, category in self.CATEGORY_KEYWORDS.items():
            if keyword in filename:
                return category

        return db_category or "기타"

    def _extract_drafter_from_filename(self, filename: str) -> Optional[str]:
        """파일명에서 기안자 이름 추출

        형식:
        - 형식1: 날짜_부서_이름_제목.pdf
        - 형식2: 날짜_이름_제목.pdf

        Args:
            filename: 파일명

        Returns:
            추출된 기안자 이름 (없으면 None)
        """
        if "_" not in filename:
            return None

        parts = filename.split("_")

        # 2번째, 3번째 위치에서 이름 찾기
        for idx in [1, 2]:
            if len(parts) <= idx:
                continue

            potential_name = parts[idx]

            # 한글 이름 패턴: 2-4글자, 숫자 없음
            if not potential_name:
                continue

            if not (2 <= len(potential_name) <= 4):
                continue

            if any(char.isdigit() for char in potential_name):
                continue

            # 제외 키워드 체크 (부분 문자열 매칭)
            if any(exc in potential_name for exc in self.EXCLUDED_KEYWORDS):
                continue

            return potential_name

        return None

    def _determine_drafter(
        self,
        filename: str,
        db_drafter: Optional[str],
        department: Optional[str] = None,
    ) -> str:
        """기안자 결정 (우선순위 적용)

        우선순위:
        1. metadata.db의 drafter 필드
        2. 파일명에서 추출
        3. department (부서명) - 제외 키워드 검증

        Args:
            filename: 파일명
            db_drafter: DB의 기안자 정보
            department: 부서명 (optional)

        Returns:
            기안자 이름 (확인 안되면 "미확인")
        """
        # 1순위: DB drafter
        if db_drafter and db_drafter.strip():
            return db_drafter.strip()

        # 2순위: 파일명 추출
        extracted = self._extract_drafter_from_filename(filename)
        if extracted:
            return extracted

        # 3순위: department (부분 문자열 체크)
        if department:
            # 제외 키워드가 포함되어 있는지 체크
            is_excluded = any(exc in department for exc in self.EXCLUDED_KEYWORDS)
            if not is_excluded:
                return department

        return "미확인"

    def _is_likely_korean_name(self, name: str) -> bool:
        """한글 이름 여부 판별 (장비명 필터링)

        Args:
            name: 체크할 이름

        Returns:
            True if likely a Korean person name
        """
        if not name or name == "미확인":
            return False

        # 제외 키워드 체크 (부분 문자열 매칭)
        if any(exc in name for exc in self.EXCLUDED_KEYWORDS):
            return False

        # 영문/숫자가 포함되면 장비명으로 간주
        if any(c.isascii() and c.isalnum() for c in name):
            return False

        # 한글만으로 구성되고 2-4글자면 이름으로 간주
        if 2 <= len(name) <= 4 and all("\uac00" <= c <= "\ud7a3" for c in name):
            return True

        return False

    def load_documents(self, version: str = "v3.3") -> pd.DataFrame:
        """문서 메타데이터 로드 (단일 패스 처리)

        Args:
            version: 버전 (현재 미사용, 하위 호환용)

        Returns:
            문서 정보 DataFrame
        """
        logger.info("문서 로드 시작 (DB 직접 조회)")

        try:
            # 1. DB 경로 확인 (self.metadata_db 사용)
            if not self.metadata_db.exists():
                logger.error(f"metadata.db 파일이 없습니다: {self.metadata_db}")
                return pd.DataFrame()

            # 2. DB 연결 및 전체 데이터 조회 (단일 쿼리)
            with sqlite3.connect(str(self.metadata_db)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT filename, path, date, year, category, drafter, keywords,
                           title, page_count, created_at, display_date, file_size, text_preview
                    FROM documents
                    ORDER BY date DESC, filename ASC
                """)
                rows = cursor.fetchall()

            logger.info(f"metadata.db에서 {len(rows)}개 문서 로드됨")

            # 3. 문서 정보 처리
            documents: list[dict] = []

            for filename, path, date, year, category, drafter, keywords, title, page_count, created_at, display_date, file_size, text_preview in rows:
                # 카테고리 분류
                doc_category = self._classify_category(filename, category)

                # 기안자 결정
                doc_drafter = self._determine_drafter(filename, drafter)

                # year를 숫자형으로 변환
                try:
                    year_int = int(year) if year else None
                except (ValueError, TypeError):
                    year_int = None

                # title 결정 우선순위:
                # 1. text_preview 첫 줄 (실제 문서 제목)
                # 2. DB title 컬럼
                # 3. 파일명에서 생성
                if text_preview and text_preview.strip():
                    # text_preview의 첫 줄을 제목으로 사용
                    first_line = text_preview.split("\n")[0].strip()
                    if first_line:
                        title = first_line
                    elif not title:
                        stem = Path(filename).stem
                        title = stem.replace("_", " ")
                elif not title:
                    stem = Path(filename).stem
                    title = stem.replace("_", " ")

                # 파일 크기를 읽기 쉬운 형식으로 변환
                if file_size:
                    try:
                        size_mb = int(file_size) / (1024 * 1024)
                        size_str = f"{size_mb:.1f} MB"
                    except (ValueError, TypeError):
                        size_str = "알 수 없음"
                else:
                    size_str = "알 수 없음"

                # 문서 정보 구성
                documents.append({
                    "filename": filename,
                    "title": title,
                    "date": date or "날짜없음",
                    "year": year_int,  # 숫자형 또는 None
                    "year_display": str(year_int) if year_int else "연도없음",  # UI 표시용
                    "category": doc_category,
                    "drafter": doc_drafter,
                    "size": size_str,
                    "path": path,
                    "keywords": keywords or "",
                    "page_count": page_count or 0,
                    "created_at": created_at or "",
                    "display_date": display_date or date or "",
                })

            # 4. DataFrame 생성 및 정렬
            df = pd.DataFrame(documents)
            if not df.empty:
                # year(숫자)로 정렬, None은 맨 뒤로
                df = df.sort_values(
                    ["year", "filename"],
                    ascending=[False, True],
                    na_position="last",
                )

            # 5. 통계 출력
            self._print_statistics(df)

            logger.info(f"{len(documents)}개 문서 로드 완료")
            return df

        except Exception as e:
            logger.error(f"문서 로드 실패: {e}", exc_info=True)
            return pd.DataFrame()

    def _print_statistics(self, df: pd.DataFrame) -> None:
        """로드 통계 출력

        Args:
            df: 문서 DataFrame
        """
        if df.empty:
            return

        total_count = len(df)
        df_with_drafter = df[
            df["drafter"].notna() &
            (df["drafter"] != "미확인") &
            (df["drafter"] != "")
        ]
        drafter_count = len(df_with_drafter)
        percentage = drafter_count * 100 // max(total_count, 1)

        # 전체 고유 기안자
        all_unique_drafters: list = list(set(df_with_drafter["drafter"].tolist())) if drafter_count > 0 else []
        all_unique_count = len(all_unique_drafters)

        # 한글 이름만 필터링
        korean_drafters = [d for d in all_unique_drafters if self._is_likely_korean_name(d)]
        korean_count = len(korean_drafters)

        logger.info("기안자 통계:")
        logger.info(f"  - 총 문서 수: {total_count}개")
        logger.info(f"  - 기안자 확인: {drafter_count}개 ({percentage}%)")
        logger.info(f"  - 기안자 미확인: {total_count - drafter_count}개")
        logger.info(f"  - 고유 기안자(한글 이름만): {korean_count}명")

        if all_unique_count > korean_count:
            logger.info(f"  - 장비명 등 제외: {all_unique_count - korean_count}개")

        # 기안자 샘플
        if korean_count > 0:
            sample = ", ".join(korean_drafters[:10])
            logger.info(f"  - 기안자 샘플: {sample}")


# 하위 호환을 위한 함수 래퍼
def load_documents(_rag_instance=None, version: str = "v3.3") -> pd.DataFrame:
    """문서 로드 (레거시 호환 함수)

    Args:
        _rag_instance: RAG 인스턴스 (현재 미사용, 호환용)
        version: 버전

    Returns:
        문서 DataFrame
    """
    loader = DocumentLoader()
    return loader.load_documents(version)
