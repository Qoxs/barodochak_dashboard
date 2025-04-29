import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# 분:초 형식으로 변환하는 함수
def format_minutes_seconds(minutes):
    total_seconds = int(minutes * 60)
    mins = total_seconds // 60
    secs = total_seconds % 60
    return f"{mins}분 {secs}초"

# Google Sheets API 설정
def get_google_sheets_data():
    # 서비스 계정 키 파일 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    SERVICE_ACCOUNT_FILE = os.path.join(current_dir, 'baro-dochack-dashboard-d7d1b43e20c8.json')
    
    # 접근 권한 범위
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    
    # 인증 객체 생성
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    
    # Sheets API 클라이언트 생성
    service = build('sheets', 'v4', credentials=creds)
    
    # 스프레드시트 ID와 범위 지정
    SPREADSHEET_ID = '18r37Qff2igl38HkUEVefFtmT1iOpJ-jIg5aQ91wIUII'
    RANGE_NAME = 'event_raw!A1:Z10000'  # 데이터 범위를 늘림
    
    # 데이터 읽기
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    
    if not values:
        st.error('데이터를 찾을 수 없습니다.')
        return None
    
    # 데이터프레임 생성
    df = pd.DataFrame(values[1:], columns=values[0])
    return df

# 페이지 설정
st.set_page_config(page_title="배달 통계 대시보드", layout="wide")

## python -m streamlit run C:\Users\USER04\Desktop\baro_dochak\dashboard.py

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
@st.cache_data(ttl=300)  # 5분마다 캐시 갱신
def load_data():
    try:
        df = get_google_sheets_data()
        if df is None:
            return None
            
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
        
        # 날짜 순서대로 정렬
        result['date'] = pd.to_datetime(result['datetime_simple'])
        result = result.sort_values('date')
        result = result.drop('date', axis=1)
        
        return result
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {str(e)}")
        return None

# 데이터 로드
data = load_data()

if data is not None:
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
        avg_delivery_time = format_minutes_seconds(filtered_data['avg_delivery_minutes'].mean())
        st.metric(
            label="평균 배달 시간",
            value=avg_delivery_time
        )

    # 그래프
    st.subheader("시간대별 배달 통계")

    # 1. 배달 시간 추이
    # 그래프용 데이터 복사
    graph_data = filtered_data.copy()
    graph_data['avg_delivery_time'] = graph_data['avg_delivery_minutes'].apply(format_minutes_seconds)
    
    fig_time = px.line(
        graph_data,
        x='datetime_simple',
        y='avg_delivery_minutes',
        color='time_period',
        title='시간대별 평균 배달 시간 추이',
        labels={'datetime_simple': '날짜', 'avg_delivery_minutes': '평균 배달 시간', 'time_period': '시간대'},
        custom_data=['avg_delivery_time']
    )
    
    # Y축 포맷팅
    fig_time.update_traces(
        hovertemplate="<br>".join([
            "날짜: %{x}",
            "시간대: %{fullData.name}",
            "평균 배달 시간: %{customdata[0]}"
        ])
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
    # 테이블에 분:초 형식 추가
    display_data = filtered_data.copy()
    display_data['평균 배달 시간'] = display_data['avg_delivery_minutes'].apply(format_minutes_seconds)
    display_data['최소 배달 시간'] = display_data['min_delivery_minutes'].apply(format_minutes_seconds)
    display_data['최대 배달 시간'] = display_data['max_delivery_minutes'].apply(format_minutes_seconds)
    
    # 원래 컬럼 제거
    display_data = display_data.drop(['avg_delivery_minutes', 'min_delivery_minutes', 'max_delivery_minutes'], axis=1)
    
    st.dataframe(display_data, use_container_width=True) 