# Systemd Service 배포 가이드

## 설치 방법

### 1. 사용자 및 디렉토리 설정

```bash
# AI-CHAT 전용 사용자 생성
sudo useradd -r -s /bin/bash -d /opt/ai-chat ai-chat

# 프로젝트 배포
sudo cp -r /path/to/AI-CHAT /opt/ai-chat
sudo chown -R ai-chat:ai-chat /opt/ai-chat

# .env 파일 권한 설정 (보안)
sudo chmod 600 /opt/ai-chat/.env
```

### 2. Service 파일 설치

```bash
# Service 파일 복사
sudo cp deploy/systemd/ai-chat-backend.service /etc/systemd/system/
sudo cp deploy/systemd/ai-chat-ui.service /etc/systemd/system/

# systemd 리로드
sudo systemctl daemon-reload
```

### 3. 서비스 시작 및 활성화

```bash
# 서비스 시작
sudo systemctl start ai-chat-backend.service
sudo systemctl start ai-chat-ui.service

# 부팅 시 자동 시작 설정
sudo systemctl enable ai-chat-backend.service
sudo systemctl enable ai-chat-ui.service

# 상태 확인
sudo systemctl status ai-chat-backend.service
sudo systemctl status ai-chat-ui.service
```

## 서비스 관리

### 로그 확인

```bash
# 실시간 로그 보기
sudo journalctl -u ai-chat-backend.service -f
sudo journalctl -u ai-chat-ui.service -f

# 최근 100줄 확인
sudo journalctl -u ai-chat-backend.service -n 100 --no-pager
```

### 재시작

```bash
# 개별 재시작
sudo systemctl restart ai-chat-backend.service
sudo systemctl restart ai-chat-ui.service

# 전체 재시작
sudo systemctl restart ai-chat-backend.service ai-chat-ui.service
```

### 중지/시작

```bash
# 중지
sudo systemctl stop ai-chat-backend.service ai-chat-ui.service

# 시작
sudo systemctl start ai-chat-backend.service ai-chat-ui.service
```

### 부팅 시 자동 시작 해제

```bash
sudo systemctl disable ai-chat-backend.service
sudo systemctl disable ai-chat-ui.service
```

## 트러블슈팅

### 서비스가 시작되지 않을 때

```bash
# 상세 로그 확인
sudo journalctl -u ai-chat-backend.service -xe

# 설정 파일 검증
sudo systemctl show ai-chat-backend.service

# 환경변수 확인
sudo systemctl show ai-chat-backend.service | grep Environment
```

### 권한 문제

```bash
# 디렉토리 권한 확인
ls -la /opt/ai-chat

# 파일 권한 수정
sudo chown -R ai-chat:ai-chat /opt/ai-chat
sudo chmod 600 /opt/ai-chat/.env
```

### GPU 접근 문제

```bash
# ai-chat 사용자를 video 그룹에 추가 (GPU 접근)
sudo usermod -a -G video ai-chat

# 서비스 재시작
sudo systemctl restart ai-chat-backend.service
```

## Nginx 리버스 프록시 설정 (선택)

```nginx
# /etc/nginx/sites-available/ai-chat
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/ssl/certs/your_cert.pem;
    ssl_certificate_key /etc/ssl/private/your_key.pem;

    # TLS 설정
    ssl_protocols TLSv1.3 TLSv1.2;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 보안 헤더
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # 파일 업로드 크기
    client_max_body_size 100M;

    # 타임아웃
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;

    # FastAPI Backend
    location /api/ {
        proxy_pass http://127.0.0.1:7860/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Streamlit UI
    location / {
        proxy_pass http://127.0.0.1:8501/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Nginx 활성화

```bash
# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/ai-chat /etc/nginx/sites-enabled/

# 설정 검증
sudo nginx -t

# Nginx 재시작
sudo systemctl reload nginx
```

## 모니터링

### Health Check

```bash
# Backend API
curl http://127.0.0.1:7860/healthz

# UI (실제 페이지 접속 필요)
curl http://127.0.0.1:8501
```

### 시스템 리소스 모니터링

```bash
# CPU/메모리 사용량
ps aux | grep -E "(uvicorn|streamlit)"

# GPU 사용량
nvidia-smi
```

## 참고

- 로그 파일: `/var/log/ai-chat/` (systemd journal 권장)
- 환경 설정: `/opt/ai-chat/.env`
- 백업 대상: `/opt/ai-chat/{var/index, metadata.db, .env}`
- 문서: [RUNBOOK.md](../../RUNBOOK.md)
