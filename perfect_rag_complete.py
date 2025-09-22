
#!/usr/bin/env python3
"""
Perfect RAG - 완전히 정리된 버전
자산 코드 제거, 기안서 문서 검색 전용
"""

import re
import warnings
import logging
import pdfplumber
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import sys
import os
from functools import lru_cache
import hashlib
import time
from contextlib import nullcontext

#   
try:
    from log_system import get_logger, TimerContext
    logger = get_logger()
except ImportError:
    logger = None
    TimerContext = None
    
# query_logger log_system 

#   
try:
    from response_formatter import ResponseFormatter
except ImportError:
    ResponseFormatter = None

# FontBBox   
warnings.filterwarnings("ignore", message=".*FontBBox.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pdfplumber")

# pdfplumber   
logging.getLogger("pdfplumber").setLevel(logging.ERROR)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

#    
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

#   import
try:
    from config_manager import config_manager as cfg
    USE_YAML_CONFIG = True
except ImportError:
    import config as cfg
    USE_YAML_CONFIG = False

from rag_system.qwen_llm import QwenLLM
from rag_system.llm_singleton import LLMSingleton
from metadata_manager import MetadataManager

#   import ( -   )
# from pdf_parallel_processor import PDFParallelProcessor
# from error_handler import RAGErrorHandler, ErrorRecovery, DetailedError, safe_execute

