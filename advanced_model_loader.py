#!/usr/bin/env python3
"""
고급 모델 로더
Split GGUF 파일 처리 및 자동 폴백
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import hashlib
import json
import time

class AdvancedModelLoader:
    """고급 모델 로딩 시스템"""

    def __init__(self):
        self.models_dir = Path("models")
        self.cache_file = Path(".model_cache.json")
        self.load_cache()

    def load_cache(self):
        """모델 캐시 로드"""
        if self.cache_file.exists():
            with open(self.cache_file, 'r') as f:
                self.cache = json.load(f)
        else:
            self.cache = {}

    def save_cache(self):
        """모델 캐시 저장"""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)

    def find_available_models(self) -> Dict[str, Dict]:
        """사용 가능한 모델 찾기"""
        models = {}

        # GGUF 파일 찾기
        gguf_files = list(self.models_dir.glob("*.gguf"))

        # Split 파일 그룹화
        split_groups = {}
        standalone_files = []

        for file in gguf_files:
            # Split 파일 패턴 확인
            if "-00001-of-" in file.name:
                base_name = file.name.split("-00001-of-")[0]
                total_parts = int(file.name.split("-of-")[1].split(".")[0])

                # 모든 파트가 있는지 확인
                all_parts = []
                for i in range(1, total_parts + 1):
                    part_file = self.models_dir / f"{base_name}-{i:05d}-of-{total_parts:05d}.gguf"
                    if part_file.exists():
                        all_parts.append(part_file)

                if len(all_parts) == total_parts:
                    split_groups[base_name] = {
                        "type": "split",
                        "files": all_parts,
                        "main_file": all_parts[0],
                        "total_size": sum(f.stat().st_size for f in all_parts) / (1024**3),
                        "parts": total_parts
                    }
            elif not any(pattern in file.name for pattern in ["-00002-of-", "-00003-of-"]):
                # Standalone 파일
                standalone_files.append({
                    "type": "standalone",
                    "file": file,
                    "size": file.stat().st_size / (1024**3)
                })

        # 결과 정리
        for name, info in split_groups.items():
            models[name] = info

        for info in standalone_files:
            name = info["file"].stem
            models[name] = info

        return models

    def test_model_loading(self, model_path: Path, quick_test: bool = True) -> bool:
        """모델 로딩 테스트"""
        try:
            from llama_cpp import Llama

            # 빠른 테스트 설정
            test_config = {
                "n_ctx": 512 if quick_test else 2048,
                "n_batch": 64 if quick_test else 256,
                "n_gpu_layers": 0,  # CPU로 테스트
                "verbose": False,
                "n_threads": 2
            }

            print(f"🔍 테스트 중: {model_path.name}")

            # 로딩 시도
            llm = Llama(
                model_path=str(model_path),
                **test_config
            )

            # 간단한 생성 테스트
            if not quick_test:
                response = llm("Test", max_tokens=5)
                if response and 'choices' in response:
                    print(f"✅ 응답 생성 성공")
                    return True
            else:
                # 모델이 로드되었는지만 확인
                return llm is not None

        except Exception as e:
            print(f"❌ 로딩 실패: {e}")
            return False

        return False

    def update_config_files(self, model_path: Path):
        """설정 파일 업데이트"""
        updates = []

        # config.yaml 업데이트
        config_yaml = Path("config.yaml")
        if config_yaml.exists():
            import yaml
            with open(config_yaml, 'r') as f:
                config = yaml.safe_load(f)

            config['models']['qwen']['path'] = str(model_path)
            config['models']['qwen']['model_file'] = model_path.name

            with open(config_yaml, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

            updates.append("config.yaml")

        # config.py 업데이트
        config_py = Path("config.py")
        if config_py.exists():
            content = config_py.read_text()

            # 기존 경로 패턴 찾기
            import re
            pattern = r'QWEN_MODEL_PATH\s*=\s*["\'].*?["\']'
            new_line = f'QWEN_MODEL_PATH = "{model_path}"'

            content = re.sub(pattern, new_line, content)
            config_py.write_text(content)

            updates.append("config.py")

        # config_manager.py 업데이트
        config_manager = Path("config_manager.py")
        if config_manager.exists():
            content = config_manager.read_text()
            if "get_default_config" in content:
                # 기본 설정 업데이트
                content = content.replace(
                    '"path": "./models/qwen2.5-7b-instruct-q5_k_m.gguf"',
                    f'"path": "{model_path}"'
                )
                config_manager.write_text(content)
                updates.append("config_manager.py")

        if updates:
            print(f"✅ 설정 파일 업데이트: {', '.join(updates)}")

        return updates

    def auto_select_model(self) -> Optional[Path]:
        """자동으로 최적 모델 선택"""
        models = self.find_available_models()

        if not models:
            print("❌ 사용 가능한 모델이 없습니다")
            return None

        print(f"\n📦 발견된 모델: {len(models)}개")

        # 우선순위 리스트
        priority_models = [
            "qwen2.5-7b-instruct-q4_k_m",
            "qwen2.5-7b-instruct-q5_k_m",
            "qwen2.5-3b-instruct",
            "qwen-7b"
        ]

        # 우선순위에 따라 선택
        for priority_name in priority_models:
            for model_name, info in models.items():
                if priority_name in model_name:
                    if info["type"] == "split":
                        model_path = info["main_file"]
                        print(f"✅ Split 모델 선택: {model_name} ({info['parts']}개 파트)")
                    else:
                        model_path = info["file"]
                        print(f"✅ 단일 모델 선택: {model_name} ({info['size']:.2f}GB)")

                    # 테스트
                    if self.test_model_loading(model_path, quick_test=True):
                        print(f"✅ 모델 로딩 테스트 성공: {model_path.name}")
                        return model_path
                    else:
                        print(f"⚠️ 모델 로딩 실패, 다음 모델 시도...")

        # 첫 번째 사용 가능한 모델 선택
        for model_name, info in models.items():
            if info["type"] == "split":
                model_path = info["main_file"]
            else:
                model_path = info["file"]

            if self.test_model_loading(model_path, quick_test=True):
                print(f"✅ 대체 모델 선택: {model_path.name}")
                return model_path

        print("❌ 로드 가능한 모델을 찾을 수 없습니다")
        return None

    def fix_all_configs(self):
        """모든 설정 자동 수정"""
        print("="*60)
        print("모델 로딩 자동 수정 시작")
        print("="*60)

        # 1. 사용 가능한 모델 찾기
        model_path = self.auto_select_model()

        if not model_path:
            return False

        # 2. 설정 파일 업데이트
        self.update_config_files(model_path)

        # 3. 캐시 저장
        self.cache["last_working_model"] = str(model_path)
        self.cache["last_update"] = time.time()
        self.save_cache()

        print(f"\n✅ 모든 설정이 업데이트되었습니다!")
        print(f"선택된 모델: {model_path.name}")

        return True


def main():
    """메인 실행"""
    loader = AdvancedModelLoader()

    # 자동 수정
    if loader.fix_all_configs():
        print("\n🎉 성공! 이제 시스템을 사용할 수 있습니다.")

        # 간단한 테스트
        print("\n테스트 실행:")
        print("  python3 -c \"from perfect_rag import PerfectRAG; rag = PerfectRAG(); print(rag.answer('테스트'))\"")

        return 0
    else:
        print("\n❌ 자동 수정 실패")
        print("수동으로 모델을 다운로드해주세요:")
        print("  https://huggingface.co/Qwen/")
        return 1


if __name__ == "__main__":
    sys.exit(main())