"""
从 railway_routes.json 构建铁路路线网络图

输出：
  data/railway_graph.json  — 相邻站对 -> 路线信息

用于：
  - 根据车次的站点序列，查找对应的真实铁路路线
  - 生成基于真实路线坐标的地图
"""

import json
import os
from collections import defaultdict

DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTES_PATH = os.path.join(DATA_DIR, 'railway_routes.json')
COORDS_PATH = os.path.join(DATA_DIR, 'station_coords.json')
OUTPUT_PATH = os.path.join(DATA_DIR, 'railway_graph.json')


def build_adjacency_table(routes: list) -> dict:
    """构建相邻站对查找表
    
    返回:
      {
        (站A, 站B): [
          {
            "route_name": "京沪高铁",
            "route_stations": ["北京南", "济南", "徐州", "南京", "上海虹桥"],
            "segment": (start_idx_in_route, end_idx_in_route)
            "direction": 1  # 正向  或 -1 反向
          },
          ...
        ]
      }
    """
    adj = defaultdict(list)
    
    for route in routes:
        stations = route.get('stations', [])
        if len(stations) < 2:
            continue
        
        name = route.get('name', '')
        route_key = f"{name}[{route.get('ref', '')}]" if route.get('ref') else name
        
        # 正向：站A -> 站B
        for i in range(len(stations) - 1):
            key = (stations[i], stations[i + 1])
            adj[key].append({
                "route_name": route_key,
                "route_stations": stations,
                "segment": (i, i + 1),
                "direction": 1
            })
    
    return dict(adj)


def get_route_line_points(route_stations: list, coords: dict) -> list:
    """获取路线经过的经纬度点串"""
    points = []
    for s in route_stations:
        if s in coords:
            points.append({
                "name": s,
                "coord": coords[s]
            })
    return points


def main():
    print("=" * 60)
    print("构建铁路路线网络图")
    print("=" * 60)
    
    # 加载路线数据
    print("\n📌 加载路线数据...")
    with open(ROUTES_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    routes = data['routes']
    print(f"  共 {len(routes)} 条路线")
    
    # 加载车站坐标
    print("\n📌 加载车站坐标...")
    with open(COORDS_PATH, 'r', encoding='utf-8') as f:
        coords = json.load(f)
    print(f"  共 {len(coords)} 个车站坐标")
    
    # 构建邻接表
    print("\n📌 构建相邻站对索引...")
    adj_table = build_adjacency_table(routes)
    print(f"  共 {len(adj_table)} 个相邻站对")
    
    # 统计
    total_edges = sum(len(v) for v in adj_table.values())
    print(f"  共 {total_edges} 条路线段")
    
    # 分析覆盖率
    print("\n📌 分析路线网络覆盖...")
    # 统计有多少相邻站对有多条路线经过（多线并行）
    multi_route_pairs = sum(1 for v in adj_table.values() if len(v) > 1)
    print(f"  多条路线共用的相邻段: {multi_route_pairs}/{len(adj_table)}")
    
    # 统计最大路线长度
    max_len = max(len(r.get('stations', [])) for r in routes)
    print(f"  最长路线站点数: {max_len}")
    
    # 保存结果
    output = {
        "total_adjacent_pairs": len(adj_table),
        "total_route_edges": total_edges,
        "adjacency": {}
    }
    
    for (s1, s2), entries in adj_table.items():
        key = f"{s1}|{s2}"
        output["adjacency"][key] = [
            {
                "route_name": e["route_name"],
                "direction": e["direction"]
            }
            for e in entries
        ]
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 结果已保存到: {OUTPUT_PATH}")
    
    # 打印样例
    print("\n📋 相邻站对样例:")
    sample_keys = [("北京南", "南京南"), ("上海", "南京"), ("北京", "上海")]
    for s1, s2 in sample_keys:
        key = f"{s1}|{s2}"
        if key in output["adjacency"]:
            print(f"  {s1} → {s2}: {len(output['adjacency'][key])} 条路线")
            for e in output["adjacency"][key][:3]:
                print(f"    - {e['route_name']}")
        else:
            print(f"  {s1} → {s2}: 未找到直接连接")
    
    # 检查有多少 train_stations 中的车站能在 coords 中找到
    print("\n📋 train_stations.json 坐标覆盖检查...")
    train_data_path = os.path.join(DATA_DIR, 'train_stations.json')
    with open(train_data_path, 'r', encoding='utf-8') as f:
        train_data = json.load(f)
    
    all_stations = set()
    for code, info in train_data.items():
        for s in info.get('stations', []):
            all_stations.add(s)
    
    found = sum(1 for s in all_stations if s in coords)
    print(f"  车次数据中共 {len(all_stations)} 个唯一车站")
    print(f"  在坐标中找到: {found} ({found*100//len(all_stations)}%)")


if __name__ == '__main__':
    main()