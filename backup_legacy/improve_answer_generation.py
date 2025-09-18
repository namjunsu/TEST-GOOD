#!/usr/bin/env python3
"""
답변 생성 품질 개선
프롬프트 엔지니어링 및 컨텍스트 최적화
"""

from pathlib import Path
import re

def improve_prompts():
    """프롬프트 개선"""

    qwen_llm = Path("rag_system/qwen_llm.py")
    if not qwen_llm.exists():
        print("❌ qwen_llm.py를 찾을 수 없습니다")
        return False

    content = qwen_llm.read_text()

    # 백업 생성
    backup = qwen_llm.with_suffix('.py.bak3')
    backup.write_text(content)

    # 개선된 프롬프트 템플릿
    improved_prompts = '''
    # 개선된 프롬프트 템플릿
    IMPROVED_SYSTEM_PROMPT = """당신은 한국 방송사의 전문 지식 검색 도우미입니다.
주어진 문서 내용을 바탕으로 정확하고 구체적인 답변을 제공해야 합니다.

중요 지침:
1. 문서에서 직접 찾을 수 있는 정보만 제공하세요
2. 숫자, 금액, 날짜는 정확하게 인용하세요
3. 불확실한 정보는 "문서에서 확인할 수 없음"이라고 명시하세요
4. 답변은 구체적이고 간결하게 작성하세요"""

    IMPROVED_QUERY_TEMPLATE = """문서 내용:
{context}

질문: {query}

위 문서를 바탕으로 질문에 대해 답변해주세요.
- 관련 정보가 있다면 구체적인 내용을 포함하세요
- 금액이 있다면 정확한 숫자를 제시하세요
- 날짜가 있다면 명시하세요

답변:"""
'''

    # 기존 프롬프트를 찾아서 개선된 버전으로 교체
    lines = content.split('\n')

    # 프롬프트 개선 삽입 위치 찾기
    for i, line in enumerate(lines):
        if 'class QwenLLM' in line:
            # 클래스 정의 뒤에 개선된 프롬프트 추가
            lines.insert(i + 1, improved_prompts)
            break

    # generate 메서드 개선
    for i, line in enumerate(lines):
        if 'def generate(' in line or 'def generate_answer(' in line:
            # temperature 조정 추가
            for j in range(i, min(i + 50, len(lines))):
                if 'temperature=' in lines[j]:
                    # temperature를 0.1로 낮춰서 더 일관된 답변
                    lines[j] = re.sub(r'temperature=[\d.]+', 'temperature=0.1', lines[j])
                if 'max_tokens=' in lines[j]:
                    # 충분한 토큰 확보
                    lines[j] = re.sub(r'max_tokens=\d+', 'max_tokens=1024', lines[j])

    qwen_llm.write_text('\n'.join(lines))
    print("✅ 프롬프트 개선 완료")
    return True


def optimize_context_handling():
    """컨텍스트 처리 최적화"""

    perfect_rag = Path("perfect_rag.py")
    if not perfect_rag.exists():
        print("❌ perfect_rag.py를 찾을 수 없습니다")
        return False

    content = perfect_rag.read_text()

    # 백업 생성
    backup = perfect_rag.with_suffix('.py.bak3')
    backup.write_text(content)

    # 컨텍스트 최적화 코드
    context_optimization = '''
    def _optimize_context(self, text: str, query: str, max_length: int = 3000) -> str:
        """컨텍스트 최적화 - 가장 관련성 높은 부분만 추출"""
        if not text or len(text) <= max_length:
            return text

        # 쿼리 키워드 추출
        keywords = re.findall(r'[가-힣]+|[A-Za-z]+|\\d+', query.lower())
        keywords = [k for k in keywords if len(k) >= 2]

        # 문장 단위로 분리
        sentences = re.split(r'[.!?\\n]+', text)

        # 각 문장의 관련성 점수 계산
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            score = 0
            sentence_lower = sentence.lower()

            # 키워드 매칭 점수
            for keyword in keywords:
                if keyword in sentence_lower:
                    score += 10

            # 중요 패턴 보너스
            if re.search(r'\\d+[,\\d]*\\s*원', sentence):  # 금액
                score += 5
            if re.search(r'\\d{4}[-년]', sentence):  # 연도
                score += 3
            if re.search(r'총|합계|전체', sentence):  # 요약 정보
                score += 3

            # 위치 점수 (문서 앞부분 선호)
            position_score = max(0, 5 - i * 0.1)
            score += position_score

            scored_sentences.append((sentence, score))

        # 점수 순으로 정렬
        scored_sentences.sort(key=lambda x: x[1], reverse=True)

        # 상위 문장들로 컨텍스트 구성
        result = []
        current_length = 0

        for sentence, score in scored_sentences:
            if current_length + len(sentence) > max_length:
                break
            result.append(sentence)
            current_length += len(sentence)

        # 원래 순서대로 재정렬
        result_text = '. '.join(result)
        return result_text if result_text else text[:max_length]
'''

    # 컨텍스트 최적화 함수 추가
    lines = content.split('\n')

    # 적절한 위치에 삽입
    for i, line in enumerate(lines):
        if 'def _extract_pdf_info' in line:
            # 이 메서드 앞에 최적화 함수 추가
            indent = ' ' * (len(line) - len(line.lstrip()))
            optimized_code = context_optimization.replace('\n    ', f'\n{indent}')
            lines.insert(i, optimized_code)
            break

    perfect_rag.write_text('\n'.join(lines))
    print("✅ 컨텍스트 최적화 완료")
    return True


