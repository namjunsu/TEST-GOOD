# 🚀 다른 PC로 옮기는 방법 (초간단)

## 📋 딱 이것만 보세요!

---

## 🎯 현재 PC에서 할 일 (5분)

### 1단계: 백업 만들기
```bash
cd /home/wnstn4647/AI-CHAT
./QUICK_MIGRATION.sh
```

**끝!** 파일이 만들어집니다: `AI-CHAT_backup_20251013_1430.tar.gz`

### 2단계: USB로 복사
```bash
# D: 드라이브인 경우
cp /home/wnstn4647/AI-CHAT_backup_*.tar.gz /mnt/d/

# 또는 E: 드라이브
cp /home/wnstn4647/AI-CHAT_backup_*.tar.gz /mnt/e/
```

**✅ 현재 PC 끝!**

---

## 🆕 새 PC에서 할 일 (10분)

### 1단계: USB에서 복사
```bash
cd ~
cp /mnt/d/AI-CHAT_backup_*.tar.gz .
```

### 2단계: 압축 풀기
```bash
tar -xzf AI-CHAT_backup_*.tar.gz
cd AI-CHAT
```

### 3단계: 자동 설치 (이게 다 알아서 해줌!)
```bash
bash SETUP_NEW_PC.sh
```

이 스크립트가 **자동으로**:
- ✅ Python 확인하고 설치 방법 알려줌
- ✅ 필요한 프로그램 17개 전부 설치
- ✅ 문제 있으면 해결 방법 알려줌
- ✅ 테스트까지 자동으로

### 4단계: 실행
```bash
source .venv/bin/activate
streamlit run web_interface.py
```

**✅ 끝!** 브라우저 접속:
- **이 PC**: `http://localhost:8501`
- **다른 PC**: `http://[이PC의IP]:8501`

💡 IP 주소 확인: `hostname -I`
📱 네트워크 접속 방법: [네트워크_접속_가이드.md](네트워크_접속_가이드.md)

---

## 🆘 문제 생기면?

**[문제해결.md](문제해결.md)** 파일 보기

---

## 📞 요약

1. **현재 PC**: `./QUICK_MIGRATION.sh` 실행 → USB 복사
2. **새 PC**: USB 복사 → `bash SETUP_NEW_PC.sh` 실행
3. **실행**: `streamlit run web_interface.py`

**끝!** 🎉