class PerfectRAG:
    """  RAG """

    def _load_performance_config(self):
        """performance_config.yaml """
        import yaml
        perf_config_path = Path(__file__).parent / 'performance_config.yaml'
        if perf_config_path.exists():
            try:
                with open(perf_config_path, 'r', encoding='utf-8') as f:
                    self.perf_config = yaml.safe_load(f)
                    if logger:
                        logger.system_logger.info(f"Performance config loaded from {perf_config_path}")
            except Exception as e:
                if logger:
                    logger.system_logger.warning(f"Failed to load performance config: {e}")
                self.perf_config = {}
        else:
            self.perf_config = {}

    #    - config.yaml 
    def _get_manufacturer_pattern(self):
        if USE_YAML_CONFIG:
            manufacturers = cfg.get('patterns.manufacturers', [])
            if manufacturers:
                pattern = '|'.join(manufacturers)
                return rf'\b({pattern})\b'
        return r'\b(SONY|Sony|HARRIS|Harris|HP|TOSHIBA|Toshiba|PANASONIC|Panasonic|CANON|Canon|NIKON|Nikon|DELL|Dell|APPLE|Apple|SAMSUNG|Samsung|LG)\b'

    def _get_model_pattern(self):
        if USE_YAML_CONFIG:
            return cfg.get('patterns.model_regex', r'\b[A-Z]{2,}[-\s]?\d+')
        return r'\b[A-Z]{2,}[-\s]?\d+'
    
    def __init__(self, preload_llm=False):
        # performance_config.yaml  
        self._load_performance_config()

        #   (YAML )
        if USE_YAML_CONFIG:
            self.docs_dir = Path(cfg.get('paths.documents_dir', './docs'))
            self.model_path = cfg.get('models.qwen.path', './models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.ggu')
            self.max_cache_size = self.perf_config.get('cache', {}).get('max_size', 500)
            self.cache_ttl = self.perf_config.get('cache', {}).get('response_ttl', 7200)
            self.max_text_length = self.perf_config.get('memory', {}).get('max_document_length', 8000)
            self.max_pdf_pages = cfg.get('limits.max_pdf_pages', 10)
            self.pdf_workers = self.perf_config.get('parallel', {}).get('pdf_workers', 4)
            self.chunk_size = self.perf_config.get('parallel', {}).get('chunk_size', 5)
        else:
            self.docs_dir = Path(cfg.DOCS_DIR)
            self.model_path = cfg.QWEN_MODEL_PATH
            self.max_cache_size = self.perf_config.get('cache', {}).get('max_size', 500)
            self.cache_ttl = self.perf_config.get('cache', {}).get('response_ttl', 7200)
            self.max_text_length = self.perf_config.get('memory', {}).get('max_document_length', 8000)
            self.max_pdf_pages = getattr(cfg, 'MAX_PDF_PAGES', 10)
            self.pdf_workers = self.perf_config.get('parallel', {}).get('pdf_workers', 4)
            self.chunk_size = self.perf_config.get('parallel', {}).get('chunk_size', 5)

        self.llm = None
        #    (   TTL)
        from collections import OrderedDict
        self.documents_cache = OrderedDict()  # LRU  
        self.metadata_cache = OrderedDict()  #  
        self.answer_cache = OrderedDict()  #   (LRU)
        self.pdf_text_cache = OrderedDict()  # PDF    ( )

        # PDF    ( -   )
        # self.pdf_processor = PDFParallelProcessor(config_manager=cfg if USE_YAML_CONFIG else None)
        # self.error_handler = RAGErrorHandler()
        # self.error_recovery = ErrorRecovery()
        self.pdf_processor = None
        self.error_handler = None
        self.error_recovery = None
        
        #   
        self.formatter = ResponseFormatter() if ResponseFormatter else None

        #  DB 
        try:
            self.metadata_db = MetadataManager()
        except Exception as e:
            print(f" MetadataManager  : {e}")
            self.metadata_db = None
        
        #  PDF TXT   (   )
        self.pdf_files = []
        self.txt_files = []

        #   
        self.pdf_files.extend(list(self.docs_dir.glob('*.pd')))
        self.txt_files.extend(list(self.docs_dir.glob('*.txt')))

        #   (year_2014 ~ year_2025)
        for year in range(2014, 2026):
            year_folder = self.docs_dir / f"year_{year}"
            if year_folder.exists():
                self.pdf_files.extend(list(year_folder.glob('*.pd')))
                self.txt_files.extend(list(year_folder.glob('*.txt')))

        #      
        #    year_*  
        # category_folders = ['category_purchase', 'category_repair', 'category_review',
        #                   'category_disposal', 'category_consumables']
        # for folder in category_folders:
        #     cat_folder = self.docs_dir / folder
        #     if cat_folder.exists():
        #         self.pdf_files.extend(list(cat_folder.glob('*.pd')))
        #         self.txt_files.extend(list(cat_folder.glob('*.txt')))

        special_folders = ['recent', 'archive']
        for folder in special_folders:
            special_folder = self.docs_dir / folder
            if special_folder.exists():
                self.pdf_files.extend(list(special_folder.glob('*.pd')))
                self.txt_files.extend(list(special_folder.glob('*.txt')))

        #   (      )
        self.pdf_files = list(set(self.pdf_files))
        self.txt_files = list(set(self.txt_files))
        self.all_files = self.pdf_files + self.txt_files

        print(f" {len(self.pdf_files)} PDF, {len(self.txt_files)} TXT  ")

        #     ( )
        self._build_metadata_cache()

        # LLM   
        if preload_llm:
            self._preload_llm()

    def _preload_llm(self):
        """LLM   ( )"""
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                print(" LLM    ...")
            else:
                print(" LLM  ")
            
            try:
                start = time.time()
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                elapsed = time.time() - start
                if elapsed > 1.0:  # 1    
                    print(f" LLM   ({elapsed:.1f})")
            except Exception as e:
                print(f" LLM  : {e}")
    
    def _manage_cache(self, cache_dict, key, value):
        """   - LRU """
        if key in cache_dict:
            #     (  )
            cache_dict.move_to_end(key)
        else:
            #   
            if len(cache_dict) >= self.max_cache_size:
                #    
                cache_dict.popitem(last=False)
            cache_dict[key] = (value, time.time())  #   
    
    def _get_from_cache(self, cache_dict, key):
        """  (TTL    )"""
        if key in cache_dict:
            cache_value = cache_dict[key]
            current_time = time.time()

            #   (value, timestamp) 
            if isinstance(cache_value, tuple) and len(cache_value) == 2:
                value, timestamp = cache_value

                if current_time - timestamp < self.cache_ttl:
                    # LRU:    
                    cache_dict.move_to_end(key)
                    #   (  )
                    cache_dict[key] = (value, current_time)
                    return value
                else:
                    # TTL  - 
                    del cache_dict[key]
                    return None
            else:
                #    (  )
                cache_dict.move_to_end(key)
                return cache_value

        return None
    
    def _parse_pdf_result(self, result: Dict) -> Dict:
        """     """
        return {
            'text': result.get('text', ''),
            'page_count': result.get('page_count', 0),
            'metadata': result.get('metadata', {}),
            'method': result.get('method', 'parallel')
        }

    def process_pdfs_in_batch(self, pdf_paths: List[Path], batch_size: int = 5) -> Dict:
        """ PDF    ( )"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import gc

        all_results = {}

        # pdf_processor    
        if self.pdf_processor is None:
            print("    -   ")

            # ThreadPoolExecutor   
            with ThreadPoolExecutor(max_workers=min(4, batch_size)) as executor:
                for i in range(0, len(pdf_paths), batch_size):
                    batch = pdf_paths[i:i + batch_size]
                    print(f"  {i//batch_size + 1}/{(len(pdf_paths)-1)//batch_size + 1}   ({len(batch)} )")

                    #  PDF  
                    futures = {executor.submit(self._extract_pdf_info, pdf): pdf for pdf in batch}

                    for future in as_completed(futures):
                        pdf_path = futures[future]
                        try:
                            result = future.result(timeout=30)  # 30 
                            all_results[str(pdf_path)] = result
                        except Exception as e:
                            print(f"   {pdf_path.name}  : {str(e)[:50]}")
                            all_results[str(pdf_path)] = {'error': str(e)}

                    #  
                    if i % (batch_size * 5) == 0:
                        gc.collect()
        else:
            #  pdf_processor 
            for i in range(0, len(pdf_paths), batch_size):
                batch = pdf_paths[i:i + batch_size]
                print(f" {i//batch_size + 1}   ({len(batch)} )")

                batch_results = self.pdf_processor.process_multiple_pdfs(batch)
                all_results.update(batch_results)

                #  
                if len(self.pdf_processor.extraction_cache) > 50:
                    self.pdf_processor.clear_cache()

        return all_results

    def _find_metadata_by_filename(self, filename: str) -> Optional[Dict]:
        """   (   )"""
        #    
        if filename in self.metadata_cache:
            return self.metadata_cache[filename]

        #     
        for cache_key, metadata in self.metadata_cache.items():
            if metadata.get('filename') == filename:
                return metadata

        return None

    def _build_metadata_cache(self):
        """     ( )"""

        print("    ...")

        #    
        use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

        #      process_pdfs_in_batch  ( )
        if self.pdf_files and len(self.pdf_files) > 10:  # 10    
            print(f" {len(self.pdf_files)} PDF   ( )...")
            pdf_results = self.process_pdfs_in_batch(self.pdf_files, batch_size=10)

            #      
            for pdf_path, result in pdf_results.items():
                pdf_path_obj = Path(pdf_path)
                filename = pdf_path_obj.name
                #     (  )
                try:
                    relative_path = pdf_path_obj.relative_to(self.docs_dir)
                    cache_key = str(relative_path)
                except ValueError:
                    cache_key = filename

                if 'error' not in result:
                    self.metadata_cache[cache_key] = {
                        'path': pdf_path_obj,
                        'filename': filename,
                        'text': result.get('text', '')[:1000],  #  
                        'page_count': result.get('page_count', 0),
                        'metadata': result.get('metadata', {})
                    }
        
        # PDF TXT   
        for file_path in self.all_files:
            filename = file_path.name

            #     
            try:
                relative_path = file_path.relative_to(self.docs_dir)
                cache_key = str(relative_path)
            except ValueError:
                cache_key = filename

            #    
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filename)
            date = date_match.group(1) if date_match else ""

            #   (  ,  )
            if filename.endswith('.pd'):
                title = filename.replace(date + '_', '').replace('.pd', '') if date else filename.replace('.pd', '')
            else:
                title = filename.replace(date + '_', '').replace('.txt', '') if date else filename.replace('.txt', '')

            #  
            year = date[:4] if date else ""

            #     
            keywords = []

            #     
            # , ,   
            words = re.findall(r'[-]+|[A-Za-z]+|\d+', filename)

            #      (2 )
            for word in words:
                if len(word) >= 2 and word not in ['pd', 'PDF', 'txt', 'TXT', '', '', '', '']:
                    keywords.append(word)

            self.metadata_cache[cache_key] = {
                'path': file_path,
                'filename': filename,  #   
                'date': date,
                'year': year,
                'title': title,
                'keywords': keywords,
                'drafter': None,  #    
                'full_text': None,  #   
                'is_txt': filename.endswith('.txt'),  # TXT  
                'is_pd': filename.endswith('.pd')  # PDF   
            }

        print(f" {len(self.metadata_cache)}    ")
    
    def _extract_txt_info(self, txt_path: Path) -> Dict:
        """TXT    """
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            info = {'text': text[:3000]}  #  3000
            
            return info

        except Exception as e:
            if logger:
                print(f" TXT   ({txt_path.name}): {e}")
            else:
                print(f" TXT   ({txt_path.name}): {e}")
            #      
            # error_handler  -   
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content:
                    return {'text': content[:3000]}
            except Exception:
                pass
            return {}

    #   (error_handler   )
    # @RAGErrorHandler.retry_with_backoff(max_retries=3, backoff_factor=1.5)
    # @RAGErrorHandler.handle_pdf_extraction_error

    def _optimize_context(self, text: str, query: str, max_length: int = 3000) -> str:
        """  -     """
        if not text or len(text) <= max_length:
            return text

        #   
        keywords = re.findall(r'[-]+|[A-Za-z]+|\d+', query.lower())
        keywords = [k for k in keywords if len(k) >= 2]

        #   
        sentences = re.split(r'[.!?\n]+', text)

        #     
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            score = 0
            sentence_lower = sentence.lower()

            #   
            for keyword in keywords:
                if keyword in sentence_lower:
                    score += 10

            #   
            if re.search(r'\d+[,\d]*\s*', sentence):  # 
                score += 5
            if re.search(r'\d{4}[-]', sentence):  # 
                score += 3
            if re.search(r'||', sentence):  #  
                score += 3

            #   (  )
            position_score = max(0, 5 - i * 0.1)
            score += position_score

            scored_sentences.append((sentence, score))

        #   
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        #    
        result = []
        current_length = 0

        for sentence, score in scored_sentences:
            if current_length + len(sentence) > max_length:
                break
            result.append(sentence)
            current_length += len(sentence)

        #   
        result_text = '. '.join(result)
        return result_text if result_text else text[:max_length]

    def _extract_pdf_info_with_retry(self, pdf_path: Path) -> Dict:
        """PDF   (     )"""
        max_retries = 2
        retry_count = 0

        while retry_count < max_retries:
            try:
                #     
                use_parallel = USE_YAML_CONFIG and cfg.get('parallel_processing.enabled', True)

                if use_parallel and self.pdf_processor is not None:
                    #   PDF 
                    results = self.pdf_processor.process_multiple_pdfs([pdf_path])
                    result = results.get(str(pdf_path), {})

                    if 'error' not in result:
                        return self._parse_pdf_result(result)
                    else:
                        #    
                        print(f"   ,   : {pdf_path.name}")
                        result = self._extract_pdf_info(pdf_path)
                else:
                    #   (   )
                    result = self._extract_pdf_info(pdf_path)

                #  
                if result:
                    return result

                #    OCR 
                if hasattr(self, '_try_ocr_extraction'):
                    ocr_text = self._try_ocr_extraction(pdf_path)
                    if ocr_text:
                        return {'text': ocr_text, 'is_ocr': True}

                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(0.5)  #   

            except MemoryError:
                print(f"    : {pdf_path.name} ( {retry_count + 1}/{max_retries})")
                import gc
                gc.collect()  #  
                retry_count += 1

            except FileNotFoundError:
                print(f"    : {pdf_path}")
                break  #    

            except Exception as e:
                print(f"   PDF   ({retry_count + 1}/{max_retries}): {pdf_path.name}")
                print(f"     : {type(e).__name__}: {str(e)[:50]}")
                retry_count += 1

        return {}
    
    def _extract_pdf_info(self, pdf_path: Path) -> Dict:
        """ PDF   () -  """
        #    (  )
        cache_key = str(pdf_path)

        #   
        if cache_key in self.pdf_text_cache:
            #   - LRU    
            cached_result = self.pdf_text_cache.pop(cache_key)
            self.pdf_text_cache[cache_key] = cached_result
            return cached_result

        text = ""

        #     
        def extract_with_pdfplumber():
            nonlocal text
            with pdfplumber.open(pdf_path) as pdf:
                #       
                pages_to_read = min(len(pdf.pages), self.max_pdf_pages)
                for page in pdf.pages[:pages_to_read]:
                    # safe_execute  (error_handler   )
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    if page_text:
                        text += page_text + "\n"
                        #     ( )
                        if len(text) > self.max_text_length:
                            break
            return text

        #   
        # error_recovery   
        text = extract_with_pdfplumber()
        if not text and hasattr(self, '_try_ocr_extraction'):
            text = self._try_ocr_extraction(pdf_path)

        # pdfplumber  OCR 
        if not text:
            try:
                from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
                ocr = EnhancedOCRProcessor()
                text, _ = ocr.extract_text_with_ocr(str(pdf_path))
            except Exception:
                pass  # OCR  

        if not text:
            return {}

        info = {}

        #   ( )
        patterns = [
            r'[\s:]*([-]+)',
            r'[\s:]*([-]+)',
            r'[\s:]*([-]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                info[''] = match.group(1).strip()
                break
            
        #   (  ,  fallback)
        date_patterns = [
            r'[\s:]*(\d{4}[-]\s*\d{1,2}[-]\s*\d{1,2})',
            r'[\s:]*(\d{4}[-]\s*\d{1,2}[-]\s*\d{1,2})',
            r'(\d{4}-\d{2}-\d{2})\s*\d{2}:\d{2}',
            r'[\s:]*(\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2})',
            r'[\s:]*(\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2})',
            r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})'  #   
        ]

        date_found = False
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                info[''] = match.group(1).strip()
                date_found = True
                break

        #        
        if not date_found:
            filename = pdf_path.name
            #     (YYYY-MM-DD, YYYY.MM.DD, YYYY_MM_DD )
            filename_date_patterns = [
                r'(20\d{2}[-_.]0?[1-9]|1[0-2][-_.][0-2]?\d|3[01])',  # YYYY-MM-DD
                r'(20\d{2})[-_.]?(\d{1,2})[-_.]?(\d{1,2})',  # YYYY MM DD ( )
            ]

            for pattern in filename_date_patterns:
                match = re.search(pattern, filename)
                if match:
                    if len(match.groups()) == 1:
                        #   
                        date_str = match.group(1)
                        date_str = date_str.replace('_', '-').replace('.', '-')
                        info[''] = date_str
                        date_found = True
                        break
                    elif len(match.groups()) == 3:
                        #   
                        year, month, day = match.groups()
                        try:
                            normalized_date = f"{year}-{int(month):02d}-{int(day):02d}"
                            info[''] = normalized_date
                            date_found = True
                            break
                        except ValueError:
                            continue
            
            #   (  )
            #  1:  
            dept_match = re.search(r'[\s:]*([^\n]+)', text)
            if dept_match:
                dept = dept_match.group(1).strip()
                dept = dept.split('')[0].strip()
                info[''] = dept
            
            #  2: -  (A )
            if '' not in info:
                team_match = re.search(r'([-]+[\--]+)', text)
                if team_match:
                    info[''] = team_match.group(1)
            
            #   (  )
            amounts = re.findall(r'(\d{1,3}(?:,\d{3})*)\s*', text)
            if amounts:
                numeric_amounts = []
                for amt in amounts:
                    try:
                        num = int(amt.replace(',', ''))
                        numeric_amounts.append((num, amt))
                    except (ValueError, AttributeError):
                        pass  #    
                if numeric_amounts:
                    numeric_amounts.sort(reverse=True)
                    info[''] = f"{numeric_amounts[0][1]}"
            
            #  
            title_match = re.search(r'[\s:]*([^\n]+)', text)
            if title_match:
                info[''] = title_match.group(1).strip()
            
            #  
            info['text'] = text[:3000]  #  3000

        #   (  )
        MAX_PDF_CACHE_SIZE = 50  #  50 PDF 
        if len(self.pdf_text_cache) >= MAX_PDF_CACHE_SIZE:
            #     (LRU)
            self.pdf_text_cache.popitem(last=False)

        #    
        self.pdf_text_cache[cache_key] = info

        return info
    
    def find_best_document(self, query: str) -> Optional[Path]:
        """     -  """
        
        query_lower = query.lower()
        
        # PDF     
        pdf_priority_keywords = [
            '', '', '', '', '', '',
            '', '', '', '', '', '',
            '', '', '', '', '', ''
        ]
        
        # PDF      
        if any(keyword in query for keyword in pdf_priority_keywords):
            # PDF   
        else:
            
            #    ( 3    )
            manufacturer_pattern = r'\b[A-Z]{3,}\b|SONY|Sony|Harris|Toshiba|Panasonic|Canon|Nikon'
            
            if ('' in query and '' in query) or \
               ('' in query and '' in query) or \
               re.search(r'\d{6,}', query) or \
        
        candidates = []
        
        #   
        #    
        query_tokens = set(query_lower.split())
        
        #   
        year_match = re.search(r'(20\d{2})', query)
        query_year = year_match.group(1) if year_match else None
        
        #   (1, 01, 1-   )
        month_match = re.search(r'(\d{1,2})\s*', query)
        query_month = None
        if month_match:
            query_month = int(month_match.group(1))
        
        for cache_key, metadata in self.metadata_cache.items():
            score = 0
            filename = metadata.get('filename', cache_key)
            filename_lower = filename.lower()
            
            # 1.   
            if query_year:
                if metadata['year'] == query_year:
                    score += 20
                    
                    #     
                    if query_month:
                        #    (YYYY-MM-DD )
                        file_month_match = re.search(r'\d{4}-(\d{2})-\d{2}', filename)
                        if file_month_match:
                            file_month = int(file_month_match.group(1))
                            if file_month == query_month:
                                score += 30  #    
                            else:
                                continue  #   
                else:
                    continue  #   
            
            # 2.  /   (  )
            #    -   
            #   
            query_words = re.findall(r'[-]+|[A-Za-z]+|[0-9]+', query_lower)
            filename_words = re.findall(r'[-]+|[A-Za-z]+|[0-9]+', filename_lower)
            
            #    (2 )
            for q_word in query_words:
                if len(q_word) >= 2:
                    for f_word in filename_words:
                        if len(f_word) >= 2:
                            #  
                            if q_word == f_word:
                                #     
                                weight = len(q_word) * 2
                                score += weight
                            #   ( )
                            elif self._calculate_similarity(q_word, f_word) >= 0.8:
                                # 80%    
                                weight = len(q_word) * 1.5
                                score += weight
                            #   (  )
                            elif len(q_word) >= 3 and len(f_word) >= 3:
                                if q_word in f_word or f_word in q_word:
                                    weight = min(len(q_word), len(f_word))
                                    score += weight
            
            # 3.   ()
            for keyword in metadata['keywords']:
                if keyword.lower() in query_lower:
                    score += 5
            
            # 4.    ( )
            filename_tokens = set(filename_lower.replace('_', ' ').replace('-', ' ').split())
            common_tokens = query_tokens & filename_tokens
            score += len(common_tokens) * 2
            
            # 5.   
            #     
            important_words = [w for w in query_lower.split() if len(w) > 2]
            for word in important_words:
                if word in filename_lower:
                    score += 3
            
            # 6.    
            # "", " "    
            doc_types = ['', ' ', '', ' ', '']
            for doc_type in doc_types:
                if doc_type in query and doc_type in filename:
                    score += 5
            
            if score > 0:
                candidates.append((score, metadata['path'], filename))
        
        #  
        candidates.sort(reverse=True)
        
        #   ( 3)
        if candidates:
            top_score = candidates[0][0]
            #   
            same_score = [c for c in candidates if c[0] == top_score]
            if len(same_score) > 1:
                #       
                same_score.sort(key=lambda x: len(x[2]))
                return same_score[0][1]
            return candidates[0][1]
        
        return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:

           +    

        #     
        if abs(len(str1) - len(str2)) > 2:
            return 0.0

        #    
        def levenshtein_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)

            if len(s2) == 0:
                return len(s1)

            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    # , ,   
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        #    
        distance = levenshtein_distance(str1, str2)
        max_len = max(len(str1), len(str2))
        similarity = 1 - (distance / max_len) if max_len > 0 else 1.0

        #   : /    
        # : /, / 
        if len(str1) == len(str2) and distance == 1:
            #    
            if all(ord('') <= ord(c) <= ord('') for c in str1 + str2):
                similarity = max(similarity, 0.85)

        return similarity

    def get_document_info(self, file_path: Path, info_type: str = "all") -> str:
        """    (PDF/TXT  )"""
        
        #  
        cache_key = f"{file_path.name}_{info_type}"
        if cache_key in self.documents_cache:
            return self.documents_cache[cache_key]
        
        #     
        if file_path.suffix == '.txt':
            info = self._extract_txt_info(file_path)
        else:
            info = self._extract_pdf_info(file_path)
        
        if not info:
            return "    "
        
        result = ""
        
        #   
        if info_type == "all":
            result = f" {file_path.stem}\n"
            result += "\n"
            for key, value in info.items():
                if key != 'text':
                    result += f" {key}: {value}\n"
        elif info_type == "":
            result = f" : {info.get('', ' ')}"
        elif info_type == "":
            result = f" : {info.get('', ' ')}"
        elif info_type == "":
            result = f" : {info.get('', ' ')}"
        elif info_type == "":
            amount = info.get('', ' ')
            result = f" : {amount}"
        else:
            #   
            if info_type in info:
                result = f" {info_type}: {info[info_type]}"
            else:
                result = f" {info_type}    "
            
            #    -   
            if amount != ' ' and len(result) < 50:
                #   
                result += "\n\n  :\n"
                result += f" : {file_path.stem}\n"
                if '' in info:
                    result += f" : {info['']}\n"
                if '' in info:
                    result += f" : {info['']}\n"
                if '' in info:
                    result += f" : {info['']}\n"
                if '' in info:
                    result += f" : {info['']}\n"
        elif info_type == "":
            #   
            result = f" {file_path.stem} \n"
            result += "\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
        else:  # all
            # LLM    
            result = f" {file_path.stem}\n\n"
#             result += " ** **\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
            if '' in info:
                result += f" : {info['']}\n"
            
#             result += "\n ** **\n"
            
            # text     (  )
            if 'text' in info:
                summary = self._generate_smart_summary(info['text'], file_path)
                result += summary
            
            if '' in info and info[''] != ' ':
#                 result += "\n ** **\n"
                result += f" : {info['']}\n"
            
            result += f"\n : {file_path.name}"
        
        #  
        self.documents_cache[cache_key] = result
        
        return result

    def _generate_smart_summary(self, text: str, file_path: Path) -> str:
        """     """

        #  
        text = text[:3000]  #  3000 
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        summary_parts = []

        # 1.    (, ,  )
        equipment_keywords = []
        financial_keywords = []
        company_keywords = []

        #   (  +  )
        equipment_pattern = r'\b[A-Z][A-Za-z0-9\-]{2,20}\b'
        equipment_matches = re.findall(equipment_pattern, text)
        for match in equipment_matches:
            if len(match) >= 3 and not match.isdigit():
                equipment_keywords.append(match)

        #  
        amount_pattern = r'(\d{1,3}(?:,\d{3})*)\s*(?:||)'
        amount_matches = re.findall(amount_pattern, text)
        if amount_matches:
            financial_keywords.extend([f"{amt}" for amt in amount_matches[:3]])

        #  (, (),  )
        company_pattern = r'(?:\s*|\s*|\(\)\s*)?([-A-Za-z]{2,20})(?:\s*|\s*|\s*\(\))?'
        company_matches = re.findall(company_pattern, text)
        for match in company_matches:
            if len(match) >= 2 and match not in ['', '', '', '']:
                company_keywords.append(match)

        # 2.     
        file_name = file_path.name.lower()

        if '' in file_name or '' in file_name:
            #  
            purchase_info = []
            if equipment_keywords:
                purchase_info.append(f" : {', '.join(set(equipment_keywords[:3]))}")
            if financial_keywords:
                purchase_info.append(f" : {', '.join(financial_keywords[:2])}")
            if company_keywords:
                purchase_info.append(f" : {', '.join(set(company_keywords[:2]))}")

            if purchase_info:
                summary_parts.append(" " + " | ".join(purchase_info))

        elif '' in file_name or '' in file_name:
            #  
            repair_info = []
            if equipment_keywords:
                repair_info.append(f" : {', '.join(set(equipment_keywords[:3]))}")
            if financial_keywords:
                repair_info.append(f" : {', '.join(financial_keywords[:2])}")

            if repair_info:
                summary_parts.append(" " + " | ".join(repair_info))

        elif '' in file_name:
            #  
            disposal_info = []
            if equipment_keywords:
                disposal_info.append(f" : {', '.join(set(equipment_keywords[:3]))}")

            if disposal_info:
                summary_parts.append(" " + " | ".join(disposal_info))

        # 3.    
        important_lines = []
        priority_keywords = [
            '', '', '', '', '', '',
            '', '', '', '', '', '',
            '1.', '2.', '3.', '', '', '', '', ''
        ]

        for line in lines[:30]:  #  30 
            if len(line) > 15:  #    
                #    
                for keyword in priority_keywords:
                    if keyword in line:
                        cleaned_line = line.replace(keyword, '').strip()
                        if len(cleaned_line) > 10:
                            important_lines.append(f" {cleaned_line[:80]}{'...' if len(cleaned_line) > 80 else ''}")
                        break

        #       
        if not important_lines:
            for line in lines[:5]:
                if len(line) > 20 and not line.isdigit():
                    important_lines.append(f" {line[:80]}{'...' if len(line) > 80 else ''}")
                    if len(important_lines) >= 3:
                        break

        #   
        result = ""
        if summary_parts:
            result += "\n".join(summary_parts) + "\n\n"

        if important_lines:
            result += "\n".join(important_lines[:4])  #  4

        return result if result else "    ..."

    def _remove_duplicate_documents(self, documents: list) -> list:
        """   ( )"""
        seen = set()
        unique_docs = []

        for doc in documents:
            #     
            filename = Path(doc.get('path', doc.get('filename', ''))).name
            if filename not in seen:
                seen.add(filename)
                unique_docs.append(doc)

        return unique_docs

    def _format_enhanced_response(self, results: list, query: str) -> str:
        """  """
        if not results:
            return "     ."

        #  
        unique_results = self._remove_duplicate_documents(results)

#         response = f" ** ** ({len(unique_results)} )\n\n"

        for i, doc in enumerate(unique_results[:5], 1):  #  5 
            title = doc.get('title', ' ')
            date = doc.get('date', ' ')
            category = doc.get('category', '')
            drafter = doc.get('drafter', '')

            #   
            if date and date != ' ' and len(date) >= 10:
                display_date = date[:10]  # YYYY-MM-DD
            elif date and len(date) >= 4:
                display_date = date[:4]  # 
            else:
                display_date = ""

            response += f"**{i}. [{category}] {title}**\n"
            response += f"    {display_date} |  {drafter}\n"

            #   
            if 'path' in doc:
                try:
                    file_path = Path(doc['path'])
                    if file_path.exists():
                        summary = self._generate_smart_summary("", file_path)
                        if summary and summary != "    ...":
                            response += f"   {summary}\n"
                except Exception:
                    pass

            response += "\n"

        if len(unique_results) > 5:
            response += f"...  {len(unique_results) - 5}   \n\n"

        response += " **     .**"

        return response

    def _classify_search_intent(self, query: str) -> str:
        
        Returns:
            'document': PDF / 

        query_lower = query.lower()
        
        #     ()
        document_keywords = [
            '', '', '', '', ' ', '', 
            '', 'pd', ' ', ' ', '',
            '', '', '', ' ',
            '', '', '', '', '', '',
            '', '', ''
        ]
        
            '', '', '', ' ', ' ',
        ]
        
        #  
        manufacturer_pattern = self._get_manufacturer_pattern()
        model_pattern = self._get_model_pattern()
        
        #   
        doc_score = 0
        
        #   
        for keyword in document_keywords:
            if keyword in query_lower:
                doc_score += 2
        
            if keyword in query_lower:
        
        #   '', ''   
        if re.search(r'20\d{2}', query) and any(w in query for w in ['', '', '', '']):
            doc_score += 3
        
        if re.search(manufacturer_pattern, query) or re.search(model_pattern, query, re.IGNORECASE):

        #  ' ', ''      
        if not any(w in query_lower for w in ['', '', '', '', '']):
            equipment_names = ['dvr', 'ccu', '', '', '', '', '', '']
            for equipment in equipment_names:
                if equipment in query_lower:
        
        if re.search(r'\d+|\d+|\s*|\s*', query):
        
        #  
    def answer_from_specific_document(self, query: str, filename: str) -> str:

        
        Args:
            query:  
            filename:   
        """"
        print(f"   : {filename}")
        
        #    
        doc_metadata = self._find_metadata_by_filename(filename)
        if not doc_metadata:
            return f"    : {filename}"
        doc_path = doc_metadata['path']
        
        # PDF TXT 
        if filename.endswith('.pd'):
            # PDF   -   
            info = self._extract_pdf_info_with_retry(doc_path)
            if not info.get('text'):
                return f" PDF    : {filename}"
            
            # LLM 
            if self.llm is None:
                print(" LLM   ...")
                self._preload_llm()
            
            #     (15000 )
            full_text = info['text'][:15000]
            
            #     
            if any(word in query for word in ['', '', '', '']):
                prompt = self._create_detailed_summary_prompt(query, full_text, filename)
            elif any(word in query for word in ['', '', '', '', '']):
                prompt = self._create_ultra_detailed_prompt(query, full_text, filename)
            elif any(word in query for word in ['', '', '', '']):
                prompt = self._create_itemized_list_prompt(query, full_text, filename)
            else:
                prompt = self._create_document_specific_prompt(query, full_text, filename)
            
            # LLM   (   )
            try:
                #       
                context_chunks = [
                    {
                        'content': full_text,
                        'source': filename,
                        'metadata': {
                            'filename': filename,
                            'date': doc_metadata.get('date', ''),
                            'title': doc_metadata.get('title', ''),
                            'is_document_only_mode': True  #    
                        }
                    }
                ]
                
                response = self.llm.generate_response(query, context_chunks)
                answer = response.answer if hasattr(response, 'answer') else str(response)
                
                #    
                if len(answer) < 200 and '' in query:
                    answer = self._enhance_short_answer(answer, full_text, query)
                    
            except Exception as e:
                print(f"LLM : {e}")
                # :    
                answer = self._detailed_text_search(info['text'], query, filename)
            
            #  
            answer += f"\n\n ****: {filename}"
            
        elif filename.endswith('.txt'):
        else:
            return f"    : {filename}"
        
        return answer
    
    def _simple_text_search(self, text: str, query: str, filename: str) -> str:
        """    (LLM )"""
        lines = text.split('\n')
        relevant_lines = []
        
        #   
        keywords = re.findall(r'[-]+|[A-Za-z]+|\d+', query)
        
        #   
        for line in lines:
            if any(keyword in line for keyword in keywords if len(keyword) > 1):
                relevant_lines.append(line.strip())
        
        if relevant_lines:
            return f" {filename}   :\n\n" + '\n'.join(relevant_lines[:20])
        else:
            return f" {filename} '{query}'     ."
    
    def _detailed_text_search(self, text: str, query: str, filename: str) -> str:
        """    (LLM )"""
        lines = text.split('\n')
        relevant_sections = []
        
        #   
        keywords = re.findall(r'[-]+|[A-Za-z]+|\d+', query)
        
        #    (  )
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in keywords if len(keyword) > 1):
                #  2 
                start = max(0, i-2)
                end = min(len(lines), i+3)
                section = '\n'.join(lines[start:end])
                if section not in relevant_sections:
                    relevant_sections.append(section)
        
        if relevant_sections:
            return f" **{filename}**  :\n\n" + '\n---\n'.join(relevant_sections[:10])
        else:
            return f" {filename} '{query}'     ."
    
    def _enhance_short_answer(self, answer: str, full_text: str, query: str) -> str:
        """  """
        enhanced = answer + "\n\n **  **:\n"
        
        #     
        keywords = re.findall(r'[-]+|[A-Za-z]+|\d+', query)
        lines = full_text.split('\n')
        
        additional_info = []
        for line in lines:
            if any(keyword in line for keyword in keywords if len(keyword) > 2):
                if line.strip() and line not in answer:
                    additional_info.append(f" {line.strip()}")
        
        if additional_info:
            enhanced += '\n'.join(additional_info[:10])
        
        return enhanced
    
    def _create_detailed_summary_prompt(self, query: str, context: str, filename: str) -> str:
        """    -  """
        return """"
[   ]

: {filename}

 **  ( )**:

 [ ]

 : []
 : [ ]
 : [ ]
  : [// ]

[   ]
 [/]
 [/]
 [/]
 [ ...]

#  ** ** ( )
 : []
  :
  - [/]: []
  - [ ]: []

 [ 1]
 [ 2]
 : [ /]

 : {filename}

 :
{context}

: {query}

 :    ,     .
""""
    
    def _create_ultra_detailed_prompt(self, query: str, context: str, filename: str) -> str:
        """   """
        return """"
[  ] -   

: {filename}
: {query}

 **  **:

1.      
2.     
3.  , , ,    
4.     
5.     

  :
{context}

 :
  500   
    
   **** 
     
""""
    
    def _create_itemized_list_prompt(self, query: str, context: str, filename: str) -> str:
        """   """
        return """"
[/   ]

: {filename}

   /  :

#  ** **:
1. /
   - : 
   - :
   - :
   - :
   - :
   - :
   - :
   - :

2. ( ...)

 :
{context}

: {query}

: 
-     
-     
-    
""""
    
    def _create_document_specific_prompt(self, query: str, context: str, filename: str) -> str:
        """     -  """
        return """"
[    ] 

   : {filename}

     .

 **  ( )**:

 [ ]

 : [  ]
 : [ ]
  : [// ]

[     ]
 [  1]
 [  2]
 [ ...]

#  ** ** (    )
 : []
  :
  - [1]: []
  - [2]: []

#  ** ** (   )
 [ 1]
 [ 2]
 : [ ]

 : {filename}

 **  **:
{context}

#  ** **: {query}

 :
-     
-       
-    
-     
""""
    
    def _get_enhanced_cache_key(self, query: str, mode: str) -> str:
        """    -"

        :
        - "2020  "  "2020  "
        - "2020  "  "2020  "
        - " 2020 "  "2020  " ()
        """"

        # 1.     
        normalized = query.strip().lower()

        # 2.    -  
        #    (,  )
        compound_particles = ['', '', '', '', '', '',
                            '', '', '', '', '', '']
        simple_particles = ['', '', '', '', '', '', '', '',
                          '', '', '', '', '', '', '', '', '', '', '',
                          '', '', '', '', '', '', '']

        #      
        words = normalized.split()
        cleaned_words = []

        for word in words:
            cleaned_word = word

            #    
            for particle in compound_particles:
                if cleaned_word.endswith(particle):
                    cleaned_word = cleaned_word[:-len(particle)]
                    break

            #   
            if cleaned_word:  #   
                for particle in simple_particles:
                    if cleaned_word.endswith(particle):
                        cleaned_word = cleaned_word[:-len(particle)]
                        break

            # 2  
            if cleaned_word and len(cleaned_word) >= 2:
                cleaned_words.append(cleaned_word)

        # 3.   (   )
        cleaned_words.sort()

        # 4.   
        cache_str = f"{mode}:{'_'.join(cleaned_words)}"
        hash_key = hashlib.md5(cache_str.encode('utf-8')).hexdigest()

        #  ( )
        # print(f"Cache: '{query}'  '{' '.join(cleaned_words)}'  {hash_key[:8]}...")

        return hash_key

    def answer_with_logging(self, query: str, mode: str = 'auto') -> str:
        """  answer  ( )"""
        #    
        cache_key = self._get_enhanced_cache_key(query, mode)
        
        #  
        if cache_key in self.answer_cache:
            cached_response, cached_time = self.answer_cache[cache_key]
            # TTL  ( 1)
            if time.time() - cached_time < self.cache_ttl:
                print(f"  ! (: {cache_key[:8]}...)")
                # LRU  (  )
                self.answer_cache.move_to_end(cache_key)
                return cached_response
            else:
                #   
                del self.answer_cache[cache_key]
        
        #    (_answer_internal   )
        start_time = time.time()
        response = self._answer_internal(query, mode)
        generation_time = time.time() - start_time
        
        #  
        self.answer_cache[cache_key] = (response, time.time())
        print(f"  : {generation_time:.1f} ( )")
        
        #    (LRU )
        if len(self.answer_cache) > self.max_cache_size:
            #    
            self.answer_cache.popitem(last=False)
        
        return response
    
    def answer(self, query: str, mode: str = 'auto') -> str:
        """   """
        return self.answer_with_logging(query, mode)
    
    def clear_cache(self):
        """ """
        self.answer_cache.clear()
        self.documents_cache.clear()
        self.metadata_cache.clear()
        print("   .")
    
    def get_cache_stats(self) -> Dict:
        """   """
        response_cache_size = len(self.response_cache) if hasattr(self, 'response_cache') else 0
        total_size = len(self.answer_cache) + len(self.documents_cache) + len(self.metadata_cache) + response_cache_size
        return {
            'size': response_cache_size,  # For compatibility with test
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'answer_cache_size': len(self.answer_cache),
            'document_cache_size': len(self.documents_cache),
            'metadata_cache_size': len(self.metadata_cache),
            'response_cache_size': response_cache_size,
            'total_cache_size': total_size,
            'max_cache_size': self.max_cache_size,
            'cache_ttl_seconds': self.cache_ttl
        }
    
    def _answer_internal(self, query: str, mode: str = 'auto') -> str:
        """"
        
        Args:
            query:  
                - document: PDF  
                - auto:  
        """"
        
        #   
        start_time = time.time()
        error_msg = None
        success = True
        response = ""
        metadata = {}
        
        try:
            #   
            if logger:
                logger.system_logger.info(f"=== Query Start: {query[:100]}...")
            
            #   
            if mode == 'auto':
                with TimerContext(logger, "classify_intent") if logger else nullcontext():
                    mode = self._classify_search_intent(query)
                print(f"  : {mode}")
            
            self.search_mode = mode
            metadata['search_mode'] = mode
            
            #   
            query_lower = query.lower()
            
                    #    
                    if not doc_path:
                        for cache_key, file_meta in self.metadata_cache.items():
                            if file_meta.get('is_txt', False):
                                filename = file_meta.get('filename', cache_key)
                                path_obj = Path(file_meta['path']) if isinstance(file_meta['path'], str) else file_meta['path']
                                if path_obj.exists():
                                    doc_path = path_obj
                                    break
                
                if doc_path:
                    #    
                    
                    #    
                    if query_intent.get('has_multiple_conditions'):
                    # /  -  
                    elif query_intent.get('search_type') == 'manager':
                    # /  
                    elif query_intent.get('search_type') == 'price':
                    #   -   
                    elif query_intent.get('search_type') == 'year':
                    #  
                    elif query_intent.get('search_type') == 'manufacturer':
                    #  
                    elif query_intent.get('search_type') == 'model':
                    elif query_intent.get('search_type') == 'location':
                        response = self._search_location_unified(doc_path, query)
                    # +  
                    elif query_intent.get('search_type') == 'location_equipment':
                        response = self._search_location_equipment_combo(doc_path, query)
                    #   
                    elif query_intent.get('search_type') == 'equipment':
                    # ""       - / 
                    elif '' in query_lower:
                        #      
                        if re.search(self._get_manufacturer_pattern(), query):
                        else:
                    # /  
                    elif "" in query_lower or "" in query_lower:
                        #    
                        equipment_keywords = ["CCU", "", "", "", "", "", "", ""]
                        found_equipment = None
                        for eq in equipment_keywords:
                            if eq.upper() in query.upper():
                                found_equipment = eq
                                break
                        
                        if found_equipment:
                            response = self._search_equipment_all_locations(doc_path, found_equipment)
                        else:
                    else:
                else:
            
            # document        
        except Exception as e:
            #  
            error_msg = str(e)
            success = False
            response = f"    : {error_msg}"
            
            #   
            processing_time = time.time() - start_time
            
            #  
            if logger:
                logger.log_error(
                    error_type=type(e).__name__,
                    error_msg=error_msg,
                    query=query
                )
            
            return response
    
    def _get_detail_only_prompt(self, query: str, context: str, filename: str) -> str:
        """      """
        return """"
    . 
 , ,        .

 **/   **
   
#  ** ** ( )
   
#  ** ** ( )
  
: {filename}
: {context[:5000]}

: {query}

  .
""""

    def _get_optimized_prompt(self, query: str, context: str, filename: str) -> str:
        """   """
        
        #   
        if any(word in query for word in ["", "", "", "", ""]):
            return """"
[  ]    

:   
: {filename}

   :
  :
  :
   :
  :

 :
{context}

: {query}

 30   
   " " 
""""
        
        # / /
        elif any(word in query for word in ["", "", "", "", "", "", "", "", "", ""]):
            #      
            has_basic_info = 'basic_summary' in locals() if 'locals' in dir() else False
            
            if has_basic_info:
                #       
                return """"
[  ] {filename}

  (,  )  .   :

 / : [ ,   ]
  : [ ]  
  : [ ]

 **  ** ()
   : [  ]
  : [, ]
  : [ ]
  : [ ]

 : [] ( /)
  :
  - [1]: [] - [] x [] = []
  - [2]: [] - [] x [] = []
 : []

 [ 1]
 [ 2]
 : [ /]

 : {filename}

 :
{context}

: {query}

 :
-     
-  /   
-     (: 820,000)
- ,     
""""
        
        # / 
        elif any(word in query for word in ["", "", "", ""]):
            return """"
[  ]   

: {filename}
: {query}

  :
  :
  :
  :
  :
  :
  - 1:
  - 2:
  - :
  :

 :
{context}

""""
        
        #   ( )
        else:
            return """"
[  ]

 **  ( )**:

 {filename.replace('.pdf', '')}

 : [  ]
 : [ ]
  : [// ]

[     ]
 [  1]
 [  2]
 [ ...]

#  ** ** (    )
 : []
  :
  - [1]: []
  - [2]: []

#  ** ** (   )
 [ 1]
 [ 2]
 : [ ]

 : {filename}

 :
{context}

: {query}

 :
-     
-      
-       
-  (, , )  
-     (: 1,234,000)
-      
""""
    
    def _is_gian_document(self, text: str) -> bool:
        """  """
        gian_keywords = ['/ ', '', '', '', '', '']
        matches = sum(1 for keyword in gian_keywords if keyword in text[:500])
        return matches >= 3
    
    def _try_ocr_extraction(self, pdf_path: Path) -> str:
        """OCR    """
        try:
            # OCR  
            from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
            
            ocr_processor = EnhancedOCRProcessor()
            text, metadata = ocr_processor.extract_text_with_ocr(str(pdf_path))
            
            if metadata.get('ocr_performed'):
                if logger:
                    logger.system_logger.info(f"OCR : {pdf_path.name} - {metadata.get('ocr_text_length', 0)} ")
                return text
            else:
                if logger:
                    logger.system_logger.warning(f"OCR : {pdf_path.name}")
                return ""
                
        except ImportError:
            if logger:
                logger.system_logger.warning("OCR    - pytesseract  Tesseract ")
            return ""
        except Exception as e:
            if logger:
                logger.system_logger.error(f"OCR   : {pdf_path.name} - {e}")
            return ""
    
    def _extract_full_pdf_content(self, pdf_path: Path) -> dict:
        """PDF     """
        try:
            import PyPDF2
            
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                
                #    ( )
                full_text = ""
                max_pages = min(len(reader.pages), 50)  #  50 
                for page_num in range(max_pages):
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    
                    #  URL 
                    page_text = re.sub(r'gw\.channela[^\n]+', '', page_text)
                    page_text = re.sub(r'\d+\.\s*\d+\.\s*\d+\.\s*[]\s*\d+:\d+\s*.*?', '', page_text)
                    
                    full_text += f"\n[ {page_num+1}]\n{page_text}\n"
                    
                    #    
                    if len(full_text) > 100000:  # 100K  
                        break
                
                #   OCR 
                if not full_text.strip():
                    logger.info(f"  , OCR : {pdf_path.name}")
                    full_text = self._try_ocr_extraction(pdf_path)
                    if not full_text:
                        return None
                
                #   
                info = {}
                
                #   
                is_gian = self._is_gian_document(full_text)
                
                if is_gian:
                    #   
                    patterns = {
                        '': r'\s+([-]+)',
                        '': r'\s+(.+?)(?:\n|$)',
                        '': r'\s+(\d{4}-\d{2}-\d{2})',
                        '': r'\s+([^\s]+)',
                        '': r'\s+([^\s\n]+)',
                        '': r'\s+(\d{4}-\d{2}-\d{2})',
                        '': r'\s+([^\s]+)',
                    }
                else:
                    #   
                    patterns = {
                        '': r'\s+([^\s\n]+)',
                        '': r'\s+(.+?)(?:\n|$)',
                        '': r'\s+(\d{4}-\d{2}-\d{2})',
                        '': r'\s+([^\s\n]+)',
                        '': r'\s+([^\s\n]+)'
                    }
                
                for key, pattern in patterns.items():
                    match = re.search(pattern, full_text)
                    if match:
                        info[key] = match.group(1).strip()
                
                #   (  )
                if is_gian:
                    #  1.  
                    match = re.search(r'1\.\s*\s*\n(.+?)(?:\n2\.|$)', full_text, re.DOTALL)
                    if match:
                        overview = match.group(1).strip()
                        #   
                        overview = re.sub(r'\n(?![-])', ' ', overview)
                        info[''] = overview[:800]  # 800 
                    
                    # 2.  
                    match = re.search(r'2\.\s*\s*\n(.+?)(?:\n3\.|$)', full_text, re.DOTALL)
                    if match:
                        content = match.group(1).strip()
                        content = re.sub(r'\n(?![-\d\)])', ' ', content)
                        info[''] = content[:1000]  # 1000 
                    
                    # 3.   
                    match = re.search(r'3\.\s*\s*\s*\n(.+?)(?:\n4\.|$)', full_text, re.DOTALL)
                    if match:
                        review = match.group(1).strip()
                        review = re.sub(r'\n(?![-])', ' ', review)
                        info[''] = review[:2500]  # 800 -> 2500
                else:
                    #    
                    if '' in full_text:
                        match = re.search(r'\s*\n(.+?)(?:\n\d+\.|$)', full_text, re.DOTALL)
                        if match:
                            info[''] = match.group(1).strip()
                
                #   (  -     )
                #      
                amount_patterns = [
                    # ,     (  )
                    r'(?:||\s*|\s*|\s*|\s*)[:\s]*(\d{1,3}(?:,\d{3})*)\s*(?:)?',
                    r'(?:||)[:\s]*(\d{1,3}(?:,\d{3})*)\s*(?:)?',
                    # VAT  
                    r'(\d{1,3}(?:,\d{3})*)\s*\s*\(?(?:VAT|)',
                    r'(\d{1,3}(?:,\d{3})*)\s*\(?(?:VAT|)',  #  
                    #   
                    r'\s*\s*(\d{1,3}(?:,\d{3})*)\s*',
                    # ,   
                    r'(\d{1,3}(?:,\d{3})*)\s*(?:||)\s*',
                    #    ( )
                    r'(\d{1,3}(?:,\d{3})*)\s*',
                ]
                
                amounts = []
                amount_contexts = []  #    
                
                for pattern in amount_patterns:
                    matches = re.finditer(pattern, full_text, re.IGNORECASE)
                    for match in matches:
                        amount = match.group(1)
                        #   (  )
                        start = max(0, match.start() - 50)
                        end = min(len(full_text), match.end() + 50)
                        context = full_text[start:end].strip()
                        
                        #    (10 )
                        try:
                            amount_int = int(amount.replace(',', ''))
                            if amount_int >= 100000:  # 10 
                                amounts.append(amount)
                                amount_contexts.append({
                                    'amount': amount,
                                    'context': context
                                })
                        except Exception as e:
                            pass
                
                #      
                if amounts:
                    #    
                    sorted_amounts = sorted(amounts, 
                                          key=lambda x: int(x.replace(',', '')), 
                                          reverse=True)
                    #  3 
                    info[''] = sorted_amounts[:3]
                    info[''] = amount_contexts[:3]
                
                #  
                if '' in full_text or '' in full_text:
                    vendor_match = re.search(r'(?:|)[:\s]*([^\n]+)', full_text)
                    if vendor_match:
                        info[''] = vendor_match.group(1).strip()
                
                #    ( )
                if ' ' in full_text:
                    match = re.search(r' (.+?)(?:3\.|$)', full_text, re.DOTALL)
                    if match:
                        opinion = match.group(1).strip()
                        opinion = re.sub(r'\n+', ' ', opinion)
                        opinion = re.sub(r'\s+', ' ', opinion)
                        info[''] = opinion[:2500]  # 500 -> 2500 
                
                #    (    )
                info[''] = []
                
                #    
                if '' in full_text and '' in full_text:
                    # , ,    
                    repair_items = []
                    if '' in full_text:
                        repair_items.append({'': '', '': '   '})
                    if '' in full_text:
                        repair_items.append({'': '', '': '   '})
                    if '' in full_text:
                        repair_items.append({'': '', '': ' '})
                    if '' in full_text:
                        repair_items.append({'': '', '': ' '})
                    if repair_items:
                        info[''] = repair_items
                
                #  Control Box   
                elif 'Control Box' in full_text or '' in full_text:
                    repair_items = []
                    if 'Tilt ' in full_text:
                        repair_items.append({'': 'Tilt ', '': ' '})
                    if repair_items:
                        info[''] = repair_items
                    
                    #   
                    if ' ' in full_text:
                        match = re.search(r' (.+?)(?:\d+\)|$)', full_text, re.DOTALL)
                        if match:
                            info[''] = match.group(1).strip()[:300]
                
                #    ( - DVR )
                info[''] = {}
                
                # DVR   
                if 'DVR' in full_text or '2,446,000' in full_text:
                    # DVR   
                    cost_match = re.search(r' .*?\s*([\d,]+)', full_text, re.DOTALL)
                    if cost_match:
                        info[''][''] = cost_match.group(1) + ''
                    
                    #   
                    if '666,000' in full_text:
                        info['']['DVR'] = '666,000 (2EA)'
                    if '1,520,000' in full_text:
                        info['']['HDD'] = '1,520,000 (10TB x 4EA)'
                    if '260,000' in full_text:
                        info[''][''] = '260,000 (2EA)'
                    if '2,446,000' in full_text:
                        info[''][''] = '2,446,000'
                
                #   
                for amt in info.get('', []):
                    try:
                        amt_int = int(amt.replace(',', ''))
                        if amt_int >= 100000:  # 10  
                            if '26,660,000' in amt:
                                info[''][''] = amt + ''
                            elif '7,680,000' in amt:
                                info[''][''] = amt + ''
                            elif '34,340,000' in amt:
                                info[''][''] = amt + ' (VAT)'
                            elif '200,000' in amt:
                                info[''][''] = amt + ' (VAT)'
                            elif not info['']:  #   
                                info[''][''] = amt + ''
                    except (ValueError, AttributeError):
                        pass  #    
                
                info[''] = full_text[:8000]  # LLM  
                
                return info
                
        except Exception as e:
            return {'error': str(e)}
    
    def _prepare_formatted_data(self, pdf_info: Dict, pdf_path: Path) -> Dict:
        """   """
        formatted_info = {
            '': pdf_info.get('', pdf_path.stem),
            '': pdf_info.get('', ''),
            '': pdf_info.get('', ''),
            '': pdf_info.get('', '')
        }
        
        #    (3)
        if self.formatter and pdf_info.get(''):
            key_points = self.formatter.extract_key_points(pdf_info[''])
            formatted_info[''] = key_points
        
        #   
        detail_content = []
        
        #   
        if pdf_info.get(''):
            detail_content.append({
                '': '',
                '': pdf_info[''][:200]
            })
        
        # / 
        if any(k in pdf_info for k in ['', '', '']):
            for key in ['', '', '']:
                if pdf_info.get(key):
                    detail_content.append({
                        '': key,
                        '': pdf_info[key][:200]
                    })
        
        formatted_info[''] = detail_content
        
        #  
        if pdf_info.get(''):
            formatted_info[''] = pdf_info['']
        
        #  
        opinions = []
        if pdf_info.get(''):
            opinions.append(pdf_info[''])
        if pdf_info.get(''):
            opinions.append(pdf_info[''])
        if opinions:
            formatted_info[''] = opinions
        
        #  
        related = []
        if pdf_info.get(''):
            related.append(f": {pdf_info['']}")
        if pdf_info.get(''):
            related.append(f": {pdf_info['']}")
        if related:
            formatted_info[''] = related
        
        return formatted_info
    
    def _analyze_user_intent(self, query: str) -> Dict[str, Any]:
        """    """
        query_lower = query.lower()
        
        intent = {
            'type': 'general',
            'needs_detail': False,
            'wants_comparison': False,
            'wants_recommendation': False,
            'is_urgent': False,
            'tone': 'informative',
            'context_keywords': [],
            'response_style': 'conversational'
        }
        
        #  
        if any(word in query_lower for word in ['', '', '', '']):
            intent['type'] = 'summary'
            intent['needs_detail'] = True
        elif any(word in query_lower for word in ['', '', ' ', ' ']):
            intent['type'] = 'comparison'
            intent['wants_comparison'] = True
            intent['wants_recommendation'] = True
        elif any(word in query_lower for word in ['', '', '', '']):
            intent['type'] = 'recommendation'
            intent['wants_recommendation'] = True
        elif any(word in query_lower for word in ['', '', '', '']):
            intent['type'] = 'urgent'
            intent['is_urgent'] = True
            intent['tone'] = 'direct'
        elif any(word in query_lower for word in ['', '', '', '']):
            intent['type'] = 'cost'
            intent['needs_detail'] = True
        elif any(word in query_lower for word in ['', '', '', '']):
            intent['type'] = 'problem'
            intent['wants_recommendation'] = True
        
        #   
        important_words = ['DVR', '', '', '', '', '', '', '', '', '']
        intent['context_keywords'] = [word for word in important_words if word.lower() in query_lower]
        
        #   
        if '?' in query:
            intent['response_style'] = 'explanatory'
        elif any(word in query_lower for word in ['', '', '']):
            intent['response_style'] = 'helpful'
        
        return intent
    
    def _generate_conversational_response(self, context: str, query: str, intent: Dict[str, Any], 
                                         pdf_info: Dict[str, Any] = None) -> str:
        """    (ChatGPT/Claude )"""
        
        # LLM     
        system_prompt = """   AI ."
        .

 :
1.   
2.     
3.      
4.        
5.     """"
        
        #    
        if intent['type'] == 'summary':
            user_prompt = """      ."

 :
{context}

 : {query}

 :
-     
-     
-      
-       """"
        
        elif intent['type'] == 'comparison':
            user_prompt = """     ."

:
{context}

 : {query}

 :
-      
-     
-    
- "  A ,   B "  """"
        
        elif intent['type'] == 'recommendation':
            user_prompt = """     ."

:
{context}

 : {query}

 :
-    
-    
-    
-    """"
        
        elif intent['type'] == 'cost':
            user_prompt = """      ."

:
{context}

 : {query}

 :
-    
-    
-     
-     """"
        
        elif intent['is_urgent']:
            user_prompt = """      ."

:
{context}

 : {query}

 :
-    
-     
-     """"
        
        else:
            user_prompt = """       ."

:
{context}

 : {query}

 :
-    
-    
-     
-    """"
        
        # LLM 
        if self.llm:
            try:
                #   
                context_chunks = [{
                    'content': context,
                    'source': pdf_info.get('', 'document') if pdf_info else 'document',
                    'score': 1.0
                }]
                
                #    
                response = self.llm.generate_conversational_response(query, context_chunks)
                
                if response and hasattr(response, 'answer'):
                    answer = response.answer
                else:
                    answer = str(response)
                
                #      
                if intent['wants_recommendation'] and '' not in answer:
                    answer += "\n\n,       .   ."
                
                return answer
                
            except Exception as e:
                print(f"LLM   : {e}")
                # :   
                return self._generate_fallback_response(context, query, intent)
        
        return self._generate_fallback_response(context, query, intent)
    
    def _generate_fallback_response(self, context: str, query: str, intent: Dict[str, Any]) -> str:
        """LLM     """
        
        #    
        lines = context.split('\n')
        key_info = []
        
        for line in lines:
            if any(keyword in line for keyword in ['', '', '', '', '', '']):
                key_info.append(line.strip())
        
        response = "  , "
        
        if intent['type'] == 'summary':
            response += "   . "
            if key_info:
                response += ' '.join(key_info[:3])
        elif intent['type'] == 'cost':
            cost_info = [line for line in key_info if '' in line or '' in line]
            if cost_info:
                response += f"  . {cost_info[0]}"
        else:
            if key_info:
                response += f"  . {key_info[0]}"
        
        return response
    
    def _generate_llm_summary(self, pdf_path: Path, query: str) -> str:
        """LLM    -  """
        
        #   
        intent = self._analyze_user_intent(query)
        
        # PDF       
        if pdf_path.suffix.lower() == '.pd':
            pdf_info = self._extract_full_pdf_content(pdf_path)
            
            #      
            context_parts = []
            summary = []
            
            #     
            if pdf_info and 'error' not in pdf_info:
                #   -  
                if '' in pdf_info:
                    context_parts.append(f": {pdf_info['']}")
                if '' in pdf_info:
                    context_parts.append(f": {pdf_info['']}")
                if '' in pdf_info:
                    context_parts.append(f": {pdf_info['']}")
                if '' in pdf_info:
                    context_parts.append(f": {pdf_info['']}")
                
                # 
                if '' in pdf_info:
                    overview = pdf_info[''].replace('\n', ' ').strip()
                    if len(overview) > 300:
                        overview = overview[:300] + "..."
                    context_parts.append(f"\n: {overview}")
                
                #  
                if '' in pdf_info and pdf_info['']:
                    _text = pdf_info[''].replace('\n', ' ').strip()
                    if len(_text) > 300:
                        _text = _text[:300] + "..."
                    context_parts.append(f"\n : {_text}")
                
                #   ( )
                if '' in pdf_info and pdf_info['']:
                    summary.append("\n ** / **")
                    
                    #  
                    _items = [item for item in pdf_info[''] if '' in item.get('', '') or '' in item.get('', '')]
                    if _items:
                        summary.append("\n**[ ]**")
                        for item in _items:
                            summary.append(f" {item['']}: {item['']}")
                    
                    #  
                    _items = [item for item in pdf_info[''] if '' in item.get('', '') or '' in item.get('', '')]
                    if _items:
                        summary.append("\n**[ ]**")
                        for item in _items:
                            summary.append(f" {item['']}: {item['']}")
                    
                    #    
                    _items = [item for item in pdf_info[''] if 'Tilt' in item.get('', '') or 'Control' in item.get('', '')]
                    if _items:
                        for item in _items:
                            summary.append(f" {item['']}: {item['']}")
                
                #   ()
                if '' in pdf_info and pdf_info['']:
