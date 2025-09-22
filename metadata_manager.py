#!/usr/bin/env python3
"""
문서 메타데이터 관리 시스템
- JSON 기반 경량 DB
- 빠른 검색 지원
- 자동 업데이트 기능
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
import re
from datetime import datetime
import threading
import hashlib
from collections import defaultdict
import time
import os
from functools import lru_cache
import fcntl  # For file locking on Unix systems

logger = logging.getLogger(__name__)

class MetadataManager:
    # 상수 정의
    DEFAULT_DB_PATH = "document_metadata.json"
    DEFAULT_CACHE_TTL = 300  # 5분
    AUTO_SAVE_INTERVAL = 10  # 10초마다 자동 저장
    NAME_MIN_LENGTH = 2
    NAME_MAX_LENGTH = 4

    def __init__(self, db_path: str = None, cache_ttl: int = None):
        self.db_path = Path(db_path) if db_path else Path(self.DEFAULT_DB_PATH)
        self.cache_ttl = cache_ttl if cache_ttl is not None else self.DEFAULT_CACHE_TTL

        # Performance optimization
        self.metadata = self.load_metadata()
        self._last_load_time = time.time()
        self._cache = {}  # Query result cache
        self._index = self._build_indexes()  # Build indexes for fast search

        # Thread safety
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()

        # Change tracking
        self._dirty = False  # Track if data needs saving
        self._last_save_time = time.time()

        # Performance metrics
        self._search_count = 0
        self._cache_hits = 0
        self._save_count = 0

        # Compile patterns
        self._compile_patterns()

    def load_metadata(self) -> Dict:
        """메타데이터 DB 로드 - 에러 처리 및 백업 지원"""
        if not self.db_path.exists():
            return {}

        try:
            # 파일 잠금으로 동시 접근 방지
            with open(self.db_path, 'r', encoding='utf-8') as f:
                try:
                    # Unix 시스템에서 파일 잠금
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    data = json.load(f)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    return data
                except (ImportError, AttributeError):
                    # Windows 또는 fcntl 없는 환경
                    return json.load(f)
        except json.JSONDecodeError as e:
            # 손상된 JSON 처리
            logger.warning(f"메타데이터 파일 손상 감지: {e}")
            backup_path = self.db_path.with_suffix('.backup')
            if backup_path.exists():
                logger.info("백업 파일에서 복구 시도...")
                with open(backup_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"메타데이터 로드 실패: {e}")
            return {}

    def save_metadata(self, force: bool = False):
        """메타데이터 DB 저장 - 백업 및 원자적 쓰기"""
        if not self._dirty and not force:
            return  # 변경사항이 없으면 저장 스킵

        with self._write_lock:
            try:
                # 기존 파일 백업
                if self.db_path.exists():
                    backup_path = self.db_path.with_suffix('.backup')
                    self.db_path.rename(backup_path)

                # 임시 파일에 먼저 쓰기 (원자적 쓰기)
                temp_path = self.db_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.metadata, f, ensure_ascii=False, indent=2)

                # 원자적 이동
                temp_path.rename(self.db_path)

                self._dirty = False
                self._last_save_time = time.time()
                self._save_count += 1

            except Exception as e:
                logger.error(f"메타데이터 저장 실패: {e}")
                # 백업에서 복구
                backup_path = self.db_path.with_suffix('.backup')
                if backup_path.exists():
                    backup_path.rename(self.db_path)
                raise

    def add_document(self, filename: str, **kwargs):
        """문서 메타데이터 추가/업데이트 - 검증 및 인덱싱"""
        with self._lock:
            # 입력 검증
            kwargs = self._validate_metadata(kwargs)

            if filename not in self.metadata:
                self.metadata[filename] = {}

            # 변경 사항 추적
            old_data = self.metadata[filename].copy()

            # 기본 정보 추가
            self.metadata[filename].update(kwargs)
            self.metadata[filename]['last_updated'] = datetime.now().isoformat()

            # 인덱스 업데이트
            self._update_indexes(filename, old_data, self.metadata[filename])

            # 변경 플래그 설정
            self._dirty = True

            # 캐시 무효화
            self._invalidate_cache()

            # 자동 저장 (배치 처리를 위해 지연)
            if time.time() - self._last_save_time > self.AUTO_SAVE_INTERVAL:
                self.save_metadata()

    def get_document(self, filename: str) -> Optional[Dict]:
        """문서 메타데이터 조회"""
        return self.metadata.get(filename)

    def search_by_drafter(self, drafter_name: str, fuzzy: bool = True) -> List[str]:
        """기안자로 검색 - 인덱스 기반 빠른 검색"""
        self._search_count += 1

        # 캐시 확인
        cache_key = f"drafter:{drafter_name}:{fuzzy}"
        if cache_key in self._cache:
            cache_time, results = self._cache[cache_key]
            if time.time() - cache_time < self.cache_ttl:
                self._cache_hits += 1
                return results

        with self._lock:
            results = set()

            # 인덱스 사용
            if 'drafter' in self._index:
                # 정확한 매칭
                if drafter_name in self._index['drafter']:
                    results.update(self._index['drafter'][drafter_name])

                # 퍼지 매칭
                if fuzzy:
                    for indexed_name, files in self._index['drafter'].items():
                        if drafter_name.lower() in indexed_name.lower() or \
                           indexed_name.lower() in drafter_name.lower():
                            results.update(files)

            results = list(results)
            # 캐시 저장
            self._cache[cache_key] = (time.time(), results)
            return results

    def search_by_field(self, field: str, value: str, fuzzy: bool = True) -> List[str]:
        """특정 필드로 검색 - 인덱스 기반"""
        self._search_count += 1

        # 캐시 확인
        cache_key = f"field:{field}:{value}:{fuzzy}"
        if cache_key in self._cache:
            cache_time, results = self._cache[cache_key]
            if time.time() - cache_time < self.cache_ttl:
                self._cache_hits += 1
                return results

        with self._lock:
            results = set()

            # 인덱스 사용
            if field in self._index:
                # 정확한 매칭
                if value in self._index[field]:
                    results.update(self._index[field][value])

                # 퍼지 매칭
                if fuzzy:
                    value_lower = value.lower()
                    for indexed_value, files in self._index[field].items():
                        if value_lower in str(indexed_value).lower():
                            results.update(files)

            results = list(results)
            # 캐시 저장
            self._cache[cache_key] = (time.time(), results)
            return results

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        self._patterns = {
            'drafter': [
                re.compile(r'기안자[\s:：]*([가-힣]{2,4})'),
                re.compile(r'작성자[\s:：]*([가-힣]{2,4})'),
                re.compile(r'담당자[\s:：]*([가-힣]{2,4})')
            ],
            'department': [
                re.compile(r'기안부서[\s:：]*([^\n]+)'),
                re.compile(r'부서[\s:：]*([^\n]+)'),
                re.compile(r'소속[\s:：]*([^\n]+)')
            ],
            'date': [
                re.compile(r'기안일자[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})'),
                re.compile(r'작성일[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})'),
                re.compile(r'날짜[\s:：]*(\d{4}[-./]\d{1,2}[-./]\d{1,2})')
            ],
            'amount': [
                re.compile(r'금액[\s:：]*([0-9,]+)원'),
                re.compile(r'총액[\s:：]*([0-9,]+)원'),
                re.compile(r'([0-9,]+)원')  # 금액 패턴
            ]
        }

        # 검증 패턴도 컴파일
        self._name_pattern = re.compile(f'^[가-힣]{{{self.NAME_MIN_LENGTH},{self.NAME_MAX_LENGTH}}}$')
        self._date_pattern = re.compile(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}')

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """텍스트에서 메타데이터 자동 추출 (컴파일된 패턴 사용)"""
        metadata = {}

        # 컴파일된 패턴으로 추출
        for field, pattern_list in self._patterns.items():
            for pattern in pattern_list:
                match = pattern.search(text)
                if match:
                    metadata[field] = match.group(1).strip()
                    break

        # 문서 타입 자동 분류
        if '긴급' in text:
            metadata['priority'] = 'high'
        elif '검토' in text:
            metadata['type'] = '검토서'
        elif '구매' in text:
            metadata['type'] = '구매기안'
        elif '수리' in text or '보수' in text:
            metadata['type'] = '수리/보수'

        return metadata

    def _build_indexes(self) -> Dict[str, Dict[str, Set[str]]]:
        """빠른 검색을 위한 인덱스 구축"""
        indexes = defaultdict(lambda: defaultdict(set))

        for filename, data in self.metadata.items():
            for field, value in data.items():
                if field not in ['last_updated']:  # 인덱싱 제외 필드
                    indexes[field][str(value)].add(filename)

        return indexes

    def _update_indexes(self, filename: str, old_data: Dict, new_data: Dict):
        """인덱스 업데이트"""
        # 기존 인덱스에서 제거
        for field, value in old_data.items():
            if field in self._index and str(value) in self._index[field]:
                self._index[field][str(value)].discard(filename)

        # 새 인덱스 추가
        for field, value in new_data.items():
            if field not in ['last_updated']:
                if field not in self._index:
                    self._index[field] = defaultdict(set)
                self._index[field][str(value)].add(filename)

    def _validate_metadata(self, metadata: Dict) -> Dict:
        """메타데이터 검증 및 정규화"""
        validated = {}

        for key, value in metadata.items():
            # 기본 검증
            if value is None or (isinstance(value, str) and not value.strip()):
                continue

            # 타입별 검증 (컴파일된 패턴 사용)
            if key == 'drafter':
                # 이름 검증 (2-4자 한글)
                if isinstance(value, str) and self._name_pattern.match(value):
                    validated[key] = value.strip()
            elif key == 'amount':
                # 금액 정규화
                if isinstance(value, (str, int)):
                    amount_str = str(value).replace(',', '')
                    if amount_str.isdigit():
                        validated[key] = int(amount_str)
            elif key == 'date':
                # 날짜 형식 검증
                if isinstance(value, str):
                    date_match = self._date_pattern.match(value)
                    if date_match:
                        validated[key] = date_match.group()
            else:
                validated[key] = value

        return validated

    def _invalidate_cache(self, pattern: Optional[str] = None):
        """캐시 무효화"""
        if pattern:
            # 특정 패턴만 무효화
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            # 전체 캐시 무효화
            self._cache.clear()

    def multi_field_search(self, criteria: Dict[str, str], operator: str = 'AND') -> List[str]:
        """다중 필드 검색"""
        results_sets = []

        for field, value in criteria.items():
            field_results = set(self.search_by_field(field, value))
            results_sets.append(field_results)

        if not results_sets:
            return []

        if operator.upper() == 'AND':
            # 교집합
            result_set = results_sets[0]
            for s in results_sets[1:]:
                result_set = result_set.intersection(s)
        else:  # OR
            # 합집합
            result_set = results_sets[0]
            for s in results_sets[1:]:
                result_set = result_set.union(s)

        return list(result_set)

    def bulk_update(self, updates: Dict[str, Dict]):
        """대량 업데이트 - 성능 최적화"""
        with self._lock:
            for filename, metadata in updates.items():
                if filename not in self.metadata:
                    self.metadata[filename] = {}

                old_data = self.metadata[filename].copy()
                validated = self._validate_metadata(metadata)

                self.metadata[filename].update(validated)
                self.metadata[filename]['last_updated'] = datetime.now().isoformat()

                self._update_indexes(filename, old_data, self.metadata[filename])

            self._dirty = True
            self._invalidate_cache()
            self.save_metadata(force=True)  # 대량 업데이트는 즉시 저장

    def get_statistics(self) -> Dict:
        """전체 통계"""
        stats = {
            'total_documents': len(self.metadata),
            'documents_with_drafter': 0,
            'documents_with_amount': 0,
            'drafters': {},
            'departments': {},
            'types': {}
        }

        for filename, data in self.metadata.items():
            if data.get('drafter'):
                stats['documents_with_drafter'] += 1
                drafter = data['drafter']
                stats['drafters'][drafter] = stats['drafters'].get(drafter, 0) + 1

            if data.get('amount'):
                stats['documents_with_amount'] += 1

            if data.get('department'):
                dept = data['department']
                stats['departments'][dept] = stats['departments'].get(dept, 0) + 1

            if data.get('type'):
                doc_type = data['type']
                stats['types'][doc_type] = stats['types'].get(doc_type, 0) + 1

        return stats

    def get_performance_stats(self) -> Dict[str, Any]:
        """성능 통계 반환"""
        cache_hit_rate = (self._cache_hits / self._search_count * 100
                         if self._search_count > 0 else 0)

        return {
            'search_count': self._search_count,
            'cache_hits': self._cache_hits,
            'cache_hit_rate': cache_hit_rate,
            'save_count': self._save_count,
            'cache_size': len(self._cache),
            'index_size': sum(len(idx) for idx in self._index.values())
        }


# 테스트 및 초기 데이터
if __name__ == "__main__":
    manager = MetadataManager()

    # 샘플 데이터 추가 (실제 문서 기반)
    sample_data = [
        {
            "filename": "2025-03-20_채널에이_중계차_카메라_노후화_장애_긴급_보수건.pdf",
            "drafter": "최새름",
            "department": "기술관리팀-보도기술관리파트",
            "type": "긴급보수",
            "amount": "2,446,000",
            "priority": "high"
        },
        {
            "filename": "2025-01-14_채널A_불용_방송_장비_폐기_요청의_건.pdf",
            "drafter": "남준수",
            "department": "기술관리팀",
            "type": "폐기요청",
            "date": "2025-01-14"
        },
        {
            "filename": "2023-12-06_오픈스튜디오_무선마이크_수신_장애_조치_기안서.pdf",
            "drafter": "최새름",
            "department": "기술관리팀",
            "type": "장애조치",
            "date": "2023-12-06"
        },
        {
            "filename": "2023-11-02_영상취재팀_트라이포드_수리_건.pdf",
            "drafter": "유인혁",
            "department": "영상취재팀",
            "type": "수리/보수",
            "date": "2023-11-02"
        },
        {
            "filename": "2024-11-14_뉴스_스튜디오_지미집_Control_Box_수리_건.pdf",
            "drafter": "남준수",
            "department": "기술관리팀",
            "type": "수리/보수",
            "date": "2024-11-14"
        },
        {
            "filename": "2019-05-31_Audio_Patch_Cable_구매.pdf",
            "drafter": "유인혁",
            "department": "기술관리팀",
            "type": "구매기안",
            "date": "2019-05-31"
        }
    ]

    # 데이터 추가
    for data in sample_data:
        filename = data.pop('filename')
        manager.add_document(filename, **data)

    logger.info("메타데이터 DB 생성 완료!")
    logger.info(f"총 {len(manager.metadata)}개 문서 정보 저장")

    # 통계 출력
    stats = manager.get_statistics()
    print("\n📈 통계:")
    print(f"  - 기안자 정보 있는 문서: {stats['documents_with_drafter']}개")
    print(f"  - 금액 정보 있는 문서: {stats['documents_with_amount']}개")

    print("\n👥 기안자별 문서:")
    for drafter, count in stats['drafters'].items():
        print(f"  - {drafter}: {count}개")

    # 테스트 검색
    print("\n🔍 최새름 기안자 문서 검색:")
    results = manager.search_by_drafter("최새름")
    for doc in results:
        print(f"  - {doc}")

    # 성능 통계 출력
    perf_stats = manager.get_performance_stats()
    print("\n⚡ 성능 통계:")
    print(f"  - 검색 횟수: {perf_stats['search_count']}")
    print(f"  - 캐시 히트율: {perf_stats['cache_hit_rate']:.1f}%")