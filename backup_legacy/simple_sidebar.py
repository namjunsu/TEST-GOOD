#!/usr/bin/env python3
"""
심플한 사이드바 - 한눈에 보는 리스트형
"""

import streamlit as st
import pandas as pd

def render_simple_sidebar():
    """초심플 사이드바 예시"""

    # 스타일 정의
    st.markdown("""
    <style>
    /* 컴팩트 테이블 스타일 */
    .simple-table {
        width: 100%;
        font-size: 11px;
        border-collapse: collapse;
    }
    .simple-table tr {
        border-bottom: 1px solid #f0f0f0;
        cursor: pointer;
    }
    .simple-table tr:hover {
        background: #f5f5f5;
    }
    .simple-table td {
        padding: 2px 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .type-badge {
        display: inline-block;
        width: 20px;
        text-align: center;
        font-weight: bold;
        font-size: 10px;
        border-radius: 2px;
        padding: 1px 2px;
    }
    .type-purchase { background: #e3f2fd; color: #1976d2; }
    .type-repair { background: #fff3e0; color: #f57c00; }
    .type-disposal { background: #ffebee; color: #c62828; }
    .type-other { background: #f5f5f5; color: #616161; }
    </style>
    """, unsafe_allow_html=True)

    # 가상의 데이터
    data = {
        '2024': [
            ('구', '11-15', '중계차 노후 보수건'),
            ('수', '11-14', '지미집 Control Box 수리'),
            ('구', '10-24', '방송시스템 소모품 구매'),
            ('검', '09-12', '조명 소모품 구매 건'),
            ('폐', '08-13', '불용 방송 장비 폐기'),
        ],
        '2023': [
            ('구', '07-11', '광화문 방송모니터 수리'),
            ('구', '06-24', '광화문 소모품 구매'),
            ('수', '05-04', 'DVR 교체 검토의 건'),
        ],
        '2022': [
            ('구', '12-21', '월모니터 고장 수리'),
            ('구', '10-20', '채널A 월모니터 구매'),
            ('검', '02-03', 'NLE 워크스테이션 교체'),
        ]
    }

    # 실제로는 이렇게 사용
    return """
    ### 📁 문서 라이브러리 (224개)

    🔍 [검색창]

    #### 2024년 (30개)
    구 11-15 중계차 노후 보수건
    수 11-14 지미집 Control Box 수리
    구 10-24 방송시스템 소모품 구매
    검 09-12 조명 소모품 구매 건
    폐 08-13 불용 방송 장비 폐기

    #### 2023년 (50개)
    구 07-11 광화문 방송모니터 수리
    구 06-24 광화문 소모품 구매
    수 05-04 DVR 교체 검토의 건

    #### 2022년 (40개)
    구 12-21 월모니터 고장 수리
    구 10-20 채널A 월모니터 구매
    검 02-03 NLE 워크스테이션 교체
    ...
    """

# 실제 적용할 심플 버전
def apply_simple_list_style():
    """web_interface.py에 적용할 스타일"""
    return """
    # 더 심플한 버전 - 텍스트 리스트처럼

    for year in sorted(filtered_df['year'].unique(), reverse=True):
        year_docs = filtered_df[filtered_df['year'] == year]

        # 연도 헤더만
        st.markdown(f"**{year}년** ({len(year_docs)}개)")

        # 심플한 텍스트 리스트
        doc_list = ""
        for idx, row in year_docs.head(50).iterrows():  # 연도당 최대 50개
            type_char = row['category'][:1]  # 첫 글자만
            date = row['date'][5:]  # MM-DD
            title = row['title'][:30]  # 30자까지

            doc_list += f"{type_char} {date} {title}\\n"

        # 클릭 가능한 영역으로
        st.text(doc_list)
    """