#                     summary.append("\n ** **")
                    if '' in pdf_info['']:
                        summary.append(f"   : {pdf_info['']['']}")
                    if '' in pdf_info['']:
                        summary.append(f"   : {pdf_info['']['']}")
                    if '' in pdf_info['']:
                        summary.append(f" ** : {pdf_info['']['']}**")
                #   (  )
                elif '' in pdf_info and pdf_info['']:
#                     summary.append("\n ** **")
                    #     
                    amounts = []
                    for amt in pdf_info['']:
                        try:
                            amt_int = int(amt.replace(',', ''))
                            if amt_int > 1000000:  # 100 
                                amounts.append((amt, amt_int))
                        except (ValueError, AttributeError):
                            pass  #    
                    amounts.sort(key=lambda x: x[1], reverse=True)
                    for amt, _ in amounts[:3]:
                        summary.append(f" {amt}")
                
                #   ( )
                if '' in pdf_info and pdf_info['']:
#                     summary.append("\n ** **")
                    opinion = pdf_info['']
                    
                    # DVR   
                    if 'DVR' in opinion or ('1' in opinion and '2' in opinion):
                        # 1   
                        if '1' in opinion:
                            1_text = re.search(r'1[^2]*(?=2|$)', opinion, re.DOTALL)
                            if 1_text:
                                1_clean = re.sub(r'[\d]+\.\s*[\d]+\.\s*[\d]+.*?(?=\n)', '', 1_text.group(0))
                                1_clean = re.sub(r'\[ \d+\]', '', 1_clean)
                                1_clean = ' '.join(1_clean.split())
                                # HD-SDI   1    
                                if 'HD-SDI' in 1_clean or 'HD' in 1_clean or ' ' in 1_clean or '1' in 1_clean:
                                    summary.append("\n** 1: HD-SDI  **")
                                    summary.append("     ")
                                    summary.append(" HD ,   ")
                                    summary.append("    ( )")
                        
                        # 2   
                        if '2' in opinion:
                            2_text = re.search(r'2[^]*(?=|$)', opinion, re.DOTALL)
                            if 2_text:
                                2_clean = re.sub(r'[\d]+\.\s*[\d]+\.\s*[\d]+.*?(?=\n)', '', 2_text.group(0))
                                2_clean = re.sub(r'\[ \d+\]', '', 2_clean)
                                if 'CVBS' in 2_clean or '' in 2_clean:
                                    summary.append("\n** 2:   **")
                                    summary.append("    ")
                                    summary.append("  ,  ")
                                    summary.append(" SD    ")
                        
                        #  
                        if '' in opinion or '' in opinion:
                            summary.append("\n**  **")
                            if '1' in opinion and ('' in opinion or '' in opinion or '' in opinion):
                                summary.append(" **1  ** -      ")
                            elif '2' in opinion and ('' in opinion or '' in opinion):
                                summary.append(" **2  ** -   ")
                    
                    #   
                    elif ' ' in opinion:
                        summary.append("  :      ")
                        if ' ' in opinion:
                            summary.append("  : 25-30  , 4K   ")
                        if '' in opinion:
                            summary.append(" **:       **")
                    else:
                        #    ( )
                        if len(opinion) > 500:
                            opinion = opinion[:500] + "..."
                        summary.append(opinion)
                
                #   (  ) -   
                if '' in pdf_info:
                    full_text = pdf_info['']
                    
                    #   
                    if '' in query or '' in query:
                        _match = re.search(r'\s*\s*[:]?\s*(\d{4})', full_text)
                        if _match:
