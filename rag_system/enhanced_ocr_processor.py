"""
향상된 OCR 프로세서 - Tesseract 통합
대용량 문서 처리를 위한 이미지 내 텍스트 추출
"""

import logging
import io
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import json
import hashlib

try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    import pdfplumber
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)

# pdfminer 경고 숨기기
logging.getLogger('pdfminer').setLevel(logging.ERROR)
logging.getLogger('pdfminer.pdffont').setLevel(logging.ERROR)

class EnhancedOCRProcessor:
    """Tesseract OCR을 포함한 향상된 PDF 텍스트 추출기"""
    
    # OCR 설정 상수
    OCR_OEM_MODE = 3  # OCR Engine Mode
    OCR_PSM_MODE = 6  # Page Segmentation Mode
    OCR_DPI = 150  # PDF to Image DPI
    OCR_LANGUAGES = 'kor+eng'
    
    # 캐시 설정 상수
    CACHE_SAVE_INTERVAL = 10  # 배치 처리시 캐시 저장 주기
    DEFAULT_CACHE_DIR = "./docs"
    DOCS_PREFIX = "docs/"
    
    # 텍스트 처리 상수
    MAX_KOREAN_WORD_LENGTH = 4  # 한글 단어 최대 길이 (합치기용)
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            try:
                from config import DOCS_DIR
                cache_dir = DOCS_DIR
            except ImportError:
                cache_dir = self.DEFAULT_CACHE_DIR
        self.cache_dir = Path(cache_dir)
        self.metadata_cache_file = self.cache_dir / ".metadata_cache.json"
        self.ocr_cache_file = self.cache_dir / ".ocr_cache.json"
        
        # 메타데이터 캐시 로드
        self.metadata_cache = self._load_cache(self.metadata_cache_file)
        self.ocr_cache = self._load_cache(self.ocr_cache_file)
        
        # OCR 언어 설정 (한국어 + 영어)
        self.tesseract_config = f'--oem {self.OCR_OEM_MODE} --psm {self.OCR_PSM_MODE}'
        self.tesseract_lang = self.OCR_LANGUAGES

        # 성능 통계
        self.ocr_count = 0
        self.total_ocr_time = 0.0
        self.cache_hits = 0
        self.cache_misses = 0

        # OCR 오류 패턴 초기화
        self._init_ocr_error_patterns()
        self._compile_patterns()
    
    def _init_ocr_error_patterns(self):
        """OCR 오류 패턴 초기화"""
        self.ocr_error_patterns = [
            # 숫자 1과 문자 l/I 혼동
            (r'[lI](\d{2},\d{3},\d{3})', r'1\1'),  # l79,300,000 → 179,300,000
            # 숫자 0과 문자 O 혼동
            (r'([A-Z]+)\s*O(\d)', r'\1 0\2'),  # HP O8 → HP 08
            # 공백 제거된 모델명
            (r'([A-Z]{2,})(\d+)', r'\1 \2'),  # HP28 → HP 28
            # 한글 오타 일반 패턴
            (r'스테이[숀션]', '스테이션'),  # 워크스테이숀 → 워크스테이션
        ]
        
        # 숫자 패턴
        self.number_patterns = [
            (r'(\d)\s*,\s*(\d)', r'\1,\2'),  # 3 , 0 0 0 -> 3,000
            (r'(\d)\s+(\d)\s+(\d)', r'\1\2\3'),  # 3 3 6 -> 336
        ]

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        # OCR 오류 패턴 컴파일
        self.compiled_ocr_patterns = [(re.compile(p), r) for p, r in self.ocr_error_patterns]

        # 숫자 패턴 컴파일
        self.compiled_number_patterns = [(re.compile(p), r) for p, r in self.number_patterns]

        # 한글 병합 패턴 컴파일
        self.korean_merge_pattern = re.compile(r'([가-힣])\s+([가-힣])\s+([가-힣])')

        logger.info(f"패턴 컴파일 완료: {len(self.compiled_ocr_patterns)}개 OCR 패턴, {len(self.compiled_number_patterns)}개 숫자 패턴")

    def _load_cache(self, cache_file: Path) -> Dict:
        """캐시 파일 로드"""
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"캐시 로드 실패: {cache_file} - {e}")
        return {}
    
    def _save_cache(self, cache_file: Path, cache_data: Dict):
        """캐시 파일 저장"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"캐시 저장 실패: {cache_file} - {e}")
    
    def _get_file_hash(self, pdf_path: str) -> str:
        """파일 해시 생성 (캐시 키용)"""
        return hashlib.md5(pdf_path.encode()).hexdigest()

    def has_text_layer(self, pdf_path: str) -> bool:
        """PDF에 텍스트 레이어가 있는지 확인

        Args:
            pdf_path: PDF 파일 경로

        Returns:
            텍스트 레이어가 있으면 True, 없으면 False (스캔 이미지 전용 PDF)
        """
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                # 첫 3페이지만 샘플링하여 텍스트 존재 여부 확인
                for page in pdf.pages[:3]:
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:  # 최소 50자 이상 텍스트가 있으면 텍스트 레이어 존재
                        return True
            return False
        except Exception as e:
            logger.warning(f"텍스트 레이어 체크 실패: {pdf_path} - {e}")
            return False  # 실패 시 스캔 PDF로 간주하여 OCR 시도

    def process_pdf_with_ocr(self, pdf_path: str, page_num: Optional[int] = None, lang: str = "kor+eng") -> Dict:
        """OCR을 사용한 PDF 처리 (UI 호출용)

        Args:
            pdf_path: PDF 파일 경로
            page_num: 특정 페이지만 처리 (None이면 전체)
            lang: Tesseract 언어 설정

        Returns:
            {
                "ok": bool,
                "text": str,
                "pages": int,
                "engine": "tesseract|skip",
                "why": "skip:has_text_layer|fail:missing_binary|success|..."
            }
        """
        result = {
            "ok": False,
            "text": "",
            "pages": 0,
            "engine": "unknown",
            "why": ""
        }

        try:
            # Tesseract 사용 가능 여부 확인
            if not TESSERACT_AVAILABLE:
                result["why"] = "fail:missing_binary"
                result["engine"] = "none"
                logger.error("[OCR] decision=fail, reason=missing_binary (pytesseract/pdf2image not installed)")
                return result

            # 텍스트 레이어 확인
            if self.has_text_layer(pdf_path):
                # 텍스트 레이어가 있으면 pdfplumber로 추출 (OCR 스킵)
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    result["pages"] = len(pdf.pages)

                    if page_num is not None:
                        # 특정 페이지만 추출
                        if 1 <= page_num <= len(pdf.pages):
                            page = pdf.pages[page_num - 1]
                            text = page.extract_text() or ""
                            result["text"] = self._post_process_text(text)
                        else:
                            result["why"] = f"fail:invalid_page_num (requested={page_num}, total={len(pdf.pages)})"
                            return result
                    else:
                        # 전체 페이지 추출
                        text_pages = []
                        for i, page in enumerate(pdf.pages, 1):
                            text = page.extract_text()
                            if text:
                                text_pages.append(f"[페이지 {i}]\n{self._post_process_text(text)}")
                        result["text"] = "\n\n".join(text_pages)

                result["ok"] = True
                result["engine"] = "skip"
                result["why"] = "skip:has_text_layer"
                logger.info(f"[OCR] decision=skip, reason=has_text_layer, pages={result['pages']}, lang={lang}")
                return result

            # 스캔 PDF인 경우 OCR 수행
            logger.info(f"[OCR] decision=run, reason=no_text_layer, lang={lang}")

            # PDF → 이미지 변환
            from pdf2image import convert_from_path
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                result["pages"] = len(pdf.pages)

            if page_num is not None:
                # 특정 페이지만 OCR
                images = convert_from_path(pdf_path, dpi=self.OCR_DPI, first_page=page_num, last_page=page_num)
            else:
                # 전체 페이지 OCR
                images = convert_from_path(pdf_path, dpi=self.OCR_DPI)

            # OCR 처리
            text_pages = []
            for i, image in enumerate(images, page_num if page_num else 1):
                try:
                    text = pytesseract.image_to_string(
                        image,
                        lang=lang,
                        config=self.tesseract_config
                    )
                    if text.strip():
                        processed_text = self._post_process_text(text)
                        text_pages.append(f"[OCR 페이지 {i}]\n{processed_text}")
                except Exception as e:
                    logger.warning(f"[OCR] 페이지 {i} OCR 실패: {e}")

            result["text"] = "\n\n".join(text_pages)
            result["ok"] = len(text_pages) > 0
            result["engine"] = "tesseract"
            result["why"] = "success" if result["ok"] else "fail:no_text_extracted"

            if result["ok"]:
                logger.info(f"[OCR] OCR 완료: pages={result['pages']}, extracted_pages={len(text_pages)}")
            else:
                logger.warning(f"[OCR] OCR 실패: 추출된 텍스트 없음")

            return result

        except ImportError as e:
            result["why"] = f"fail:missing_binary ({str(e)})"
            result["engine"] = "none"
            logger.error(f"[OCR] decision=fail, reason=missing_binary, detail={e}")
            return result
        except Exception as e:
            result["why"] = f"fail:exception ({str(e)[:100]})"
            result["engine"] = "error"
            logger.error(f"[OCR] decision=fail, reason=exception, detail={e}")
            return result

    def extract_text_with_ocr(self, pdf_path: str) -> Tuple[str, Dict]:
        """
        PDF에서 텍스트 추출 (텍스트 레이어 + OCR 이미지)
        Returns: (전체 텍스트, 메타데이터)
        """
        pdf_hash = self._get_file_hash(pdf_path)
        
        # OCR 캐시 확인
        if pdf_hash in self.ocr_cache:
            logger.info(f"OCR 캐시 사용: {Path(pdf_path).name}")
            self.cache_hits += 1
            return self.ocr_cache[pdf_hash]['text'], self.ocr_cache[pdf_hash]['metadata']

        self.cache_misses += 1
        start_time = time.time()
        
        full_text = ""
        metadata = {
            'has_images': False,
            'ocr_performed': False,
            'page_count': 0,
            'image_count': 0,
            'ocr_text_length': 0
        }
        
        try:
            # 1단계: pdfplumber로 텍스트 레이어 추출
            with pdfplumber.open(pdf_path) as pdf:
                metadata['page_count'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages, 1):
                    # 텍스트 추출
                    page_text = page.extract_text()
                    if page_text:
                        # 텍스트 후처리
                        page_text = self._post_process_text(page_text)
                        full_text += f"\n[페이지 {page_num}]\n{page_text}\n"
                    
                    # 이미지 확인
                    images = page.images if hasattr(page, 'images') else []
                    if images:
                        metadata['has_images'] = True
                        metadata['image_count'] += len(images)
            
            # 2단계: Tesseract OCR로 이미지에서 텍스트 추출
            if TESSERACT_AVAILABLE and metadata['has_images']:
                logger.info(f"OCR 처리 시작: {Path(pdf_path).name} ({metadata['image_count']}개 이미지)")
                ocr_text = self._extract_ocr_text(pdf_path)
                if ocr_text:
                    metadata['ocr_performed'] = True
                    metadata['ocr_text_length'] = len(ocr_text)
                    full_text += f"\n\n[OCR 추출 텍스트]\n{ocr_text}\n"
            
            # 캐시 저장
            self.ocr_cache[pdf_hash] = {
                'text': full_text,
                'metadata': metadata
            }
            self._save_cache(self.ocr_cache_file, self.ocr_cache)

            # 성능 통계 업데이트
            self.ocr_count += 1
            self.total_ocr_time += time.time() - start_time

            return full_text, metadata
            
        except Exception as e:
            logger.error(f"텍스트 추출 실패: {pdf_path} - {e}")
            return full_text, metadata
    
    def _extract_ocr_text(self, pdf_path: str) -> str:
        """Tesseract OCR로 이미지에서 텍스트 추출"""
        ocr_text = ""
        
        try:
            # PDF를 이미지로 변환 (DPI 낮춰서 메모리 절약)
            images = convert_from_path(pdf_path, dpi=self.OCR_DPI)
            
            for page_num, image in enumerate(images, 1):
                try:
                    # Tesseract OCR 실행
                    text = pytesseract.image_to_string(
                        image,
                        lang=self.tesseract_lang,
                        config=self.tesseract_config
                    )
                    
                    if text.strip():
                        # OCR 텍스트 후처리
                        text = self._post_process_text(text)
                        ocr_text += f"\n[OCR 페이지 {page_num}]\n{text}\n"
                        
                except Exception as e:
                    logger.debug(f"페이지 {page_num} OCR 실패: {e}")
            
        except Exception as e:
            logger.warning(f"OCR 처리 실패: {pdf_path} - {e}")
        
        return ocr_text
    
    def _post_process_text(self, text: str) -> str:
        """텍스트 후처리 - 오타 수정 및 포맷팅 (컴파일된 패턴 사용)"""
        # 패턴 기반 수정 적용 (컴파일된 패턴 사용)
        for pattern, replacement in self.compiled_ocr_patterns:
            text = pattern.sub(replacement, text)

        # 숫자 분리 문제 해결 (컴파일된 패턴 사용)
        for pattern, replacement in self.compiled_number_patterns:
            text = pattern.sub(replacement, text)
        
        # OCR로 분리된 한글 단어 복원
        text = self._merge_korean_words(text)
        
        # 불필요한 공백 제거
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def _merge_korean_words(self, text: str) -> str:
        """분리된 한글 단어 병합 (컴파일된 패턴 사용)"""
        # 2-3글자 한글이 공백으로 분리된 경우 합치기
        return self.korean_merge_pattern.sub(
            lambda m: m.group(1) + m.group(2) + m.group(3)
            if len(m.group(1) + m.group(2) + m.group(3)) <= self.MAX_KOREAN_WORD_LENGTH
            else m.group(0),
            text
        )
    
    def get_metadata_from_cache(self, pdf_path: str) -> Optional[Dict]:
        """메타데이터 캐시에서 정보 가져오기"""
        relative_path = f"{self.DOCS_PREFIX}{Path(pdf_path).name}"
        return self.metadata_cache.get(relative_path)
    
    def process_batch(self, pdf_files: List[str], use_multiprocessing: bool = False, max_workers: int = 4) -> Dict[str, Tuple[str, Dict]]:
        """
        여러 PDF 파일 배치 처리 (수백 개 문서 대응)
        """
        results = {}
        total = len(pdf_files)
        start_time = time.time()

        if use_multiprocessing and total > 1:
            # 멀티프로세싱 처리
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_pdf = {executor.submit(self.extract_text_with_ocr, pdf): pdf
                                for pdf in pdf_files}

                for idx, future in enumerate(as_completed(future_to_pdf), 1):
                    pdf_path = future_to_pdf[future]
                    try:
                        text, metadata = future.result()
                        results[pdf_path] = (text, metadata)
                        logger.info(f"처리 완료: {idx}/{total} - {Path(pdf_path).name}")
                    except Exception as e:
                        logger.error(f"처리 실패: {Path(pdf_path).name} - {e}")
                        results[pdf_path] = ("", {})

                    # 메모리 관리 (주기적 캐시 저장)
                    if idx % self.CACHE_SAVE_INTERVAL == 0:
                        self._save_cache(self.ocr_cache_file, self.ocr_cache)
        else:
            # 순차 처리
            for idx, pdf_path in enumerate(pdf_files, 1):
                logger.info(f"처리 중: {idx}/{total} - {Path(pdf_path).name}")
                text, metadata = self.extract_text_with_ocr(pdf_path)
                results[pdf_path] = (text, metadata)

                # 메모리 관리 (주기적 캐시 저장)
                if idx % self.CACHE_SAVE_INTERVAL == 0:
                    self._save_cache(self.ocr_cache_file, self.ocr_cache)

        batch_time = time.time() - start_time
        logger.info(f"배치 처리 완료: {total}개 파일, {batch_time:.2f}초")

        return results

    def get_stats(self) -> Dict:
        """성능 통계 반환"""
        cache_hit_rate = (self.cache_hits / (self.cache_hits + self.cache_misses) * 100
                         if (self.cache_hits + self.cache_misses) > 0 else 0.0)

        stats = {
            'ocr_count': self.ocr_count,
            'total_ocr_time': self.total_ocr_time,
            'avg_ocr_time': self.total_ocr_time / self.ocr_count if self.ocr_count > 0 else 0.0,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'cache_hit_rate': cache_hit_rate,
            'cache_size': {
                'metadata': len(self.metadata_cache),
                'ocr': len(self.ocr_cache)
            },
            'compiled_patterns': {
                'ocr_error': len(self.compiled_ocr_patterns),
                'number': len(self.compiled_number_patterns)
            }
        }
        return stats