# OCR 스크립트 통합 계획

**작성일**: 2025-11-24  
**목적**: 5개 OCR 스크립트를 단일 통합 스크립트로 통합

---

## 현재 상태 분석

### 1. 기존 OCR 스크립트 (5개)

| 스크립트 | 라인 수 | 선택 기준 | 특징 |
|---------|---------|-----------|------|
| **force_ocr_update.py** | 127 | `text_preview < threshold` | ✅ 기준 스크립트, 간결함 |
| **reprocess_with_ocr.py** | 240 | `avg_char_per_page < threshold` | 상세 로깅, dry-run 지원 |
| **batch_ocr_zero_chars.py** | 150 | `text_preview = 0` | 0자 문서만 타겟 |
| **reprocess_poor_docs_with_ocr.py** | 120 | `text_preview < threshold` | force_ocr_update.py와 거의 동일 |
| **batch_ocr_from_report.py** | 180 | 파일 목록 읽기 | 1회성 마이그레이션용 |

### 2. 공통 함수 패턴

모든 스크립트가 동일한 3단계 패턴을 공유:

```python
# 1단계: 문서 선택 (서로 다른 기준)
def find_xxx_docs(db_path, threshold=100):
    """DB에서 OCR 대상 문서 선택"""
    # - force_ocr: text_preview < threshold
    # - reprocess_with_ocr: avg_char_per_page < threshold
    # - batch_ocr_zero: text_preview = 0
    pass

# 2단계: OCR 실행 (완전 동일!)
def ocr_extract_pdf(pdf_path: Path) -> str:
    """PDF → 이미지 → Tesseract OCR"""
    images = convert_from_path(pdf_path, dpi=300)
    texts = []
    for i, image in enumerate(images, 1):
        text = pytesseract.image_to_string(image, lang="kor+eng")
        texts.append(f"[OCR 페이지 {i}]\n{text}")
    return "\n\n".join(texts)

# 3단계: DB 업데이트 (거의 동일)
def update_document_text(db_path, filename, full_text):
    """documents.text_preview 업데이트 → FTS5 자동 동기화"""
    conn.execute("UPDATE documents SET text_preview = ? WHERE filename = ?", ...)
    conn.commit()
```

### 3. 중복 코드 분석

**완전 중복** (5개 스크립트 모두 동일):
- `ocr_extract_pdf()`: PDF → OCR 텍스트 추출 (pytesseract + pdf2image)
- `update_document_text()`: DB 업데이트 로직

**부분 중복** (선택 기준만 다름):
- `find_poor_docs()`, `find_ocr_candidates()`, `find_zero_char_files()`

---

## 통합 설계

### 옵션 A: 단일 통합 스크립트 (권장)

**파일 구조**:
```
scripts/ops/
  ocr_reprocess.py         # 통합 스크립트 (CLI)

app/rag/ocr/
  pipeline.py              # OCR 파이프라인 (공통 로직)
  selectors.py             # 문서 선택기 (선택 기준별)
```

**통합 스크립트 사용법**:
```bash
# 텍스트 < 100자 문서
python scripts/ops/ocr_reprocess.py --mode poor --threshold 100

# 페이지당 평균 < 300자 문서
python scripts/ops/ocr_reprocess.py --mode average --threshold 300

# 0자 문서만
python scripts/ops/ocr_reprocess.py --mode zero

# 파일 목록에서 읽기
python scripts/ops/ocr_reprocess.py --mode list --file-list docs/ocr_targets.txt

# Dry-run 모드
python scripts/ops/ocr_reprocess.py --mode poor --dry-run
```

### 코드 구조

#### 1. `app/rag/ocr/pipeline.py` (공통 OCR 파이프라인)

