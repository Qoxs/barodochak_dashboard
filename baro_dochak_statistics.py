import pandas as pd
import os
import plotly.express as px

# 현재 스크립트의 디렉토리 경로를 가져옴
current_dir = os.path.dirname(os.path.abspath(__file__))

# 데이터 불러오기
df = pd.read_excel(os.path.join(current_dir, 'order_raw.xlsx'))

# 필요한 컬럼만 사용
df = df[['datetime', 'order_id', 'event_type', 'datetime_simple']]

# datetime을 datetime 타입으로 변환
df['datetime'] = pd.to_datetime(df['datetime'])

# 시간대 구분을 위한 함수
def get_time_period(hour):
    if 10 <= hour < 15:
        return 'lunch'
    elif 17 <= hour < 22:
        return 'dinner'
    else:
        return 'other'

# 시간대 컬럼 추가
df['time_period'] = df['datetime'].dt.hour.apply(get_time_period)

# other 시간대 제외
df = df[df['time_period'] != 'other']

# 주문별로 '주문 접수'와 '배달 완료' 시간 추출
order_group = df[df['event_type'].isin(['주문 접수', '배달 완료'])].pivot_table(
    index=['order_id', 'datetime_simple', 'time_period'],
    columns='event_type',
    values='datetime',
    aggfunc='min'
).reset_index()

# 배송 소요 시간(초) 계산
order_group['delivery_seconds'] = (
    order_group['배달 완료'] - order_group['주문 접수']
).dt.total_seconds()

# 10분(600초) 이내 도착 주문만 필터링
order_10min = order_group[order_group['delivery_seconds'] <= 600]

# 30분(1800초) 이상 도착 주문 필터링
order_30min = order_group[order_group['delivery_seconds'] >= 1800]

# 시간대별 전체 주문 수
order_count = order_group.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='total_orders')

# 시간대별 10분 이내 도착 주문 수
fast_count = order_10min.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='under_10min_orders')

# 시간대별 30분 이상 도착 주문 수
slow_count = order_30min.groupby(['datetime_simple', 'time_period'])['order_id'].count().reset_index(name='over_30min_orders')

# 시간대별 통계 계산
time_stats = order_group.groupby(['datetime_simple', 'time_period'])['delivery_seconds'].agg(['mean', 'min', 'max']).reset_index()
time_stats['avg_delivery_minutes'] = (time_stats['mean'] / 60).round(2)
time_stats['min_delivery_minutes'] = (time_stats['min'] / 60).round(2)
time_stats['max_delivery_minutes'] = (time_stats['max'] / 60).round(2)

# 결과 병합
result = pd.merge(order_count, fast_count, on=['datetime_simple', 'time_period'], how='left')
result = pd.merge(result, slow_count, on=['datetime_simple', 'time_period'], how='left')
result = pd.merge(result, time_stats[['datetime_simple', 'time_period', 'avg_delivery_minutes', 'min_delivery_minutes', 'max_delivery_minutes']], 
                 on=['datetime_simple', 'time_period'], how='left')

# 결측치 처리
result = result.fillna(0)
result['under_10min_orders'] = result['under_10min_orders'].astype(int)
result['over_30min_orders'] = result['over_30min_orders'].astype(int)

# 10분 이내 배달 비율 계산 (소수점 둘째자리까지)
result['under_10min_ratio'] = (result['under_10min_orders'] / result['total_orders'] * 100).round(2)

# 30분 이상 배달 비율 계산 (소수점 둘째자리까지)
result['over_30min_ratio'] = (result['over_30min_orders'] / result['total_orders'] * 100).round(2)

# 결과 확인
print("시간대별 통계 (lunch & dinner):")
print(result)

# 그래프용 데이터 복사
graph_data = result.copy()

# 날짜 컬럼을 datetime 타입으로 변환
graph_data['datetime_simple'] = pd.to_datetime(graph_data['datetime_simple'])

# 날짜 기준으로 정렬
graph_data = graph_data.sort_values('datetime_simple')

graph_data['avg_delivery_time'] = graph_data['avg_delivery_minutes'].apply(lambda x: f"{int(x)}분 {int((x - int(x)) * 60)}초")

fig_time = px.line(
    graph_data,
    x='datetime_simple',
    y='avg_delivery_minutes',
    color='time_period',
    title='시간대별 평균 배달 시간 추이',
    labels={'datetime_simple': '날짜', 'avg_delivery_minutes': '평균 배달 시간', 'time_period': '시간대'},
    custom_data=['avg_delivery_time']
)
fig_time.update_xaxes(dtick="D", tickformat="%Y-%m-%d")  # x축을 날짜로 명확히 표시
