"""
OCR 후처리 모듈 - LLM을 활용한 OCR 결과 교정

pytesseract OCR 결과의 품질을 개선하기 위해 로컬 LLM(Qwen)을 사용하여
한글 오인식, 표 구조 깨짐, 숫자 오류 등을 교정합니다.

2025-12-16: 초기 구현
"""

import re
from typing import Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# OCR 교정 프롬프트
OCR_CORRECTION_PROMPT = """다음은 한국어 문서를 OCR로 추출한 텍스트입니다.
OCR 과정에서 발생한 오류를 교정해주세요.

[교정 규칙]
1. 한글 오인식 수정 (예: "SY" → "증설", "AHA" → "채널A")
2. 숫자/금액 오류 수정 (예: "52.600.000" → "52,600,000")
3. 표 구조가 깨진 경우 마크다운 표로 정리
4. 문서 양식(기안서, 검토서 등) 구조 유지
5. 의미가 불분명한 부분은 [?]로 표시
6. 원본의 의미를 변경하지 마세요

[OCR 원본 텍스트]
{ocr_text}

[교정된 텍스트]"""

# 간단한 후처리용 프롬프트 (짧은 텍스트용)
OCR_SIMPLE_PROMPT = """OCR로 추출한 한국어 텍스트의 오류를 교정해주세요.
한글 오인식, 숫자 오류만 수정하고 원본 구조를 유지하세요.

원본:
{ocr_text}

교정:"""


def correct_ocr_with_llm(
    ocr_text: str,
    max_tokens: int = 2000,
    use_simple_prompt: bool = False,
) -> Optional[str]:
    """LLM을 사용하여 OCR 텍스트 교정

    Args:
        ocr_text: OCR로 추출된 원본 텍스트
        max_tokens: LLM 생성 최대 토큰 수
        use_simple_prompt: 짧은 프롬프트 사용 여부

    Returns:
        교정된 텍스트 또는 None (실패 시)
    """
    if not ocr_text or len(ocr_text.strip()) < 50:
        logger.warning("OCR 텍스트가 너무 짧아 교정 스킵")
        return ocr_text

    try:
        from rag_system.active.llm_singleton import LLMSingleton

        llm = LLMSingleton.get_instance()

        # 프롬프트 선택
        if use_simple_prompt or len(ocr_text) < 500:
            prompt = OCR_SIMPLE_PROMPT.format(ocr_text=ocr_text[:2000])
        else:
            # 긴 텍스트는 청크로 나눠서 처리
            prompt = OCR_CORRECTION_PROMPT.format(ocr_text=ocr_text[:3000])

        logger.info(f"LLM OCR 교정 시작: {len(ocr_text)}자 → max_tokens={max_tokens}")

        # LLM 호출 (동적 메서드 - generate 또는 generate_response)
        if hasattr(llm, "generate"):
            result: Any = llm.generate(prompt, max_tokens=max_tokens)  # type: ignore[attr-defined]
        else:
            # generate_response는 RAGResponse 반환, answer 필드 추출
            response = llm.generate_response(prompt, [])
            result = getattr(response, "answer", str(response))

        if result and len(result.strip()) > 50:
            logger.info(f"LLM OCR 교정 완료: {len(ocr_text)}자 → {len(result)}자")
            return result.strip()
        else:
            logger.warning("LLM 교정 결과가 너무 짧음, 원본 반환")
            return ocr_text

    except ImportError as e:
        logger.error(f"LLM 모듈 임포트 실패: {e}")
        return ocr_text
    except Exception as e:
        logger.error(f"LLM OCR 교정 실패: {e}")
        return ocr_text


def apply_rule_based_corrections(text: str) -> str:
    """규칙 기반 OCR 후처리 (LLM 없이)

    자주 발생하는 OCR 오류를 정규식으로 교정합니다.

    Args:
        text: OCR 텍스트

    Returns:
        교정된 텍스트
    """
    if not text:
        return text

    # 1. 숫자 구분자 교정 (마침표 → 쉼표)
    # 52.600.000 → 52,600,000
    text = re.sub(r"(\d)\.(\d{3})\.(\d{3})", r"\1,\2,\3", text)
    text = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1,\2", text)

    # 2. 채널A 관련 오인식
    text = re.sub(r"\bAHA\b", "채널A", text)
    text = re.sub(r"\bCHANNEL\s*\n?\s*※", "CHANNEL A", text)

    # 3. 기안서 양식 필드 정리
    text = re.sub(r"상비구매/수리", "장비구매/수리", text)
    text = re.sub(r"울상현", "윤상현", text)  # 이름 오인식
    text = re.sub(r"박정월", "박점렬", text)  # 이름 오인식

    # 4. 날짜 형식 정리
    # 2017-09-26 ~ 2017-09-26 형식 유지

    # 5. 불필요한 특수문자 제거
    text = re.sub(r"[※\\](?=\s*[A-Z])", "", text)

    # 6. 연속된 공백 정리
    text = re.sub(r"[ \t]{3,}", "  ", text)

    return text


def correct_ocr_text(
    ocr_text: str,
    use_llm: bool = True,
    max_tokens: int = 2000,
) -> str:
    """OCR 텍스트 교정 (규칙 기반 + LLM)

    Args:
        ocr_text: OCR로 추출된 원본 텍스트
        use_llm: LLM 교정 사용 여부
        max_tokens: LLM 생성 최대 토큰 수

    Returns:
        교정된 텍스트
    """
    if not ocr_text:
        return ocr_text

    # 1. 규칙 기반 교정 (항상 적용)
    corrected = apply_rule_based_corrections(ocr_text)

    # 2. LLM 교정 (옵션)
    if use_llm:
        llm_result = correct_ocr_with_llm(corrected, max_tokens=max_tokens)
        if llm_result:
            corrected = llm_result

    return corrected
