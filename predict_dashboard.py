import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 데이터 불러오기 함수 (기존 get_google_sheets_data 재활용)
def get_google_sheets_data():
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    service = build('sheets', 'v4', credentials=creds)
    SPREADSHEET_ID = '18r37Qff2igl38HkUEVefFtmT1iOpJ-jIg5aQ91wIUII'
    RANGE_NAME = 'event_raw!A1:Z30000'
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    if not values:
        st.error('데이터를 찾을 수 없습니다.')
        return None
    df = pd.DataFrame(values[1:], columns=values[0])
    # datetime 컬럼이 있다면 time_period 컬럼 추가
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        def get_time_period(hour):
            if 10 <= hour < 15:
                return 'lunch'
            elif 17 <= hour < 22:
                return 'dinner'
            else:
                return 'other'
        df['time_period'] = df['datetime'].dt.hour.apply(get_time_period)
        df = df[df['time_period'] != 'other']
    return df

st.set_page_config(page_title="주문수 예측 대시보드", layout="wide")
st.title("주문수 예측: 이동평균 기반 선형회귀")

df = get_google_sheets_data()
if df is None:
    st.error("구글 시트에서 데이터를 불러오지 못했습니다.")
    st.stop()

df['datetime_simple'] = pd.to_datetime(df['datetime_simple'])
df['weekday_type'] = df['datetime_simple'].dt.weekday.apply(lambda x: '주말' if x >= 5 else '평일')

# 필터 UI
hname_options = df['order_hname'].unique().tolist()
menu_options = df['menu_name'].unique().tolist()
time_options = df['time_period'].unique().tolist()
weekday_options = ['전체', '평일', '주말']
min_date = df['datetime_simple'].min().date()
max_date = df['datetime_simple'].max().date()

col1, col2, col3, col4 = st.columns(4)
with col1:
    selected_hname = st.multiselect("행정동", hname_options, default=hname_options)
with col2:
    selected_menu = st.multiselect("메뉴명", menu_options, default=menu_options)
with col3:
    selected_time = st.multiselect("시간대", time_options, default=time_options)
with col4:
    selected_weekday = st.multiselect("요일구분", weekday_options, default=['전체'])

start_date, end_date = st.date_input("날짜 범위", value=(min_date, max_date), min_value=min_date, max_value=max_date)

# 평일/주말 필터 적용
if '전체' in selected_weekday or not selected_weekday:
    weekday_mask = df['weekday_type'].isin(['평일', '주말'])
else:
    weekday_mask = df['weekday_type'].isin(selected_weekday)

filtered = df[
    (df['order_hname'].isin(selected_hname)) &
    (df['menu_name'].isin(selected_menu)) &
    (df['time_period'].isin(selected_time)) &
    (df['datetime_simple'] >= pd.to_datetime(start_date)) &
    (df['datetime_simple'] <= pd.to_datetime(end_date)) &
    (df['event_type'] == '주문 접수') &
    (weekday_mask)
]

# 집계: 동/메뉴/시간대/날짜별 주문수
agg = (
    filtered.groupby(['order_hname', 'menu_name', 'time_period', 'datetime_simple'])
    .size()
    .reset_index(name='order_count')
)

