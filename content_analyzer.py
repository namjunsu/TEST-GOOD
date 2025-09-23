
class ContentAnalyzer:
    """컨텐츠 분석 전문 클래스"""

    def __init__(self, rag_instance):
        self.rag = rag_instance

    def analyze_by_content(self, query: str, content_type: str) -> Dict:
        """컨텐츠 기반 분석 (기존 186줄 → 25줄)"""
        # 1. 컨텐츠 타입별 처리
        handler = self._get_content_handler(content_type)

        # 2. 분석 실행
        results = handler.analyze(query)

        # 3. 후처리
        return self._post_process(results)

    def _get_content_handler(self, content_type: str):
        """핸들러 선택 (15줄)"""
        handlers = {
            'pdf': PDFContentHandler(self.rag),
            'text': TextContentHandler(self.rag),
            'mixed': MixedContentHandler(self.rag)
        }
        return handlers.get(content_type, handlers['mixed'])

    def _post_process(self, results: Dict) -> Dict:
        """후처리 (20줄)"""
        # 정제, 포맷팅 등
        return results

class PDFContentHandler:
    """PDF 전문 핸들러 (50줄)"""
    def analyze(self, query: str) -> Dict:
        pass

class TextContentHandler:
    """텍스트 전문 핸들러 (30줄)"""
    def analyze(self, query: str) -> Dict:
        pass

class MixedContentHandler:
    """혼합 컨텐츠 핸들러 (40줄)"""
    def analyze(self, query: str) -> Dict:
        pass
