"""
Performance Alerting System
임계값 기반 알림
"""

from typing import Dict, List, Callable
import smtplib
from email.mime.text import MIMEText
import logging

logger = logging.getLogger(__name__)

class AlertManager:
    """알림 관리자"""

    def __init__(self):
        self.thresholds = {
            'cpu_percent': 80,
            'memory_percent': 85,
            'error_rate': 0.1,
            'response_time_ms': 1000
        }
        self.alert_history = []
        self.alert_callbacks = []

    def check_thresholds(self, metrics: Dict):
        """임계값 확인"""
        alerts = []

        # CPU 체크
        cpu = metrics.get('system', {}).get('cpu_percent', 0)
        if cpu > self.thresholds['cpu_percent']:
            alerts.append({
                'level': 'WARNING',
                'metric': 'cpu_percent',
                'value': cpu,
                'threshold': self.thresholds['cpu_percent'],
                'message': f'CPU usage high: {cpu:.1f}%'
            })

        # 메모리 체크
        mem = metrics.get('system', {}).get('memory_percent', 0)
        if mem > self.thresholds['memory_percent']:
            alerts.append({
                'level': 'WARNING',
                'metric': 'memory_percent',
                'value': mem,
                'threshold': self.thresholds['memory_percent'],
                'message': f'Memory usage high: {mem:.1f}%'
            })

        # 알림 처리
        for alert in alerts:
            self._handle_alert(alert)

        return alerts

    def _handle_alert(self, alert: Dict):
        """알림 처리"""
        # 히스토리 기록
        self.alert_history.append({
            'timestamp': datetime.now(),
            **alert
        })

        # 콜백 실행
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        # 로그 출력
        logger.warning(f"ALERT: {alert['message']}")

    def add_callback(self, callback: Callable):
        """알림 콜백 추가"""
        self.alert_callbacks.append(callback)

    def get_alert_summary(self) -> Dict:
        """알림 요약"""
        if not self.alert_history:
            return {'total': 0}

        return {
            'total': len(self.alert_history),
            'by_level': self._count_by_level(),
            'by_metric': self._count_by_metric(),
            'recent': self.alert_history[-10:]
        }

    def _count_by_level(self) -> Dict:
        """레벨별 카운트"""
        counts = {}
        for alert in self.alert_history:
            level = alert['level']
            counts[level] = counts.get(level, 0) + 1
        return counts

    def _count_by_metric(self) -> Dict:
        """메트릭별 카운트"""
        counts = {}
        for alert in self.alert_history:
            metric = alert['metric']
            counts[metric] = counts.get(metric, 0) + 1
        return counts

# 전역 알림 관리자
alert_manager = AlertManager()
