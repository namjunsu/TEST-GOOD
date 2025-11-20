# 폴더 구조 정리 계획

**작성일**: 2025-11-19
**목적**: 헷갈리는 중복/백업 폴더 정리

---

## 🎯 정리 원칙

1. **안전 우선**: 삭제 전 백업
2. **점진적 정리**: 한 번에 하나씩
3. **문서화**: 무엇을 왜 지웠는지 기록

---

## 📊 현재 문제점

### 1. 중복 백업 폴더/파일 (여러 곳에 분산)
```
./backups/               - 명시적 백업 폴더
./backup/                - 또 다른 백업 폴더
./archive/               - 아카이브 (3개 하위 폴더)
./var/index_backup_*/    - 인덱스 백업 (여러 개)
./var_backup_*.tar.gz    - var 전체 백업
*.backup, *.bak 파일들   - 개별 파일 백업
```
→ **너무 많은 백업 장소**, 어디가 최신인지 모름

### 2. docs 폴더 중복
```
docs/incoming/      - 새 문서 임시 저장?
docs/processed/     - 처리된 문서?
docs/year_YYYY/     - 연도별 문서 (정식)
docs/quarantine/    - 격리?
docs/rejected/      - 거부?
docs/broken_pdfs/   - 손상된 PDF
```
→ **같은 PDF가 여러 곳에** 있을 가능성

### 3. modules vs modules_legacy
```
modules/         - 비어있음 (0개)
modules_legacy/  - 9개 파일
```
→ **빈 폴더 vs 레거시**, modules는 왜 있나?

### 4. 61개 스크립트
→ 사용 안 하는 스크립트 많을 듯

### 5. rag_system 하위 폴더
```
rag_system/active/   - 현재 사용 중
rag_system/db/       - 뭐가 있나?
rag_system/cache/    - 캐시?
rag_system/logs/     - 로그 (var/에도 있음)
```

---

## 🗑️ 정리 대상 (안전하게 삭제 가능)

### Phase 1: 명백한 백업/임시 파일 (즉시 삭제 OK)

#### 1-1. 오래된 백업 파일
```bash
# var 폴더 백업 (이미 재생성됨)
./var_backup_20251119_090739.tar.gz  # 오늘 만든 백업

# 오래된 index 백업들
./var/index_backup_1763516459/
./var/index_backup_1763515940/
→ 최신 인덱스만 유지, 나머지 삭제

# 오래된 metadata 백업
./backups/metadata_backup_20251110_*.db  # 9일 전
./metadata.db.backup_20251031_131423      # 19일 전
./metadata.db.bak
→ 최신 1개만 유지
```

#### 1-2. .bak / .backup 파일
```bash
./config/*.bak                              # 설정 파일 백업
./modules_legacy/metadata_extractor.py.backup
./start_ai_chat.sh.backup_20251113_092657
→ 원본이 있으면 삭제
```

#### 1-3. 빈 폴더
```bash
./modules/  # 비어있음
→ 삭제
```

---

### Phase 2: 신중한 검토 필요

#### 2-1. docs 폴더 중복 해결
```bash
# 방침 결정 필요
docs/incoming/   - 삭제? 또는 year_YYYY로 이동?
docs/processed/  - 삭제? 또는 year_YYYY로 이동?
docs/quarantine/ - 격리 정책 확인 후 결정
docs/rejected/   - 왜 거부됐나 확인 후 삭제
docs/broken_pdfs/- 수리 불가능하면 삭제
```

**추천 방침**:
- year_YYYY/ 폴더만 "정식 문서"로 취급
- incoming/processed는 중복이면 삭제
- quarantine/rejected는 로그 확인 후 판단

#### 2-2. archive 폴더
```bash
./archive/20251113_experiments/   # 실험 코드
./archive/scripts_backup_20251112/ # 스크립트 백업
./archive/root_backup_20251112/    # 루트 백업
./archive/components_backup_20251112/
```

**추천**:
- 실험 성공했으면 삭제
- 백업은 1주일 지나면 삭제