```python
#!/usr/bin/env python3
"""
OCR 파이프라인 공통 모듈
모든 OCR 작업에서 재사용
"""

import logging
from pathlib import Path
from typing import Optional

import pytesseract
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)


def ocr_extract_pdf(
    pdf_path: Path,
    dpi: int = 300,
    lang: str = "kor+eng",
    progress_callback=None
) -> str:
    """PDF를 OCR로 텍스트 추출 (Tesseract)
    
    Args:
        pdf_path: PDF 파일 경로
        dpi: 이미지 변환 해상도 (기본 300)
        lang: Tesseract 언어 (기본 kor+eng)
        progress_callback: 진행 상황 콜백 (optional)
    
    Returns:
        추출된 텍스트 (페이지별 구분)
    
    Raises:
        FileNotFoundError: PDF 파일이 없을 때
        RuntimeError: OCR 실패 시
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일 없음: {pdf_path}")
    
    try:
        logger.info(f"OCR 추출 시작: {pdf_path.name} (dpi={dpi})")
        
        # PDF → 이미지 변환
        images = convert_from_path(str(pdf_path), dpi=dpi)
        
        # 각 페이지 OCR
        text_pages = []
        for i, image in enumerate(images, 1):
            logger.debug(f"  페이지 {i}/{len(images)} OCR 중...")
            
            # Progress callback
            if progress_callback:
                progress_callback(i, len(images))
            
            text = pytesseract.image_to_string(image, lang=lang)
            if text.strip():
                text_pages.append(f"[OCR 페이지 {i}]\n{text}")
        
        full_text = "\n\n".join(text_pages)
        logger.info(f"OCR 완료: {len(full_text):,}자 추출")
        return full_text
    
    except Exception as e:
        logger.error(f"OCR 실패: {pdf_path.name} - {e}")
        raise RuntimeError(f"OCR 실패: {e}") from e


def update_document_text(
    db_path: str,
    filename: str,
    full_text: str,
    use_transaction: bool = True
) -> bool:
    """documents 테이블의 text_preview 업데이트
    
    Args:
        db_path: DB 파일 경로
        filename: 문서 파일명
        full_text: OCR 추출 텍스트
        use_transaction: 트랜잭션 사용 여부
    
    Returns:
        업데이트 성공 여부
    
    Note:
        - documents 테이블 업데이트 → FTS5 자동 동기화됨 (트리거)
        - v2.1: sqlite_helpers.connect_metadata() 사용
    """
    from app.utils.sqlite_helpers import connect_metadata
    
    try:
        conn = connect_metadata(db_path, enable_row_factory=False)
        
        if use_transaction:
            conn.execute("BEGIN IMMEDIATE")
        
        conn.execute(
            """
            UPDATE documents
            SET text_preview = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE filename = ?
            """,
            (full_text, filename),
        )
        
        if use_transaction:
            conn.commit()
        
        conn.close()
        logger.info(f"DB 업데이트 완료: {filename} ({len(full_text):,}자)")
        return True
    
    except Exception as e:
        logger.error(f"DB 업데이트 실패: {filename} - {e}")
        if use_transaction:
            conn.rollback()
        return False
```

#### 2. `app/rag/ocr/selectors.py` (문서 선택기)

```python
#!/usr/bin/env python3
"""
OCR 대상 문서 선택기
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def select_by_text_length(
    db_path: str,
    threshold: int = 100,
    limit: int = None
) -> List[Dict[str, Any]]:
    """텍스트 길이 기준 선택 (force_ocr_update.py 로직)
    
    Args:
        db_path: DB 파일 경로
        threshold: 텍스트 길이 임계값 (기본 100자)
        limit: 최대 개수 제한
    
    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT 
            id,
            path,
            filename,
            page_count,
            LENGTH(text_preview) as text_len
        FROM documents
        WHERE LENGTH(text_preview) < ?
        ORDER BY text_len ASC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor = conn.execute(query, (threshold,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"선택 (text_length < {threshold}): {len(results)}개 문서")
    return results


def select_by_avg_per_page(
    db_path: str,
    threshold: int = 300,
    limit: int = None
) -> List[Dict[str, Any]]:
    """페이지당 평균 글자수 기준 선택 (reprocess_with_ocr.py 로직)
    
    Args:
        db_path: DB 파일 경로
        threshold: 페이지당 평균 글자수 임계값 (기본 300자)
        limit: 최대 개수 제한
    
    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT
            id,
            path,
            filename,
            page_count,
            LENGTH(text_preview) as text_len,
            CAST(LENGTH(text_preview) AS FLOAT) / NULLIF(page_count, 0) as avg_per_page
        FROM documents
        WHERE page_count > 0
          AND text_preview IS NOT NULL
          AND LENGTH(text_preview) > 0
          AND (CAST(LENGTH(text_preview) AS FLOAT) / page_count) < ?
        ORDER BY avg_per_page ASC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor = conn.execute(query, (threshold,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"선택 (avg_per_page < {threshold}): {len(results)}개 문서")
    return results


def select_zero_text(
    db_path: str,
    limit: int = None
) -> List[Dict[str, Any]]:
    """0자 문서 선택 (batch_ocr_zero_chars.py 로직)
    
    Args:
        db_path: DB 파일 경로
        limit: 최대 개수 제한
    
    Returns:
        선택된 문서 목록
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT
            id,
            path,
            filename,
            page_count
        FROM documents
        WHERE filename LIKE '%.pdf'
          AND (text_preview IS NULL OR LENGTH(text_preview) = 0)
        ORDER BY filename
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor = conn.execute(query)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"선택 (zero_text): {len(results)}개 문서")
    return results


def select_from_file_list(
    file_list_path: str,
    db_path: str = "metadata.db"
) -> List[Dict[str, Any]]:
    """파일 목록에서 읽기 (batch_ocr_from_report.py 로직)
    
    Args:
        file_list_path: 파일 목록 경로 (한 줄에 하나씩)
        db_path: DB 파일 경로
    
    Returns:
        선택된 문서 목록
    """
    from pathlib import Path
    
    file_list = Path(file_list_path).read_text().strip().split("\n")
    file_list = [f.strip() for f in file_list if f.strip()]
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    results = []
    for filename in file_list:
        cursor = conn.execute(
            "SELECT id, path, filename, page_count FROM documents WHERE filename = ?",
            (filename,)
        )
        row = cursor.fetchone()
        if row:
            results.append(dict(row))
        else:
            logger.warning(f"DB에 없는 파일: {filename}")
    
    conn.close()
    logger.info(f"선택 (file_list): {len(results)}개 문서")
    return results
```

