# AI-CHAT 보안 정책 및 접근 제어 가이드

> 시스템 보안, 인증, 권한 관리 정책

---

## 목차

1. [현재 보안 상태](#현재-보안-상태)
2. [API 인증 설정](#api-인증-설정)
3. [Streamlit 비밀번호 보호](#streamlit-비밀번호-보호)
4. [DB 접근 제어](#db-접근-제어)
5. [네트워크 보안](#네트워크-보안)
6. [민감 정보 관리](#민감-정보-관리)
7. [보안 체크리스트](#보안-체크리스트)

---

## 현재 보안 상태

### 가정 환경
- **배포 환경**: 내부망 (VPN 또는 사내 네트워크)
- **외부 노출**: 없음 (로컬 localhost:8501, localhost:7860)
- **API 인증**: **없음** ⚠️
- **Streamlit 비밀번호**: **없음** ⚠️
- **DB 암호화**: 없음 (SQLite 평문)

### 보안 등급
| 항목 | 상태 | 권장 |
|------|------|------|
| API 인증 | ❌ 없음 | ✅ JWT 또는 API Key |
| 웹 인증 | ❌ 없음 | ✅ 비밀번호 또는 SSO |
| DB 암호화 | ❌ 없음 | ⚠️ 민감 데이터만 암호화 |
| HTTPS | ❌ HTTP | ✅ HTTPS (Nginx + Let's Encrypt) |
| 방화벽 | ⚠️ OS 방화벽 | ✅ UFW 또는 iptables |

---

## API 인증 설정

### 1. API Key 인증 (간단)

**장점**: 구현 쉬움, 빠른 적용
**단점**: 키 공유 시 보안 취약

#### 구현 방법

**1) `.env` 파일에 API Key 추가**

```bash
API_KEY=your-secret-api-key-here-change-this
```

**2) FastAPI 미들웨어 추가**

`app/api/main.py` 수정:

```python
from fastapi import FastAPI, Header, HTTPException, Depends
import os

app = FastAPI()

API_KEY = os.getenv("API_KEY", "")

async def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True

@app.post("/api/search")
async def search(query: str, authenticated: bool = Depends(verify_api_key)):
    # 기존 로직
    ...
```

**3) 클라이언트 사용 예시**

```bash
curl -X POST http://localhost:7860/api/search \
  -H "X-API-Key: your-secret-api-key-here-change-this" \
  -H "Content-Type: application/json" \
  -d '{"query": "DVR 구매"}'
```

---

### 2. JWT 인증 (권장)

**장점**: 만료 시간 설정, 사용자별 권한 관리
**단점**: 구현 복잡도 높음

#### 필요 패키지

```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

#### 구현 예시

```python
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-256-bit-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

security = HTTPBearer()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/search")
async def search(query: str, username: str = Depends(verify_token)):
    # 기존 로직
    ...
```

---

## Streamlit 비밀번호 보호

### 방법 1: 간단한 비밀번호 (빠른 적용)

`web_interface.py` 수정:

```python
import streamlit as st
import os

def check_password():
    """간단한 비밀번호 확인"""

    def password_entered():
        if st.session_state["password"] == os.getenv("WEB_PASSWORD", "admin"):
            st.session_state["authenticated"] = True
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("비밀번호", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["authenticated"]:
        st.text_input("비밀번호", type="password", on_change=password_entered, key="password")
        st.error("비밀번호가 틀렸습니다")
        return False
    else:
        return True

# 메인 코드 앞에 추가
if not check_password():
    st.stop()

# 기존 Streamlit 코드
st.title("AI-CHAT 문서 검색")
...
```

`.env` 파일에 추가:

```bash
WEB_PASSWORD=your-secure-password-here
```

---

### 방법 2: 여러 사용자 지원

```python
import hashlib

USERS = {
    "admin": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",  # "admin" 해시
    "user1": "0a041b9462caa4a31bac3567e0b6e6fd9100787db2ab433d96f6d178cabfce90",  # "password123" 해시
}

def verify_user(username, password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return username in USERS and USERS[username] == hashed
```

---

## DB 접근 제어

### 1. 파일 권한 설정

```bash
# DB 파일을 소유자만 읽기/쓰기
chmod 600 metadata.db

# 그룹은 읽기만 가능
chmod 640 metadata.db
chown wnstn4647:ai-chat-users metadata.db
```

### 2. SQLite 암호화 (민감 데이터)

**옵션 A: SQLCipher 사용**

```bash
pip install pysqlcipher3
```

```python
from pysqlcipher3 import dbapi2 as sqlite3

conn = sqlite3.connect("metadata.db")
conn.execute("PRAGMA key='your-encryption-key'")
```

**옵션 B: 특정 컬럼만 암호화**

```python
from cryptography.fernet import Fernet

# .env에 ENCRYPTION_KEY 저장
KEY = os.getenv("ENCRYPTION_KEY")
cipher = Fernet(KEY)

def encrypt_field(text: str) -> str:
    return cipher.encrypt(text.encode()).decode()

def decrypt_field(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()
```

---

## 네트워크 보안

### 1. 방화벽 설정 (UFW)

```bash
# UFW 설치 및 활성화
sudo apt-get install ufw
sudo ufw enable

# SSH 허용 (원격 접속용)
sudo ufw allow ssh

# Streamlit (내부망에서만)
sudo ufw allow from 192.168.0.0/16 to any port 8501

# API (내부망에서만)
sudo ufw allow from 192.168.0.0/16 to any port 7860

# 외부 접속 차단 (기본)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 상태 확인
sudo ufw status
```

---

### 2. Nginx 리버스 프록시 + HTTPS

**장점**: HTTPS 암호화, 로그 관리, 로드 밸런싱

#### 설정 파일 (`/etc/nginx/sites-available/ai-chat`)

```nginx
server {
    listen 443 ssl;
    server_name ai-chat.company.local;

    ssl_certificate /etc/ssl/certs/ai-chat.crt;
    ssl_certificate_key /etc/ssl/private/ai-chat.key;

    # Streamlit
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # API
    location /api/ {
        proxy_pass http://localhost:7860/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # IP 화이트리스트
    allow 192.168.0.0/16;
    deny all;
}
```

---

## 민감 정보 관리

### 1. `.env` 파일 보호

```bash
# 권한 설정 (소유자만 읽기)
chmod 600 .env

# .gitignore 확인
echo ".env" >> .gitignore
```

### 2. 비밀번호 해싱 (절대 평문 저장 금지)

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 해시 생성
hashed = pwd_context.hash("user_password")

# 검증
pwd_context.verify("user_password", hashed)
```

### 3. 민감 로그 제외

`app/core/logging.py` 수정:

```python
import re

def sanitize_log(message: str) -> str:
    # 비밀번호 마스킹
    message = re.sub(r'password["\']?\s*[:=]\s*["\']?([^"\'}\s]+)', 'password=***', message, flags=re.IGNORECASE)
    # API Key 마스킹
    message = re.sub(r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'}\s]+)', 'api_key=***', message, flags=re.IGNORECASE)
    return message
```

---

## 보안 체크리스트

### 배포 전 필수 항목

- [ ] `.env` 파일 권한 설정 (`chmod 600`)
- [ ] API 인증 활성화 (API Key 또는 JWT)
- [ ] Streamlit 비밀번호 설정
- [ ] 방화벽 설정 (UFW 또는 iptables)
- [ ] HTTPS 설정 (Nginx + SSL)
- [ ] DB 파일 권한 설정 (`chmod 640`)
- [ ] 민감 정보 로그 마스킹
- [ ] `.gitignore`에 `.env` 추가 확인
- [ ] 기본 비밀번호 변경 (admin/password 등)
- [ ] 불필요한 포트 닫기

### 주기적 점검 (월 1회)

- [ ] 로그 파일 검토 (이상 접근 시도)
- [ ] 사용자 권한 검토
- [ ] 패키지 보안 업데이트 (`pip list --outdated`)
- [ ] SSL 인증서 만료일 확인
- [ ] 백업 파일 접근 권한 확인

---

## 침해 사고 대응

### 1. 즉시 조치

```bash
# 1. 서버 중단
pkill -f streamlit
pkill -f uvicorn

# 2. 방화벽 모든 연결 차단
sudo ufw --force enable
sudo ufw default deny incoming

# 3. 로그 백업
cp -r logs/ logs_incident_$(date +%Y%m%d_%H%M%S)/
```

### 2. 원인 분석

```bash
# 접속 로그 확인
tail -1000 logs/app.log | grep -E "(401|403|500)"

# 네트워크 연결 확인
sudo netstat -tulnp | grep -E "(8501|7860)"

# 최근 로그인 기록
last | head -20
```

### 3. 복구 절차

1. 원인 파악 및 제거
2. 비밀번호 전체 변경
3. 백업에서 데이터 검증 후 복원
4. 보안 패치 적용
5. 재시작 및 모니터링

---

## 참고 자료

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- Streamlit Authentication: https://blog.streamlit.io/streamlit-authenticator/
- SQLite Security: https://www.sqlite.org/security.html

---

**마지막 업데이트**: 2025-11-25
**보안 등급**: ⚠️ 내부망 환경 (외부 노출 시 추가 조치 필요)
