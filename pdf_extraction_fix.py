#!/usr/bin/env python3
"""
PDF 텍스트 추출 오류 수정 패치
PyPDF2와 pdfplumber의 오류를 안전하게 처리
"""

def safe_pdf_extract_pypdf2(pdf_path, max_pages=50):
    """
    PyPDF2를 사용한 안전한 PDF 텍스트 추출
    """
    import PyPDF2
    import re

    full_text = ""

    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            actual_pages = min(len(reader.pages), max_pages)

            for page_num in range(actual_pages):
                try:
                    page = reader.pages[page_num]
                    # extract_text() 메서드 호출시 오류 처리
                    try:
                        page_text = page.extract_text()
                    except (ValueError, TypeError, KeyError) as e:
                        # 알려진 PyPDF2 오류들
                        # "not enough values to unpack"
                        # "Invalid octal" 등
                        continue

                    # 텍스트 유효성 검사
                    if not page_text or len(page_text.strip()) < 10:
                        continue

                    # 인코딩 문제 처리
                    try:
                        # UTF-8로 인코딩/디코딩하여 잘못된 문자 제거
                        page_text = page_text.encode('utf-8', errors='ignore').decode('utf-8')
                    except:
                        continue

                    # 그룹웨어 URL 제거
                    page_text = re.sub(r'gw\.channela[^\n]+', '', page_text)
                    page_text = re.sub(r'\d+\.\s*\d+\.\s*\d+\.\s*오[전후]\s*\d+:\d+\s*장비구매.*?기안서', '', page_text)

                    if page_text:
                        full_text += f"\n[페이지 {page_num+1}]\n{page_text}\n"

                except Exception as e:
                    # 개별 페이지 오류는 무시하고 계속
                    continue

                # 텍스트가 너무 길면 중단
                if len(full_text) > 100000:
                    break

    except Exception as e:
        # 전체 파일 읽기 실패
        return ""

    return full_text


def safe_pdf_extract_pdfplumber(pdf_path, max_pages=30):
    """
    pdfplumber를 사용한 안전한 PDF 텍스트 추출
    """
    import pdfplumber

    text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_read = min(len(pdf.pages), max_pages)

            for i, page in enumerate(pdf.pages[:pages_to_read]):
                try:
                    # extract_text() 호출시 오류 처리
                    page_text = None
                    try:
                        page_text = page.extract_text()
                    except (ValueError, TypeError, KeyError) as e:
                        # 알려진 pdfplumber 오류들
                        continue
                    except Exception:
                        continue

                    # 텍스트 유효성 검사
                    if page_text and len(page_text.strip()) > 10:
                        # 인코딩 문제 처리
                        try:
                            page_text = page_text.encode('utf-8', errors='ignore').decode('utf-8')
                            text += page_text + "\n"
                        except:
                            continue

                except Exception:
                    # 페이지 처리 오류 무시
                    continue

                # 텍스트 길이 제한
                if len(text) > 50000:
                    break

    except Exception as e:
        # 전체 파일 읽기 실패
        return ""

    return text


def apply_fix_to_perfect_rag():
    """
    perfect_rag.py에 수정사항 적용
    """
    print("📝 PDF 추출 오류 수정 패치 적용 중...")

    # 수정할 코드 패턴들
    fix_instructions = """

    perfect_rag.py 파일의 PDF 추출 부분을 다음과 같이 수정하세요:

    1. PyPDF2 사용 부분 (약 2132-2140줄):
       - page.extract_text() 호출을 try-except로 감싸기
       - ValueError, TypeError, KeyError 예외 처리
       - 페이지별 오류는 continue로 건너뛰기

    2. pdfplumber 사용 부분 (약 515-525줄, 2870-2875줄):
       - page.extract_text() 호출을 try-except로 감싸기
       - 텍스트 유효성 검사 추가 (len > 10)
       - 인코딩 오류 처리 추가

    3. 공통 개선사항:
       - 모든 extract_text() 호출에 예외 처리
       - 텍스트가 없거나 너무 짧은 경우 건너뛰기
       - UTF-8 인코딩 문제 처리
       - 디버그 로그는 self.debug 플래그 확인 후 출력

    """

    print(fix_instructions)
    print("\n✅ 수정 가이드 생성 완료")
    print("🔧 위 지침에 따라 perfect_rag.py를 수정하면 PDF 추출 오류가 해결됩니다.")


def test_pdf_extraction():
    """
    PDF 추출 테스트
    """
    from pathlib import Path

    print("\n🧪 PDF 추출 테스트")
    print("="*50)

    # 테스트할 PDF 파일들
    test_pdfs = [
        Path("docs/year_2020") / "20200102 중계차 통합SI 및 오디오 시스템 유지보수(신규_통신) 검토.pdf",
        Path("docs/year_2019") / "20190102 스튜디오 모니터용 스피커(JBL 305P MKII) 구매.pdf",
    ]

    for pdf_path in test_pdfs:
        if pdf_path.exists():
            print(f"\n📄 테스트: {pdf_path.name}")

            # PyPDF2 테스트
            print("  - PyPDF2 방식...")
            text1 = safe_pdf_extract_pypdf2(str(pdf_path), max_pages=5)
            print(f"    추출: {len(text1)} 문자")

            # pdfplumber 테스트
            print("  - pdfplumber 방식...")
            text2 = safe_pdf_extract_pdfplumber(str(pdf_path), max_pages=5)
            print(f"    추출: {len(text2)} 문자")

            if text1 or text2:
                print("    ✅ 성공")
            else:
                print("    ⚠️ 텍스트 추출 실패")

    print("\n✨ 테스트 완료")


if __name__ == "__main__":
    print("🔧 PDF 텍스트 추출 오류 수정 도구")
    print("="*50)

    # 수정 가이드 출력
    apply_fix_to_perfect_rag()

    # 테스트 실행
    # test_pdf_extraction()