# --- 모든 동+모든 메뉴 합산 (최상단에 배치) ---
st.markdown("### [모든 동+메뉴 합산] 전체 주문수 예측 (이동평균 회귀)")
for tp in selected_time:
    sub = agg[
        (agg['time_period'] == tp)
    ].groupby('datetime_simple')['order_count'].sum().reset_index()
    if len(sub) < 8:
        continue
    # 주문수가 0인 row 제거
    sub = sub[sub['order_count'] > 0]
    # 이동평균 계산
    sub['ma3'] = sub['order_count'].rolling(window=3, min_periods=1).mean().shift(1)
    sub['ma7'] = sub['order_count'].rolling(window=7, min_periods=1).mean().shift(1)
    sub = sub.dropna(subset=['ma3', 'ma7'])
    # 모델 학습
    X = sub[['ma3', 'ma7']].values
    y = sub['order_count'].values
    model = LinearRegression().fit(X, y)
    y_pred = model.predict(X)
    r2 = model.score(X, y)
    # 다음날 예측 (전날까지의 평균, 0 제외)
    if len(sub) > 3:
        ma3 = sub['order_count'].iloc[-3:].mean()
    else:
        ma3 = sub['order_count'].mean()
    if len(sub) > 7:
        ma7 = sub['order_count'].iloc[-7:].mean()
    else:
        ma7 = sub['order_count'].mean()
    next_pred = model.predict(np.array([[ma3, ma7]]))[0]
    next_day = sub['datetime_simple'].max() + pd.Timedelta(days=1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y, mode='lines+markers', name='실제 주문수'))
    fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y_pred, mode='lines+markers', name='예측 주문수'))
    # 다음날 예측값 추가
    fig.add_trace(go.Scatter(
        x=[next_day], y=[next_pred],
        mode='markers+text', name='다음날 예측',
        marker=dict(color='red', size=12),
        text=[f"{next_pred:.1f}"], textposition="top center"
    ))
    fig.update_layout(title=f"[모든 동+메뉴 합산] {tp} 전체 주문수 예측", xaxis_title="날짜", yaxis_title="주문수")
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"**회귀식:** 주문수 = {model.coef_[0]:.3f} × 3일이동평균 + {model.coef_[1]:.3f} × 7일이동평균 + {model.intercept_:.3f}")
    st.write(f"**설명력(R²):** {r2:.3f}")
    st.info(f"**{next_day.date()} 예측 주문수: {next_pred:.2f}**")

# --- 모든 동 합산: 각 메뉴별 ---
st.markdown("### [모든 동 합산] 메뉴별 주문수 예측 (이동평균 회귀)")
for menu in selected_menu:
    for tp in selected_time:
        sub = agg[
            (agg['menu_name'] == menu) &
            (agg['time_period'] == tp)
        ].groupby('datetime_simple')['order_count'].sum().reset_index()
        if len(sub) < 8:
            continue
        # 주문수가 0인 row 제거
        sub = sub[sub['order_count'] > 0]

        # 이동평균 계산
        sub['ma3'] = sub['order_count'].rolling(window=3, min_periods=1).mean().shift(1)
        sub['ma7'] = sub['order_count'].rolling(window=7, min_periods=1).mean().shift(1)
        sub = sub.dropna(subset=['ma3', 'ma7'])

        # 모델 학습
        X = sub[['ma3', 'ma7']].values
        y = sub['order_count'].values
        model = LinearRegression().fit(X, y)
        y_pred = model.predict(X)
        r2 = model.score(X, y)

        # 다음날 예측 (전날까지의 평균, 0 제외)
        if len(sub) > 3:
            ma3 = sub['order_count'].iloc[-3:].mean()
        else:
            ma3 = sub['order_count'].mean()
        if len(sub) > 7:
            ma7 = sub['order_count'].iloc[-7:].mean()
        else:
            ma7 = sub['order_count'].mean()
        next_pred = model.predict(np.array([[ma3, ma7]]))[0]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y, mode='lines+markers', name='실제 주문수'))
        fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y_pred, mode='lines+markers', name='예측 주문수'))
        # 다음날 예측값 추가
        fig.add_trace(go.Scatter(
            x=[sub['datetime_simple'].max() + pd.Timedelta(days=1)], y=[next_pred],
            mode='markers+text', name='다음날 예측',
            marker=dict(color='red', size=12),
            text=[f"{next_pred:.1f}"], textposition="top center"
        ))
        fig.update_layout(title=f"[모든 동 합산] {menu} - {tp} 주문수 예측", xaxis_title="날짜", yaxis_title="주문수")
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"**회귀식:** 주문수 = {model.coef_[0]:.3f} × 3일이동평균 + {model.coef_[1]:.3f} × 7일이동평균 + {model.intercept_:.3f}")
        st.write(f"**설명력(R²):** {r2:.3f}")
        st.info(f"**{sub['datetime_simple'].max().date() + pd.Timedelta(days=1)} 예측 주문수: {next_pred:.2f}**")
