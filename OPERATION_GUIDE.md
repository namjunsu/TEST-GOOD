# 📚 AI-CHAT RAG 시스템 운영 가이드

## 🚀 시스템 시작 (누구나 가능)

### 1️⃣ 시스템 시작 명령어 (한 줄)
```bash
./start_system.sh
```

이 명령어 하나로:
- ✅ 웹 인터페이스 시작
- ✅ 자동 인덱싱 시작
- ✅ OCR 모니터 시작
- ✅ 성능 최적화 적용

## 📁 문서 추가 방법

### 새 문서 추가 시:
1. **PDF 파일을 넣을 위치**:
   ```
   docs/year_2025/새문서.pdf  (2025년 문서)
   docs/year_2024/새문서.pdf  (2024년 문서)
   ```

2. **자동으로 일어나는 일**:
   - 60초 내 자동 감지
   - 텍스트 추출 시도
   - 스캔 PDF면 OCR 자동 처리
   - 메타데이터 자동 추출
   - 검색 인덱스 자동 업데이트

## 🖥️ 일반 사용자 가이드

### 웹 인터페이스 접속:
```
http://localhost:8501
```

### 검색 방법:
1. **일반 검색**: "2020년 구매 문서"
2. **기안자 검색**: "유인혁이 작성한 문서"
3. **금액 검색**: "100만원 이상 구매건"
4. **날짜 검색**: "2024년 7월 문서"

## 🔧 관리자 가이드

### 시스템 상태 확인:
```bash
./check_status.sh
```

### 로그 확인:
```bash
# 시스템 로그
tail -f logs/system.log

# OCR 처리 로그
tail -f logs/ocr_process.log

# 웹 인터페이스 로그
tail -f logs/web_interface.log
```

### 문제 해결:

#### 1. 시스템이 느려진 경우:
```bash
./restart_system.sh
```

#### 2. 문서가 검색되지 않는 경우:
```bash
python3 build_metadata_db.py --batch-size 100
```

#### 3. OCR이 작동하지 않는 경우:
```bash
python3 run_full_ocr.py
```

## 📊 시스템 구성

### 핵심 컴포넌트:
1. **웹 인터페이스** (`web_interface.py`)
   - 사용자 인터페이스
   - 검색 및 답변 생성

2. **RAG 엔진** (`perfect_rag.py`)
   - 문서 검색
   - AI 답변 생성

3. **자동 인덱싱** (`auto_indexer.py`)
   - 새 문서 자동 감지
   - 인덱스 자동 업데이트

4. **OCR 처리** (`auto_ocr_monitor.py`)
   - 스캔 PDF 자동 처리
   - 텍스트 추출

5. **메타데이터 관리** (`metadata_manager.py`)
   - 문서 정보 관리
   - 캐싱 및 최적화

## 🔄 자동화된 프로세스

### 매일 자동 실행:
- ✅ 새 문서 인덱싱 (60초마다)
- ✅ 스캔 PDF OCR 처리 (자동)
- ✅ 캐시 정리 (매일 새벽 3시)
- ✅ 로그 순환 (7일 보관)

## 📈 성능 모니터링

### 대시보드 확인:
```
http://localhost:8501
→ 사이드바 → 시스템 상태
```

표시되는 정보:
- 총 문서 수
- 처리된 문서
- 캐시 히트율
- 평균 응답 시간

## 🚨 알림 설정

### 이메일 알림 (선택사항):
```bash
# 설정 파일 수정
nano config/alerts.yaml
```

알림 조건:
- 새 문서 100개 이상 추가
- OCR 실패율 10% 초과
- 시스템 오류 발생

## 💾 백업

### 자동 백업 설정:
```bash
./setup_autostart.sh  # 매주 일요일 새벽 3시 자동 백업 설정
```

### 수동 백업:
```bash
./backup_system.sh
```

백업 내용:
- 문서 메타데이터
- 검색 인덱스
- 시스템 설정
- 처리 로그

### 복원 방법:
```bash
./restore_backup.sh backups/백업파일.tar.gz
```

## 📞 문제 발생 시

### 1. 자가 진단:
```bash
python3 system_health_check.py
```

### 2. 자동 복구:
```bash
./auto_repair.sh
```

### 3. 전체 재구축:
```bash
./rebuild_all.sh
```

## 🎯 핵심 원칙

1. **Zero-Touch Operation**: 관리자 개입 최소화
2. **Self-Healing**: 자동 오류 복구
3. **Auto-Scaling**: 부하에 따른 자동 조정
4. **Continuous Learning**: 사용할수록 똑똑해짐

---

## 📌 Quick Reference

| 작업 | 명령어 |
|------|--------|
| 시작 | `./start_system.sh` |
| 중지 | `./stop_system.sh` |
| 재시작 | `./restart_system.sh` |
| 상태 확인 | `./check_status.sh` |
| 로그 확인 | `tail -f logs/system.log` |
| 문서 추가 | docs/year_YYYY/ 폴더에 복사 |
| 백업 | `./backup_system.sh` |

---

*최종 업데이트: 2025-01-22*
*버전: 1.0*