#                             summary.append(f"\n ** **: {_match.group(1)}")
                
                #  
                if '' in pdf_info:
#                     summary.append(f"\n ** **: {pdf_info['']}")
            
            #    (if   )
            basic_summary = '\n'.join(summary) if summary else ""
            
            #      
            if '' in query or '' in query or '' in query:
                #  
                context_text = ""
                if pdf_info and 'error' not in pdf_info:
                    #    
                    context_parts = []
                    if '' in pdf_info:
                        context_parts.append(f" : {pdf_info['']}")
                    if '' in pdf_info:
                        context_parts.append(f": {pdf_info['']}")
                    if '' in pdf_info:
                        context_parts.append(f": {pdf_info['']}")
                    if '' in pdf_info:
                        context_parts.append(f"\n: {pdf_info['']}")
                    if '' in pdf_info:
                        amounts = pdf_info['']
                        if amounts:
                            #      
                            main_amount = amounts[0] if amounts else None
                            if main_amount:
                                #     
                                if '' in pdf_info and pdf_info['']:
                                    context_info = pdf_info[''][0].get('context', '')
                                    # ,     
                                    if '' in context_info or '' in context_info:
                                        context_parts.append(f"\n : {main_amount}")
                                    else:
                                        context_parts.append(f"\n: {main_amount}")
                                else:
                                    context_parts.append(f"\n: {main_amount}")
                    if '' in pdf_info:
                        context_parts.append(f"\n : {pdf_info[''][:500]}")
                    
                    context_text = "\n".join(context_parts)
                
                # LLM 
                if self.llm is None:
                    if not LLMSingleton.is_loaded():
                        print(" LLM   ...")
                    self.llm = LLMSingleton.get_instance(model_path=self.model_path)
                
                #    -   
                if self.llm and context_text:
                    #    (   )
                    if '' in pdf_info and pdf_info['']:
                        full_context = f"{context_text}\n\n[  ]\n{pdf_info[''][:3000]}"
                    else:
                        full_context = context_text
                    
                    context_chunks = [{
                        'content': full_context,
                        'source': pdf_path.name,
                        'score': 1.0
                    }]
                    
                    response = self.llm.generate_conversational_response(query, context_chunks)
                    
                    if response and hasattr(response, 'answer'):
                        answer = response.answer
                    else:
                        answer = str(response)
                    
                    #   
                    if pdf_path.name not in answer:
                        answer += f"\n\n(: {pdf_path.name})"
                    
                    return answer
            
            #      
        
        # LLM  () -  
        if self.llm is None:
            if not LLMSingleton.is_loaded():
                print(" LLM   ...")
            self.llm = LLMSingleton.get_instance(model_path=self.model_path)
        
        #     
        try:
            text = ""
            
            # TXT  
            if pdf_path.suffix.lower() == '.txt':
                with open(pdf_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            # PDF  
            else:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                
                # pdfplumber  OCR 
                if not text:
                    try:
                        from rag_system.enhanced_ocr_processor import EnhancedOCRProcessor
                        ocr = EnhancedOCRProcessor()
                        text, _ = ocr.extract_text_with_ocr(str(pdf_path))
                    except Exception as e:
                        pass
            
            if not text:
                return "     "
            
            #   
            #    
            #     (5000 -> 15000)
            max_text_length = 15000  # 15,000 
            
            #       
            if 'basic_summary' in locals():
                #     
                prompt = self._get_detail_only_prompt(query, text[:max_text_length], pdf_path.name)
            else:
                prompt = self._get_optimized_prompt(query, text[:max_text_length], pdf_path.name)
            
            # LLM  -   
            context_chunks = [{'content': text[:max_text_length], 'metadata': {'source': pdf_path.name}, 'score': 1.0}]
            
            # /    
            if '' in query or '' in query or '' in query:
                response = self.llm.generate_conversational_response(query, context_chunks)
            else:
                #  
                response = self.llm.generate_response(prompt, context_chunks)
            
            answer = response.answer if hasattr(response, 'answer') else str(response)
            
            #      
            if '' in query or '' in query or '' in query:
                #      
                if pdf_path.name not in answer:
                    answer += f"\n\n( : {pdf_path.name})"
                return answer
            else:
                #   ( )
                if 'basic_summary' in locals() and basic_summary:
#                     combined_answer = f"{basic_summary}\n\n ** **\n{answer}"
                    return f"{combined_answer}\n\n : {pdf_path.name}"
                else:
                    return f"{answer}\n\n : {pdf_path.name}"
            
        except Exception as e:
            return f"   : {e}"
    
    def _collect_statistics_data(self, query: str) -> Dict:
        """    """
        stats_data = {
            'title': '',
            'headers': [],
            'table_data': [],
            '': '',
            '': {},
            '': []
        }
        
        #  
        year_match = re.search(r'(20\d{2})', query)
        target_year = year_match.group(1) if year_match else None
        
        if "" in query and "" in query:
            stats_data['title'] = "  "
            stats_data['headers'] = ['', '', ' ', ' ']
            
            yearly_data = {}
            for filename, metadata in self.metadata_cache.items():
                if '' in filename or '' in filename:
                    year = metadata['year']
                    if year not in yearly_data:
                        yearly_data[year] = {'count': 0, 'total': 0, 'items': []}
                    
                    yearly_data[year]['count'] += 1
                    #   
                    pdf_path = self.docs_dir / filename
                    info = self._extract_pdf_info(pdf_path)
                    if info.get(''):
                        amount = self._parse_amount(info[''])
                        yearly_data[year]['total'] += amount
                    if info.get(''):
                        yearly_data[year]['items'].append(info[''])
            
            #   
            total_amount = 0
            for year in sorted(yearly_data.keys()):
                data = yearly_data[year]
                total_amount += data['total']
                items_str = ', '.join(data['items'][:2])  #  2
                if len(data['items']) > 2:
                    items_str += f"  {len(data['items'])-2}"
                
                stats_data['table_data'].append([
                    year,
                    f"{data['count']}",
                    f"{data['total']:,}",
                    items_str
                ])
            
            stats_data[''] = f"{total_amount:,}"
            stats_data['']['  '] = f"{total_amount // len(yearly_data):,}"
            stats_data[''].append("      ")
            
        elif target_year:
            #    
            stats_data['title'] = f"{target_year}  "
            stats_data['headers'] = ['', '', ' ', '']
            
            categories = {'': 0, '': 0, '': 0, '': 0}
            amounts = {'': 0, '': 0, '': 0, '': 0}
            
            for filename, metadata in self.metadata_cache.items():
                if metadata['year'] == target_year:
                    #  
                    if '' in filename or '' in filename:
                        cat = ''
                    elif '' in filename or '' in filename:
                        cat = ''
                    elif '' in filename:
                        cat = ''
                    else:
                        cat = ''
                    
                    categories[cat] += 1
                    
                    #  
                    pdf_path = self.docs_dir / filename
                    info = self._extract_pdf_info(pdf_path)
                    if info.get(''):
                        amounts[cat] += self._parse_amount(info[''])
            
            #  
            total_docs = sum(categories.values())
            total_amount = sum(amounts.values())
            
            #   
            for cat in ['', '', '', '']:
                if categories[cat] > 0:
                    ratio = (categories[cat] / total_docs * 100) if total_docs > 0 else 0
                    stats_data['table_data'].append([
                        cat,
                        f"{categories[cat]}",
                        f"{amounts[cat]:,}",
                        f"{ratio:.1f}%"
                    ])
            
            stats_data[''] = f" {total_docs},  {total_amount:,}"
            stats_data[''][' '] = f"{amounts['']/total_amount*100:.1f}%" if total_amount > 0 else "0%"
            stats_data[''][' '] = f"{amounts['']/total_amount*100:.1f}%" if total_amount > 0 else "0%"
        
        return stats_data
    
    def _generate_statistics_report(self, query: str) -> str:
        """      -  """
        try:
            # formatter      
            if self.formatter:
                stats_data = self._collect_statistics_data(query)
                return self.formatter.format_statistics_response(stats_data, query)
            
            #   (formatter  )
            #   
            if "" in query and "" in query:
                return self._generate_yearly_purchase_report(query)
            elif "" in query:
                return self._generate_drafter_report(query)
            elif "" in query and "" in query:
                return self._generate_monthly_repair_report(query)
            
            # :    
            year_match = re.search(r'(20\d{2})', query)
            target_year = year_match.group(1) if year_match else None
            
            #   
            stats = {
                '': [],
                '': [],
                '': [],
                '': [],
                '': []
            }
            
            drafters = {}  #  
            monthly = {}  #  
            total_amount = 0
            doc_count = 0
            
            for filename, metadata in self.metadata_cache.items():
                #  
                if target_year and metadata['year'] != target_year:
                    continue
                
                doc_count += 1
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                #  
                category = ''
                if '' in filename:
                    category = ''
                elif '' in filename or '' in filename:
                    category = ''
                elif '' in filename:
                    category = ''
                elif '' in filename:
                    category = ''
                
                #  
                doc_info = {
                    'filename': filename,
                    'date': info.get('', ''),
                    'drafter': info.get('', ''),
                    'amount': info.get('', ''),
                    'title': info.get('', filename.replace('.pd', ''))
                }
                
                stats[category].append(doc_info)
                
                #  
                drafter = doc_info['drafter']
                if drafter not in drafters:
                    drafters[drafter] = 0
                drafters[drafter] += 1
                
                #   (  )
                if doc_info['date']:
                    month_match = re.search(r'-(\d{2})-', doc_info['date'])
                    if month_match:
                        month = month_match.group(1)
                        if month not in monthly:
                            monthly[month] = 0
                        monthly[month] += 1
                
                #  
                if doc_info['amount']:
                    amount_num = re.search(r'(\d+(?:,\d+)*)', doc_info['amount'])
                    if amount_num:
                        try:
                            total_amount += int(amount_num.group(1).replace(',', ''))
                        except (ValueError, AttributeError):
                            pass  #    
            
            #  
            report = []
            
            if target_year:
                report.append(f" {target_year}    ")
            else:
                report.append("      ")
            
            report.append("=" * 50)
            report.append("")
            
            #  
            report.append("###   ")
            report.append(f"   : {doc_count}")
            if total_amount > 0:
                report.append(f"  : {total_amount:,}")
            report.append("")
            
            #  
            report.append("###   ")
            report.append("")
            
            for category, docs in stats.items():
                if docs:
                    count = len(docs)
                    ratio = (count / doc_count * 100) if doc_count > 0 else 0
                    report.append(f" **{category}**: {count} ({ratio:.1f}%)")
            report.append("")
            
            #  
            if drafters:
                report.append("###   ")
                report.append("")
                
                for drafter, count in sorted(drafters.items(), key=lambda x: x[1], reverse=True):
                    if drafter and drafter != '':
                        report.append(f" **{drafter}**: {count}")
                
                report.append("")
            
            #   ( )
            if target_year and monthly:
                report.append("###   ")
                report.append("")
                
                for month in sorted(monthly.keys()):
                    count = monthly[month]
                    report.append(f" **{int(month)}**: {count}")
                
                report.append("")
            
            #   
            report.append("###    ")
            for category, docs in stats.items():
                if docs:
                    report.append(f"\n {category} ({len(docs)})")
                    for doc in docs[:3]:  #    3
                        date = doc['date'][:10] if doc['date'] else ''
                        drafter = doc['drafter'] if doc['drafter'] != '' else ''
                        amount = f" - {doc['amount']}" if doc['amount'] else ""
                        
                        title = doc['title'][:30] + "..." if len(doc['title']) > 30 else doc['title']
                        report.append(f"   [{date}] {title}")
                        if drafter or amount:
                            report.append(f"    {drafter}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"    : {e}"
    
    def _generate_yearly_purchase_report(self, query: str) -> str:
        """   """
        try:
            yearly_stats = {}
            
            for filename, metadata in self.metadata_cache.items():
                if '' not in filename:
                    continue
                    
                year = metadata['year']
                if year not in yearly_stats:
                    yearly_stats[year] = {'count': 0, 'amount': 0, 'items': []}
                
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                yearly_stats[year]['count'] += 1
                yearly_stats[year]['items'].append({
                    'filename': filename,
                    'date': info.get('', ''),
                    'drafter': info.get('', ''),
                    'amount': info.get('', ''),
                    'title': info.get('', filename.replace('.pd', ''))
                })
                
                #  
                if info.get(''):
                    amount_num = re.search(r'(\d+(?:,\d+)*)', info[''])
                    if amount_num:
                        try:
                            yearly_stats[year]['amount'] += int(amount_num.group(1).replace(',', ''))
                        except (ValueError, AttributeError):
                            pass  #    
            
            #  
            report = []
            report.append("     (2021-2025)")
            report.append("=" * 50)
            report.append("")
            
            report.append("###    ")
            report.append("")
            
            total_count = 0
            total_amount = 0
            
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                total_count += stats['count']
                total_amount += stats['amount']
                
                amount_str = f"{stats['amount']:,}" if stats['amount'] > 0 else ""
                report.append(f" **{year}**: {stats['count']} - {amount_str}")
            
            report.append("")
            report.append(f"** : {total_count} - {total_amount:,}**")
            report.append("")
            
            #   
            report.append("###    ")
            for year in sorted(yearly_stats.keys()):
                stats = yearly_stats[year]
                if stats['items']:
                    report.append(f"\n {year} ({stats['count']})")
                    for item in stats['items']:
                        date = item['date'][:10] if item['date'] else ''
                        title = item['title'][:35] + "..." if len(item['title']) > 35 else item['title']
                        amount = f" - {item['amount']}" if item['amount'] else ""
                        report.append(f"   [{date}] {title}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"     : {e}"
    
    def _generate_drafter_report(self, query: str) -> str:
        """   """
        try:
            drafter_stats = {}
            
            for filename, metadata in self.metadata_cache.items():
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                drafter = info.get('', '')
                if drafter not in drafter_stats:
                    drafter_stats[drafter] = {
                        'count': 0,
                        'categories': {'': 0, '': 0, '': 0, '': 0},
                        'years': {},
                        'items': []
                    }
                
                #  
                category = ''
                if '' in filename:
                    category = ''
                elif '' in filename or '' in filename:
                    category = ''
                elif '' in filename:
                    category = ''
                
                drafter_stats[drafter]['count'] += 1
                drafter_stats[drafter]['categories'][category] += 1
                
                #  
                year = metadata['year']
                if year not in drafter_stats[drafter]['years']:
                    drafter_stats[drafter]['years'][year] = 0
                drafter_stats[drafter]['years'][year] += 1
                
                drafter_stats[drafter]['items'].append({
                    'filename': filename,
                    'date': info.get('', ''),
                    'category': category,
                    'title': info.get('', filename.replace('.pd', ''))
                })
            
            #  
            report = []
            report.append("    ")
            report.append("=" * 50)
            report.append("")
            
            report.append("###    ")
            report.append("")
            
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '':
                    stats = drafter_stats[drafter]
                    cat_str = f" {stats['categories']['']},  {stats['categories']['']}"
                    if stats['categories'][''] > 0:
                        cat_str += f",  {stats['categories']['']}"
                    if stats['categories'][''] > 0:
                        cat_str += f",  {stats['categories']['']}"
                    report.append(f" **{drafter}**:  {stats['count']} ({cat_str})")
            
            report.append("")
            
            #   
            report.append("###    ")
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '':
                    stats = drafter_stats[drafter]
                    year_str = ", ".join([f"{year}({count})" for year, count in sorted(stats['years'].items())])
                    report.append(f" {drafter}: {year_str}")
            report.append("")
            
            #   
            report.append("###     ()")
            report.append("*     *")
            report.append("")
            
            for drafter in sorted(drafter_stats.keys()):
                if drafter and drafter != '':
                    stats = drafter_stats[drafter]
                    report.append(f"####  **{drafter}** ({stats['count']})")
                    
                    #  
                    docs_by_year = {}
                    for item in sorted(stats['items'], key=lambda x: x['date'], reverse=True):
                        year = item['date'][:4] if item['date'] else ''
                        if year not in docs_by_year:
                            docs_by_year[year] = []
                        docs_by_year[year].append(item)
                    
                    #  
                    for year in sorted(docs_by_year.keys(), reverse=True):
                        report.append(f"\n**{year}:**")
                        for item in docs_by_year[year]:
                            date = item['date'][5:10] if item['date'] and len(item['date']) >= 10 else ''
                            cat_emoji = {
                                '': '',
                                '': '', 
                                '': '',
                                '': ''
                            }.get(item['category'], '')
                            
                            #    ( )
                            title = item['title']
                            report.append(f"   [{date}] {cat_emoji} {title}")
                    report.append("")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"    : {e}"
    
    def _generate_monthly_repair_report(self, query: str) -> str:
        """   """
        try:
            monthly_stats = {}
            total_amount = 0
            
            for filename, metadata in self.metadata_cache.items():
                if '' not in filename and '' not in filename:
                    continue
                
                pdf_path = self.docs_dir / filename
                info = self._extract_pdf_info(pdf_path)
                
                #  
                date = info.get('', '')
                if date:
                    month_match = re.search(r'-(\d{2})-', date)
                    if month_match:
                        month = int(month_match.group(1))
                        year = metadata['year']
                        month_key = f"{year}-{month:02d}"
                        
                        if month_key not in monthly_stats:
                            monthly_stats[month_key] = {'count': 0, 'amount': 0, 'items': []}
                        
                        monthly_stats[month_key]['count'] += 1
                        monthly_stats[month_key]['items'].append({
                            'filename': filename,
                            'date': date,
                            'drafter': info.get('', ''),
                            'amount': info.get('', ''),
                            'title': info.get('', filename.replace('.pd', ''))
                        })
                        
                        #  
                        if info.get(''):
                            amount_num = re.search(r'(\d+(?:,\d+)*)', info[''])
                            if amount_num:
                                try:
                                    amount = int(amount_num.group(1).replace(',', ''))
                                    monthly_stats[month_key]['amount'] += amount
                                    total_amount += amount
                                except (ValueError, KeyError):
                                    pass  #    
            
            #  
            report = []
            report.append("      ")
            report.append("=" * 50)
            report.append("")
            
            report.append("###   ")
            total_count = sum(stats['count'] for stats in monthly_stats.values())
            report.append(f"   : {total_count}")
            if total_amount > 0:
                report.append(f"   : {total_amount:,}")
                report.append(f"   : {total_amount // total_count:,}")
            report.append("")
            
            report.append("###    ")
            report.append("")
            
            for month_key in sorted(monthly_stats.keys()):
                stats = monthly_stats[month_key]
                year, month = month_key.split('-')
                amount_str = f"{stats['amount']:,}" if stats['amount'] > 0 else ""
                report.append(f" **{year} {int(month)}**: {stats['count']} - {amount_str}")
            
            report.append("")
            
            #   
            report.append("###     ")
            for month_key in sorted(monthly_stats.keys()):
                stats = monthly_stats[month_key]
                year, month = month_key.split('-')
                report.append(f"\n {year} {int(month)} ({stats['count']})")
                
                for item in stats['items']:
                    date = item['date'][:10] if item['date'] else ''
                    title = item['title'][:35] + "..." if len(item['title']) > 35 else item['title']
                    amount = f" - {item['amount']}" if item['amount'] else ""
                    report.append(f"   [{date}] {title}{amount}")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"     : {e}"
    
    def _format_conditions(self, conditions: dict) -> str:
        """    """
        formatted = []
        
        if 'location' in conditions:
            formatted.append(f" : {conditions['location']}")
        
        if 'manufacturer' in conditions:
            formatted.append(f" : {conditions['manufacturer']}")
        
        if 'year' in conditions:
            year_str = f" : {conditions['year']}"
            if conditions.get('year_range') == 'before':
                year_str += " "
            elif conditions.get('year_range') == 'after':
                year_str += " "
            elif conditions.get('year_range') == 'between':
                year_str = f" : {conditions.get('year_start')} ~ {conditions.get('year_end')}"
            formatted.append(year_str)
        
        if 'price' in conditions:
            price_str = f" : {conditions['price']:,.0f}"
            if conditions.get('price_range') == 'above':
                price_str += " "
            elif conditions.get('price_range') == 'below':
                price_str += " "
            formatted.append(price_str)
        
        if 'equipment_type' in conditions:
            formatted.append(f"  : {conditions['equipment_type']}")
        
        if 'model' in conditions:
            formatted.append(f" : {conditions['model']}")
        
        return '\n'.join(formatted) if formatted else " "
    
    def _search_location_summary(self, txt_path: Path, location: str) -> str:
        """    """
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            equipment_by_category = {}  # {: [ ]}
            current_item = []
            total_count = 0
            total_amount = 0  #  
            
            for line in lines:
                if re.match(r'^\[\d{4}\]', line.strip()):
                    if current_item:
                        item_text = '\n'.join(current_item)
                        #  
                        if self._check_location_in_item(item_text, location):
                            total_count += 1
                            #   
                            equipment_name = current_item[0].split(']')[1].strip() if ']' in current_item[0] else current_item[0]
                            
                            #  
                            category = self._determine_equipment_category(equipment_name, item_text)
                            
                            if category not in equipment_by_category:
                                equipment_by_category[category] = []
                            
                            #  
                            info = {
                                'name': equipment_name,
                                'model': "N/A",
                                'price': 0,
                                'quantity': 1,
                                'date': "N/A"
                            }
                            
                            for item_line in current_item:
                                # 
                                if ":" in item_line:
                                    model_match = re.search(r':\s*([^|]+)', item_line)
                                    if model_match:
                                        info['model'] = model_match.group(1).strip()
                                
                                #  
                                if ":" in item_line:
                                    amount_match = re.search(r':\s*([\d,]+)', item_line)
                                    if amount_match:
                                        amount_str = amount_match.group(1).replace(',', '')
                                        try:
                                            info['price'] = int(amount_str)
                                            total_amount += info['price']
                                        except Exception as e:
                                            pass
                                
                                # 
                                if ":" in item_line:
                                    qty_match = re.search(r':\s*(\d+)', item_line)
                                    if qty_match:
                                        info['quantity'] = int(qty_match.group(1))
                                
                                # 
                                if ":" in item_line:
                                    date_match = re.search(r':\s*([^\s|]+)', item_line)
                                    if date_match:
                                        info['date'] = date_match.group(1).strip()
                            
                            equipment_by_category[category].append(info)
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            #   
            if current_item:
                item_text = '\n'.join(current_item)
                if self._check_location_in_item(item_text, location):
                    total_count += 1
                    equipment_name = current_item[0].split(']')[1].strip() if ']' in current_item[0] else current_item[0]
                    category = self._determine_equipment_category(equipment_name, item_text)
                    if category not in equipment_by_category:
                        equipment_by_category[category] = []
                    
                    info = {
                        'name': equipment_name,
                        'model': "N/A",
                        'price': 0,
                        'quantity': 1,
                        'date': "N/A"
                    }
                    
                    for item_line in current_item:
                        if ":" in item_line:
                            model_match = re.search(r':\s*([^|]+)', item_line)
                            if model_match:
                                info['model'] = model_match.group(1).strip()
                        if ":" in item_line:
                            amount_match = re.search(r':\s*([\d,]+)', item_line)
                            if amount_match:
                                amount_str = amount_match.group(1).replace(',', '')
                                try:
                                    info['price'] = int(amount_str)
                                    total_amount += info['price']
                                except Exception as e:
                                    pass
                        if ":" in item_line:
                            qty_match = re.search(r':\s*(\d+)', item_line)
                            if qty_match:
                                info['quantity'] = int(qty_match.group(1))
                        if ":" in item_line:
                            date_match = re.search(r':\s*([^\s|]+)', item_line)
                            if date_match:
                                info['date'] = date_match.group(1).strip()
                    
                    equipment_by_category[category].append(info)
            
            #  
            if equipment_by_category:
                response = f" **{location}  **\n"
                response += "=" * 70 + "\n"
                response += f"  **{total_count}** \n"
                if total_amount > 0:
                    #   (/ )
                    if total_amount >= 100000000:  # 1 
                        amount_str = f"{total_amount/100000000:.1f}"
                    elif total_amount >= 10000000:  # 1 
                        amount_str = f"{total_amount/10000000:.0f}"
                    else:
                        amount_str = f"{total_amount:,}"
                else:
                    response += "\n"
                
                #  
                response += "###    \n"
                response += "-" * 50 + "\n"
                
                #   (   )
                sorted_categories = sorted(equipment_by_category.items(), key=lambda x: len(x[1]), reverse=True)
                
                for category, items in sorted_categories:
                    #   
                    category_amount = sum(item['price'] for item in items)
                    
                    response += f"\n**{category}** ({len(items)}"
                    if category_amount > 0:
                        if category_amount >= 100000000:
                            response += f", {category_amount/100000000:.1f}"
                        elif category_amount >= 10000000:
                            response += f", {category_amount/10000000:.0f}"
                        else:
                            response += f", {category_amount:,}"
                    response += ")\n"
                    
                    #   
                    equipment_summary = {}
                    for item in items:
                        key = f"{item['name']} ({item['model']})" if item['model'] != "N/A" else item['name']
                        if key not in equipment_summary:
                            equipment_summary[key] = {
                                'count': 0,
                                'total_price': 0,
                                'unit_price': item['price'] // item['quantity'] if item['quantity'] > 0 else item['price']
                            }
                        equipment_summary[key]['count'] += item['quantity']
                        equipment_summary[key]['total_price'] += item['price']
                    
                    #    
                    sorted_equipment = sorted(equipment_summary.items(), 
                                           key=lambda x: x[1]['total_price'], 
                                           reverse=True)
                    
                    #  5 
                    for i, (equip_name, equip_info) in enumerate(sorted_equipment[:5], 1):
                        line = f"  {i}. {equip_name}"
                        if equip_info['count'] > 1:
                            line += f" - {equip_info['count']}"
                        if equip_info['total_price'] > 0:
                            line += f" ({equip_info['total_price']:,})"
                        response += line + "\n"
                    
                    if len(sorted_equipment) > 5:
                        response += f"  ...  {len(sorted_equipment)-5}\n"
                
                response += f"\n : {txt_path.name}"
                # LLM  
            else:
                return f" {location}    ."
                
        except Exception as e:
            return f"  : {e}"
    
    def _determine_equipment_category(self, equipment_name: str, item_text: str) -> str:
        """   """
        name_lower = equipment_name.lower()
        text_lower = item_text.lower()
        
        if any(kw in name_lower or kw in text_lower for kw in ['camera', '', 'ccu', 'viewfinder', '']):
            return "  "
        elif any(kw in name_lower or kw in text_lower for kw in ['monitor', '', 'display']):
            return " "
        elif any(kw in name_lower or kw in text_lower for kw in ['audio', '', 'mixer', '', 'mic', '']):
            return "  "
        elif any(kw in name_lower or kw in text_lower for kw in ['server', '', 'storage', '']):
            return " /"
        elif any(kw in name_lower or kw in text_lower for kw in ['switch', '', 'router', '', 'matrix']):
            return " /"
        elif any(kw in name_lower or kw in text_lower for kw in ['cable', '', 'connector', '']):
            return " /"
        elif any(kw in name_lower or kw in text_lower for kw in ['tripod', '', 'pedestal', '']):
            return "  "
        elif any(kw in name_lower or kw in text_lower for kw in ['intercom', '', 'talkback']):
            return " "
        elif any(kw in name_lower or kw in text_lower for kw in ['converter', '', 'encoder', '']):
            return " /"
        else:
            return "  "

    def _search_location_unified(self, txt_path: Path, query: str) -> str:
        try:
            #    
            if complete_path.exists():
                txt_path = complete_path
            
            #   
            location_keywords = {
                '': '',
                'news van': 'News VAN',
                'mini van': 'Mini VAN',
                '': '',
                '': '',
                '': '',
                '': '',
                '': ''
            }
            
            found_location = None
            query_lower = query.lower()
            for key, value in location_keywords.items():
                if key in query_lower:
                    found_location = value
                    break
            
            #    
            if found_location:
                # "", "", ""    
                if any(kw in query for kw in ['', '', '', '']):
                    return self._search_location_summary(txt_path, found_location)
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            #   
            location_keyword = None
            
            #  
            if '' in query.lower() or 'van' in query.lower():
                location_keyword = ''
                search_term = 'Van'  #   Van 
            else:
                #    
                location_patterns = [
                    (r'\s*', ''),
                    (r'\s*', ''),
                    (r'\s*', ''),
                    (r'\s*', ''),
                    (r'', ''),
                    (r'', ''),
                    (r'[-]{2,}(?:||||||||||)', None)
                ]
                
                for pattern, keyword in location_patterns:
                    match = re.search(pattern, query)
                    if match:
                        location_keyword = keyword if keyword else match.group(0)
                        search_term = location_keyword
                        break
            
            if not location_keyword:
                return "     . (:  , , )"
            
            lines = content.split('\n')
            matching_items = []
            current_item = []
            item_count = 0
            
            for line in lines:
                if re.match(r'^\[\d{4}\]', line):
                    #   
                    if current_item:
                        item_text = '\n'.join(current_item)
                        #  
                        if search_term in item_text or (location_keyword in item_text):
                            matching_items.append(item_text)
                            item_count += 1
                    
                    current_item = [line]
                elif current_item:
                    current_item.append(line)
            
            #   
            if current_item:
                item_text = '\n'.join(current_item)
                if search_term in item_text or (location_keyword in item_text):
                    matching_items.append(item_text)
                    item_count += 1
            
            if matching_items:
                #   
                response = f" **{location_keyword}  **\n"
                response += "=" * 70 + "\n"
                response += f"  **{item_count}** \n\n"
                
                #   
                equipment_types = {}
                for item in matching_items:
                    #  
                    if ':' in item:
                        part_match = re.search(r':\s*([^\n]+)', item)
                        if part_match:
                            part_name = part_match.group(1).strip()
                            #  
                            if 'Camera' in part_name or '' in part_name:
                                type_name = ''
                            elif 'Monitor' in part_name or '' in part_name:
                                type_name = ''
                            elif 'Audio' in part_name or '' in part_name or 'Mic' in part_name:
                                type_name = '/'
                            elif 'Light' in part_name or '' in part_name:
                                type_name = ''
                            elif 'Lens' in part_name or '' in part_name:
                                type_name = ''
                            elif 'CCU' in part_name or 'Control Unit' in part_name:
                                type_name = 'CCU/'
                            elif 'Server' in part_name or '' in part_name:
                                type_name = '/'
                            else:
                                type_name = ''
                            
                            equipment_types[type_name] = equipment_types.get(type_name, 0) + 1
                
                if equipment_types:
                    response += " **  **:\n"
                    for type_name, count in sorted(equipment_types.items(), key=lambda x: x[1], reverse=True):
                        response += f"   {type_name}: {count}\n"
                    response += "\n"
                
                response += "-" * 70 + "\n"
                response += " **  ** ( 15):\n\n"
                
                #   ( 15)
                for i, item in enumerate(matching_items[:15], 1):
                    lines = item.split('\n')
                    
                    #   
                    item_info = {}
                    for line in lines:
                        if re.match(r'^\[\d{4}\]', line):
                            item_info['id'] = line.strip()
                        elif ':' in line:
                            item_info['name'] = line.split(':')[1].strip()
                        elif ':' in line:
                            item_info['model'] = line.split(':')[1].strip()
                        elif ':' in line and ':' not in line:
                            item_info['manufacturer'] = line.split(':')[1].strip()
                        elif ':' in line:
                            item_info['date'] = line.split(':')[1].strip()[:10]
                        elif ':' in line:
                            item_info['manager'] = line.split(':')[1].strip()
                    
                    response += f"[{i}] **{item_info.get('id', '')}**"
                    if 'name' in item_info:
                        response += f" {item_info['name']}\n"
                    else:
                        response += "\n"
                    
                    if 'model' in item_info:
                        response += f"     : {item_info['model']}\n"
                    if 'manufacturer' in item_info:
                        response += f"     : {item_info['manufacturer']}\n"
                    if 'date' in item_info:
                        response += f"     : {item_info['date']}\n"
                    if 'manager' in item_info:
                        response += f"     : {item_info['manager']}\n"
                    response += "\n"
                
                if len(matching_items) > 15:
                    response += f"...  {len(matching_items) - 15} \n"
                
                response += f"\n : {txt_path.name}"
                # LLM  
            else:
                return f" {location_keyword}    ."
            
        except Exception as e:
            return f"  : {e}"
    
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            summary += "" * 40 + "\n"
            
            #  100   
            for line in lines[:100]:
                if '  :' in line or \
                   ' ' in line and ('' in line or '' in line):
                    summary += line
            
            summary += f"\n : {txt_path.name}"
            return summary
            
        except Exception as e:
            return f"   : {e}"
    
    def _categorize_equipment(self, equipment_name: str) -> str:
        """    """
        name_lower = equipment_name.lower()
        
        #    
        if any(word in name_lower for word in ['camera', 'ccu', '', 'cam']):
            return ' '
        elif any(word in name_lower for word in ['monitor', '', 'display']):
            return '/'
        elif any(word in name_lower for word in ['mic', 'microphone', '', 'audio']):
            return '/'
        elif any(word in name_lower for word in ['switcher', 'router', '', '']):
            return '/'
        elif any(word in name_lower for word in ['server', '', 'storage', 'nas']):
            return '/'
        elif any(word in name_lower for word in ['converter', '', 'adapter']):
            return '/'
        elif any(word in name_lower for word in ['lens', '', 'optical']):
            return '/'
        elif any(word in name_lower for word in ['tripod', '', 'stand']):
            return '/'
        elif any(word in name_lower for word in ['battery', '', 'charger', 'power']):
            return '/'
        elif any(word in name_lower for word in ['cable', '', 'connector']):
            return '/'
        elif any(word in name_lower for word in ['analyzer', 'test', '', '']):
            return '/ '
        elif any(word in name_lower for word in ['transmitter', 'receiver', '', '']):
            return ' '
        elif any(word in name_lower for word in ['recorder', 'player', '', '']):
            return '/ '
        elif any(word in name_lower for word in ['light', '', 'led', 'lamp']):
            return ' '
        elif 'nexio' in name_lower:
            return 'NEXIO '
        elif 'hp' in name_lower and any(word in name_lower for word in ['z8', 'z6', 'z4', 'workstation']):
            return 'HP '
        else:
            #   
            return ' '
    
    def _count_by_field(self, content: str, field_name: str, search_value: str) -> dict:
        """    """
        lines = content.split('\n')
        count = 0
        items = []
        current_item = []
        is_matching = False
        
        for line in lines:
            #    
            if re.match(r'^\[\d{4}\]', line):
                #    
                if is_matching and current_item:
                    count += 1
                    if len(items) < 10:  #  10 
                        items.append('\n'.join(current_item))
                
                #   
                current_item = [line]
                is_matching = False
            elif current_item:
                current_item.append(line)
                #   
                if field_name == "" and ":" in line:
                    if search_value in line:
                        is_matching = True
                elif field_name == "" and ":" in line:
                    #     
                    location_match = re.search(r':\s*([^|\n]+)', line)
                    if location_match:
                        actual_location = location_match.group(1).strip()
                        
                        #   
                        if search_value == actual_location:
                            #  
                            is_matching = True
                        elif search_value == '':
                            # ''  '*'  
                            is_matching = actual_location.endswith('')
                        elif search_value == '':
                            # ''  '*'   
                            is_matching = actual_location.endswith('')
                        elif search_value == '':
                            # ''  '*'  
                            is_matching = actual_location.endswith('')
                        elif search_value in ['', 'van', 'Van', 'VAN']:
                            #   Van    
                            is_matching = 'Van' in actual_location or 'VAN' in actual_location
                        elif len(search_value) > 3:
                            # 3      
                            is_matching = search_value in actual_location
                elif field_name == "" and ":" in line:
                    if search_value in line:
                        is_matching = True
                elif field_name == "" and ":" in line:
                    if search_value.upper() in line.upper():
                        is_matching = True
        
        #   
        if is_matching and current_item:
            count += 1
            if len(items) < 10:
                items.append('\n'.join(current_item))
        
        return {
            'count': count,
            'sample_items': items
        }
    
        lines = []
        lines.append(f" **{model}  **")
        lines.append("=" * 60)
        
        locations = {}
            if '' in item:
                loc = item['']
                locations[loc] = locations.get(loc, 0) + 1
        
        if locations:
            for loc, count in sorted(locations.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f" **{loc}**: {count}")
            lines.append("")
        
        #   -      
        lines.append("###    ")
        lines.append("")
        
            # [1]    
            item_name = f"{item.get('', model)}"
            lines.append(f"[{i}]  {item_name}")
            
            #  -   
            basic_info = []
            if '' in item:
                basic_info.append(f": {item['']}")
            if '' in item:
                basic_info.append(f": {item['']}")
            if basic_info:
                lines.append(f"  : {' | '.join(basic_info)}")
            
            # 
            location_info = []
            if '' in item:
                location_info.append(f": {item['']}")
            if '' in item:
                location_info.append(f": {item['']}")
            if location_info:
                lines.append(f"  : {' | '.join(location_info)}")
            
            #  -    
            mgmt_info = []
            if '' in item:
                mgmt_info.append(f": {item['']}")
            if '' in item:
                mgmt_info.append(f": {item['']}")
            if '' in item:
                mgmt_info.append(f": {item['']}")
            if '' in item:
                mgmt_info.append(f": {item['']}")
            if mgmt_info:
                lines.append(f"  : {' | '.join(mgmt_info)}")
            
            lines.append("")  #    
        
        #  
        lines.append("\n###   ")
        
        #  
        years = {}
            if '' in item:
                year = item[''][:4] if len(item['']) >= 4 else None
                if year and year.isdigit():
                    years[year] = years.get(year, 0) + 1
        
        if years:
            lines.append("\n** :**")
            for year, count in sorted(years.items(), reverse=True)[:3]:
                lines.append(f" {year}: {count}")
        
        lines.append("\n---")
        
        return '\n'.join(lines)
    
    def _search_multiple_documents(self, query: str) -> str:
        """     """
        try:
            #   
            query_lower = query.lower()
            
            #   
            matched_docs = []
            
            for cache_key, metadata in self.metadata_cache.items():
                # TXT   (PDF )
                if metadata.get('is_txt', False):
                    continue

                filename = metadata.get('filename', cache_key)
                score = 0
                filename_lower = filename.lower()
                
                #  
                keywords_in_query = []

                #    ( )
                query_words = re.findall(r'[-]+|[A-Za-z]+', query_lower)
                file_words = re.findall(r'[-]+|[A-Za-z]+', filename_lower)

                #  
                stopwords = ['', '', '', '', '', '', '', '', '', '', '']

                #    ( DB )
                if '' in query_lower:
                    # " "  " "  
                    drafter_match = re.search(r'([-]{2,4})\s*|\s*([-]{2,4})', query)
                    if drafter_match:
                        search_drafter = drafter_match.group(1) or drafter_match.group(2)
                        if search_drafter and metadata.get('is_pd'):
                            found_drafter = False

                            # 1.  DB  
                            if self.metadata_db:
                                db_info = self.metadata_db.get_document(filename)
                                if db_info and db_info.get('drafter'):
                                    if search_drafter in db_info['drafter']:
                                        score += 50
                                        found_drafter = True

                            # 2. DB  PDF   
                            if not found_drafter and metadata.get('drafter') is None:
                                try:
                                    #     ( )
                                    import pdfplumber
                                    with pdfplumber.open(metadata['path']) as pdf:
                                        if pdf.pages:
                                            #    
                                            text = pdf.pages[0].extract_text() or ""
                                            if len(text) > 50:  #  PDF 
                                                #   
                                                patterns = [
                                                    r'[\s:]*([-]{2,4})',
                                                    r'[\s:]*([-]{2,4})',
                                                ]
                                                for pattern in patterns:
                                                    match = re.search(pattern, text)
                                                    if match:
                                                        drafter = match.group(1).strip()
                                                        # DB 
                                                        if self.metadata_db:
                                                            self.metadata_db.add_document(filename, drafter=drafter)
                                                        if search_drafter in drafter:
                                                            score += 50
                                                            found_drafter = True
                                                        break
                                except Exception as e:
                                    pass

                        #     
                        if score < 50:
                            continue

                #    (DVR, CCU ) -  
                equipment_names = ['dvr', 'ccu', '', '', '', '', '', '', '', '']
                for equipment in equipment_names:
                    if equipment in query_lower:
                        # DVR  DVR  (  )
                        if equipment == 'dvr':
                            # DVR    (D-tap, VR  )
                            if re.search(r'\bDVR\b', filename, re.IGNORECASE):
                                score += 20  # DVR  
                            elif 'dvr' in filename_lower and 'd-tap' not in filename_lower and 'vr' not in filename_lower:
                                score += 15
                        else:
                            #    
                            if equipment in filename_lower:
                                score += 15

                        #  
                        if any(equipment == kw.lower() for kw in metadata.get('keywords', [])):
                            score += 8
                
                for word in query_words:
                    if len(word) >= 2 and word not in stopwords:
                        keywords_in_query.append(word)
                        #      
                        if word in file_words:
                            #    
                            score += len(word) * 2
                        #   - DVR    
                        elif len(word) >= 4:  # 4   
                            for f_word in file_words:
                                #     
                                if len(f_word) >= 4 and (word in f_word or f_word in word):
                                    score += len(word) // 2  #    
                
                #   
                for keyword in metadata['keywords']:
                    if keyword.lower() in query_lower:
                        score += 3
                
                #   
                year_match = re.search(r'(20\d{2})', query)
                month_match = re.search(r'(\d{1,2})\s*', query)
                
                if year_match:
                    query_year = year_match.group(1)
                    if metadata['year'] == query_year:
                        score += 5
                        
                        #   
                        if month_match:
                            query_month = int(month_match.group(1))
                            file_month_match = re.search(r'\d{4}-(\d{2})-\d{2}', filename)
                            if file_month_match:
                                file_month = int(file_month_match.group(1))
                                if file_month == query_month:
                                    score += 10  #    
                                else:
                                    score = 0  #   
                                    continue
                    else:
                        #   
                        continue  #    
                
                #     (   )
                #     
                has_equipment = False  #   

                if '' in query_lower:
                    MIN_SCORE = 1 if score > 0 else 999  #     
                elif re.search(r'20\d{2}', query):
                    MIN_SCORE = 2  #    
                else:
                    MIN_SCORE = 3  #   3  

                #     
                for equipment in equipment_names:
                    if equipment in query_lower:
                        has_equipment = True
                        # DVR   
                        if equipment == 'dvr':
                            if 'DVR' in filename or ('dvr' in filename_lower and 'd-tap' not in filename_lower and 'vr' not in filename_lower):
                                MIN_SCORE = 0  # DVR   
                            else:
                                MIN_SCORE = 10  # DVR  DVR   
                        else:
                            #  
                            if equipment in filename_lower:
                                MIN_SCORE = 0
                            else:
                                MIN_SCORE = max(3, MIN_SCORE)
                        break
                
                if score >= MIN_SCORE:
                    # metadata path 
                    pdf_path = metadata.get('path')
                    if isinstance(pdf_path, str):
                        pdf_path = Path(pdf_path)
                    if not pdf_path:
                        pdf_path = self.docs_dir / filename

                    info = self._extract_pdf_info(pdf_path)
                    matched_docs.append({
                        'filename': filename,
                        'score': score,
                        'info': info,
                        'year': metadata['year'],
                        'cache_key': cache_key  #    
                    })
            
            #    
            unique_docs = {}
            for doc in matched_docs:
                filename = doc['filename']
                if filename not in unique_docs:
                    unique_docs[filename] = doc
                else:
                    #      
                    if doc['score'] > unique_docs[filename]['score']:
                        unique_docs[filename] = doc
                    #   year_  
                    elif doc['score'] == unique_docs[filename]['score'] and 'year_' in doc.get('cache_key', ''):
                        unique_docs[filename] = doc

            matched_docs = list(unique_docs.values())

            #   
            matched_docs.sort(key=lambda x: x['score'], reverse=True)

            #   ( )
            #   20,   15
            max_results = 20 if has_equipment else 15
            if len(matched_docs) > max_results:
                matched_docs = matched_docs[:max_results]
            
            if not matched_docs:
                return "     ."
            
            #   ( UI)
            report = []
            report.append(f"##  '{query}'  ")
            report.append(f"** {len(matched_docs)}  **\n")
            report.append("---\n")
            
            #   (    )
            docs_by_year = {}

            for doc in matched_docs:
                year = doc['year']
                if year not in docs_by_year:
                    docs_by_year[year] = []
                docs_by_year[year].append(doc)
            
            #  
            for year in sorted(docs_by_year.keys(), reverse=True):
                report.append(f"###  {year} ({len(docs_by_year[year])})\n")
                
                for doc in docs_by_year[year]:
                    info = doc['info']
                    filename = doc['filename']
                    relative_path = doc.get('cache_key', filename)  #    
                    
                    #    
                    if '' in filename:
                        category = ""
                        emoji = ""
                    elif '' in filename or '' in filename:
                        category = "/"
                        emoji = ""
                    elif '' in filename:
                        category = ""
                        emoji = ""
                    elif '' in filename:
                        category = ""
                        emoji = ""
                    else:
                        category = ""
                        emoji = ""
                    
                    #   ( )
                    title_parts = filename.replace('.pd', '').split('_', 1)
                    title = title_parts[1] if len(title_parts) > 1 else title_parts[0]
                    
                    #  
                    drafter = info.get('', '')
                    date = info.get('', '')
                    amount = info.get('', '')
                    
                    #   - metadata_cache   
                    summary = ""

                    # metadata   
                    cached_metadata = None
                    for ck, md in self.metadata_cache.items():
                        if md.get('filename') == filename:
                            cached_metadata = md
                            break

                    if cached_metadata and cached_metadata.get('text'):
                        #     
                        text = cached_metadata['text'][:500]  #  500

                        #   
                        if '' in text:
                            purpose_match = re.search(r'[:\s]+([^\n]+)', text)
                            if purpose_match:
                                summary = purpose_match.group(1).strip()
                        elif '' in text:
                            content_match = re.search(r'[:\s]+([^\n]+)', text)
                            if content_match:
                                summary = content_match.group(1).strip()
                        elif '' in text:
                            reason_match = re.search(r'[:\s]+([^\n]+)', text)
                            if reason_match:
                                summary = reason_match.group(1).strip()

                    #     
                    if not summary:
                        if '' in filename:
                            summary = "  "
                        elif '' in filename or '' in filename:
                            summary = " / "
                        elif '' in filename:
                            summary = "   "
                        elif '' in filename:
                            summary = "   "
                        elif '' in filename:
                            summary = "  "
                        else:
                            summary = "  "
                    
                    #  UI  
                    report.append(f"#### {emoji} **{title}**")
                    report.append(f"**[{category}]** | {date if date else ' '}")
                    
                    #  
                    if drafter:
                        report.append(f"- ****: {drafter}")
                    if amount:
                        report.append(f"- ****: {amount}")
                    if summary:
                        report.append(f"- ****: {summary}")
                    
                    #     (web_interface   )
                    #   : @@PDF_PREVIEW@@
                    file_path_str = str(relative_path) if relative_path else filename
                    report.append(f"- ****: [{file_path_str}] @@PDF_PREVIEW@@{file_path_str}@@")
                    report.append("")  # 
                
                report.append("---\n")
            
            return "\n".join(report)
            
        except Exception as e:
            return f"   : {e}"

    def _search_and_analyze_by_content(self, query: str) -> str:
        """"

        :
        - "DVR   "  DVR        
        - "  "       
        """"
        try:
            # 1.     
            query_lower = query.lower()

            # / 
            equipment_keywords = []
            equipment_terms = ['DVR', '', '', '', '', 'CCU', '', '', '', '']
            for term in equipment_terms:
                if term.lower() in query_lower:
                    equipment_keywords.append(term)

            #   
            action_keywords = []
            action_terms = ['', '', '', '', '', '', '', '', '']
            for term in action_terms:
                if term in query_lower:
                    action_keywords.append(term)

            if not equipment_keywords:
                #   
                nouns = re.findall(r'[\uac00-\ud7a3]{2,}', query)
                equipment_keywords = [n for n in nouns if n not in ['', '', '', '', '']]

            print(f"  : {equipment_keywords},  : {action_keywords}")

            # 2.   
            #  1:    
            primary_files = []
            #  2:    
            secondary_files = []
            #  3:     (, )
            content_match_files = []

            for cache_key, metadata in self.metadata_cache.items():
                if metadata.get('is_pd'):
                    #    (cache_key  metadata['filename'])
                    filename_lower = metadata.get('filename', cache_key).lower()
                    path = metadata['path']

                    #     
                    has_equipment_keyword = any(kw.lower() in filename_lower for kw in equipment_keywords)
                    has_action_keyword = any(kw.lower() in filename_lower for kw in action_keywords)

                    if has_equipment_keyword:
                        primary_files.append(path)
                    elif has_action_keyword:
                        secondary_files.append(path)

            # 3.   ( 15)
            relevant_files = primary_files[:10] + secondary_files[:5]

            if not relevant_files:
                #       ( )
                if len(equipment_keywords) > 0:
                    print("   ,   ...")
                    for file_path, metadata in list(self.metadata_cache.items())[:30]:  #  30
                        if metadata.get('is_pd'):
                            try:
                                info = self._extract_pdf_info(metadata['path'])
                                if info and 'text' in info:
                                    content = info['text'][:2000]  #  2000
                                    if any(kw.lower() in content.lower() for kw in equipment_keywords):
                                        content_match_files.append(metadata['path'])
                                        if len(content_match_files) >= 5:  #  5
                                            break
                            except Exception as e:
                                continue
                    relevant_files.extend(content_match_files)

            if not relevant_files:
                return f" '{', '.join(equipment_keywords + action_keywords)}'     ."

            print(f" {len(relevant_files)}   ")

            #  :  5  
            max_docs_to_process = 5
            files_to_process = relevant_files[:max_docs_to_process]
            if len(relevant_files) > max_docs_to_process:
                print(f"  :  {max_docs_to_process}   ( {len(relevant_files)} )")

            # 4.      
            document_analyses = []
            all_contents = []

            for file_path in files_to_process:
                try:
                    info = self._extract_pdf_info(file_path)
                    if info:
                        #     
                        relevant_content = []
                        if 'text' in info:
                            lines = info['text'].split('\n')
                            for i, line in enumerate(lines):
                                line_lower = line.lower()
                                #       
                                if any(kw in line_lower for kw in action_keywords + equipment_keywords):
                                    #  2 
                                    start = max(0, i-2)
                                    end = min(len(lines), i+3)
                                    context = ' '.join(lines[start:end])
                                    relevant_content.append(context)

                        doc_analysis = {
                            'filename': file_path.name,
                            'title': info.get('', file_path.stem),
                            'date': info.get('', ''),
                            'drafter': info.get('', ''),
                            'amount': info.get('', ''),
                            'relevant_content': relevant_content[:3],  #  3  
                            'full_text': info.get('text', '')[:2000]  #   
                        }
                        document_analyses.append(doc_analysis)
                        all_contents.append(f"[{file_path.name}]\n" + '\n'.join(relevant_content[:3]))
                except Exception as e:
                    print(f" {file_path.name}  : {e}")
                    continue

            if not document_analyses:
                return "     ."

            # 5. LLM   
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print(" LLM   ...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)

            combined_text = '\n\n'.join(all_contents)

            prompt = f""" '{', '.join(equipment_keywords)}'  '{', '.join(action_keywords)}'   ."

 : {query}

 :
{combined_text[:6000]}

      .
  :
1.     
2. /  ()
3.    
4.  
5.   

 .""""

            context_chunks = [{
                'content': combined_text[:6000],
                'metadata': {'source': 'multiple_documents'},
                'score': 1.0
            }]

            response_obj = self.llm.generate_response(prompt, context_chunks)
            llm_response = response_obj.answer if hasattr(response_obj, 'answer') else str(response_obj)

            # 6.  
            result = []
            result.append(f" **'{', '.join(equipment_keywords)}'  {len(document_analyses)}  **\n")
            result.append("="*50 + "\n\n")

            # LLM  
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            #   
            result.append("\n ** :**\n")
            for doc in document_analyses:
                result.append(f"\n **{doc['title']}**")
                if doc['date']:
                    result.append(f"  - : {doc['date']}")
                if doc['drafter']:
                    result.append(f"  - : {doc['drafter']}")
                if doc['amount']:
                    result.append(f"  - : {doc['amount']}")
                if doc['relevant_content']:
                    result.append(f"  -  : {len(doc['relevant_content'])}  ")

            return '\n'.join(result)

        except Exception as e:
            return f"    : {e}"

    def _read_and_summarize_documents(self, query: str) -> str:
        """"

        Args:
            query:   (: "DVR    ")

        Returns:
              
        """"
        try:
            #  
            query_lower = query.lower()
            keywords = []

            #   
            important_keywords = ['DVR', '', '', '', '', '', '', '']
            for kw in important_keywords:
                if kw.lower() in query_lower:
                    keywords.append(kw)

            #     
            if not keywords:
                #   
                nouns = re.findall(r'[\uac00-\ud7a3]{2,}', query)
                keywords = [n for n in nouns if n not in ['', '', '', '', '', '', '']]

            if not keywords:
                return "     .   ."

            print(f"   : {keywords}")

            #   
            relevant_files = []
            for file_path, metadata in self.metadata_cache.items():
                if metadata.get('is_pd'):
                    #      
                    filename_lower = file_path.lower()
                    for kw in keywords:
                        if kw.lower() in filename_lower:
                            relevant_files.append(metadata['path'])
                            break

            if not relevant_files:
                return f" '{', '.join(keywords)}'     ."

            print(f" {len(relevant_files)}   ")

            #    
            all_contents = []
            document_summaries = []

            for file_path in relevant_files[:10]:  #  10  
                try:
                    # PDF  
                    info = self._extract_pdf_info(file_path)
                    if info:
                        doc_summary = {
                            'filename': file_path.name,
                            'title': info.get('', file_path.stem),
                            'date': info.get('', ' '),
                            'drafter': info.get('', ''),
                            'amount': info.get('', ''),
                            'content': info.get('text', '')[:3000]  #  3000
                        }

                        #   
                        if 'text' in info:
                            #   
                            important_sentences = []
                            lines = info['text'].split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and len(line) > 20:
                                    #    
                                    if any(kw in line for kw in ['', '', '', '', '', '', '', '', '']):
                                        important_sentences.append(line[:200])

                            doc_summary['key_points'] = important_sentences[:5]

                        document_summaries.append(doc_summary)
                        all_contents.append(f"\n[{file_path.name}]\n{info.get('text', '')[:3000]}")

                except Exception as e:
                    print(f" {file_path.name}  : {e}")
                    continue

            if not document_summaries:
                return "     ."

            # LLM   
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print(" LLM   ...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)

            #   
            combined_text = '\n\n'.join(all_contents)

            prompt = f""" '{', '.join(keywords)}'   ."

    .

  :
1.   
2. /  
3.     ()
4.   ()
5.   
6.  

 :
{combined_text[:8000]}

   .      .""""

            # LLM 
            context_chunks = [{
                'content': combined_text[:8000],
                'metadata': {'source': 'multiple_documents'},
                'score': 1.0
            }]

            response_obj = self.llm.generate_response(prompt, context_chunks)
            llm_response = response_obj.answer if hasattr(response_obj, 'answer') else str(response_obj)

            #  
            result = []
            result.append(f" **{len(document_summaries)} {', '.join(keywords)}    **\n")
            result.append("="*50 + "\n")

            # LLM  
            result.append(llm_response)
            result.append("\n" + "="*50 + "\n")

            #    
            result.append("\n **  :**\n")
            for doc in document_summaries:
                result.append(f"\n **{doc['title']}**")
                result.append(f"  - : {doc['date']}")
                result.append(f"  - : {doc['drafter']}")
                if doc['amount']:
                    result.append(f"  - : {doc['amount']}")

            return '\n'.join(result)

        except Exception as e:
            return f"    : {e}"

    def _generate_detailed_location_list(self, content: str, location: str, result: dict, txt_path: Path) -> str:
        """    LLM  """
        try:
            # LLM  ()
            if self.llm is None:
                if not LLMSingleton.is_loaded():
                    print(" LLM   ...")
                self.llm = LLMSingleton.get_instance(model_path=self.model_path)
            
            #    
            lines = content.split('\n')
            location_items = []
            current_item = []
            
            for line in lines:
                if line.strip().startswith('[') and line.strip().endswith(']'):
                    #    
                    if current_item and self._is_location_match(current_item, location):
                        location_items.append('\n'.join(current_item))
                    current_item = [line]
                elif current_item:
                    current_item.append(line)
            
            #   
            if current_item and self._is_location_match(current_item, location):
                location_items.append('\n'.join(current_item))
            
            if not location_items:
                return f" {location}    ."
            
            # LLM    ( 50)
            sample_items = location_items[:50]
            sample_text = '\n\n'.join(sample_items)
            
            # LLM  -    
            prompt = """"
 "{location}"   . 
       .

:
1.    (, , , ,  )
3.   : {len(location_items)}

 :
{sample_text[:8000]}

  :

##  {location}   

###    : {len(location_items)}

###    

**  **

**  ** 

** /**

** /**

** /**

: , (//), (/)  .
""""

            # LLM 
            context = [{'content': sample_text[:8000], 'metadata': {'source': txt_path.name}, 'score': 1.0}]
            response = self.llm.generate_response(prompt, context)
            
            answer = response.answer if hasattr(response, 'answer') else str(response)
            
            if len(location_items) > 50:
                answer += f"\n\n  {len(location_items)}   50  ."
            
            answer += f"\n\n : {txt_path.name}"
            return answer
            
        except Exception as e:
            # LLM    
            response = f" {location}  \n"
            response += "=" * 50 + "\n"
            response += f"   : {result['count']}\n\n"
            
            if result.get('sample_items'):
                response += "   :\n"
                for i, item in enumerate(result['sample_items'][:10], 1):
                    lines = item.split('\n')
                    for line in lines:
                        if '[' in line and ']' in line:
                            response += f"{i}. {line.strip()}\n"
                        elif ':' in line or ':' in line:
                            response += f"   {line.strip()}\n"
                    response += "\n"
            
            response += f" : {txt_path.name}"
            return response

    def _is_location_match(self, item_lines: list, location: str) -> bool:
        """    -   """
        item_text = '\n'.join(item_lines)
        
        #     
        for line in item_lines:
            if ':' in line or ':' in line:
                #   
                location_match = re.search(r':\s*([^|\n]+)', line)
                if location_match:
                    actual_location = location_match.group(1).strip()
                    
                    #   
                    if location == actual_location:
                        #   ( )
                        return True
                    elif location == '':
                        # ''  '*'  
                        return actual_location.endswith('')
                    elif location == '':
                        # ''  '*'   
                        return actual_location.endswith('')
                    elif location == '':
                        # ''  '*'  
                        return actual_location.endswith('')
                    elif location in ['', 'van', 'Van', 'VAN']:
                        #   Van    
                        return 'Van' in actual_location or 'VAN' in actual_location
                    elif location == "":
                        # " "    
                        return "" in actual_location and "" in actual_location
                    elif len(location) > 3:
                        # 3      
                        return location in actual_location
        
        return False

    def _search_location_equipment_combo(self, txt_path: Path, query: str) -> str:
        """ +    (:  CCU)"""
        try:
            #    
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            #    (  )
            equipment_keywords = ["CCU", "", "", "", "", "", "", ""]
            found_equipment = None
            query_upper = query.upper()
            for eq in equipment_keywords:
                if eq.upper() in query_upper:
                    found_equipment = eq
                    break
            
            if not found_equipment:
                #       
                found_equipment = query  #    
            
            #   
            location_pattern = r'[-]{2,}(?:||||||||||)||van|Van|VAN'
            locations = re.findall(location_pattern, query, re.IGNORECASE)
            
            if is_all_locations and not locations:
                return self._search_equipment_all_locations(txt_path, found_equipment)
            
            if not locations and not is_all_locations:
                return "     ."
            
            found_location = locations[0] if locations else None
            
            #   -  [NNNN]  
            lines = content.split('\n')
            matching_items = []
            current_item = []
            
            for line in lines:
                # [NNNN]    
                if re.match(r'^\[\d{4}\]', line.strip()):
                    #   
                    if current_item:
                        item_text = '\n'.join(current_item)
                        #   
                        location_match = self._check_location_in_item(item_text, found_location)
                        #    - CCU  "Camera Control Unit" 
                        if found_equipment.upper() == "CCU":
                            equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                        else:
                            equipment_match = found_equipment.upper() in item_text.upper()
                        
                        if location_match and equipment_match:
                            matching_items.append(item_text)
                    
                    current_item = [line]
                else:
                    if current_item:  #     
                        current_item.append(line)
            
            #   
            if current_item:
                item_text = '\n'.join(current_item)
                location_match = self._check_location_in_item(item_text, found_location)
                #    - CCU  "Camera Control Unit" 
                if found_equipment == "CCU":
                    equipment_match = "CCU" in item_text or "Camera Control Unit" in item_text
                else:
                    equipment_match = found_equipment in item_text
                
                if location_match and equipment_match:
                    matching_items.append(item_text)
            
            if not matching_items:
                return f" {found_location} {found_equipment}    ."
            
            #  
            response = f" {found_location} {found_equipment} \n"
            response += "=" * 60 + "\n"
            response += f"  {len(matching_items)}\n\n"
            
            #  
            for i, item in enumerate(matching_items, 1):
                response += f"[{i}] "
                lines = item.split('\n')
                
                #  
                title_line = lines[0] if lines else ""
                response += title_line.replace('[', '').replace(']', '').strip() + "\n"
                
                #   
                for line in lines[1:]:
                    if ':' in line or ':' in line or ':' in line:
                        response += f"  {line.strip()}\n"
                
                response += "\n"
            
            response += f" : {txt_path.name}"
            return response
            
        except Exception as e:
            return f"  : {e}"
    
    def _search_location_all_equipment(self, txt_path: Path, query: str) -> str:
        """     """
        try:
            #    
            if complete_path.exists():
                txt_path = complete_path
            
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            #   
            location_keyword = None
            if '' in query:
                location_keyword = ''
            else:
                #    
                location_pattern = r'[-]{2,}(?:||||||||||)'
                locations = re.findall(location_pattern, query)
                if locations:
                    location_keyword = locations[0]
            
            if not location_keyword:
                return "   ."
            
            #  
            lines = content.split('\n')
            matching_items = []
            current_item = []
            
            for line in lines:
                # [NNNN]   
                if re.match(r'^\[\d{4}\]', line.strip()):
                    #   
                    if current_item:
                        item_text = '\n'.join(current_item)
                        #  
                        if self._check_location_in_item(item_text, location_keyword):
                            matching_items.append(item_text)
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            #   
            if current_item:
                item_text = '\n'.join(current_item)
                if self._check_location_in_item(item_text, location_keyword):
                    matching_items.append(item_text)
            
            if not matching_items:
                return f" {location_keyword}  ."
            
            #   -   
            response = f" {location_keyword}  \n"
            response += "=" * 70 + "\n"
            response += f"  {len(matching_items)} \n\n"
            
            #  
            categories = {}
            for item in matching_items:
                #   ()
                cat_match = re.search(r':\s*([^|]+)', item)
                if cat_match:
                    cat = cat_match.group(1).strip().split()[0] if cat_match.group(1).strip() else ""
                else:
                    cat = ""
                
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(item)
            
            #  
            response += "   :\n"
            for cat, items in sorted(categories.items()):
                response += f"   {cat}: {len(items)}\n"
            response += "\n" + "-" * 70 + "\n\n"
            
            #   
            total_value = 0
            for item in matching_items:
                amount_match = re.search(r':\s*([\d,]+)', item)
                if amount_match:
                    amount_str = amount_match.group(1).replace(',', '')
                    try:
                        total_value += int(amount_str)
                    except Exception as e:
                        pass
            
            if total_value > 0:
                #   
                value_in_billions = total_value / 100000000
            
            #   (30 )
            response += " **  ** ( 30):\n\n"
            
            #     (30 )
            display_items = matching_items[:30] if len(matching_items) > 30 else matching_items
            
            for i, item in enumerate(display_items, 1):
                lines = item.split('\n')
                
                #  
                title_match = re.match(r'^\[(\d{4})\]\s*(.+)', lines[0])
                if title_match:
                    item_no = title_match.group(1)
                    item_name = title_match.group(2)
                    response += f"[{i}] [{item_no}] {item_name}\n"
                
                #    
                item_info = {}
                
                #   
                for line in lines[1:]:
                    if ':' in line:
                        info_match = re.search(r':\s*(.+?)(?:\||$)', line)
                        if info_match:
                            basic_info = info_match.group(1).strip()
                            #   
                            parts = basic_info.split()
                            if len(parts) >= 2:
                                item_info['model'] = parts[0]
                                item_info['manufacturer'] = parts[1] if len(parts) > 1 else ''
                            response += f"     : {basic_info}\n"
                    elif ':' in line:
                        loc_match = re.search(r':\s*([^|]+)', line)
                        if loc_match:
                            item_info['location'] = loc_match.group(1).strip()
                            response += f"     : {item_info['location']}\n"
                    elif ':' in line:
                        #    
                        mgmt_full = line.split(':')[1] if ':' in line else ''
                        mgmt_parts = mgmt_full.split('|')
                        
                        for part in mgmt_parts:
                            part = part.strip()
                            if ':' in part:
                                manager = part.replace(':', '').strip()
                                if manager:
                                    response += f"     : {manager}\n"
                        #    
                        purchase_full = line.split(':')[1] if ':' in line else ''
                        purchase_parts = purchase_full.split('|')
                        
                        for part in purchase_parts:
                            part = part.strip()
                            if ':' in part:
                                purchase_date = part.replace(':', '').strip()
                                if purchase_date:
                                    response += f"     : {purchase_date}\n"
                            elif ':' in part:
                                amount = part.replace(':', '').strip()
                                if amount and amount != '0':
                                    response += f"     : {amount}\n"
                            elif '' in part and '' not in part:
                                #    
                                if part.strip() and part.strip() != '0':
                                    response += f"     : {part.strip()}\n"
                
                response += "\n"
            
            if len(matching_items) > len(display_items):
                response += f"\n...  {len(matching_items) - len(display_items)}   \n"
            
            response += f"\n : {txt_path.name}"
            
            # LLM  
            if self.llm and len(matching_items) > 0:
                try:
                    #  
                        raw_data=response,
                        query=query,
                        llm=self.llm
                    )
                    
                    if enhanced_response and len(enhanced_response) > len(response):
                        return enhanced_response
                except Exception as e:
                    #   
            
            return response
            
        except Exception as e:
            return f"  : {e}"
    
    def _search_equipment_all_locations(self, txt_path: Path, equipment: str) -> str:
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            #  
            lines = content.split('\n')
            location_equipment = {}  # {: [ ]}
            current_item = []
            
            for line in lines:
                # [NNNN]    
                if re.match(r'^\[\d{4}\]', line.strip()):
                    #   
                    if current_item:
                        item_text = '\n'.join(current_item)
                        #   
                        if equipment.upper() == "CCU":
                            equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                        else:
                            equipment_match = equipment.upper() in item_text.upper()
                        
                        if equipment_match:
                            #  
                            location_info = None
                            for item_line in current_item:
                                if ":" in item_line:
                                    # :   
                                    match = re.search(r':\s*([^|]+)', item_line)
                                    if match:
                                        location_info = match.group(1).strip()
                                        break
                            
                            if location_info:
                                if location_info not in location_equipment:
                                    location_equipment[location_info] = []
                                #    ( )
                                location_equipment[location_info].append(current_item[0])
                    
                    current_item = [line]
                else:
                    if current_item:
                        current_item.append(line)
            
            #   
            if current_item:
                item_text = '\n'.join(current_item)
                if equipment.upper() == "CCU":
                    equipment_match = "CCU" in item_text.upper() or "Camera Control Unit" in item_text
                else:
                    equipment_match = equipment.upper() in item_text.upper()
                
                if equipment_match:
                    location_info = None
                    for item_line in current_item:
                        if ":" in item_line:
                            match = re.search(r':\s*([^|]+)', item_line)
                            if match:
                                location_info = match.group(1).strip()
                                break
                    
                    if location_info:
                        if location_info not in location_equipment:
                            location_equipment[location_info] = []
                        location_equipment[location_info].append(current_item[0])
            
            #  
            if location_equipment:
                total_count = sum(len(items) for items in location_equipment.values())
                response += "=" * 70 + "\n"
                response += f"  {total_count}  {len(location_equipment)}  \n\n"
                
                sorted_locations = sorted(location_equipment.items(), key=lambda x: len(x[1]), reverse=True)
                
                for location, items in sorted_locations:
                    response += f" **{location}**: {len(items)}\n"
                    #  3 
                    for i, item in enumerate(items[:3], 1):
                        response += f"   {i}. {item}\n"
                    if len(items) > 3:
                        response += f"   ...  {len(items)-3}\n"
                    response += "\n"
                
                response += f" : {txt_path.name}"
                return response
            else:
                return f" {equipment.upper()}    ."
                
        except Exception as e:
            return f"  : {e}"

    def _check_location_in_item(self, item_text: str, search_location: str) -> bool:
        """   """
        #   
        location_match = re.search(r':\s*([^|\n]+)', item_text)
        if not location_match:
            return False
            
        actual_location = location_match.group(1).strip()
        
        #    
        if search_location == actual_location:
            return True
        elif search_location == '':
            return actual_location.endswith('')
        elif search_location == '':
            return actual_location.endswith('')
        elif search_location == '':
            return actual_location.endswith('')
        elif search_location in ['', 'van', 'Van', 'VAN']:
            return 'Van' in actual_location or 'VAN' in actual_location or '' in actual_location
        elif len(search_location) > 3:
            return search_location in actual_location
        
        return False

def main():
    """  """
    print("=" * 60)
    print(" Perfect RAG -    ")
    print("=" * 60)
    
    #  
    rag = PerfectRAG()
    
    #  
    test_queries = [
        "2024      ?",
        "     ?",
        "     ?",
        "2021    ?",
        "     ",
    ]
    
    print("\n  ")
    print("=" * 60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n {i}: {query}")
        print("-" * 40)
        answer = rag.answer(query)
        print(answer)
        print("-" * 40)
        
        #   (input )
    
    print("\n" + "=" * 60)
    print("  !")
    print("=" * 60)

if __name__ == "__main__":
    main()