#### 3. `scripts/ops/ocr_reprocess.py` (통합 CLI 스크립트)

```python
#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
OCR 재처리 통합 스크립트

사용법:
    # 텍스트 < 100자 문서
    python scripts/ops/ocr_reprocess.py --mode poor --threshold 100
    
    # 페이지당 평균 < 300자 문서
    python scripts/ops/ocr_reprocess.py --mode average --threshold 300
    
    # 0자 문서만
    python scripts/ops/ocr_reprocess.py --mode zero
    
    # 파일 목록에서 읽기
    python scripts/ops/ocr_reprocess.py --mode list --file-list docs/targets.txt
    
    # Dry-run
    python scripts/ops/ocr_reprocess.py --mode poor --dry-run
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import get_logger
from app.rag.ocr.pipeline import ocr_extract_pdf, update_document_text
from app.rag.ocr.selectors import (
    select_by_text_length,
    select_by_avg_per_page,
    select_zero_text,
    select_from_file_list,
)

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="OCR 재처리 통합 스크립트")
    parser.add_argument(
        "--mode",
        choices=["poor", "average", "zero", "list"],
        required=True,
        help="선택 모드 (poor: text<threshold, average: avg/page<threshold, zero: 0자, list: 파일목록)"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="임계값 (poor: 100, average: 300)"
    )
    parser.add_argument(
        "--file-list",
        type=str,
        help="파일 목록 경로 (mode=list 필수)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="최대 처리 개수"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="시뮬레이션만 (실제 OCR/DB 업데이트 안 함)"
    )
    parser.add_argument(
        "--db-path",
        default="metadata.db",
        help="DB 파일 경로 (기본: metadata.db)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="OCR DPI (기본: 300)"
    )
    
    args = parser.parse_args()
    
    # 1. 문서 선택
    logger.info(f"OCR 재처리 시작 (mode={args.mode}, threshold={args.threshold}, dry_run={args.dry_run})")
    
    if args.mode == "poor":
        candidates = select_by_text_length(args.db_path, args.threshold, args.limit)
    elif args.mode == "average":
        candidates = select_by_avg_per_page(args.db_path, args.threshold, args.limit)
    elif args.mode == "zero":
        candidates = select_zero_text(args.db_path, args.limit)
    elif args.mode == "list":
        if not args.file_list:
            logger.error("--file-list 필수 (mode=list)")
            sys.exit(1)
        candidates = select_from_file_list(args.file_list, args.db_path)
    
    if not candidates:
        logger.info("처리할 문서 없음")
        return
    
    logger.info(f"총 {len(candidates)}개 문서 선택됨")
    
    # 2. OCR 처리
    success_count = 0
    fail_count = 0
    docs_root = Path("docs").resolve()
    
    for i, doc in enumerate(candidates, 1):
        filename = doc["filename"]
        rel_path = doc.get("path", filename)
        pdf_path = docs_root / rel_path
        
        logger.info(f"[{i}/{len(candidates)}] 처리 중: {filename}")
        
        if not pdf_path.exists():
            logger.warning(f"  파일 없음: {pdf_path}")
            fail_count += 1
            continue
        
        try:
            if args.dry_run:
                logger.info(f"  [DRY-RUN] OCR 스킵: {filename}")
                success_count += 1
                continue
            
            # OCR 실행
            full_text = ocr_extract_pdf(
                pdf_path,
                dpi=args.dpi,
                progress_callback=lambda page, total: logger.debug(f"    페이지 {page}/{total}")
            )
            
            # DB 업데이트
            if update_document_text(args.db_path, filename, full_text):
                success_count += 1
                logger.info(f"  ✅ 성공: {len(full_text):,}자 추출")
            else:
                fail_count += 1
                logger.error(f"  ❌ DB 업데이트 실패")
        
        except Exception as e:
            logger.error(f"  ❌ 처리 실패: {e}")
            fail_count += 1
        
        # 진행 상황 출력
        if i % 10 == 0:
            logger.info(f"진행 상황: {i}/{len(candidates)} (성공={success_count}, 실패={fail_count})")
    
    # 3. 최종 결과
    logger.info("=" * 80)
    logger.info(f"OCR 재처리 완료")
    logger.info(f"  총 대상: {len(candidates)}개")
    logger.info(f"  성공: {success_count}개")
    logger.info(f"  실패: {fail_count}개")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
```

