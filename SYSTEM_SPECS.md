# 시스템 사양 비교 및 프로젝트 환경 설정 가이드

## 📊 현재 PC 사양 (2025-09-10 기준)

### 하드웨어
- **CPU**: Intel(R) Core(TM) Ultra 9 285HX (24 cores, 24 threads)
  - 최신 Intel Ultra 시리즈 프로세서
  - 고성능 멀티코어 처리 가능
- **RAM**: 7.5GB (WSL2 할당)
  - 실제 사용 가능: 5.6GB
  - 현재 사용 중: 1.7GB
- **Storage**: 1TB (946GB 사용 가능)
  - 현재 사용: 11GB (2%)
- **GPU**: 없음 (WSL2 환경에서 감지 안됨)

### 소프트웨어 환경
- **OS**: Windows 11 Pro (10.0.26100)
- **WSL2**: Ubuntu 22.04.5 LTS
- **Kernel**: 6.6.87.2-microsoft-standard-WSL2
- **Python**: 3.10.12
- **pip**: 22.0.2 (설치됨)

## 🆚 이전 PC와 비교 (CLAUDE.md 기록 기준)

### 이전 PC (기록상)
- **경로**: `/home/userwnstn4647/AI-CHAT-V3/`
- **Python**: 3.12.3
- **모델 크기**: 5.7GB (Qwen2.5-7B)

### 현재 PC
- **경로**: `/home/wnstn4647/AI-CHAT/`
- **Python**: 3.10.12 (다운그레이드됨)
- **모델 크기**: 4.4GB (정리 완료)

## ⚠️ 주요 차이점 및 영향

### 1. **Python 버전 차이**
- 이전: Python 3.12.3
- 현재: Python 3.10.12
- **영향**: 일부 최신 기능 사용 불가, 하지만 대부분 호환 가능

### 2. **메모리 제한**
- WSL2에 7.5GB만 할당 (Windows 호스트의 일부)
- **권장사항**: WSL2 메모리 할당 증가 필요
  ```powershell
  # .wslconfig 파일 수정 (Windows 호스트)
  [wsl2]
  memory=16GB  # 시스템 RAM에 따라 조정
  ```

### 3. **CPU 성능**
- **장점**: Intel Ultra 9 285HX는 최신 고성능 프로세서
- 24코어로 병렬 처리 우수
- LLM 추론에 유리

## 🔧 현재 환경 설정 상태

### ✅ 완료된 작업
1. Qwen2.5 모델 파일 정리 (models/ 디렉토리로 이동)
2. 중복 파일 제거 (core/, Zone.Identifier 파일들)
3. pip 설치 확인됨

### ❌ 필요한 작업
1. Python 패키지 설치
2. 가상환경 생성
3. 모델 경로 확인 및 수정

## 📦 패키지 설치 가이드

### 1. 가상환경 생성 (권장)
```bash
python3 -m venv ai-chat-env
source ai-chat-env/bin/activate
```

### 2. pip 업그레이드
```bash
pip install --upgrade pip setuptools wheel
```

### 3. 필수 패키지 설치
```bash
# 기본 패키지들
pip install streamlit pdfplumber PyPDF2
pip install faiss-cpu rank_bm25
pip install sentence-transformers transformers

# LLM 라이브러리 (시간 소요)
pip install llama-cpp-python

# 한국어 처리
pip install konlpy kiwipiepy
```

### 4. 전체 requirements 설치
```bash
pip install -r requirements_updated.txt
```

## 🚀 프로젝트 실행 방법

### 1. 시스템 테스트
```bash
# Python 모듈 확인
python3 -c "import pdfplumber, streamlit, faiss; print('기본 모듈 OK')"

# RAG 시스템 테스트
python3 perfect_rag.py
```

### 2. 웹 인터페이스 실행
```bash
streamlit run web_interface.py
```

## 💡 성능 최적화 팁

### WSL2 메모리 최적화
1. Windows에서 `.wslconfig` 파일 생성/수정
2. 메모리 할당 증가 (최소 16GB 권장)
3. WSL2 재시작: `wsl --shutdown` 후 재실행

### CPU 활용 최적화
- 24코어 활용을 위한 설정:
  ```python
  # config.py에서 수정
  n_threads = 20  # CPU 코어 수 - 4
  ```

### 디스크 I/O 최적화
- 946GB 여유 공간 활용
- 인덱스 파일은 SSD에 저장 권장

## 📌 현재 상태 요약

### ✅ 장점
- 최신 고성능 CPU (Intel Ultra 9)
- 충분한 디스크 공간 (946GB)
- pip 설치됨 (패키지 설치 가능)

### ⚠️ 제약사항
- Python 버전 다운그레이드 (3.12 → 3.10)
- WSL2 메모리 제한 (7.5GB)
- GPU 미지원 (CPU 전용 모드)

### 🎯 다음 단계
1. **즉시**: Python 패키지 설치
2. **선택**: WSL2 메모리 증가
3. **실행**: RAG 시스템 테스트 및 최적화

---

**작성일**: 2025-09-10  
**시스템**: Intel Ultra 9 285HX / WSL2 Ubuntu 22.04  
**프로젝트**: AI-CHAT-V3 한국어 방송장비 RAG 시스템