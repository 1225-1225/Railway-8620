"""
GPKG 分析报告：表结构、字段取值、铁路类型细分、数据质量评估

只依赖 china_output.gpkg，不参考任何其他已生成数据
"""

import sqlite3
import os
import re
import struct
import math
from collections import Counter

GPKG_PATH = r"d:\PyCharm\Railway-8620\data\pbf\china_output.gpkg"
REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gpkg_analysis_report.txt')


def parse_other_tags(tags_str):
    """解析 OSM other_tags 格式: "key"=>"value" """
    result = {}
    if not tags_str:
        return result
    for m in re.finditer(r'"([^"]+)"\s*=>\s*"([^"]*)"', tags_str):
        result[m.group(1)] = m.group(2)
    return result


def haversine_distance(lng1, lat1, lng2, lat2):
    """近似距离 km"""
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def get_wkb_from_gpkg(blob):
    """从 GPKG blob 中提取 WKB，正确处理 envelope"""
    if not blob or blob[:2] != b'GP':
        return None
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0x07
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    envelope_bytes = envelope_sizes.get(envelope_indicator, 0)
    return blob[8 + envelope_bytes:]


def parse_geometry_points(blob):
    """解析 GPKG 几何二进制，返回坐标列表 [(lng, lat), ...]"""
    wkb = get_wkb_from_gpkg(blob)
    if not wkb or len(wkb) < 5:
        return []

    bo = wkb[0]
    endian = '<' if (bo & 0x01) else '>'
    raw_type = struct.unpack(f'{endian}I', wkb[1:5])[0]
    base_type = raw_type & 0xFFFF
    offset = 5
    all_points = []

    if base_type == 1:  # Point
        if len(wkb) < 21:
            return []
        x = struct.unpack(f'{endian}d', wkb[5:13])[0]
        y = struct.unpack(f'{endian}d', wkb[13:21])[0]
        return [(round(x, 6), round(y, 6))]

    elif base_type == 2:  # LineString
        num_pts = struct.unpack(f'{endian}I', wkb[offset:offset + 4])[0]
        offset += 4
        for j in range(num_pts):
            if offset + 16 > len(wkb):
                break
            x = round(struct.unpack(f'{endian}d', wkb[offset:offset + 8])[0], 6)
            y = round(struct.unpack(f'{endian}d', wkb[offset + 8:offset + 16])[0], 6)
            all_points.append((x, y))
            offset += 16

    elif base_type == 5:  # MultiLineString
        num_lines = struct.unpack(f'{endian}I', wkb[offset:offset + 4])[0]
        offset += 4
        for i in range(num_lines):
            if offset + 5 > len(wkb):
                break
            sub_endian = '<' if (wkb[offset] & 0x01) else '>'
            sub_type = struct.unpack(f'{sub_endian}I', wkb[offset + 1:offset + 5])[0]
            sub_base = sub_type & 0xFFFF
            offset += 5
            if sub_base == 2:  # LineString
                if offset + 4 > len(wkb):
                    break
                sub_num = struct.unpack(f'{sub_endian}I', wkb[offset:offset + 4])[0]
                offset += 4
                for j in range(sub_num):
                    if offset + 16 > len(wkb):
                        break
                    x = round(struct.unpack(f'{sub_endian}d', wkb[offset:offset + 8])[0], 6)
                    y = round(struct.unpack(f'{sub_endian}d', wkb[offset + 8:offset + 16])[0], 6)
                    all_points.append((x, y))
                    offset += 16
            else:
                break

    return all_points


def trajectory_length(points):
    total = 0
    for i in range(len(points) - 1):
        total += haversine_distance(points[i][0], points[i][1],
                                    points[i + 1][0], points[i + 1][1])
    return total


