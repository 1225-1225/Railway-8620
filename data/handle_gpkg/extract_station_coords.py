"""
从 china_output.gpkg 的 points 表中提取所有车站的经纬度坐标

输出：
  data/station_coords.json  — 车站名 -> [经度, 纬度]

车站判断条件：other_tags 中包含 "railway"=>"station" 或 "railway"=>"halt"

GPKG 几何二进制格式:
  - 2 bytes: "GP" magic
  - 1 byte: version
  - 1 byte: flags
  - 4 bytes: SRS ID (little endian)
  - WKB content
"""

import sqlite3
import json
import os
import struct

GPKG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'pbf', 'china_output.gpkg'))
OUTPUT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'station_coords.json'))

# GPKG 几何二进制头部大小: "GP"(2) + version(1) + flags(1) + srs_id(4) = 8
GPKG_HEADER_SIZE = 8


def parse_wkb_point(blob: bytes):
    """解析包含 GPKG 头部的 WKB Point，返回 (经度, 纬度) 或 None
    
    WKB Point 格式:
      - 1 byte: byte order (0=big-endian, 1=little-endian)
      - 4 bytes: geometry type (1=Point)
      - 8 bytes: X (double)
      - 8 bytes: Y (double)
    """
    if not blob or len(blob) < GPKG_HEADER_SIZE + 21:
        return None
    
    # 跳过 GPKG 头部 8 字节
    wkb = blob[GPKG_HEADER_SIZE:]
    
    # 字节序
    byte_order = wkb[0]
    
    # 几何类型（验证是 Point=1）
    if byte_order == 1:  # 小端
        geom_type = struct.unpack('<I', wkb[1:5])[0]
        x = struct.unpack('<d', wkb[5:13])[0]
        y = struct.unpack('<d', wkb[13:21])[0]
    else:  # 大端
        geom_type = struct.unpack('>I', wkb[1:5])[0]
        x = struct.unpack('>d', wkb[5:13])[0]
        y = struct.unpack('>d', wkb[13:21])[0]
    
    if geom_type != 1:
        return None
    
    return (round(x, 6), round(y, 6))


def main():
    print("=" * 60)
    print("从 GPKG 提取车站坐标")
    print("=" * 60)
    
    conn = sqlite3.connect(GPKG_PATH)
    c = conn.cursor()
    
    # 查询所有车站点（railway=station 或 railway=halt）
    print("\n📌 查询车站...")
    c.execute("""
        SELECT fid, name, geom FROM points
        WHERE (other_tags LIKE '%"railway"=>"station"%'
           OR other_tags LIKE '%"railway"=>"halt"%')
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)
    
    rows = c.fetchall()
    print(f"  共找到 {len(rows)} 个车站点")
    
    # 提取坐标，按车站名去重（同名车站取第一个）
    station_coords = {}
    duplicate_count = 0
    parse_fail_count = 0
    valid_count = 0
    
    for row in rows:
        fid, name, geom_blob = row
        if not geom_blob:
            parse_fail_count += 1
            continue
        
        coords = parse_wkb_point(geom_blob)
        if coords is None:
            parse_fail_count += 1
            continue
        
        # 过滤无效坐标（经度应为 70-140，纬度应为 15-55）
        lng, lat = coords
        if not (70 <= lng <= 140 and 15 <= lat <= 55):
            parse_fail_count += 1
            continue
        
        valid_count += 1
        
        if name in station_coords:
            duplicate_count += 1
        else:
            station_coords[name] = coords
    
    conn.close()
    
    print(f"  解析成功：{valid_count} 个点")
    print(f"  解析失败：{parse_fail_count} 个点")
    print(f"  去重后：{len(station_coords)} 个唯一车站")
    print(f"  同名车站（取第一个）: {duplicate_count} 个")
    
    # 保存结果
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(station_coords, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 结果已保存到: {OUTPUT_PATH}")
    print(f"   共 {len(station_coords)} 个车站坐标")
    
    # 打印样例
    print("\n📋 坐标样例（前20个）:")
    for i, (name, coords) in enumerate(list(station_coords.items())[:20]):
        print(f"  {name}: {coords}")
    
    # 检查一些关键车站
    key_stations = ['北京', '北京南', '北京西', '北京丰台', '上海', '上海虹桥', 
                    '广州', '广州南', '深圳', '深圳北', '合肥', '合肥南', 
                    '杭州', '杭州东', '南京', '南京南', '武汉', '汉口',
                    '西安', '成都', '重庆']
    print("\n📋 关键车站坐标检查:")
    for s in key_stations:
        if s in station_coords:
            print(f"  ✅ {s}: {station_coords[s]}")
        else:
            print(f"  ❌ {s}: 未找到")


if __name__ == '__main__':
    main()