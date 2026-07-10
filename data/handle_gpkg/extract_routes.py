"""
从 china_output.gpkg 中提取铁路路线信息，输出 JSON 文件

方法（高效版）：
1. 从 multilinestrings 提取所有铁路路线
2. 从 points 提取所有车站
3. 利用 GPKG RTree 空间索引做批量车站-路线匹配
4. 输出 路线名 -> 站点列表 的 JSON

核心优化：批量查询 + 只解析必要的几何
"""

import sqlite3
import json
import os
import re
import struct
import math
from collections import defaultdict, OrderedDict


GPKG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'pbf', 'china_output.gpkg'))
OUTPUT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'railway_routes.json'))


def parse_other_tags(tags_str: str) -> dict:
    """解析 OSM other_tags 格式: "key"=>"value" """
    result = {}
    if not tags_str:
        return result
    for m in re.finditer(r'"([^"]+)"\s*=>\s*"([^"]*)"', tags_str):
        result[m.group(1)] = m.group(2)
    return result


def main():
    print("=" * 60)
    print("从 GPKG 提取铁路路线及车站信息")
    print("=" * 60)
    
    conn = sqlite3.connect(GPKG_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # ===== 1. 提取所有铁路路线 =====
    print("\n📌 第一步：提取铁路路线...")
    c.execute("""
        SELECT fid, name, other_tags FROM multilinestrings
        WHERE type = 'route'
          AND other_tags LIKE '%"route"=>"railway"%'
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)
    routes = []
    for row in c.fetchall():
        tags = parse_other_tags(row['other_tags']) if row['other_tags'] else {}
        routes.append({
            'fid': row['fid'],
            'name': row['name'].strip(),
            'ref': tags.get('ref', ''),
            'from': tags.get('from', ''),
            'to': tags.get('to', ''),
            'stations': []
        })
    print(f"  找到 {len(routes)} 条铁路路线")
    
    # ===== 2. 提取所有车站 =====
    print("\n📌 第二步：提取车站...")
    c.execute("""
        SELECT fid, name FROM points
        WHERE (other_tags LIKE '%"railway"=>"station"%'
           OR other_tags LIKE '%"railway"=>"halt"%')
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)
    stations = [{'fid': r['fid'], 'name': r['name'].strip()} for r in c.fetchall()]
    station_fid_set = {s['fid'] for s in stations}
    station_name_set = {s['name'] for s in stations}
    print(f"  找到 {len(stations)} 个车站")
    
    # ===== 3. 按路线名匹配线段，再通过 RTree 找车站 =====
    print("\n📌 第三步：匹配路线与车站...")
    
    # 建立路线名->路线索引
    route_name_map = {}
    for r in routes:
        route_name_map[r['name']] = r
        alt = r['name'].replace('线', '')
        if alt != r['name']:
            route_name_map.setdefault(alt, r)
    
    # 收集所有铁路线段FID（按名称分组）
    c.execute("""
        SELECT fid, name FROM lines
        WHERE railway = 'rail' AND name IS NOT NULL AND name != ''
    """)
    line_fids_by_name = defaultdict(list)
    line_name_set = set()
    for row in c.fetchall():
        name = row['name'].strip()
        line_fids_by_name[name].append(row['fid'])
        line_name_set.add(name)
    print(f"  找到 {sum(len(v) for v in line_fids_by_name.values())} 条铁路线段，{len(line_name_set)} 个不同名称")
    
    # 为每条路线匹配线段，然后用 RTree 找车站
    # 先批量收集需要查询的线段FID
    route_line_fids = {}  # route_name -> set of line_fids
    for r in routes:
        name = r['name']
        fids = line_fids_by_name.get(name, [])
        if not fids:
            alt = name.replace('线', '')
            fids = line_fids_by_name.get(alt, [])
        route_line_fids[name] = fids
    
    # 统计所有需要查询的线段FID
    all_line_fids = set()
    for fids in route_line_fids.values():
        all_line_fids.update(fids)
    print(f"  需要查询 {len(all_line_fids)} 条不同线段的空间关系")
    
    # 批量获取线段周围的车站（通过 RTree）
    # 思路：对于每个线段FID，查 RTree 找出覆盖范围内的车站点FID
    print("\n📌 第四步：空间关联（利用 RTree 索引）...")
    
    # 先建立 station_fid -> station_name 的映射
    fid_to_station = {s['fid']: s['name'] for s in stations}
    
    # 限制处理数量，优先处理有 from/to 的路线
    prioritized_routes = [r for r in routes if r['from'] or r['to']]
    other_routes = [r for r in routes if not r['from'] and not r['to']]
    
    # 先从起终点添加
    for r in prioritized_routes + other_routes:
        route_stations = OrderedDict()
        if r['from'] and r['from'] in station_name_set:
            route_stations[r['from']] = True
        if r['to'] and r['to'] in station_name_set:
            route_stations[r['to']] = True
        r['stations'] = list(route_stations.keys())
    
    # 只对优先路线做空间匹配（有起终点的才更可能找到车站）
    batch_size = 200
    target_routes = prioritized_routes[:batch_size]
    
    processed = 0
    for r in target_routes:
        fids = route_line_fids.get(r['name'], [])
        if not fids:
            alt = r['name'].replace('线', '')
            fids = route_line_fids.get(alt, [])
        
        # 收集该路线所有线段附近的车站
        route_stations = OrderedDict()
        
        # 已有起终点
        if r['from']:
            route_stations[r['from']] = True
        if r['to']:
            route_stations[r['to']] = True
        
        # 遍历每条线段，查 RTree
        for line_fid in fids[:10]:  # 每条路线最多查10条线段
            c.execute("""
                SELECT minx, maxx, miny, maxy FROM rtree_lines_geom WHERE id = ?
            """, (line_fid,))
            bbox_row = c.fetchone()
            if not bbox_row:
                continue
            
            minx, maxx, miny, maxy = bbox_row
            
            # 扩大包围盒（车站可能在轨道旁边）
            margin = 0.015
            minx -= margin
            maxx += margin
            miny -= margin
            maxy += margin
            
            # 通过 RTree 查找该范围内的车站
            c.execute("""
                SELECT DISTINCT p.id FROM rtree_points_geom p
                WHERE p.minx <= ? AND p.maxx >= ?
                  AND p.miny <= ? AND p.maxy >= ?
            """, (maxx, minx, maxy, miny))
            
            nearby_fids = {row[0] for row in c.fetchall()}
            
            # 只保留在我们车站列表中的
            for sfid in nearby_fids:
                if sfid in fid_to_station:
                    route_stations[fid_to_station[sfid]] = True
        
        r['stations'] = list(route_stations.keys())
        processed += 1
        if processed % 20 == 0:
            print(f"  已处理 {processed}/{len(target_routes)} 条路线...")
    
    # 统计
    routes_with_stations = sum(1 for r in routes if r['stations'])
    print(f"\n📊 有车站匹配的路线: {routes_with_stations}/{len(routes)}")
    
    # ===== 5. 输出结果 =====
    all_station_names = sorted(station_name_set)
    output = {
        'total_routes': len(routes),
        'total_stations': len(stations),
        'routes': routes,
        'all_stations': all_station_names
    }
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 结果已保存到: {OUTPUT_PATH}")
    print(f"路线数量: {len(routes)}")
    print(f"车站数量: {len(stations)}")
    
    # 打印前 30 条路线
    print(f"\n📋 前 30 条路线:")
    for r in routes[:30]:
        station_str = ', '.join(r['stations'][:10]) if r['stations'] else '(无)'
        ref_str = f" [{r['ref']}]" if r['ref'] else ""
        print(f"  {r['name']}{ref_str}: {station_str}")
    
    conn.close()


if __name__ == '__main__':
    main()