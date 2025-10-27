#!/usr/bin/env python3
"""
from app.core.logging import get_logger
캐시 관리 모듈 - Perfect RAG에서 분리된 캐시 관련 기능
2025-09-29 리팩토링

이 모듈은 LRU 캐시, TTL 관리, 다중 캐시 시스템 등
캐싱 관련 기능을 담당합니다.
"""

import os
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from collections import OrderedDict
import pickle

logger = get_logger(__name__)


class CacheModule:
    """캐시 관리 통합 모듈"""

    def __init__(self, config: Dict = None):
        """
        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}

        # 캐시 설정
        self.max_cache_size = self.config.get('max_cache_size', 100)
        self.max_metadata_cache = self.config.get('max_metadata_cache', 500)
        self.max_pdf_cache = self.config.get('max_pdf_cache', 50)
        self.cache_ttl = self.config.get('cache_ttl', 3600)  # 1시간

        # 캐시 디렉토리
        self.cache_dir = Path(self.config.get('cache_dir', './cache'))
        self.cache_dir.mkdir(exist_ok=True)

        # 캐시 인스턴스들
        self.documents_cache = OrderedDict()  # 문서 캐시
        self.metadata_cache = OrderedDict()   # 메타데이터 캐시
        self.answer_cache = OrderedDict()     # 응답 캐시
        self.pdf_text_cache = OrderedDict()   # PDF 텍스트 캐시
        self.search_cache = OrderedDict()     # 검색 결과 캐시

        # 통계
        self.cache_hits = 0
        self.cache_misses = 0

        # 캐시 파일 경로
        self.cache_file = self.cache_dir / 'cache_state.pkl'

        # 캐시 로드
        self.load_cache_from_disk()

    def manage_cache(self, cache_dict: OrderedDict, key: str, value: Any,
                    max_size: Optional[int] = None) -> None:
        """
        캐시 크기 관리 - LRU 방식

        Args:
            cache_dict: 관리할 캐시 딕셔너리
            key: 캐시 키
            value: 저장할 값
            max_size: 최대 크기 (기본값: self.max_cache_size)
        """
        if max_size is None:
            max_size = self.max_cache_size

        if key in cache_dict:
            # 기존 항목을 끝으로 이동 (가장 최근 사용)
            cache_dict.move_to_end(key)
        else:
            # 새 항목 추가
            if len(cache_dict) >= max_size:
                # 가장 오래된 항목 제거
                removed_key = cache_dict.popitem(last=False)[0]
                logger.debug(f"캐시 제거 (LRU): {removed_key}")

        # 값과 타임스탬프 저장
        cache_dict[key] = (value, time.time())

    def get_from_cache(self, cache_dict: OrderedDict, key: str) -> Optional[Any]:
        """
        캐시에서 가져오기 (TTL 체크 및 타임스탬프 갱신)

        Args:
            cache_dict: 캐시 딕셔너리
            key: 캐시 키

        Returns:
            캐시된 값 또는 None
        """
        if key in cache_dict:
            cache_value = cache_dict[key]
            current_time = time.time()

            # 튜플 형식 (value, timestamp) 체크
            if isinstance(cache_value, tuple) and len(cache_value) == 2:
                value, timestamp = cache_value

                if current_time - timestamp < self.cache_ttl:
                    # LRU: 사용한 항목을 끝으로 이동
                    cache_dict.move_to_end(key)
                    # 타임스탬프 갱신 (사용 시간 연장)
                    cache_dict[key] = (value, current_time)
                    self.cache_hits += 1
                    return value
                else:
                    # TTL 만료 - 삭제
                    del cache_dict[key]
                    logger.debug(f"캐시 만료: {key}")
                    self.cache_misses += 1
                    return None
            else:
                # 이전 형식 호환 (튜플 아닌 경우)
                cache_dict.move_to_end(key)
                self.cache_hits += 1
                return cache_value

        self.cache_misses += 1
        return None

    def set_document_cache(self, key: str, value: Any) -> None:
        """문서 캐시에 저장"""
        self.manage_cache(self.documents_cache, key, value, self.max_cache_size)

    def get_document_cache(self, key: str) -> Optional[Any]:
        """문서 캐시에서 가져오기"""
        return self.get_from_cache(self.documents_cache, key)

    def set_metadata_cache(self, key: str, value: Any) -> None:
        """메타데이터 캐시에 저장"""
        self.manage_cache(self.metadata_cache, key, value, self.max_metadata_cache)

    def get_metadata_cache(self, key: str) -> Optional[Any]:
        """메타데이터 캐시에서 가져오기"""
        return self.get_from_cache(self.metadata_cache, key)

    def set_answer_cache(self, query: str, answer: str) -> None:
        """응답 캐시에 저장"""
        self.manage_cache(self.answer_cache, query, answer, self.max_cache_size)

    def get_answer_cache(self, query: str) -> Optional[str]:
        """응답 캐시에서 가져오기"""
        return self.get_from_cache(self.answer_cache, query)

    def set_pdf_cache(self, pdf_path: str, text_data: Dict) -> None:
        """PDF 텍스트 캐시에 저장"""
        self.manage_cache(self.pdf_text_cache, pdf_path, text_data, self.max_pdf_cache)

    def get_pdf_cache(self, pdf_path: str) -> Optional[Dict]:
        """PDF 텍스트 캐시에서 가져오기"""
        return self.get_from_cache(self.pdf_text_cache, pdf_path)

    def set_search_cache(self, query: str, results: List) -> None:
        """검색 결과 캐시에 저장"""
        self.manage_cache(self.search_cache, query, results, self.max_cache_size)

    def get_search_cache(self, query: str) -> Optional[List]:
        """검색 결과 캐시에서 가져오기"""
        return self.get_from_cache(self.search_cache, query)

    def clear_all_cache(self) -> None:
        """모든 캐시 초기화"""
        self.documents_cache.clear()
        self.metadata_cache.clear()
        self.answer_cache.clear()
        self.pdf_text_cache.clear()
        self.search_cache.clear()

        # 통계 초기화
        self.cache_hits = 0
        self.cache_misses = 0

        logger.info("♻️ 모든 캐시가 초기화되었습니다.")

    def clear_cache(self, cache_type: str = 'all') -> None:
        """
        특정 캐시 초기화

        Args:
            cache_type: 'documents', 'metadata', 'answer', 'pdf', 'search', 'all'
        """
        if cache_type == 'all':
            self.clear_all_cache()
        elif cache_type == 'documents':
            self.documents_cache.clear()
        elif cache_type == 'metadata':
            self.metadata_cache.clear()
        elif cache_type == 'answer':
            self.answer_cache.clear()
        elif cache_type == 'pdf':
            self.pdf_text_cache.clear()
        elif cache_type == 'search':
            self.search_cache.clear()
        else:
            logger.warning(f"Unknown cache type: {cache_type}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 상태 정보 반환"""
        total_size = (
            len(self.documents_cache) +
            len(self.metadata_cache) +
            len(self.answer_cache) +
            len(self.pdf_text_cache) +
            len(self.search_cache)
        )

        hit_rate = 0
        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses)

        return {
            'total_size': total_size,
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': f"{hit_rate:.2%}",
            'document_cache_size': len(self.documents_cache),
            'metadata_cache_size': len(self.metadata_cache),
            'answer_cache_size': len(self.answer_cache),
            'pdf_cache_size': len(self.pdf_text_cache),
            'search_cache_size': len(self.search_cache),
            'ttl': self.cache_ttl,
            'max_sizes': {
                'cache': self.max_cache_size,
                'metadata': self.max_metadata_cache,
                'pdf': self.max_pdf_cache
            }
        }

    def save_cache_to_disk(self) -> bool:
        """
        캐시를 디스크에 저장

        Returns:
            성공 여부
        """
        try:
            cache_data = {
                'documents': dict(self.documents_cache),
                'metadata': dict(self.metadata_cache),
                'answer': dict(self.answer_cache),
                'pdf': dict(self.pdf_text_cache),
                'search': dict(self.search_cache),
                'stats': {
                    'hits': self.cache_hits,
                    'misses': self.cache_misses,
                    'saved_at': time.time()
                }
            }

            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)

            logger.info(f"💾 캐시 저장 완료: {self.cache_file}")
            return True

        except Exception as e:
            logger.error(f"캐시 저장 실패: {e}")
            return False

    def load_cache_from_disk(self) -> bool:
        """
        디스크에서 캐시 로드

        Returns:
            성공 여부
        """
        if not self.cache_file.exists():
            logger.info("캐시 파일이 없습니다. 새로 시작합니다.")
            return False

        try:
            with open(self.cache_file, 'rb') as f:
                cache_data = pickle.load(f)

            # 캐시 복원
            self.documents_cache = OrderedDict(cache_data.get('documents', {}))
            self.metadata_cache = OrderedDict(cache_data.get('metadata', {}))
            self.answer_cache = OrderedDict(cache_data.get('answer', {}))
            self.pdf_text_cache = OrderedDict(cache_data.get('pdf', {}))
            self.search_cache = OrderedDict(cache_data.get('search', {}))

            # 통계 복원
            stats = cache_data.get('stats', {})
            self.cache_hits = stats.get('hits', 0)
            self.cache_misses = stats.get('misses', 0)

            # TTL 체크 및 만료 항목 제거
            self._cleanup_expired_items()

            logger.info(f"📂 캐시 로드 완료: {self.cache_file}")
            return True

        except Exception as e:
            logger.error(f"캐시 로드 실패: {e}")
            return False

    def _cleanup_expired_items(self) -> int:
        """
        만료된 캐시 항목 제거

        Returns:
            제거된 항목 수
        """
        current_time = time.time()
        removed_count = 0

        for cache_dict in [
            self.documents_cache,
            self.metadata_cache,
            self.answer_cache,
            self.pdf_text_cache,
            self.search_cache
        ]:
            expired_keys = []
            for key, value in cache_dict.items():
                if isinstance(value, tuple) and len(value) == 2:
                    _, timestamp = value
                    if current_time - timestamp >= self.cache_ttl:
                        expired_keys.append(key)

            for key in expired_keys:
                del cache_dict[key]
                removed_count += 1

        if removed_count > 0:
            logger.info(f"🧹 만료된 캐시 {removed_count}개 제거")

        return removed_count

    def optimize_cache(self) -> Dict[str, int]:
        """
        캐시 최적화 (만료 항목 제거, 크기 조정)

        Returns:
            최적화 결과
        """
        stats = {
            'expired_removed': self._cleanup_expired_items(),
            'before_size': sum(len(c) for c in [
                self.documents_cache, self.metadata_cache,
                self.answer_cache, self.pdf_text_cache, self.search_cache
            ])
        }

        # 크기 초과 항목 제거 (LRU)
        for cache_dict, max_size in [
            (self.documents_cache, self.max_cache_size),
            (self.metadata_cache, self.max_metadata_cache),
            (self.answer_cache, self.max_cache_size),
            (self.pdf_text_cache, self.max_pdf_cache),
            (self.search_cache, self.max_cache_size)
        ]:
            while len(cache_dict) > max_size:
                cache_dict.popitem(last=False)

        stats['after_size'] = sum(len(c) for c in [
            self.documents_cache, self.metadata_cache,
            self.answer_cache, self.pdf_text_cache, self.search_cache
        ])

        stats['removed_total'] = stats['before_size'] - stats['after_size']

        logger.info(f"✨ 캐시 최적화 완료: {stats['removed_total']}개 항목 제거")

        return stats