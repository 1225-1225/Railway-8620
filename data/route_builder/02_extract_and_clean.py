"""
从 china_output.gpkg 提取铁路路线和站点坐标，进行多轨道去噪

输出：
  data/station_coords.json        - 站点名 → [经度, 纬度]
  data/cleaned_route_geometries.json - 路线名 → {轨迹, 元数据, 站点列表}
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import re
import struct
import math
import json
from tqdm import tqdm

GPKG_PATH = r"d:\PyCharm\Railway-8620\data\pbf\china_output.gpkg"
DATA_DIR = r"d:\PyCharm\Railway-8620\data"
STATION_OUTPUT = os.path.join(DATA_DIR, 'station_coords.json')
ROUTE_OUTPUT = os.path.join(DATA_DIR, 'cleaned_route_geometries.json')


# ─── GPKG 几何解析 ──────────────────────────────────────────

def get_wkb_from_gpkg(blob):
    """从 GPKG blob 提取 WKB，正确处理 envelope"""
    if not blob or blob[:2] != b'GP':
        return None
    flags = blob[3]
    envelope_indicator = (flags >> 1) & 0x07
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    envelope_bytes = envelope_sizes.get(envelope_indicator, 0)
    return blob[8 + envelope_bytes:]


def parse_other_tags(tags_str):
    """解析 OSM other_tags: "key"=>"value" 格式"""
    result = {}
    if not tags_str:
        return result
    for m in re.finditer(r'"([^"]+)"\s*=>\s*"([^"]*)"', tags_str):
        result[m.group(1)] = m.group(2)
    return result


def parse_multilinestring_sublines(blob):
    """解析 GPKG MultiLineString，返回子线段列表 [[(lng, lat), ...], ...]"""
    wkb = get_wkb_from_gpkg(blob)
    if not wkb or len(wkb) < 5:
        return []

    bo = wkb[0]
    endian = '<' if (bo & 0x01) else '>'
    raw_type = struct.unpack(f'{endian}I', wkb[1:5])[0]
    base_type = raw_type & 0xFFFF

    offset = 5
    sublines = []

    if base_type == 5:  # MultiLineString
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
                pts = []
                for j in range(sub_num):
                    if offset + 16 > len(wkb):
                        break
                    x = round(struct.unpack(f'{sub_endian}d', wkb[offset:offset + 8])[0], 6)
                    y = round(struct.unpack(f'{sub_endian}d', wkb[offset + 8:offset + 16])[0], 6)
                    pts.append((x, y))
                    offset += 16
                if pts:
                    sublines.append(pts)
            else:
                break

    elif base_type == 2:  # LineString
        num_pts = struct.unpack(f'{endian}I', wkb[offset:offset + 4])[0]
        offset += 4
        pts = []
        for j in range(num_pts):
            if offset + 16 > len(wkb):
                break
            x = round(struct.unpack(f'{endian}d', wkb[offset:offset + 8])[0], 6)
            y = round(struct.unpack(f'{endian}d', wkb[offset + 8:offset + 16])[0], 6)
            pts.append((x, y))
            offset += 16
        if pts:
            sublines.append(pts)

    return sublines


def parse_point_geom(blob):
    """解析 GPKG POINT"""
    wkb = get_wkb_from_gpkg(blob)
    if not wkb or len(wkb) < 21:
        return None
    bo = wkb[0]
    endian = '<' if (bo & 0x01) else '>'
    geom_type = struct.unpack(f'{endian}I', wkb[1:5])[0]
    if geom_type != 1:
        return None
    x = struct.unpack(f'{endian}d', wkb[5:13])[0]
    y = struct.unpack(f'{endian}d', wkb[13:21])[0]
    return (round(x, 6), round(y, 6))


# ─── 距离与轨迹工具 ────────────────────────────────────────

def haversine_km(lng1, lat1, lng2, lat2):
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def traj_length(points):
    total = 0.0
    for i in range(len(points) - 1):
        total += haversine_km(points[i][0], points[i][1],
                              points[i + 1][0], points[i + 1][1])
    return total


# ─── 多轨道去噪 ─────────────────────────────────────────────

def merge_sublines(sublines, threshold_km=1.5):
    """贪心合并子线段：从最长开始，逐步连接端点距离 < threshold 的子线段"""
    if not sublines:
        return [], []

    sublines = sorted(sublines, key=lambda s: -traj_length(s))
    merged = list(sublines[0])
    remaining = list(sublines[1:])

    changed = True
    while changed and remaining:
        changed = False
        best_dist = threshold_km
        best_idx = -1
        best_mode = None

        for i, sub in enumerate(remaining):
            # Case 1: sub[0] → merged[-1]（正向追加）
            d = haversine_km(sub[0][0], sub[0][1], merged[-1][0], merged[-1][1])
            if d < best_dist:
                best_dist, best_idx, best_mode = d, i, 'append_fwd'
            # Case 2: sub[-1] → merged[-1]（反向追加）
            d = haversine_km(sub[-1][0], sub[-1][1], merged[-1][0], merged[-1][1])
            if d < best_dist:
                best_dist, best_idx, best_mode = d, i, 'append_rev'
            # Case 3: sub[-1] → merged[0]（正向前插）
            d = haversine_km(sub[-1][0], sub[-1][1], merged[0][0], merged[0][1])
            if d < best_dist:
                best_dist, best_idx, best_mode = d, i, 'prepend_fwd'
            # Case 4: sub[0] → merged[0]（反向前插）
            d = haversine_km(sub[0][0], sub[0][1], merged[0][0], merged[0][1])
            if d < best_dist:
                best_dist, best_idx, best_mode = d, i, 'prepend_rev'

        if best_idx >= 0:
            sub = remaining.pop(best_idx)
            if best_mode == 'append_fwd':
                merged.extend(sub[1:])
            elif best_mode == 'append_rev':
                merged.extend(reversed(sub[:-1]))
            elif best_mode == 'prepend_fwd':
                merged = list(sub[:-1]) + merged
            elif best_mode == 'prepend_rev':
                merged = list(reversed(sub[1:])) + merged
            changed = True

    return merged, remaining


def simplify_trajectory(points, min_dist_deg=0.0005):
    """简化轨迹：移除距离过近的点（~50m）"""
    if len(points) <= 2:
        return points
    result = [points[0]]
    for i in range(1, len(points) - 1):
        dlng = points[i][0] - result[-1][0]
        dlat = points[i][1] - result[-1][1]
        if abs(dlng) >= min_dist_deg or abs(dlat) >= min_dist_deg:
            result.append(points[i])
    result.append(points[-1])
    return result


def _min_dist_to_traj(point, traj, max_check=500):
    """计算点到轨迹的最近距离（km），降采样以加速"""
    step = max(1, len(traj) // max_check)
    search = traj[::step]
    return min(haversine_km(point[0], point[1], p[0], p[1]) for p in search)


def _is_parallel(sub, main_traj, sample_step=50):
    """检测子线段是否与主线平行（重合）。
    只检测长子线段（避免误杀延伸段），且要求所有采样点都在主线附近。
    """
    if not main_traj or len(sub) < 2:
        return False

    # 只对长度 > 主线 30% 的子线段做平行检测（短线段可能是延伸）
    sub_len = traj_length(sub)
    main_len = traj_length(main_traj)
    if main_len > 0 and sub_len < main_len * 0.3:
        return False

    # 采样主线用于距离计算
    search = main_traj[::sample_step] if len(main_traj) > sample_step * 10 else main_traj

    # 检查子线段的起点、中点、终点是否都在主线 1.5km 内
    check_points = [sub[0], sub[len(sub) // 2], sub[-1]]
    matches = 0
    for cp in check_points:
        for mp in search:
            d = haversine_km(cp[0], cp[1], mp[0], mp[1])
            if d < 1.5:
                matches += 1
                break
    return matches >= 3  # 3个点全部在主线附近 → 平行


def dedup_reversed_sublines(sublines):
    """去除反向重复的子线段（上下行正线的重复）。
    对每个子线段，用排序后的端点作为 key 去重。
    """
    seen = set()
    result = []
    for sub in sublines:
        if len(sub) < 2:
            result.append(sub)
            continue
        # 用排序后的端点作为 key（保留 3 位小数）
        p1 = (round(sub[0][0], 3), round(sub[0][1], 3))
        p2 = (round(sub[-1][0], 3), round(sub[-1][1], 3))
        key = tuple(sorted([p1, p2]))
        if key not in seen:
            seen.add(key)
            result.append(sub)
    return result


def merge_sublines_spatial(sublines):
    """空间排序合并：按主方向投影排序子线段，然后顺序连接。
    适用于子线段有大间隙但整体方向一致的情况。
    """
    if not sublines:
        return []

    # 计算每个子线段的中点
    midpoints = []
    for sub in sublines:
        if len(sub) < 2:
            continue
        mid_idx = len(sub) // 2
        midpoints.append((sub[mid_idx], sub))

    if not midpoints:
        return []

    # 确定主方向（经度跨度 vs 纬度跨度）
    all_lngs = [mp[0][0] for mp in midpoints]
    all_lats = [mp[0][1] for mp in midpoints]
    lng_range = max(all_lngs) - min(all_lngs)
    lat_range = max(all_lats) - min(all_lats)

    if lat_range >= lng_range:
        # 南北向路线，按纬度排序
        midpoints.sort(key=lambda x: x[0][1])
    else:
        # 东西向路线，按经度排序
        midpoints.sort(key=lambda x: x[0][0])

    # 顺序连接：对每对相邻子线段，选择连接方向
    merged = list(midpoints[0][1])
    used = {0}

    for _ in range(len(midpoints) * 2):  # 多轮以确保连接
        best_dist = 30.0  # 30km 阈值
        best_idx = -1
        best_mode = None

        for i, (mp, sub) in enumerate(midpoints):
            if i in used:
                continue
            if len(sub) < 2:
                continue
            # 检查 4 种连接方式
            for mode, sp, ref in [('af', sub[0], merged[-1]),
                                   ('ar', sub[-1], merged[-1]),
                                   ('pf', sub[-1], merged[0]),
                                   ('pr', sub[0], merged[0])]:
                d = haversine_km(sp[0], sp[1], ref[0], ref[1])
                if d < best_dist:
                    best_dist, best_idx, best_mode = d, i, mode

        if best_idx < 0:
            break

        sub = midpoints[best_idx][1]
        used.add(best_idx)
        if best_mode == 'af':
            merged.extend(sub[1:])
        elif best_mode == 'ar':
            merged.extend(reversed(sub[:-1]))
        elif best_mode == 'pf':
            merged = list(sub[:-1]) + merged
        elif best_mode == 'pr':
            merged = list(reversed(sub[1:])) + merged

    return merged


def filter_sublines_by_bbox(sublines, route_bbox, margin_deg=0.08):
    """用 lines 表 railway='rail' 的 bbox 过滤偏离主线太远的子线段"""
    if not route_bbox:
        return sublines, 0
    min_lng, max_lng, min_lat, max_lat = route_bbox
    before = len(sublines)
    filtered = []
    for sub in sublines:
        if not sub:
            continue
        # 取子线段中点
        mid_idx = len(sub) // 2
        c_lng, c_lat = sub[mid_idx][0], sub[mid_idx][1]
        if (min_lng - margin_deg <= c_lng <= max_lng + margin_deg and
                min_lat - margin_deg <= c_lat <= max_lat + margin_deg):
            filtered.append(sub)
    if not filtered:
        return sublines, 0  # 全被过滤了反而说明 bbox 有问题，保留原数据
    return filtered, before - len(filtered)


def denoise_route(sublines):
    """去噪：去除反向重复 → 过滤短线段 → 贪心合并 → 简化"""
    if not sublines:
        return []

    # 去除反向重复子线段（上下行正线）
    sublines = dedup_reversed_sublines(sublines)

    # 计算各子线段长度
    sub_lens = [(sub, traj_length(sub)) for sub in sublines]

    # 过滤短于 5km 的子线段（侧线、联络线等噪声）
    long_subs = [s for s, l in sub_lens if l >= 5.0]
    if not long_subs:
        sub_lens.sort(key=lambda x: -x[1])
        long_subs = [s for s, _ in sub_lens[:5]]

    total_sub_len = sum(l for _, l in sub_lens if l >= 5.0)

    # 贪心合并：逐步增大阈值
    best_merged = []
    best_len = 0

    for threshold in [10, 30, 50, 100]:
        merged, remaining = merge_sublines(long_subs, threshold_km=threshold)
        merged_len = traj_length(merged)
        if merged_len > best_len:
            best_merged = merged
            best_len = merged_len
        if best_len >= total_sub_len * 0.7:
            break

    merged = best_merged

    # 简化
    merged = simplify_trajectory(merged)

    # 限制最大点数
    if len(merged) > 15000:
        step = len(merged) // 15000
        merged = merged[::step][:15000]

    return merged


# ─── 站名规范化 ─────────────────────────────────────────────

def normalize_name(name):
    """规范化名称：去空格、去站后缀"""
    name = name.strip()
    if name.endswith('站'):
        name = name[:-1]
    return name


# ─── 站点-路线空间匹配 ─────────────────────────────────────

def find_stations_on_route(trajectory, station_coords, max_dist_km=5.0):
    """找出轨迹沿线的站点，按沿轨迹位置排序"""
    if not trajectory or not station_coords:
        return []

    # 轨迹 bbox
    lngs = [p[0] for p in trajectory]
    lats = [p[1] for p in trajectory]
    margin = 0.03  # ~3km
    min_lng, max_lng = min(lngs) - margin, max(lngs) + margin
    min_lat, max_lat = min(lats) - margin, max(lats) + margin

    # 如果轨迹过长，降采样用于匹配
    search_traj = trajectory
    if len(trajectory) > 2000:
        step = len(trajectory) // 2000
        search_traj = trajectory[::step]

    # 筛选 bbox 内的站点
    candidates = []
    for name, coord in station_coords.items():
        if min_lng <= coord[0] <= max_lng and min_lat <= coord[1] <= max_lat:
            candidates.append((name, coord[0], coord[1]))

    if not candidates:
        return []

    # 对每个候选站点，找最近轨迹点
    result = []
    max_dist_deg_sq = (max_dist_km / 111.0) ** 2

    for name, s_lng, s_lat in candidates:
        best_dist_sq = float('inf')
        best_idx = 0
        for i, (tlng, tlat) in enumerate(search_traj):
            dlng = s_lng - tlng
            dlat = s_lat - tlat
            dist_sq = dlng * dlng + dlat * dlat
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_idx = i

        # 实际距离检查
        if best_dist_sq < max_dist_deg_sq:
            actual_km = haversine_km(s_lng, s_lat,
                                      search_traj[best_idx][0],
                                      search_traj[best_idx][1])
            if actual_km <= max_dist_km:
                result.append((name, best_idx, actual_km))

    result.sort(key=lambda x: x[1])
    return [(r[0], round(r[2], 2)) for r in result]


# ─── lines 表辅助 ──────────────────────────────────────────

def parse_linestring_geom(blob):
    """解析 GPKG LINESTRING，返回点列表 [(lng, lat), ...]"""
    wkb = get_wkb_from_gpkg(blob)
    if not wkb or len(wkb) < 9:
        return []
    endian = '<' if (wkb[0] & 0x01) else '>'
    geom_type = struct.unpack(f'{endian}I', wkb[1:5])[0]
    base_type = geom_type & 0xFFFF
    if base_type != 2:
        return []
    num_pts = struct.unpack(f'{endian}I', wkb[5:9])[0]
    pts = []
    offset = 9
    for j in range(num_pts):
        if offset + 16 > len(wkb):
            break
        x = round(struct.unpack(f'{endian}d', wkb[offset:offset + 8])[0], 6)
        y = round(struct.unpack(f'{endian}d', wkb[offset + 8:offset + 16])[0], 6)
        pts.append((x, y))
        offset += 16
    return pts


def load_lines_bbox(c):
    """从 lines 表加载 railway='rail' 的各路线 bbox（利用 rtree 空间索引）"""
    print("\n  加载 lines 表 railway='rail' 的路线 bbox...")
    c.execute("""
        SELECT l.name,
               MIN(r.minx) as min_lng, MAX(r.maxx) as max_lng,
               MIN(r.miny) as min_lat, MAX(r.maxy) as max_lat
        FROM lines l
        JOIN rtree_lines_geom r ON l.fid = r.id
        WHERE l.railway = 'rail' AND l.name IS NOT NULL AND l.name != ''
        GROUP BY l.name
    """)
    rows = c.fetchall()
    bbox_map = {}
    for row in rows:
        name = row[0]
        min_lng = row[1]; max_lng = row[2]
        min_lat = row[3]; max_lat = row[4]
        if min_lng < 70 or max_lng > 140 or min_lat < 15 or max_lat > 55:
            continue
        bbox_map[name] = (min_lng, max_lng, min_lat, max_lat)
    print(f"    加载 {len(bbox_map)} 条路线的 bbox")
    return bbox_map


def load_lines_trajectory(c, name, limit=10000):
    """从 lines 表读取同名 railway='rail' 的所有线段，拼接成完整轨迹"""
    c.execute("SELECT geom FROM lines WHERE railway = 'rail' AND name = ? LIMIT ?", (name, limit))
    rows = c.fetchall()
    if not rows:
        return None
    sublines = []
    for row in rows:
        pts = parse_linestring_geom(row[0])
        if pts and len(pts) >= 2:
            sublines.append(pts)
    if not sublines:
        return None

    # lines 表每条线段是短 OSM way（1-3km），包含上下行正线
    # 先用 endpoint 去重（去除反向重复的上下行）
    sublines = dedup_reversed_sublines(sublines)

    # 再用中点去重：如果两条线段的中点 < 200m，保留较长的
    with_mid = []
    for sub in sublines:
        mid = sub[len(sub) // 2]
        with_mid.append((mid, sub))
    with_mid.sort(key=lambda x: (round(x[0][1], 3), round(x[0][0], 3)))
    deduped = []
    last_mid = None
    last_sub = None
    for mid, sub in with_mid:
        if last_mid:
            d = haversine_km(last_mid[0], last_mid[1], mid[0], mid[1])
            if d < 0.2:  # 200m 内 → 平行轨道，保留较长的
                if last_sub and len(sub) > len(last_sub):
                    deduped[-1] = sub
                    last_sub = sub
                continue
        deduped.append(sub)
        last_mid = mid
        last_sub = sub
    sublines = deduped if len(deduped) > 10 else sublines  # 防误杀

    # 按主方向排序后顺序合并
    all_lngs = [p[0] for sub in sublines for p in [sub[0], sub[-1]]]
    all_lats = [p[1] for sub in sublines for p in [sub[0], sub[-1]]]
    lng_span = max(all_lngs) - min(all_lngs)
    lat_span = max(all_lats) - min(all_lats)

    mids = []
    for i, sub in enumerate(sublines):
        if len(sub) < 2:
            continue
        mid_pt = sub[len(sub) // 2]
        mids.append((mid_pt, i))

    if lat_span >= lng_span:
        mids.sort(key=lambda x: x[0][1])
    else:
        mids.sort(key=lambda x: x[0][0])

    merged = []
    for mid_pt, idx in mids:
        sub = sublines[idx]
        if not merged:
            merged = list(sub)
            continue
        d_fwd = haversine_km(merged[-1][0], merged[-1][1], sub[0][0], sub[0][1])
        d_rev = haversine_km(merged[-1][0], merged[-1][1], sub[-1][0], sub[-1][1])
        if d_fwd <= d_rev:
            merged.extend(sub[1:])
        else:
            merged.extend(reversed(sub[:-1]))

    if len(merged) < 2:
        return None

    merged = simplify_trajectory(merged)
    if len(merged) > 15000:
        step = len(merged) // 15000
        merged = merged[::step][:15000]
    return merged


# ─── 主流程 ─────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("提取铁路路线和站点坐标（含去噪）")
    print("=" * 70)

    conn = sqlite3.connect(GPKG_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ===== 1. 提取站点坐标 =====
    print("\n[1/3] 提取站点坐标...")
    c.execute("""
        SELECT fid, name, geom, other_tags FROM points
        WHERE (other_tags LIKE '%"railway"=>"station"%'
            OR other_tags LIKE '%"railway"=>"halt"%')
          AND name IS NOT NULL AND name != ''
    """)

    station_rows = c.fetchall()
    print(f"  查询到 {len(station_rows)} 个铁路站点点")

    station_coords = {}
    for row in station_rows:
        name = normalize_name(row['name'])
        if not name:
            continue
        coord = parse_point_geom(row['geom'])
        if coord is None:
            continue
        lng, lat = coord
        if not (70 <= lng <= 140 and 15 <= lat <= 55):
            continue
        if name not in station_coords:
            station_coords[name] = [lng, lat]

    print(f"  去重后: {len(station_coords)} 个唯一站点")

    with open(STATION_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(station_coords, f, ensure_ascii=False)
    print(f"  已保存: {STATION_OUTPUT}")

    # ===== 2. 提取路线并去噪 =====
    print("\n[2/3] 提取铁路路线并去噪...")

    # 预加载 lines 表 bbox（用于辅助去噪过滤）
    lines_bbox = load_lines_bbox(c)

    c.execute("""
        SELECT fid, name, other_tags, geom FROM multilinestrings
        WHERE other_tags LIKE '%"route"=>"railway"%'
          AND name IS NOT NULL AND name != ''
        ORDER BY name
    """)

    route_rows = c.fetchall()
    print(f"  查询到 {len(route_rows)} 条铁路路线")

    route_geometries = {}
    stats = {'success': 0, 'no_geom': 0, 'empty': 0,
             'total_sublines': 0, 'noise_removed': 0, 'total_points': 0,
             'bbox_unavailable': 0, 'bbox_filtered_sublines': 0,
             'lines_fallback': 0}

    for i, row in enumerate(tqdm(route_rows, desc="  路线去噪", unit="条")):
        name = row['name']
        tags = parse_other_tags(row['other_tags'])
        sublines = parse_multilinestring_sublines(row['geom'])

        if not sublines:
            stats['no_geom'] += 1
            continue

        stats['total_sublines'] += len(sublines)

        # 获取该路线的 lines bbox（如果有）
        route_bbox = lines_bbox.get(name, None)
        if route_bbox is None:
            stats['bbox_unavailable'] += 1

        # 用 lines bbox 预过滤偏离主线的子线段
        sublines, bbox_filtered = filter_sublines_by_bbox(sublines, route_bbox)
        stats['bbox_filtered_sublines'] += bbox_filtered

        # 去噪
        trajectory = denoise_route(sublines)

        # 检查轨迹完整性：如果 multilinestrings 轨迹与 lines bbox 差距过大，用 lines 表重建
        used_lines_fallback = False
        if trajectory and route_bbox:
            traj_lngs = [p[0] for p in trajectory]
            traj_lats = [p[1] for p in trajectory]
            traj_span_lat = max(traj_lats) - min(traj_lats)
            lines_span_lat = route_bbox[3] - route_bbox[2]
            traj_span_lng = max(traj_lngs) - min(traj_lngs)
            lines_span_lng = route_bbox[1] - route_bbox[0]
            lat_ratio = traj_span_lat / lines_span_lat if lines_span_lat > 0 else 1.0
            lng_ratio = traj_span_lng / lines_span_lng if lines_span_lng > 0 else 1.0
            if lat_ratio < 0.5 or lng_ratio < 0.5:
                lines_traj = load_lines_trajectory(c, name)
                if lines_traj and traj_length(lines_traj) > traj_length(trajectory) * 1.2:
                    print(f"    ✓ '{name}' 用 lines 表补充 ({len(lines_traj)}点, {traj_length(lines_traj):.0f}km)")
                    trajectory = lines_traj
                    used_lines_fallback = True
                    stats['lines_fallback'] += 1

        if not trajectory or len(trajectory) < 2:
            stats['empty'] += 1
            continue

        total_km = traj_length(trajectory)

        route_geometries[name] = {
            'name': name,
            'ref': tags.get('ref', ''),
            'from': tags.get('from', ''),
            'to': tags.get('to', ''),
            'trajectory': [[lng, lat] for lng, lat in trajectory],
            'total_km': round(total_km, 1),
            'point_count': len(trajectory)
        }

        stats['success'] += 1
        stats['total_points'] += len(trajectory)

    print(f"\n  去噪统计:")
    print(f"    成功提取: {stats['success']}/{len(route_rows)}")
    print(f"    无几何: {stats['no_geom']}")
    print(f"    去噪后为空: {stats['empty']}")
    print(f"    原始子线段总数: {stats['total_sublines']}")
    print(f"    去噪后总点数: {stats['total_points']}")
    print(f"    lines bbox 可用: {stats['success'] - stats['bbox_unavailable']}/{stats['success']}")
    print(f"    bbox 过滤子线段数: {stats['bbox_filtered_sublines']}")
    print(f"    lines 表补充轨迹: {stats['lines_fallback']} 条路线")

    # ===== 3. 匹配站点到路线 =====
    print("\n[3/3] 匹配站点到路线...")

    for route_name, route_info in tqdm(route_geometries.items(), desc="  站点匹配", unit="条"):
        traj = [(p[0], p[1]) for p in route_info['trajectory']]
        stations = find_stations_on_route(traj, station_coords, max_dist_km=5.0)
        route_info['stations'] = [s[0] for s in stations]
        route_info['station_count'] = len(stations)

    # 统计
    station_counts = [r['station_count'] for r in route_geometries.values()]
    if station_counts:
        print(f"\n  站点匹配统计:")
        print(f"    平均站点数/路线: {sum(station_counts)/len(station_counts):.1f}")
        print(f"    最多: {max(station_counts)}, 最少: {min(station_counts)}")
        print(f"    无站点路线: {sum(1 for s in station_counts if s == 0)}")

    # 保存
    with open(ROUTE_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(route_geometries, f, ensure_ascii=False)

    file_size = os.path.getsize(ROUTE_OUTPUT) / (1024 * 1024)
    print(f"\n  已保存: {ROUTE_OUTPUT} ({file_size:.1f} MB)")

    # 打印样例
    print("\n  路线样例:")
    for name in ['京沪高速线', '京广高速线', '京九线', '陇海线', '兰新线',
                 '京沪线', '京广线', '胶济客专线']:
        if name in route_geometries:
            r = route_geometries[name]
            st = r.get('stations', [])
            print(f"    {name}: {r['point_count']}点, {r['total_km']}km, {r['station_count']}站")
            if st:
                print(f"      站点: {', '.join(st[:15])}...")

    conn.close()
    print("\n完成!")


if __name__ == '__main__':
    main()
