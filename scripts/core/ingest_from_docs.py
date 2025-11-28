#!/usr/bin/env python3
"""
문서 투입 인덱싱 CLI
docs/incoming/*.pdf를 스캔하여 메타DB 및 벡터 인덱스에 추가합니다.

사용법:
    python scripts/ingest_from_docs.py                    # 전체 처리
    python scripts/ingest_from_docs.py --limit 10         # 최대 10개만
    python scripts/ingest_from_docs.py --only "2025*"     # 패턴 매칭
    python scripts/ingest_from_docs.py --dry-run          # 실제 이동/업서트 없이 리포트만
    python scripts/ingest_from_docs.py --ocr              # OCR 활성화
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import get_logger
from app.data.metadata_db import MetadataDB
from app.rag.parse.doctype import classify_document
from app.rag.parse.parse_meta import MetaParser
from app.rag.parse.parse_tables import TableParser
from app.rag.preprocess.clean_text import TextCleaner

logger = get_logger(__name__)

# OCR 모드 상수
OCR_MODE_OFF = "off"
OCR_MODE_FALLBACK = "fallback"
OCR_MODE_FORCE = "force"


def extract_claimed_total_fallback(text: str) -> Optional[int]:
    """본문에서 비용 합계 금액을 폴백 추출

    Args:
        text: 문서 본문 텍스트

    Returns:
        추출된 금액 (정수) 또는 None
    """
    # 🛡️ 오매칭 방지: 수량 패턴 제외 ("합계 2000개" 같은 케이스)
    if re.search(r"합계\s*[\d,]+\s*개\b", text):
        logger.debug("수량 패턴 감지 (합계 N개), 금액 추출 스킵")
        return None

    # 합계 라벨 패턴 (OR): 비용 합계, 합계(VAT별도), 합계, 총계
    label_pattern = r"(?:비용\s*합계|합계\s*\(VAT\s*별도\)|합계(?!\s*검증)|총계)"
    # 금액 패턴: 선택적 통화 기호 + 숫자+구분자 + 선택적 통화 단위
    amount_pattern = r"(?:₩|KRW)?\s*([\d\.,]+)\s*(?:원|KRW|₩)?"

    # 전체 패턴: 라벨 + 선택적 공백/기호 + 금액
    full_pattern = label_pattern + r"\s*[:\s]*" + amount_pattern

    match = re.search(full_pattern, text)
    if not match:
        return None

    try:
        amount_str = match.group(1)
    except (IndexError, AttributeError):
        return None

    try:
        # 숫자 정규화: , ₩ 원 공백 제거
        normalized = amount_str.replace(",", "").replace("₩", "").replace("원", "").replace(" ", "")
        claimed_total = int(normalized)

        # 🛡️ 최소 금액 필터: 1만원 미만은 의심 (수량 오인 가능성)
        if claimed_total < 10000:
            logger.warning(f"claimed_total={claimed_total:,}원 너무 작음, 수량 오인 가능성으로 제외")
            return None

        try:
            pattern_preview = match.group(0)[:50] if match else "N/A"
        except (IndexError, AttributeError):
            pattern_preview = "N/A"
        logger.info(f"claimed_total_fallback={claimed_total:,}원 (패턴: {pattern_preview})")
        return claimed_total
    except (ValueError, OverflowError) as e:
        logger.warning(f"claimed_total 변환 실패: {amount_str} - {e}")
        return None


class DocumentIngester:
    """문서 투입 처리기"""

    def __init__(
        self,
        incoming_dir: str = "docs/incoming",
        processed_dir: str = "docs/processed",
        rejected_dir: str = "docs/rejected",
        quarantine_dir: str = "docs/quarantine",
        extracted_dir: str = "data/extracted",
        db_path: str = "metadata.db",
        ocr_enabled: bool = False,  # Deprecated: use ocr_mode instead
        ocr_mode: Optional[str] = None,  # "off" | "fallback" | "force"
        dry_run: bool = False,
    ):
        self.incoming_dir = Path(incoming_dir)
        self.processed_dir = Path(processed_dir)
        self.rejected_dir = Path(rejected_dir)
        self.quarantine_dir = Path(quarantine_dir)
        self.extracted_dir = Path(extracted_dir)
        self.db_path = db_path
        self.dry_run = dry_run

        # OCR 모드 결정 (v1 스키마 지원)
        if ocr_mode is not None:
            # v1: 명시적 ocr_mode 우선
            self.ocr_mode = ocr_mode
        elif ocr_enabled:
            # v0 호환: ocr_enabled=True → fallback 모드
            self.ocr_mode = OCR_MODE_FALLBACK
        else:
            # 기본값: fallback (2024-11-24 변경: off → fallback)
            # 텍스트 추출 실패 시 자동으로 OCR 실행
            self.ocr_mode = OCR_MODE_FALLBACK

        # 하위 호환 속성 유지
        self.ocr_enabled = (self.ocr_mode != OCR_MODE_OFF)

        # 폴더 생성
        for d in [
            self.processed_dir,
            self.rejected_dir,
            self.quarantine_dir,
            self.extracted_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # 파서 초기화
        self.meta_parser = MetaParser()
        self.table_parser = TableParser()
        self.text_cleaner = TextCleaner()

        # DB 연결
        if not dry_run:
            self.db = MetadataDB(db_path=db_path)
        else:
            self.db = None

        # 통계
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "rejected": 0,
            "quarantined": 0,
        }
        self.results = []

    def _compute_hash(self, file_path: Path) -> str:
        """파일 해시 계산 (SHA1)"""
        sha1 = hashlib.sha1()
        with Path(file_path).open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha1.update(chunk)
        return sha1.hexdigest()

    def _normalize_filename(self, filename: str) -> str:
        """파일명 정규화 (중복 판정용)"""
        import unicodedata

        n = filename.strip()
        n = unicodedata.normalize("NFKC", n)
        n = n.replace(" ", "_").replace("-", "_").lower()
        n = re.sub(r"\((\d+)\)(?=\.pdf$)", "", n, flags=re.I)
        n = re.sub(r"_(\d+)(?=\.pdf$)", "", n, flags=re.I)
        n = re.sub(r"__+", "_", n)
        return n

    def _extract_text_from_pdf(self, pdf_path: Path) -> tuple[str, dict[str, Any]]:
        """PDF 텍스트 추출"""
        try:
            import pdfplumber

            text_pages = []
            metadata = {}

            with pdfplumber.open(pdf_path) as pdf:
                metadata["page_count"] = len(pdf.pages)
                metadata["file_size"] = pdf_path.stat().st_size

                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_pages.append(text)

            full_text = "\n\n".join(text_pages)

            # OCR 모드별 처리 (v1 스키마)
            page_count = metadata.get("page_count", 1)
            avg_chars_per_page = len(full_text) / page_count if page_count > 0 else 0

            # OCR 필요 여부 판단
            needs_ocr = False
            if self.ocr_mode == OCR_MODE_FORCE:
                # force: 항상 OCR 사용
                needs_ocr = True
                logger.info(f"OCR force 모드: {pdf_path.name}")
            elif self.ocr_mode == OCR_MODE_FALLBACK:
                # fallback: 텍스트가 없거나 페이지당 평균 300자 미만일 때만
                needs_ocr = not full_text or avg_chars_per_page < 300

            if needs_ocr:
                if not full_text:
                    logger.warning(f"pdfplumber 실패, OCR 폴백: {pdf_path.name}")
                else:
                    logger.warning(f"텍스트 부족 ({avg_chars_per_page:.0f}자/페이지), OCR 폴백: {pdf_path.name}")
                full_text = self._ocr_extract(pdf_path)

            return full_text, metadata

        except Exception as e:
            logger.error(f"PDF 추출 실패: {pdf_path.name} - {e}")
            return "", {}

    def _ocr_extract(self, pdf_path: Path) -> str:
        """OCR을 사용한 PDF 텍스트 추출"""
        try:
            import pytesseract
            from pdf2image import convert_from_path

            logger.info(f"OCR 추출 시작: {pdf_path.name}")

            # PDF → 이미지 변환
            images = convert_from_path(pdf_path, dpi=300)

            # 각 페이지 OCR
            text_pages = []
            for i, image in enumerate(images, 1):
                logger.debug(f"  페이지 {i}/{len(images)} OCR 중...")
                text = pytesseract.image_to_string(image, lang="kor+eng")
                if text.strip():
                    text_pages.append(text)

            full_text = "\n\n".join(text_pages)
            logger.info(f"OCR 완료: {pdf_path.name}, {len(full_text)}자 추출")

            return full_text

        except ImportError as e:
            logger.error(f"OCR 라이브러리 미설치: {e}")
            logger.error("설치 방법: pip install pytesseract pdf2image")
            return ""
        except Exception as e:
            logger.error(f"OCR 추출 실패: {pdf_path.name} - {e}")
            return ""

    def _is_duplicate(
        self, file_path: Path, file_hash: str, norm_filename: str,
    ) -> tuple[bool, str]:
        """중복 판정"""
        if self.dry_run or not self.db:
            return False, ""

        # 해시 기반 중복 체크 (향후 구현 - DB에 hash 컬럼 추가 필요)
        # ...

        # 정규화된 파일명 기반 중복 체크
        conn = self.db._get_conn()
        rows = conn.execute("SELECT filename, path FROM documents").fetchall()
        for row in rows:
            existing_filename = row[0]
            existing_norm = self._normalize_filename(existing_filename)
            if existing_norm == norm_filename:
                return True, f"정규화 파일명 중복: {existing_filename}"

        return False, ""

    def process_file(self, pdf_path: Path) -> dict[str, Any]:
        """단일 파일 처리"""
        start_time = time.time()
        result = {
            "filename": pdf_path.name,
            "status": "unknown",
            "reason": "",
            "duration_ms": 0,
            "doctype": "",
            "actions": [],
        }

        try:
            # 1. 해시 계산
            file_hash = self._compute_hash(pdf_path)
            norm_filename = self._normalize_filename(pdf_path.name)
            result["actions"].append(f"hash={file_hash[:8]}")

            # 2. 중복 체크
            is_dup, dup_reason = self._is_duplicate(pdf_path, file_hash, norm_filename)
            if is_dup:
                result["status"] = "duplicate"
                result["reason"] = dup_reason
                self.stats["duplicate"] += 1
                return result

            # 3. 텍스트 추출
            raw_text, pdf_meta = self._extract_text_from_pdf(pdf_path)
            if not raw_text:
                result["status"] = "rejected"
                result["reason"] = "텍스트 추출 실패 (빈 PDF)"
                self.stats["rejected"] += 1
                if not self.dry_run:
                    self._move_file(pdf_path, self.rejected_dir)
                result["actions"].append("→rejected")
                return result

            result["actions"].append(f"extracted={len(raw_text)}chars")

            # 4. 텍스트 클리닝
            cleaned_text, _ = self.text_cleaner.clean(raw_text)
            result["actions"].append(f"cleaned={len(cleaned_text)}chars")

            # 5. doctype 분류
            doctype_info = classify_document(cleaned_text[:2000], pdf_path.name)
            doctype = doctype_info.get("doctype", "unknown")
            result["doctype"] = doctype
            result["actions"].append(f"doctype={doctype}")

            # 6. 메타데이터 파싱
            # MetaParser를 사용한 메타데이터 추출
            parsed_meta = self.meta_parser.parse(
                metadata={},
                title=pdf_path.stem,
                content=cleaned_text[:1000],
            )

            # TableParser를 사용한 비용 정보 추출
            cost_data = self.table_parser.extract_cost_table(raw_text)

            # 한글 필드명 직접 추출 (기안서 프린트뷰 전용)
            import re
            korean_fields = {}

            # 시행일자 추출
            action_date_match = re.search(r"시행일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s*~\s*\d{4}[-./]\d{1,2}[-./]\d{1,2})?)", raw_text)
            if action_date_match:
                try:
                    korean_fields["시행일자"] = action_date_match.group(1)
                except (IndexError, AttributeError):
                    logger.debug("시행일자 그룹 추출 실패")

            # 기안일자 추출
            draft_date_match = re.search(r"기안일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{2})?)", raw_text)
            if draft_date_match:
                try:
                    korean_fields["기안일자"] = draft_date_match.group(1)
                except (IndexError, AttributeError):
                    logger.debug("기안일자 그룹 추출 실패")

            # 작성일자 추출
            created_date_match = re.search(r"작성일자\s+(\d{4}[-./]\d{1,2}[-./]\d{1,2})", raw_text)
            if created_date_match:
                try:
                    korean_fields["작성일자"] = created_date_match.group(1)
                except (IndexError, AttributeError):
                    logger.debug("작성일자 그룹 추출 실패")

            # 기안자 추출 (다양한 구분자 허용: 공백, 탭, ㅣ, |, :, ：)
            drafter_match = re.search(r"기안자[\s\|\ㅣ:：\t]*([가-힣]{2,10})", raw_text)
            if drafter_match:
                try:
                    korean_fields["기안자"] = drafter_match.group(1)
                except (IndexError, AttributeError):
                    logger.debug("기안자 그룹 추출 실패")

            # 기안부서 추출
            dept_match = re.search(r"기안부서\s+([^\n]+)", raw_text)
            if dept_match:
                try:
                    korean_fields["기안부서"] = dept_match.group(1).strip()
                except (IndexError, AttributeError):
                    logger.debug("기안부서 그룹 추출 실패")

            # parsed_meta에 한글 필드 병합
            if korean_fields:
                parsed_meta.update(korean_fields)
            result["actions"].append("meta_parsed")

            # 7. 표 파싱 (비용표)
            tables = self.table_parser.parse(raw_text)
            cost_data = None
            if tables.get("cost_table"):
                cost_data = tables["cost_table"]
                result["actions"].append(
                    f"cost_items={len(cost_data.get('items', []))}",
                )

            # 7.1 claimed_total 추출 (표 파싱 → 폴백)
            claimed_total = None
            if cost_data and cost_data.get("claimed_total"):
                claimed_total = cost_data.get("claimed_total")
            else:
                # 폴백: 본문에서 "비용 합계", "합계(VAT별도)" 등 추출
                claimed_total = extract_claimed_total_fallback(raw_text)
                if claimed_total:
                    result["actions"].append(f"claimed_total_fallback={claimed_total:,}")

            # 7.2 sum_match 계산
            sum_match = None
            if claimed_total is not None and cost_data and cost_data.get("items"):
                # 라인아이템이 있으면 합계 검증
                items = cost_data.get("items", [])
                items_sum = sum(item.get("amount", 0) for item in items if item.get("amount"))

                if items_sum > 0:
                    # ±1원 허용 (반올림 오차)
                    if abs(items_sum - claimed_total) <= 1:
                        sum_match = True
                        result["actions"].append(f"sum_match=True ({items_sum:,}≈{claimed_total:,})")
                    else:
                        sum_match = False
                        result["actions"].append(f"sum_match=False ({items_sum:,}≠{claimed_total:,})")
            # 라인아이템 없으면 sum_match는 None 유지

            # 8. 텍스트 저장
            if not self.dry_run:
                extracted_file = self.extracted_dir / f"{pdf_path.stem}.txt"
                extracted_file.write_text(cleaned_text, encoding="utf-8")
                result["actions"].append(f"saved→{extracted_file.name}")

            # 9. 메타DB 업서트 (실패 시 파일 이동 금지)
            db_save_success = False
            # Determine year from display_date or filename (BEFORE try block)
            year = None
            if parsed_meta.get("display_date"):
                year = parsed_meta.get("display_date", "")[:4]
            else:
                # Extract year from filename (e.g., 2024-01-15_...)
                import re
                year_match = re.match(r"^(\d{4})", pdf_path.name)
                if year_match:
                    year = year_match.group(1)

            if not self.dry_run and self.db:
                try:

                    # Determine final path: year_YYYY/ if year available, else processed/
                    if year:
                        final_path = Path("docs") / f"year_{year}" / pdf_path.name
                    else:
                        final_path = self.processed_dir / pdf_path.name

                    # Convert to relative path from docs/
                    docs_dir_abs = (Path.cwd() / "docs").resolve()
                    final_path_abs = (Path.cwd() / final_path).resolve()
                    relative_path = str(final_path_abs.relative_to(docs_dir_abs))

                    doc_metadata = {
                        "path": relative_path,
                        "filename": pdf_path.name,
                        "title": parsed_meta.get("title", pdf_path.stem),
                        "date": parsed_meta.get("display_date", ""),
                        "year": year or "",
                        "month": (
                            parsed_meta.get("display_date", "")[:7]
                            if len(parsed_meta.get("display_date", "")) >= 7
                            else ""
                        ),
                        "category": parsed_meta.get("category", ""),
                        "drafter": parsed_meta.get("drafter", ""),
                        "amount": cost_data.get("total", 0) if cost_data else 0,
                        "file_size": pdf_meta.get("file_size", 0),
                        "page_count": pdf_meta.get("page_count", 0),
                        "text_preview": cleaned_text[:500],
                        "keywords": [],
                        "doctype": doctype,
                        "display_date": parsed_meta.get("display_date", ""),
                        "claimed_total": claimed_total,
                        "sum_match": sum_match,
                    }
                    doc_id = self.db.add_document(doc_metadata)
                    if not doc_id or doc_id <= 0:
                        raise RuntimeError(f"메타데이터 DB 저장 실패 (doc_id={doc_id})")
                    db_save_success = True
                    result["actions"].append(f"db_upserted(id={doc_id})")
                    logger.info(f"DB 저장 성공: {pdf_path.name} (id={doc_id})")
                except Exception as e:
                    logger.error(f"DB 저장 실패: {pdf_path.name} - {e}")
                    result["actions"].append(f"db_failed({str(e)[:50]})")
                    # DB 저장 실패 시 파일 이동하지 않음

            elif not self.dry_run:
                # DB 인스턴스가 없는 경우
                logger.warning(f"DB 인스턴스 없음, 파일 이동 취소: {pdf_path.name}")

            # 10. year_YYYY/ 또는 processed/로 이동 (DB 저장 성공 시에만)
            if not self.dry_run and db_save_success:
                # Move to year_YYYY/ if year is available, else processed/
                if year:
                    year_dir = Path("docs") / f"year_{year}"
                    year_dir.mkdir(parents=True, exist_ok=True)
                    dest = year_dir / pdf_path.name

                    # 목적지에 동일 파일명이 이미 존재하는 경우 처리
                    if dest.exists():
                        # 해시 비교 후 완전 동일하면 중복으로 보고 incoming만 삭제
                        try:
                            existing_hash = self._compute_hash(dest)
                        except Exception as e:
                            logger.error(f"기존 파일 해시 계산 실패: {dest} ({e})")
                            existing_hash = None

                        if existing_hash is not None and existing_hash == file_hash:
                            logger.warning(f"중복 파일 (동일 해시), incoming만 삭제: {dest}")
                            pdf_path.unlink(missing_ok=True)
                            result["actions"].append("→already_exists_same_hash_skipped")
                        else:
                            # 내용이 다를 가능성: 자동 rename 대신 '충돌' 상태만 로그
                            logger.error(
                                f"year 폴더에 동일 이름 다른 파일 존재. 자동 rename 금지: src={pdf_path}, dest={dest}",
                            )
                            result["actions"].append("→conflict_existing_different_file")
                            # incoming에 그대로 남겨서 수동 처리 유도
                    else:
                        # 목적지에 없으면 정상 이동
                        shutil.move(str(pdf_path), str(dest))
                        logger.info(f"이동: {pdf_path.name} → {dest}")
                        result["actions"].append(f"→year_{year}")
                else:
                    self._move_file(pdf_path, self.processed_dir)
                    result["actions"].append("→processed")
            elif not self.dry_run and not db_save_success:
                logger.warning(f"DB 저장 실패로 파일 이동 취소: {pdf_path.name}")
                result["actions"].append("→kept_in_incoming")

            result["status"] = "success"
            self.stats["success"] += 1

        except Exception as e:
            logger.error(f"파일 처리 실패: {pdf_path.name} - {e}")
            result["status"] = "failed"
            result["reason"] = str(e)
            self.stats["failed"] += 1

            if not self.dry_run:
                self._move_file(pdf_path, self.rejected_dir)
                result["actions"].append("→rejected")

        finally:
            result["duration_ms"] = int((time.time() - start_time) * 1000)

        return result

    def _move_file(self, src: Path, dest_dir: Path):
        """파일 이동"""
        dest_path = dest_dir / src.name
        # 동일 파일명이 이미 있으면 (1), (2) 등 추가
        counter = 1
        while dest_path.exists():
            stem = src.stem
            suffix = src.suffix
            dest_path = dest_dir / f"{stem}({counter}){suffix}"
            counter += 1

        shutil.move(str(src), str(dest_path))
        logger.info(f"이동: {src.name} → {dest_path}")

    def run(self, limit: Optional[int] = None, pattern: Optional[str] = None):
        """전체 처리 실행"""
        logger.info("=" * 80)
        logger.info("📥 문서 투입 인덱싱 시작")
        logger.info(f"incoming: {self.incoming_dir}")
        logger.info(f"dry_run: {self.dry_run}")
        logger.info(f"ocr_mode: {self.ocr_mode}")
        logger.info("=" * 80)

        # PDF 파일 목록 가져오기
        if pattern:
            pdf_files = list(self.incoming_dir.glob(pattern))
        else:
            pdf_files = list(self.incoming_dir.glob("*.pdf")) + list(
                self.incoming_dir.glob("*.PDF"),
            )

        pdf_files = pdf_files[:limit] if limit else pdf_files
        self.stats["total"] = len(pdf_files)

        logger.info(f"📄 처리 대상: {len(pdf_files)}개 파일")

        # 파일 처리
        for pdf_file in pdf_files:
            logger.info(f"\n처리 중: {pdf_file.name}")
            result = self.process_file(pdf_file)
            self.results.append(result)

            # 진행 상황 출력
            logger.info(
                f"  ✓ {result['status']} ({result['duration_ms']}ms) - {result['doctype']}",
            )
            if result["reason"]:
                logger.info(f"    사유: {result['reason']}")
            logger.info(f"    경로: {' → '.join(result['actions'])}")

        # 인덱스 재빌드 트리거 (필요 시)
        if not self.dry_run and self.stats["success"] > 0:
            logger.info("\n🔄 인덱스 재빌드 트리거 (필요 시 수동 실행)")
            logger.info("  - FAISS: python scripts/rebuild_rag_indexes.py")
            logger.info("  - BM25: python scripts/quick_rebuild_bm25.py")

        # 최종 통계
        self._print_summary()

        # 로그 저장
        self._save_log()

    def _print_summary(self):
        """요약 통계 출력"""
        logger.info("\n" + "=" * 80)
        logger.info("📊 처리 결과 요약")
        logger.info("=" * 80)
        logger.info(f"총 파일: {self.stats['total']}")
        logger.info(f"✅ 성공: {self.stats['success']}")
        logger.info(f"❌ 실패: {self.stats['failed']}")
        logger.info(f"🔁 중복: {self.stats['duplicate']}")
        logger.info(f"🚫 거부: {self.stats['rejected']}")
        logger.info(f"⚠️ 격리: {self.stats['quarantined']}")

        # 성공률
        if self.stats["total"] > 0:
            success_rate = (self.stats["success"] / self.stats["total"]) * 100
            logger.info(f"\n성공률: {success_rate:.1f}%")

        # SLA 체크 (10건 / 60초)
        total_duration = sum(r["duration_ms"] for r in self.results)
        avg_duration = total_duration / len(self.results) if self.results else 0
        logger.info(f"평균 처리 시간: {avg_duration:.0f}ms/파일")

        if self.stats["total"] == 10:
            sla_ok = total_duration <= 60000
            logger.info(
                f"SLA (10건/60초): {'✅ 통과' if sla_ok else '❌ 초과'} ({total_duration / 1000:.1f}초)",
            )

        logger.info("=" * 80)

    def _save_log(self):
        """상세 로그 저장"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"ingest_{timestamp}.json"

        log_data = {
            "timestamp": timestamp,
            "dry_run": self.dry_run,
            "ocr_mode": self.ocr_mode,
            "ocr_enabled": self.ocr_enabled,  # v0 호환
            "stats": self.stats,
            "results": self.results,
        }

        log_file.write_text(
            json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        logger.info(f"\n📄 상세 로그 저장: {log_file}")


def main():
    parser = argparse.ArgumentParser(description="문서 투입 인덱싱 CLI")
    parser.add_argument("--limit", type=int, help="처리할 최대 파일 수")
    parser.add_argument("--only", type=str, help="파일명 패턴 (glob)")
    parser.add_argument(
        "--ocr-mode",
        type=str,
        choices=["off", "fallback", "force"],
        help="OCR 모드: off (비활성), fallback (실패 시), force (항상 사용)",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="OCR 활성화 (Deprecated: --ocr-mode fallback 사용 권장)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="실제 이동/업서트 없이 리포트만",
    )

    args = parser.parse_args()

    # OCR 모드 결정 (v1 우선, v0 폴백)
    ocr_mode = args.ocr_mode if args.ocr_mode else None
    ocr_enabled = args.ocr

    ingester = DocumentIngester(
        ocr_mode=ocr_mode, ocr_enabled=ocr_enabled, dry_run=args.dry_run,
    )

    ingester.run(limit=args.limit, pattern=args.only)


if __name__ == "__main__":
    main()