def main():
    report_lines = []

    def p(text=""):
        print(text)
        report_lines.append(text)

    p("=" * 70)
    p("GPKG 分析报告")
    p(f"文件: {GPKG_PATH}")
    p("=" * 70)

    conn = sqlite3.connect(GPKG_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ===== 1. 列出所有表 =====
    p("\n" + "=" * 70)
    p("1. 表结构分析")
    p("=" * 70)

    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    all_tables = [row[0] for row in c.fetchall()]
    p(f"\n所有表 ({len(all_tables)}): {all_tables}")

    # gpkg_contents
    try:
        c.execute("SELECT table_name, data_type, identifier FROM gpkg_contents")
        p("\ngpkg_contents:")
        for row in c.fetchall():
            p(f"  {row['table_name']}: type={row['data_type']}, id={row['identifier']}")
    except Exception:
        p("\ngpkg_contents 表不存在")

    # gpkg_geometry_columns
    try:
        c.execute("SELECT table_name, column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns")
        p("\ngpkg_geometry_columns:")
        for row in c.fetchall():
            p(f"  {row['table_name']}: geom_col={row['column_name']}, type={row['geometry_type_name']}, srs={row['srs_id']}")
    except Exception:
        p("\ngpkg_geometry_columns 表不存在")

    # ===== 2. 各数据表字段信息 =====
    key_tables = ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

    for table_name in key_tables:
        if table_name not in all_tables:
            continue

        p(f"\n{'─' * 50}")
        p(f"表: {table_name}")
        p(f"{'─' * 50}")

        c.execute(f"PRAGMA table_info({table_name})")
        columns = c.fetchall()
        p(f"字段 ({len(columns)}):")
        for col in columns:
            p(f"  {col['name']} ({col['type']})")

        c.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = c.fetchone()[0]
        p(f"总记录数: {count}")

    # ===== 3. 关键字段取值分布 =====
    p("\n" + "=" * 70)
    p("2. 关键字段取值分布")
    p("=" * 70)

    # --- points 表 ---
    if 'points' in all_tables:
        p(f"\n{'─' * 50}")
        p("points 表分析")
        p(f"{'─' * 50}")

        c.execute("SELECT COUNT(*) FROM points")
        p(f"总点数: {c.fetchone()[0]}")

        c.execute("SELECT COUNT(*) FROM points WHERE name IS NOT NULL AND name != ''")
        p(f"有名称的点: {c.fetchone()[0]}")

        # railway 字段
        try:
            c.execute("SELECT railway, COUNT(*) as cnt FROM points WHERE railway IS NOT NULL AND railway != '' GROUP BY railway ORDER BY cnt DESC")
            p("\nrailway 字段取值分布:")
            for row in c.fetchall():
                p(f"  {row['railway']}: {row['cnt']}")
        except Exception:
            p("\nrailway 字段不存在")

        # other_tags 中 railway 的取值
        p("\nother_tags 中 railway 取值分布:")
        c.execute("SELECT other_tags FROM points WHERE other_tags LIKE '%railway%' LIMIT 50000")
        railway_counter = Counter()
        for row in c.fetchall():
            tags = parse_other_tags(row['other_tags'])
            if 'railway' in tags:
                railway_counter[tags['railway']] += 1
        for val, cnt in railway_counter.most_common(20):
            p(f"  {val}: {cnt}")

    # --- lines 表 ---
    if 'lines' in all_tables:
        p(f"\n{'─' * 50}")
        p("lines 表分析")
        p(f"{'─' * 50}")

        c.execute("SELECT COUNT(*) FROM lines")
        p(f"总线段数: {c.fetchone()[0]}")

        c.execute("SELECT COUNT(*) FROM lines WHERE name IS NOT NULL AND name != ''")
        p(f"有名称的线段: {c.fetchone()[0]}")

        # railway 字段
        try:
            c.execute("SELECT railway, COUNT(*) as cnt FROM lines WHERE railway IS NOT NULL AND railway != '' GROUP BY railway ORDER BY cnt DESC")
            p("\nrailway 字段取值分布:")
            for row in c.fetchall():
                p(f"  {row['railway']}: {row['cnt']}")
        except Exception:
            p("\nrailway 字段不存在")

        # other_tags 中 railway 的取值
        p("\nother_tags 中 railway 取值分布:")
        c.execute("SELECT other_tags FROM lines WHERE other_tags LIKE '%railway%' LIMIT 100000")
        railway_counter = Counter()
        for row in c.fetchall():
            tags = parse_other_tags(row['other_tags'])
            if 'railway' in tags:
                railway_counter[tags['railway']] += 1
        for val, cnt in railway_counter.most_common(30):
            p(f"  {val}: {cnt}")

    # --- multilinestrings 表 ---
    if 'multilinestrings' in all_tables:
        p(f"\n{'─' * 50}")
        p("multilinestrings 表分析")
        p(f"{'─' * 50}")

        c.execute("SELECT COUNT(*) FROM multilinestrings")
        p(f"总多线段数: {c.fetchone()[0]}")

        c.execute("SELECT COUNT(*) FROM multilinestrings WHERE name IS NOT NULL AND name != ''")
        p(f"有名称的多线段: {c.fetchone()[0]}")

        # type 字段
        try:
            c.execute("SELECT type, COUNT(*) as cnt FROM multilinestrings WHERE type IS NOT NULL AND type != '' GROUP BY type ORDER BY cnt DESC")
            p("\ntype 字段取值分布:")
            for row in c.fetchall():
                p(f"  {row['type']}: {row['cnt']}")
        except Exception:
            p("\ntype 字段不存在")

        # other_tags 中 route 的取值
        p("\nother_tags 中 route 取值分布:")
        c.execute("SELECT other_tags FROM multilinestrings WHERE other_tags LIKE '%route%' LIMIT 100000")
        route_counter = Counter()
        for row in c.fetchall():
            tags = parse_other_tags(row['other_tags'])
            if 'route' in tags:
                route_counter[tags['route']] += 1
        for val, cnt in route_counter.most_common(20):
            p(f"  {val}: {cnt}")

        # other_tags 中 railway 的取值
        p("\nother_tags 中 railway 取值分布:")
        c.execute("SELECT other_tags FROM multilinestrings WHERE other_tags LIKE '%railway%' LIMIT 100000")
        railway_counter = Counter()
        for row in c.fetchall():
            tags = parse_other_tags(row['other_tags'])
            if 'railway' in tags:
                railway_counter[tags['railway']] += 1
        for val, cnt in railway_counter.most_common(20):
            p(f"  {val}: {cnt}")

    # ===== 4. 铁路路线数据质量评估 =====
    p("\n" + "=" * 70)
    p("3. 铁路路线数据质量评估 (multilinestrings, route=railway)")
    p("=" * 70)

    c.execute("""
        SELECT fid, name, other_tags, geom FROM multilinestrings
        WHERE other_tags LIKE '%"route"=>"railway"%'
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)
    route_rows = c.fetchall()
    p(f"\nroute=railway 且有名称的路线数: {len(route_rows)}")

    # 分析每条路线
    route_stats = []
    name_counter = Counter()

    for row in route_rows:
        name = row['name']
        tags = parse_other_tags(row['other_tags'])
        points = parse_geometry_points(row['geom'])

        name_counter[name] += 1

        if not points:
            route_stats.append({
                'name': name, 'fid': row['fid'], 'point_count': 0,
                'total_km': 0, 'abnormal_coords': 0
            })
            continue

        total_len = trajectory_length(points)
        abnormal = sum(1 for x, y in points if not (70 <= x <= 140 and 15 <= y <= 55))

        route_stats.append({
            'name': name, 'fid': row['fid'], 'point_count': len(points),
            'total_km': round(total_len, 1), 'abnormal_coords': abnormal
        })

    # 重复路线名统计
    p(f"\n路线名重复统计 (同名多轨道):")
    multi_name = [(name, cnt) for name, cnt in name_counter.most_common() if cnt > 1]
    p(f"  有重复名称的路线: {len(multi_name)} 个")
    for name, cnt in multi_name[:30]:
        p(f"  {name}: {cnt} 条轨道")

    # 路线质量统计
    p(f"\n路线质量统计:")
    if route_stats:
        p(f"  总路线数: {len(route_stats)}")
        p(f"  有几何数据的: {sum(1 for r in route_stats if r['point_count'] > 0)}")
        p(f"  总坐标点数: {sum(r['point_count'] for r in route_stats)}")
        p(f"  总长度: {sum(r['total_km'] for r in route_stats):.0f} km")
        p(f"  异常坐标路线数: {sum(1 for r in route_stats if r['abnormal_coords'] > 0)}")

        route_stats.sort(key=lambda x: -x['total_km'])
        p(f"\n  最长路线 Top 30:")
        for r in route_stats[:30]:
            p(f"    {r['name']} (fid={r['fid']}): {r['point_count']}点, {r['total_km']}km, 异常{r['abnormal_coords']}个")

        route_stats.sort(key=lambda x: x['total_km'])
        p(f"\n  最短路线 Top 20 (可能是噪声):")
        for r in route_stats[:20]:
            p(f"    {r['name']} (fid={r['fid']}): {r['point_count']}点, {r['total_km']}km")

    # lines 表中按名称分组
    if 'lines' in all_tables:
        p(f"\n{'─' * 50}")
        p("lines 表中 railway=rail 按名称分组 Top 30")
        p(f"{'─' * 50}")
        try:
            c.execute("""
                SELECT name, COUNT(*) as cnt FROM lines
                WHERE railway = 'rail' AND name IS NOT NULL AND name != ''
                GROUP BY name ORDER BY cnt DESC LIMIT 30
            """)
            for row in c.fetchall():
                p(f"  {row['name']}: {row['cnt']} 条线段")
        except Exception:
            p("查询失败")

    conn.close()

    # 保存报告
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    p(f"\n报告已保存到: {REPORT_PATH}")


if __name__ == '__main__':
    main()
