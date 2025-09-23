#!/usr/bin/env python3
"""
시스템 헬스 모니터링 및 자동 복구
====================================

세심한 디테일까지 관리하는 스마트 모니터
"""

import psutil
import os
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading
import signal
import sys

# 색상 코드
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


class SystemHealthMonitor:
    """시스템 헬스 모니터링"""

    def __init__(self):
        self.running = True
        self.health_status = {
            'cpu': {'status': 'ok', 'value': 0, 'threshold': 80},
            'memory': {'status': 'ok', 'value': 0, 'threshold': 85},
            'disk': {'status': 'ok', 'value': 0, 'threshold': 90},
            'gpu': {'status': 'ok', 'value': 0, 'threshold': 90},
            'processes': {'status': 'ok', 'count': 0},
            'api': {'status': 'unknown', 'response_time': 0},
            'web': {'status': 'unknown', 'response_time': 0}
        }
        self.issues = []
        self.auto_recovery_enabled = True
        self.log_file = Path("logs/health_monitor.log")
        self.log_file.parent.mkdir(exist_ok=True)

    def check_cpu(self) -> Dict:
        """CPU 상태 체크"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # 각 코어별 사용률
            per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)

            status = {
                'percent': cpu_percent,
                'cores': cpu_count,
                'per_core': per_cpu,
                'status': 'ok' if cpu_percent < self.health_status['cpu']['threshold'] else 'warning'
            }

            if cpu_percent > 90:
                status['status'] = 'critical'
                self.issues.append(f"CPU 과부하: {cpu_percent}%")

            self.health_status['cpu']['value'] = cpu_percent
            return status
        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def check_memory(self) -> Dict:
        """메모리 상태 체크"""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # 메모리 누수 감지
            process = psutil.Process()
            mem_info = process.memory_info()

            status = {
                'ram_percent': mem.percent,
                'ram_used_gb': mem.used / (1024**3),
                'ram_available_gb': mem.available / (1024**3),
                'swap_percent': swap.percent,
                'process_rss_gb': mem_info.rss / (1024**3),
                'status': 'ok'
            }

            if mem.percent > self.health_status['memory']['threshold']:
                status['status'] = 'warning'
                self.issues.append(f"메모리 부족: {mem.percent}%")

            if mem.percent > 95:
                status['status'] = 'critical'
                self._trigger_memory_cleanup()

            self.health_status['memory']['value'] = mem.percent
            return status
        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def check_disk(self) -> Dict:
        """디스크 상태 체크"""
        try:
            disk = psutil.disk_usage('/')

            # 디스크 I/O 체크
            io_counters = psutil.disk_io_counters()

            status = {
                'percent': disk.percent,
                'free_gb': disk.free / (1024**3),
                'total_gb': disk.total / (1024**3),
                'read_mb_s': io_counters.read_bytes / (1024**2),
                'write_mb_s': io_counters.write_bytes / (1024**2),
                'status': 'ok'
            }

            if disk.percent > self.health_status['disk']['threshold']:
                status['status'] = 'warning'
                self.issues.append(f"디스크 공간 부족: {disk.percent}%")
                self._cleanup_old_logs()

            self.health_status['disk']['value'] = disk.percent
            return status
        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def check_gpu(self) -> Dict:
        """GPU 상태 체크 (NVIDIA)"""
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()

            if not gpus:
                return {'status': 'not_available'}

            gpu = gpus[0]

            status = {
                'name': gpu.name,
                'memory_percent': gpu.memoryUtil * 100,
                'memory_used_mb': gpu.memoryUsed,
                'memory_total_mb': gpu.memoryTotal,
                'temperature': gpu.temperature,
                'load_percent': gpu.load * 100,
                'status': 'ok'
            }

            # 온도 체크
            if gpu.temperature > 80:
                status['status'] = 'warning'
                self.issues.append(f"GPU 온도 높음: {gpu.temperature}°C")

            if gpu.temperature > 90:
                status['status'] = 'critical'
                self._throttle_gpu_usage()

            self.health_status['gpu']['value'] = gpu.load * 100
            return status

        except ImportError:
            return {'status': 'gputil_not_installed'}
        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def check_processes(self) -> Dict:
        """프로세스 상태 체크"""
        try:
            critical_processes = {
                'streamlit': ['web_interface.py', 'streamlit', 'run'],
                'api_server': ['api_server'],
                'auto_indexer': ['auto_indexer.py']
            }

            running = {}
            zombie_count = 0
            high_memory_processes = []

            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status', 'memory_percent']):
                try:
                    # 좀비 프로세스 체크
                    if proc.info['status'] == psutil.STATUS_ZOMBIE:
                        zombie_count += 1

                    # 높은 메모리 사용 프로세스
                    if proc.info['memory_percent'] > 10:
                        high_memory_processes.append({
                            'name': proc.info['name'],
                            'pid': proc.info['pid'],
                            'memory': proc.info['memory_percent']
                        })

                    # 중요 프로세스 체크
                    cmdline_list = proc.info.get('cmdline', [])
                    if cmdline_list is None:
                        cmdline_list = []
                    cmdline = ' '.join(cmdline_list)
                    for key, patterns in critical_processes.items():
                        # 여러 패턴 중 하나라도 매치하면 실행중으로 판단
                        if any(pattern in cmdline for pattern in patterns):
                            running[key] = {
                                'pid': proc.info['pid'],
                                'status': 'running',
                                'memory': proc.info['memory_percent']
                            }

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # 실행되지 않은 중요 프로세스
            not_running = []
            for key in critical_processes:
                if key not in running:
                    not_running.append(key)
                    if self.auto_recovery_enabled:
                        self._restart_process(key)

            status = {
                'running': running,
                'not_running': not_running,
                'zombie_count': zombie_count,
                'high_memory': high_memory_processes[:5],  # 상위 5개
                'total_processes': len(list(psutil.process_iter())),
                'status': 'ok' if not not_running and zombie_count == 0 else 'warning'
            }

            if zombie_count > 5:
                status['status'] = 'critical'
                self._clean_zombie_processes()

            self.health_status['processes']['count'] = len(running)
            return status

        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def check_network(self) -> Dict:
        """네트워크 상태 체크"""
        try:
            import requests

            endpoints = {
                'web': 'http://localhost:8501',
                'api': 'http://localhost:8000/health',
                'monitor': 'http://localhost:8502'
            }

            status = {}

            for name, url in endpoints.items():
                try:
                    start = time.time()
                    response = requests.get(url, timeout=2)
                    elapsed = time.time() - start

                    status[name] = {
                        'status_code': response.status_code,
                        'response_time': round(elapsed * 1000, 2),  # ms
                        'status': 'ok' if response.status_code == 200 else 'error'
                    }

                    if elapsed > 1:  # 1초 이상
                        status[name]['status'] = 'slow'

                except requests.exceptions.RequestException as e:
                    status[name] = {
                        'status': 'offline',
                        'error': str(e)[:50]
                    }

            return status

        except ImportError:
            return {'status': 'requests_not_installed'}
        except Exception as e:
            return {'error': str(e), 'status': 'error'}

    def _trigger_memory_cleanup(self):
        """메모리 정리 트리거"""
        try:
            # Python 가비지 컬렉션
            import gc
            gc.collect()

            # 시스템 캐시 정리 (Linux)
            if sys.platform == 'linux':
                os.system('sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null')

            self.log("메모리 정리 실행")

        except Exception as e:
            self.log(f"메모리 정리 실패: {e}")

    def _cleanup_old_logs(self):
        """오래된 로그 정리"""
        try:
            logs_dir = Path("logs")
            if logs_dir.exists():
                for log_file in logs_dir.glob("*.log"):
                    # 7일 이상 된 로그 삭제
                    if time.time() - log_file.stat().st_mtime > 7 * 24 * 3600:
                        log_file.unlink()
                        self.log(f"오래된 로그 삭제: {log_file}")

        except Exception as e:
            self.log(f"로그 정리 실패: {e}")

    def _throttle_gpu_usage(self):
        """GPU 사용량 제한"""
        try:
            # GPU 메모리 제한 설정
            os.environ['CUDA_VISIBLE_DEVICES'] = '0'
            os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
            self.log("GPU 사용량 제한 적용")

        except Exception as e:
            self.log(f"GPU 제한 실패: {e}")

    def _restart_process(self, process_name: str):
        """프로세스 재시작"""
        try:
            commands = {
                'streamlit': 'nohup streamlit run web_interface.py > logs/streamlit.log 2>&1 &',
                'api_server': 'nohup python3 api_server.py > logs/api.log 2>&1 &',
                'auto_indexer': 'nohup python3 auto_indexer.py > logs/indexer.log 2>&1 &'
            }

            if process_name in commands:
                subprocess.Popen(commands[process_name], shell=True)
                self.log(f"프로세스 재시작: {process_name}")

        except Exception as e:
            self.log(f"프로세스 재시작 실패: {e}")

    def _clean_zombie_processes(self):
        """좀비 프로세스 정리"""
        try:
            os.system("ps aux | grep defunct | awk '{print $2}' | xargs kill -9 2>/dev/null")
            self.log("좀비 프로세스 정리 완료")

        except Exception as e:
            self.log(f"좀비 프로세스 정리 실패: {e}")

    def log(self, message: str):
        """로그 기록"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        with open(self.log_file, 'a') as f:
            f.write(log_entry)

        print(f"{CYAN}[MONITOR]{RESET} {message}")

    def get_health_summary(self) -> Dict:
        """전체 헬스 요약"""
        cpu = self.check_cpu()
        memory = self.check_memory()
        disk = self.check_disk()
        gpu = self.check_gpu()
        processes = self.check_processes()
        network = self.check_network()

        # 전체 상태 판단
        overall_status = 'healthy'

        if any(s.get('status') == 'warning' for s in [cpu, memory, disk, gpu, processes]):
            overall_status = 'warning'

        if any(s.get('status') in ['critical', 'error'] for s in [cpu, memory, disk, gpu, processes]):
            overall_status = 'critical'

        return {
            'timestamp': datetime.now().isoformat(),
            'overall_status': overall_status,
            'cpu': cpu,
            'memory': memory,
            'disk': disk,
            'gpu': gpu,
            'processes': processes,
            'network': network,
            'issues': self.issues[-10:],  # 최근 10개 이슈
            'auto_recovery': self.auto_recovery_enabled
        }

    def print_status(self):
        """상태 출력"""
        health = self.get_health_summary()

        # 상태별 색상
        status_colors = {
            'healthy': GREEN,
            'warning': YELLOW,
            'critical': RED
        }

        color = status_colors.get(health['overall_status'], RESET)

        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}🏥 System Health Monitor{RESET}")
        print(f"{'='*60}")
        print(f"⏰ {health['timestamp']}")
        print(f"📊 Overall Status: {color}{health['overall_status'].upper()}{RESET}")
        print()

        # CPU
        cpu_status = health['cpu']
        if 'percent' in cpu_status:
            cpu_color = GREEN if cpu_status['percent'] < 70 else YELLOW if cpu_status['percent'] < 90 else RED
            print(f"🖥️  CPU: {cpu_color}{cpu_status['percent']:.1f}%{RESET} ({cpu_status['cores']} cores)")

        # Memory
        mem_status = health['memory']
        if 'ram_percent' in mem_status:
            mem_color = GREEN if mem_status['ram_percent'] < 70 else YELLOW if mem_status['ram_percent'] < 85 else RED
            print(f"🧠 Memory: {mem_color}{mem_status['ram_percent']:.1f}%{RESET} ({mem_status['ram_available_gb']:.1f}GB available)")

        # Disk
        disk_status = health['disk']
        if 'percent' in disk_status:
            disk_color = GREEN if disk_status['percent'] < 80 else YELLOW if disk_status['percent'] < 90 else RED
            print(f"💾 Disk: {disk_color}{disk_status['percent']:.1f}%{RESET} ({disk_status['free_gb']:.1f}GB free)")

        # GPU
        gpu_status = health['gpu']
        if 'load_percent' in gpu_status:
            gpu_color = GREEN if gpu_status['load_percent'] < 70 else YELLOW if gpu_status['load_percent'] < 90 else RED
            print(f"🎮 GPU: {gpu_color}{gpu_status['load_percent']:.1f}%{RESET} ({gpu_status['temperature']}°C)")

        # Processes
        proc_status = health['processes']
        if 'running' in proc_status:
            print(f"\n📋 Critical Processes:")
            for name, info in proc_status['running'].items():
                print(f"   ✅ {name}: PID {info['pid']} (Memory: {info['memory']:.1f}%)")
            for name in proc_status.get('not_running', []):
                print(f"   ❌ {name}: NOT RUNNING")

        # Network
        net_status = health['network']
        if net_status:
            print(f"\n🌐 Service Status:")
            for name, info in net_status.items():
                if info.get('status') == 'ok':
                    print(f"   ✅ {name}: {info['response_time']}ms")
                elif info.get('status') == 'slow':
                    print(f"   {YELLOW}⚠️  {name}: SLOW ({info['response_time']}ms){RESET}")
                else:
                    print(f"   {RED}❌ {name}: OFFLINE{RESET}")

        # Issues
        if health['issues']:
            print(f"\n{YELLOW}⚠️  Recent Issues:{RESET}")
            for issue in health['issues'][-3:]:
                print(f"   • {issue}")

        print(f"\n🔧 Auto Recovery: {'ON' if health['auto_recovery'] else 'OFF'}")
        print(f"{'='*60}\n")

    def run_monitoring(self, interval: int = 30):
        """모니터링 실행"""
        self.log("헬스 모니터링 시작")

        while self.running:
            try:
                self.issues = []  # 이슈 초기화
                self.print_status()

                # 헬스 데이터 저장
                health = self.get_health_summary()
                with open('logs/health_history.json', 'a') as f:
                    f.write(json.dumps(health) + '\n')

                time.sleep(interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"모니터링 오류: {e}")
                time.sleep(5)

        self.log("헬스 모니터링 종료")

    def stop(self):
        """모니터링 중지"""
        self.running = False


def signal_handler(signum, frame):
    """시그널 핸들러"""
    print(f"\n{YELLOW}모니터링을 종료합니다...{RESET}")
    monitor.stop()
    sys.exit(0)


if __name__ == "__main__":
    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"{BOLD}{CYAN}🏥 AI-CHAT System Health Monitor{RESET}")
    print(f"{CYAN}세심한 디테일까지 관리하는 스마트 모니터{RESET}")
    print("="*60)

    monitor = SystemHealthMonitor()

    # 인터벌 설정
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=30, help='모니터링 간격 (초)')
    parser.add_argument('--auto-recovery', action='store_true', help='자동 복구 활성화')
    args = parser.parse_args()

    if args.auto_recovery:
        monitor.auto_recovery_enabled = True
        print(f"{GREEN}✅ 자동 복구 모드 활성화{RESET}")

    monitor.run_monitoring(interval=args.interval)