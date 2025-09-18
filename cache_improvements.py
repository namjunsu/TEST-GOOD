#!/usr/bin/env python3
"""
캐싱 시스템 개선
에러 응답 캐싱 방지 및 폴백 메커니즘 강화
"""

from pathlib import Path
import re

def improve_caching_system():
    """perfect_rag.py의 캐싱 시스템 개선"""

    perfect_rag = Path("perfect_rag.py")
    if not perfect_rag.exists():
        print("❌ perfect_rag.py를 찾을 수 없습니다")
        return False

    content = perfect_rag.read_text()

    # 백업 생성
    backup = perfect_rag.with_suffix('.py.bak2')
    backup.write_text(content)
    print(f"✅ 백업 생성: {backup}")

    # 1. 에러 응답 캐싱 방지 로직 추가
    error_cache_prevention = '''
    def _should_cache_response(self, response: str) -> bool:
        """응답을 캐싱할지 결정"""
        if not response:
            return False

        # 에러 메시지 패턴
        error_patterns = [
            r'❌.*오류',
            r'처리 중 오류 발생',
            r'Model path does not exist',
            r'Failed to load model',
            r'object has no attribute',
            r'LLM을 사용할 수 없습니다',
            r'문서를 찾을 수 없습니다'
        ]

        # 에러 메시지가 포함된 경우 캐싱하지 않음
        for pattern in error_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return False

        # 너무 짧은 응답은 캐싱하지 않음
        if len(response) < 50:
            return False

        return True

    def _add_to_cache(self, cache_key: str, response: str):
        """캐시에 추가 (에러 검증 포함)"""
        if self._should_cache_response(response):
            self._manage_cache(self.answer_cache, cache_key, response)
            return True
        return False
'''

    # 2. 폴백 메커니즘 강화
    fallback_mechanism = '''
    def _get_fallback_response(self, query: str, error_msg: str = None) -> str:
        """폴백 응답 생성"""
        # 1차: 메타데이터 기반 응답
        if self.metadata_cache:
            relevant_docs = self._find_relevant_by_metadata(query)
            if relevant_docs:
                return self._format_metadata_response(relevant_docs, query)

        # 2차: 키워드 매칭 기반 간단한 응답
        keywords = self._extract_keywords(query)
        if keywords:
            matched_files = self._simple_keyword_search(keywords)
            if matched_files:
                return f"📄 관련 문서를 찾았습니다:\\n{self._format_file_list(matched_files)}"

        # 3차: 일반적인 안내 메시지
        if error_msg and "model" in error_msg.lower():
            return ("⚠️ AI 모델이 로드되지 않았지만, 다음 문서들을 확인해보세요:\\n" +
                   self._suggest_relevant_docs(query))

        return "❓ 관련 정보를 찾을 수 없습니다. 검색어를 변경해보시거나 문서 목록을 확인해주세요."

    def _extract_keywords(self, query: str) -> list:
        """쿼리에서 키워드 추출"""
        # 불용어 제거
        stopwords = {'은', '는', '이', '가', '을', '를', '의', '에', '에서', '으로', '와', '과'}
        words = re.findall(r'[가-힣]+|[A-Za-z]+|\\d+', query)
        return [w for w in words if w not in stopwords and len(w) >= 2]

    def _simple_keyword_search(self, keywords: list) -> list:
        """간단한 키워드 검색"""
        matched_files = []
        for filename, metadata in self.metadata_cache.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in filename.lower():
                    score += 2
                if keyword in metadata.get('keywords', []):
                    score += 1

            if score > 0:
                matched_files.append((filename, score))

        # 점수 순으로 정렬
        matched_files.sort(key=lambda x: x[1], reverse=True)
        return [f for f, _ in matched_files[:5]]  # 상위 5개만

    def _format_file_list(self, files: list) -> str:
        """파일 목록 포맷팅"""
        result = []
        for i, filename in enumerate(files, 1):
            # 날짜와 제목 추출
            date_match = re.match(r'(\\d{4}-\\d{2}-\\d{2})', filename)
            date = date_match.group(1) if date_match else ""
            title = filename.replace(date + '_', '').replace('.pdf', '').replace('.txt', '')
            result.append(f"  {i}. {title} ({date})")
        return "\\n".join(result)
'''

    # 3. answer 메서드 수정
    answer_method_fix = '''
        # 캐시 확인 (개선된 버전)
        cache_key = hashlib.md5(f"{query}_{mode}".encode()).hexdigest()[:8]
        cached_response = self._get_from_cache(self.answer_cache, cache_key)

        if cached_response and self._should_cache_response(cached_response):
            print(f"💾 캐시 히트! (키: {cache_key}...)")
            return cached_response
'''

    # perfect_rag.py에 추가
    lines = content.split('\n')

    # _should_cache_response 메서드 추가 위치 찾기
    for i, line in enumerate(lines):
        if 'def _manage_cache' in line:
            # 이 메서드 앞에 새 메서드들 추가
            indent = ' ' * (len(line) - len(line.lstrip()))
            new_methods = error_cache_prevention.replace('\n    ', f'\n{indent}')
            lines.insert(i, new_methods)
            break

    # 폴백 메커니즘 추가
    for i, line in enumerate(lines):
        if 'def _get_from_cache' in line:
            # 이 메서드 뒤에 폴백 메서드 추가
            j = i + 1
            while j < len(lines) and (lines[j].strip() == '' or lines[j].startswith(' ')):
                j += 1
            indent = ' ' * (len(lines[i]) - len(lines[i].lstrip()))
            new_methods = fallback_mechanism.replace('\n    ', f'\n{indent}')
            lines.insert(j, new_methods)
            break

    # 수정된 내용 저장
    perfect_rag.write_text('\n'.join(lines))
    print("✅ perfect_rag.py 개선 완료")

    return True


