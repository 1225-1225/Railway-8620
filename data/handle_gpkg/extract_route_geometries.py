"""
从 china_output.gpkg 的 multilinestrings 中提取所有铁路路线的完整轨迹坐标

输出：
  data/route_geometries.json  — 路线名 -> [ [经度, 纬度], ... ]

格式说明：
  GPKG MULTILINESTRING = 8字节 header + 32字节 envelope + WKB
  WKB MultiLineString: 每个子线段是 LineString，包含多个坐标点
  这里将所有子线段合并为一条连续的坐标序列

用于 route_map_generator.py 绘制沿真实铁路轨道的路线
"""

import sqlite3
import struct
import json
import os

GPKG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'pbf', 'china_output.gpkg'))
OUTPUT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'route_geometries.json'))


def parse_multilinestring_geom(blob):
    """解析 GPKG MULTILINESTRING 的二进制，返回合并的坐标列表
    
    GPKG 格式:
      bytes 0-1: 'GP' magic
      bytes 2: flags
      bytes 3-6: SRS ID (little endian)
      bytes 7-39: envelope (32 bytes = 4 doubles for 2D)
      bytes 40+: standard WKB
    """
    if blob[:2] != b'GP':
        raise ValueError("Not GPKG format")
    
    # 跳过 8 字节 header + 32 字节 envelope
    wkb = blob[40:]
    
    if len(wkb) < 9:
        return []
    
    bo = wkb[0]
    endian = '<' if (bo & 0x01) else '>'
    raw_type = struct.unpack(f'{endian}I', wkb[1:5])[0]
    base_type = raw_type & 0xFFFF
    
    offset = 5
    all_points = []
    
    if base_type == 5:  # MultiLineString
        num_lines = struct.unpack(f'{endian}I', wkb[offset:offset+4])[0]
        offset += 4
        for i in range(num_lines):
            sub_bo = wkb[offset]
            sub_endian = '<' if (sub_bo & 0x01) else '>'
            sub_type = struct.unpack(f'{sub_endian}I', wkb[offset+1:offset+5])[0]
            sub_base = sub_type & 0xFFFF
            offset += 5
            
            if sub_base == 2:  # LineString
                sub_num = struct.unpack(f'{sub_endian}I', wkb[offset:offset+4])[0]
                offset += 4
                for j in range(sub_num):
                    x = round(struct.unpack(f'{sub_endian}d', wkb[offset:offset+8])[0], 6)
                    y = round(struct.unpack(f'{sub_endian}d', wkb[offset+8:offset+16])[0], 6)
                    all_points.append((x, y))
                    offset += 16
            else:
                break
    
    elif base_type == 2:  # LineString (个别路线是单线)
        num_pts = struct.unpack(f'{endian}I', wkb[offset:offset+4])[0]
        offset += 4
        for j in range(num_pts):
            x = round(struct.unpack(f'{endian}d', wkb[offset:offset+8])[0], 6)
            y = round(struct.unpack(f'{endian}d', wkb[offset+8:offset+16])[0], 6)
            all_points.append((x, y))
            offset += 16
    
    return all_points


def main():
    print("=" * 60)
    print("提取铁路路线轨迹坐标")
    print("=" * 60)
    
    conn = sqlite3.connect(GPKG_PATH)
    c = conn.cursor()
    
    # 查询所有有名称的铁路路线
    print("\n📌 查询路线...")
    c.execute("""
        SELECT fid, name, geom FROM multilinestrings
        WHERE type = 'route'
          AND other_tags LIKE '%"route"=>"railway"%'
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)
    
    rows = c.fetchall()
    print(f"  共 {len(rows)} 条铁路路线")
    
    # 提取几何坐标
    route_geometries = {}
    success_count = 0
    fail_count = 0
    
    print("\n📌 解析几何数据...")
    for i, (fid, name, geom) in enumerate(rows):
        try:
            points = parse_multilinestring_geom(geom)
            if points and len(points) >= 2:
                route_geometries[name] = points
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
        
        if (i + 1) % 500 == 0:
            print(f"  已处理 {i+1}/{len(rows)}...")
    
    conn.close()
    
    print(f"\n  解析成功: {success_count} 条路线")
    print(f"  解析失败: {fail_count} 条路线")
    
    # 统计总点数
    total_points = sum(len(pts) for pts in route_geometries.values())
    print(f"  总坐标点数: {total_points}")
    
    # 统计点分布
    point_dist = {}
    for name, pts in route_geometries.items():
        bucket = len(pts) // 100 * 100
        key = f"{bucket}-{bucket+99}"
        point_dist[key] = point_dist.get(key, 0) + 1
    
    # 保存结果（只保留需要的精度以减少文件大小）
    print("\n📌 保存结果...")
    output = {}
    for name, points in route_geometries.items():
        # 转换为 [lng, lat] 格式以节省空间
        output[name] = [[x, y] for x, y in points]
    
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False)
    
    file_size = os.path.getsize(OUTPUT_PATH)
    print(f"  已保存到: {OUTPUT_PATH}")
    print(f"  文件大小: {file_size/1024/1024:.1f} MB")
    
    # 打印样例
    print(f"\n📋 前10条路线轨道点数:")
    for i, (name, pts) in enumerate(list(route_geometries.items())[:10]):
        print(f"  {name}: {len(pts)} 点")
    
    # 打印一些重要路线
    key_routes = ['京广高速线', '京沪高速线', '京哈高速线', '京张高速线', '沪昆高速线']
    print(f"\n📋 关键大线轨道点数:")
    for name in key_routes:
        if name in route_geometries:
            pts = route_geometries[name]
            print(f"  ✅ {name}: {len(pts)} 点")
            print(f"     首: ({pts[0][0]:.4f}, {pts[0][1]:.4f})")
            print(f"     尾: ({pts[-1][0]:.4f}, {pts[-1][1]:.4f})")
        else:
            # 尝试前缀匹配
            found = False
            for rn, pts in route_geometries.items():
                if name.replace('高速线', '') in rn and '高速' in rn:
                    print(f"  ✅ {rn}: {len(pts)} 点")
                    found = True
                    break
            if not found:
                print(f"  ❌ {name}: 未找到（或名称不同）")


if __name__ == '__main__':
    main()