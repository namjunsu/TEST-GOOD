#!/usr/bin/env python3
"""
AI-CHAT-V3 마이그레이션 패키지 검증 스크립트
설치 전후 필수 파일들과 기능을 검증합니다.

사용법:
    python3 validate_migration.py --check-package  # 패키지 검증
    python3 validate_migration.py --check-install  # 설치 후 검증
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
import importlib.util

def check_file_exists(filepath: Path, description: str = "") -> Tuple[bool, str]:
    """파일 존재 여부 확인"""
    if filepath.exists():
        size = filepath.stat().st_size
        size_str = f"{size:,} bytes"
        if size > 1024*1024:
            size_str = f"{size/(1024*1024):.1f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.1f} KB"
        
        return True, f"✅ {description or filepath.name}: {size_str}"
    else:
        return False, f"❌ {description or filepath.name}: 파일 없음"

def check_python_import(module_name: str, description: str = "") -> Tuple[bool, str]:
    """Python 모듈 import 가능 여부 확인"""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is not None:
            return True, f"✅ {description or module_name}: 모듈 사용 가능"
        else:
            return False, f"❌ {description or module_name}: 모듈 없음"
    except ImportError:
        return False, f"❌ {description or module_name}: import 실패"

def validate_migration_package(package_dir: Path) -> Dict[str, List[str]]:
    """마이그레이션 패키지 검증"""
    results = {"success": [], "error": [], "warning": []}
    
    print("🔍 마이그레이션 패키지 검증 중...")
    print("=" * 50)
    
    # 1. 필수 디렉토리 구조 확인
    required_dirs = {
        "core": "핵심 Python 파일들",
        "rag_system": "RAG 시스템 모듈들", 
        "docs": "PDF 문서들",
        "config": "설정 파일들"
    }
    
    print("📁 디렉토리 구조 확인:")
    for dir_name, description in required_dirs.items():
        dir_path = package_dir / dir_name
        success, message = check_file_exists(dir_path, f"{description}")
        if success:
            file_count = len(list(dir_path.iterdir()))
            message += f" ({file_count}개 파일)"
            results["success"].append(message)
        else:
            results["error"].append(message)
        print(f"  {message}")
    
    print()
    
    # 2. 핵심 파일 확인
    print("🔧 핵심 파일 확인:")
    core_files = {
        "core/perfect_rag.py": "메인 RAG 시스템",
        "core/web_interface.py": "Streamlit 웹 UI",
        "core/build_index.py": "인덱싱 시스템",
        "core/config.py": "시스템 설정",
        "config/requirements.txt": "패키지 목록",
        "config/CLAUDE.md": "개발 가이드"
    }
    
    for file_path, description in core_files.items():
        full_path = package_dir / file_path
        success, message = check_file_exists(full_path, description)
        results["success" if success else "error"].append(message)
        print(f"  {message}")
    
    print()
    
    # 3. RAG 시스템 모듈 확인
    print("🤖 RAG 시스템 모듈 확인:")
    rag_modules = [
        "hybrid_search.py",
        "qwen_llm.py", 
        "korean_vector_store.py",
        "bm25_store.py",
        "metadata_extractor.py"
    ]
    
    rag_dir = package_dir / "rag_system"
    if rag_dir.exists():
        for module in rag_modules:
            module_path = rag_dir / module
            success, message = check_file_exists(module_path)
            results["success" if success else "error"].append(message)
            print(f"  {message}")
    else:
        results["error"].append("❌ rag_system 디렉토리 없음")
    
    print()
    
    # 4. 문서 파일 확인
    print("📚 문서 파일 확인:")
    docs_dir = package_dir / "docs"
    if docs_dir.exists():
        pdf_files = list(docs_dir.glob("*.pdf"))
        txt_files = list(docs_dir.glob("*.txt"))
        
        pdf_count = len(pdf_files)
        txt_count = len(txt_files)
        
        if pdf_count > 0:
            total_pdf_size = sum(f.stat().st_size for f in pdf_files)
            results["success"].append(f"✅ PDF 파일: {pdf_count}개 ({total_pdf_size/(1024*1024):.1f}MB)")
        else:
            results["error"].append("❌ PDF 파일이 없음")
            
        if txt_count > 0:
            total_txt_size = sum(f.stat().st_size for f in txt_files)
            results["success"].append(f"✅ TXT 파일: {txt_count}개 ({total_txt_size/(1024*1024):.1f}MB)")
        else:
            results["warning"].append("⚠️  TXT 파일이 없음 (선택사항)")
    
    for msg in results["success"][-2:]:
        print(f"  {msg}")
    for msg in results["error"][-2:] if results["error"] else []:
        print(f"  {msg}")
        
    print()
    
    # 5. 설치 스크립트 확인
    print("🚀 설치 스크립트 확인:")
    scripts = {
        "setup.sh": "Linux/WSL2 설치 스크립트",
        "setup.bat": "Windows 설치 스크립트", 
        "download_models.py": "모델 다운로드 스크립트",
        "MIGRATION_GUIDE.md": "마이그레이션 가이드"
    }
    
    for script, description in scripts.items():
        script_path = package_dir / script
        success, message = check_file_exists(script_path, description)
        results["success" if success else "error"].append(message)
        print(f"  {message}")
    
    return results

def validate_installed_system(install_dir: Path) -> Dict[str, List[str]]:
    """설치된 시스템 검증"""
    results = {"success": [], "error": [], "warning": []}
    
    print("🔍 설치된 시스템 검증 중...")
    print("=" * 50)
    
    # 1. 설치 디렉토리 확인
    if not install_dir.exists():
        results["error"].append(f"❌ 설치 디렉토리 없음: {install_dir}")
        return results
    
    print("📁 설치 디렉토리 구조:")
    
    # 2. 필수 파일들 확인
    required_files = [
        "perfect_rag.py",
        "web_interface.py", 
        "build_index.py",
        "config.py",
        "requirements.txt"
    ]
    
    for filename in required_files:
        filepath = install_dir / filename
        success, message = check_file_exists(filepath)
        results["success" if success else "error"].append(message)
        print(f"  {message}")
    
    print()
    
    # 3. 모델 파일 확인
    print("🤖 모델 파일 확인:")
    models_dir = install_dir / "models"
    if models_dir.exists():
        model_files = list(models_dir.glob("*.gguf"))
        if len(model_files) >= 2:
            total_size = sum(f.stat().st_size for f in model_files)
            results["success"].append(f"✅ 모델 파일: {len(model_files)}개 ({total_size/(1024**3):.1f}GB)")
        else:
            results["warning"].append("⚠️  모델 파일 부족 (2개 필요)")
    else:
        results["warning"].append("⚠️  models 디렉토리 없음")
    
    for msg in results["success"][-1:]:
        print(f"  {msg}")
    for msg in results["warning"][-1:] if results["warning"] else []:
        print(f"  {msg}")
    
    print()
    
    # 4. 가상환경 확인
    print("🐍 가상환경 확인:")
    venv_dir = install_dir / "ai-chat-env"
    if venv_dir.exists():
        python_exe = venv_dir / "bin" / "python"  # Linux
        if not python_exe.exists():
            python_exe = venv_dir / "Scripts" / "python.exe"  # Windows
            
        if python_exe.exists():
            results["success"].append("✅ 가상환경 설치됨")
        else:
            results["error"].append("❌ 가상환경 Python 실행파일 없음")
    else:
        results["warning"].append("⚠️  가상환경 없음")
    
    for msg in results["success"][-1:]:
        print(f"  {msg}")
    for msg in results["error"][-1:] if results["error"] else []:
        print(f"  {msg}")
    for msg in results["warning"][-1:] if results["warning"] else []:
        print(f"  {msg}")
    
    print()
    
    # 5. 패키지 import 테스트 (현재 환경에서)
    print("📦 주요 패키지 확인:")
    key_packages = {
        "streamlit": "Streamlit 웹 프레임워크",
        "sentence_transformers": "문장 임베딩",
        "faiss": "벡터 검색",
        "pdfplumber": "PDF 처리"
    }
    
    for package, description in key_packages.items():
        success, message = check_python_import(package, description)
        results["success" if success else "warning"].append(message)
        print(f"  {message}")
    
    print()
    
    # 6. 인덱스 파일 확인
    print("🗂️  인덱스 파일 확인:")
    db_dir = install_dir / "rag_system" / "db"
    if db_dir.exists():
        index_files = list(db_dir.glob("*"))
        if len(index_files) > 0:
            results["success"].append(f"✅ 인덱스 파일: {len(index_files)}개")
        else:
            results["warning"].append("⚠️  인덱스 파일 없음 (build_index.py 실행 필요)")
    else:
        results["warning"].append("⚠️  db 디렉토리 없음")
    
    for msg in results["success"][-1:]:
        print(f"  {msg}")
    for msg in results["warning"][-1:] if results["warning"] else []:
        print(f"  {msg}")
    
    return results

def print_summary(results: Dict[str, List[str]], title: str):
    """결과 요약 출력"""
    print(f"\n📊 {title} 요약:")
    print("=" * 30)
    
    success_count = len(results["success"])
    error_count = len(results["error"]) 
    warning_count = len(results["warning"])
    
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 오류: {error_count}개")
    print(f"⚠️  경고: {warning_count}개")
    
    if error_count == 0:
        print(f"\n🎉 {title} 완료!")
        if warning_count > 0:
            print("⚠️  경고 사항들을 확인해주세요.")
    else:
        print(f"\n❌ {title} 실패!")
        print("오류 사항들을 수정해주세요:")
        for error in results["error"]:
            print(f"  {error}")
    
    return error_count == 0

def main():
    parser = argparse.ArgumentParser(description="AI-CHAT-V3 마이그레이션 검증")
    parser.add_argument(
        "--check-package",
        action="store_true", 
        help="마이그레이션 패키지 검증"
    )
    parser.add_argument(
        "--check-install",
        action="store_true",
        help="설치된 시스템 검증" 
    )
    parser.add_argument(
        "--package-dir",
        type=str,
        default=".",
        help="마이그레이션 패키지 디렉토리 (기본값: 현재 디렉토리)"
    )
    parser.add_argument(
        "--install-dir", 
        type=str,
        default=None,
        help="설치 디렉토리 (기본값: ~/AI-CHAT-V3)"
    )
    
    args = parser.parse_args()
    
    if not args.check_package and not args.check_install:
        parser.print_help()
        return 1
    
    success = True
    
    if args.check_package:
        package_dir = Path(args.package_dir).resolve()
        results = validate_migration_package(package_dir)
        package_success = print_summary(results, "패키지 검증")
        success = success and package_success
    
    if args.check_install:
        if args.install_dir:
            install_dir = Path(args.install_dir).resolve()
        else:
            install_dir = Path.home() / "AI-CHAT-V3"
        
        results = validate_installed_system(install_dir) 
        install_success = print_summary(results, "설치 검증")
        success = success and install_success
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())