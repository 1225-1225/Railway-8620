"""
从 RailRhythm12306 原始数据提取完整的车次详细信息（含到达/发车时间）

输入：
  c:/Users/1225/Desktop/RailRhythm12306-main/train_data/train_list20250706.json
  c:/Users/1225/Desktop/RailRhythm12306-main/train_data/no_list20250706.json

输出：
  data/train_details.json  — 车次号 -> 完整信息（含 station_details 时间信息）
"""

import json
import os

# ===== 路径配置 =====
RAILRHYTHM_DIR = r"c:/Users/1225/Desktop/RailRhythm12306-main/train_data"
OUTPUT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'train_details.json'))
LATEST_DATE = "20250706"


def load_json(filename):
    path = os.path.join(RAILRHYTHM_DIR, filename)
    if not os.path.exists(path):
        print(f"⚠️  文件不存在: {path}")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    print("=" * 60)
    print("提取车次完整详细信息（含时间）")
    print(f"数据日期: {LATEST_DATE}")
    print("=" * 60)
    
    # 加载数据
    train_list = load_json(f"train_list{LATEST_DATE}.json")
    no_list = load_json(f"no_list{LATEST_DATE}.json")
    
    if not train_list or not no_list:
        print("❌ 数据加载失败")
        return
    
    print(f"\n📊 train_list: {len(train_list)} 条记录")
    print(f"📊 no_list: {len(no_list)} 条记录")
    
    # 建立 train_no -> train_code 的映射
    no_to_code = {}
    for code, no in no_list.items():
        no_to_code[str(no)] = code
    
    # 提取信息
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
            'from': first.get('start_station_name', '').strip(),
            'to': first.get('end_station_name', '').strip(),
            'class': first.get('train_class_name', '').strip(),
            'stations': station_names,
            'station_details': station_details
        }
    
    print(f"\n📌 共提取 {len(result)} 个车次的完整信息")
    
    # 保存
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 结果已保存到: {OUTPUT_PATH}")
    
    # 打印样例
    print("\n📋 车次样例:")
    sample_codes = list(result.keys())[:3]
    for code in sample_codes:
        info = result[code]
        print(f"\n  {code} ({info['class']}): {info['from']} → {info['to']}")
        print(f"  经停 {len(info['stations'])} 站:")
        for sd in info['station_details'][:6]:
            print(f"    {sd['no']}. {sd['name']} 到达:{sd['arrive']} 发车:{sd['depart']}")
        if len(info['station_details']) > 6:
            print(f"    ... 还有 {len(info['station_details'])-6} 站")


if __name__ == '__main__':
    main()