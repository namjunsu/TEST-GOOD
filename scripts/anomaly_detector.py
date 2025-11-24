#!/usr/bin/env python3
"""메타데이터 이상 감지 및 알림 시스템

메타데이터 품질 이상을 감지하고 알림을 발송합니다.
"""

import sqlite3
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import os
import pickle

class AnomalyDetector:
    """메타데이터 이상 감지기"""

    def __init__(self, config_path: str = 'config/alerts.json'):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.thresholds = self.config.get('thresholds', {})
        self.last_alert_file = Path('var/last_alert.json')
        self.alert_history = self._load_alert_history()

    def _load_config(self) -> Dict:
        """알림 설정 로드"""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        else:
            # 기본 설정
            return {
                'thresholds': {
                    'drafter_missing_rate': 0.2,  # 20% 이상
                    'category_missing_rate': 0.5,  # 50% 이상
                    'sync_diff_count': 10,  # 10개 이상 불일치
                    'health_score': 60  # 60점 이하
                },
                'cooldown_hours': 24,  # 동일 알림 재발송 방지 (24시간)
                'enabled': True
            }

    def _load_alert_history(self) -> Dict:
        """이전 알림 기록 로드"""
        if self.last_alert_file.exists():
            with open(self.last_alert_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_alert_history(self):
        """알림 기록 저장"""
        self.last_alert_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.last_alert_file, 'w') as f:
            json.dump(self.alert_history, f, indent=2)

    def detect_anomalies(self) -> List[Dict]:
        """이상 감지"""
        anomalies = []

        # 1. DB 통계 확인
        conn = sqlite3.connect('metadata.db')
        cursor = conn.cursor()

        # 전체 문서 수
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]

        # 기안자 누락
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE drafter IS NULL OR drafter = ''
        """)
        missing_drafters = cursor.fetchone()[0]
        drafter_missing_rate = missing_drafters / max(total_docs, 1)

        if drafter_missing_rate > self.thresholds['drafter_missing_rate']:
            anomalies.append({
                'type': 'drafter_missing_high',
                'severity': 'high',
                'title': '기안자 누락률 높음',
                'message': f"기안자 누락률: {drafter_missing_rate*100:.1f}% ({missing_drafters}/{total_docs})",
                'value': drafter_missing_rate,
                'threshold': self.thresholds['drafter_missing_rate'],
                'action': 'scripts/fix_missing_drafters.py 실행 필요'
            })

        # 카테고리 누락
        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE category IS NULL OR category = ''
        """)
        missing_category = cursor.fetchone()[0]
        category_missing_rate = missing_category / max(total_docs, 1)

        if category_missing_rate > self.thresholds['category_missing_rate']:
            anomalies.append({
                'type': 'category_missing_high',
                'severity': 'medium',
                'title': '카테고리 누락률 높음',
                'message': f"카테고리 누락률: {category_missing_rate*100:.1f}% ({missing_category}/{total_docs})",
                'value': category_missing_rate,
                'threshold': self.thresholds['category_missing_rate'],
                'action': 'scripts/auto_categorize_documents.py 실행 필요'
            })

        conn.close()

        # 2. 동기화 상태 확인
        sync_anomaly = self._check_sync_status()
        if sync_anomaly:
            anomalies.append(sync_anomaly)

        # 3. 건강도 점수 확인
        health_score = self._calculate_health_score(
            total_docs, missing_drafters, missing_category
        )

        if health_score < self.thresholds['health_score']:
            anomalies.append({
                'type': 'health_score_low',
                'severity': 'high',
                'title': '전체 건강도 낮음',
                'message': f"메타데이터 건강도: {health_score:.1f}/100",
                'value': health_score,
                'threshold': self.thresholds['health_score'],
                'action': '전체 메타데이터 점검 필요'
            })

        # 4. 급격한 변화 감지
        sudden_changes = self._detect_sudden_changes()
        anomalies.extend(sudden_changes)

        return anomalies

    def _check_sync_status(self) -> Optional[Dict]:
        """동기화 상태 확인"""
        # DB 문서 수
        conn = sqlite3.connect('metadata.db')
        cursor = conn.execute("SELECT COUNT(*) FROM documents")
        db_count = cursor.fetchone()[0]
        conn.close()

        # 인덱스 문서 수
        index_count = 0
        try:
            with open('var/index/bm25_index.pkl', 'rb') as f:
                idx = pickle.load(f)
                if 'metadata' in idx:
                    index_count = len(idx['metadata'])
        except:
            pass

        diff = abs(db_count - index_count)
        if diff > self.thresholds['sync_diff_count']:
            return {
                'type': 'sync_mismatch',
                'severity': 'critical',
                'title': 'DB-인덱스 동기화 불일치',
                'message': f"DB: {db_count}개, Index: {index_count}개 (차이: {diff}개)",
                'value': diff,
                'threshold': self.thresholds['sync_diff_count'],
                'action': 'scripts/reindex_atomic.py 즉시 실행 필요'
            }
        return None

    def _calculate_health_score(self, total: int, missing_drafters: int, missing_category: int) -> float:
        """건강도 점수 계산"""
        score = 100.0
        score -= (missing_drafters / max(total, 1)) * 40
        score -= (missing_category / max(total, 1)) * 30
        return max(0, score)

    def _detect_sudden_changes(self) -> List[Dict]:
        """급격한 변화 감지"""
        anomalies = []

        # 최근 검증 보고서와 비교
        try:
            current_report_path = Path('reports/metadata/latest.json')
            if current_report_path.exists():
                with open(current_report_path, 'r') as f:
                    current = json.load(f)

                # 이전 보고서 찾기
                reports_dir = Path('reports/metadata')
                report_files = sorted(reports_dir.glob('metadata_validation_*.json'))
                if len(report_files) >= 2:
                    with open(report_files[-2], 'r') as f:
                        previous = json.load(f)

                    # 기안자 누락 급증
                    curr_missing = current['summary'].get('missing_drafters', 0)
                    prev_missing = previous['summary'].get('missing_drafters', 0)

                    if curr_missing > prev_missing * 1.5 and curr_missing - prev_missing > 10:
                        anomalies.append({
                            'type': 'sudden_increase_missing',
                            'severity': 'medium',
                            'title': '기안자 누락 급증',
                            'message': f"기안자 누락: {prev_missing} → {curr_missing} (+{curr_missing-prev_missing})",
                            'value': curr_missing - prev_missing,
                            'threshold': prev_missing * 1.5,
                            'action': '최근 변경사항 확인 필요'
                        })
        except Exception as e:
            print(f"급격한 변화 감지 실패: {e}")

        return anomalies

    def should_send_alert(self, anomaly: Dict) -> bool:
        """알림 발송 여부 결정 (쿨다운 체크)"""
        alert_key = anomaly['type']
        last_sent = self.alert_history.get(alert_key)

        if last_sent:
            last_time = datetime.fromisoformat(last_sent)
            hours_passed = (datetime.now() - last_time).total_seconds() / 3600
            if hours_passed < self.config.get('cooldown_hours', 24):
                return False

        return True

    def send_alerts(self, anomalies: List[Dict]):
        """알림 발송"""
        if not anomalies:
            return

        # 심각도별 분류
        critical = [a for a in anomalies if a['severity'] == 'critical']
        high = [a for a in anomalies if a['severity'] == 'high']
        medium = [a for a in anomalies if a['severity'] == 'medium']

        # 알림 메시지 구성
        message = self._format_alert_message(critical, high, medium)

        # 발송할 이상 항목 필터링 (쿨다운 적용)
        to_send = [a for a in anomalies if self.should_send_alert(a)]

        if not to_send:
            print("모든 알림이 쿨다운 중입니다.")
            return

        # 콘솔 출력
        print("\n" + "=" * 60)
        print("🚨 메타데이터 이상 감지")
        print("=" * 60)
        print(message)

        # Slack 알림 (설정된 경우)
        if self.config.get('slack_webhook'):
            self._send_slack_alert(message, to_send)

        # 이메일 알림 (설정된 경우)
        if self.config.get('email'):
            self._send_email_alert(message, to_send)

        # 알림 기록 업데이트
        for anomaly in to_send:
            self.alert_history[anomaly['type']] = datetime.now().isoformat()
        self._save_alert_history()

    def _format_alert_message(self, critical: List, high: List, medium: List) -> str:
        """알림 메시지 포맷팅"""
        lines = []

        if critical:
            lines.append("🔴 **심각 (Critical)**")
            for a in critical:
                lines.append(f"  - {a['title']}: {a['message']}")
                lines.append(f"    조치: {a['action']}")

        if high:
            lines.append("\n🟠 **높음 (High)**")
            for a in high:
                lines.append(f"  - {a['title']}: {a['message']}")
                lines.append(f"    조치: {a['action']}")

        if medium:
            lines.append("\n🟡 **중간 (Medium)**")
            for a in medium:
                lines.append(f"  - {a['title']}: {a['message']}")
                lines.append(f"    조치: {a['action']}")

        lines.append(f"\n시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"시스템: AI-CHAT 메타데이터 모니터링")

        return "\n".join(lines)

    def _send_slack_alert(self, message: str, anomalies: List[Dict]):
        """Slack 웹훅으로 알림 발송"""
        webhook_url = self.config.get('slack_webhook')
        if not webhook_url:
            return

        try:
            # Slack 블록 메시지 구성
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 메타데이터 이상 감지"
                    }
                }
            ]

            for anomaly in anomalies:
                emoji = "🔴" if anomaly['severity'] == 'critical' else "🟠" if anomaly['severity'] == 'high' else "🟡"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{anomaly['title']}*\n{anomaly['message']}\n_조치: {anomaly['action']}_"
                    }
                })

            payload = {"blocks": blocks}
            response = requests.post(webhook_url, json=payload)
            if response.status_code == 200:
                print("✅ Slack 알림 발송 완료")
            else:
                print(f"❌ Slack 알림 실패: {response.status_code}")
        except Exception as e:
            print(f"Slack 알림 오류: {e}")

    def _send_email_alert(self, message: str, anomalies: List[Dict]):
        """이메일 알림 발송"""
        email_config = self.config.get('email', {})
        if not email_config:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = email_config['from']
            msg['To'] = email_config['to']
            msg['Subject'] = f"[AI-CHAT] 메타데이터 이상 감지 - {datetime.now().strftime('%Y-%m-%d')}"

            # HTML 본문 생성
            html_body = self._format_email_html(anomalies)
            msg.attach(MIMEText(html_body, 'html'))

            # SMTP 발송
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
                print("✅ 이메일 알림 발송 완료")
        except Exception as e:
            print(f"이메일 알림 오류: {e}")

    def _format_email_html(self, anomalies: List[Dict]) -> str:
        """이메일 HTML 포맷팅"""
        html = """
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #d9534f;">🚨 메타데이터 이상 감지</h2>
            <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse;">
                <tr style="background-color: #f5f5f5;">
                    <th>심각도</th>
                    <th>문제</th>
                    <th>상세</th>
                    <th>조치</th>
                </tr>
        """

        for anomaly in anomalies:
            color = "#d9534f" if anomaly['severity'] == 'critical' else "#f0ad4e" if anomaly['severity'] == 'high' else "#f0ad4e"
            html += f"""
                <tr>
                    <td style="color: {color}; font-weight: bold;">{anomaly['severity'].upper()}</td>
                    <td>{anomaly['title']}</td>
                    <td>{anomaly['message']}</td>
                    <td>{anomaly['action']}</td>
                </tr>
            """

        html += f"""
            </table>
            <p style="margin-top: 20px; color: #666;">
                <small>
                    시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                    시스템: AI-CHAT 메타데이터 모니터링
                </small>
            </p>
        </body>
        </html>
        """
        return html

def main():
    """메인 실행"""
    detector = AnomalyDetector()

    # 이상 감지
    anomalies = detector.detect_anomalies()

    if anomalies:
        print(f"🚨 {len(anomalies)}개 이상 감지됨")
        detector.send_alerts(anomalies)
    else:
        print("✅ 모든 지표 정상")

    # 상태 저장
    status = {
        'last_check': datetime.now().isoformat(),
        'anomalies_found': len(anomalies),
        'anomalies': anomalies
    }

    status_file = Path('var/anomaly_status.json')
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)

if __name__ == "__main__":
    main()