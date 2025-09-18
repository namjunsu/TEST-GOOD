"""
장비 자산 데이터 캐싱 및 인덱싱 모듈
"""
import json
import pickle
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import re
from collections import defaultdict

class AssetCache:
    """장비 자산 데이터 캐싱 클래스"""
    
    def __init__(self, cache_dir: str = "cache/assets"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 메모리 캐시
        self._memory_cache = {}
        self._index_cache = {
            'by_location': defaultdict(list),
            'by_manufacturer': defaultdict(list),
            'by_model': defaultdict(list),
            'by_manager': defaultdict(list),
            'by_year': defaultdict(list),
            'by_serial': {}
        }
        self._cache_timestamp = None
        self._cache_ttl = timedelta(hours=1)  # 1시간 캐시
        
    def is_cache_valid(self) -> bool:
        """캐시 유효성 검사"""
        if self._cache_timestamp is None:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_ttl
    
    def load_cache(self, force_reload: bool = False) -> bool:
        """캐시 로드"""
        cache_file = self.cache_dir / "asset_cache.pkl"
        
        if not force_reload and cache_file.exists() and self.is_cache_valid():
            try:
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                    self._memory_cache = data['cache']
                    self._index_cache = data['index']
                    self._cache_timestamp = data['timestamp']
                return True
            except:
                pass
        
        return False
    
    def save_cache(self):
        """캐시 저장"""
        cache_file = self.cache_dir / "asset_cache.pkl"
        
        data = {
            'cache': self._memory_cache,
            'index': self._index_cache,
            'timestamp': datetime.now()
        }
        
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
    
    def build_index(self, asset_data: List[Dict[str, Any]]):
        """자산 데이터 인덱싱"""
        # 인덱스 초기화
        self._index_cache = {
            'by_location': defaultdict(list),
            'by_manufacturer': defaultdict(list),
            'by_model': defaultdict(list),
            'by_manager': defaultdict(list),
            'by_year': defaultdict(list),
            'by_serial': {}
        }
        
        for idx, item in enumerate(asset_data):
            # 위치별 인덱싱
            if '위치' in item:
                location = item['위치'].strip()
                self._index_cache['by_location'][location].append(idx)
                
                # 상위 위치도 인덱싱 (예: "광화문 3층" -> "광화문"도 인덱싱)
                if ' ' in location:
                    main_location = location.split()[0]
                    self._index_cache['by_location'][main_location].append(idx)
            
            # 제조사별 인덱싱
            if '제조사' in item:
                manufacturer = item['제조사'].strip().upper()
                self._index_cache['by_manufacturer'][manufacturer].append(idx)
            
            # 모델별 인덱싱
            if '모델' in item:
                model = item['모델'].strip().upper()
                self._index_cache['by_model'][model].append(idx)
                
                # 모델명 부분 매칭을 위한 추가 인덱싱
                model_parts = re.findall(r'[A-Z]+|\d+', model)
                for part in model_parts:
                    if len(part) > 2:  # 너무 짧은 부분은 제외
                        self._index_cache['by_model'][part].append(idx)
            
            # 담당자별 인덱싱
            if '담당자' in item:
                manager = item['담당자'].strip()
                self._index_cache['by_manager'][manager].append(idx)
            
            # 구입연도별 인덱싱
            if '구입일' in item:
                try:
                    year = str(item['구입일'])[:4]
                    self._index_cache['by_year'][year].append(idx)
                except:
                    pass
            
            # 시리얼번호 인덱싱 (유니크)
            if '시리얼' in item:
                serial = item['시리얼'].strip()
                self._index_cache['by_serial'][serial] = idx
        
        # 메모리 캐시에 저장
        self._memory_cache['asset_data'] = asset_data
        self._cache_timestamp = datetime.now()
        
        # 디스크에 저장
        self.save_cache()
    
    def search_by_location(self, location: str) -> List[Dict[str, Any]]:
        """위치별 검색"""
        if 'asset_data' not in self._memory_cache:
            return []
        
        indices = set()
        location_upper = location.upper()
        
        # 정확한 매칭
        for key in self._index_cache['by_location']:
            if location in key or key in location:
                indices.update(self._index_cache['by_location'][key])
        
        asset_data = self._memory_cache['asset_data']
        return [asset_data[i] for i in indices]
    
    def search_by_manufacturer(self, manufacturer: str) -> List[Dict[str, Any]]:
        """제조사별 검색"""
        if 'asset_data' not in self._memory_cache:
            return []
        
        manufacturer_upper = manufacturer.upper()
        indices = self._index_cache['by_manufacturer'].get(manufacturer_upper, [])
        
        asset_data = self._memory_cache['asset_data']
        return [asset_data[i] for i in indices]
    
    def search_by_model(self, model: str) -> List[Dict[str, Any]]:
        """모델별 검색"""
        if 'asset_data' not in self._memory_cache:
            return []
        
        model_upper = model.upper()
        indices = set()
        
        # 정확한 매칭
        if model_upper in self._index_cache['by_model']:
            indices.update(self._index_cache['by_model'][model_upper])
        
        # 부분 매칭
        for key in self._index_cache['by_model']:
            if model_upper in key or key in model_upper:
                indices.update(self._index_cache['by_model'][key])
        
        asset_data = self._memory_cache['asset_data']
        return [asset_data[i] for i in indices]
    
    def search_by_manager(self, manager: str) -> List[Dict[str, Any]]:
        """담당자별 검색"""
        if 'asset_data' not in self._memory_cache:
            return []
        
        indices = self._index_cache['by_manager'].get(manager, [])
        
        asset_data = self._memory_cache['asset_data']
        return [asset_data[i] for i in indices]
    
    def search_by_year(self, year: str) -> List[Dict[str, Any]]:
        """구입연도별 검색"""
        if 'asset_data' not in self._memory_cache:
            return []
        
        indices = self._index_cache['by_year'].get(str(year), [])
        
        asset_data = self._memory_cache['asset_data']
        return [asset_data[i] for i in indices]
    
    def search_by_serial(self, serial: str) -> Optional[Dict[str, Any]]:
        """시리얼번호로 검색"""
        if 'asset_data' not in self._memory_cache:
            return None
        
        idx = self._index_cache['by_serial'].get(serial)
        if idx is not None:
            return self._memory_cache['asset_data'][idx]
        
        # 부분 매칭 시도
        for key, idx in self._index_cache['by_serial'].items():
            if serial in key or key in serial:
                return self._memory_cache['asset_data'][idx]
        
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        if 'asset_data' not in self._memory_cache:
            return {}
        
        stats = {
            'total_count': len(self._memory_cache['asset_data']),
            'locations': len(self._index_cache['by_location']),
            'manufacturers': len(self._index_cache['by_manufacturer']),
            'models': len(self._index_cache['by_model']),
            'managers': len(self._index_cache['by_manager']),
            'years': len(self._index_cache['by_year']),
            'cache_time': self._cache_timestamp.strftime('%Y-%m-%d %H:%M:%S') if self._cache_timestamp else 'N/A'
        }
        
        return stats