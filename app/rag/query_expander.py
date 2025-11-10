"""
Query Expansion using LLM
사용자 질문에서 키워드와 동의어/관련어를 추출하여 검색 범위 확장
"""

import json
import yaml
from pathlib import Path
from typing import List, Dict, Any, Set
from app.core.logging import get_logger
from rag_system.llm_singleton import LLMSingleton

logger = get_logger(__name__)

# 설정 로드
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "filters.yaml"


class QueryExpander:
    """LLM 기반 쿼리 확장"""

    def __init__(self):
        """초기화"""
        self.llm = LLMSingleton.get_instance()
        self.cache = {}  # 간단한 메모리 캐시
        self.search_stopwords = self._load_search_stopwords()
        logger.info(f"✅ QueryExpander 초기화: {len(self.search_stopwords)}개 검색 불용어")

    def _load_search_stopwords(self) -> Set[str]:
        """검색 불용어 로드"""
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            stopwords = set(config.get('search_stopwords', []))
            logger.info(f"📋 검색 불용어 {len(stopwords)}개 로드됨")
            return stopwords
        except Exception as e:
            logger.warning(f"⚠️ 검색 불용어 로드 실패, 기본값 사용: {e}")
            return {'및', '과', '해줘', '좀', '문서', '내용', '요약', '건'}

    def expand_query(self, query: str) -> Dict[str, Any]:
        """사용자 질문에서 키워드 추출 및 확장

        Args:
            query: 사용자 질문

        Returns:
            {
                "original_keywords": ["키워드1", "키워드2"],
                "expanded_keywords": ["동의어1", "동의어2", "관련어1"],
                "search_query": "확장된 FTS 쿼리"
            }
        """
        # 캐시 확인 (동일 질문 반복 방지)
        if query in self.cache:
            logger.info(f"💾 Cache hit for query: '{query[:30]}...'")
            return self.cache[query]

        # LLM 프롬프트
        prompt = f"""다음 질문에서 검색에 필요한 키워드와 동의어를 추출하세요.

질문: {query}

다음 JSON 형식으로만 답변하세요 (설명 없이):
{{
  "keywords": ["핵심키워드1", "핵심키워드2"],
  "synonyms": {{
    "핵심키워드1": ["동의어1", "동의어2"],
    "핵심키워드2": ["동의어1", "동의어2"]
  }}
}}

예시:
질문: "카메라 삼각대 다리 부분 교체"
{{
  "keywords": ["카메라", "삼각대", "다리", "교체"],
  "synonyms": {{
    "삼각대": ["트라이포트", "트라이포드", "tripod"],
    "다리": ["발판", "지지대", "leg"],
    "교체": ["수리", "교체", "고장", "변경"]
  }}
}}

질문: "렌즈 고장났어"
{{
  "keywords": ["렌즈", "고장"],
  "synonyms": {{
    "고장": ["수리", "불량", "파손", "오류"],
    "렌즈": ["lens", "렌즈"]
  }}
}}

이제 위 질문에 대해 JSON만 출력하세요:"""

        try:
            # LLM 호출
            # QwenLLM 시그니처: generate_response(question, context_chunks, max_retries=2, enable_complex_processing=True, mode="rag")
            response = self.llm.generate_response(
                question=prompt,
                context_chunks=[],
                enable_complex_processing=False,  # 단순 키워드 추출이므로 복합처리 불필요
                mode="rag"
            )

            # JSON 파싱
            # RAGResponse 객체에서 answer 추출
            if hasattr(response, 'answer'):
                response_text = response.answer.strip()
            else:
                response_text = str(response).strip()

            # LLM 응답에서 JSON 부분만 추출 (```json 태그 제거)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            result = json.loads(response_text)

            keywords = result.get("keywords", [])
            synonyms_dict = result.get("synonyms", {})

            # 모든 키워드 수집 (원본 + 동의어)
            all_keywords = set(keywords)
            for syn_list in synonyms_dict.values():
                all_keywords.update(syn_list)

            # 불용어 제거 (길이 1인 키워드도 제거 - 조사/접속사)
            filtered_keywords = {
                kw for kw in all_keywords
                if kw.lower() not in self.search_stopwords and len(kw) > 1
            }

            if len(filtered_keywords) < len(all_keywords):
                removed = all_keywords - filtered_keywords
                logger.info(f"🧹 불용어 제거: {removed}")

            # 최소 1개 키워드는 유지
            if not filtered_keywords:
                filtered_keywords = all_keywords
                logger.warning(f"⚠️ 모든 키워드가 불용어 - 필터링 건너뜀")

            # FTS 쿼리 생성 (OR로 연결, 각 키워드를 따옴표로 감싸서 리터럴 처리)
            # 날짜 패턴(2025-06-10 등)의 하이픈이 SQL 연산자로 인식되지 않도록 방지
            quoted_keywords = [f'"{kw}"' for kw in filtered_keywords]
            search_query = " OR ".join(quoted_keywords)

            logger.info(f"✅ Query expansion: {query[:30]}... → {len(all_keywords)}개 키워드")

            result = {
                "original_keywords": keywords,
                "expanded_keywords": list(all_keywords),
                "search_query": search_query,
                "synonyms": synonyms_dict
            }

            # 캐시에 저장
            self.cache[query] = result

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ JSON 파싱 실패, fallback 사용: {e}")
            logger.debug(f"LLM response: {response[:500]}")
            # Fallback: 원본 쿼리 단어 분리 + 불용어 제거
            words = query.replace("?", "").replace(".", "").split()
            filtered_words = [w for w in words if w.lower() not in self.search_stopwords and len(w) > 1]
            if not filtered_words:
                filtered_words = words  # 모두 불용어면 원본 유지
            quoted_words = [f'"{w}"' for w in filtered_words]
            return {
                "original_keywords": words,
                "expanded_keywords": filtered_words,
                "search_query": " OR ".join(quoted_words),
                "synonyms": {},
                "fallback": True  # Fallback 사용 표시
            }

        except Exception as e:
            logger.warning(f"⚠️ Query expansion 실패, fallback 사용: {e}")
            # Fallback + 불용어 제거
            words = query.replace("?", "").replace(".", "").split()
            filtered_words = [w for w in words if w.lower() not in self.search_stopwords and len(w) > 1]
            if not filtered_words:
                filtered_words = words
            quoted_words = [f'"{w}"' for w in filtered_words]
            return {
                "original_keywords": words,
                "expanded_keywords": filtered_words,
                "search_query": " OR ".join(quoted_words),
                "synonyms": {},
                "fallback": True
            }


# 싱글톤 인스턴스
_expander = None


def get_query_expander() -> QueryExpander:
    """싱글톤 QueryExpander 인스턴스 반환"""
    global _expander
    if _expander is None:
        _expander = QueryExpander()
    return _expander
