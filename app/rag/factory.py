"""RAG 파이프라인 컴포넌트 팩토리 모듈

pipeline.py에서 분리된 팩토리 메서드들.
Retriever, Compressor, Generator 등의 기본 인스턴스 생성을 담당.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from app.config.settings import settings
from app.core.logging import get_logger
from app.rag.adapters import (
    _DummyGenerator,
    _DummyRetriever,
    _LLMAdapter,
    _NoOpCompressor,
    _QuickFixGenerator,
)

if TYPE_CHECKING:
    from app.rag.contracts import Compressor, Generator, Retriever

logger = get_logger(__name__)


class RAGPipelineFactory:
    """RAG 파이프라인 컴포넌트 팩토리

    Retriever, Compressor, Generator 등의 기본 인스턴스를 생성.
    """

    @staticmethod
    def create_retriever() -> "Retriever":
        """기본 검색 엔진 생성 (HybridRetriever)

        Returns:
            Retriever: 검색 엔진 인스턴스
        """
        try:
            from app.rag.retrievers.hybrid import HybridRetriever

            retriever = HybridRetriever()
            logger.info("Default HybridRetriever 생성 완료")
            return retriever
        except Exception as e:
            logger.error(f"HybridRetriever 생성 실패: {e}", exc_info=True)
            return _DummyRetriever()

    @staticmethod
    def create_compressor() -> "Compressor":
        """기본 압축기 생성 (현재는 no-op)

        Returns:
            Compressor: 압축기 인스턴스
        """
        logger.info("Default compressor 생성 (no-op)")
        return _NoOpCompressor()

    @staticmethod
    def create_generator() -> "Generator":
        """기본 LLM 생성기 생성 (레거시 어댑터 사용)

        Returns:
            Generator: 생성기 인스턴스
        """
        try:
            # 레거시 구현 어댑터 사용 (점진적 이관 준비)
            legacy_rag = RAGPipelineFactory.create_legacy_adapter()
            if legacy_rag is None:
                logger.warning("LLM adapter 생성 실패, DummyGenerator 사용")
                return _DummyGenerator()
            logger.info("Default generator 생성 (Legacy Adapter 래핑)")
            return _QuickFixGenerator(legacy_rag)
        except Exception as e:
            logger.error(f"Generator 생성 실패: {e}", exc_info=True)
            return _DummyGenerator()

    @staticmethod
    def create_legacy_adapter() -> Optional["_LLMAdapter"]:
        """레거시 구현 어댑터 생성 (캡슐화)

        QwenLLM을 래핑하여 기존 레거시 시스템과 연결합니다.
        향후 이 메서드만 수정하여 신규 구현으로 점진 전환 가능.

        Returns:
            _LLMAdapter: LLM 어댑터 인스턴스
        """
        try:
            from rag_system.active.llm_singleton import LLMSingleton

            model_path = settings.MODEL_PATH
            logger.debug(f"LLM 로드 시도: model_path={model_path}, exists={Path(model_path).exists()}")
            llm = LLMSingleton.get_instance(model_path=model_path)
            logger.info(f"✅ LLM adapter 생성 완료 (model={model_path})")
            return _LLMAdapter(llm)
        except Exception as e:
            logger.error(f"LLM adapter 생성 실패: {e}", exc_info=True)
            return None

    @staticmethod
    def load_known_drafters() -> set[str]:
        """메타DB에서 고유 기안자 로드 (Closed-World Validation용)

        Returns:
            set: 고유 기안자 이름 집합
        """
        try:
            from app.data.metadata_db import MetadataDB

            db = MetadataDB()
            drafters = db.list_unique_drafters()
            db.close()

            logger.info(f"✅ 고유 기안자 {len(drafters)}명 캐싱 완료")
            return drafters
        except Exception as e:
            logger.error(f"기안자 로드 실패: {e}", exc_info=True)
            return set()
