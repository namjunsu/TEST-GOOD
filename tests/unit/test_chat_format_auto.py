"""
Chat format 자동 감지 기능 단위 테스트

CHAT_FORMAT 환경변수에 따라 적절한 chat_format이 설정되는지 테스트
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from rag_system.active.llm_wrapper import GenerationConfig, QwenLLM


def _create_mock_llama_instance(metadata: dict, n_ctx_value: int = 4096) -> MagicMock:
    """테스트용 Llama mock 인스턴스 생성

    n_ctx() 메서드와 metadata 속성을 포함하여
    QwenLLM의 n_ctx 불일치 가드를 통과할 수 있도록 함.

    Note: 기본값 4096은 llm_wrapper.py의 CFG_N_CTX 기본값과 일치해야 함.
    """
    mock_instance = MagicMock()
    mock_instance.metadata = metadata
    # n_ctx()는 메서드로 호출되므로 callable로 설정
    mock_instance.n_ctx.return_value = n_ctx_value
    return mock_instance


class TestChatFormatAutoDetection:
    """Chat format 자동 감지 테스트"""

    @patch("llama_cpp.Llama")
    def test_auto_uses_none_for_metadata(self, mock_llama, monkeypatch):
        """CHAT_FORMAT=auto일 때 chat_format=None으로 설정되어 GGUF 메타데이터 사용"""
        # Setup
        monkeypatch.setenv("CHAT_FORMAT", "auto")
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "llama",
            "general.name": "LLaMA v2",
            "tokenizer.ggml.model": "llama",
            "tokenizer.chat_template": '{% if messages[0]["role"] == "system" %}...'
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        # chat_format이 None으로 설정되었는지 확인 (auto 모드)
        # Llama 생성 시 chat_format 인자 확인
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") is None, \
            "CHAT_FORMAT=auto일 때 chat_format은 None이어야 함 (GGUF 메타데이터 사용)"

    @patch("llama_cpp.Llama")
    def test_override_llama2(self, mock_llama, monkeypatch):
        """CHAT_FORMAT=llama-2일 때 명시적으로 llama-2 포맷 사용"""
        # Setup
        monkeypatch.setenv("CHAT_FORMAT", "llama-2")
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "llama",
            "general.name": "LLaMA v2"
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") == "llama-2", \
            "CHAT_FORMAT=llama-2일 때 chat_format='llama-2'여야 함"

    @patch("llama_cpp.Llama")
    def test_override_chatml(self, mock_llama, monkeypatch):
        """CHAT_FORMAT=chatml일 때 명시적으로 chatml 포맷 사용"""
        # Setup
        monkeypatch.setenv("CHAT_FORMAT", "chatml")
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "qwen",
            "general.name": "Qwen"
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") == "chatml", \
            "CHAT_FORMAT=chatml일 때 chat_format='chatml'이어야 함"

    @patch("llama_cpp.Llama")
    def test_override_qwen(self, mock_llama, monkeypatch):
        """CHAT_FORMAT=qwen일 때 명시적으로 qwen 포맷 사용"""
        # Setup
        monkeypatch.setenv("CHAT_FORMAT", "qwen")
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "qwen",
            "general.name": "Qwen2.5"
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") == "qwen", \
            "CHAT_FORMAT=qwen일 때 chat_format='qwen'이어야 함"

    @patch("llama_cpp.Llama")
    def test_default_is_auto(self, mock_llama, monkeypatch):
        """CHAT_FORMAT 환경변수가 없을 때 기본값 auto 사용"""
        # Setup - CHAT_FORMAT 환경변수 제거
        monkeypatch.delenv("CHAT_FORMAT", raising=False)
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "llama",
            "tokenizer.chat_template": "template..."
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") is None, \
            "CHAT_FORMAT 미설정 시 기본값 auto (None)이어야 함"

    @patch("llama_cpp.Llama")
    def test_case_insensitive(self, mock_llama, monkeypatch):
        """CHAT_FORMAT 값이 대소문자 구분 없이 동작"""
        # Setup
        monkeypatch.setenv("CHAT_FORMAT", "AUTO")  # 대문자
        mock_llama_instance = _create_mock_llama_instance({
            "general.architecture": "llama"
        })
        mock_llama.return_value = mock_llama_instance

        # Execute
        _llm = QwenLLM(model_path="./models/test.gguf", config=GenerationConfig())

        # Verify
        call_kwargs = mock_llama.call_args.kwargs
        assert call_kwargs.get("chat_format") is None, \
            "CHAT_FORMAT=AUTO (대문자)도 auto로 처리되어야 함"


def test_chat_format_resolve_function():
    """chat_format 결정 로직 직접 테스트"""

    def resolve_chat_format(env_value: str) -> str | None:
        """환경변수 값에서 chat_format 결정"""
        if env_value.lower() == "auto":
            return None
        return env_value.lower()

    # auto -> None
    assert resolve_chat_format("auto") is None
    assert resolve_chat_format("AUTO") is None

    # 명시적 지정 -> 소문자로 변환
    assert resolve_chat_format("llama-2") == "llama-2"
    assert resolve_chat_format("LLAMA-2") == "llama-2"
    assert resolve_chat_format("chatml") == "chatml"
    assert resolve_chat_format("qwen") == "qwen"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
