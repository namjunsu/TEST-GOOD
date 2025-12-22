"""
Multi-LLM Support System
Qwen GGUF + Llama Safetensors 모델 지원
한국어 특화 프롬프트 템플릿 최적화
"""

import logging
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.core.types import QuestionType
from config.constants import LLMWrapperConfig
from rag_system.active.llm_models import (
    MAX_LLM_RETRY,
    MODE_TOKEN_CONFIG,
    BaseRAGLLM,
    GenerationConfig,
    RAGResponse,
)

# 호환성을 위한 re-export
__all__ = [
    "GenerationConfig",
    "RAGResponse",
    "BaseRAGLLM",
    "MODE_TOKEN_CONFIG",
    "MAX_LLM_RETRY",
    "QwenLLM",
    "LlamaLLM",
    "VllmLLM",
    "create_llm",
]


class QwenLLM(BaseRAGLLM):

    # 프롬프트 템플릿 상수
    SYSTEM_ROLE = "한국 방송사의 전문 지식 검색 도우미"
    ANSWER_LANGUAGE = "한국어"
    CITATION_FORMAT = "[파일명.pdf]"

    # 프롬프트 템플릿 (2025-12-08: 답변 품질 개선 - 범위 제한 강화)
    IMPROVED_SYSTEM_PROMPT = f"""당신은 {SYSTEM_ROLE}입니다.

[핵심 원칙 - 반드시 지켜주세요]
★ 질문이 요청한 범위만 답변하세요. 요청하지 않은 정보는 포함하지 마세요.
  - "개요만" → 개요 섹션만 답변
  - "비용만" → 비용 정보만 답변
  - "무슨 내용이야?" → 3-5문장으로 핵심 요약만

[답변 규칙]
1. 첫 문장에서 질문의 핵심 답변을 제시하세요.
2. 문서에 있는 정보만 사용하세요. 추측 금지.
3. 숫자/금액/날짜는 정확하게 인용하세요.
4. 출처: [파일명.pdf] 형식으로 표시하세요.
5. 반드시 {ANSWER_LANGUAGE}로 답변하세요.

[금지사항]
- 질문 범위를 넘어선 추가 정보 금지
- 문서 전체를 나열하는 것 금지
- 과장이나 확대해석 금지"""

    IMPROVED_QUERY_TEMPLATE = """문서 내용:
{context}

질문: {query}

★ 위 질문이 요청한 범위만 답변하세요. 요청하지 않은 정보는 포함하지 마세요.
- 금액 질문 → 금액만 답변
- 개요/요약 질문 → 3-5문장으로 핵심만
- 특정 항목 질문 → 해당 항목만

답변:""".replace("{CITATION_FORMAT}", CITATION_FORMAT)

    """Qwen 모델 래퍼 클래스"""

    def __init__(self, model_path: str, config: Optional[GenerationConfig] = None, length_analyzer=None):
        super().__init__()  # BaseRAGLLM 초기화
        self.logger.info(f"🔍 DEBUG QwenLLM.__init__: Received model_path={model_path}")
        self.model_path = Path(model_path)
        self.logger.info(f"🔍 DEBUG QwenLLM.__init__: Converted to Path={self.model_path}")
        self.logger.info(f"🔍 DEBUG QwenLLM.__init__: File exists={self.model_path.exists()}")
        self.config = config or GenerationConfig()
        self.length_analyzer = length_analyzer  # length_analyzer 주입 (None 가능)

        # LLM 최적화 설정 로드
        self._load_optimization_config()

        # Chat format 자동 감지 설정 (환경변수 우선)
        chat_format_env = os.getenv("CHAT_FORMAT", "auto").lower()
        if chat_format_env == "auto":
            # auto: GGUF 메타데이터의 tokenizer.chat_template 사용
            self.chat_format = None
            self.logger.info("🔧 Chat format: auto (GGUF 메타데이터 사용)")
        else:
            # 명시적 지정: llama-2, chatml, qwen 등
            self.chat_format = chat_format_env
            self.logger.info(f"🔧 Chat format: {chat_format_env} (환경변수 강제 지정)")

        self.stop_tokens = ["</s>", "<|im_end|>", "<|endoftext|>"]

        self.llm = None
        self._load_model()

        # 인용 패턴 컴파일 (성능 향상)
        self.citation_patterns = [
            re.compile(r"\[([^\]]+\.pdf[^\]]*)\]"),  # [파일명.pdf] 형식
            re.compile(r"「([^」]+\.pdf[^」]*)」"),    # 「파일명.pdf」 형식
            re.compile(r"출처:\s*([^\n]+\.pdf[^\n]*)"),  # 출처: 파일명.pdf 형식
            re.compile(r"근거:\s*([^\n]+\.pdf[^\n]*)"),  # 근거: 파일명.pdf 형식
            re.compile(r"\[([^\]]*\d{4}-\d{2}-\d{2}[^\]]*\.pdf[^\]]*)\]"),  # 날짜 포함 파일명
            re.compile(r"(\d{4}-\d{2}-\d{2}_[^\s\]]+\.pdf)"),  # 날짜로 시작하는 파일명
            re.compile(r"([A-Za-z0-9가-힣_\-\s]+\.pdf)"),  # 일반적인 PDF 파일명 패턴
        ]

    def _load_optimization_config(self):
        """LLM 최적화 설정 로드"""
        self.use_optimized_prompts = False
        self.max_context_tokens = LLMWrapperConfig.MAX_CONTEXT_TOKENS
        self.max_response_tokens = LLMWrapperConfig.MAX_RESPONSE_TOKENS

        config_path = Path(__file__).parent.parent / "config" / "llm_optimization.yaml"

        # 환경 변수로 최적화 강제 활성화
        if os.environ.get("USE_OPTIMIZED_PROMPTS", "false").lower() == "true":
            self.use_optimized_prompts = True
            self.max_context_tokens = int(os.environ.get(
                "MAX_CONTEXT_TOKENS",
                str(LLMWrapperConfig.MAX_CONTEXT_TOKENS),
            ))
            self.logger.info("환경변수로 최적화 활성화")

        # YAML 설정 파일 로드
        elif config_path.exists():
            try:
                with Path(config_path).open("r", encoding="utf-8") as f:
                    opt_config = yaml.safe_load(f)
                    if opt_config and "prompts" in opt_config:
                        self.use_optimized_prompts = opt_config["prompts"].get("use_optimized", False)
                        self.max_context_tokens = opt_config["prompts"].get(
                            "max_context_tokens",
                            LLMWrapperConfig.MAX_CONTEXT_TOKENS,
                        )
                        self.max_response_tokens = opt_config["prompts"].get(
                            "max_response_tokens",
                            LLMWrapperConfig.MAX_RESPONSE_TOKENS,
                        )
                        self.logger.info(f"최적화 설정 로드: {config_path}")
            except Exception as e:
                self.logger.warning(f"최적화 설정 로드 실패: {e}")

    def _load_model(self):
        """모델 로드"""
        try:
            from llama_cpp import Llama

            # 환경 변수 우선 폴백 헬퍼
            def _env_int(name: str, default: int, *alts):
                """환경변수 읽기 (int) with fallback"""
                for key in (name, *alts):
                    val = os.getenv(key)
                    if val and val.strip():
                        try:
                            return int(val)
                        except ValueError:
                            pass
                return default

            def _env_bool(name: str, default: bool, *alts):
                """환경변수 읽기 (bool) with fallback"""
                for key in (name, *alts):
                    val = os.getenv(key)
                    if val and val.strip():
                        return val.lower() in ("true", "1", "yes", "on")
                return default

            # config.py에서 GPU 최적화 설정 가져오기 (폴백용)
            try:
                from config import F16_KV as CFG_F16_KV  # type: ignore[attr-defined]
                from config import N_BATCH as CFG_N_BATCH  # type: ignore[attr-defined]
                from config import N_CTX as CFG_N_CTX  # type: ignore[attr-defined]
                from config import N_GPU_LAYERS as CFG_N_GPU_LAYERS  # type: ignore[attr-defined]
                from config import N_THREADS as CFG_N_THREADS  # type: ignore[attr-defined]
                from config import USE_MLOCK as CFG_USE_MLOCK  # type: ignore[attr-defined]
                from config import USE_MMAP as CFG_USE_MMAP  # type: ignore[attr-defined]
            except ImportError:
                # config.py 없을 때 기본값 (GPU 최적화)
                CFG_N_THREADS, CFG_N_CTX, CFG_N_BATCH = 8, 4096, 768
                CFG_USE_MLOCK, CFG_USE_MMAP, CFG_N_GPU_LAYERS, CFG_F16_KV = False, True, -1, True

            # 환경변수 우선, config.py 폴백 (N_CTX, LLM_N_CTX 둘 다 지원)
            N_THREADS = _env_int("N_THREADS", CFG_N_THREADS, "LLM_N_THREADS")
            N_CTX = _env_int("N_CTX", CFG_N_CTX, "LLM_N_CTX")
            N_BATCH = _env_int("N_BATCH", CFG_N_BATCH, "LLM_N_BATCH")
            N_GPU_LAYERS = _env_int("N_GPU_LAYERS", CFG_N_GPU_LAYERS, "LLM_N_GPU_LAYERS")
            USE_MLOCK = _env_bool("USE_MLOCK", CFG_USE_MLOCK)
            USE_MMAP = _env_bool("USE_MMAP", CFG_USE_MMAP)
            F16_KV = _env_bool("F16_KV", CFG_F16_KV)

            self.logger.info(f"🔧 [LLM Config] n_ctx={N_CTX}, n_gpu_layers={N_GPU_LAYERS}, n_batch={N_BATCH}, n_threads={N_THREADS}")

            # GPU 설정: 잘못된 파라미터 제거 (offload_kqv, mul_mat_q 등이 GPU 사용 방해)
            # 기본 파라미터만 사용하여 GPU 오프로드가 제대로 작동하도록 함

            self.llm = Llama(
                model_path=str(self.model_path),
                chat_format=self.chat_format,
                n_ctx=N_CTX,           # config: 16384 (확장된 컨텍스트)
                n_threads=N_THREADS,   # config: 4 (GPU 사용시 CPU 스레드 최소화)
                n_gpu_layers=N_GPU_LAYERS,  # config: -1 (모든 레이어 GPU 사용!)
                f16_kv=F16_KV,        # config: True (GPU 메모리 최적화)
                use_mlock=USE_MLOCK,  # config: False (GPU 사용시 비활성화)
                use_mmap=USE_MMAP,    # config: True (메모리 매핑)
                verbose=False,        # 터미널 출력 최소화
                n_batch=N_BATCH,       # config: 1024 (배치 크기 증가)
            )

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 🔒 CRITICAL: n_ctx 불일치 가드 (재발 방지)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            requested_n_ctx = N_CTX
            effective_n_ctx = getattr(self.llm, "n_ctx", lambda: None)()

            # Effective config logging
            self.logger.info(
                f"🔧 [LLM Config] requested: n_ctx={requested_n_ctx}, n_batch={N_BATCH}, "
                f"n_gpu_layers={N_GPU_LAYERS}, n_threads={N_THREADS}",
            )
            self.logger.info(
                f"🔧 [LLM Config] effective: n_ctx={effective_n_ctx}",
            )

            # Mismatch guard
            if effective_n_ctx and int(effective_n_ctx) != int(requested_n_ctx):
                raise RuntimeError(
                    f"❌ FATAL: n_ctx mismatch detected!\n"
                    f"   Requested: {requested_n_ctx}\n"
                    f"   Effective: {effective_n_ctx}\n"
                    f"   This indicates stale LLM instance or environment variable loading failure.\n"
                    f"   Please restart the process with clean environment.",
                )

            # 로드된 모델 메타데이터 로그
            self.logger.info(f"✅ LLM 모델 로드 완료: {self.model_path.name}")

            # GGUF 메타데이터에서 architecture 추출
            try:
                metadata = self.llm.metadata if hasattr(self.llm, "metadata") else {}
                architecture = metadata.get("general.architecture", "unknown")
                model_type = metadata.get("general.name", "unknown")
                vocab_type = metadata.get("tokenizer.ggml.model", "unknown")

                self.logger.info(f"📊 Model Architecture: {architecture}")
                self.logger.info(f"📊 Model Type: {model_type}")
                self.logger.info(f"📊 Vocab Type: {vocab_type}")

                # Chat format 정보 (auto일 때 실제 사용된 템플릿)
                chat_template = metadata.get("tokenizer.chat_template", "")
                if self.chat_format is None and chat_template:
                    self.logger.info("💬 Chat Template: Loaded from GGUF metadata")
                    self.logger.debug(f"   Template preview: {chat_template[:100]}...")
                elif self.chat_format:
                    self.logger.info(f"💬 Chat Format: {self.chat_format} (override)")
                else:
                    self.logger.warning("⚠️  No chat template found, using llama-2 fallback")

            except Exception as e:
                self.logger.warning(f"메타데이터 추출 실패 (무시 가능): {e}")

            self.logger.info(f"⚙️  최적화 모드: {'활성화' if self.use_optimized_prompts else '비활성화'}")

        except ImportError:
            self.logger.error("llama-cpp-python 패키지가 설치되지 않았습니다.")
            raise
        except Exception as e:
            self.logger.error(f"모델 로드 실패: {e}")
            raise

    def _chat_complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repeat_penalty: Optional[float] = None,
    ) -> str:
        """통합 chat completion 호출 (중복 제거용 헬퍼)

        Args:
            messages: 메시지 리스트 [{"role": "system/user", "content": "..."}]
            max_tokens: 최대 생성 토큰 수
            temperature: 생성 온도 (None이면 config 기본값)
            top_p: top_p 값 (None이면 config 기본값)
            top_k: top_k 값 (None이면 config 기본값)
            repeat_penalty: 반복 패널티 (None이면 config 기본값)

        Returns:
            생성된 텍스트 (strip 적용됨)

        Raises:
            RuntimeError: LLM이 로드되지 않은 경우
        """
        if self.llm is None:
            raise RuntimeError("LLM이 로드되지 않았습니다")

        response = self.llm.create_chat_completion(
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=max_tokens,
            top_p=top_p if top_p is not None else self.config.top_p,
            top_k=top_k if top_k is not None else self.config.top_k,
            repeat_penalty=repeat_penalty if repeat_penalty is not None else self.config.repeat_penalty,
            stop=self.stop_tokens,
        )

        # response는 dict 또는 Iterator - dict인 경우만 처리
        choices = response["choices"]  # type: ignore[index]
        content = choices[0]["message"]["content"]
        return content.strip() if content else ""

    @lru_cache(maxsize=32)  # noqa: B019 - 의도적 메서드 캐싱 (성능 최적화)
    def create_system_prompt(self) -> str:
        """최적화된 시스템 프롬프트 (캐시됨)"""
        if self.use_optimized_prompts:
            # 최적화된 프롬프트 - 73.9% 토큰 감소
            return """방송기술 전문가. 제공문서 기반 정확답변. 출처명시."""
        # 원본 프롬프트
        return """당신은 한국어 방송기술 문서 전문 AI 어시스턴트입니다.

필수 규칙:
1. 반드시 한국어로만 답변하세요. 중국어나 영어로 답변하지 마세요.
2. 답변 마지막에 반드시 [출처: 파일명.pdf] 형식으로 출처를 명시하세요.

역할: 제공된 문서를 철저히 분석하여 사용자의 질문에 완전하고 정확하게 한국어로 답변

원칙:
1. 제공된 문서의 내용을 적극적으로 활용하여 답변
2. 문서에 있는 모든 관련 정보를 찾아서 종합
3. 구체적인 수치, 날짜, 모델명 등을 정확히 추출하여 사용
4. 자연스러운 한국어로 답변
5. 반드시 출처 문서를 [파일명.pdf] 형식으로 인용

답변 방식: 문서 내용을 바탕으로 한 구체적이고 유용한 답변 + 출처 인용"""

    def create_user_prompt(self, question: str, context_chunks: list[dict[str, Any]]) -> str:
        """사용자 프롬프트 생성 (최적화 모드 지원)"""

        if self.use_optimized_prompts:
            return self._create_optimized_user_prompt(question, context_chunks)

        # 요약 요청 여부 확인
        is_summary_request = any(keyword in question.lower() for keyword in ["요약", "개요", "내용"])

        # 전체 리스트 요청 여부 확인
        is_list_request = any(keyword in question.lower() for keyword in ["전부", "모든", "모두", "리스트", "목록", "품목"])

        # 특별 처리가 필요한 요청
        is_special_request = is_summary_request or is_list_request

        context_text = ""

        for i, chunk in enumerate(context_chunks, 1):
            filename = Path(self._get_chunk_source(chunk)).name
            # 🔥 CRITICAL: Support both 'content' and 'snippet' fields
            content = chunk.get("content") or chunk.get("snippet", "")
            score = chunk.get("score")

            # 점수가 없거나 0.0인 경우 경고 및 기본값 처리 (관련도 0.000 방지)
            if score is None or score == 0.0:
                self.logger.warning(f"⚠️ 점수 미설정: {filename}, 기본값 1.0 사용")
                score = 1.0

            context_text += f"\n--- 문서 {i}: {filename} (관련도: {score:.3f}) ---\n"

            # 특별 요청이 아닌 경우에만 메타데이터 추가 (메타데이터가 답변을 방해하므로)
            if not is_special_request:
                metadata = chunk.get("metadata", {})
                author = metadata.get("기안자", metadata.get("author", ""))
                doc_date = metadata.get("기안일자", metadata.get("date", ""))
                doc_type = metadata.get("신청구분", metadata.get("doc_type", ""))

                if author or doc_date or doc_type:
                    meta_info = []
                    if author:
                        meta_info.append(f"기안자: {author}")
                    if doc_date:
                        meta_info.append(f"날짜: {doc_date}")
                    if doc_type:
                        meta_info.append(f"문서유형: {doc_type}")
                    context_text += f"[메타데이터: {', '.join(meta_info)}]\n"

            context_text += content + "\n"

        # 요청 유형별 특별한 지시문
        if is_summary_request:
            instruction = """📋 기술 문서 요약 (반드시 아래 순서대로 작성):

1. 【개요】 한 문장으로 문서 목적 설명
2. 【장애/문제】 (있는 경우)
   - 장비명: 정확한 모델명
   - 증상: 구체적 장애 내용
   - 원인: 파악된 원인
3. 【조치 내용】
   - 수리/교체 항목 (모델명, 수량, 단가 포함)
4. 【총 비용】 금액 (VAT 제외/포함 명시)
5. 【검토 의견】 핵심 결론 및 필요 사항

⚠️ 문서의 모든 수치, 금액, 모델명을 정확히 기재하세요.
⚠️ 정보가 없는 항목은 "정보 없음"으로 표시하세요."""

        elif is_list_request:
            instruction = """🎯 전체 목록 추출 지침:
위 문서에서 언급된 모든 항목들을 완전하게 추출해주세요:

1. **품목명/모델명**: 정확한 제품명과 모델번호
2. **수량 및 가격**: 수치 정보를 빠짐없이 포함
3. **추가 정보**: 브랜드, 용도, 특징 등
4. **구조화**: 번호를 매겨서 체계적으로 정리

💡 문서 전체를 꼼꼼히 검토하여 누락되는 정보 없이 완전한 목록을 만들어주세요."""

        else:
            instruction = """🎯 질문 답변 지침:
위 문서의 내용을 바탕으로 질문에 대해 완전하고 정확하게 한국어로 답변해주세요.
문서에서 관련 정보를 찾아 구체적이고 유용한 답변을 제공하고, 반드시 [파일명.pdf] 형식으로 출처를 인용해주세요.

💡 문서에 있는 정보를 적극적으로 활용하여 사용자에게 도움이 되는 한국어 답변을 만들어주세요."""

        return f"""한국어로 답변해주세요.

질문: {question}

참고 문서:
{context_text}

{instruction}

반드시 한국어로만 답변하세요. 중국어나 영어로 답변하지 마세요."""

    def _create_optimized_user_prompt(self, question: str, context_chunks: list[dict[str, Any]]) -> str:
        """최적화된 사용자 프롬프트 생성 - 금액/품목 정보 우선"""
        context_text = ""
        total_tokens = 0

        # 품목/금액 질문인 경우 전체 컨텍스트 사용
        is_items_query = any(kw in question for kw in ["품목", "구매", "소모품", "장비", "물품", "금액", "가격", "얼마"])

        for _i, chunk in enumerate(context_chunks, 1):
            if total_tokens >= self.max_context_tokens:
                break

            filename = Path(self._get_chunk_source(chunk)).name
            # 🔥 CRITICAL: Support both 'content' and 'snippet' fields
            content = chunk.get("content") or chunk.get("snippet", "")

            context_text += f"\n[{filename}]\n"

            # 컨텍스트 최대 길이 (환경변수)
            max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "5000"))

            if is_items_query:
                # 품목/금액 질문: 전체 사용 (필터링 X)
                context_text += content[:max_context_chars]
            else:
                # 일반 질문: 중요 키워드 필터링
                important_keywords = ["날짜", "금액", "구매", "목적", "제목", "수량", "모델", "기안"]
                important_lines = []
                for line in content.split("\n"):
                    if any(kw in line for kw in important_keywords):
                        important_lines.append(line.strip())

                if important_lines:
                    context_text += "\n".join(important_lines[:20])  # 최대 20라인으로 확장

            context_text += "\n"
            total_tokens += len(context_text.split())

        # 품목/금액 질문에 특화된 프롬프트
        if is_items_query:
            return f"""문서:
{context_text}

질문: {question}

**답변 시 필수 포함 사항:**
1. 품목명 (정확한 이름)
2. 수량
3. 금액 (있는 경우 반드시 포함)
4. 출처: [파일명.pdf]

답변:"""
        # 일반 질문용 프롬프트
        return f"""문서:
{context_text}

Q: {question}
A:"""

    def create_full_document_prompt(self, question: str, document_text: str, file_path: str) -> str:
        """전체 문서 전용 프롬프트 생성"""

        filename = Path(file_path).name

        return f"""질문: {question}

전체 문서 내용 ({filename}):
{document_text}

🎯 문서 기반 답변 생성 (보수적 답변 금지):
1. **문서에 있는 정보는 반드시 활용**: 제공된 문서의 모든 관련 정보를 적극 활용
2. **구체적 정보 우선 추출**: 금액, 날짜, 기안자, 품목명, 수량 등 모든 구체적 정보
3. **완전한 요약 제공**: 문서의 목적, 주요 내용, 금액, 품목을 체계적으로 정리
4. **사용자에게 도움이 되는 답변**: "확인되지 않음"이 아닌 실제 정보 제공
5. **출처 인용**: [{filename}] 형식으로 반드시 인용

💪 적극적 정보 활용 원칙:
- 기안서에서 기안자, 날짜, 금액 정보 추출 필수
- 품목 목록이 있으면 주요 품목들 나열
- 총 금액과 세부 카테고리별 금액 제시
- 문서의 배경과 목적 설명
- 파일명의 날짜와 제목 정보도 활용

⚠️ 절대 금지: "구체적인 정보는 문서에서 찾을 수 없다" 등의 소극적 답변

답변 목표: 사용자가 문서 내용을 완전히 이해할 수 있는 유용한 요약 + [{filename}]"""

    def generate_response(self, question: str, context_chunks: list[dict[str, Any]],
                         max_retries: int = 2, enable_complex_processing: bool = True,
                         mode: str = "rag") -> RAGResponse:
        """RAG 응답 생성 (복합 질문 처리 및 적응형 길이 조정 통합)"""

        # 모드별 토큰 예산 적용 (2025-12-08: fallback 값을 .env와 동기화)
        mode_token_budgets = {
            "chat": int(os.getenv("CHAT_MAX_TOKENS", "512")),      # 64 → 512
            "rag": int(os.getenv("RAG_MAX_TOKENS", "3072")),       # 160 → 3072
            "summarize": int(os.getenv("SUMMARIZE_MAX_TOKENS", "2048")),
            "summary": int(os.getenv("SUMMARY_MAX_TOKENS", "2048")),  # 상세 요약용
        }
        mode_max_tokens = mode_token_budgets.get(mode.lower(), self.config.max_tokens)
        self.logger.info(f"🎯 Mode={mode}, max_tokens={mode_max_tokens} (budget: {mode_token_budgets.get(mode.lower(), 'N/A')})")

        # 0단계: 같은 문서의 모든 청크 우선 선택 (중간 단계 접근법)
        context_chunks = self._prioritize_same_document_chunks(context_chunks, max_chunks=10)

        # 적응형 길이 조정용
        length_recommendation = None

        # 기본 처리 모드 (적응형 길이 적용)
        if self.config.enable_adaptive_length and length_recommendation:
            system_prompt = self._create_adaptive_system_prompt(length_recommendation)
        else:
            system_prompt = self.create_system_prompt()

        user_prompt = self.create_user_prompt(question, context_chunks)

        retry_count = 0
        start_time = time.time()
        best_answer = None  # 인용이 없어도 가장 좋은 답변 저장

        for attempt in range(max_retries + 1):
            try:
                # 대화 메시지 구성
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]

                # 적응형 max_tokens 계산 (모드별 예산 우선)
                if self.config.enable_adaptive_length and length_recommendation:
                    adaptive_max_tokens = self._calculate_adaptive_max_tokens(length_recommendation)
                    self.logger.debug(f"적응형 토큰: {adaptive_max_tokens} (기본: {self.config.max_tokens})")
                    # 모드 예산과 적응형 중 최소값 사용
                    final_max_tokens = min(mode_max_tokens, adaptive_max_tokens)
                else:
                    final_max_tokens = mode_max_tokens

                # 생성 (헬퍼 메서드 사용)
                answer = self._chat_complete(messages, max_tokens=final_max_tokens)
                # 외국어 텍스트 필터링
                answer = self._remove_foreign_text(answer)
                generation_time = time.time() - start_time

                # 첫 번째 답변을 최선의 답변으로 저장 (인용 없어도)
                if best_answer is None and len(answer) > 10:  # 너무 짧지 않은 답변만
                    best_answer = {
                        "answer": answer,
                        "generation_time": generation_time,
                        "retry_count": retry_count,
                    }

                # 인용 검증
                citation_check = self._validate_citations(answer, context_chunks)

                if citation_check["has_citations"]:
                    # 적응형 길이 조정 적용
                    original_length = len(answer)
                    length_adjustments = []
                    adjusted_answer = answer

                    if self.config.enable_adaptive_length and length_recommendation and self.length_analyzer:
                        adjusted_answer, length_adjustments = self.length_analyzer.validate_and_adjust_answer(
                            answer, length_recommendation)

                    # 인용이 있는 답변 - 즉시 반환 (최우선)
                    return RAGResponse(
                        answer=adjusted_answer,
                        sources_cited=citation_check["cited_files"],
                        confidence=self._calculate_confidence(adjusted_answer, context_chunks),
                        generation_time=generation_time,
                        has_proper_citation=True,
                        retry_count=retry_count,
                        length_recommendation=length_recommendation,
                        original_length=original_length,
                        length_adjustments=length_adjustments,
                        adaptive_length_used=self.config.enable_adaptive_length,
                    )
                # 인용이 없지만 답변 품질 체크
                if self._is_meaningful_answer(answer):
                    # 의미있는 답변이면 저장하고 재시도 계속
                    best_answer = {
                        "answer": answer,
                        "generation_time": generation_time,
                        "retry_count": retry_count,
                    }
                    self.logger.info(f"인용 없지만 의미있는 답변 저장 (시도 {attempt + 1})")

                # 재시도 조건
                retry_count += 1
                if attempt < max_retries:
                    self.logger.warning(f"인용 없는 응답, 재시도 {attempt + 1}/{max_retries}")
                    # REMOVED: 실제 filename 있을 때만 인용하므로 placeholder 불필요
                    continue

            except Exception as e:
                self.logger.error(f"응답 생성 실패 (시도 {attempt + 1}): {e}")
                retry_count += 1

                if attempt < max_retries:
                    continue

        # 모든 재시도 완료 - 최선의 답변 반환 + 출처 강제 추가
        if best_answer and len(best_answer["answer"]) > 10:
            self.logger.info("인용 없는 답변 → 출처 강제 추가")

            # 사용된 문서 출처 강제 추가
            answer_with_sources = best_answer["answer"]

            # 이미 인용이 있는지 다시 확인
            has_any_citation = "[" in answer_with_sources and ".pdf]" in answer_with_sources

            if not has_any_citation:
                # 상위 2개 문서 출처 강제 추가
                top_sources = [chunk.get("source", "") for chunk in context_chunks[:2] if chunk.get("source")]
                if top_sources:
                    sources_text = ", ".join([f"[{src}]" for src in top_sources])
                    answer_with_sources += f"\n\n출처: {sources_text}"
                    self.logger.info(f"출처 강제 추가 완료: {len(top_sources)}개")

            return RAGResponse(
                answer=answer_with_sources,
                sources_cited=[self._get_chunk_source(chunk) for chunk in context_chunks[:2]],  # 상위 2개 문서
                confidence=self._calculate_confidence(answer_with_sources, context_chunks) * 0.8,  # 신뢰도 약간 감소
                generation_time=best_answer["generation_time"],
                has_proper_citation=True,  # 강제 추가했으므로 True
                retry_count=best_answer["retry_count"],
            )

        # 완전 실패 - 하지만 context_chunks가 있으면 기본 요약 제공
        generation_time = time.time() - start_time

        # 🔥 CRITICAL: 검색 결과(context_chunks)가 있으면 "없음" 메시지 금지
        if context_chunks and len(context_chunks) > 0:
            self.logger.warning(f"LLM 생성 실패했지만 context_chunks={len(context_chunks)}개 있음 → 기본 요약 제공")

            # 검색 결과를 기반으로 간단한 요약 생성
            summary_parts = []
            for i, chunk in enumerate(context_chunks[:3], 1):
                # 소스 추출 (다양한 필드 검색)
                filename = self._get_chunk_source(chunk)
                if not filename:
                    # 폴백: 청크에서 제목/doc_id 추출 시도
                    filename = (chunk.get("title")
                                or chunk.get("meta", {}).get("title")
                                or f"문서 {i}")
                # 🔥 CRITICAL: Support both 'content' and 'snippet' fields
                content_preview = ((chunk.get("content") or chunk.get("snippet", ""))[:200] or "(내용 없음)")
                summary_parts.append(f"{i}. {filename}\n{content_preview}...")

            basic_summary = f"다음 {len(context_chunks[:3])}개 문서에서 관련 정보를 찾았습니다:\n\n" + "\n\n".join(summary_parts)

            # 출처 추가
            top_sources = [self._get_chunk_source(chunk) for chunk in context_chunks[:2] if self._get_chunk_source(chunk)]
            if top_sources:
                sources_text = ", ".join([f"[{src}]" for src in top_sources])
                basic_summary += f"\n\n출처: {sources_text}"

            return RAGResponse(
                answer=basic_summary,
                sources_cited=top_sources,
                confidence=0.3,  # 낮은 신뢰도지만 검색 결과는 있음
                generation_time=generation_time,
                has_proper_citation=bool(top_sources),
                retry_count=retry_count,
            )

        # 정말로 context_chunks가 없는 경우에만 "없음" 메시지
        return RAGResponse(
            answer="검색된 관련 문서가 없습니다.",
            sources_cited=[],
            confidence=0.0,
            generation_time=generation_time,
            has_proper_citation=False,
            retry_count=retry_count,
        )

    def _generate_structured_response(self, question_analysis: dict[str, Any],
                                    context_chunks: list[dict[str, Any]],
                                    max_retries: int = 2) -> RAGResponse:
        """구조화된 복합 질문 응답 생성"""

        start_time = time.time()
        retry_count = 0

        # 복합 질문의 특별 처리 (품질 우선으로 재시도 횟수 증가)
        quality_retries = max_retries + 1  # 품질을 위해 재시도 1회 추가

        q_type = question_analysis.get("question_type")
        if q_type == QuestionType.COMPARISON:
            return self._handle_comparison_question(question_analysis, context_chunks, quality_retries)
        if q_type == QuestionType.ANALYSIS:
            return self._handle_analysis_question(question_analysis, context_chunks, quality_retries)
        if q_type == QuestionType.COMPLEX_MULTI:
            return self._handle_complex_multi_question(question_analysis, context_chunks, quality_retries)

        # 일반적인 구조화된 처리
        answer_templates = getattr(self, "answer_templates", None)
        if answer_templates is None:
            # answer_templates가 없으면 기본 응답 생성으로 폴백
            return self.generate_response(
                question_analysis.get("original_question", ""),
                context_chunks,
                max_retries=MAX_LLM_RETRY,
                enable_complex_processing=False,
            )
        structured_prompt = answer_templates.generate_structured_prompt(question_analysis, context_chunks)
        template = answer_templates.get_template(q_type)

        for attempt in range(max_retries + 1):
            try:
                # 시스템 프롬프트에 구조화된 지침 추가
                enhanced_system_prompt = self.create_system_prompt() + f"""

🎯 특별 지침 (질문 유형: {q_type.value if q_type else "GENERAL"}):
- 최대 {template.max_length}자 이내
- 템플릿 구조: {template.structure}
- 필수 요소: {', '.join(template.required_fields)}

예시 답변: {template.example}"""

                messages = [
                    {"role": "system", "content": enhanced_system_prompt},
                    {"role": "user", "content": structured_prompt},
                ]

                raw_answer = self._chat_complete(
                    messages,
                    max_tokens=min(self.config.max_tokens, template.max_length + 50),
                )
                # 외국어 텍스트 필터링
                raw_answer = self._remove_foreign_text(raw_answer)
                generation_time = time.time() - start_time

                # 답변 후처리 및 검증
                processed_answer = answer_templates.post_process_answer(raw_answer, question_analysis)
                validation = answer_templates.validate_answer_structure(processed_answer, template)

                # 인용 검증
                citation_check = self._validate_citations(processed_answer, context_chunks)

                # 구조화된 답변 반환
                confidence = self._calculate_confidence(processed_answer, context_chunks)

                # 검증 실패 시 신뢰도 감소
                if not validation["is_valid"]:
                    confidence *= 0.8
                    self.logger.warning(f"구조 검증 실패: {validation['issues']}")

                return RAGResponse(
                    answer=processed_answer,
                    sources_cited=citation_check["cited_files"],
                    confidence=confidence,
                    generation_time=generation_time,
                    has_proper_citation=citation_check["has_citations"],
                    retry_count=retry_count,
                )

            except Exception as e:
                self.logger.error(f"구조화된 응답 생성 실패 (시도 {attempt + 1}): {e}")
                retry_count += 1

                if attempt < max_retries:
                    continue

        # 구조화된 처리 실패 시 기본 모드로 폴백
        self.logger.warning("구조화된 처리 실패, 기본 모드로 폴백")
        original_q = question_analysis.get("original_question", "")
        return self.generate_response(original_q, context_chunks,
                                    max_retries=MAX_LLM_RETRY, enable_complex_processing=False)

    def _handle_comparison_question(self, question_analysis: dict[str, Any],
                                  context_chunks: list[dict[str, Any]],
                                  max_retries: Optional[int] = None) -> RAGResponse:
        """비교 질문 특별 처리"""

        # .env에서 읽은 값 사용
        if max_retries is None:
            max_retries = MAX_LLM_RETRY

        # 단일 문서 모드 강화 - 가장 관련성 높은 문서만 사용
        if context_chunks:
            best_chunk = context_chunks[0]  # 최고 점수 문서
            best_source = self._get_chunk_source(best_chunk)
            filtered_chunks = [chunk for chunk in context_chunks
                             if self._get_chunk_source(chunk) == best_source]

            self.logger.info(f"비교 질문: 단일 문서 모드 적용 - {Path(best_source).name if best_source else '(unknown)'}")
            context_chunks = filtered_chunks[:3]  # 최대 3개 청크만 사용

        original_question = question_analysis.get("original_question", "")
        comparison_targets = question_analysis.get("comparison_targets", [])
        enhanced_prompt = f"""질문: {original_question}

🎯 비교 질문 전용 지침 (품질 최우선):
1. 비교 대상: {', '.join(comparison_targets) if comparison_targets else '문서에서 찾아서 비교'}
2. 🚨 절대 중요: 문서에 정확히 명시된 숫자만 사용하세요 - 추정/변형 절대 금지
3. 각 항목의 구체적 수치를 문서에서 정확히 복사하여 사용
4. "A는 X, B는 Y입니다" 형식으로 명확한 대조 구조
5. 단일 문서 기준으로만 비교 (정보 혼합 절대 금지)
6. 숫자가 불분명하면 비교하지 말고 찾을 수 있는 정보만 제공

⚠️ 환각 방지 규칙:
- 문서에 없는 숫자 절대 생성 금지
- 대략적인 계산이나 추정 금지
- 의심스러우면 "문서에서 확인된 정보만 제공"

참고 문서 (단일 문서 모드):"""

        max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "5000"))
        for i, chunk in enumerate(context_chunks[:2], 1):  # 최대 2개만 사용
            filename = Path(self._get_chunk_source(chunk)).name
            # 폴백 체인: text → content → snippet → text_preview
            content = (chunk.get("text") or chunk.get("content") or
                      chunk.get("snippet") or chunk.get("text_preview") or "")[:max_context_chars]
            score = chunk.get("score", 0.0)

            enhanced_prompt += f"\n--- 청크 {i}: {filename} (점수: {score:.3f}) ---\n{content}..."

        enhanced_prompt += """

🎯 비교 답변 템플릿 (정확성 최우선):
문서에서 찾은 정확한 정보를 바탕으로 자연스럽게 비교하여 답변하세요. [파일명.pdf]

🔍 답변 작성 단계:
1. 문서에서 첫 번째 항목의 정확한 숫자 찾기
2. 문서에서 두 번째 항목의 정확한 숫자 찾기
3. 찾은 숫자를 정확히 복사하여 비교문 작성
4. 숫자를 찾을 수 없으면 해당 항목은 "문서에서 확인되지 않음" 명시

🚨 절대 금지: 추측, 계산, 반올림, 근사치 사용 금지
✅ 허용: 문서에 명시된 정확한 숫자만 사용"""

        return self._generate_with_enhanced_prompt(enhanced_prompt, context_chunks, max_retries, "비교")

    def _handle_analysis_question(self, question_analysis: dict[str, Any],
                                context_chunks: list[dict[str, Any]],
                                max_retries: int = 2) -> RAGResponse:
        """분석 질문 특별 처리"""

        original_question = question_analysis.get("original_question", "")
        enhanced_prompt = f"""질문: {original_question}

🎯 분석 질문 전용 지침 (품질 최우선):
1. 🔍 모든 관련 데이터를 철저히 검토하여 최대값/최소값/평균값 정확히 찾기
2. 🚨 문서에서 정확히 확인된 숫자만 사용 - 추정 절대 금지
3. "X가 가장 [기준]입니다" 형식으로 결론 명확히 제시
4. 구체적 근거 데이터와 수치 반드시 포함
5. 비교 대상이 여러 개인 경우 모든 항목 검토 후 판단

⚠️ 분석 정확성 보장:
- 모든 후보를 나열하고 비교
- 가장 높은/낮은 수치를 정확히 식별
- 동일한 기준으로 비교 (가격은 가격끼리, 수량은 수량끼리)
- 확실하지 않으면 "검토 가능한 범위에서" 명시

참고 문서:"""

        max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "5000"))
        for i, chunk in enumerate(context_chunks[:3], 1):
            filename = Path(self._get_chunk_source(chunk)).name
            # 폴백 체인: text → content → snippet → text_preview
            content = (chunk.get("text") or chunk.get("content") or
                      chunk.get("snippet") or chunk.get("text_preview") or "")[:max_context_chars]
            score = chunk.get("score", 0.0)

            enhanced_prompt += f"\n--- 문서 {i}: {filename} (점수: {score:.3f}) ---\n{content}..."

        enhanced_prompt += """

🎯 분석 답변 템플릿:
"[결과]가 가장 [기준]입니다. [구체적근거] [파일명.pdf]"

중요: 모든 데이터를 비교 검토한 후 정확한 결론을 도출하세요."""

        return self._generate_with_enhanced_prompt(enhanced_prompt, context_chunks, max_retries, "분석")

    def _handle_complex_multi_question(self, question_analysis: dict[str, Any],
                                     context_chunks: list[dict[str, Any]],
                                     max_retries: int = 2) -> RAGResponse:
        """복합 다중 질문 특별 처리"""

        original_question = question_analysis.get("original_question", "")
        required_info_types = question_analysis.get("required_info_types", [])
        enhanced_prompt = f"""질문: {original_question}

🎯 복합 질문 전용 지침:
1. 질문을 단계별로 분해하여 처리
2. 각 단계별 답변을 통합
3. 정보가 부족한 부분은 명시
4. 요약 + 세부사항 구조

필요 정보 유형: {', '.join(required_info_types)}

참고 문서:"""

        max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "5000"))
        for i, chunk in enumerate(context_chunks[:4], 1):  # 복합 질문은 최대 4개 문서
            filename = Path(self._get_chunk_source(chunk)).name
            # 폴백 체인: text → content → snippet → text_preview
            content = (chunk.get("text") or chunk.get("content") or
                      chunk.get("snippet") or chunk.get("text_preview") or "")[:max_context_chars]
            score = chunk.get("score", 0.0)

            enhanced_prompt += f"\n--- 문서 {i}: {filename} (점수: {score:.3f}) ---\n{content}..."

        enhanced_prompt += """

🎯 복합 답변 템플릿:
"[요약답변] [세부사항1] [세부사항2] [파일명.pdf]"

중요: 각 요구사항을 체계적으로 확인하고 통합된 답변을 제공하세요."""

        return self._generate_with_enhanced_prompt(enhanced_prompt, context_chunks, max_retries, "복합")

    def _generate_with_enhanced_prompt(self, enhanced_prompt: str, context_chunks: list[dict[str, Any]],
                                     max_retries: int, question_type_name: str) -> RAGResponse:
        """향상된 프롬프트로 응답 생성 (품질 최우선 매개변수)"""

        start_time = time.time()

        # 품질 중심 시스템 프롬프트 강화
        quality_focused_system_prompt = self.create_system_prompt() + """

🎯 **문서 활용 최우선 원칙**:
1. 제공된 문서의 정보를 적극적으로 활용하여 답변
2. 문서에서 찾을 수 있는 모든 관련 정보를 종합하여 활용
3. 구체적인 숫자, 날짜, 모델명을 문서에서 정확히 추출
4. 문서 내용을 바탕으로 완전하고 유용한 답변 제공
5. 출처를 정확한 파일명으로 반드시 인용

💡 사용자 도움 최우선: 문서가 제공되면 그 내용을 최대한 활용하여 도움이 되는 답변 제공"""

        for attempt in range(max_retries + 1):
            try:
                messages = [
                    {"role": "system", "content": quality_focused_system_prompt},
                    {"role": "user", "content": enhanced_prompt},
                ]

                answer = self._chat_complete(messages, max_tokens=self.config.max_tokens)
                # 외국어 텍스트 필터링
                answer = self._remove_foreign_text(answer)
                generation_time = time.time() - start_time

                # 인용 검증
                citation_check = self._validate_citations(answer, context_chunks)

                self.logger.info(f"{question_type_name} 질문 처리 완료: {len(answer)}자, 인용: {citation_check['has_citations']}")

                return RAGResponse(
                    answer=answer,
                    sources_cited=citation_check["cited_files"],
                    confidence=self._calculate_confidence(answer, context_chunks),
                    generation_time=generation_time,
                    has_proper_citation=citation_check["has_citations"],
                    retry_count=attempt,
                )

            except Exception as e:
                self.logger.error(f"{question_type_name} 질문 처리 실패 (시도 {attempt + 1}): {e}")
                if attempt < max_retries:
                    continue

        # 완전 실패 시 기본 오류 응답
        return RAGResponse(
            answer=f"{question_type_name} 질문 처리 중 오류가 발생했습니다.",
            sources_cited=[],
            confidence=0.0,
            generation_time=time.time() - start_time,
            has_proper_citation=False,
            retry_count=max_retries,
        )

    def _prioritize_same_document_chunks(self, context_chunks: list[dict[str, Any]], max_chunks: int = 10) -> list[dict[str, Any]]:
        """같은 문서의 청크들을 우선적으로 선택하여 포괄적 정보 제공"""
        if not context_chunks:
            return context_chunks

        # 가장 점수가 높은 문서 찾기
        best_chunk = context_chunks[0]
        best_source = self._get_chunk_source(best_chunk)

        # DEBUG: 첫 번째 청크의 키 확인
        self.logger.info(f"📦 First chunk keys: {list(best_chunk.keys())}")
        # DEBUG: 텍스트 필드 확인
        for key in ["text", "content", "snippet", "text_preview", "page_content"]:
            value = best_chunk.get(key)
            if value:
                preview = str(value)[:80].replace("\n", " ")
                self.logger.info(f"   ✓ {key}: {preview}...")
            else:
                # Show the actual value (even if empty string)
                self.logger.info(f"   ✗ {key}: {value!r}")

        self.logger.info(f"우선 문서: {Path(best_source).name if best_source else '(unknown)'}")

        # 같은 문서의 모든 청크와 다른 문서의 청크 분리
        same_doc_chunks = []
        other_doc_chunks = []

        for chunk in context_chunks:
            chunk_source = self._get_chunk_source(chunk)
            if chunk_source == best_source:
                same_doc_chunks.append(chunk)
            else:
                other_doc_chunks.append(chunk)

        # 같은 문서 청크 우선 + 다른 문서 청크로 최대 max_chunks개까지 구성
        prioritized_chunks = same_doc_chunks[:max_chunks]  # 같은 문서 청크 먼저

        # 남은 공간에 다른 문서 청크 추가
        remaining_slots = max_chunks - len(prioritized_chunks)
        if remaining_slots > 0:
            prioritized_chunks.extend(other_doc_chunks[:remaining_slots])

        self.logger.info(f"청크 선택: 같은 문서 {len(same_doc_chunks)}개, 다른 문서 {len(other_doc_chunks)}개 → 총 {len(prioritized_chunks)}개 사용")

        return prioritized_chunks

    def _remove_foreign_text(self, text: str) -> str:
        """외국어 텍스트 제거 헬퍼 메서드"""
        # 1. 중국어 문자 범위 (CJK 통합 한자 + 확장)
        chinese_pattern = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]"
        # 2. 일본어 히라가나/카타카나
        japanese_pattern = r"[\u3040-\u309f\u30a0-\u30ff]"
        # 3. 중국어 구두점 및 특수문자
        chinese_punctuation = r"[。，、；：？！…—·「」『』（）【】《》〈〉]"

        # 라인별 필터링
        lines = text.split("\n")
        filtered_lines = []

        for line in lines:
            # 외국어가 없는 라인만 유지
            if not (re.search(chinese_pattern, line) or
                   re.search(japanese_pattern, line) or
                   re.search(chinese_punctuation, line)):
                filtered_lines.append(line)

        result = "\n".join(filtered_lines)

        # 빈 줄 정리
        result = re.sub(r"\n\n+", "\n\n", result)

        return result.strip()

    def _validate_citations(self, answer: str, context_chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """인용 유효성 검증"""
        cited_files = []
        available_files = set()

        # 사용 가능한 파일명 수집
        for chunk in context_chunks:
            source = self._get_chunk_source(chunk)
            if source:
                filename = Path(source).name
                available_files.add(filename)

        # 답변에서 인용 추출 (컴파일된 패턴 사용)
        for pattern in self.citation_patterns:
            matches = pattern.findall(answer)
            for match in matches:
                # 파일명 정리
                filename = match.strip()
                if filename.endswith(".pdf") and filename not in cited_files:
                    cited_files.append(filename)

        # 인용 검증
        valid_citations = []
        for cited_file in cited_files:
            # 정확한 파일명 매칭 또는 부분 매칭
            is_valid = any(
                cited_file == available_file or
                cited_file in available_file or
                available_file in cited_file
                for available_file in available_files
            )

            if is_valid:
                valid_citations.append(cited_file)

        return {
            "has_citations": len(valid_citations) > 0,
            "cited_files": valid_citations,
            "invalid_citations": [f for f in cited_files if f not in valid_citations],
            "citation_count": len(cited_files),
        }

    def _is_meaningful_answer(self, answer: str) -> bool:
        """의미있는 답변인지 판단 (문서 활용 중심)"""

        # 너무 짧은 답변 제외
        if len(answer.strip()) < 15:
            return False

        # 완전 거부 표현들만 제외 (부분적 정보라도 의미 있음)
        # 2025-12-09: 되물음/질문 표현 추가 (LLM이 답변 대신 질문하는 경우)
        rejection_phrases = [
            "답변을 드릴 수 없습니다",
            "전혀 찾을 수 없습니다",
            "완전히 알 수 없습니다",
            # 되물음/질문 표현 (LLM이 답변 대신 질문하는 경우)
            "알려줄 수 있나요",
            "알려드릴 수 있나요",
            "알려주실 수 있나요",
            "확인해 주시겠어요",
            "다시 질문해 주시겠어요",
            "더 구체적으로",
            "어떤 정보를 원하시",
            "무엇을 알고 싶으신",
        ]

        # 2025-12-09: 프롬프트 반복 감지 (LLM이 프롬프트를 그대로 출력하는 경우)
        if "참고 문서:" in answer or "--- 문서 " in answer or "(관련도:" in answer:
            self.logger.warning("⚠️ LLM이 프롬프트 내용을 반복함 → 의미 없는 답변으로 처리")
            return False

        answer_lower = answer.lower()
        for phrase in rejection_phrases:
            if phrase in answer_lower:
                return False

        # 구체적 정보나 문서 활용 신호 체크
        meaningful_patterns = [
            r"\d{4}년",  # 연도
            r"\d{1,3}(?:,\d{3})*원",  # 금액
            r"\d{1,3}(?:,\d{3})*만원",  # 만원
            r"\d+만",  # 간단한 만 단위
            r"\d+원",   # 간단한 원 단위
            r"HP\s*Z8",  # 제품명
            r"워크스테이션",  # 장비명
            r"카메라",  # 장비명
            r"모니터",  # 장비명
            r"광화문",  # 장소명
            r"스튜디오",  # 장소명
            r"ECM-77BC",  # 마이크 모델
            r"티비로직",  # 브랜드명
            r"뷰파인더",  # 장비명
            r"소모품",  # 카테고리
            r"케이블",  # 품목
            r"기안자",  # 문서 요소
            r"검토",    # 문서 유형
            r"승인",    # 문서 상태
            r"구매",    # 업무 유형
            r"교체",    # 업무 유형
        ]

        meaningful_count = 0
        for pattern in meaningful_patterns:
            if re.search(pattern, answer):
                meaningful_count += 1

        # 구체적 정보가 1개 이상 있으면 의미있는 답변으로 간주 (더 관대하게)
        return meaningful_count >= 1

    def _apply_length_preference_adjustments(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        """길이 선호도에 따른 조정 적용"""

        # 길이 선호도별 조정 비율
        length_multipliers = {
            "concise": 0.7,     # 30% 짧게
            "balanced": 1.0,    # 기본값
            "detailed": 1.4,     # 40% 길게
        }

        multiplier = length_multipliers.get(self.config.length_preference, 1.0)

        # 조정된 길이 계산 (dict 접근 방식 사용)
        optimal_length = recommendation.get("optimal_length", 150)
        min_length = recommendation.get("min_length", 50)
        max_length = recommendation.get("max_length", 300)
        adjusted_optimal = int(optimal_length * multiplier)
        adjusted_min = int(min_length * multiplier)
        adjusted_max = int(max_length * multiplier)

        # 사용자 강제 설정 적용
        if self.config.min_length_override:
            adjusted_min = max(adjusted_min, self.config.min_length_override)
        if self.config.max_length_override:
            adjusted_max = min(adjusted_max, self.config.max_length_override)

        # 최소-최대 범위 보정
        adjusted_optimal = max(adjusted_min, min(adjusted_optimal, adjusted_max))

        reasoning = recommendation.get("reasoning", "표준 길이")
        content_density = recommendation.get("content_density", 0.5)
        adjustment_factors = recommendation.get("adjustment_factors", [])
        return dict(
            optimal_length=adjusted_optimal,
            min_length=adjusted_min,
            max_length=adjusted_max,
            reasoning=reasoning + f" | 선호도 조정: {self.config.length_preference} (x{multiplier})",
            content_density=content_density,
            adjustment_factors=adjustment_factors + [f"길이선호도_{self.config.length_preference}"],
        )

    def _calculate_adaptive_max_tokens(self, recommendation: dict[str, Any]) -> int:
        """적응형 길이 추천에 따른 max_tokens 계산"""
        # 한국어 기준: 대략 1.5토큰/글자 (여유를 위해 2.0 사용)
        tokens_per_char = 2.0

        # 목표 길이에서 토큰 수 계산 (여유분 20% 추가)
        # recommendation이 dict일 수도 있고 object일 수도 있으므로 안전하게 처리
        max_length = recommendation.get("max_length") if isinstance(recommendation, dict) else getattr(recommendation, "max_length", 200)
        adaptive_tokens = int(max_length * tokens_per_char * 1.2)

        # 최소/최대 토큰 수 제한 (환경변수 지원)
        min_tokens = int(os.getenv("ADAPTIVE_MIN_TOKENS", "50"))
        max_tokens = int(os.getenv("ADAPTIVE_MAX_TOKENS", "800"))

        return max(min_tokens, min(adaptive_tokens, max_tokens))

    def _create_adaptive_system_prompt(self, recommendation: dict[str, Any]) -> str:
        """적응형 길이 기반 시스템 프롬프트 생성"""
        base_prompt = self.create_system_prompt()

        # recommendation이 dict일 수도 있고 object일 수도 있으므로 안전하게 처리
        if isinstance(recommendation, dict):
            optimal_length = recommendation.get("optimal_length", 150)
            min_length = recommendation.get("min_length", 50)
            max_length = recommendation.get("max_length", 300)
            content_density = recommendation.get("content_density", 0.5)
            reasoning = recommendation.get("reasoning", "표준 길이")
        else:
            optimal_length = getattr(recommendation, "optimal_length", 150)
            min_length = getattr(recommendation, "min_length", 50)
            max_length = getattr(recommendation, "max_length", 300)
            content_density = getattr(recommendation, "content_density", 0.5)
            reasoning = getattr(recommendation, "reasoning", "표준 길이")

        adaptive_instructions = f"""

🎯 **적응형 답변 길이 가이드라인**:
- 목표 길이: {optimal_length}자
- 허용 범위: {min_length}-{max_length}자
- 콘텐츠 밀도: {content_density:.2f}
- 조정 이유: {reasoning}

📏 **길이 조정 원칙**:
1. 정확성과 완전성을 우선으로 하되, 가능한 목표 길이에 맞추세요
2. 필수 정보 (가격, 날짜, 모델명 등)는 길이와 상관없이 포함하세요
3. 부가 설명은 목표 길이에 따라 조절하세요
4. 출처 인용은 반드시 포함하세요 (길이에 포함되지 않음)

⚡ **효율적 답변 구성**:
- 짧은 답변({min_length}자 미만): 핵심 사실만
- 적당한 답변({min_length}-{optimal_length}자): 핵심 + 간단한 설명
- 긴 답변({optimal_length}자 이상): 상세 설명 + 배경 정보"""

        return base_prompt + adaptive_instructions

    def _generate_structured_response_with_adaptive_length(self, question_analysis: dict[str, Any],
                                                         context_chunks: list[dict[str, Any]],
                                                         max_retries: int,
                                                         length_recommendation: Optional[dict[str, Any]] = None) -> RAGResponse:
        """적응형 길이 조정을 포함한 구조화된 답변 생성"""

        # 기존 구조화된 응답 생성 (길이 조정 없이)
        base_response = self._generate_structured_response(question_analysis, context_chunks, max_retries)

        # 적응형 길이 조정이 비활성화되어 있으면 그대로 반환
        if not self.config.enable_adaptive_length or not length_recommendation:
            return base_response

        # 길이 조정 적용
        original_length = len(base_response.answer)
        if self.length_analyzer is None:
            return base_response
        adjusted_answer, length_adjustments = self.length_analyzer.validate_and_adjust_answer(
            base_response.answer, length_recommendation)

        # 적응형 정보가 추가된 새로운 RAGResponse 생성
        return RAGResponse(
            answer=adjusted_answer,
            sources_cited=base_response.sources_cited,
            confidence=base_response.confidence,
            generation_time=base_response.generation_time,
            has_proper_citation=base_response.has_proper_citation,
            retry_count=base_response.retry_count,
            length_recommendation=length_recommendation,
            original_length=original_length,
            length_adjustments=length_adjustments,
            adaptive_length_used=True,
        )

    def _calculate_confidence(self, answer: str, context_chunks: list[dict[str, Any]]) -> float:
        """답변 신뢰도 계산"""
        if not context_chunks:
            return 0.0

        # 기본 신뢰도는 최고 스코어 청크의 점수
        base_confidence = max(chunk.get("score", 0.0) for chunk in context_chunks)

        # 인용 보너스
        citation_check = self._validate_citations(answer, context_chunks)
        citation_bonus = min(0.2, len(citation_check["cited_files"]) * 0.1)

        # 답변 길이 고려 (너무 짧거나 긴 답변은 신뢰도 감소)
        length_penalty = 0.0
        answer_length = len(answer)
        if answer_length < 50:
            length_penalty = 0.1
        elif answer_length > 1000:
            length_penalty = 0.05

        # 부정 표현 감지 ("찾을 수 없습니다" 등)
        negative_phrases = ["찾을 수 없", "확인할 수 없", "명시되지 않", "불분명"]
        negative_penalty = 0.0
        for phrase in negative_phrases:
            if phrase in answer:
                negative_penalty = 0.2
                break

        confidence = base_confidence + citation_bonus - length_penalty - negative_penalty
        return max(0.0, min(1.0, confidence))

    def generate_conversational_response(self, question: str, context_chunks: list[dict[str, Any]],
                                        max_retries: int = 2) -> RAGResponse:
        """대화형 응답 생성 (ChatGPT/Claude 스타일)"""

        start_time = time.time()

        # 대화형 시스템 프롬프트 - 한국어 전용 강화
        conversational_system = """당신은 친절하고 유능한 한국어 AI 어시스턴트입니다. ChatGPT나 Claude처럼 자연스럽게 대화하세요.

🚫 절대 규칙: 오직 한국어로만 답변하세요. 중국어(中文), 영어(English), 일본어 등 다른 언어는 절대 사용하지 마세요.

중요 원칙:
1. 100% 한국어로만 자연스럽고 친근하게 답변하세요
2. 템플릿이나 정형화된 형식을 사용하지 마세요
3. 사용자의 의도를 파악하여 실제로 도움이 되는 정보를 제공하세요
4. 필요하면 추가 정보나 대안을 자연스럽게 제안하세요
5. 의사결정에 도움이 되는 인사이트를 제공하세요
6. 출처는 자연스럽게 문장 속에 녹여서 언급하세요

답변 스타일:
- 대화하듯 자연스럽게
- 핵심을 먼저, 세부사항은 이어서
- 실용적이고 actionable한 정보 제공
- 필요시 장단점이나 고려사항 언급

⚠️ 다시 한번 강조: 절대로 중국어나 다른 언어를 사용하지 마세요. 오직 한국어만 사용하세요."""

        # 컨텍스트 구성 - 자연스러운 대화형 답변을 위한 컨텍스트
        context_parts = []
        for chunk in context_chunks[:5]:
            # 폴백 체인: text → content → snippet → text_preview
            content = (chunk.get("text") or chunk.get("content") or
                      chunk.get("snippet") or chunk.get("text_preview") or "").strip()
            source = self._get_chunk_source(chunk) or "unknown"

            if content:
                context_parts.append(f"[{source}]\n{content}")

        context = "\n\n".join(context_parts)

        conversational_prompt = f"""다음 정보를 참고하여 사용자 질문에 자연스럽게 답변해주세요:

{context}

사용자 질문: {question}

답변 방식:
- ChatGPT나 Claude처럼 자연스럽게 대화하듯 답변
- 핵심 내용을 먼저 간단히 설명한 후 세부사항 제공
- 도움이 될 만한 추가 정보나 고려사항도 언급
- 출처는 자연스럽게 문장 속에 포함 (예: '구매기안서에 따르면...')
- 딱딱한 리스트나 템플릿 형식 사용 금지

⚠️ 중요 지침:
- 제공된 문서 정보에 있는 내용만 사용하세요
- 금액은 문서에 명시된 정확한 금액만 언급하세요
- 추측하거나 없는 정보를 만들어내지 마세요
- 확실하지 않은 정보는 언급하지 마세요

🚨 필수: 오직 한국어로만 답변하세요. 중국어(中文/汉字), 영어, 일본어 등 다른 언어는 절대 사용 금지!
답변 언어: 한국어 (Korean Only)"""

        retry_count = 0
        best_answer = None

        for attempt in range(max_retries + 1):
            try:
                messages = [
                    {"role": "system", "content": conversational_system},
                    {"role": "user", "content": conversational_prompt},
                ]

                answer = self._chat_complete(
                    messages,
                    max_tokens=int(os.getenv(
                        "CONVERSATIONAL_MAX_TOKENS",
                        str(LLMWrapperConfig.CONVERSATIONAL_MAX_TOKENS),
                    )),
                    temperature=LLMWrapperConfig.CONVERSATIONAL_TEMPERATURE,
                    top_p=LLMWrapperConfig.CONVERSATIONAL_TOP_P,
                    top_k=40,
                    repeat_penalty=1.1,
                )

                # 외국어 텍스트 필터링 (헬퍼 메서드 사용)
                answer = self._remove_foreign_text(answer)

                best_answer = answer

                # 출처 추출 (자연스럽게 포함된 경우도 처리)
                sources_cited = []
                for pattern in self.citation_patterns:
                    matches = re.findall(pattern, answer)
                    sources_cited.extend(matches)

                sources_cited = list(set(sources_cited))  # 중복 제거

                generation_time = time.time() - start_time

                return RAGResponse(
                    answer=answer,
                    sources_cited=sources_cited,
                    confidence=0.85,
                    generation_time=generation_time,
                    has_proper_citation=len(sources_cited) > 0,
                    retry_count=retry_count,
                )

            except Exception as e:
                self.logger.error(f"대화형 응답 생성 실패 (시도 {attempt + 1}): {e}")
                retry_count += 1
                if attempt == max_retries:
                    break

        # 실패 시 기본 응답
        if best_answer:
            return RAGResponse(
                answer=best_answer,
                sources_cited=[],
                confidence=0.5,
                generation_time=time.time() - start_time,
                has_proper_citation=False,
                retry_count=retry_count,
            )

        return RAGResponse(
            answer="요청하신 정보를 처리하는 중 문제가 발생했습니다.",
            sources_cited=[],
            confidence=0.0,
            generation_time=time.time() - start_time,
            has_proper_citation=False,
            retry_count=retry_count,
        )

    def generate_smart_response(self, question: str, search_result: dict[str, Any], max_retries: int = 2) -> RAGResponse:
        """스마트 모드 응답 생성: 검색 결과에 따라 적절한 방식으로 답변 생성"""

        if not search_result.get("success", False):
            # 검색 실패시 기본 오류 응답
            return RAGResponse(
                answer=search_result.get("error", "관련 정보를 찾을 수 없습니다."),
                sources_cited=[],
                confidence=0.0,
                generation_time=0.0,
                has_proper_citation=False,
                retry_count=0,
            )

        mode = search_result.get("mode", "chunk_search")
        start_time = time.time()

        if mode == "full_document":
            # 전체 문서 모드
            return self._generate_full_document_response(question, search_result, max_retries, start_time)
        # 청크 검색 모드 (기존 방식)
        search_results = search_result.get("search_results", {})
        context_chunks = search_results.get("fused_results", [])
        return self.generate_response(question, context_chunks, max_retries)

    def _generate_full_document_response(self, question: str, search_result: dict[str, Any],
                                       max_retries: int, start_time: float) -> RAGResponse:
        """전체 문서 모드 응답 생성"""

        full_doc_chunk = search_result.get("full_document_chunk", {})
        document_path = search_result.get("document_path", "")
        document_text = full_doc_chunk.get("content", "")

        if not document_text:
            generation_time = time.time() - start_time
            return RAGResponse(
                answer="문서 내용을 읽을 수 없습니다.",
                sources_cited=[],
                confidence=0.0,
                generation_time=generation_time,
                has_proper_citation=False,
                retry_count=0,
            )

        # 전체 문서 전용 프롬프트 생성
        full_doc_prompt = self.create_full_document_prompt(question, document_text, document_path)

        retry_count = 0
        best_answer = None

        for attempt in range(max_retries + 1):
            try:
                # 전체 문서 모드용 시스템 프롬프트 (간단하고 직접적)
                system_prompt = """당신은 한국어 문서 분석 어시스턴트입니다.

작업: 제공된 문서를 분석하여 한국어로 완전한 요약을 작성하세요.

규칙:
1. 문서의 모든 정보를 추출하세요: 기안자, 날짜, 금액, 품목
2. 추출한 정보로 완전한 한국어 요약을 작성하세요
3. "정보를 찾을 수 없다" 또는 "확인 불가" 같은 표현 금지
4. 반드시 [파일명.pdf] 형식으로 출처를 표시하세요
5. 오직 한국어로만 답변하세요

예시:
문서 내용: "기안자 남준수, 2025-06-24, 총액 4,985,500원"
답변: "2025년 6월 24일 남준수가 기안한 문서로, 총 4,985,500원의 구매 건입니다. [filename.pdf]"

중요: 문서 내용을 활용하여 유용한 한국어 요약을 만드세요."""

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_doc_prompt},
                ]

                answer = self._chat_complete(
                    messages,
                    max_tokens=LLMWrapperConfig.FULL_DOC_MAX_TOKENS,
                )
                generation_time = time.time() - start_time

                # 첫 번째 답변을 최선의 답변으로 저장
                if best_answer is None and len(answer) > 10:
                    best_answer = {
                        "answer": answer,
                        "generation_time": generation_time,
                        "retry_count": retry_count,
                    }

                # 인용 검증
                citation_check = self._validate_citations(answer, [full_doc_chunk])

                if citation_check["has_citations"]:
                    # 인용이 있는 답변 - 즉시 반환
                    return RAGResponse(
                        answer=answer,
                        sources_cited=citation_check["cited_files"],
                        confidence=self._calculate_confidence(answer, [full_doc_chunk]),
                        generation_time=generation_time,
                        has_proper_citation=True,
                        retry_count=retry_count,
                    )
                # 인용이 없지만 의미있는 답변이면 저장
                if self._is_meaningful_answer(answer):
                    best_answer = {
                        "answer": answer,
                        "generation_time": generation_time,
                        "retry_count": retry_count,
                    }
                    self.logger.info(f"인용 없지만 의미있는 답변 저장 (시도 {attempt + 1})")

                # 재시도
                retry_count += 1
                if attempt < max_retries:
                    self.logger.warning(f"인용 없는 응답, 재시도 {attempt + 1}/{max_retries}")
                    continue

            except Exception as e:
                self.logger.error(f"전체 문서 응답 생성 실패 (시도 {attempt + 1}): {e}")
                retry_count += 1
                if attempt < max_retries:
                    continue

        # 모든 재시도 완료 - 최선의 답변 반환
        if best_answer and len(best_answer["answer"]) > 10:
            return RAGResponse(
                answer=best_answer["answer"],
                sources_cited=[],
                confidence=self._calculate_confidence(best_answer["answer"], [full_doc_chunk]) * LLMWrapperConfig.FULL_DOC_CONFIDENCE_MULTIPLIER,
                generation_time=best_answer["generation_time"],
                has_proper_citation=False,
                retry_count=best_answer["retry_count"],
            )

        # 완전 실패
        generation_time = time.time() - start_time
        return RAGResponse(
            answer="전체 문서 분석 중 오류가 발생했습니다.",
            sources_cited=[],
            confidence=0.0,
            generation_time=generation_time,
            has_proper_citation=False,
            retry_count=retry_count,
        )

    def test_model(self) -> bool:
        """모델 테스트"""
        try:
            test_messages = [
                {"role": "system", "content": "간단한 인사를 해주세요."},
                {"role": "user", "content": "안녕하세요?"},
            ]

            try:
                answer = self._chat_complete(
                    test_messages,
                    max_tokens=LLMWrapperConfig.TEST_MODEL_MAX_TOKENS,
                    temperature=0.1,
                )
            except RuntimeError as e:
                self.logger.error(f"모델 테스트 실패: {e}")
                return False

            self.logger.info(f"모델 테스트 성공: {answer[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"모델 테스트 실패: {e}")
            return False


# 테스트 함수
def test_qwen_llm():
    """Qwen LLM 테스트"""

    # 모델 경로 설정 (실제 모델 파일들을 합쳐서 사용)
    try:
        from config import QWEN_MODEL_PATH
        model_files = [QWEN_MODEL_PATH]
    except ImportError:
        model_files = [
            "./models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
            "./models/qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
        ]

    # 첫 번째 파일만 사용 (테스트용)
    if Path(model_files[0]).exists():
        try:
            qwen = QwenLLM(model_files[0])

            # 기본 테스트
            if qwen.test_model():
                print("✓ Qwen 모델 로드 및 기본 테스트 성공")

            # RAG 테스트
            test_context = [
                {
                    "source": "2025-01-09_광화문스튜디오모니터교체검토서.pdf",
                    "content": "총 검토 금액은 9,760,000원입니다. 모니터 3대와 On-Air Tally 시스템을 포함합니다.",
                    "score": 0.85,
                },
            ]

            response = qwen.generate_response(
                "검토 금액이 얼마인가요?",
                test_context,
            )

            print("\n=== RAG 테스트 결과 ===")
            print(f"답변: {response.answer}")
            print(f"인용 파일: {response.sources_cited}")
            print(f"신뢰도: {response.confidence:.3f}")
            print(f"응답 시간: {response.generation_time:.2f}초")
            print(f"올바른 인용: {response.has_proper_citation}")

        except Exception as e:
            print(f"테스트 실패: {e}")
    else:
        print(f"모델 파일 없음: {model_files[0]}")


class LlamaLLM(BaseRAGLLM):
    """Llama-3.1-Korean-8B-Instruct 모델 (Transformers 기반)"""

    def __init__(self, model_path: str = None, length_analyzer=None):
        super().__init__()  # BaseRAGLLM 초기화
        if model_path is None:
            try:
                from config import LLAMA_MODEL_PATH
                model_path = LLAMA_MODEL_PATH
            except ImportError:
                model_path = "./models/Llama-3.1-Korean-8B-Instruct"
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.length_analyzer = length_analyzer  # length_analyzer 주입 (None 가능)
        self._load_model()

    def _load_model(self):
        """Llama 모델 로드"""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.logger.info(f"Llama 모델 로딩 중: {self.model_path}")

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float32,
            )

            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            self.logger.info("✅ Llama 모델 로딩 완료")

        except Exception as e:
            self.logger.error(f"Llama 모델 로딩 실패: {e}")
            raise

    def generate_response(self, question: str, context_chunks: list[dict[str, Any]]) -> RAGResponse:
        """Llama로 응답 생성"""
        start_time = time.time()

        try:
            # 한국어 특화 프롬프트
            context_text = self._format_context(context_chunks)

            prompt = f"""다음 문서들을 바탕으로 질문에 정확하고 구체적으로 답해주세요.

문서 내용:
{context_text}

질문: {question}

답변 지침:
- 문서에 있는 구체적인 정보를 우선적으로 사용하세요
- "확인되지 않음"이나 "알 수 없습니다" 같은 애매한 답변은 피하세요
- 날짜, 이름, 금액, 부서 등 구체적 정보가 있으면 반드시 포함하세요
- 출처 파일명을 답변 마지막에 명시하세요

답변:"""

            import torch
            from transformers import GenerationConfig

            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)

            with torch.no_grad():
                outputs = self.model.generate(
                    inputs.input_ids,
                    attention_mask=inputs.attention_mask,
                    generation_config=GenerationConfig(
                        max_new_tokens=800,
                        temperature=0.8,
                        top_p=LLMWrapperConfig.STREAMING_TOP_P,
                        do_sample=True,
                        eos_token_id=self.tokenizer.eos_token_id,
                        pad_token_id=self.tokenizer.pad_token_id,
                    ),
                )

            response_text = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

            generation_time = time.time() - start_time

            return RAGResponse(
                answer=response_text.strip(),
                sources_cited=self._extract_sources(context_chunks),
                confidence=LLMWrapperConfig.SEARCH_HIGH_CONFIDENCE,
                generation_time=generation_time,
                has_proper_citation=True,
                retry_count=0,
            )

        except Exception as e:
            self.logger.error(f"Llama 응답 생성 실패: {e}")
            return RAGResponse(
                answer="응답 생성 실패",
                sources_cited=[],
                confidence=0.0,
                generation_time=time.time() - start_time,
                has_proper_citation=False,
                retry_count=0,
            )


