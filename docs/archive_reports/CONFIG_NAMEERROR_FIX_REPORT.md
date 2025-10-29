# config NameError 수정 보고서

## 문제 상황
```
NameError: name 'config' is not defined
Traceback:
  File "/home/wnstn4647/AI-CHAT/web_interface.py", line 390, in main
    render_document_preview(st.session_state.rag, config)
                                                  ^^^^^^
```

web_interface.py에서 `render_document_preview` 함수 호출 시 `config` 변수가 정의되지 않음.

## 원인 분석

### 1. 네임 충돌 수정의 부작용
- 네임 충돌 수정 시 `import config`를 제거
- `from app.config.settings import DOCS_DIR, ...`로 변경
- `config` 변수가 더 이상 존재하지 않음

### 2. 하위 호환성 문제
- `render_document_preview(rag_instance, config)` 함수가 config 모듈 객체를 기대
- `config.DOCS_DIR` 형태로 접근하기 위해 모듈 객체 필요

## 수정 내용

### 1. web_interface.py - config 변수 추가
**파일**: `web_interface.py`

```python
# 변경 전
from app.config.settings import DOCS_DIR, ALLOWED_EXTS, PROJECT_ROOT

# 변경 후
from app.config.settings import DOCS_DIR, ALLOWED_EXTS, PROJECT_ROOT
import app.config.settings as config  # config 모듈 이름으로도 사용 (하위 호환성)
```

이렇게 하면:
- `DOCS_DIR`, `ALLOWED_EXTS` 등은 직접 사용 가능
- `config` 변수는 `app.config.settings` 모듈을 가리킴
- `config.DOCS_DIR` 형태로도 접근 가능

### 2. components/document_preview.py - 개선
**파일**: `components/document_preview.py`

#### A. DOCS_DIR 직접 임포트
```python
def render_document_preview(rag_instance: Any, config_module: Any) -> None:
    from components.pdf_viewer import show_pdf_preview
    from app.config.settings import DOCS_DIR  # 직접 임포트 추가
```

#### B. 파일 경로 처리 로직 개선
**변경 전** (버그 있음):
```python
file_path = Path(doc.get('path', Path(DOCS_DIR) / doc['filename']))
```

문제: `doc['path']`가 None이면 None을 반환 → TypeError

**변경 후** (안전한 처리):
```python
if 'path' in doc and doc['path']:
    file_path = Path(doc['path'])
else:
    file_path = Path(DOCS_DIR) / doc['filename']
```

#### C. Exception 처리 수정
```python
# 변경 전
except Exception as _:  # 변수 사용 불가
    st.text(f"오류 타입: {type(e).__name__}")  # NameError!

# 변경 후
except Exception as e:  # 변수 사용 가능
    st.text(f"오류 타입: {type(e).__name__}")
```

## 검증 결과

### 테스트 실행
```bash
$ python test_config_fix.py

✅ PASS: web_interface config
  config module: app.config.settings
  config.DOCS_DIR: /home/wnstn4647/AI-CHAT/docs

✅ PASS: document_preview imports
  DOCS_DIR: /home/wnstn4647/AI-CHAT/docs
  file_path 생성: /home/wnstn4647/AI-CHAT/docs/test.pdf

✅ 모든 테스트 통과! NameError 문제 해결 완료.
```

## 수정된 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `web_interface.py` | `import app.config.settings as config` 추가 |
| `components/document_preview.py` | DOCS_DIR 직접 임포트, 파일 경로 처리 개선, Exception 처리 수정 |
| `test_config_fix.py` | 신규 생성 - NameError 수정 검증 테스트 |

## 개선 효과

### 1. NameError 해결
- ✅ `config` 변수가 정의되어 `render_document_preview` 호출 가능
- ✅ `config.DOCS_DIR` 형태로 접근 가능

### 2. 하위 호환성 유지
- ✅ 기존 `config` 모듈 사용 패턴 유지
- ✅ 새로운 `DOCS_DIR` 직접 임포트 패턴도 지원

### 3. 버그 수정
- ✅ `doc.get('path', default)` 버그 수정 (`path=None` 처리)
- ✅ Exception 핸들러에서 변수 접근 가능

## 모범 사례

### 1. 두 가지 임포트 패턴 지원
```python
# 방법 1: 직접 임포트 (권장)
from app.config.settings import DOCS_DIR
docs_path = Path(DOCS_DIR)

# 방법 2: 모듈 임포트 (하위 호환성)
import app.config.settings as config
docs_path = Path(config.DOCS_DIR)
```

### 2. 안전한 딕셔너리 접근
```python
# ❌ 안전하지 않음
file_path = Path(doc.get('path', default_path))  # path=None 시 None 반환

# ✅ 안전함
if 'path' in doc and doc['path']:
    file_path = Path(doc['path'])
else:
    file_path = default_path
```

## 결론

NameError 문제가 완전히 해결되었습니다.
- **이전**: `NameError: name 'config' is not defined`
- **현재**: ✅ `config` 변수 정의 완료, 모든 테스트 통과

web_interface.py가 정상적으로 실행되며, Streamlit UI에서 문서 미리보기 기능이 작동합니다.