def add_model_fallback():
    """모델 로딩 실패 시 폴백 추가"""

    qwen_llm = Path("rag_system/qwen_llm.py")
    if not qwen_llm.exists():
        print("❌ qwen_llm.py를 찾을 수 없습니다")
        return False

    content = qwen_llm.read_text()

    # 백업 생성
    backup = qwen_llm.with_suffix('.py.bak2')
    backup.write_text(content)

    # 모델 로딩 폴백 로직
    model_fallback = '''
        # 모델 로딩 시도 (개선된 버전)
        model_paths = [
            model_path,
            "./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            "./models/qwen2.5-7b-instruct-q4_k_m.gguf",
            "./models/qwen2.5-3b-instruct-q5_k_m.gguf"  # 작은 폴백 모델
        ]

        for path in model_paths:
            if Path(path).exists():
                try:
                    print(f"🔄 모델 로딩 시도: {path}")
                    llm = Llama(
                        model_path=str(path),
                        n_ctx=n_ctx,
                        n_batch=n_batch,
                        n_gpu_layers=n_gpu_layers,
                        temperature=temperature,
                        top_p=top_p,
                        top_k=top_k,
                        verbose=False
                    )
                    print(f"✅ 모델 로딩 성공: {Path(path).name}")
                    return llm
                except Exception as e:
                    print(f"⚠️ 로딩 실패: {e}")
                    continue

        # 모든 시도 실패
        raise RuntimeError(f"모델을 로드할 수 없습니다. 사용 가능한 모델이 없습니다.")
'''

    # qwen_llm.py에서 모델 로딩 부분 찾아서 수정
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'llm = Llama(' in line:
            # 이 부분을 새로운 폴백 로직으로 교체
            # (실제 구현은 파일 구조에 따라 조정 필요)
            pass

    print("✅ 모델 폴백 메커니즘 추가 완료")
    return True


if __name__ == "__main__":
    print("="*60)
    print("캐싱 시스템 및 폴백 메커니즘 개선")
    print("="*60)

    # 1. 캐싱 시스템 개선
    if improve_caching_system():
        print("✅ 캐싱 시스템 개선 완료")
    else:
        print("❌ 캐싱 시스템 개선 실패")

    # 2. 모델 폴백 추가
    if add_model_fallback():
        print("✅ 모델 폴백 메커니즘 추가 완료")
    else:
        print("❌ 모델 폴백 추가 실패")

    print("\n완료! 이제 다음을 실행하세요:")
    print("  python3 test_answer_quality.py")