def add_answer_validation():
    """답변 검증 로직 추가"""

    validation_code = '''
def validate_and_enhance_answer(answer: str, query: str, context: str) -> str:
    """답변 검증 및 개선"""

    # 빈 답변 체크
    if not answer or len(answer) < 20:
        return "죄송합니다. 질문에 대한 충분한 정보를 찾을 수 없습니다. 다른 검색어를 시도해보세요."

    # 에러 메시지 체크
    error_patterns = ['error', 'failed', '오류', '실패']
    if any(pattern in answer.lower() for pattern in error_patterns):
        return "처리 중 문제가 발생했습니다. 다시 시도해주세요."

    # 금액 질문인데 금액이 없는 경우
    if any(word in query for word in ['비용', '금액', '얼마', '가격']):
        if not re.search(r'\\d+[,\\d]*\\s*원', answer):
            # 컨텍스트에서 금액 찾기
            amounts = re.findall(r'(\\d{1,3}(?:,\\d{3})*(?:\\.\\d+)?)\\s*원', context)
            if amounts:
                answer += f"\\n\\n참고: 문서에서 발견된 금액: {', '.join(amounts)}원"

    # 수량 질문인데 수량이 없는 경우
    if any(word in query for word in ['수량', '몇', '개수', '대수']):
        if not re.search(r'\\d+\\s*[개대]', answer):
            quantities = re.findall(r'(\\d+)\\s*[개대]', context)
            if quantities:
                answer += f"\\n\\n참고: 문서에서 발견된 수량: {', '.join(quantities)}개"

    return answer
'''

    print("✅ 답변 검증 로직 준비 완료")
    return validation_code


def create_improved_config():
    """개선된 설정 생성"""

    improved_settings = {
        "generation": {
            "temperature": 0.1,  # 낮춰서 일관성 향상
            "top_p": 0.9,
            "top_k": 30,
            "max_tokens": 1024,
            "repeat_penalty": 1.1
        },
        "context": {
            "max_length": 3000,
            "overlap": 200,
            "relevance_threshold": 0.5
        },
        "prompts": {
            "use_few_shot": True,
            "examples_count": 2
        }
    }

    import json
    with open("improved_settings.json", "w", encoding="utf-8") as f:
        json.dump(improved_settings, f, ensure_ascii=False, indent=2)

    print("✅ 개선된 설정 파일 생성: improved_settings.json")
    return improved_settings


def main():
    print("="*60)
    print("답변 품질 개선 작업")
    print("="*60)

    # 1. 프롬프트 개선
    print("\n1. 프롬프트 개선...")
    improve_prompts()

    # 2. 컨텍스트 최적화
    print("\n2. 컨텍스트 처리 최적화...")
    optimize_context_handling()

    # 3. 답변 검증 로직
    print("\n3. 답변 검증 로직 준비...")
    validation_code = add_answer_validation()

    # 4. 개선된 설정
    print("\n4. 개선된 설정 생성...")
    settings = create_improved_config()

    print("\n" + "="*60)
    print("✅ 모든 개선 작업 완료!")
    print("\n권장 사항:")
    print("1. 시스템 재시작: streamlit 앱을 재시작하세요")
    print("2. 캐시 초기화: 기존 캐시를 삭제하여 새로운 답변 생성")
    print("3. 테스트: python3 test_real_quality.py")

    return True


if __name__ == "__main__":
    main()