#!/usr/bin/env python3
"""
LLM 모델 자동 설치 스크립트
Qwen2.5-7B 모델을 다운로드하고 설치합니다
"""

import os
import sys
import urllib.request
import hashlib
from pathlib import Path
import json
import time

# 색상 코드
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"


class ModelInstaller:
    def __init__(self):
        self.models_dir = Path("models")
        self.model_configs = {
            "qwen2.5-7b": {
                "filename": "qwen2.5-7b-instruct-q5_k_m.gguf",
                "urls": [
                    # Hugging Face 미러
                    "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q5_k_m.gguf",
                    # 대체 URL (백업)
                    "https://huggingface.co/TheBloke/Qwen-7B-Chat-GGUF/resolve/main/qwen-7b-chat.Q5_K_M.gguf"
                ],
                "size_gb": 5.4,
                "sha256": None  # 실제 해시값으로 업데이트 필요
            },
            "qwen2.5-7b-small": {
                "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
                "urls": [
                    "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf"
                ],
                "size_gb": 4.5,
                "sha256": None
            },
            "fallback-3b": {
                "filename": "qwen2.5-3b-instruct-q5_k_m.gguf",
                "urls": [
                    "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q5_k_m.gguf"
                ],
                "size_gb": 2.4,
                "sha256": None
            }
        }

    def check_disk_space(self, required_gb):
        """디스크 공간 확인"""
        stat = os.statvfs(".")
        available_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)

        if available_gb < required_gb * 1.2:  # 20% 여유 공간
            print(f"{RED}❌ 디스크 공간 부족: {available_gb:.1f}GB 사용 가능, {required_gb:.1f}GB 필요{RESET}")
            return False

        print(f"{GREEN}✅ 디스크 공간 충분: {available_gb:.1f}GB 사용 가능{RESET}")
        return True

    def download_with_progress(self, url, filepath, expected_size_gb=None):
        """진행률 표시와 함께 다운로드"""
        try:
            print(f"{BLUE}📥 다운로드 시작: {url}{RESET}")

            # 파일 크기 확인
            with urllib.request.urlopen(url) as response:
                total_size = int(response.headers.get('Content-Length', 0))

                if total_size == 0:
                    print(f"{YELLOW}⚠️ 파일 크기를 확인할 수 없습니다{RESET}")

                downloaded = 0
                chunk_size = 1024 * 1024  # 1MB chunks

                with open(filepath, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        # 진행률 표시
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            downloaded_gb = downloaded / (1024**3)
                            total_gb = total_size / (1024**3)

                            print(f"\r진행률: {progress:.1f}% ({downloaded_gb:.2f}/{total_gb:.2f} GB)", end="")

            print(f"\n{GREEN}✅ 다운로드 완료: {filepath.name}{RESET}")
            return True

        except Exception as e:
            print(f"\n{RED}❌ 다운로드 실패: {e}{RESET}")
            return False

    def verify_model(self, filepath, expected_hash=None):
        """모델 파일 검증"""
        if not filepath.exists():
            return False

        # 파일 크기 확인
        size_gb = filepath.stat().st_size / (1024**3)
        print(f"파일 크기: {size_gb:.2f} GB")

        if size_gb < 0.1:
            print(f"{RED}❌ 파일이 너무 작습니다{RESET}")
            return False

        # SHA256 해시 확인 (선택적)
        if expected_hash:
            print("해시 검증 중...")
            sha256 = hashlib.sha256()
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)

            if sha256.hexdigest() != expected_hash:
                print(f"{RED}❌ 해시 불일치{RESET}")
                return False

        return True

    def install_model(self, model_name="qwen2.5-7b"):
        """모델 설치"""
        if model_name not in self.model_configs:
            print(f"{RED}❌ 알 수 없는 모델: {model_name}{RESET}")
            return False

        config = self.model_configs[model_name]

        # 모델 디렉토리 생성
        self.models_dir.mkdir(exist_ok=True)
        model_path = self.models_dir / config["filename"]

        # 이미 존재하는지 확인
        if model_path.exists():
            print(f"{YELLOW}⚠️ 모델이 이미 존재합니다: {model_path}{RESET}")
            if self.verify_model(model_path, config.get("sha256")):
                print(f"{GREEN}✅ 기존 모델이 유효합니다{RESET}")
                return True
            else:
                print(f"{YELLOW}기존 모델이 손상되었습니다. 재다운로드합니다...{RESET}")
                model_path.unlink()

        # 디스크 공간 확인
        if not self.check_disk_space(config["size_gb"]):
            return False

        # URL 순차적으로 시도
        for url in config["urls"]:
            print(f"\n{BLUE}시도 중: {model_name}{RESET}")

            if self.download_with_progress(url, model_path, config["size_gb"]):
                if self.verify_model(model_path, config.get("sha256")):
                    print(f"{GREEN}✅ 모델 설치 성공!{RESET}")
                    return True
                else:
                    print(f"{YELLOW}⚠️ 검증 실패, 다음 URL 시도...{RESET}")
                    model_path.unlink(missing_ok=True)

        return False

    def create_config_update(self):
        """config.yaml 업데이트"""
        config_file = Path("config.yaml")

        if config_file.exists():
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # 모델 경로 업데이트
            if 'models' in config and 'qwen' in config['models']:
                config['models']['qwen']['path'] = str(self.models_dir / "qwen2.5-7b-instruct-q5_k_m.gguf")

                with open(config_file, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

                print(f"{GREEN}✅ config.yaml 업데이트 완료{RESET}")

    def install_fallback_model(self):
        """더 작은 폴백 모델 설치"""
        print(f"\n{YELLOW}기본 모델 설치 실패. 더 작은 모델을 시도합니다...{RESET}")

        # 3B 모델 시도
        if self.install_model("fallback-3b"):
            # config 업데이트
            self.update_config_for_fallback()
            return True

        return False

    def update_config_for_fallback(self):
        """폴백 모델용 설정 업데이트"""
        config_file = Path("config.yaml")
        if config_file.exists():
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            config['models']['qwen']['path'] = str(self.models_dir / "qwen2.5-3b-instruct-q5_k_m.gguf")
            config['models']['qwen']['name'] = "Qwen2.5-3B (Fallback)"

            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def main():
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}LLM 모델 자동 설치 시스템{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

    installer = ModelInstaller()

    # 설치 옵션 선택
    print("설치할 모델을 선택하세요:")
    print("1. Qwen2.5-7B (권장, 5.4GB)")
    print("2. Qwen2.5-7B Small (4.5GB)")
    print("3. Qwen2.5-3B (경량, 2.4GB)")
    print("4. 자동 선택 (디스크 공간에 따라)")

    choice = input("\n선택 (1-4, 기본값 4): ").strip() or "4"

    model_map = {
        "1": "qwen2.5-7b",
        "2": "qwen2.5-7b-small",
        "3": "fallback-3b",
        "4": "auto"
    }

    selected_model = model_map.get(choice, "auto")

    if selected_model == "auto":
        # 디스크 공간에 따라 자동 선택
        stat = os.statvfs(".")
        available_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)

        if available_gb > 10:
            selected_model = "qwen2.5-7b"
        elif available_gb > 6:
            selected_model = "qwen2.5-7b-small"
        else:
            selected_model = "fallback-3b"

        print(f"\n자동 선택: {selected_model} (사용 가능 공간: {available_gb:.1f}GB)")

    # 모델 설치
    success = installer.install_model(selected_model)

    if not success and selected_model != "fallback-3b":
        # 폴백 시도
        success = installer.install_fallback_model()

    if success:
        installer.create_config_update()
        print(f"\n{GREEN}🎉 모델 설치가 완료되었습니다!{RESET}")
        print(f"이제 RAG 시스템을 사용할 수 있습니다.")
        return 0
    else:
        print(f"\n{RED}❌ 모델 설치에 실패했습니다.{RESET}")
        print("수동으로 모델을 다운로드해주세요:")
        print("https://huggingface.co/Qwen/")
        return 1


if __name__ == "__main__":
    sys.exit(main())