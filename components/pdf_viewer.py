"""
PDF Viewer Component
Modular PDF viewing with multiple rendering modes
"""

from __future__ import annotations

import base64
import io
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st

from utils.pdf_utils import (
    MAX_PDF_BYTES,
    MAX_PDF_MB,
    generate_file_hash,
    load_pdf_bytes_with_limit,
)

if TYPE_CHECKING:
    pass


@st.cache_data(ttl=600, show_spinner=False)
def _cached_page_png(path: str, mtime: float, page_index: int, zoom: float) -> bytes | None:
    """페이지를 PNG로 렌더링하여 캐시 (색공간 안전 처리)"""
    try:
        import fitz

        doc = fitz.open(path)
        try:
            if page_index >= doc.page_count:
                return None
            page = doc[page_index]
            mat = fitz.Matrix(zoom, zoom)
            # alpha=False, colorspace=csRGB로 색공간 문제 해결
            pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)
            try:
                # tobytes("png")로 PIL 호환성 보장
                return pix.tobytes("png")
            finally:
                del pix
                del page
        finally:
            doc.close()
    except Exception:
        return None


class ViewMode(Enum):
    """PDF 보기 모드"""

    ORIGINAL = "📖 원본 PDF"
    IMAGES = "🖼️ 페이지별 이미지"
    TEXT = "📄 텍스트 추출"


@dataclass
class PDFInfo:
    """PDF 파일 정보"""

    path: Path
    size_mb: float
    total_pages: int | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_large(self) -> bool:
        """대용량 파일 여부 (10MB 초과)"""
        return self.size_mb > 10


