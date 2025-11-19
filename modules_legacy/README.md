# modules_legacy/ - 레거시 모듈 아카이브

**상태**: 2025-11-14 이후 사용 중단 (DEPRECATED)

## 📋 이력

이 폴더는 과거 `modules/` 디렉토리로 존재했으나, 아키텍처 정리 과정에서 다음과 같이 마이그레이션되었습니다:

### 마이그레이션 완료 항목

| 레거시 경로 | 신규 경로 | 상태 |
|------------|----------|------|
| `modules/metadata_db.py` | `app/data/metadata_db.py` | ✅ 마이그레이션 완료 |
| `modules/amount_parser_v2.py` | `app/data/amount_parser_v2.py` | ✅ 마이그레이션 완료 |
| `modules/metadata_extractor.py` | *(미사용)* | ⚠️ UNUSED |
| `modules/search_module.py` | *(미사용)* | ⚠️ UNUSED |
| `modules/search_module_hybrid.py` | *(미사용)* | ⚠️ UNUSED |

## ⚠️ 주의사항

- **이 폴더의 파일들은 실제 런타임에서 사용되지 않습니다.**
- 신규 코드에서 `from modules_legacy import ...` 형태의 import를 추가하지 마세요.
- 프로덕션 배포 시 이 폴더는 제외됩니다.

## 🗑️ 삭제 계획

- **보존 기간**: 2025-12-31까지 (약 6주)
- **삭제 예정일**: 2026-01-01
- **조건**: 해당 기간 동안 런타임 오류가 없고, 테스트가 모두 통과하는 경우

## 📚 참고

아키텍처 변경 내역은 `reports/xray/` 폴더의 최신 분석 리포트를 참조하세요.

---

*생성일: 2025-11-14*
*생성자: Claude Code (xray 분석 기반 자동 정리)*
