"""
LLM Handler Module
대규모 언어 모델 처리 모듈
"""

import os
import time
from typing import Dict, Any, Optional
from threading import Lock
from llama_cpp import Llama


class LLMHandler:
    """LLM 핸들러 - Qwen2.5-7B"""

    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        """싱글톤 패턴 구현"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Dict[str, Any]):
        if hasattr(self, '_initialized'):
            return

        self.config = config
        self.model_path = "models/qwen2_5-7b-instruct-q4_k_m.gguf"
        self.model = None

        # LLM 파라미터
        self.temperature = 0.3
        self.max_tokens = 800
        self.top_p = 0.85
        self.top_k = 30

        self._load_model()
        self._initialized = True

    def _load_model(self):
        """모델 로드"""
        if not os.path.exists(self.model_path):
            print(f"⚠️ 모델 파일이 없습니다: {self.model_path}")
            print("Qwen2.5-7B 모델을 다운로드해주세요.")
            return

        print("🔧 LLM 모델 로드 중...")
        start_time = time.time()

        try:
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=8192,  # 컨텍스트 윈도우
                n_batch=512,
                n_threads=8,  # CPU 스레드
                n_gpu_layers=35,  # GPU 레이어 (RTX 4000용)
                verbose=False
            )

            elapsed = time.time() - start_time
            print(f"✅ LLM 모델 로드 완료 ({elapsed:.1f}초)")

        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            self.model = None

    def generate(self, query: str, context: str) -> str:
        """답변 생성"""
        if not self.model:
            return "죄송합니다. LLM 모델이 로드되지 않았습니다."

        # 프롬프트 구성
        prompt = self._build_prompt(query, context)

        # 생성
        try:
            response = self.model(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                top_p=self.top_p,
                top_k=self.top_k,
                stop=["</답변>", "\n\n질문:"],
                echo=False
            )

            answer = response['choices'][0]['text'].strip()

            # 후처리
            answer = self._postprocess_answer(answer)

            return answer

        except Exception as e:
            print(f"❌ 답변 생성 오류: {e}")
            return "답변 생성 중 오류가 발생했습니다."

    def _build_prompt(self, query: str, context: str) -> str:
        """프롬프트 템플릿 구성"""
        prompt = f"""<시스템>
당신은 한국 방송사의 문서 검색 시스템 AI 어시스턴트입니다.
주어진 문서 내용을 바탕으로 정확하고 도움이 되는 답변을 제공하세요.

규칙:
1. 문서에 있는 내용만을 바탕으로 답변하세요
2. 추측이나 가정을 하지 마세요
3. 한국어로 자연스럽게 답변하세요
4. 중요한 정보는 강조하여 전달하세요
</시스템>

<문서>
{context}
</문서>

<질문>
{query}
</질문>

<답변>
"""
        return prompt

    def _postprocess_answer(self, answer: str) -> str:
        """답변 후처리"""
        # 불필요한 태그 제거
        answer = answer.replace("</답변>", "").strip()

        # 중국어 제거
        import re
        answer = re.sub(r'[\u4e00-\u9fff]+', '', answer)

        # 빈 답변 처리
        if not answer or len(answer) < 10:
            return "관련 정보를 찾을 수 없습니다."

        return answer

    def generate_summary(self, text: str, max_length: int = 200) -> str:
        """텍스트 요약"""
        if not self.model:
            return text[:max_length]

        prompt = f"""<시스템>
다음 텍스트를 {max_length}자 이내로 간단히 요약하세요.
핵심 내용만 포함하세요.
</시스템>

<텍스트>
{text[:2000]}
</텍스트>

<요약>
"""

        try:
            response = self.model(
                prompt,
                temperature=0.3,
                max_tokens=max_length,
                stop=["</요약>"],
                echo=False
            )

            summary = response['choices'][0]['text'].strip()
            return summary if summary else text[:max_length]

        except:
            return text[:max_length]