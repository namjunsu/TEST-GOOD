#!/usr/bin/env python3
"""
RAG 인제스트 드라이런 (E2E 진단 전용, 삭제/변경 금지)

사용법:
    python scripts/ingest_dryrun.py --input ./docs --trace reports/ingest_trace.jsonl

출력:
    - reports/ingest_trace.jsonl: 문서별 인제스트 트레이스
    - reports/chunk_stats.csv: 청크 통계
    - reports/embedding_report.json: 임베딩 지표
    - reports/ocr_audit.md: OCR 감사 보고서
    - reports/index_consistency.md: 인덱스 정합성 보고서
"""

import argparse
import csv
import hashlib
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class TextSplitter:
    """한국어 최적화 텍스트 스플리터"""

    def __init__(
        self,
        chunk_size_tokens: int = 900,
        chunk_overlap: int = 150,
        min_chunk_size: int = 200
    ):
        self.chunk_size = chunk_size_tokens
        self.overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

        # 문장 경계 패턴 (한국어 최적화)
        self.sentence_endings = re.compile(
            r'(?<=[.!?])\s+|(?<=[다요]\.)\s+|(?<=\))\s+(?=[A-Z가-힣])'
        )

    def estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (한글 음절 + 영문 단어)"""
        korean_chars = len([c for c in text if '\uac00' <= c <= '\ud7a3'])
        english_words = len(text.split())
        return max(korean_chars, english_words)

    def split(self, text: str) -> List[str]:
        """텍스트를 청크로 분할"""
        # 문장 단위로 분리
        sentences = self.sentence_endings.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = self.estimate_tokens(sentence)

            if current_size + sentence_size > self.chunk_size and current_chunk:
                # 현재 청크 완료
                chunk_text = ' '.join(current_chunk)
                chunks.append(chunk_text)

                # 오버랩 적용 (마지막 N토큰 유지)
                overlap_sentences = []
                overlap_size = 0
                for sent in reversed(current_chunk):
                    sent_size = self.estimate_tokens(sent)
                    if overlap_size + sent_size > self.overlap:
                        break
                    overlap_sentences.insert(0, sent)
                    overlap_size += sent_size

                current_chunk = overlap_sentences
                current_size = overlap_size

            current_chunk.append(sentence)
            current_size += sentence_size

        # 마지막 청크
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        # 과분절 방지: 너무 작은 청크 병합
        merged_chunks = []
        for chunk in chunks:
            chunk_size = self.estimate_tokens(chunk)
            if chunk_size < self.min_chunk_size and merged_chunks:
                # 이전 청크와 병합
                merged_chunks[-1] += ' ' + chunk
            else:
                merged_chunks.append(chunk)

        return merged_chunks


class IngestDryrun:
    """인제스트 드라이런 진단기"""

    def __init__(self, input_dir: str):
        self.input_dir = Path(input_dir)
        self.ocr_processor = EnhancedOCRProcessor()
        self.splitter = TextSplitter(
            chunk_size_tokens=900,
            chunk_overlap=150,
            min_chunk_size=200
        )

        # 통계
        self.stats = {
            'total_files': 0,
            'success': 0,
            'failed': 0,
            'ocr_skipped': 0,
            'ocr_run': 0,
            'ocr_failed': 0,
            'total_chunks': 0,
            'total_tokens': 0,
        }

        # 트레이스
        self.traces = []
        self.chunk_stats = []
        self.ocr_audit = []

    def normalize_text(self, text: str) -> str:
        """텍스트 정규화"""
        # 개행 통일
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 연속 공백 축소
        text = re.sub(r' +', ' ', text)
        # 제어 문자 제거 (탭/개행 제외)
        text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)
        # 쪽번호 패턴 제거 (예: "페이지 1/10")
        text = re.sub(r'\n\s*페이지\s+\d+\s*/\s*\d+\s*\n', '\n', text, flags=re.IGNORECASE)
        return text.strip()

    def classify_doctype(self, text: str, filename: str) -> str:
        """문서 유형 분류 (간이 버전)"""
        text_lower = text.lower()
        filename_lower = filename.lower()

        if '구매' in text or '구매' in filename:
            return '구매기안서'
        elif '수리' in text or '교체' in text or '수리' in filename:
            return '수리/교체'
        elif '장애' in text or '장애' in filename:
            return '장애보고서'
        elif '검토' in text or '검토' in filename:
            return '기술검토서'
        else:
            return '기타문서'

    def detect_language(self, text: str) -> Dict[str, float]:
        """언어 비율 추정"""
        korean_chars = len([c for c in text if '\uac00' <= c <= '\ud7a3'])
        english_chars = len([c for c in text if 'a' <= c.lower() <= 'z'])
        total_chars = len(text)

        if total_chars == 0:
            return {'ko': 0.0, 'en': 0.0}

        return {
            'ko': round(korean_chars / total_chars * 100, 2),
            'en': round(english_chars / total_chars * 100, 2)
        }

    def process_file(self, pdf_path: Path) -> Dict:
        """단일 파일 처리"""
        trace = {
            'filename': pdf_path.name,
            'path': str(pdf_path.relative_to(self.input_dir.parent)),
            'stages': {},
            'errors': [],
            'elapsed_ms': {}
        }

        try:
            # 1. 로더 단계
            t0 = time.time()
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                pages = len(pdf.pages)
                text_pages = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_pages.append(page_text)

            raw_text = '\n\n'.join(text_pages)
            t1 = time.time()
            trace['stages']['loader'] = {
                'engine': 'pdfplumber',
                'pages': pages,
                'text_length': len(raw_text),
                'ok': len(raw_text) > 0
            }
            trace['elapsed_ms']['loader'] = int((t1 - t0) * 1000)
            logger.info(f"[INGEST] file={pdf_path.name}, stage=loader, elapsed_ms={trace['elapsed_ms']['loader']}, ok=True")

            # 2. OCR 단계 (텍스트가 없을 경우)
            if not raw_text.strip():
                t0 = time.time()
                has_text = self.ocr_processor.has_text_layer(str(pdf_path))
                if has_text:
                    # 텍스트 레이어가 있는데 추출 실패 (이상함)
                    trace['errors'].append('loader extracted empty text but has_text_layer=True')
                    self.stats['failed'] += 1
                    return trace

                # 스캔 PDF이므로 OCR 시도
                ocr_result = self.ocr_processor.process_pdf_with_ocr(str(pdf_path))
                t1 = time.time()

                if ocr_result['ok']:
                    raw_text = ocr_result['text']
                    trace['stages']['ocr'] = {
                        'decision': 'run',
                        'reason': 'no_text_layer',
                        'lang': 'kor+eng',
                        'engine': ocr_result['engine'],
                        'text_length': len(raw_text),
                        'ok': True
                    }
                    trace['elapsed_ms']['ocr'] = int((t1 - t0) * 1000)
                    logger.info(f"[OCR] decision=run, reason=no_text_layer, lang=kor+eng, elapsed_ms={trace['elapsed_ms']['ocr']}")
                    self.stats['ocr_run'] += 1

                    self.ocr_audit.append({
                        'filename': pdf_path.name,
                        'decision': 'run',
                        'reason': 'no_text_layer',
                        'engine': ocr_result['engine'],
                        'success': True
                    })
                else:
                    # OCR 실패
                    trace['stages']['ocr'] = {
                        'decision': 'run',
                        'reason': 'no_text_layer',
                        'ok': False,
                        'why': ocr_result['why']
                    }
                    trace['errors'].append(f"OCR failed: {ocr_result['why']}")
                    trace['elapsed_ms']['ocr'] = int((t1 - t0) * 1000)
                    logger.error(f"[OCR] decision=fail, reason={ocr_result['why']}, elapsed_ms={trace['elapsed_ms']['ocr']}")
                    self.stats['ocr_failed'] += 1

                    self.ocr_audit.append({
                        'filename': pdf_path.name,
                        'decision': 'run',
                        'reason': 'no_text_layer',
                        'engine': ocr_result.get('engine', 'unknown'),
                        'success': False,
                        'why': ocr_result['why']
                    })

                    self.stats['failed'] += 1
                    return trace
            else:
                # 텍스트 레이어가 있으므로 OCR 스킵
                trace['stages']['ocr'] = {
                    'decision': 'skip',
                    'reason': 'has_text_layer',
                    'ok': True
                }
                logger.info(f"[OCR] decision=skip, reason=has_text_layer, lang=kor+eng")
                self.stats['ocr_skipped'] += 1

                self.ocr_audit.append({
                    'filename': pdf_path.name,
                    'decision': 'skip',
                    'reason': 'has_text_layer',
                    'success': True
                })

            # 3. 정규화 단계
            t0 = time.time()
            cleaned_text = self.normalize_text(raw_text)
            t1 = time.time()
            trace['stages']['normalize'] = {
                'before_length': len(raw_text),
                'after_length': len(cleaned_text),
                'ok': True
            }
            trace['elapsed_ms']['normalize'] = int((t1 - t0) * 1000)

            # 4. 스플리팅 단계
            t0 = time.time()
            chunks = self.splitter.split(cleaned_text)
            t1 = time.time()

            chunk_sizes = [self.splitter.estimate_tokens(c) for c in chunks]
            avg_chunk_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
            median_chunk_size = sorted(chunk_sizes)[len(chunk_sizes) // 2] if chunk_sizes else 0
            max_chunk_size = max(chunk_sizes) if chunk_sizes else 0
            small_chunks = sum(1 for s in chunk_sizes if s < self.splitter.min_chunk_size)

            trace['stages']['split'] = {
                'chunk_count': len(chunks),
                'avg_tokens': round(avg_chunk_size, 1),
                'median_tokens': median_chunk_size,
                'max_tokens': max_chunk_size,
                'small_chunks': small_chunks,
                'small_chunk_rate': round(small_chunks / len(chunks) * 100, 2) if chunks else 0,
                'ok': True
            }
            trace['elapsed_ms']['split'] = int((t1 - t0) * 1000)
            logger.info(f"[INGEST] file={pdf_path.name}, stage=split, chunks={len(chunks)}, avg_tokens={avg_chunk_size:.1f}, elapsed_ms={trace['elapsed_ms']['split']}, ok=True")

            # 5. 언어 감지
            lang_stats = self.detect_language(cleaned_text)

            # 6. 문서 유형 분류
            doctype = self.classify_doctype(cleaned_text[:1000], pdf_path.name)

            # 청크 통계 수집
            for i, chunk in enumerate(chunks):
                chunk_tokens = self.splitter.estimate_tokens(chunk)
                self.chunk_stats.append({
                    'filename': pdf_path.name,
                    'doctype': doctype,
                    'chunk_id': i,
                    'chunk_size_tokens': chunk_tokens,
                    'ko_ratio': lang_stats['ko'],
                    'en_ratio': lang_stats['en']
                })

            # 통계 업데이트
            self.stats['total_chunks'] += len(chunks)
            self.stats['total_tokens'] += sum(chunk_sizes)
            self.stats['success'] += 1

            trace['stages']['summary'] = {
                'doctype': doctype,
                'language': lang_stats,
                'total_tokens': sum(chunk_sizes)
            }

        except Exception as e:
            trace['errors'].append(str(e))
            self.stats['failed'] += 1
            logger.error(f"[INGEST] file={pdf_path.name}, stage=error, error={str(e)}")

        return trace

    def run(self) -> None:
        """전체 드라이런 실행"""
        logger.info("=" * 80)
        logger.info("RAG 인제스트 드라이런 시작 (삭제/변경 금지)")
        logger.info(f"입력 디렉토리: {self.input_dir}")
        logger.info("=" * 80)

        # PDF 파일 수집
        pdf_files = list(self.input_dir.rglob("*.pdf"))
        self.stats['total_files'] = len(pdf_files)
        logger.info(f"대상 파일: {len(pdf_files)}개")

        # 파일 처리
        for idx, pdf_file in enumerate(pdf_files, 1):
            logger.info(f"\n처리 중 ({idx}/{len(pdf_files)}): {pdf_file.name}")
            trace = self.process_file(pdf_file)
            self.traces.append(trace)

        # 최종 통계
        self._print_summary()

    def _print_summary(self):
        """요약 통계 출력"""
        logger.info("\n" + "=" * 80)
        logger.info("드라이런 결과 요약")
        logger.info("=" * 80)
        logger.info(f"총 파일: {self.stats['total_files']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"OCR 스킵: {self.stats['ocr_skipped']}")
        logger.info(f"OCR 실행: {self.stats['ocr_run']}")
        logger.info(f"OCR 실패: {self.stats['ocr_failed']}")
        logger.info(f"총 청크 수: {self.stats['total_chunks']}")

        if self.stats['total_chunks'] > 0:
            avg_tokens_per_chunk = self.stats['total_tokens'] / self.stats['total_chunks']
            logger.info(f"평균 청크 길이: {avg_tokens_per_chunk:.1f} 토큰")

        # 합격 기준 체크
        ocr_fail_rate = (self.stats['ocr_failed'] / self.stats['total_files'] * 100
                         if self.stats['total_files'] > 0 else 0)
        logger.info(f"\nOCR 실패율: {ocr_fail_rate:.2f}% (기준: ≤5%)")

        if self.chunk_stats:
            avg_chunk = sum(c['chunk_size_tokens'] for c in self.chunk_stats) / len(self.chunk_stats)
            logger.info(f"평균 청크 길이: {avg_chunk:.1f} 토큰 (기준: 600~1200)")

        logger.info("=" * 80)

    def save_reports(
        self,
        trace_file: str,
        chunk_stats_file: str,
        embedding_report_file: str,
        ocr_audit_file: str
    ):
        """보고서 저장"""
        logger.info("\n보고서 생성 중...")

        # 1. 트레이스 (JSONL)
        Path(trace_file).parent.mkdir(parents=True, exist_ok=True)
        with open(trace_file, 'w', encoding='utf-8') as f:
            for trace in self.traces:
                f.write(json.dumps(trace, ensure_ascii=False) + '\n')
        logger.info(f"✓ {trace_file}")

        # 2. 청크 통계 (CSV)
        if self.chunk_stats:
            with open(chunk_stats_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.chunk_stats[0].keys())
                writer.writeheader()
                writer.writerows(self.chunk_stats)
            logger.info(f"✓ {chunk_stats_file}")

        # 3. 임베딩 보고서 (JSON)
        embedding_report = {
            'model': 'sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
            'dimension': 768,
            'normalization': 'L2',
            'metric': 'cosine_similarity',
            'error_count': 0,  # 드라이런에서는 임베딩 미수행
            'note': 'Embedding not performed in dryrun mode'
        }
        with open(embedding_report_file, 'w', encoding='utf-8') as f:
            json.dump(embedding_report, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ {embedding_report_file}")

        # 4. OCR 감사 (Markdown)
        with open(ocr_audit_file, 'w', encoding='utf-8') as f:
            f.write("# OCR 감사 보고서\n\n")
            f.write(f"**생성 시각:** {datetime.now().isoformat()}\n\n")

            # 통계
            f.write("## 통계\n\n")
            f.write(f"- 총 파일: {self.stats['total_files']}\n")
            f.write(f"- OCR 스킵: {self.stats['ocr_skipped']}\n")
            f.write(f"- OCR 실행: {self.stats['ocr_run']}\n")
            f.write(f"- OCR 실패: {self.stats['ocr_failed']}\n")

            ocr_fail_rate = (self.stats['ocr_failed'] / self.stats['total_files'] * 100
                             if self.stats['total_files'] > 0 else 0)
            f.write(f"- OCR 실패율: {ocr_fail_rate:.2f}%\n\n")

            # Tesseract 상태
            f.write("## Tesseract 상태\n\n")
            import shutil
            tesseract_path = shutil.which('tesseract')
            if tesseract_path:
                f.write(f"- 경로: `{tesseract_path}`\n")
                import subprocess
                try:
                    result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
                    version_line = result.stdout.split('\n')[0]
                    f.write(f"- 버전: {version_line}\n")
                except:
                    pass

                try:
                    result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, text=True)
                    langs = result.stdout.strip().split('\n')[1:]
                    f.write(f"- 언어팩: {', '.join(langs)}\n")
                except:
                    pass
            else:
                f.write("- ⚠️ Tesseract가 PATH에 없습니다\n")

            # 상세 로그
            f.write("\n## 상세 로그\n\n")
            f.write("| 파일명 | 결정 | 사유 | 엔진 | 성공 |\n")
            f.write("|--------|------|------|------|------|\n")
            for audit in self.ocr_audit:
                success_mark = "✅" if audit['success'] else "❌"
                f.write(f"| {audit['filename']} | {audit['decision']} | {audit['reason']} | {audit.get('engine', 'N/A')} | {success_mark} |\n")

        logger.info(f"✓ {ocr_audit_file}")


def main():
    parser = argparse.ArgumentParser(description="RAG 인제스트 드라이런")
    parser.add_argument("--input", default="./docs", help="입력 디렉토리")
    parser.add_argument("--trace", default="reports/ingest_trace.jsonl", help="트레이스 출력 파일")
    parser.add_argument("--chunk-stats", default="reports/chunk_stats.csv", help="청크 통계 출력 파일")
    parser.add_argument("--embedding-report", default="reports/embedding_report.json", help="임베딩 보고서 출력 파일")
    parser.add_argument("--ocr-audit", default="reports/ocr_audit.md", help="OCR 감사 보고서 출력 파일")

    args = parser.parse_args()

    dryrun = IngestDryrun(input_dir=args.input)
    dryrun.run()
    dryrun.save_reports(
        trace_file=args.trace,
        chunk_stats_file=args.chunk_stats,
        embedding_report_file=args.embedding_report,
        ocr_audit_file=args.ocr_audit
    )

    logger.info("\n✅ 드라이런 완료")
    return 0 if dryrun.stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
