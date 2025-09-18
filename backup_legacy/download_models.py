#!/usr/bin/env python3
"""
AI-CHAT-V3 모델 다운로드 스크립트
Qwen2.5-7B-Instruct GGUF 모델 자동 다운로드

사용법:
    python3 download_models.py
    python3 download_models.py --model-dir ./models
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Optional
import hashlib

def install_huggingface_hub():
    """huggingface_hub 패키지 설치"""
    try:
        import huggingface_hub
        return True
    except ImportError:
        print("📦 huggingface-hub 패키지 설치 중...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface-hub"])
            import huggingface_hub
            return True
        except Exception as e:
            print(f"❌ huggingface-hub 설치 실패: {e}")
            return False

def get_file_size_mb(filepath: Path) -> float:
    """파일 크기를 MB 단위로 반환"""
    if filepath.exists():
        return filepath.stat().st_size / (1024 * 1024)
    return 0

def verify_file_size(filepath: Path, expected_mb: float, tolerance: float = 10.0) -> bool:
    """파일 크기 검증 (tolerance MB 오차 허용)"""
    if not filepath.exists():
        return False
    
    actual_mb = get_file_size_mb(filepath)
    diff = abs(actual_mb - expected_mb)
    
    if diff <= tolerance:
        return True
    else:
        print(f"⚠️  파일 크기 이상: {filepath.name}")
        print(f"   예상: {expected_mb:.1f}MB, 실제: {actual_mb:.1f}MB, 차이: {diff:.1f}MB")
        return False

def download_with_huggingface_hub(model_dir: Path) -> bool:
    """huggingface_hub를 사용하여 모델 다운로드"""
    if not install_huggingface_hub():
        return False
    
    try:
        from huggingface_hub import hf_hub_download
        
        repo_id = "Qwen/Qwen2.5-7B-Instruct-GGUF"
        
        # 다운로드할 파일들과 예상 크기 (MB)
        files_to_download = [
            ("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf", 3800.0),
            ("qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf", 658.0)
        ]
        
        print(f"📥 Hugging Face Hub에서 모델 다운로드 시작...")
        print(f"📂 저장 위치: {model_dir}")
        print(f"🔗 Repository: {repo_id}")
        
        for filename, expected_size in files_to_download:
            filepath = model_dir / filename
            
            # 이미 있고 크기가 맞으면 스킵
            if filepath.exists() and verify_file_size(filepath, expected_size):
                print(f"✅ {filename} 이미 존재 (크기 확인됨)")
                continue
            
            print(f"📥 {filename} 다운로드 중... (약 {expected_size:.0f}MB)")
            
            try:
                downloaded_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=str(model_dir),
                    local_dir_use_symlinks=False,
                    resume_download=True
                )
                
                if verify_file_size(Path(downloaded_path), expected_size):
                    print(f"✅ {filename} 다운로드 완료")
                else:
                    print(f"❌ {filename} 다운로드 완료되었으나 크기가 다름")
                    return False
                    
            except Exception as e:
                print(f"❌ {filename} 다운로드 실패: {e}")
                return False
        
        print("🎉 모든 모델 파일 다운로드 완료!")
        return True
        
    except Exception as e:
        print(f"❌ Hugging Face Hub 다운로드 실패: {e}")
        return False

def download_with_wget_curl(model_dir: Path) -> bool:
    """wget 또는 curl을 사용하여 모델 다운로드"""
    base_url = "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main"
    
    files_to_download = [
        ("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf", 3800.0),
        ("qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf", 658.0)
    ]
    
    # wget 또는 curl 확인
    download_cmd = None
    if subprocess.run(["which", "wget"], capture_output=True).returncode == 0:
        download_cmd = "wget"
    elif subprocess.run(["which", "curl"], capture_output=True).returncode == 0:
        download_cmd = "curl"
    else:
        print("❌ wget 또는 curl이 필요합니다.")
        return False
    
    print(f"📥 {download_cmd}를 사용하여 모델 다운로드 시작...")
    
    for filename, expected_size in files_to_download:
        filepath = model_dir / filename
        url = f"{base_url}/{filename}"
        
        # 이미 있고 크기가 맞으면 스킵
        if filepath.exists() and verify_file_size(filepath, expected_size):
            print(f"✅ {filename} 이미 존재 (크기 확인됨)")
            continue
        
        print(f"📥 {filename} 다운로드 중... (약 {expected_size:.0f}MB)")
        
        try:
            if download_cmd == "wget":
                cmd = [
                    "wget", "--progress=bar:force:noscroll", 
                    "--continue", "-O", str(filepath), url
                ]
            else:  # curl
                cmd = [
                    "curl", "-L", "--progress-bar", 
                    "--continue-at", "-", "-o", str(filepath), url
                ]
            
            result = subprocess.run(cmd, check=True)
            
            if verify_file_size(filepath, expected_size):
                print(f"✅ {filename} 다운로드 완료")
            else:
                print(f"❌ {filename} 다운로드 완료되었으나 크기가 다름")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"❌ {filename} 다운로드 실패: {e}")
            return False
    
    print("🎉 모든 모델 파일 다운로드 완료!")
    return True

def main():
    parser = argparse.ArgumentParser(description="AI-CHAT-V3 모델 다운로드")
    parser.add_argument(
        "--model-dir", 
        type=str, 
        default="./models",
        help="모델 파일을 저장할 디렉토리 (기본값: ./models)"
    )
    parser.add_argument(
        "--method",
        choices=["auto", "huggingface", "wget"],
        default="auto",
        help="다운로드 방법 선택 (기본값: auto)"
    )
    
    args = parser.parse_args()
    
    # 모델 디렉토리 생성
    model_dir = Path(args.model_dir).resolve()
    model_dir.mkdir(parents=True, exist_ok=True)
    
    print("🚀 AI-CHAT-V3 모델 다운로드 시작")
    print("=" * 40)
    print(f"📂 저장 위치: {model_dir}")
    
    # 현재 공간 확인
    import shutil
    free_space_gb = shutil.disk_usage(model_dir).free / (1024**3)
    print(f"💾 사용 가능 공간: {free_space_gb:.1f}GB")
    
    if free_space_gb < 5:
        print("⚠️  디스크 공간이 부족할 수 있습니다. (5GB 이상 권장)")
        response = input("계속 진행하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("❌ 다운로드 취소됨")
            return 1
    
    print()
    
    # 다운로드 방법 선택
    success = False
    
    if args.method == "auto":
        # 1. huggingface_hub 시도
        print("🔄 방법 1: Hugging Face Hub 시도...")
        success = download_with_huggingface_hub(model_dir)
        
        # 2. wget/curl 시도
        if not success:
            print("\n🔄 방법 2: wget/curl 시도...")
            success = download_with_wget_curl(model_dir)
            
    elif args.method == "huggingface":
        success = download_with_huggingface_hub(model_dir)
    elif args.method == "wget":
        success = download_with_wget_curl(model_dir)
    
    if success:
        print("\n🎉 모델 다운로드가 완료되었습니다!")
        print(f"📁 위치: {model_dir}")
        
        # 다운로드된 파일 확인
        total_size = 0
        for file_path in model_dir.glob("*.gguf"):
            size_mb = get_file_size_mb(file_path)
            total_size += size_mb
            print(f"   📄 {file_path.name}: {size_mb:.1f}MB")
        
        print(f"💾 총 크기: {total_size:.1f}MB ({total_size/1024:.1f}GB)")
        print("\n✅ 이제 build_index.py를 실행하여 시스템을 설정할 수 있습니다.")
        return 0
    else:
        print("\n❌ 모델 다운로드 실패")
        print("💡 해결방법:")
        print("   1. 인터넷 연결 확인")
        print("   2. 디스크 공간 확인 (5GB 이상)")
        print("   3. 수동 다운로드:")
        print("      https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/tree/main")
        return 1

if __name__ == "__main__":
    sys.exit(main())