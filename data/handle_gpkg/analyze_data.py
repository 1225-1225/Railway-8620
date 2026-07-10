"""
统计 data/ 目录下所有生成的数据文件
"""

import json

# 读取新生成的数据
train_data = json.load(open('data/train_stations.json', 'r', encoding='utf-8'))
route_data = json.load(open('data/route_stations.json', 'r', encoding='utf-8'))
gpkg_data = json.load(open('data/railway_routes.json', 'r', encoding='utf-8'))

print('=' * 60)
print('数据总览')
print('=' * 60)
print(f'RailRhythm12306 车次数: {len(train_data)}')
print(f'RailRhythm12306 路线分组: {len(route_data)}')
print(f'GPKG 提取路线: {gpkg_data["total_routes"]}')
print(f'GPKG 提取车站: {gpkg_data["total_stations"]}')

# 车次类型统计
types = {}
for code in train_data:
    prefix = code[0] if code[0].isalpha() else 'P'
    types[prefix] = types.get(prefix, 0) + 1
print()
print('车次类型分布:')
name_map = {'G':'高速', 'D':'动车', 'C':'城际', 'Z':'直特', 'T':'特快', 'K':'快速', 'S':'市郊', 'Y':'旅游', 'P':'纯数字'}
for t in sorted(types):
    name = name_map.get(t, t)
    print(f'  {t} ({name}): {types[t]}')

# 最长的路线（经过站最多的）
all_trains = [(code, info) for code, info in train_data.items()]
all_trains.sort(key=lambda x: -len(x[1]['stations']))
print()
print('经停站最多的10趟车:')
for code, info in all_trains[:10]:
    print(f'  {code} {info["from"]}->{info["to"]}: {len(info["stations"])}站')

# 主要高铁线路（G字头10站以上）
g_trains = [(code, info) for code, info in all_trains if code.startswith('G') and len(info['stations']) >= 10]
g_trains.sort(key=lambda x: -len(x[1]['stations']))
print()
print('主要高铁线路（G字头10站以上）前15趟:')
for code, info in g_trains[:15]:
    s = info['stations']
    print(f'  {code} {s[0]}->{s[-1]}: {len(s)}站')

print()
print('文件大小:')
import os
for f in ['data/train_stations.json', 'data/route_stations.json', 'data/railway_routes.json']:
    size = os.path.getsize(f)
    print(f'  {f}: {size/1024:.1f} KB')