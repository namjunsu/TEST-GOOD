#\!/bin/bash
# RAG 시스템 실행 스크립트

# 경로 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src:$(pwd)/rag_system"

# Streamlit 실행
streamlit run src/web_interface.py --server.port 8501 --server.address 0.0.0.0