---

## 이전 (기존 스크립트 폐기 계획)

### Deprecated 폴더로 이동

```bash
mkdir -p scripts/deprecated/ocr
mv scripts/force_ocr_update.py scripts/deprecated/ocr/
mv scripts/reprocess_with_ocr.py scripts/deprecated/ocr/
mv scripts/batch_ocr_zero_chars.py scripts/deprecated/ocr/
mv scripts/reprocess_poor_docs_with_ocr.py scripts/deprecated/ocr/
mv scripts/batch_ocr_from_report.py scripts/deprecated/ocr/
```

### 각 스크립트에 deprecation guard 추가

```python
#!/home/wnstn4647/AI-CHAT/.venv/bin/python3
"""
[DEPRECATED - 2025-11-24]
이 스크립트는 scripts/ops/ocr_reprocess.py로 통합되었습니다.
→ 사용 금지: 대신 scripts/ops/ocr_reprocess.py --mode poor 를 사용하십시오.
"""

import sys
raise RuntimeError(
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "  [DEPRECATED] force_ocr_update.py는 사용 중지되었습니다.\n"
    "  대신 사용하세요: python scripts/ops/ocr_reprocess.py --mode poor\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
)
```

---

## 마이그레이션 가이드

### 기존 명령어 → 새 명령어

| 기존 명령어 | 새 명령어 |
|------------|----------|
| `python scripts/force_ocr_update.py --threshold 100` | `python scripts/ops/ocr_reprocess.py --mode poor --threshold 100` |
| `python scripts/reprocess_with_ocr.py --threshold 300 --limit 10` | `python scripts/ops/ocr_reprocess.py --mode average --threshold 300 --limit 10` |
| `python scripts/batch_ocr_zero_chars.py` | `python scripts/ops/ocr_reprocess.py --mode zero` |
| `python scripts/batch_ocr_from_report.py poor_docs.txt` | `python scripts/ops/ocr_reprocess.py --mode list --file-list poor_docs.txt` |

---

## 구현 순서

1. ✅ **Step 9.1**: 설계 문서 작성 (완료)
2. **Step 9.2**: `app/rag/ocr/pipeline.py` 생성
3. **Step 9.3**: `app/rag/ocr/selectors.py` 생성
4. **Step 9.4**: `scripts/ops/ocr_reprocess.py` 생성
5. **Step 9.5**: 테스트 (dry-run 모드)
6. **Step 9.6**: 기존 스크립트 deprecated 처리
7. **Step 9.7**: OPERATIONS_GUIDE.md 업데이트

---

## 예상 효과

- ✅ **코드 중복 제거**: 5개 스크립트 → 1개 통합 스크립트
- ✅ **유지보수성 향상**: OCR 로직 변경 시 1곳만 수정
- ✅ **일관성 확보**: 모든 OCR 작업이 동일한 파이프라인 사용
- ✅ **테스트 용이성**: 단일 진입점으로 테스트 간소화
- ✅ **확장성**: 새로운 선택 모드 추가 쉬움 (selectors.py에만 함수 추가)

---

## 변경 이력

| 날짜 | 변경 내용 | 작성자 |
|------|-----------|--------|
| 2025-11-24 | 초안 작성 (설계) | AI Assistant |
