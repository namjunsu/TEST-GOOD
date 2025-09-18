#!/usr/bin/env python3
"""
load_documents 함수 수정 스크립트
"""

new_function = '''@st.cache_data(ttl=3600)
def load_documents():
    """문서 메타데이터 로드 (캐시 사용으로 빠른 로딩)"""
    import html
    import re
    from datetime import datetime
    from perfect_rag import PerfectRAG

    documents = []

    # PerfectRAG 인스턴스에서 문서 정보 가져오기
    try:
        rag = PerfectRAG()
        pdf_files = rag.pdf_files  # 이미 로드된 PDF 파일 목록 사용

        # 각 PDF 파일에 대한 메타데이터 생성
        for pdf_file in pdf_files:
            # 파일명에서 메타데이터 추출
            name_parts = pdf_file.stem.split('_', 1)
            doc_date = name_parts[0] if len(name_parts) > 0 else ""
            doc_title = name_parts[1] if len(name_parts) > 1 else pdf_file.stem
            doc_title = html.unescape(doc_title)

            # 연도 추출
            year = doc_date[:4] if len(doc_date) >= 4 else "연도없음"
            month = doc_date[5:7] if len(doc_date) >= 7 else ""

            # 카테고리 분류
            category = "기타"
            if "구매" in pdf_file.name or "구입" in pdf_file.name:
                category = "구매"
            elif "폐기" in pdf_file.name:
                category = "폐기"
            elif "수리" in pdf_file.name or "보수" in pdf_file.name:
                category = "수리"
            elif "소모품" in pdf_file.name:
                category = "소모품"

            # 메타데이터 생성
            metadata = {
                'title': doc_title,
                'filename': pdf_file.name,
                'path': str(pdf_file),
                'category': category,
                'date': doc_date,
                'year': year,
                'month': month,
                'drafter': "미상",
                'modified': datetime.fromtimestamp(pdf_file.stat().st_mtime)
            }

            documents.append(metadata)

    except Exception as e:
        print(f"문서 로드 중 오류: {e}")
        import traceback
        traceback.print_exc()

    # DataFrame 생성 및 정렬
    df = pd.DataFrame(documents)
    if not df.empty:
        df = df.sort_values('date', ascending=False)

    print(f"📊 총 {len(documents)}개 문서 로드 완료")

    return df'''

# web_interface.py 파일 읽기
with open('/home/wnstn4647/AI-CHAT/web_interface.py', 'r', encoding='utf-8') as f:
    content = f.read()

# load_documents 함수 찾기
import re

# 함수 전체를 찾기 위한 패턴
pattern = r'@st\.cache_data\(ttl=3600\)\ndef load_documents\(\):.*?(?=\n(?:def |class |@|if __name__|$))'

# 새 함수로 교체
new_content = re.sub(pattern, new_function, content, flags=re.DOTALL)

# 파일 쓰기
with open('/home/wnstn4647/AI-CHAT/web_interface.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ load_documents 함수 수정 완료")