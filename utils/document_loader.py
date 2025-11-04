"""
Document Loader Module
데이터베이스에서 문서 메타데이터를 로드하고 처리
"""

import sqlite3
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DocumentInfo:
    """문서 정보 구조"""
    filename: str
    title: str
    date: str
    year: str
    category: str
    drafter: str
    size: str
    path: str
    keywords: str


class DocumentLoader:
    """문서 메타데이터 로더

    두 개의 SQLite 데이터베이스에서 문서 정보를 조회:
    - everything_index.db: 문서 목록 및 메타데이터
    - metadata.db: 추가 기안자 정보
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
        '영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출',
        '구매', '수리', '교체', '검토', '폐기',
        '방송기술팀', '영상취재팀', '영상제작팀', '기술관리팀',
        '명상제작팀', '그래픽디자인파트'
    ]

    def __init__(
        self,
        everything_db: str = "everything_index.db",
        metadata_db: str = "metadata.db"
    ):
        """
        Args:
            everything_db: 메인 문서 DB 경로
            metadata_db: 메타데이터 DB 경로
        """
        self.everything_db = Path(everything_db)
        self.metadata_db = Path(metadata_db)

    def _load_metadata_drafters(self) -> Dict[str, str]:
        """metadata.db에서 기안자 정보 로드

        Returns:
            파일명 -> 기안자 매핑 딕셔너리
        """
        drafters = {}

        if not self.metadata_db.exists():
            return drafters

        try:
            conn = sqlite3.connect(str(self.metadata_db))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT filename, drafter FROM documents "
                "WHERE drafter IS NOT NULL AND drafter != ''"
            )

            for fname, drafter in cursor.fetchall():
                if drafter and drafter.strip():
                    drafters[fname] = drafter.strip()

            conn.close()

        except Exception as e:
            print(f"⚠️ metadata.db 로드 실패: {e}")

        return drafters

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
        if '_' not in filename:
            return None

        parts = filename.split('_')

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

            # 제외 키워드 체크
            if any(exc in potential_name for exc in self.EXCLUDED_KEYWORDS):
                continue

            return potential_name

        return None

    def _determine_drafter(
        self,
        filename: str,
        metadata_drafters: Dict[str, str],
        department: Optional[str]
    ) -> str:
        """기안자 결정 (우선순위 적용)

        우선순위:
        1. metadata.db의 drafter 필드
        2. 파일명에서 추출
        3. department (부서명)

        Args:
            filename: 파일명
            metadata_drafters: metadata DB의 기안자 정보
            department: 부서명

        Returns:
            기안자 이름 (확인 안되면 "미확인")
        """
        # 1순위: metadata.db
        if filename in metadata_drafters:
            return metadata_drafters[filename]

        # 2순위: 파일명 추출
        drafter = self._extract_drafter_from_filename(filename)
        if drafter:
            return drafter

        # 3순위: department (부서명이 실제 카테고리가 아닌 경우)
        if department and department not in self.EXCLUDED_KEYWORDS:
            return department

        return "미확인"

    def load_documents(self, version: str = "v3.3") -> pd.DataFrame:
        """문서 메타데이터 로드

        Args:
            version: 버전 (현재 미사용, 하위 호환용)

        Returns:
            문서 정보 DataFrame
        """
        print("🚀 초고속 문서 로드 시작 (DB 직접 조회)")

        try:
            # 1. metadata.db에서 기안자 정보 로드
            metadata_drafters = self._load_metadata_drafters()
            if metadata_drafters:
                unique_drafters = len(set(metadata_drafters.values()))
                print(f"📋 metadata.db에서 {len(metadata_drafters)}개 문서의 기안자 정보 로드 (고유 기안자 {unique_drafters}명)")

            # 2. metadata.db 연결 (everything_index.db 대신)
            metadata_db_path = Path("metadata.db")
            if not metadata_db_path.exists():
                print(f"❌ metadata.db 파일이 없습니다")
                return pd.DataFrame()

            conn = sqlite3.connect(str(metadata_db_path))
            cursor = conn.cursor()

            # 3. 문서 목록 조회 (documents 테이블 사용)
            cursor.execute("""
                SELECT filename, path, date, year, category, drafter, keywords
                FROM documents
                ORDER BY year DESC, filename ASC
            """)

            rows = cursor.fetchall()
            print(f"📊 metadata.db에서 {len(rows)}개 문서 로드됨")

            # 4. 문서 정보 처리
            documents: List[Dict[str, str]] = []

            for filename, path, date, year, category, drafter, keywords in rows:
                # 카테고리 분류
                doc_category = self._classify_category(filename, category)

                # 기안자는 이미 metadata.db에서 가져옴 (department 필요 없음)
                if not drafter:
                    drafter = self._determine_drafter(
                        filename,
                        metadata_drafters,
                        None
                    )

                # 문서 정보 구성
                documents.append({
                    'filename': filename,
                    'title': filename.replace('.pdf', '').replace('_', ' '),
                    'date': date or '날짜없음',
                    'year': year or '연도없음',
                    'category': doc_category,
                    'drafter': drafter,
                    'size': '알 수 없음',
                    'path': path,
                    'keywords': keywords or ''
                })

            conn.close()

            # 5. DataFrame 생성 및 정렬
            df = pd.DataFrame(documents)
            if not df.empty:
                df = df.sort_values(['year', 'filename'], ascending=[False, True])

            # 6. 통계 출력
            self._print_statistics(df)

            print(f"✅ {len(documents)}개 문서 초고속 로드 완료!")
            return df

        except Exception as e:
            print(f"❌ 초고속 로드 실패: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    def _is_likely_korean_name(self, name: str) -> bool:
        """한글 이름 여부 판별 (장비명 필터링)

        Args:
            name: 체크할 이름

        Returns:
            True if likely a Korean person name
        """
        if not name or name == '미확인':
            return False

        # 영문/숫자가 포함되면 장비명으로 간주
        if any(c.isascii() and c.isalnum() for c in name):
            return False

        # 한글만으로 구성되고 2-4글자면 이름으로 간주
        if 2 <= len(name) <= 4 and all('\uac00' <= c <= '\ud7a3' for c in name):
            return True

        return False

    def _print_statistics(self, df: pd.DataFrame) -> None:
        """로드 통계 출력

        Args:
            df: 문서 DataFrame
        """
        if df.empty:
            return

        total_count = len(df)
        df_with_drafter = df[df['drafter'].notna() & (df['drafter'] != '미확인') & (df['drafter'] != '')]
        drafter_count = len(df_with_drafter)
        percentage = drafter_count * 100 // max(total_count, 1)

        # 전체 고유 기안자 (장비명 포함)
        all_unique_drafters = df_with_drafter['drafter'].unique() if drafter_count > 0 else []
        all_unique_count = len(all_unique_drafters)

        # 한글 이름만 필터링 (장비명 제외)
        korean_drafters = [d for d in all_unique_drafters if self._is_likely_korean_name(d)]
        korean_count = len(korean_drafters)

        print(f"📈 기안자 통계:")
        print(f"  - 총 문서 수: {total_count}개")
        print(f"  - 기안자 확인: {drafter_count}개 ({percentage}%)")
        print(f"  - 기안자 미확인: {total_count - drafter_count}개")
        print(f"  - 고유 기안자(한글 이름만): {korean_count}명")

        if all_unique_count > korean_count:
            print(f"  - 장비명 등 제외: {all_unique_count - korean_count}개")

        # 기안자 샘플 (한글 이름만, 상위 10명)
        if korean_count > 0:
            sample = ', '.join(korean_drafters[:10])
            print(f"  - 기안자 샘플: {sample}")


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
