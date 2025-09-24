# 🎯 AI-CHAT RAG System

## 🚀 실행 방법 (간단!)

```bash
# Docker로 실행 (권장)
docker compose up

# 또는 로컬 실행
streamlit run web_interface.py
```

## 📁 파일 설명 (이것만 있으면 됨!)

### 핵심 파일 7개:
- `web_interface.py` - 웹 UI
- `perfect_rag.py` - 검색 엔진
- `auto_indexer.py` - 자동 인덱싱
- `config.py` - 설정
- `log_system.py` - 로깅
- `response_formatter.py` - 응답 포맷
- `smart_search_enhancer.py` - 검색 개선

### 설정 파일:
- `requirements_updated.txt` - **이것만 사용!**
- `.env` - 환경 변수
- `docker-compose.yml` - Docker 설정

## ❌ 제거된 것들:
- Asset/장비 검색 (완전 제거)
- 복잡한 추가 시스템들
- 중복 requirements 파일들
- 사용 안하는 Python 파일 30개+

## ✅ 남은 기능:
- PDF 문서 검색
- Qwen2.5 AI 답변
- 자동 인덱싱
- 캐싱 시스템

---
*깔끔하게 정리 완료!*
