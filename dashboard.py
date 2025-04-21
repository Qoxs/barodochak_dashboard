import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os

# 페이지 설정
st.set_page_config(page_title="배달 통계 대시보드", layout="wide")

# 스타일 설정
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# 데이터 처리 함수
@st.cache_data
def load_data():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    df = pd.read_excel(os.path.join(current_dir, 'order_raw.xlsx'))
    
    # 필요한 컬럼만 사용
    df = df[['datetime', 'order_id', 'event_type', 'datetime_simple']]
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # 시간대 구분
    def get_time_period(hour):
        if 10 <= hour < 15:
            return 'lunch'
        elif 17 <= hour < 22:
            return 'dinner'
        else:
            return 'other'
    
    df['time_period'] = df['datetime'].dt.hour.apply(get_time_period)
    df = df[df['time_period'] != 'other']
    
    # 주문별 통계 계산
    order_group = df[df['event_type'].isin(['주문 접수', '배달 완료'])].pivot_table(
        index=['order_id', 'datetime_simple', 'time_period'],
        columns='event_type',
        values='datetime',
        aggfunc='min'
    ).reset_index()
    
    order_group['delivery_seconds'] = (
        order_group['배달 완료'] - order_group['주문 접수']
    ).dt.total_seconds()
    
    # 10분 이내, 30분 이상 주문 필터링
    order_10min = order_group[order_group['delivery_seconds'] <= 600]
    order_30min = order_group[order_group['delivery_seconds'] >= 1800]
    
    # 통계 계산
    order_count = order_group.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='total_orders')
    fast_count = order_10min.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='under_10min_orders')
    slow_count = order_30min.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='over_30min_orders')
    
    time_stats = order_group.groupby(['datetime_simple', 'time_period'])['delivery_seconds'].agg(['mean', 'min', 'max']).reset_index()
    time_stats['avg_delivery_minutes'] = (time_stats['mean'] / 60).round(2)
    time_stats['min_delivery_minutes'] = (time_stats['min'] / 60).round(2)
    time_stats['max_delivery_minutes'] = (time_stats['max'] / 60).round(2)
    
    # 결과 병합
    result = pd.merge(order_count, fast_count, on=['datetime_simple', 'time_period'], how='left')
    result = pd.merge(result, slow_count, on=['datetime_simple', 'time_period'], how='left')
    result = pd.merge(result, time_stats[['datetime_simple', 'time_period', 'avg_delivery_minutes', 'min_delivery_minutes', 'max_delivery_minutes']], 
                     on=['datetime_simple', 'time_period'], how='left')
    
    result = result.fillna(0)
    result['under_10min_orders'] = result['under_10min_orders'].astype(int)
    result['over_30min_orders'] = result['over_30min_orders'].astype(int)
    result['under_10min_ratio'] = (result['under_10min_orders'] / result['total_orders'] * 100).round(2)
    result['over_30min_ratio'] = (result['over_30min_orders'] / result['total_orders'] * 100).round(2)
    
    return result

# 데이터 로드
data = load_data()

# 대시보드 제목
st.title("배달 통계 대시보드")

# 사이드바 필터
st.sidebar.header("필터")
time_period = st.sidebar.multiselect(
    "시간대 선택",
    options=data['time_period'].unique(),
    default=data['time_period'].unique()
)

# 필터링된 데이터
filtered_data = data[data['time_period'].isin(time_period)]

# 메트릭 카드
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="전체 주문 수",
        value=f"{filtered_data['total_orders'].sum():,}",
    )

with col2:
    st.metric(
        label="10분 이내 배달 비율",
        value=f"{filtered_data['under_10min_ratio'].mean():.1f}%",
    )

with col3:
    st.metric(
        label="30분 이상 배달 비율",
        value=f"{filtered_data['over_30min_ratio'].mean():.1f}%",
    )

with col4:
    st.metric(
        label="평균 배달 시간",
        value=f"{filtered_data['avg_delivery_minutes'].mean():.1f}분",
    )

# 그래프
st.subheader("시간대별 배달 통계")

# 1. 배달 시간 추이
fig_time = px.line(
    filtered_data,
    x='datetime_simple',
    y='avg_delivery_minutes',
    color='time_period',
    title='시간대별 평균 배달 시간 추이',
    labels={'datetime_simple': '날짜', 'avg_delivery_minutes': '평균 배달 시간(분)', 'time_period': '시간대'}
)
st.plotly_chart(fig_time, use_container_width=True)

# 2. 10분 이내/30분 이상 배달 비율
col1, col2 = st.columns(2)

with col1:
    fig_10min = px.bar(
        filtered_data,
        x='datetime_simple',
        y='under_10min_ratio',
        color='time_period',
        title='10분 이내 배달 비율',
        labels={'datetime_simple': '날짜', 'under_10min_ratio': '비율(%)', 'time_period': '시간대'}
    )
    st.plotly_chart(fig_10min, use_container_width=True)

with col2:
    fig_30min = px.bar(
        filtered_data,
        x='datetime_simple',
        y='over_30min_ratio',
        color='time_period',
        title='30분 이상 배달 비율',
        labels={'datetime_simple': '날짜', 'over_30min_ratio': '비율(%)', 'time_period': '시간대'}
    )
    st.plotly_chart(fig_30min, use_container_width=True)

# 상세 데이터 테이블
st.subheader("상세 데이터")
st.dataframe(filtered_data, use_container_width=True) 