"""
从 RailRhythm12306 的 train_list*.json 中提取车次及其经停站数据

数据来源：c:/Users/1225/Desktop/RailRhythm12306-main/train_data/
最新数据：train_list20250706.json + no_list20250706.json

输出：
  data/train_stations.json  — 车次号 -> 经停站列表
  data/route_stations.json  — 路线名 -> 经停站列表（合并同一线路所有车次）
"""

import json
import os
import re
from collections import OrderedDict, defaultdict

# ===== 路径配置 =====
RAILRHYTHM_DIR = r"c:/Users/1225/Desktop/RailRhythm12306-main/train_data"
OUTPUT_TRAIN_STATIONS = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'train_stations.json'))
OUTPUT_ROUTE_STATIONS = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'route_stations.json'))
LATEST_DATE = "20250706"  # 使用最新日期


def load_json(filename):
    path = os.path.join(RAILRHYTHM_DIR, filename)
    if not os.path.exists(path):
        print(f"⚠️  文件不存在: {path}")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_train_info():
    """
    提取每条车次的经停站列表
    
    返回: {
        "G1": {
            "train_code": "G1",
            "start_station": "北京南",
            "end_station": "上海虹桥",
            "train_class": "高速",
            "stations": ["北京南", "南京南", "上海虹桥"],
            "station_details": [
                {"name": "北京南", "arrive": "", "depart": "07:00", "no": 1},
                ...
            ]
        },
        ...
    }
    """
    # 加载数据
    train_list = load_json(f"train_list{LATEST_DATE}.json")
    no_list = load_json(f"no_list{LATEST_DATE}.json")
    
    if not train_list or not no_list:
        print("❌ 数据加载失败")
        return {}
    
    print(f"📊 train_list: {len(train_list)} 条记录")
    print(f"📊 no_list: {len(no_list)} 条记录")
    
    # 建立 train_no -> train_code 的映射
    # no_list 结构: {train_code: train_no}
    no_to_code = {}
    for code, no in no_list.items():
        no_to_code[str(no)] = code
    
    # 提取每条车次信息
    result = {}
    for train_no, stations in train_list.items():
        train_code = no_to_code.get(train_no, train_no)
        
        if not stations:
            continue
        
        first = stations[0]
        last = stations[-1]
        
        station_names = []
        station_details = []
        for s in stations:
            name = s.get('station_name', '').strip()
            station_names.append(name)
            station_details.append({
                'name': name,
                'arrive': s.get('arrive_time', '').strip(),
                'depart': s.get('start_time', '').strip(),
                'no': int(s.get('station_no', 0))
            })
        
        result[train_code] = {
            'train_code': train_code,
            'start_station': first.get('start_station_name', '').strip(),
            'end_station': first.get('end_station_name', '').strip(),
            'train_class': first.get('train_class_name', '').strip(),
            'stations': station_names,
            'station_details': station_details
        }
    
    return result


def group_by_route(train_data):
    """
    将车次按路线分组，提取每条路线经过的所有站点
    
    路线判断：从车次名和起终点推断
    同一路线的车次：始发站或终到站相同/相近
    """
    # 按方向分组：先按始发站-终到站分组
    route_groups = defaultdict(list)
    for code, info in train_data.items():
        key = f"{info['start_station']}→{info['end_station']}"
        route_groups[key].append(info)
    
    # 合并同一条路线（方向相反）
    merged = defaultdict(list)
    visited = set()
    
    for key in route_groups:
        if key in visited:
            continue
        visited.add(key)
        
        # 找相反方向
        start, end = key.split('→')
        reverse_key = f"{end}→{start}"
        if reverse_key in route_groups:
            visited.add(reverse_key)
            merged_key = f"{start}/{end}"
            merged[merged_key] = route_groups[key] + route_groups[reverse_key]
        else:
            merged[key] = route_groups[key]
    
    # 对每条路线，收集所有站点（按出现顺序去重）
    route_stations = {}
    for route_name, trains in merged.items():
        all_stations = OrderedDict()
        
        # 按车次号排序（G先、D次之、K/Z/T在后）
        trains.sort(key=lambda t: (
            t['train_code'][0] if t['train_code'][0].isalpha() else 'Z',
            t['train_code']
        ))
        
        for t in trains:
            for s in t['stations']:
                all_stations[s] = True
        
        route_stations[route_name] = {
            'route_name': route_name,
            'train_count': len(trains),
            'stations': list(all_stations.keys()),
            'example_codes': [t['train_code'] for t in trains[:5]]
        }
    
    return route_stations


def main():
    print("=" * 60)
    print("从 RailRhythm12306 提取车次经停站数据")
    print(f"数据日期: {LATEST_DATE}")
    print("=" * 60)
    
    # 1. 提取车次信息
    train_data = extract_train_info()
    if not train_data:
        return
    
    print(f"\n📌 共提取 {len(train_data)} 个车次")
    
    # 2. 按路线分组
    route_data = group_by_route(train_data)
    print(f"📌 共 {len(route_data)} 条路线分组")
    
    # 3. 输出车次-经停站 JSON
    output_train = {}
    for code, info in train_data.items():
        output_train[code] = {
            'from': info['start_station'],
            'to': info['end_station'],
            'class': info['train_class'],
            'stations': info['stations']
        }
    
    os.makedirs(os.path.dirname(OUTPUT_TRAIN_STATIONS), exist_ok=True)
    with open(OUTPUT_TRAIN_STATIONS, 'w', encoding='utf-8') as f:
        json.dump(output_train, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 车次数据已保存: {OUTPUT_TRAIN_STATIONS}")
    print(f"   共 {len(output_train)} 个车次")
    
    # 4. 输出路线-经停站 JSON
    output_route = {}
    for name, info in route_data.items():
        output_route[name] = {
            'train_count': info['train_count'],
            'stations': info['stations'],
            'example_codes': info['example_codes']
        }
    
    with open(OUTPUT_ROUTE_STATIONS, 'w', encoding='utf-8') as f:
        json.dump(output_route, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 路线数据已保存: {OUTPUT_ROUTE_STATIONS}")
    print(f"   共 {len(output_route)} 条路线")
    
    # 5. 打印样例
    print("\n📋 车次样例（前10条）:")
    for i, (code, info) in enumerate(list(output_train.items())[:10]):
        station_str = ', '.join(info['stations'][:8])
        print(f"  {code} {info['from']}→{info['to']}: [{len(info['stations'])}站] {station_str}")
    
    print(f"\n📋 路线样例（前20条）:")
    for i, (name, info) in enumerate(list(output_route.items())[:20]):
        station_str = ', '.join(info['stations'][:8])
        print(f"  {name}: [{len(info['stations'])}站] {station_str}")


if __name__ == '__main__':
    main()