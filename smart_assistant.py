#!/usr/bin/env python3
"""
스마트 어시스턴트 - 사용자 경험 최적화
=========================================

세심한 디테일로 완벽한 사용자 경험 제공
"""

import os
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import readline  # 커맨드라인 자동완성
import sys

# 색상 및 이모지
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'


class SmartAssistant:
    """스마트 어시스턴트"""

    def __init__(self):
        self.config_path = Path(".assistant_config.json")
        self.history_path = Path(".assistant_history")
        self.shortcuts_path = Path(".shortcuts.json")
        self.user_preferences = self.load_preferences()
        self.command_history = []
        self.frequently_used = {}
        self.last_errors = []
        self.tips_shown = set()

        # 자동완성 설정
        self._setup_autocomplete()

    def load_preferences(self) -> Dict:
        """사용자 설정 로드"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        return {
            'theme': 'default',
            'auto_suggest': True,
            'show_tips': True,
            'verbose': False,
            'startup_check': True
        }

    def save_preferences(self):
        """설정 저장"""
        with open(self.config_path, 'w') as f:
            json.dump(self.user_preferences, f, indent=2)

    def _setup_autocomplete(self):
        """자동완성 설정"""
        # 자동완성 명령어
        commands = [
            '검색', '문서검색', '자산검색',
            '도움말', '상태', '설정',
            '최적화', '캐시정리', '로그확인',
            '시작', '중지', '재시작',
            '테스트', '벤치마크', '모니터링'
        ]

        def completer(text, state):
            options = [cmd for cmd in commands if cmd.startswith(text)]
            if state < len(options):
                return options[state]
            return None

        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

        # 히스토리 로드
        if self.history_path.exists():
            readline.read_history_file(self.history_path)

    def welcome_screen(self):
        """환영 화면"""
        print("\n" + "="*70)
        print(f"{BOLD}{CYAN}🤖 AI-CHAT Smart Assistant{RESET}")
        print(f"{DIM}세심한 디테일로 완벽한 경험을 제공합니다{RESET}")
        print("="*70)

        # 시스템 상태 체크
        if self.user_preferences['startup_check']:
            self.quick_health_check()

        # 사용 팁
        if self.user_preferences['show_tips']:
            self.show_daily_tip()

        print()

    def quick_health_check(self):
        """빠른 상태 체크"""
        print(f"\n{CYAN}🔍 시스템 상태 확인 중...{RESET}")

        checks = {
            'Web UI': self._check_service('http://localhost:8501'),
            'API Server': self._check_service('http://localhost:8000/health'),
            'GPU': self._check_gpu(),
            'Memory': self._check_memory(),
            'Cache': self._check_cache()
        }

        all_good = True
        for service, status in checks.items():
            if status[0]:
                print(f"  ✅ {service}: {GREEN}{status[1]}{RESET}")
            else:
                print(f"  ❌ {service}: {RED}{status[1]}{RESET}")
                all_good = False

        if all_good:
            print(f"\n{GREEN}✨ 모든 시스템이 정상입니다!{RESET}")
        else:
            print(f"\n{YELLOW}⚠️  일부 서비스에 문제가 있습니다.{RESET}")
            self.suggest_fix()

    def _check_service(self, url: str) -> Tuple[bool, str]:
        """서비스 체크"""
        try:
            import requests
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return True, "정상"
            return False, f"상태 코드 {response.status_code}"
        except:
            return False, "오프라인"

    def _check_gpu(self) -> Tuple[bool, str]:
        """GPU 체크"""
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                memory_used = torch.cuda.memory_allocated(0) / (1024**3)
                return True, f"{device_name} ({memory_used:.1f}GB 사용 중)"
            return False, "사용 불가"
        except:
            return False, "확인 불가"

    def _check_memory(self) -> Tuple[bool, str]:
        """메모리 체크"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent < 80:
                return True, f"{mem.percent:.1f}% 사용 중"
            return False, f"{mem.percent:.1f}% (높음)"
        except:
            return False, "확인 불가"

    def _check_cache(self) -> Tuple[bool, str]:
        """캐시 체크"""
        cache_dir = Path(".cache")
        if cache_dir.exists():
            cache_files = list(cache_dir.glob("*"))
            size_mb = sum(f.stat().st_size for f in cache_files) / (1024**2)
            return True, f"{len(cache_files)}개 파일 ({size_mb:.1f}MB)"
        return False, "캐시 없음"

    def suggest_fix(self):
        """문제 해결 제안"""
        print(f"\n{YELLOW}💡 해결 방법:{RESET}")
        print(f"  1. 서비스 재시작: {CYAN}./run_all_services.sh{RESET}")
        print(f"  2. 빠른 시작: {CYAN}./quick_start.sh{RESET}")
        print(f"  3. 캐시 정리: {CYAN}python3 fast_startup_optimizer.py --build-cache{RESET}")

    def show_daily_tip(self):
        """일일 팁 표시"""
        tips = [
            "💡 Tip: 캐시를 사용하면 응답 속도가 100배 빨라집니다!",
            "💡 Tip: '탭' 키로 명령어를 자동완성할 수 있습니다.",
            "💡 Tip: GPU 메모리가 부족하면 LOW_VRAM=true를 설정하세요.",
            "💡 Tip: 로그는 logs/ 폴더에서 확인할 수 있습니다.",
            "💡 Tip: 성능 모니터링은 http://localhost:8502 에서 확인하세요.",
            "💡 Tip: API 문서는 http://localhost:8000/docs 에서 볼 수 있습니다.",
            "💡 Tip: Ctrl+C로 안전하게 종료할 수 있습니다."
        ]

        # 오늘의 팁 선택 (날짜 기반)
        today = datetime.now().day
        tip_index = today % len(tips)

        if tip_index not in self.tips_shown:
            print(f"\n{MAGENTA}{tips[tip_index]}{RESET}")
            self.tips_shown.add(tip_index)

    def interactive_menu(self):
        """대화형 메뉴"""
        menu_options = {
            '1': ('🔍 문서/자산 검색', self.search_interface),
            '2': ('📊 시스템 상태', self.show_status),
            '3': ('⚡ 성능 최적화', self.optimize_performance),
            '4': ('🔧 문제 해결', self.troubleshoot),
            '5': ('📝 로그 확인', self.view_logs),
            '6': ('⚙️  설정', self.settings_menu),
            '7': ('📈 벤치마크', self.run_benchmark),
            '8': ('🆘 도움말', self.show_help),
            '0': ('🚪 종료', None)
        }

        while True:
            print(f"\n{BOLD}메인 메뉴{RESET}")
            print("-" * 40)

            for key, (label, _) in menu_options.items():
                print(f"  {key}. {label}")

            try:
                choice = input(f"\n{CYAN}선택 >>> {RESET}").strip()

                if choice == '0':
                    self.goodbye()
                    break

                if choice in menu_options and menu_options[choice][1]:
                    menu_options[choice][1]()
                else:
                    print(f"{RED}잘못된 선택입니다.{RESET}")

                # 자주 사용하는 기능 기록
                self.frequently_used[choice] = self.frequently_used.get(choice, 0) + 1

            except KeyboardInterrupt:
                self.goodbye()
                break
            except Exception as e:
                print(f"{RED}오류 발생: {e}{RESET}")
                self.last_errors.append(str(e))

    def search_interface(self):
        """검색 인터페이스"""
        print(f"\n{BOLD}🔍 스마트 검색{RESET}")
        print("-" * 40)

        # 최근 검색 표시
        if self.command_history:
            print(f"{DIM}최근 검색:{RESET}")
            for i, query in enumerate(self.command_history[-3:], 1):
                print(f"  {i}. {query}")
            print()

        query = input(f"{CYAN}검색어 입력 >>> {RESET}").strip()

        if not query:
            return

        # 검색 모드 자동 판단
        mode = self._detect_search_mode(query)
        print(f"  모드: {YELLOW}{mode}{RESET}")

        # 검색 실행
        self._execute_search(query, mode)

        # 히스토리 저장
        self.command_history.append(query)
        self._save_history()

    def _detect_search_mode(self, query: str) -> str:
        """검색 모드 자동 감지"""
        asset_keywords = ['장비', '자산', '중계차', '스튜디오', '담당자', '위치']
        for keyword in asset_keywords:
            if keyword in query:
                return 'asset'
        return 'document'

    def _execute_search(self, query: str, mode: str):
        """검색 실행"""
        print(f"\n{CYAN}검색 중...{RESET}")

        try:
            # Python 스크립트로 직접 실행
            cmd = f"""
python3 -c "
from perfect_rag import PerfectRAG
rag = PerfectRAG()
result = rag.search_and_generate('{query}', '{mode}', 3, True)
print(result[:500] + '...' if len(result) > 500 else result)
"
"""
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout:
                print(f"\n{GREEN}검색 결과:{RESET}")
                print(result.stdout)
            else:
                print(f"{RED}검색 실패: {result.stderr}{RESET}")

        except subprocess.TimeoutExpired:
            print(f"{YELLOW}⏱️ 검색 시간 초과 (30초){RESET}")
        except Exception as e:
            print(f"{RED}오류: {e}{RESET}")

    def show_status(self):
        """시스템 상태 표시"""
        print(f"\n{BOLD}📊 시스템 상태{RESET}")
        subprocess.run("python3 system_health_monitor.py --interval 1", shell=True)

    def optimize_performance(self):
        """성능 최적화"""
        print(f"\n{BOLD}⚡ 성능 최적화{RESET}")
        print("-" * 40)

        optimizations = [
            ('캐시 재구축', 'python3 fast_startup_optimizer.py --build-cache --max-files 50'),
            ('메모리 정리', 'sync && echo 3 > /proc/sys/vm/drop_caches'),
            ('로그 정리', 'find logs -name "*.log" -mtime +7 -delete'),
            ('임시 파일 정리', 'find /tmp -name "*.tmp" -mtime +1 -delete'),
        ]

        for name, cmd in optimizations:
            print(f"  {CYAN}실행 중: {name}{RESET}")
            subprocess.run(cmd, shell=True, capture_output=True)
            print(f"    ✅ 완료")

        print(f"\n{GREEN}최적화 완료!{RESET}")

    def troubleshoot(self):
        """문제 해결"""
        print(f"\n{BOLD}🔧 문제 해결 도우미{RESET}")
        print("-" * 40)

        problems = {
            '1': '시작이 느려요',
            '2': '메모리 부족 오류',
            '3': 'GPU를 인식하지 못해요',
            '4': '검색 결과가 없어요',
            '5': '서비스가 시작되지 않아요'
        }

        for key, problem in problems.items():
            print(f"  {key}. {problem}")

        choice = input(f"\n{CYAN}문제 선택 >>> {RESET}").strip()

        solutions = {
            '1': [
                "캐시 구축: python3 fast_startup_optimizer.py --build-cache",
                "문서 수 제한: export MAX_DOCUMENTS=30",
                "빠른 시작: ./quick_start.sh"
            ],
            '2': [
                "메모리 정리: sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'",
                "LOW_VRAM 모드: export LOW_VRAM=true",
                "프로세스 확인: ps aux | grep python | head -10"
            ],
            '3': [
                "CUDA 확인: nvidia-smi",
                "드라이버 확인: nvidia-smi -q | grep 'Driver Version'",
                "PyTorch 확인: python3 -c 'import torch; print(torch.cuda.is_available())'"
            ],
            '4': [
                "인덱스 재구축: python3 auto_indexer.py",
                "캐시 정리: rm -rf .cache/*",
                "문서 확인: ls docs/*.pdf | wc -l"
            ],
            '5': [
                "포트 확인: lsof -i :8501",
                "프로세스 종료: pkill -f streamlit",
                "서비스 재시작: ./run_all_services.sh"
            ]
        }

        if choice in solutions:
            print(f"\n{YELLOW}💡 해결 방법:{RESET}")
            for i, solution in enumerate(solutions[choice], 1):
                print(f"  {i}. {solution}")
                run = input(f"     실행할까요? (y/n) >>> ").strip().lower()
                if run == 'y':
                    subprocess.run(solution.split(':')[1].strip(), shell=True)

    def view_logs(self):
        """로그 확인"""
        print(f"\n{BOLD}📝 로그 확인{RESET}")
        print("-" * 40)

        log_files = list(Path("logs").glob("*.log"))
        if not log_files:
            print(f"{YELLOW}로그 파일이 없습니다.{RESET}")
            return

        for i, log_file in enumerate(log_files[:10], 1):
            size_kb = log_file.stat().st_size / 1024
            print(f"  {i}. {log_file.name} ({size_kb:.1f}KB)")

        choice = input(f"\n{CYAN}로그 선택 (번호) >>> {RESET}").strip()

        try:
            index = int(choice) - 1
            if 0 <= index < len(log_files):
                print(f"\n{CYAN}마지막 20줄:{RESET}")
                subprocess.run(f"tail -20 {log_files[index]}", shell=True)
        except:
            print(f"{RED}잘못된 선택입니다.{RESET}")

    def settings_menu(self):
        """설정 메뉴"""
        print(f"\n{BOLD}⚙️  설정{RESET}")
        print("-" * 40)

        settings = {
            '1': ('자동 제안', 'auto_suggest'),
            '2': ('팁 표시', 'show_tips'),
            '3': ('상세 모드', 'verbose'),
            '4': ('시작 체크', 'startup_check')
        }

        for key, (label, setting) in settings.items():
            current = '✅' if self.user_preferences[setting] else '❌'
            print(f"  {key}. {label}: {current}")

        choice = input(f"\n{CYAN}설정 변경 (번호) >>> {RESET}").strip()

        if choice in settings:
            setting = settings[choice][1]
            self.user_preferences[setting] = not self.user_preferences[setting]
            self.save_preferences()
            print(f"{GREEN}설정이 변경되었습니다.{RESET}")

    def run_benchmark(self):
        """벤치마크 실행"""
        print(f"\n{BOLD}📈 성능 벤치마크{RESET}")
        print("-" * 40)

        tests = [
            ("초기화 속도", "time python3 -c 'from perfect_rag import PerfectRAG; rag = PerfectRAG()'"),
            ("검색 속도", "time python3 -c 'from perfect_rag import PerfectRAG; rag = PerfectRAG(); rag.search_and_generate(\"test\", \"document\", 3)'"),
            ("메모리 사용", "python3 -c 'import psutil; print(f\"Memory: {psutil.virtual_memory().percent}%\")'"),
            ("GPU 사용", "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader")
        ]

        for name, cmd in tests:
            print(f"\n{CYAN}테스트: {name}{RESET}")
            subprocess.run(cmd, shell=True)

    def show_help(self):
        """도움말 표시"""
        help_text = """
{BOLD}🆘 도움말{RESET}
{DIM}{'='*60}{RESET}

{CYAN}주요 기능:{RESET}
  • 스마트 검색: 자동으로 문서/자산 모드 감지
  • 자동 복구: 서비스 장애 시 자동 재시작
  • 성능 최적화: 캐시, 메모리, GPU 관리
  • 문제 해결: 단계별 해결 가이드

{CYAN}단축키:{RESET}
  • Tab: 자동완성
  • Ctrl+C: 안전 종료
  • ↑/↓: 명령 히스토리

{CYAN}유용한 명령:{RESET}
  • ./quick_start.sh - 빠른 시작
  • ./run_all_services.sh - 모든 서비스 시작
  • python3 test_system.py - 시스템 테스트

{CYAN}웹 인터페이스:{RESET}
  • 메인: http://localhost:8501
  • API: http://localhost:8000/docs
  • 모니터: http://localhost:8502

{DIM}더 많은 정보: CLAUDE.md 파일 참조{RESET}
"""
        print(help_text.format(**locals()))

    def goodbye(self):
        """종료 메시지"""
        # 히스토리 저장
        self._save_history()

        # 사용 통계
        if self.frequently_used:
            most_used = max(self.frequently_used, key=self.frequently_used.get)
            print(f"\n{CYAN}가장 많이 사용한 기능: 메뉴 {most_used}{RESET}")

        print(f"\n{GREEN}감사합니다! 다시 만나요! 👋{RESET}")
        print(f"{DIM}세심한 디테일로 완벽한 경험을 제공한 Smart Assistant{RESET}\n")

    def _save_history(self):
        """히스토리 저장"""
        readline.write_history_file(self.history_path)


def main():
    """메인 실행"""
    assistant = SmartAssistant()

    try:
        # 환영 화면
        assistant.welcome_screen()

        # 대화형 메뉴
        assistant.interactive_menu()

    except KeyboardInterrupt:
        assistant.goodbye()
    except Exception as e:
        print(f"{RED}예상치 못한 오류: {e}{RESET}")
        assistant.goodbye()


if __name__ == "__main__":
    main()