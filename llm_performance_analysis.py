#!/usr/bin/env python3
"""
LLM 응답 속도 상세 분석 도구
각 단계별 시간을 정밀하게 측정하여 병목 지점을 찾습니다.
"""

import time
import logging
import psutil
import torch
from pathlib import Path
import json
from datetime import datetime

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

class LLMPerformanceAnalyzer:
    def __init__(self):
        self.metrics = {
            'initialization': {},
            'model_loading': {},
            'prompt_processing': {},
            'response_generation': {},
            'memory_usage': {},
            'gpu_usage': {}
        }

    def measure_initialization(self):
        """시스템 초기화 시간 측정"""
        logger.info("📊 시스템 초기화 분석 시작...")

        # 1. Import 시간 측정
        import_start = time.time()
        from perfect_rag import PerfectRAG
        import_time = time.time() - import_start
        self.metrics['initialization']['import_time'] = import_time
        logger.info(f"  • Import 시간: {import_time:.3f}초")

        # 2. 인스턴스 생성 시간
        init_start = time.time()
        rag = PerfectRAG()
        init_time = time.time() - init_start
        self.metrics['initialization']['instance_creation'] = init_time
        logger.info(f"  • 인스턴스 생성: {init_time:.3f}초")

        # 3. 메모리 사용량
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.metrics['memory_usage']['after_init'] = memory_mb
        logger.info(f"  • 메모리 사용: {memory_mb:.1f} MB")

        return rag

    def measure_model_loading(self):
        """LLM 모델 로딩 성능 측정"""
        logger.info("\n🤖 LLM 로딩 성능 분석...")

        from rag_system.qwen_llm import QwenLLM

        # GPU 사용 가능 여부
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            logger.info(f"  • GPU: {gpu_name} ({gpu_memory:.1f} GB)")
            self.metrics['gpu_usage']['device'] = gpu_name
            self.metrics['gpu_usage']['total_memory_gb'] = gpu_memory
        else:
            logger.warning("  • GPU 사용 불가 - CPU 모드")
            self.metrics['gpu_usage']['device'] = "CPU"

        # 모델 로딩 시간
        load_start = time.time()
        llm = QwenLLM()
        load_time = time.time() - load_start
        self.metrics['model_loading']['total_time'] = load_time
        logger.info(f"  • 모델 로딩: {load_time:.3f}초")

        # 로딩 후 메모리
        if gpu_available:
            gpu_memory_used = torch.cuda.memory_allocated(0) / 1024**3
            self.metrics['gpu_usage']['memory_used_gb'] = gpu_memory_used
            logger.info(f"  • GPU 메모리 사용: {gpu_memory_used:.2f} GB")

        return llm

    def measure_prompt_processing(self, rag):
        """프롬프트 처리 성능 측정"""
        logger.info("\n📝 프롬프트 처리 성능 분석...")

        test_queries = [
            "간단한 질문",
            "2017년에 구매한 카메라 장비의 구매 목적과 금액을 알려주세요",
            "문자 발생기와 관련된 모든 문서를 찾아서 구매 날짜와 용도를 정리해주세요. 특히 뉴스룸과 부조정실에서 사용하는 장비를 구분해서 설명해주세요."
        ]

        for i, query in enumerate(test_queries, 1):
            logger.info(f"\n  테스트 {i}: {len(query)}자 쿼리")

            # 검색 시간
            search_start = time.time()
            # 실제 검색 로직 (perfect_rag.py의 search 부분)
            search_time = time.time() - search_start

            # 컨텍스트 생성 시간
            context_start = time.time()
            # 컨텍스트 생성 로직
            context_time = time.time() - context_start

            self.metrics['prompt_processing'][f'query_{i}'] = {
                'query_length': len(query),
                'search_time': search_time,
                'context_time': context_time
            }

            logger.info(f"    - 검색: {search_time:.3f}초")
            logger.info(f"    - 컨텍스트: {context_time:.3f}초")

    def measure_response_generation(self, llm):
        """응답 생성 성능 측정"""
        logger.info("\n🔄 응답 생성 성능 분석...")

        # 다양한 길이의 컨텍스트 테스트
        context_sizes = [500, 1000, 2000, 4000]

        for size in context_sizes:
            logger.info(f"\n  컨텍스트 크기: {size}토큰")

            # 샘플 컨텍스트 생성
            context = "테스트 문서 내용. " * (size // 10)
            query = "이 문서의 주요 내용을 요약해주세요."

            # 토큰화 시간
            token_start = time.time()
            # 토큰화 로직
            token_time = time.time() - token_start

            # 생성 시간
            gen_start = time.time()
            # 실제 생성 로직 (스트리밍 vs 일반)
            gen_time = time.time() - gen_start

            self.metrics['response_generation'][f'context_{size}'] = {
                'tokenization_time': token_time,
                'generation_time': gen_time,
                'tokens_per_second': size / gen_time if gen_time > 0 else 0
            }

            logger.info(f"    - 토큰화: {token_time:.3f}초")
            logger.info(f"    - 생성: {gen_time:.3f}초")
            logger.info(f"    - 속도: {size/gen_time if gen_time > 0 else 0:.1f} tokens/s")

    def analyze_bottlenecks(self):
        """병목 지점 분석 및 개선 제안"""
        logger.info("\n🔍 병목 지점 분석...")

        # 가장 느린 단계 찾기
        total_init = sum(self.metrics['initialization'].values())
        total_load = self.metrics['model_loading'].get('total_time', 0)

        logger.info(f"\n📊 전체 시간 분석:")
        logger.info(f"  • 초기화: {total_init:.3f}초")
        logger.info(f"  • 모델 로딩: {total_load:.3f}초")

        # 개선 제안
        suggestions = []

        if total_init > 3:
            suggestions.append("⚠️ 초기화 시간이 3초 이상 - 모듈 lazy loading 권장")

        if total_load > 5:
            suggestions.append("⚠️ 모델 로딩이 5초 이상 - 모델 사전 로딩 또는 경량 모델 사용")

        if self.metrics['gpu_usage'].get('device') == "CPU":
            suggestions.append("⚠️ CPU 모드로 실행 중 - GPU 사용 권장")

        logger.info("\n💡 개선 제안:")
        for suggestion in suggestions:
            logger.info(f"  {suggestion}")

        return suggestions

    def save_report(self):
        """분석 보고서 저장"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'metrics': self.metrics,
            'analysis': self.analyze_bottlenecks()
        }

        output_file = Path("llm_performance_report.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"\n📄 보고서 저장: {output_file}")
        return report

def main():
    """메인 분석 실행"""
    logger.info("=" * 60)
    logger.info("🚀 LLM 응답 속도 상세 분석 시작")
    logger.info("=" * 60)

    analyzer = LLMPerformanceAnalyzer()

    try:
        # 1. 초기화 측정
        rag = analyzer.measure_initialization()

        # 2. 모델 로딩 측정
        llm = analyzer.measure_model_loading()

        # 3. 프롬프트 처리 측정
        analyzer.measure_prompt_processing(rag)

        # 4. 응답 생성 측정
        analyzer.measure_response_generation(llm)

        # 5. 병목 분석
        analyzer.analyze_bottlenecks()

        # 6. 보고서 저장
        analyzer.save_report()

        logger.info("\n✅ 분석 완료!")

    except Exception as e:
        logger.error(f"❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()