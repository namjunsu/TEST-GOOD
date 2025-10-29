#!/usr/bin/env python3
"""
질문-답변 흐름 진단 도구
실제 질문을 넣고 각 단계별로 무슨 일이 일어나는지 추적합니다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_query_routing(query: str):
    """쿼리 라우팅 테스트"""
    print(f"\n{'='*80}")
    print(f"🔍 쿼리 라우팅 테스트")
    print(f"{'='*80}")
    print(f"입력 쿼리: {query}")
    print()

    try:
        from app.rag.query_router import QueryRouter

        router = QueryRouter()

        # 모드 분류
        mode = router.classify_mode(query)
        reason = router.get_routing_reason(query)

        print(f"✅ 분류 결과:")
        print(f"  모드: {mode.value}")
        print(f"  이유: {reason}")

        return mode

    except Exception as e:
        print(f"❌ 라우팅 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_document_search(query: str):
    """문서 검색 테스트"""
    print(f"\n{'='*80}")
    print(f"📚 문서 검색 테스트")
    print(f"{'='*80}")

    try:
        from modules.metadata_db import MetadataDB

        db = MetadataDB()

        # 기안자/연도 추출 시도
        import re

        # 연도 패턴
        year_match = re.search(r'20\d{2}', query)
        year = year_match.group(0) if year_match else None

        # 기안자 패턴 (간단한 예시)
        drafter_patterns = ['작성', '기안', '담당']
        drafter = None
        for pattern in drafter_patterns:
            if pattern in query:
                # 패턴 주변 단어 추출 (간단한 로직)
                words = query.split()
                for i, word in enumerate(words):
                    if pattern in word and i > 0:
                        drafter = words[i-1]
                        break

        print(f"추출된 검색 조건:")
        print(f"  연도: {year or '없음'}")
        print(f"  기안자: {drafter or '없음'}")
        print()

        # 문서 검색
        if year or drafter:
            results = db.search_documents(drafter=drafter, year=year, limit=5)
            print(f"✅ 검색 결과: {len(results)}개 문서")
            for i, doc in enumerate(results[:3], 1):
                print(f"  {i}. {doc['title'][:50]}... ({doc['filename']})")
        else:
            # 전체 문서 수
            total = db.count_unique_documents()
            print(f"✅ 전체 문서 수: {total}개")

        db.close()

    except Exception as e:
        print(f"❌ 문서 검색 실패: {e}")
        import traceback
        traceback.print_exc()


def test_full_answer(query: str):
    """전체 답변 생성 테스트"""
    print(f"\n{'='*80}")
    print(f"🤖 전체 답변 생성 테스트")
    print(f"{'='*80}")

    try:
        # RAG 파이프라인 초기화
        print("RAG 파이프라인 초기화 중...")
        from app.rag.pipeline import RAGPipeline

        rag = RAGPipeline()
        print("✅ RAG 초기화 완료")
        print()

        # 답변 생성
        print(f"질문: {query}")
        print("답변 생성 중...")
        print()

        response = rag.answer(query)

        # 응답 분석
        print("="*80)
        print("📝 응답 결과:")
        print("="*80)

        if isinstance(response, dict):
            print(f"응답 타입: dict")
            print(f"키: {list(response.keys())}")
            print()

            if 'text' in response:
                text = response['text']
                print(f"답변 텍스트 ({len(text)} 글자):")
                print("-" * 80)
                print(text)
                print("-" * 80)
            else:
                print("⚠️ 'text' 키가 없습니다")
                print(f"전체 응답: {response}")

            print()

            if 'evidence' in response or 'citations' in response:
                evidence = response.get('evidence') or response.get('citations', [])
                print(f"출처 문서: {len(evidence)}개")
                for i, ev in enumerate(evidence[:3], 1):
                    if isinstance(ev, dict):
                        print(f"  {i}. {ev.get('filename', 'unknown')}")
            else:
                print("⚠️ 출처 정보 없음")

            print()

            if 'status' in response:
                status = response['status']
                print(f"상태:")
                print(f"  - 검색된 문서: {status.get('retrieved_count', 'N/A')}")
                print(f"  - 선택된 문서: {status.get('selected_count', 'N/A')}")
                print(f"  - 발견 여부: {status.get('found', 'N/A')}")

        else:
            print(f"⚠️ 예상하지 못한 응답 타입: {type(response)}")
            print(f"응답: {response}")

        return response

    except Exception as e:
        print(f"❌ 답변 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def interactive_mode():
    """대화형 모드"""
    print("="*80)
    print("🔧 질문-답변 흐름 진단 도구 (대화형 모드)")
    print("="*80)
    print()
    print("명령어:")
    print("  - 'q' 또는 'quit': 종료")
    print("  - 'route <질문>': 라우팅만 테스트")
    print("  - 'search <질문>': 문서 검색만 테스트")
    print("  - 'full <질문>': 전체 답변 생성")
    print("  - '<질문>': 전체 테스트 (라우팅 + 검색 + 답변)")
    print()

    while True:
        try:
            user_input = input("\n질문을 입력하세요 > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['q', 'quit', 'exit']:
                print("종료합니다.")
                break

            # 명령어 파싱
            if user_input.startswith('route '):
                query = user_input[6:].strip()
                test_query_routing(query)

            elif user_input.startswith('search '):
                query = user_input[7:].strip()
                test_document_search(query)

            elif user_input.startswith('full '):
                query = user_input[5:].strip()
                test_full_answer(query)

            else:
                # 전체 테스트
                query = user_input
                mode = test_query_routing(query)
                test_document_search(query)
                test_full_answer(query)

        except KeyboardInterrupt:
            print("\n\n종료합니다.")
            break
        except Exception as e:
            print(f"❌ 오류: {e}")
            import traceback
            traceback.print_exc()


def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='질문-답변 흐름 진단 도구')
    parser.add_argument('query', nargs='?', help='테스트할 질문 (없으면 대화형 모드)')
    parser.add_argument('--route-only', action='store_true', help='라우팅만 테스트')
    parser.add_argument('--search-only', action='store_true', help='검색만 테스트')

    args = parser.parse_args()

    if args.query:
        # 단일 질문 모드
        if args.route_only:
            test_query_routing(args.query)
        elif args.search_only:
            test_document_search(args.query)
        else:
            # 전체 테스트
            test_query_routing(args.query)
            test_document_search(args.query)
            test_full_answer(args.query)
    else:
        # 대화형 모드
        interactive_mode()


if __name__ == "__main__":
    main()