#### 2-3. 스크립트 정리 (61개)
```bash
# 사용 중: reindex_atomic.py, sync_db_text_preview.py 등
# 미사용: 확인 필요

# 정리 방법
scripts/active/     - 현재 사용 중
scripts/archive/    - 더 이상 안 씀
```

---

## ✅ 정리 후 목표 구조

### 최종 폴더 구조
```
AI-CHAT/
├── app/              # 핵심 코드
├── scripts/          # 운영 스크립트만 (10-15개)
│   └── archive/      # 안 쓰는 스크립트
├── docs/
│   ├── year_YYYY/    # 정식 문서 (유일한 원천)
│   ├── dev/          # 개발 문서
│   └── xray/         # 분석 리포트
├── data/
│   └── extracted/    # txt 파일
├── var/              # 런타임 (gitignore)
│   ├── index/        # 현재 인덱스만
│   └── cache/        # 캐시
├── backups/          # 백업 (최신 1주일만)
├── archive/          # 오래된 코드 (1개월 이상)
├── tests/            # 테스트
└── rag_system/
    └── active/       # 현재 사용 중인 모듈만
```

### 삭제할 것
```
❌ modules/ (빈 폴더)
❌ modules_legacy/ (archive로 이동)
❌ backup/ (backups로 통합)
❌ docs/incoming/, docs/processed/ (중복 확인 후)
❌ var/index_backup_*/ (오래된 것)
❌ *.bak, *.backup 파일들
❌ 9일 이상 된 백업들
```

---

## 🚀 실행 계획

### Step 1: 안전 백업 (전체)
```bash
# 정리 전 스냅샷
tar -czf cleanup_before_$(date +%Y%m%d_%H%M%S).tar.gz \
  backups/ backup/ archive/ var/index_backup_*/ modules/ modules_legacy/ \
  --exclude='*.pyc' --exclude='__pycache__'
```

### Step 2: Phase 1 실행 (안전한 것부터)
```bash
# 1. 빈 폴더
rm -rf modules/

# 2. 오래된 백업
rm -rf var/index_backup_*/
rm -f backups/metadata_backup_20251110_*.db
rm -f metadata.db.backup_20251031_131423
rm -f metadata.db.bak

# 3. .bak 파일 (원본 확인 후)
rm -f config/*.bak
rm -f start_ai_chat.sh.backup_*
```

### Step 3: Phase 2 실행 (검토 필요)
```bash
# docs 중복 확인
python scripts/check_docs_duplicates.py

# 결과 보고 판단
# - incoming/processed 중복이면 삭제
# - quarantine/rejected 검토 후 삭제
```

### Step 4: 검증
```bash
# 시스템 정상 동작 확인
python scripts/reindex_atomic.py  # 재인덱싱 성공?
streamlit run web_interface.py    # 웹 UI 정상?
```

---

## 📊 예상 효과

### 디스크 공간
```
현재: 약 1-2GB (추정)
정리 후: 약 500MB-1GB
절감: 500MB-1GB
```

### 혼란도
```
현재: 😵 "어디에 뭐가 있지?"
정리 후: 😊 "docs/year_YYYY가 정식이구나"
```

### 유지보수성
```
현재: 백업이 여러 곳, 어느 게 최신?
정리 후: backups/ 폴더 하나만 확인
```

---

## ⚠️ 주의사항

1. **절대 삭제 금지**
   - docs/year_YYYY/ (정식 문서)
   - metadata.db (현재 DB)
   - var/index/bm25_index.pkl (현재 인덱스)
   - app/ (핵심 코드)

2. **삭제 전 확인**
   - git status (추적 중인 파일?)
   - 최근 수정일 (최근 사용?)
   - 크기 (너무 크면 별도 백업)

3. **점진적 삭제**
   - 한 번에 다 지우지 말기
   - 단계별로 검증하면서 진행

---

## 📝 다음 단계

1. ✅ metadata.db 동기화 (완료)
2. ⏳ 정리 계획 검토 (현재)
3. ⏳ Phase 1 실행 (안전한 것)
4. ⏳ Phase 2 실행 (검토 필요)
5. ⏳ 최종 검증

---

**작성자**: Claude Code
**승인 필요**: 사용자 확인 후 진행
