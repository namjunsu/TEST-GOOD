#!/usr/bin/env python3
"""
문서 메타데이터 사전 캐싱 스크립트
서버 시작 전에 미리 실행하여 캐시 구축
"""
import time
from pathlib import Path
import sys

def preload_documents():
    """문서 메타데이터를 미리 로드하여 캐시 구축"""
    print("="*60)
    print("📚 문서 메타데이터 사전 캐싱 시작")
    print("="*60)

    start_time = time.time()

    # PerfectRAG 인스턴스 생성 (캐시 구축)
    from perfect_rag import PerfectRAG
    rag = PerfectRAG()

    end_time = time.time()
    elapsed = end_time - start_time

    print("\n" + "="*60)
    print("✅ 캐싱 완료!")
    print(f"⏱️  소요 시간: {elapsed:.2f}초")
    print(f"📊 처리된 파일:")
    print(f"   - PDF: {len(rag.pdf_files)}개")
    print(f"   - TXT: {len(rag.txt_files)}개")
    print(f"   - 메타데이터: {len(rag.metadata_cache)}개")
    print("\n💡 이제 웹 인터페이스를 실행하면 빠르게 로드됩니다!")
    print("   streamlit run web_interface.py")
    print("="*60)

if __name__ == "__main__":
    preload_documents()