import pandas as pd
import re

file_path = 'min_hourly_wage.xlsx'
df = pd.read_excel(file_path, header=None)
df.columns = [f'col_{i}' for i in range(df.shape[1])]

df['rider_phone'] = df['col_7'].astype(str).str.extract(r'(\d{11})')
df['event_time'] = pd.to_datetime(df['col_0'], errors='coerce')

df = df[['event_time', 'col_2', 'rider_phone', 'col_12', 'col_13']]
df = df[df['col_2'].isin(['주문 접수', '배달 완료'])]

result = []
for (rider, date, time_zone), group in df.groupby(['rider_phone', 'col_12', 'col_13']):
    first_order = group[group['col_2'] == '주문 접수']['event_time'].min()
    last_delivery = group[group['col_2'] == '배달 완료']['event_time'].max()
    if pd.notnull(first_order) and pd.notnull(last_delivery):
        duration = (last_delivery - first_order).total_seconds() // 60
        result.append({
            'rider_phone': rider,
            'date': date,            # 반드시 'date' key로 저장
            'time_zone': time_zone,  # 반드시 'time_zone' key로 저장
            'first_order_time': first_order,
            'last_delivery_time': last_delivery,
            'duration_min': int(duration)
        })

result_df = pd.DataFrame(result)
print(result_df.columns)  # 여기서 반드시 'date'가 있는지 확인

if not result_df.empty:
    result_df = result_df.sort_values(['date', 'rider_phone', 'time_zone'])
    result_df.to_excel('rider_daily_duration.xlsx', index=False)
    print(result_df)
else:
    print('집계 결과가 없습니다.')
