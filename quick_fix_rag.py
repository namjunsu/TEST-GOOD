#!/usr/bin/env python3
"""
빠른 수정: LLM 없이 검색만 하는 RAG
문제 해결용 임시 솔루션
"""

from perfect_rag import PerfectRAG
import time

class QuickFixRAG:
    """LLM 답변 생성 문제 우회용 RAG"""

    def __init__(self):
        self.rag = PerfectRAG()

    def answer(self, query: str) -> str:
        """검색 결과만 반환 (LLM 답변 생성 제외)"""

        try:
            # 1. 기안자 검색인지 확인
            import re
            drafter_match = re.search(r'기안자\s*([가-힣]+)', query)
            if drafter_match:
                drafter_name = drafter_match.group(1)
                # 전체 개수 확인을 위해 많은 수로 검색
                search_results = self.rag.search_module.search_by_drafter(drafter_name, top_k=200)
                if search_results:
                    # 기안자로 작성된 문서 우선 표시
                    return self._format_drafter_results(query, drafter_name, search_results)

            # 2. 일반 검색
            search_results = self.rag.search_module.search_by_content(query, top_k=5)

            if not search_results:
                return "❌ 관련 문서를 찾을 수 없습니다."

            # 2. 검색 결과 포매팅 (LLM 없이)
            answer = f"**{query}** 검색 결과\n\n"
            answer += f"총 {len(search_results)}개 문서 발견\n\n"

            for i, doc in enumerate(search_results, 1):
                answer += f"**{i}. {doc['filename']}**\n"
                if doc.get('date'):
                    answer += f"   - 날짜: {doc['date']}\n"
                if doc.get('category'):
                    answer += f"   - 카테고리: {doc['category']}\n"

                # 기안자 정보 우선 표시 (department 필드에 저장됨)
                drafter = doc.get('department', '')
                if drafter and drafter not in ['영상', '카메라', '조명', '중계', 'DVR', '스튜디오', '송출']:
                    answer += f"   - 기안자: {drafter}\n"
                elif doc.get('extracted_dept'):
                    answer += f"   - 부서: {doc['extracted_dept']}\n"

                answer += "\n"

            return answer

        except Exception as e:
            return f"❌ 검색 중 오류 발생: {e}"

    def _format_drafter_results(self, query: str, drafter_name: str, search_results) -> str:
        """기안자별 검색 결과 포매팅"""
        total_count = len(search_results)
        answer = f"**{query}** 검색 결과\n\n"
        answer += f"📝 **{drafter_name}** 기안자가 작성한 문서: **{total_count}개** (최신순)\n\n"

        # 처음 15개만 상세히 표시
        display_count = min(15, total_count)

        for i, doc in enumerate(search_results[:display_count], 1):
            answer += f"**{i}. {doc['filename']}**\n"
            if doc.get('date'):
                answer += f"   - 날짜: {doc['date']}\n"
            if doc.get('category'):
                answer += f"   - 카테고리: {doc['category']}\n"
            answer += f"   - 기안자: {doc.get('department', '')}\n"
            answer += "\n"

        # 나머지가 있으면 요약 정보 추가
        if total_count > display_count:
            remaining = total_count - display_count
            answer += f"📋 **추가 {remaining}개 문서**가 더 있습니다.\n\n"

            # 연도별 통계
            year_stats = {}
            for doc in search_results:
                if doc.get('date'):
                    year = doc['date'][:4]
                    year_stats[year] = year_stats.get(year, 0) + 1

            if year_stats:
                answer += "📊 **연도별 분포:**\n"
                for year in sorted(year_stats.keys(), reverse=True):
                    answer += f"   - {year}년: {year_stats[year]}개\n"

        return answer

    def answer_from_specific_document(self, query: str, filename: str) -> str:
        """특정 문서에 대해서만 답변 생성 (문서 전용 모드)

        Args:
            query: 사용자 질문
            filename: 특정 문서 파일명
        """
        try:
            # 1. 파일명으로 문서 검색
            from pathlib import Path
            docs_dir = Path("docs")

            # 모든 하위 폴더에서 파일 찾기
            pdf_path = None
            for year_dir in docs_dir.glob("year_*"):
                potential_path = year_dir / filename
                if potential_path.exists():
                    pdf_path = potential_path
                    break

            if not pdf_path or not pdf_path.exists():
                return f"❌ 문서를 찾을 수 없습니다: {filename}"

            # 2. PDF 내용 추출 (OCR 캐시 우선)
            full_text = self._get_pdf_content(pdf_path)

            if not full_text.strip():
                return f"❌ PDF에서 텍스트를 추출할 수 없습니다: {filename}"

            # 3. 질문에 따라 답변 생성
            if any(word in query for word in ['요약', '정리', '개요', '내용']):
                return self._summarize_document(full_text, filename)
            elif any(word in query for word in ['비용', '금액', '가격', '원']):
                return self._extract_cost_info(full_text, filename)
            elif any(word in query for word in ['장비', '모델', '제품']):
                return self._extract_equipment_info(full_text, filename)
            else:
                return self._keyword_search(full_text, query, filename)

        except Exception as e:
            return f"❌ 오류 발생: {e}"

    def _summarize_document(self, text: str, filename: str) -> str:
        """문서 요약 (처음 2000자)"""
        preview = text[:2000]
        lines = [line.strip() for line in preview.split('\n') if line.strip()]

        answer = f"📄 **{filename}** 문서 요약\n\n"
        answer += '\n'.join(lines[:30])

        if len(text) > 2000:
            answer += f"\n\n... (총 {len(text)}자 중 일부)\n"

        return answer

    def _extract_cost_info(self, text: str, filename: str) -> str:
        """비용 정보 추출"""
        import re

        answer = f"💰 **{filename}** 비용 정보\n\n"

        # 금액 패턴 찾기 (쉼표 포함 숫자, "원" 선택적)
        cost_patterns = [
            r'(\d{1,3}(?:,\d{3})+)\s*원',  # 1,234,567원
            r'(\d+)\s*원',                   # 123원
            r'합계[:\s]*(\d{1,3}(?:,\d{3})+)',  # 합계: 1,234,567
            r'총[액비용][:\s]*(\d{1,3}(?:,\d{3})+)',  # 총액: 1,234,567
            r'(?:비용|금액|가격)[:\s]*(\d{1,3}(?:,\d{3})+)',  # 비용: 1,234,567
            r'\n(\d{1,3}(?:,\d{3})+)\n',    # 줄바꿈으로 둘러싸인 금액
        ]

        found_costs = []
        for pattern in cost_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                cost = match.group(1)
                # 주변 텍스트 추출
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()
                found_costs.append((cost, context))

        if found_costs:
            # 중복 제거
            seen = set()
            for cost, context in found_costs:
                if cost not in seen:
                    answer += f"• **{cost}원**\n"
                    answer += f"  ({context})\n\n"
                    seen.add(cost)
        else:
            answer += "❌ 금액 정보를 찾을 수 없습니다.\n"

        return answer

    def _extract_equipment_info(self, text: str, filename: str) -> str:
        """장비 정보 추출"""
        import re

        answer = f"🔧 **{filename}** 장비 정보\n\n"

        # 장비 관련 키워드 패턴
        equipment_patterns = [
            r'([A-Z0-9]+(?:ex|EX)[0-9.]+[A-Z]*)',  # HJ22ex7.6B 같은 모델명
            r'(CAM#?\d+)',  # CAM#1, CAM1
            r'카메라\s*([가-힣\s]+)',
            r'모델[:\s]*([A-Z0-9-]+)',
        ]

        found_equipment = []
        for pattern in equipment_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                equipment = match.group(1).strip()
                if len(equipment) > 2:
                    # 주변 텍스트
                    start = max(0, match.start() - 50)
                    end = min(len(text), match.end() + 50)
                    context = text[start:end].strip()
                    found_equipment.append((equipment, context))

        if found_equipment:
            seen = set()
            for equip, context in found_equipment:
                if equip not in seen and len(equip) > 2:
                    answer += f"• **{equip}**\n"
                    answer += f"  ({context[:100]}...)\n\n"
                    seen.add(equip)
        else:
            answer += "❌ 장비 정보를 찾을 수 없습니다.\n"

        return answer

    def _keyword_search(self, text: str, query: str, filename: str) -> str:
        """키워드 기반 검색"""
        import re

        answer = f"🔍 **{filename}** 검색 결과\n\n"

        # 질문에서 키워드 추출
        keywords = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}|\d+', query)

        # 키워드가 포함된 줄 찾기
        lines = text.split('\n')
        relevant_sections = []

        for i, line in enumerate(lines):
            if any(keyword in line for keyword in keywords):
                # 앞뒤 2줄씩 포함
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                section = '\n'.join(lines[start:end])
                if section.strip() and section not in relevant_sections:
                    relevant_sections.append(section.strip())

        if relevant_sections:
            answer += '\n\n---\n\n'.join(relevant_sections[:5])
        else:
            answer += f"❌ '{query}'에 대한 정보를 찾을 수 없습니다.\n"
            answer += "\n📄 문서 미리보기 (처음 500자):\n\n"
            answer += text[:500]

        return answer

    def _get_pdf_content(self, pdf_path) -> str:
        """PDF 내용 추출 (OCR 캐시 우선)"""
        import pdfplumber
        import json
        import hashlib
        from pathlib import Path

        # 1. pdfplumber로 추출 시도
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
        except Exception as e:
            print(f"pdfplumber 추출 실패: {e}")

        # 2. OCR 캐시 확인
        ocr_cache_path = Path("docs/.ocr_cache.json")
        if ocr_cache_path.exists():
            try:
                with open(ocr_cache_path, 'r', encoding='utf-8') as f:
                    ocr_cache = json.load(f)

                # 파일 해시 계산
                with open(pdf_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                # OCR 캐시에서 찾기
                if file_hash in ocr_cache:
                    ocr_text = ocr_cache[file_hash].get('text', '')
                    # OCR 텍스트가 더 길면 사용
                    if len(ocr_text) > len(full_text):
                        print(f"✅ OCR 캐시 사용: {pdf_path.name} ({len(ocr_text)}자)")
                        return ocr_text
            except Exception as e:
                print(f"OCR 캐시 로드 실패: {e}")

        return full_text

def main():
    """테스트"""
    print("🚀 빠른 수정 RAG 테스트")

    rag = QuickFixRAG()

    test_queries = [
        "기안자 남준수 문서 찾아줘",
        "DVR 관련 문서",
        "카메라 수리 비용"
    ]

    for query in test_queries:
        print(f"\n📌 {query}")
        print("-" * 50)

        start = time.time()
        response = rag.answer(query)
        elapsed = time.time() - start

        print(response)
        print(f"⏱️ 응답 시간: {elapsed:.2f}초")

if __name__ == "__main__":
    main()