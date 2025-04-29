import streamlit as st
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go

# 데이터 불러오기 함수 (기존 get_google_sheets_data 재활용)
def get_google_sheets_data():
    # ... (생략, 기존과 동일) ...
    return df

st.set_page_config(page_title="주문수 예측 대시보드", layout="wide")
st.title("주문수 예측: 이동평균 기반 선형회귀")

df = get_google_sheets_data()
df['datetime_simple'] = pd.to_datetime(df['datetime_simple'])

# 필터 UI
hname_options = df['order_hname'].unique().tolist()
menu_options = df['menu_name'].unique().tolist()
time_options = df['time_period'].unique().tolist()
min_date = df['datetime_simple'].min().date()
max_date = df['datetime_simple'].max().date()

col1, col2, col3 = st.columns(3)
with col1:
    selected_hname = st.multiselect("행정동", hname_options, default=hname_options)
with col2:
    selected_menu = st.multiselect("메뉴명", menu_options, default=menu_options)
with col3:
    selected_time = st.multiselect("시간대", time_options, default=time_options)

start_date, end_date = st.date_input("날짜 범위", value=(min_date, max_date), min_value=min_date, max_value=max_date)

# 필터 적용
filtered = df[
    (df['order_hname'].isin(selected_hname)) &
    (df['menu_name'].isin(selected_menu)) &
    (df['time_period'].isin(selected_time)) &
    (df['datetime_simple'] >= pd.to_datetime(start_date)) &
    (df['datetime_simple'] <= pd.to_datetime(end_date)) &
    (df['event_type'] == '주문 접수')
]

# 집계: 동/메뉴/시간대/날짜별 주문수
agg = (
    filtered.groupby(['order_hname', 'menu_name', 'time_period', 'datetime_simple'])
    .size()
    .reset_index(name='order_count')
)

# 각 조합별로 모델링
for hname in selected_hname:
    for menu in selected_menu:
        for tp in selected_time:
            sub = agg[
                (agg['order_hname'] == hname) &
                (agg['menu_name'] == menu) &
                (agg['time_period'] == tp)
            ].sort_values('datetime_simple')
            if len(sub) < 8:
                continue  # 데이터가 너무 적으면 스킵

            sub = sub.set_index('datetime_simple').asfreq('D', fill_value=0).reset_index()
            sub['ma3'] = sub['order_count'].rolling(window=3, min_periods=1).mean()
            sub['ma7'] = sub['order_count'].rolling(window=7, min_periods=1).mean()

            # 오늘 이후 데이터는 예측용으로 분리 가능 (여기선 전체 fit)
            X = sub[['ma3', 'ma7']].values
            y = sub['order_count'].values
            model = LinearRegression().fit(X, y)
            y_pred = model.predict(X)
            r2 = model.score(X, y)

            # 시각화
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y, mode='lines+markers', name='실제 주문수'))
            fig.add_trace(go.Scatter(x=sub['datetime_simple'], y=y_pred, mode='lines+markers', name='예측 주문수'))
            fig.update_layout(title=f"{hname} - {menu} - {tp} 주문수 예측 (이동평균 회귀)", xaxis_title="날짜", yaxis_title="주문수")
            st.plotly_chart(fig, use_container_width=True)

            # 잔차 플롯
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=sub['datetime_simple'], y=(y - y_pred), name='잔차(오차)'))
            fig2.update_layout(title="잔차(실제-예측)", xaxis_title="날짜", yaxis_title="오차")
            st.plotly_chart(fig2, use_container_width=True)

            # 모델 계수 및 R2
            st.write(f"**회귀식:** 주문수 = {model.coef_[0]:.3f} × 3일이동평균 + {model.coef_[1]:.3f} × 7일이동평균 + {model.intercept_:.3f}")
            st.write(f"**설명력(R²):** {r2:.3f}")