class VllmLLM(BaseRAGLLM):
    """vLLM 엔진 기반 LLM (Qwen2.5-72B-Instruct-AWQ on H100)"""

    # 프롬프트 템플릿 (2025-12-21: GPT/Claude 수준 자연스러운 대화 + 출처 인용 강화)
    SYSTEM_ROLE = "한국 방송사의 전문 지식 검색 도우미"
    ANSWER_LANGUAGE = "한국어"
    CITATION_FORMAT = "[파일명.pdf]"

    IMPROVED_SYSTEM_PROMPT = f"""당신은 {SYSTEM_ROLE}입니다. 사용자와 자연스럽게 대화하며 문서 기반으로 정확한 정보를 제공합니다.

[대화 스타일]
- 친근하고 전문적인 톤으로 대화하세요.
- 사용자의 질문 의도를 파악하고 핵심을 명확히 답변하세요.
- 필요시 추가 정보나 관련 맥락을 제공하세요.

[답변 규칙]
1. 첫 문장에서 질문의 핵심 답변을 제시하세요.
2. 문서에 있는 정보만 사용하세요. 추측하지 마세요.
3. 숫자/금액/날짜는 정확하게 인용하세요.
4. ★ 반드시 출처를 [파일명.pdf] 형식으로 명시하세요.
5. 반드시 {ANSWER_LANGUAGE}로 답변하세요.

[출처 인용 - 필수]
- 모든 사실적 주장에는 반드시 출처를 표시하세요.
- 형식: "~입니다. [파일명.pdf]" 또는 "~에 따르면 [파일명.pdf]"
- 출처 없는 답변은 허용되지 않습니다.

[금지사항]
- 문서에 없는 정보 추측 금지
- 출처 없이 사실 주장 금지
- 과장이나 확대해석 금지"""

    IMPROVED_QUERY_TEMPLATE = """참고 문서:
{context}

사용자 질문: {query}

위 문서를 참고하여 사용자 질문에 답변하세요.
- 자연스럽고 이해하기 쉽게 설명하세요.
- 반드시 [파일명.pdf] 형식으로 출처를 인용하세요.
- 문서에 없는 내용은 "해당 정보는 문서에서 확인되지 않습니다"라고 답변하세요.

답변:""".replace("{CITATION_FORMAT}", CITATION_FORMAT)

    def __init__(self, model_path: str = None, config: GenerationConfig = None, length_analyzer=None):
        super().__init__()
        # model_path가 None이면 환경변수에서 가져옴
        if model_path is None:
            model_path = os.getenv("LLM_MODEL_PATH", os.getenv("VLLM_MODEL_PATH", "/home/user/Desktop/AI/AI-CHAT/models"))
        self.model_path = Path(model_path)
        self.config = config or GenerationConfig()
        self.length_analyzer = length_analyzer
        self.llm = None

        # vLLM 설정 로드 (2025-12-21: H100 최적화)
        self.gpu_memory_utilization = float(os.getenv(
            "VLLM_GPU_MEMORY_UTILIZATION",
            str(LLMWrapperConfig.VLLM_GPU_MEMORY_UTILIZATION),
        ))
        self.max_model_len = int(os.getenv(
            "VLLM_MAX_MODEL_LEN",
            str(LLMWrapperConfig.VLLM_MAX_MODEL_LEN),
        ))
        self.tensor_parallel_size = int(os.getenv(
            "VLLM_TENSOR_PARALLEL_SIZE",
            str(LLMWrapperConfig.VLLM_TENSOR_PARALLEL_SIZE),
        ))
        self.trust_remote_code = os.getenv("VLLM_TRUST_REMOTE_CODE", "true").lower() == "true"
        self.enable_prefix_caching = os.getenv("VLLM_ENABLE_PREFIX_CACHING", "true").lower() == "true"
        self.enforce_eager = os.getenv("VLLM_ENFORCE_EAGER", "false").lower() == "true"

        self._load_model()

    def _load_model(self):
        """vLLM 모델 로드"""
        try:
            from vllm import LLM

            self.logger.info(f"🚀 vLLM 모델 로딩 중: {self.model_path}")
            self.logger.info(f"   - GPU 메모리 활용률: {self.gpu_memory_utilization}")
            self.logger.info(f"   - 최대 모델 길이: {self.max_model_len}")
            self.logger.info(f"   - 텐서 병렬화: {self.tensor_parallel_size}")
            self.logger.info(f"   - 프리픽스 캐싱: {self.enable_prefix_caching}")
            self.logger.info(f"   - Eager 모드: {self.enforce_eager}")

            self.llm = LLM(
                model=str(self.model_path),
                gpu_memory_utilization=self.gpu_memory_utilization,
                max_model_len=self.max_model_len,
                tensor_parallel_size=self.tensor_parallel_size,
                trust_remote_code=self.trust_remote_code,
                dtype="float16",  # AWQ 모델용
                quantization="awq",  # AWQ 양자화 명시
                enforce_eager=self.enforce_eager,  # 환경변수로 제어 (false=CUDA 그래프 활성화)
                enable_prefix_caching=self.enable_prefix_caching,  # 프롬프트 캐싱
            )

            self.logger.info("✅ vLLM 모델 로딩 완료 (Qwen2.5-72B-Instruct-AWQ)")

        except Exception as e:
            self.logger.error(f"❌ vLLM 모델 로딩 실패: {e}")
            raise

    def generate_response(self, question: str, context_chunks: list[dict[str, Any]]) -> RAGResponse:
        """vLLM으로 응답 생성"""
        start_time = time.time()

        try:
            from vllm import SamplingParams

            # 컨텍스트 포맷팅
            context_text = self._format_context(context_chunks)

            # 프롬프트 생성
            user_prompt = self.IMPROVED_QUERY_TEMPLATE.format(
                context=context_text,
                query=question
            )

            # Qwen2.5 chat template 적용
            messages = [
                {"role": "system", "content": self.IMPROVED_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]

            # vLLM 샘플링 파라미터
            sampling_params = SamplingParams(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                top_p=self.config.top_p,
                top_k=self.config.top_k,
                repetition_penalty=self.config.repeat_penalty,
            )

            # 추론 실행
            outputs = self.llm.chat(messages, sampling_params=sampling_params)

            # 응답 추출
            response_text = outputs[0].outputs[0].text

            generation_time = time.time() - start_time

            # 출처 추출
            sources = self._extract_sources(context_chunks)

            # 인용 확인
            has_citation = any(source in response_text for source in sources)

            return RAGResponse(
                answer=response_text.strip(),
                sources_cited=sources,
                confidence=LLMWrapperConfig.RAG_HIGH_CONFIDENCE,
                generation_time=generation_time,
                has_proper_citation=has_citation,
                retry_count=0,
            )

        except Exception as e:
            self.logger.error(f"❌ vLLM 응답 생성 실패: {e}")
            return RAGResponse(
                answer=f"응답 생성 실패: {str(e)}",
                sources_cited=[],
                confidence=0.0,
                generation_time=time.time() - start_time,
                has_proper_citation=False,
                retry_count=0,
            )


class Qwen72BLLM(BaseRAGLLM):
    """Qwen2.5-72B-Instruct-AWQ (Transformers 기반 - H100용)"""

    SYSTEM_ROLE = "한국 방송사의 전문 지식 검색 도우미"
    ANSWER_LANGUAGE = "한국어"

    IMPROVED_SYSTEM_PROMPT = f"""당신은 {SYSTEM_ROLE}입니다.

[핵심 원칙]
★ 질문이 요청한 범위만 답변하세요.
★ 문서에 있는 정보만 사용하세요. 추측 금지.
★ 숫자/금액/날짜는 정확하게 인용하세요.
★ 출처를 [파일명.pdf] 형식으로 표시하세요.
★ 반드시 {ANSWER_LANGUAGE}로 답변하세요."""

    def __init__(self, model_path: str = None, config: GenerationConfig = None, length_analyzer=None):
        super().__init__()
        # model_path가 None이면 환경변수에서 가져옴
        if model_path is None:
            model_path = os.getenv("LLM_MODEL_PATH", "/home/user/Desktop/AI/AI-CHAT/models")
        self.model_path = Path(model_path)
        self.config = config or GenerationConfig()
        self.length_analyzer = length_analyzer
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        """Transformers로 72B AWQ 모델 로드"""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.logger.info(f"🚀 Qwen2.5-72B-Instruct-AWQ 로딩 중: {self.model_path}")
            self.logger.info("   H100 GPU에서 로딩 (약 30-60초 소요)")

            # Tokenizer 로드
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(self.model_path),
                trust_remote_code=True
            )

            # Flash Attention 설정 (환경변수 기반)
            enable_flash_attn = os.getenv("ENABLE_FLASH_ATTENTION", "false").lower() == "true"

            # TF32 활성화 (H100 성능 향상)
            if torch.cuda.is_available():
                torch.set_float32_matmul_precision("high")  # TF32
                os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

            # 모델 로드 (AWQ quantization 자동 인식)
            model_kwargs = {
                "device_map": "auto",  # H100에 자동 배치
                "torch_dtype": torch.float16,
                "trust_remote_code": True,
                "low_cpu_mem_usage": True,
            }

            # Flash Attention 활성화 (설치된 경우)
            if enable_flash_attn:
                try:
                    import importlib.util
                    if importlib.util.find_spec("flash_attn") is not None:
                        model_kwargs["attn_implementation"] = "flash_attention_2"
                        self.logger.info("⚡ Flash Attention 2 활성화됨")
                    else:
                        self.logger.warning("⚠️ flash-attn 미설치 - 기본 어텐션 사용")
                except ImportError:
                    self.logger.warning("⚠️ flash-attn 미설치 - 기본 어텐션 사용")

            self.model = AutoModelForCausalLM.from_pretrained(
                str(self.model_path),
                **model_kwargs
            )

            self.logger.info("✅ Qwen2.5-72B-Instruct-AWQ 로딩 완료!")
            self.logger.info(f"   GPU 메모리 사용: {torch.cuda.memory_allocated() / 1024**3:.1f} GB")

        except Exception as e:
            self.logger.error(f"❌ 모델 로딩 실패: {e}")
            raise

    def generate_response(self, question: str, context_chunks: list[dict[str, Any]]) -> RAGResponse:
        """72B 모델로 응답 생성"""
        start_time = time.time()

        try:
            import torch

            # 컨텍스트 포맷팅
            context_text = self._format_context(context_chunks)

            # 프롬프트 생성
            user_prompt = f"""문서 내용:
{context_text}

질문: {question}

답변:"""

            messages = [
                {"role": "system", "content": self.IMPROVED_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]

            # Chat template 적용
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            # Tokenization
            model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

            # 생성
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **model_inputs,
                    max_new_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    top_k=self.config.top_k,
                    repetition_penalty=self.config.repeat_penalty,
                    do_sample=True if self.config.temperature > 0 else False,
                )

            # 응답 추출
            generated_ids = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

            generation_time = time.time() - start_time

            # 출처 추출
            sources = self._extract_sources(context_chunks)
            has_citation = any(source in response_text for source in sources)

            return RAGResponse(
                answer=response_text.strip(),
                sources_cited=sources,
                confidence=LLMWrapperConfig.RAG_HIGH_CONFIDENCE,
                generation_time=generation_time,
                has_proper_citation=has_citation,
                retry_count=0,
            )

        except Exception as e:
            self.logger.error(f"❌ 응답 생성 실패: {e}")
            return RAGResponse(
                answer=f"응답 생성 실패: {str(e)}",
                sources_cited=[],
                confidence=0.0,
                generation_time=time.time() - start_time,
                has_proper_citation=False,
                retry_count=0,
            )

    def generate_batch_responses(
        self,
        questions: list[str],
        context_chunks_list: list[list[dict[str, Any]]]
    ) -> list[RAGResponse]:
        """여러 질의를 배치로 처리 (H100 성능 활용)

        Args:
            questions: 질의 리스트
            context_chunks_list: 각 질의에 대응하는 컨텍스트 청크 리스트

        Returns:
            RAGResponse 리스트
        """
        start_time = time.time()

        try:
            import torch

            if len(questions) != len(context_chunks_list):
                raise ValueError(f"질의({len(questions)})와 컨텍스트({len(context_chunks_list)}) 개수 불일치")

            # 프롬프트 일괄 생성
            prompts = []
            for question, chunks in zip(questions, context_chunks_list):
                context_text = self._format_context(chunks)
                user_prompt = f"""문서 내용:
{context_text}

질문: {question}

답변:"""
                messages = [
                    {"role": "system", "content": self.IMPROVED_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
                text = self.tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
                prompts.append(text)

            # 배치 토크나이징 (패딩 적용 - Flash Attention은 left padding 필요)
            max_context = int(os.getenv("LLM_N_CTX", "16384"))
            original_padding_side = self.tokenizer.padding_side
            self.tokenizer.padding_side = "left"

            model_inputs = self.tokenizer(
                prompts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_context
            ).to(self.model.device)

            # 원래 패딩 설정 복원
            self.tokenizer.padding_side = original_padding_side

            # 배치 생성
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **model_inputs,
                    max_new_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    do_sample=True if self.config.temperature > 0 else False,
                )

            # 응답 추출
            responses = []
            total_time = time.time() - start_time
            avg_time = total_time / len(questions)

            for i, (input_ids, output_ids) in enumerate(zip(model_inputs.input_ids, generated_ids)):
                # 입력 부분 제거하고 생성된 부분만 추출
                response_ids = output_ids[len(input_ids):]
                response_text = self.tokenizer.decode(response_ids, skip_special_tokens=True)

                # 출처 추출
                sources = self._extract_sources(context_chunks_list[i])
                has_citation = any(source in response_text for source in sources)

                responses.append(RAGResponse(
                    answer=response_text.strip(),
                    sources_cited=sources,
                    confidence=LLMWrapperConfig.RAG_HIGH_CONFIDENCE,
                    generation_time=avg_time,  # 평균 시간 사용
                    has_proper_citation=has_citation,
                    retry_count=0,
                ))

            self.logger.info(f"✅ 배치 생성 완료 ({len(questions)}개, {total_time:.2f}초, 평균 {avg_time:.2f}초)")
            return responses

        except Exception as e:
            self.logger.error(f"❌ 배치 응답 생성 실패: {e}")
            # 실패 시 개별 응답 반환
            return [
                RAGResponse(
                    answer=f"배치 생성 실패: {str(e)}",
                    sources_cited=[],
                    confidence=0.0,
                    generation_time=0.0,
                    has_proper_citation=False,
                    retry_count=0,
                )
                for _ in questions
            ]


def create_llm(model_type: str = "llama", **kwargs) -> Any:
    """LLM 팩토리 함수"""
    if model_type.lower() == "qwen72b":
        return Qwen72BLLM(**kwargs)
    if model_type.lower() == "vllm":
        return VllmLLM(**kwargs)
    if model_type.lower() == "llama":
        return LlamaLLM(**kwargs)
    if model_type.lower() == "qwen":
        return QwenLLM(**kwargs)
    raise ValueError(f"지원되지 않는 모델 타입: {model_type}")


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.INFO)
    test_qwen_llm()
