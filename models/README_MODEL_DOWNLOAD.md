# AI 모델 다운로드 가이드

## 현재 상태
더미 파일이 설치되어 시스템 검증은 통과하지만, **실제 AI 기능을 사용하려면 모델 파일을 다운로드해야 합니다**.

## 필요한 모델
- **모델명**: Qwen2.5-7B-Instruct (GGUF 형식, Q4_K_M 양자화)
- **파일명**: `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf`
- **예상 크기**: ~4-7GB
- **용도**: AI 답변 생성, 문서 분석

## 다운로드 방법

### 방법 1: Hugging Face에서 직접 다운로드
```bash
# Hugging Face CLI 설치 (없는 경우)
pip install huggingface-hub

# 모델 다운로드
huggingface-cli download \
  Qwen/Qwen2.5-7B-Instruct-GGUF \
  qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
  --local-dir models/ \
  --local-dir-use-symlinks False
```

### 방법 2: wget으로 직접 다운로드
```bash
# URL 확인 후 다운로드 (예시)
cd models/
wget [Hugging Face 모델 URL]
```

### 방법 3: 브라우저로 다운로드
1. https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF 방문
2. `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` 파일 다운로드
3. `models/` 디렉토리에 저장

## 다운로드 후
```bash
# 파일 확인
ls -lh models/*.gguf

# 시스템 재시작
./start_ai_chat.sh
```

## 대안: 모델 없이 사용
- 문서 검색 기능은 모델 없이도 작동
- AI 답변 생성 시 적절한 에러 메시지 표시
- 임베딩 모델 (ko-sroberta)은 별도로 자동 다운로드됨

## 참고
- 모델 파일은 최초 1회만 다운로드하면 됨
- 디스크 공간 확인: 최소 10GB 여유 권장
- GPU 메모리: RTX 4000 (16GB)로 충분
