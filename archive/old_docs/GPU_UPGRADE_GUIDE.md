# GPU 업그레이드 가이드

## 🎮 현재 상황 (2025-09-10)

### 감지된 GPU
- **모델**: NVIDIA RTX PRO 4000 (16GB VRAM)
- **Driver**: 573.49 
- **CUDA Runtime**: 12.8
- **상태**: 설치되어 있지만 사용 안함

### 현재 설정
- **CPU**: Intel Ultra 9 285HX (24코어) - 20개 활용 중
- **Mode**: CPU 전용 (최적화 완료)
- **성능**: 예상 1-3초 (매우 양호)

## ⚠️ GPU 설치 실패 원인

1. **CUDA 버전 불일치**
   - Runtime: 12.8 vs Toolkit: 11.5
   - 해결 필요: 일치하는 버전 설치

2. **빌드 환경 문제**
   - g++-11과 CUDA 호환성 이슈
   - ninja 빌드 도구 부족

3. **저장소 설정 오류**
   - NVIDIA 저장소 추가 중 오류 발생

## 🛠️ GPU 업그레이드 단계별 가이드

### 1단계: 환경 정리
```bash
# 현재 CUDA 제거
sudo apt-get remove --purge nvidia-cuda-toolkit

# 저장소 오류 파일 제거
sudo rm -f /etc/apt/sources.list.d/archive_uri-https_developer_download_nvidia_com_comp-jammy.list

# 시스템 업데이트
sudo apt-get update
```

### 2단계: CUDA 12.8 설치 (Runtime과 맞추기)
```bash
# NVIDIA 공식 저장소 추가
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt-get update

# CUDA 12.8 설치
sudo apt-get install cuda-toolkit-12-8

# 환경 변수 설정
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 3단계: llama-cpp-python GPU 버전 설치
```bash
# 현재 CPU 버전 제거
pip uninstall llama-cpp-python -y

# GPU 버전 빌드 및 설치
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --no-cache-dir
```

### 4단계: config.py 설정 변경
```python
# GPU 설정 활성화
N_GPU_LAYERS = -1  # 모든 레이어 GPU 사용 (현재: 0)
N_THREADS = 8      # GPU 사용시 CPU 스레드 줄이기 (현재: 20)
```

## 🎯 대안 방법들

### Option A: Docker 사용
```bash
# NVIDIA Docker 설치
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# CUDA 환경이 준비된 컨테이너 실행
docker run --gpus all -it nvidia/cuda:12.8-devel-ubuntu22.04
```

### Option B: Conda 환경 사용
```bash
# Miniconda 설치
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh

# CUDA 환경 생성
conda create -n gpu-env python=3.10
conda activate gpu-env
conda install cudatoolkit=12.8 -c conda-forge
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

### Option C: 사전 컴파일된 바이너리 사용
```bash
# 특정 CUDA 버전용 휠 다운로드
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

## 📊 성능 비교 예상

| 설정 | 추론 속도 | 메모리 사용 | 안정성 |
|------|---------|------------|--------|
| **현재 (CPU 최적화)** | 1-3초 | RAM 3-4GB | ⭐⭐⭐ |
| **GPU (RTX PRO 4000)** | 0.3-0.8초 | VRAM 7-8GB | ⭐⭐ |

## 🚀 권장사항

### 즉시 사용하려면
- **현재 CPU 최적화 버전 사용** (이미 매우 좋은 성능)
- 24코어로 충분히 실용적

### GPU가 꼭 필요하면  
1. **Option B (Conda)** 시도
2. **Option A (Docker)** 시도  
3. **수동 설치** (위험부담 있음)

## ⚡ 현재 CPU 최적화 상태

```python
# 현재 최적화된 설정 (config.py)
N_THREADS = 20        # 24코어 중 20개 활용
N_CTX = 4096         # 적정 컨텍스트
N_BATCH = 512        # 효율적 배치 크기
USE_MLOCK = True     # 메모리 고정으로 성능 향상
USE_MMAP = True      # 메모리 매핑으로 효율성 증대
```

**결론**: 현재 CPU 버전으로도 충분히 실용적입니다. GPU는 나중에 여유가 있을 때 천천히 업그레이드하는 것을 권장합니다.

---

**작성일**: 2025-09-10  
**대상 GPU**: NVIDIA RTX PRO 4000 (16GB)  
**현재 CPU**: Intel Ultra 9 285HX (24코어, 최적화 완료)