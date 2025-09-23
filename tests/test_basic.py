"""기본 테스트"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_import():
    """Import 테스트"""
    import perfect_rag
    import config
    assert True

def test_pdf_files_exist():
    """PDF 파일 존재 확인"""
    docs_dir = Path("docs")
    pdfs = list(docs_dir.rglob("*.pdf"))
    assert len(pdfs) > 0

def test_config_values():
    """설정 값 확인"""
    import config
    assert config.N_CTX > 0
    assert config.N_GPU_LAYERS >= 0
