"""
Document Processing Module
문서 처리 및 청킹 모듈
"""

import os
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import pdfplumber
import hashlib
from datetime import datetime


class DocumentProcessor:
    """문서 처리기"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.chunk_size = config.get('chunk_size', 500)
        self.chunk_overlap = config.get('chunk_overlap', 100)

    def load_document(self, file_path: Path) -> Optional[str]:
        """문서 로드"""
        try:
            if file_path.suffix.lower() == '.pdf':
                return self._extract_pdf_text(file_path)
            elif file_path.suffix.lower() == '.txt':
                return file_path.read_text(encoding='utf-8')
            else:
                return None
        except Exception as e:
            print(f"문서 로드 실패: {e}")
            return None

    def _extract_pdf_text(self, file_path: Path) -> str:
        """PDF 텍스트 추출"""
        text_parts = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            return '\n'.join(text_parts)

        except Exception as e:
            print(f"PDF 추출 실패: {e}")
            return ""

    def extract_metadata(self, file_path: Path, content: str) -> Dict[str, Any]:
        """메타데이터 추출"""
        metadata = {
            'filename': file_path.name,
            'path': str(file_path),
            'size': file_path.stat().st_size,
            'modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        }

        # 연도 추출
        year_match = re.search(r'20\d{2}', file_path.name)
        if year_match:
            metadata['year'] = int(year_match.group())

        # 카테고리 추출
        category = self._extract_category(file_path.name, content)
        if category:
            metadata['category'] = category

        # 키워드 추출
        keywords = self._extract_keywords(content)
        if keywords:
            metadata['keywords'] = keywords

        return metadata

    def _extract_category(self, filename: str, content: str) -> Optional[str]:
        """카테고리 추출"""
        categories = {
            '구매': ['구매', '구입', '도입', '입찰'],
            '수리': ['수리', '보수', '정비', '점검'],
            '검토': ['검토', '검수', '평가', '분석'],
            '폐기': ['폐기', '처분', '제각', '불용'],
            '소모품': ['소모품', '부품', '액세서리']
        }

        filename_lower = filename.lower()
        content_preview = content[:1000].lower() if content else ""

        for category, keywords in categories.items():
            if any(kw in filename_lower or kw in content_preview for kw in keywords):
                return category

        return None

    def _extract_keywords(self, content: str) -> List[str]:
        """핵심 키워드 추출"""
        if not content:
            return []

        # 간단한 키워드 추출 (추후 개선 필요)
        keywords = []

        # 장비명 패턴
        equipment_pattern = r'(중계차|카메라|렌즈|삼각대|조명|스위처|믹서|모니터|서버|스토리지)'
        matches = re.findall(equipment_pattern, content[:2000])
        keywords.extend(list(set(matches)))

        # 회사명 패턴
        company_pattern = r'([가-힣]+(?:테크|시스템|전자|정보|통신|미디어|방송))'
        matches = re.findall(company_pattern, content[:2000])
        keywords.extend(list(set(matches[:5])))  # 최대 5개

        return keywords[:10]  # 최대 10개 키워드

    def chunk_document(self, doc: 'Document') -> List['Chunk']:
        """문서를 청크로 분할"""
        from rag_core import Chunk

        chunks = []
        content = doc.content
        doc_id = doc.id

        # 의미적 경계를 고려한 청킹
        sentences = self._split_sentences(content)

        current_chunk = []
        current_size = 0
        chunk_index = 0

        for sentence in sentences:
            sentence_size = len(sentence.split())

            if current_size + sentence_size > self.chunk_size and current_chunk:
                # 청크 생성
                chunk_content = ' '.join(current_chunk)
                chunk_id = f"{doc_id}_{chunk_index:04d}"

                chunk = Chunk(
                    id=chunk_id,
                    doc_id=doc_id,
                    content=chunk_content,
                    metadata={
                        'chunk_index': chunk_index,
                        'doc_metadata': doc.metadata
                    }
                )

                chunks.append(chunk)
                chunk_index += 1

                # 오버랩 처리
                overlap_size = 0
                overlap_sentences = []

                for sent in reversed(current_chunk):
                    overlap_size += len(sent.split())
                    overlap_sentences.insert(0, sent)
                    if overlap_size >= self.chunk_overlap:
                        break

                current_chunk = overlap_sentences
                current_size = overlap_size

            current_chunk.append(sentence)
            current_size += sentence_size

        # 마지막 청크 처리
        if current_chunk:
            chunk_content = ' '.join(current_chunk)
            chunk_id = f"{doc_id}_{chunk_index:04d}"

            chunk = Chunk(
                id=chunk_id,
                doc_id=doc_id,
                content=chunk_content,
                metadata={
                    'chunk_index': chunk_index,
                    'doc_metadata': doc.metadata
                }
            )

            chunks.append(chunk)

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장으로 분할"""
        # 간단한 문장 분할 (추후 개선 필요)
        sentences = re.split(r'[.!?]\s+', text)

        # 빈 문장 제거 및 정제
        sentences = [s.strip() for s in sentences if s.strip()]

        return sentences