class PDFViewer:
    """PDF 미리보기 컴포넌트

    여러 렌더링 모드 지원:
    - 원본 PDF (base64 embedding)
    - 페이지별 이미지 (PyMuPDF)
    - 텍스트 추출 (pdfplumber + OCR)
    """

    def __init__(self, file_path: str, height: int = 700):
        """
        Args:
            file_path: PDF 파일 경로 (상대/절대 경로 모두 지원)
            height: 뷰어 높이 (픽셀)
        """
        file_path_obj = Path(file_path)

        # 상대 경로인 경우 DOCS_DIR 기준으로 변환
        if not file_path_obj.is_absolute():
            try:
                from app.config.settings import settings
                self.file_path = settings.DOCS_DIR / file_path_obj
            except Exception:
                # settings import 실패 시 그대로 사용 (fallback)
                self.file_path = file_path_obj
        else:
            self.file_path = file_path_obj

        self.height = height
        self.info: PDFInfo | None = None

        # 인스턴스별 고유 ID (키 충돌 방지)
        self._instance_id = uuid.uuid4().hex[:8]

        # 라이브러리 가용성 체크
        self.pymupdf_available = self._check_pymupdf()
        self.pdfplumber_available = self._check_pdfplumber()

    def _check_pymupdf(self) -> bool:
        """PyMuPDF 설치 여부 확인"""
        try:
            import fitz  # noqa: F401

            return True
        except ImportError:
            return False

    def _check_pdfplumber(self) -> bool:
        """pdfplumber 설치 여부 확인"""
        try:
            import pdfplumber  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_pdf_info(self) -> PDFInfo | None:
        """PDF 파일 정보 가져오기"""
        if not self.file_path.exists():
            st.error(f"⚠️ 파일을 찾을 수 없습니다: {self.file_path.name}")
            return None

        file_size = self.file_path.stat().st_size
        size_mb = file_size / (1024 * 1024)

        # 총 페이지 수 (PyMuPDF 우선, 없으면 pdfplumber)
        total_pages = None
        if self.pymupdf_available:
            try:
                import fitz

                doc = fitz.open(str(self.file_path))
                try:
                    total_pages = doc.page_count
                finally:
                    doc.close()
            except Exception:
                pass
        elif self.pdfplumber_available:
            try:
                import pdfplumber

                with pdfplumber.open(self.file_path) as pdf:
                    total_pages = len(pdf.pages)
            except Exception:
                pass

        return PDFInfo(path=self.file_path, size_mb=size_mb, total_pages=total_pages)

    def _render_info_bar(self, info: PDFInfo) -> None:
        """파일 정보 및 다운로드 버튼 표시 (메모리 가드 적용)"""
        col1, col2, col3 = st.columns([2, 1, 1])

        with col1:
            st.markdown(f"**📄 {info.name}**")

        with col2:
            st.markdown(f"**💾 {info.size_mb:.1f}MB**")

        with col3:
            data = load_pdf_bytes_with_limit(str(self.file_path), MAX_PDF_BYTES)
            if data is None:
                st.button(
                    "📥 다운로드",
                    disabled=True,
                    key=f"dl_disabled_{self._instance_id}_{generate_file_hash(str(self.file_path))}",
                )
                st.caption(f"({MAX_PDF_MB:.0f}MB 초과 또는 접근 불가)")
            else:
                st.download_button(
                    label="📥 다운로드",
                    data=data,
                    file_name=info.name,
                    mime="application/pdf",
                    key=f"dl_{self._instance_id}_{generate_file_hash(str(self.file_path))}",
                )

        st.markdown("---")

    def _get_available_modes(self, info: PDFInfo) -> tuple[list[ViewMode], ViewMode | None]:
        """사용 가능한 보기 모드 및 기본 모드 반환

        Returns:
            (available_modes, default_mode) - default_mode는 모드가 없으면 None
        """
        if self.pymupdf_available:
            modes = [ViewMode.ORIGINAL, ViewMode.IMAGES, ViewMode.TEXT]

            # 대용량 파일은 이미지 모드 권장
            default = ViewMode.IMAGES if info.is_large else ViewMode.ORIGINAL

            if info.is_large:
                st.info(
                    f"💡 대용량 파일({info.size_mb:.1f}MB)은 "
                    "페이지별 이미지 모드를 권장합니다",
                )
        elif self.pdfplumber_available:
            modes = [ViewMode.TEXT]
            default = ViewMode.TEXT
            st.warning(
                "⚠️ PyMuPDF 미설치로 텍스트 추출만 가능합니다. "
                "전체 기능을 위해 'pip install pymupdf' 실행을 권장합니다",
            )
        else:
            # 아무것도 없는 경우
            modes = []
            default = None
            st.error(
                "🔴 PDF 라이브러리가 설치되지 않았습니다.\n"
                "다음 중 하나를 설치하세요:\n"
                "- `pip install pymupdf` (전체 기능)\n"
                "- `pip install pdfplumber` (텍스트 추출만)",
            )

        return modes, default

    def _render_original_pdf(self, info: PDFInfo) -> bool:
        """원본 PDF 표시 (base64 embedding, 메모리 가드 적용)"""
        # 1.5MB 이하만 지원
        if info.size_mb > 1.5:
            st.warning(
                f"⚠️ 큰 파일({info.size_mb:.1f}MB)은 "
                "페이지별 이미지 모드를 사용해주세요",
            )
            st.info("🖼️ 위에서 '페이지별 이미지' 모드를 선택하시면 PDF를 볼 수 있습니다")
            return False

        try:
            data = load_pdf_bytes_with_limit(str(self.file_path), MAX_PDF_BYTES)
            if not data:
                st.warning("⚠️ 원본 로딩 불가 → 이미지/텍스트 모드를 사용하세요")
                return False

            base64_pdf = base64.b64encode(data).decode("utf-8")

            # iframe으로 PDF 표시
            html = f"""
            <div style="width:100%;border:1px solid #ddd;border-radius:6px;background:#fff;">
              <iframe
                 src="data:application/pdf;base64,{base64_pdf}#view=FitH&toolbar=1&navpanes=1&scrollbar=1"
                 width="100%" height="{self.height}" style="border:none"></iframe>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
            return True

        except Exception as e:
            st.error(f"🔴 PDF 표시 실패: {e}")
            st.info("💡 이미지 또는 텍스트 모드를 시도하세요")
            return False

    def _render_pdf_as_images(self, info: PDFInfo) -> bool:
        """페이지별 이미지로 PDF 렌더링 (색공간 안전 + 캐싱 + 자원 해제)"""
        if not self.pymupdf_available:
            st.error("PyMuPDF가 필요합니다. 'pip install pymupdf'로 설치해주세요")
            return False

        try:
            import fitz
            from PIL import Image

            # PDF 열기
            doc = fitz.open(str(self.file_path))
            try:
                total_pages = doc.page_count

                # 세션 상태로 현재 페이지 관리 (해시 키 사용)
                page_key = f"page_{generate_file_hash(str(self.file_path))}"
                if page_key not in st.session_state:
                    st.session_state[page_key] = 1

                current_page = st.session_state[page_key]

                # 페이지 선택 UI (2페이지 이상일 때)
                if total_pages > 1:
                    col1, col2, col3 = st.columns([1, 3, 1])
                    with col2:
                        new_page = st.slider(
                            "📄 페이지 이동",
                            min_value=1,
                            max_value=total_pages,
                            value=current_page,
                            key=f"slider_{generate_file_hash(str(self.file_path))}",
                            help="슬라이더를 움직여 페이지를 이동하세요",
                        )
                        if new_page != current_page:
                            st.session_state[page_key] = new_page
                            current_page = new_page

                # 파일 크기에 따라 렌더링 품질 동적 조정
                if info.size_mb > 50:
                    zoom = 1.0
                    st.caption("📊 대용량 파일 - 최적화된 품질로 렌더링")
                elif info.size_mb > 20:
                    zoom = 1.5
                else:
                    zoom = 2.0

                # 캐시된 PNG 렌더링 (색공간 안전 처리)
                mtime = self.file_path.stat().st_mtime
                png_bytes = _cached_page_png(
                    str(self.file_path), mtime, current_page - 1, zoom,
                )

                if png_bytes is None:
                    st.error(f"⚠️ 페이지 {current_page} 렌더링 실패")
                    return False

                # PIL 이미지로 변환
                with io.BytesIO(png_bytes) as bio:
                    img = Image.open(bio).convert("RGB")

                # 디스플레이 크기 조정
                display_width = 850
                if img.width > display_width:
                    ratio = display_width / img.width
                    img = img.resize(
                        (display_width, int(img.height * ratio)), Image.Resampling.LANCZOS,
                    )

                # 이미지 표시
                st.image(img)

                # 페이지 네비게이션 버튼
                if total_pages > 1:
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 2])
                    with col2:
                        if st.button(
                            "◀ 이전",
                            key=f"prev_{generate_file_hash(str(self.file_path))}",
                            disabled=(current_page == 1),
                        ):
                            st.session_state[page_key] = max(1, current_page - 1)
                            st.rerun()  # 2025-12-26: UI 갱신 (버튼 클릭 반영)

                    with col3:
                        st.markdown(
                            f"<center><b>{current_page} / {total_pages}</b></center>",
                            unsafe_allow_html=True,
                        )

                    with col4:
                        if st.button(
                            "다음 ▶",
                            key=f"next_{generate_file_hash(str(self.file_path))}",
                            disabled=(current_page == total_pages),
                        ):
                            st.session_state[page_key] = min(total_pages, current_page + 1)
                            st.rerun()  # 2025-12-26: UI 갱신 (버튼 클릭 반영)

                return True

            finally:
                # 자원 해제
                doc.close()

        except Exception as e:
            st.error(f"🔴 PDF 이미지 렌더링 실패: {e}")
            st.info("💡 대체 방법: 텍스트 추출 모드를 시도해보세요")
            return False

    def _render_pdf_text(self, info: PDFInfo) -> bool:
        """텍스트 추출 (OCR 지원, expander로 UI 개선)"""
        if not self.pdfplumber_available:
            st.error("pdfplumber가 필요합니다. 'pip install pdfplumber'로 설치해주세요")
            return False

        try:
            import pdfplumber

            with pdfplumber.open(self.file_path) as pdf:
                total_pages = len(pdf.pages)

                # 페이지 선택 (2페이지 이상일 때)
                if total_pages > 1:
                    page_num = st.slider(
                        "📄 페이지 선택",
                        min_value=1,
                        max_value=total_pages,
                        value=1,
                        key=f"text_page_{generate_file_hash(str(self.file_path))}",
                    )
                else:
                    page_num = 1

                st.markdown(f"**페이지 {page_num} / {total_pages}**")

                # 텍스트 추출
                page = pdf.pages[page_num - 1]
                text = page.extract_text() or ""

                if text.strip():
                    # 미리보기 + 전체 내용 (5000자 초과 시 expander)
                    preview = text[:2000]
                    with st.expander("본문 미리보기 (앞 2,000자)", expanded=True):
                        st.text(preview)

                    if len(text) > 2000:
                        with st.expander("📄 전체 내용 보기"):
                            st.text_area(
                                "전체 텍스트",
                                text,
                                height=400,
                                key=f"text_full_{generate_file_hash(str(self.file_path))}",
                            )
                    return True
                # OCR 시도
                return self._try_ocr(page_num)

        except Exception as e:
            st.error(f"🔴 텍스트 추출 실패: {e}")
            return False

    def _try_ocr(self, page_num: int) -> bool:
        """OCR 처리 시도"""
        st.info("🔍 스캔된 문서로 보입니다. OCR 처리를 시도합니다...")

        try:
            from rag_system.active.enhanced_ocr_processor import EnhancedOCRProcessor

            # OCR 프로세서 초기화 (캐싱)
            if "ocr_processor" not in st.session_state:
                st.session_state.ocr_processor = EnhancedOCRProcessor()

            ocr = st.session_state.ocr_processor

            with st.spinner("OCR 처리 중... 시간이 걸릴 수 있습니다"):
                ocr_result = ocr.process_pdf_with_ocr(str(self.file_path), page_num)

            if ocr_result.get("ok") and ocr_result.get("text", "").strip():
                # 성공 메시지 (OCR 스킵 또는 성공)
                if ocr_result.get("engine") == "skip":
                    st.info(
                        f"ℹ️ 텍스트 레이어가 있어 OCR을 스킵했습니다 (총 {ocr_result.get('pages', 0)}페이지)",
                    )
                else:
                    st.success(
                        f"✅ OCR 처리 성공! (엔진: {ocr_result.get('engine', 'tesseract')})",
                    )

                ocr_text = ocr_result["text"]
                preview = ocr_text[:2000]
                with st.expander("OCR 추출 내용 (앞 2,000자)", expanded=True):
                    st.text(preview)

                if len(ocr_text) > 2000:
                    with st.expander("📄 전체 OCR 내용 보기"):
                        st.text_area(
                            "전체 OCR 텍스트",
                            ocr_text,
                            height=400,
                            key=f"ocr_content_{generate_file_hash(str(self.file_path))}",
                        )
                return True
            # 실패 메시지
            why = ocr_result.get("why", "unknown")
            if "missing_binary" in why:
                st.warning("⚠️ Tesseract OCR이 설치되지 않았거나 라이브러리가 없습니다")
                st.info("💡 설치: pip install pytesseract pdf2image")
            else:
                st.warning(
                    f"⚠️ OCR 처리 후에도 텍스트를 추출할 수 없습니다 (사유: {why})",
                )
            return False

        except ImportError:
            st.warning(
                "⚠️ OCR 기능을 사용하려면 "
                "'pip install pytesseract pdf2image' 설치가 필요합니다",
            )
            return False

        except Exception as ocr_error:
            st.error(f"❌ OCR 처리 실패: {ocr_error}")
            st.info("💡 Tesseract OCR이 설치되어 있는지 확인해주세요")
            return False

    def render(self) -> bool:
        """PDF 뷰어 렌더링

        Returns:
            성공 여부
        """
        try:
            # PDF 정보 가져오기
            self.info = self._get_pdf_info()
            if not self.info:
                return False

            # 정보 바 표시
            self._render_info_bar(self.info)

            # 사용 가능한 보기 모드
            available_modes, default_mode = self._get_available_modes(self.info)

            if not available_modes or default_mode is None:
                self._render_fallback_download()
                return False

            # 보기 모드 선택 (해시 키 사용)
            mode_values = [mode.value for mode in available_modes]
            default_index = available_modes.index(default_mode)

            view_mode_str = st.radio(
                "보기 모드 선택",
                mode_values,
                index=default_index,
                key=f"view_mode_{generate_file_hash(str(self.file_path))}",
                horizontal=True,
            )

            # 선택된 모드로 렌더링
            if view_mode_str == ViewMode.ORIGINAL.value:
                return self._render_original_pdf(self.info)

            if view_mode_str == ViewMode.IMAGES.value:
                return self._render_pdf_as_images(self.info)

            if view_mode_str == ViewMode.TEXT.value:
                return self._render_pdf_text(self.info)

            return False

        except Exception as e:
            st.error(f"❌ PDF 미리보기 오류: {e}")

            # 상세 오류 정보 (디버깅용)
            with st.expander("🔍 상세 오류 정보"):
                import traceback

                st.text(traceback.format_exc())

            # 오류 시에도 다운로드 제공
            self._render_fallback_download()
            return False

    def _render_fallback_download(self) -> None:
        """오류 발생 시 대체 다운로드 버튼"""
        try:
            data = load_pdf_bytes_with_limit(str(self.file_path), MAX_PDF_BYTES)
            if data:
                st.download_button(
                    label="📥 PDF 다운로드 (미리보기 실패)",
                    data=data,
                    file_name=self.file_path.name,
                    mime="application/pdf",
                    key=f"fallback_dl_{self._instance_id}_{generate_file_hash(str(self.file_path))}",
                    help="미리보기는 실패했지만 파일을 다운로드할 수 있습니다",
                )
                st.info("💡 미리보기가 실패해도 다운로드하여 로컬에서 확인 가능합니다")
            else:
                st.error(f"⚠️ 파일이 너무 크거나 접근할 수 없습니다 (>{MAX_PDF_MB:.0f}MB)")

        except Exception as dl_error:
            st.error(f"다운로드도 실패: {dl_error}")


# 하위 호환성을 위한 함수 래퍼
def show_pdf_preview(file_path: str, height: int = 700) -> bool:
    """PDF 미리보기 표시 (레거시 호환 함수)

    Args:
        file_path: PDF 파일 경로
        height: 미리보기 높이 (픽셀)

    Returns:
        성공 여부
    """
    viewer = PDFViewer(file_path, height)
    return viewer.render()
