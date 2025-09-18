"""
장비 자산 검색 LLM 답변 개선 모듈
Asset 모드에서 자연스럽고 정리된 답변 생성
"""

import re
from typing import Dict, List, Any, Optional
from pathlib import Path

class AssetLLMEnhancer:
    """장비 자산 검색 결과를 LLM으로 개선하는 클래스"""
    
    def __init__(self, llm=None):
        self.llm = llm
        
    def enhance_asset_response(self, raw_data: str, query: str, llm=None) -> str:
        """날 데이터를 자연스러운 답변으로 변환"""
        
        if llm:
            self.llm = llm
            
        # 사용자 의도 분석
        intent = self._analyze_query_intent(query)
        
        # 데이터 구조화
        structured_data = self._structure_raw_data(raw_data)
        
        # 원본 데이터에서 상세 항목 추출 (최대 5개)
        original_items = self._extract_original_items(raw_data)
        
        # LLM이 있으면 자연스러운 답변 생성
        if self.llm:
            enhanced = self._generate_natural_response(structured_data, query, intent)
            # 원본 데이터 추가
            if original_items:
                enhanced += "\n\n" + "="*60 + "\n"
                enhanced += "📋 **원본 데이터 샘플**\n"
                enhanced += "-"*40 + "\n"
                enhanced += original_items
            return enhanced
        else:
            # LLM 없으면 개선된 포맷팅만 적용
            formatted = self._format_structured_response(structured_data, intent)
            if original_items:
                formatted += "\n\n" + "="*60 + "\n"
                formatted += "📋 **원본 데이터 샘플**\n"
                formatted += "-"*40 + "\n"
                formatted += original_items
            return formatted
    
    def _analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """사용자 질문 의도 분석"""
        query_lower = query.lower()
        
        intent = {
            'type': 'general',  # general, count, detail, comparison, cost
            'wants_summary': False,
            'wants_details': False,
            'wants_statistics': False,
            'location': None,
            'equipment_type': None,
            'manager': None,
            'year': None
        }
        
        # 의도 타입 판단
        if any(word in query_lower for word in ['몇개', '얼마나', '총', '전체']):
            intent['type'] = 'count'
            intent['wants_statistics'] = True
        elif any(word in query_lower for word in ['상세', '자세히', '설명', '보여줘']):
            intent['type'] = 'detail'
            intent['wants_details'] = True
        elif any(word in query_lower for word in ['비교', '차이', '어떤게']):
            intent['type'] = 'comparison'
        elif any(word in query_lower for word in ['금액', '비용', '가격', '얼마']):
            intent['type'] = 'cost'
            intent['wants_statistics'] = True
        
        # 요약 요청 확인
        if any(word in query_lower for word in ['요약', '간단히', '핵심만']):
            intent['wants_summary'] = True
            
        # 위치 추출
        location_keywords = ['중계차', '광화문', '스튜디오', '부조정실', '주조정실']
        for loc in location_keywords:
            if loc in query_lower:
                intent['location'] = loc
                break
                
        # 장비 타입 추출
        equipment_types = ['카메라', '모니터', '오디오', '조명', 'ccu', '렌즈']
        for eq in equipment_types:
            if eq in query_lower:
                intent['equipment_type'] = eq
                break
                
        return intent
    
    def _structure_raw_data(self, raw_data: str) -> Dict[str, Any]:
        """날 데이터를 구조화된 형태로 변환"""
        
        structured = {
            'total_count': 0,
            'total_value': 0,
            'categories': {},
            'items': [],
            'summary': '',
            'has_truncation': False
        }
        
        lines = raw_data.split('\n')
        
        # 총 개수 추출
        count_match = re.search(r'총\s*(\d+)\s*개', raw_data)
        if count_match:
            structured['total_count'] = int(count_match.group(1))
        
        # 총 금액 추출
        value_match = re.search(r'(\d+(?:\.\d+)?)\s*억원', raw_data)
        if value_match:
            structured['total_value'] = float(value_match.group(1))
        
        # 카테고리별 분류 추출
        category_section = False
        for line in lines:
            if '카테고리별' in line or '장비 카테고리' in line:
                category_section = True
                continue
            if category_section and '•' in line:
                cat_match = re.match(r'\s*•\s*([^:]+):\s*(\d+)개', line)
                if cat_match:
                    structured['categories'][cat_match.group(1)] = int(cat_match.group(2))
            elif category_section and '---' in line:
                category_section = False
        
        # 상세 항목 추출 (최대 10개만)
        item_pattern = r'\[(\d+)\].*?\[(\d{4})\]\s*(.+)'
        for line in lines:
            item_match = re.match(item_pattern, line)
            if item_match and len(structured['items']) < 10:
                structured['items'].append({
                    'index': item_match.group(1),
                    'id': item_match.group(2),
                    'name': item_match.group(3)
                })
        
        # 잘림 여부 확인
        if '... 외' in raw_data:
            structured['has_truncation'] = True
            
        return structured
    
    def _generate_natural_response(self, data: Dict, query: str, intent: Dict) -> str:
        """LLM을 사용해 자연스러운 답변 생성"""
        
        # 컨텍스트 구성 - 더 상세하게
        context_text = f"""장비 자산 데이터 요약:
- 총 장비 수: {data['total_count']}개
- 총 자산가치: {data.get('total_value', 0)}억원
- 위치: {intent.get('location', '전체')}
"""
        
        if data['categories']:
            context_text += "\n카테고리별 분포:\n"
            for cat, count in list(data['categories'].items())[:5]:
                context_text += f"- {cat}: {count}개\n"
        
        if data['items']:
            context_text += "\n주요 장비 예시:\n"
            for item in data['items'][:3]:
                context_text += f"- [{item['id']}] {item['name']}\n"
        
        # 컨텍스트 구성
        context_chunks = [{
            'content': context_text,
            'source': 'asset_database',
            'score': 1.0
        }]
        
        try:
            # 간단한 프롬프트로 LLM 호출
            simple_prompt = f"""사용자 질문: {query}

위 데이터를 바탕으로 자연스럽고 친근한 한국어로 답변해주세요.
중요한 숫자와 통계를 포함해서 답변하되, 너무 길지 않게 요약해주세요."""
            
            # LLM 호출 - generate_response 사용
            if hasattr(self.llm, 'generate_response'):
                response = self.llm.generate_response(simple_prompt, context_chunks)
                if response and hasattr(response, 'answer'):
                    answer = response.answer
                else:
                    answer = str(response) if response else ""
            else:
                # 폴백
                answer = ""
            
            # 답변이 비어있거나 너무 짧으면 구조화된 응답 사용
            if not answer or len(answer) < 50:
                return self._format_structured_response(data, intent)
            
            # 주요 정보 추가 (답변에 없는 경우)
            if str(data['total_count']) not in answer:
                answer = f"총 {data['total_count']:,}개의 장비가 있습니다.\n\n" + answer
            
            return answer
            
        except Exception as e:
            print(f"LLM 답변 생성 실패: {e}")
            return self._format_structured_response(data, intent)
    
    def _build_llm_prompt(self, data: Dict, query: str, intent: Dict) -> str:
        """LLM용 프롬프트 생성 - 할루시네이션 방지 강화"""
        
        # 실제 데이터 개수 확인
        actual_count = data.get('total_count', 0)
        
        prompt = f"""[중요 지침]
- 반드시 제공된 데이터만 사용하여 답변하세요
- 숫자나 통계를 추측하거나 가정하지 마세요
- 제공된 데이터: {actual_count}개 장비
- 데이터가 0개면 "검색 결과가 없습니다"라고 답변하세요

사용자 질문: {query}

[확인된 실제 데이터]
총 장비 수: {data['total_count']}개 (이 숫자를 정확히 사용하세요)
"""
        
        if data.get('total_value', 0) > 0:
            prompt += f"총 자산 가치: {data['total_value']}억원\n"
        
        if data.get('categories'):
            prompt += "\n실제 카테고리별 분포:\n"
            for cat, count in data['categories'].items():
                prompt += f"- {cat}: {count}개 (정확한 숫자)\n"
        
        # 샘플 항목 추가 (실제 데이터)
        if data.get('sample_items'):
            prompt += "\n실제 장비 예시 (처음 3개):\n"
            for i, item in enumerate(data['sample_items'][:3], 1):
                prompt += f"{i}. {item}\n"
        
        prompt += f"""
[답변 작성 규칙]
1. 위 데이터만 사용하여 답변
2. 숫자는 반드시 제공된 값 그대로 사용
3. "약", "대략", "추정" 같은 표현 금지
4. 데이터에 없는 정보는 "확인되지 않음"으로 표시
5. 총 {actual_count}개라고 명확히 표시
6. 한국어로 자연스럽게 작성

답변 (데이터 기반으로만):"""
        
        return prompt
    
    def _format_structured_response(self, data: Dict, intent: Dict) -> str:
        """LLM 없이 구조화된 응답 포맷팅"""
        
        response = []
        
        # 헤더
        if intent['location']:
            response.append(f"📊 **{intent['location']} 장비 현황**")
        else:
            response.append("📊 **장비 자산 현황**")
        
        response.append("=" * 60)
        
        # 요약 정보
        if data['total_count'] > 0:
            response.append(f"✅ 총 **{data['total_count']:,}개** 장비 보유")
            if data['total_value'] > 0:
                response.append(f"💰 총 자산가치: **{data['total_value']:.1f}억원**")
        else:
            response.append("❌ 해당하는 장비를 찾을 수 없습니다.")
            return '\n'.join(response)
        
        response.append("")
        
        # 카테고리별 분포
        if data['categories'] and intent['wants_statistics']:
            response.append("### 📈 카테고리별 분포")
            response.append("-" * 40)
            for cat, count in sorted(data['categories'].items(), key=lambda x: x[1], reverse=True):
                percentage = (count / data['total_count']) * 100
                response.append(f"• **{cat}**: {count:,}개 ({percentage:.1f}%)")
            response.append("")
        
        # 주요 장비 목록
        if data['items'] and intent['wants_details']:
            response.append("### 📋 주요 장비 목록")
            response.append("-" * 40)
            for i, item in enumerate(data['items'][:10], 1):
                response.append(f"{i}. [{item['id']}] **{item['name']}**")
            
            if data['has_truncation']:
                remaining = data['total_count'] - len(data['items'])
                response.append(f"\n... 외 {remaining:,}개 장비")
        
        # 추가 안내
        if intent['type'] == 'count':
            response.append("")
            response.append("💡 **Tip**: 특정 카테고리나 위치의 상세 정보가 필요하시면 추가로 질문해주세요.")
        elif intent['type'] == 'detail':
            response.append("")
            response.append("📌 **Note**: 전체 목록이 필요하시면 Excel 파일로 내보내기 기능을 사용하세요.")
        
        return '\n'.join(response)
    
    def _extract_original_items(self, raw_data: str) -> str:
        """원본 데이터에서 상세 항목 추출"""
        lines = raw_data.split('\n')
        original_items = []
        item_count = 0
        current_item = []
        
        for line in lines:
            # 새 항목 시작 패턴
            if re.match(r'^\[\d{4}\]', line):
                # 이전 항목 저장
                if current_item and item_count < 5:
                    original_items.append('\n'.join(current_item))
                    item_count += 1
                # 새 항목 시작
                current_item = [line]
            elif current_item and item_count < 5:
                # 현재 항목에 속하는 라인들 (구분정보, 기본정보, 구입정보, 위치정보, 관리정보)
                if any(keyword in line for keyword in ['구분정보:', '기본정보:', '구입정보:', '위치정보:', '관리정보:']):
                    current_item.append(line)
        
        # 마지막 항목 처리
        if current_item and item_count < 5:
            original_items.append('\n'.join(current_item))
        
        if original_items:
            result = "\n\n".join(original_items[:5])  # 최대 5개 항목
            if len(lines) > 50:  # 많은 데이터가 있을 경우
                remaining = len([l for l in lines if re.match(r'^\[\d{4}\]', l)]) - 5
                if remaining > 0:
                    result += f"\n\n... 외 {remaining}개 장비"
            return result
        
        return ""
    
    def format_asset_statistics(self, data: Dict) -> str:
        """통계 정보를 보기 좋게 포맷팅"""
        
        stats = []
        stats.append("📊 **장비 자산 통계**")
        stats.append("=" * 50)
        
        # 기본 통계
        stats.append(f"• 총 장비 수: {data.get('total_count', 0):,}개")
        stats.append(f"• 총 자산가치: {data.get('total_value', 0):.2f}억원")
        
        if data.get('total_count', 0) > 0:
            avg_value = (data.get('total_value', 0) * 100000000) / data.get('total_count', 1)
            stats.append(f"• 평균 장비 가격: {avg_value:,.0f}원")
        
        # 카테고리별 통계
        if data.get('categories'):
            stats.append("\n**카테고리별 분포:**")
            sorted_cats = sorted(data['categories'].items(), key=lambda x: x[1], reverse=True)
            for cat, count in sorted_cats[:5]:
                stats.append(f"  • {cat}: {count:,}개")
            
            if len(sorted_cats) > 5:
                stats.append(f"  • 기타: {sum(c for _, c in sorted_cats[5:]):,}개")
        
        return '\n'.join(stats)