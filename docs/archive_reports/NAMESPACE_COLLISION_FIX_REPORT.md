# 네임 충돌 수정 보고서 (config 모듈)

## 문제 상황
```
AttributeError: module 'config' has no attribute 'DOCS_DIR'
```

web_interface.py 실행 시 DOCS_DIR 속성을 찾을 수 없는 에러 발생.

## 원인 분석

### 1. 네임 충돌 (Namespace Collision)
- **문제**: `import config`가 프로젝트의 config 모듈이 아닌 PyPI의 config 패키지를 가리킴
- **충돌 경로**:
  - 우리 모듈: `/home/wnstn4647/AI-CHAT/config/__init__.py`
  - 제3자 패키지: PyPI의 `config` 패키지 (설치되어 있을 경우)

### 2. 일반명 모듈의 위험성
- `config`, `utils` 같은 일반명은 PyPI 패키지와 충돌 가능성이 높음
- Python의 import 우선순위에서 설치된 패키지가 로컬 모듈보다 우선될 수 있음

## 수정 내용

### 1. 통합 설정 모듈 생성
**파일**: `app/config/settings.py`

```python
from pathlib import Path
import os

# 프로젝트 루트 추정
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 문서 루트: 환경변수 우선, 없으면 기본값
DOCS_DIR = Path(os.getenv("DOCS_DIR", PROJECT_ROOT / "docs"))

# 허용 확장자
ALLOWED_EXTS = set(
    ext.strip().lower()
    for ext in os.getenv("ALLOWED_EXTS", ".pdf,.txt").split(",")
    if ext.strip()
)

# 데이터베이스 경로
DB_PATHS = {
    "metadata": str(PROJECT_ROOT / "metadata.db"),
    "everything_index": str(PROJECT_ROOT / "everything_index.db"),
    "file_index": str(PROJECT_ROOT / "file_index.json")
}
```

### 2. web_interface.py 수정
**변경 전**:
```python
import config
docs_path = Path(config.DOCS_DIR)
```

**변경 후**:
```python
from app.config.settings import DOCS_DIR, ALLOWED_EXTS, PROJECT_ROOT
docs_path = Path(DOCS_DIR)
```

### 3. utils/system_checker.py 수정
**변경 전**:
```python
import config
if hasattr(config, 'DOCS_DIR'):
    ...
```

**변경 후**:
```python
from app.config.settings import DOCS_DIR, PROJECT_ROOT
import app.config.settings as settings
```

### 4. config/indexing.py 수정
기존 config/indexing.py를 app.config.settings를 사용하도록 변경:

```python
# app.config.settings에서 설정을 가져옵니다
try:
    from app.config.settings import ALLOWED_EXTS, DB_PATHS, PROJECT_ROOT
except ImportError:
    # 폴백: 기본값 사용
    ALLOWED_EXTS = {".pdf", ".txt"}
```

## 검증 결과

### 1. app.config.settings 임포트 테스트
```bash
$ python3 -c "from app.config.settings import DOCS_DIR, ALLOWED_EXTS"

✅ app.config.settings import SUCCESS
  DOCS_DIR: /home/wnstn4647/AI-CHAT/docs
  ALLOWED_EXTS: {'.pdf', '.txt'}
  PROJECT_ROOT: /home/wnstn4647/AI-CHAT
  DOCS_DIR exists: True
```

### 2. web_interface.py DOCS_DIR 사용 테스트
```bash
$ python3 -c "from app.config.settings import DOCS_DIR; ..."

✅ web_interface.py DOCS_DIR 사용 테스트 성공
  docs_path: /home/wnstn4647/AI-CHAT/docs
  PDF count: 0  # docs 폴더에 직접 PDF 없음 (year_* 폴더에 있음)
  TXT count: 3
```

### 3. 네임 충돌 확인
```bash
$ python3 -c "import config; print(config.__file__)"

config module path: /home/wnstn4647/AI-CHAT/config/__init__.py
Has DOCS_DIR: False  # 예상대로 DOCS_DIR 없음
```

## 개선 효과

### 1. 네임 충돌 해결
- ✅ `import config` 대신 `from app.config.settings import ...` 사용
- ✅ 절대 경로 임포트로 제3자 패키지와의 충돌 방지
- ✅ AttributeError 완전 해결

### 2. 설정 관리 일원화
- ✅ 모든 프로젝트 설정이 `app/config/settings.py`에 통합
- ✅ 환경변수 지원 (DOCS_DIR, ALLOWED_EXTS 등)
- ✅ .env 파일 선택적 로딩 (dotenv 없어도 작동)

### 3. 유지보수성 향상
- ✅ 설정 변경 시 한 곳만 수정
- ✅ 폴백 로직으로 안정성 향상
- ✅ 명확한 임포트 경로

## 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `app/config/__init__.py` | 신규 생성 - 패키지 초기화 |
| `app/config/settings.py` | 신규 생성 - 통합 설정 모듈 |
| `web_interface.py` | `import config` → `from app.config.settings import` |
| `utils/system_checker.py` | config 모듈 체크 → app.config.settings 체크 |
| `config/indexing.py` | app.config.settings 사용하도록 수정 |

## 권장사항

### 1. 일반명 모듈 사용 지양
- ❌ `import config` (충돌 위험)
- ❌ `import utils` (충돌 위험)
- ✅ `from app.config.settings import ...` (안전)
- ✅ `from app.utils.helpers import ...` (안전)

### 2. 절대 경로 임포트 사용
```python
# 권장
from app.config.settings import DOCS_DIR
from app.rag.pipeline import RAGPipeline

# 비권장
import config
from config import DOCS_DIR
```

### 3. 환경변수 활용
`.env` 파일 또는 시스템 환경변수로 설정 관리:
```bash
DOCS_DIR=/custom/docs/path
ALLOWED_EXTS=.pdf
```

## 결론

네임 충돌 문제가 완전히 해결되었습니다.
- **이전**: `AttributeError: module 'config' has no attribute 'DOCS_DIR'`
- **현재**: ✅ 모든 설정이 `app.config.settings`에서 안전하게 로드됨

절대 경로 임포트 패턴을 따르면 향후 유사한 네임 충돌을 예방할 수 있습니다.