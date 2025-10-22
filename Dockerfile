# AI-CHAT Docker Image
# Python 3.12 기반 이미지
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필수 패키지 설치
# - tesseract-ocr: OCR 처리용
# - poppler-utils: PDF 처리용
# - build-essential: Python 패키지 빌드용
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사
COPY requirements.txt .

# Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# .env 파일을 .env.production에서 복사 (없으면 건너뜀)
RUN if [ -f .env.production ]; then cp .env.production .env; fi

# 포트 노출
EXPOSE 8501

# Streamlit 서버 실행
CMD ["streamlit", "run", "web_interface.py", "--server.port=8501", "--server.address=0.0.0.0"]
