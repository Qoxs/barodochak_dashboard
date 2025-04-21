import pandas as pd
import os

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

# 날짜별로 가장 빠른 배송 시간 찾기
fastest_per_day = order_group.groupby('datetime_simple')['delivery_seconds'].min().reset_index()

# 결과 확인
print(fastest_per_day)

# 모든 날짜의 주문 상세 정보 출력
print("\n모든 날짜의 주문 상세 정보:")
all_orders = order_group.copy()
all_orders['delivery_minutes'] = (all_orders['delivery_seconds'] / 60).round(2)

# 날짜별로 그룹화하여 출력
for date in sorted(all_orders['datetime_simple'].unique()):
    print(f"\n{date} 주문 상세 정보:")
    date_orders = all_orders[all_orders['datetime_simple'] == date]
    print(date_orders[['order_id', 'time_period', 'delivery_minutes']].sort_values('delivery_minutes'))

