#!/usr/bin/env python3
"""메타데이터 품질 실시간 모니터링 대시보드

Streamlit 기반 메타데이터 품질 및 동기화 상태 실시간 모니터링
"""

import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
from pathlib import Path
import pickle
from typing import Dict, List, Tuple

# 페이지 설정
st.set_page_config(
    page_title="메타데이터 품질 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일
st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .alert-box {
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .alert-warning {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
    }
    .alert-danger {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
    }
    .alert-success {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)  # 1분 캐시
def load_database_stats() -> Dict:
    """DB 통계 로드"""
    conn = sqlite3.connect('metadata.db')

    # 전체 통계
    stats = {}

    # 전체 문서 수
    cursor = conn.execute("SELECT COUNT(*) FROM documents")
    stats['total_docs'] = cursor.fetchone()[0]

    # 기안자 누락
    cursor = conn.execute("""
        SELECT COUNT(*) FROM documents
        WHERE drafter IS NULL OR drafter = ''
    """)
    stats['missing_drafters'] = cursor.fetchone()[0]

    # 카테고리 누락
    cursor = conn.execute("""
        SELECT COUNT(*) FROM documents
        WHERE category IS NULL OR category = ''
    """)
    stats['missing_category'] = cursor.fetchone()[0]

    # 날짜 문제
    cursor = conn.execute("""
        SELECT COUNT(*) FROM documents
        WHERE date IS NULL OR date = ''
        OR date NOT LIKE '20__-__-__'
    """)
    stats['date_issues'] = cursor.fetchone()[0]

    # 연도별 분포
    df_yearly = pd.read_sql_query("""
        SELECT SUBSTR(filename, 1, 4) as year,
               COUNT(*) as total,
               SUM(CASE WHEN drafter IS NULL OR drafter = '' THEN 1 ELSE 0 END) as missing_drafter,
               SUM(CASE WHEN category IS NULL OR category = '' THEN 1 ELSE 0 END) as missing_category
        FROM documents
        GROUP BY year
        ORDER BY year
    """, conn)
    stats['yearly_dist'] = df_yearly

    # 카테고리 분포
    df_category = pd.read_sql_query("""
        SELECT category, COUNT(*) as count
        FROM documents
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY count DESC
        LIMIT 10
    """, conn)
    stats['category_dist'] = df_category

    # 기안자 통계
    df_drafter = pd.read_sql_query("""
        SELECT drafter, COUNT(*) as doc_count
        FROM documents
        WHERE drafter IS NOT NULL AND drafter != ''
        GROUP BY drafter
        ORDER BY doc_count DESC
        LIMIT 10
    """, conn)
    stats['top_drafters'] = df_drafter

    conn.close()
    return stats

@st.cache_data(ttl=60)
def check_index_sync() -> Tuple[bool, Dict]:
    """인덱스 동기화 상태 확인"""
    # DB 문서 수
    conn = sqlite3.connect('metadata.db')
    cursor = conn.execute("SELECT COUNT(*) FROM documents")
    db_count = cursor.fetchone()[0]

    cursor = conn.execute("SELECT filename FROM documents")
    db_files = set(row[0] for row in cursor.fetchall())
    conn.close()

    # BM25 인덱스 문서 수
    index_count = 0
    index_files = set()

    try:
        with open('var/index/bm25_index.pkl', 'rb') as f:
            idx = pickle.load(f)
            if 'metadata' in idx:
                index_count = len(idx['metadata'])
                for meta in idx['metadata']:
                    if isinstance(meta, dict) and 'filename' in meta:
                        index_files.add(meta['filename'])
    except:
        pass

    # 동기화 상태
    is_synced = (db_count == index_count) and (db_files == index_files)

    sync_info = {
        'db_count': db_count,
        'index_count': index_count,
        'is_synced': is_synced,
        'only_in_db': len(db_files - index_files),
        'only_in_index': len(index_files - db_files)
    }

    return is_synced, sync_info

def load_latest_validation_report() -> Dict:
    """최신 검증 보고서 로드"""
    try:
        report_path = Path('reports/metadata/latest.json')
        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def calculate_health_score(stats: Dict) -> float:
    """전체 건강도 점수 계산 (0-100)"""
    score = 100.0

    # 기안자 누락 (최대 -30점)
    drafter_missing_rate = stats['missing_drafters'] / max(stats['total_docs'], 1)
    score -= min(30, drafter_missing_rate * 100)

    # 카테고리 누락 (최대 -20점)
    category_missing_rate = stats['missing_category'] / max(stats['total_docs'], 1)
    score -= min(20, category_missing_rate * 50)

    # 날짜 문제 (최대 -10점)
    date_issue_rate = stats['date_issues'] / max(stats['total_docs'], 1)
    score -= min(10, date_issue_rate * 100)

    # 동기화 문제 (최대 -20점)
    is_synced, sync_info = check_index_sync()
    if not is_synced:
        score -= 20

    return max(0, score)

def main():
    # 헤더
    st.title("📊 메타데이터 품질 모니터링 대시보드")
    st.markdown("실시간 메타데이터 품질 및 동기화 상태 모니터링")

    # 새로고침 버튼
    col1, col2, col3 = st.columns([1, 1, 8])
    with col1:
        if st.button("🔄 새로고침"):
            st.cache_data.clear()
            st.rerun()
    with col2:
        auto_refresh = st.checkbox("자동 새로고침", value=False)

    if auto_refresh:
        st.write("60초마다 자동 새로고침")
        st.empty()  # Placeholder for auto-refresh

    # 데이터 로드
    stats = load_database_stats()
    is_synced, sync_info = check_index_sync()
    health_score = calculate_health_score(stats)
    report = load_latest_validation_report()

    # 1. 핵심 지표 (상단)
    st.markdown("## 📈 핵심 지표")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            label="전체 문서",
            value=f"{stats['total_docs']:,}",
            delta=None
        )

    with col2:
        drafter_rate = (1 - stats['missing_drafters']/max(stats['total_docs'], 1)) * 100
        st.metric(
            label="기안자 완성도",
            value=f"{drafter_rate:.1f}%",
            delta=f"-{stats['missing_drafters']}개 누락",
            delta_color="inverse"
        )

    with col3:
        category_rate = (1 - stats['missing_category']/max(stats['total_docs'], 1)) * 100
        st.metric(
            label="카테고리 완성도",
            value=f"{category_rate:.1f}%",
            delta=f"-{stats['missing_category']}개 누락",
            delta_color="inverse"
        )

    with col4:
        st.metric(
            label="동기화 상태",
            value="✅ 정상" if is_synced else "⚠️ 불일치",
            delta=f"DB: {sync_info['db_count']} / Index: {sync_info['index_count']}"
        )

    with col5:
        health_color = "🟢" if health_score >= 80 else "🟡" if health_score >= 60 else "🔴"
        st.metric(
            label="전체 건강도",
            value=f"{health_color} {health_score:.1f}",
            delta=None
        )

    # 2. 알림 섹션
    st.markdown("## 🚨 알림")

    alerts = []

    # 기안자 누락 알림
    if stats['missing_drafters'] / max(stats['total_docs'], 1) > 0.2:
        alerts.append({
            'level': 'danger',
            'title': '기안자 누락률 높음',
            'message': f"{stats['missing_drafters']}개 문서 ({stats['missing_drafters']/stats['total_docs']*100:.1f}%)의 기안자가 누락되어 있습니다.",
            'action': 'scripts/fix_missing_drafters.py 실행 권장'
        })
    elif stats['missing_drafters'] / max(stats['total_docs'], 1) > 0.1:
        alerts.append({
            'level': 'warning',
            'title': '기안자 누락 주의',
            'message': f"{stats['missing_drafters']}개 문서의 기안자 확인 필요",
            'action': '주간 복구 스크립트 실행 예정'
        })

    # 동기화 알림
    if not is_synced:
        alerts.append({
            'level': 'danger',
            'title': 'DB-인덱스 불일치',
            'message': f"DB: {sync_info['db_count']}개, Index: {sync_info['index_count']}개",
            'action': 'scripts/reindex_atomic.py 즉시 실행 필요'
        })

    # 최근 검증 보고서의 권장사항
    if report and 'recommendations' in report:
        for rec in report['recommendations']:
            if rec['priority'] == 'HIGH':
                alerts.append({
                    'level': 'warning',
                    'title': f"권장사항: {rec['issue']}",
                    'message': rec.get('impact', ''),
                    'action': rec.get('action', '')
                })

    if alerts:
        for alert in alerts:
            alert_class = f"alert-{alert['level']}"
            st.markdown(f"""
                <div class="alert-box {alert_class}">
                    <strong>{alert['title']}</strong><br>
                    {alert['message']}<br>
                    <small>조치: {alert['action']}</small>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ 모든 지표 정상")

    # 3. 차트 섹션
    st.markdown("## 📊 상세 분석")

    tab1, tab2, tab3, tab4 = st.tabs(["연도별 추이", "카테고리 분포", "기안자 통계", "실시간 로그"])

    with tab1:
        # 연도별 추이
        df_yearly = stats['yearly_dist']
        if not df_yearly.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(name='전체', x=df_yearly['year'], y=df_yearly['total']))
            fig.add_trace(go.Bar(name='기안자 누락', x=df_yearly['year'], y=df_yearly['missing_drafter']))
            fig.add_trace(go.Bar(name='카테고리 누락', x=df_yearly['year'], y=df_yearly['missing_category']))
            fig.update_layout(
                title="연도별 문서 및 누락 현황",
                barmode='group',
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

            # 문제가 많은 연도 하이라이트
            problem_years = df_yearly[df_yearly['missing_drafter'] > df_yearly['total'] * 0.3]
            if not problem_years.empty:
                st.warning(f"⚠️ {', '.join(problem_years['year'].astype(str))}년 문서의 기안자 누락률이 30% 이상입니다.")

    with tab2:
        # 카테고리 분포
        df_category = stats['category_dist']
        if not df_category.empty:
            fig = px.pie(
                df_category,
                values='count',
                names='category',
                title="카테고리별 문서 분포"
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)

            # 카테고리 테이블
            st.dataframe(df_category, use_container_width=True)

    with tab3:
        # 기안자 통계
        df_drafter = stats['top_drafters']
        if not df_drafter.empty:
            fig = px.bar(
                df_drafter,
                x='doc_count',
                y='drafter',
                orientation='h',
                title="상위 10명 기안자별 문서 수"
            )
            st.plotly_chart(fig, use_container_width=True)

            # 통계 요약
            col1, col2 = st.columns(2)
            with col1:
                st.metric("총 기안자 수", len(df_drafter))
            with col2:
                st.metric("평균 문서/기안자", f"{df_drafter['doc_count'].mean():.1f}")

    with tab4:
        # 실시간 로그
        st.markdown("### 📝 최근 작업 로그")

        log_files = {
            'daily.log': '일일 검증',
            'weekly.log': '주간 복구',
            'monthly.log': '월간 분석'
        }

        selected_log = st.selectbox("로그 선택", list(log_files.keys()))

        log_path = Path(f'logs/cron/{selected_log}')
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 최근 50줄만 표시
                recent_lines = lines[-50:] if len(lines) > 50 else lines
                st.text_area(
                    f"{log_files[selected_log]} 로그",
                    value=''.join(recent_lines),
                    height=400
                )
        else:
            st.info("로그 파일이 아직 생성되지 않았습니다.")

    # 4. 사이드바 - 빠른 작업
    with st.sidebar:
        st.markdown("## ⚡ 빠른 작업")

        if st.button("🔍 메타데이터 검증"):
            st.info("scripts/validate_metadata.py 실행 중...")
            # 실제 실행 코드 추가 가능

        if st.button("🔧 기안자 복구"):
            st.info("scripts/fix_missing_drafters.py 실행 중...")

        if st.button("📂 카테고리 재분류"):
            st.info("scripts/auto_categorize_documents.py 실행 중...")

        if st.button("🔄 인덱스 재생성"):
            st.info("scripts/reindex_atomic.py 실행 중...")

        st.markdown("---")

        # 최근 검증 정보
        st.markdown("## 📅 최근 검증")
        if report:
            timestamp = report.get('timestamp', 'N/A')
            if timestamp != 'N/A':
                dt = datetime.fromisoformat(timestamp)
                st.write(f"시간: {dt.strftime('%Y-%m-%d %H:%M')}")

                summary = report.get('summary', {})
                st.write(f"전체: {summary.get('total_documents', 0)}개")
                st.write(f"문제: {summary.get('missing_drafters', 0)}개")
                st.write(f"권장사항: {len(report.get('recommendations', []))}개")

        st.markdown("---")

        # 시스템 정보
        st.markdown("## ℹ️ 시스템 정보")
        st.write(f"DB 경로: metadata.db")
        st.write(f"인덱스: var/index/bm25_index.pkl")
        st.write(f"로그: logs/cron/")

if __name__ == "__main__":
    main()