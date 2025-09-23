#!/usr/bin/env python3
"""테스트 시스템 구축"""

from pathlib import Path
import subprocess

def create_test_structure():
    """테스트 구조 생성"""
    print("📁 테스트 구조 생성...")
    Path("tests").mkdir(exist_ok=True)
    Path("tests/unit").mkdir(exist_ok=True)
    Path("tests/integration").mkdir(exist_ok=True)
    (Path("tests") / "__init__.py").touch()
    (Path("tests/unit") / "__init__.py").touch()
    print("✅ 완료")

def create_pytest_ini():
    """pytest.ini 생성"""
    content = """[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
"""
    with open("pytest.ini", "w") as f:
        f.write(content)
    print("✅ pytest.ini 생성")

def create_basic_test():
    """기본 테스트 생성"""
    test_content = '''"""기본 테스트"""
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
'''
    
    with open("tests/test_basic.py", "w") as f:
        f.write(test_content)
    print("✅ 기본 테스트 생성")

def install_pytest():
    """pytest 설치"""
    print("📦 pytest 설치...")
    subprocess.run(["pip", "install", "-q", "pytest", "pytest-cov"], capture_output=True)
    print("✅ 설치 완료")

def main():
    print("🧪 테스트 시스템 구축")
    print("=" * 50)
    
    create_test_structure()
    create_pytest_ini()
    create_basic_test()
    install_pytest()
    
    print("\n✅ 완료! 테스트 실행: pytest tests/")

if __name__ == "__main__":
    main()
