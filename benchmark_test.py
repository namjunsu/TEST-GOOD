#!/usr/bin/env python3
"""
LLM 성능 벤치마크 테스트
최적화 전후 성능을 정확하게 측정합니다.
"""

import time
import logging
import statistics
from pathlib import Path
import json
import psutil
import gc

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class BenchmarkRunner:
    """벤치마크 테스트 실행기"""

    def __init__(self):
        self.results = {
            'original': {
                'init_times': [],
                'response_times': [],
                'memory_usage': []
            },
            'optimized': {
                'init_times': [],
                'response_times': [],
                'memory_usage': []
            }
        }

        # 테스트 쿼리 세트
        self.test_queries = [
            "시스템 테스트",  # 짧은 쿼리
            "2017년 카메라 구매 내역",  # 중간 쿼리
            "문자 발생기 관련 모든 문서를 찾아서 구매 날짜와 용도를 정리해주세요",  # 긴 쿼리
            "트라이포드 수리 건의 상세 내용과 비용을 알려주세요",  # 구체적 쿼리
            "방송 장비 중에서 가장 최근에 구매한 것은 무엇인가요?"  # 분석 쿼리
        ]

    def warm_up(self):
        """시스템 워밍업"""
        logger.info("🔥 시스템 워밍업...")

        # GPU 워밍업
        try:
            import torch
            if torch.cuda.is_available():
                dummy = torch.randn(1000, 1000).cuda()
                del dummy
                torch.cuda.empty_cache()
        except:
            pass

        # 메모리 정리
        gc.collect()
        time.sleep(2)

    def measure_original_performance(self, num_runs: int = 3):
        """원본 성능 측정"""
        logger.info("\n📊 원본 성능 측정 시작...")

        from perfect_rag import PerfectRAG

        for run in range(num_runs):
            logger.info(f"\n  실행 {run + 1}/{num_runs}")

            # 초기화 시간
            init_start = time.time()
            rag = PerfectRAG()
            init_time = time.time() - init_start
            self.results['original']['init_times'].append(init_time)
            logger.info(f"    초기화: {init_time:.2f}초")

            # 각 쿼리에 대한 응답 시간
            for i, query in enumerate(self.test_queries, 1):
                response_start = time.time()
                try:
                    response = rag.answer(query)
                    response_time = time.time() - response_start
                    self.results['original']['response_times'].append(response_time)
                    logger.info(f"    쿼리 {i}: {response_time:.2f}초")
                except Exception as e:
                    logger.error(f"    쿼리 {i} 실패: {e}")
                    self.results['original']['response_times'].append(None)

            # 메모리 사용량
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.results['original']['memory_usage'].append(memory_mb)
            logger.info(f"    메모리: {memory_mb:.1f} MB")

            # 인스턴스 정리
            del rag
            gc.collect()
            time.sleep(2)

    def apply_optimizations(self):
        """최적화 적용"""
        logger.info("\n⚙️ 최적화 적용 중...")

        # config/llm_optimization.yaml 로드
        config_path = Path("config/llm_optimization.yaml")
        if config_path.exists():
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"  ✅ 최적화 설정 로드 완료")

                # 설정 내용 표시
                logger.info(f"    - 최대 컨텍스트: {config['prompts']['max_context_tokens']}토큰")
                logger.info(f"    - 최대 응답: {config['prompts']['max_response_tokens']}토큰")
                logger.info(f"    - 배치 사이즈: {config['batch']['batch_size']}")
        else:
            logger.warning("  ⚠️ 최적화 설정 파일 없음")

    def measure_optimized_performance(self, num_runs: int = 3):
        """최적화된 성능 측정"""
        logger.info("\n⚡ 최적화 성능 측정 시작...")

        # 최적화 설정 적용
        import os
        os.environ['USE_OPTIMIZED_PROMPTS'] = 'true'
        os.environ['MAX_CONTEXT_TOKENS'] = '2000'
        os.environ['ENABLE_BATCHING'] = 'true'

        from perfect_rag import PerfectRAG

        for run in range(num_runs):
            logger.info(f"\n  실행 {run + 1}/{num_runs}")

            # 초기화 시간
            init_start = time.time()
            rag = PerfectRAG()
            init_time = time.time() - init_start
            self.results['optimized']['init_times'].append(init_time)
            logger.info(f"    초기화: {init_time:.2f}초")

            # 각 쿼리에 대한 응답 시간
            for i, query in enumerate(self.test_queries, 1):
                response_start = time.time()
                try:
                    response = rag.answer(query)
                    response_time = time.time() - response_start
                    self.results['optimized']['response_times'].append(response_time)
                    logger.info(f"    쿼리 {i}: {response_time:.2f}초")
                except Exception as e:
                    logger.error(f"    쿼리 {i} 실패: {e}")
                    self.results['optimized']['response_times'].append(None)

            # 메모리 사용량
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.results['optimized']['memory_usage'].append(memory_mb)
            logger.info(f"    메모리: {memory_mb:.1f} MB")

            # 인스턴스 정리
            del rag
            gc.collect()
            time.sleep(2)

    def analyze_results(self):
        """결과 분석"""
        logger.info("\n" + "=" * 60)
        logger.info("📈 벤치마크 결과 분석")
        logger.info("=" * 60)

        # 초기화 시간 분석
        original_init = statistics.mean(self.results['original']['init_times'])
        optimized_init = statistics.mean(self.results['optimized']['init_times'])
        init_improvement = (original_init - optimized_init) / original_init * 100

        logger.info("\n🚀 초기화 시간:")
        logger.info(f"  • 원본: {original_init:.2f}초")
        logger.info(f"  • 최적화: {optimized_init:.2f}초")
        logger.info(f"  • 개선: {init_improvement:.1f}%")

        # 응답 시간 분석
        valid_original = [t for t in self.results['original']['response_times'] if t]
        valid_optimized = [t for t in self.results['optimized']['response_times'] if t]

        if valid_original and valid_optimized:
            original_response = statistics.mean(valid_original)
            optimized_response = statistics.mean(valid_optimized)
            response_improvement = (original_response - optimized_response) / original_response * 100

            logger.info("\n⏱️ 평균 응답 시간:")
            logger.info(f"  • 원본: {original_response:.2f}초")
            logger.info(f"  • 최적화: {optimized_response:.2f}초")
            logger.info(f"  • 개선: {response_improvement:.1f}%")

            # 최대/최소 응답 시간
            logger.info("\n📊 응답 시간 범위:")
            logger.info(f"  • 원본: {min(valid_original):.2f}초 ~ {max(valid_original):.2f}초")
            logger.info(f"  • 최적화: {min(valid_optimized):.2f}초 ~ {max(valid_optimized):.2f}초")

        # 메모리 사용량 분석
        original_memory = statistics.mean(self.results['original']['memory_usage'])
        optimized_memory = statistics.mean(self.results['optimized']['memory_usage'])
        memory_reduction = (original_memory - optimized_memory) / original_memory * 100

        logger.info("\n💾 평균 메모리 사용:")
        logger.info(f"  • 원본: {original_memory:.1f} MB")
        logger.info(f"  • 최적화: {optimized_memory:.1f} MB")
        logger.info(f"  • 절감: {memory_reduction:.1f}%")

        # 종합 평가
        logger.info("\n🎯 종합 평가:")
        total_improvement = (init_improvement + response_improvement) / 2

        if total_improvement > 30:
            logger.info(f"  ✨ 탁월한 개선! 전체 성능 {total_improvement:.1f}% 향상")
        elif total_improvement > 20:
            logger.info(f"  ✅ 좋은 개선! 전체 성능 {total_improvement:.1f}% 향상")
        elif total_improvement > 10:
            logger.info(f"  👍 개선 확인! 전체 성능 {total_improvement:.1f}% 향상")
        else:
            logger.info(f"  📊 미미한 개선: {total_improvement:.1f}%")

        return {
            'init_improvement': init_improvement,
            'response_improvement': response_improvement,
            'memory_reduction': memory_reduction,
            'total_improvement': total_improvement
        }

    def save_results(self):
        """결과 저장"""
        output = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'raw_results': self.results,
            'analysis': self.analyze_results()
        }

        output_file = Path("benchmark_results.json")
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)

        logger.info(f"\n💾 결과 저장: {output_file}")

def main():
    """메인 벤치마크 실행"""
    logger.info("=" * 60)
    logger.info("🏁 LLM 성능 벤치마크 시작")
    logger.info("=" * 60)

    runner = BenchmarkRunner()

    try:
        # 1. 워밍업
        runner.warm_up()

        # 2. 원본 성능 측정
        runner.measure_original_performance(num_runs=2)

        # 3. 최적화 적용
        runner.apply_optimizations()

        # 4. 최적화 성능 측정
        runner.measure_optimized_performance(num_runs=2)

        # 5. 결과 분석
        runner.analyze_results()

        # 6. 결과 저장
        runner.save_results()

        logger.info("\n✅ 벤치마크 완료!")

    except Exception as e:
        logger.error(f"❌ 벤치마크 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()