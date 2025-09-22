#!/usr/bin/env python3
"""
모든 스캔 PDF를 OCR 처리하는 스크립트
"""

import logging
import time
from background_ocr_processor import BackgroundOCRProcessor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    print("="*60)
    print("🚀 전체 OCR 처리 시작")
    print("="*60)

    # 처리기 초기화 (배치 크기 10개로 증가)
    processor = BackgroundOCRProcessor(batch_size=10, interval=5)

    # 초기 상태 확인
    scanned_pdfs = processor.identify_scanned_pdfs()
    total_count = len(scanned_pdfs)

    if total_count == 0:
        print("✅ 모든 문서가 이미 처리되었습니다!")
        return

    print(f"📊 처리할 스캔 PDF: {total_count}개")
    print(f"⚙️  배치 크기: {processor.batch_size}개")
    print(f"⏱️  예상 시간: 약 {(total_count * 25) / 3600:.1f}시간\n")

    # 처리 시작
    start_time = time.time()
    batch_count = 0

    while True:
        print(f"\n--- 배치 #{batch_count + 1} 처리 중 ---")

        # 배치 처리
        has_more = processor.process_batch()

        if not has_more:
            print("\n✅ 모든 문서 처리 완료!")
            break

        batch_count += 1

        # 진행 상황 출력
        remaining = len(processor.identify_scanned_pdfs())
        processed = total_count - remaining
        progress = (processed / total_count) * 100

        elapsed = time.time() - start_time
        avg_time = elapsed / processed if processed > 0 else 0
        eta = (remaining * avg_time) / 3600 if avg_time > 0 else 0

        print(f"\n📈 진행률: {progress:.1f}% ({processed}/{total_count})")
        print(f"⏱️  경과 시간: {elapsed/60:.1f}분")
        print(f"🎯 남은 시간: 약 {eta:.1f}시간")
        print(f"📊 처리 통계: 성공 {processor.processed_count}개, 오류 {processor._error_count}개")

        # 다음 배치까지 잠시 대기 (시스템 부하 방지)
        if has_more:
            print(f"\n💤 {processor.interval}초 후 다음 배치 시작...")
            time.sleep(processor.interval)

    # 최종 통계
    total_elapsed = time.time() - start_time
    final_stats = processor.get_stats()

    print("\n" + "="*60)
    print("🎉 OCR 처리 완료!")
    print("="*60)
    print(f"📊 최종 통계:")
    print(f"  - 총 처리: {final_stats['processed_count']}개")
    print(f"  - 오류: {final_stats['error_count']}개")
    print(f"  - 총 시간: {total_elapsed/60:.1f}분 ({total_elapsed/3600:.1f}시간)")
    print(f"  - 평균 속도: {final_stats['avg_time_per_file']:.1f}초/파일")
    print(f"\n💾 메타데이터 저장 완료: document_metadata.json")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자가 중단했습니다.")
        print("나중에 다시 실행하면 중단된 지점부터 계속됩니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()