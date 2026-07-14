"""
构建相邻站点间采样路线段缓存和站对-路线索引

输入：
  data/station_coords.json         - 站点名 → [经度, 纬度]
  data/cleaned_route_geometries.json - 路线名 → {trajectory, stations, ...}

输出：
  data/segment_cache.pkl           - {(station_a, station_b, route_name): [[lng, lat], ...]}
  data/station_pair_route_index.json - {"station_a|station_b": [route_name, ...]}
  data/station_route_index.json    - {"station_name": [route_name, ...]}
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import math
import pickle
from tqdm import tqdm

DATA_DIR = r"d:\PyCharm\Railway-8620\data"
STATION_INPUT = os.path.join(DATA_DIR, 'station_coords.json')
ROUTE_INPUT = os.path.join(DATA_DIR, 'cleaned_route_geometries.json')
SEGMENT_OUTPUT = os.path.join(DATA_DIR, 'segment_cache.pkl')
PAIR_INDEX_OUTPUT = os.path.join(DATA_DIR, 'station_pair_route_index.json')
STATION_INDEX_OUTPUT = os.path.join(DATA_DIR, 'station_route_index.json')


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


def find_nearest_idx(station_coord, trajectory, max_check=1000):
    """找到站点在轨迹上最近点的索引"""
    if not trajectory:
        return -1
    # 降采样以加速
    step = max(1, len(trajectory) // max_check)
    search = trajectory[::step]

    best_dist = float('inf')
    best_search_idx = 0
    for i, pt in enumerate(search):
        d = haversine_km(station_coord[0], station_coord[1], pt[0], pt[1])
        if d < best_dist:
            best_dist = d
            best_search_idx = i

    # 精细搜索周围
    orig_idx = best_search_idx * step
    best_orig_idx = orig_idx
    best_orig_dist = float('inf')
    start = max(0, orig_idx - step)
    end = min(len(trajectory), orig_idx + step + 1)
    for i in range(start, end):
        pt = trajectory[i]
        d = haversine_km(station_coord[0], station_coord[1], pt[0], pt[1])
        if d < best_orig_dist:
            best_orig_dist = d
            best_orig_idx = i

    return best_orig_idx, best_orig_dist


def extract_segment(trajectory, idx_a, idx_b):
    """从轨迹中提取两个索引之间的线段"""
    if idx_a == idx_b:
        return [trajectory[idx_a]]

    if idx_a < idx_b:
        segment = trajectory[idx_a:idx_b + 1]
    else:
        segment = list(reversed(trajectory[idx_b:idx_a + 1]))

    return [list(p) for p in segment]


def downsample_segment(points, points_per_100km=25):
    """等距降采样：每100km约25个点"""
    if len(points) <= 2:
        return [list(p) for p in points]

    total_km = traj_length(points)
    target_count = max(2, int(total_km / 100.0 * points_per_100km))

    if target_count >= len(points):
        return [list(p) for p in points]

    # 累计距离采样
    cumulative = [0.0]
    for i in range(len(points) - 1):
        d = haversine_km(points[i][0], points[i][1],
                         points[i + 1][0], points[i + 1][1])
        cumulative.append(cumulative[-1] + d)

    total_dist = cumulative[-1]
    if total_dist < 0.01:
        return [list(p) for p in points]

    step = total_dist / (target_count - 1)
    result = [list(points[0])]

    next_target = step
    for i in range(1, len(points) - 1):
        if cumulative[i] >= next_target:
            result.append(list(points[i]))
            next_target += step

    # 确保首尾是站点坐标
    result[0] = list(points[0])
    result.append(list(points[-1]))

    return result


def main():
    print("=" * 70)
    print("构建站对-路线索引和采样线段缓存")
    print("=" * 70)

    # ===== 加载数据 =====
    print("\n[1/4] 加载数据...")
    with open(STATION_INPUT, 'r', encoding='utf-8') as f:
        station_coords = json.load(f)
    print(f"  站点数: {len(station_coords)}")

    with open(ROUTE_INPUT, 'r', encoding='utf-8') as f:
        route_geometries = json.load(f)
    print(f"  路线数: {len(route_geometries)}")

    # ===== 站点位置定位 =====
    print("\n[2/4] 定位站点在路线上的位置...")

    segment_cache = {}
    pair_index = {}  # "station_a|station_b" → [route_name, ...]
    station_index = {}  # station_name → [route_name, ...]

    stats = {
        'routes_processed': 0,
        'routes_with_stations': 0,
        'segments_extracted': 0,
        'segments_too_long': 0,
        'segments_empty': 0,
        'total_segments_points': 0,
    }

    for route_name, route_info in tqdm(route_geometries.items(), desc="  构建缓存", unit="条"):
        stats['routes_processed'] += 1
        stations = route_info.get('stations', [])
        trajectory = route_info['trajectory']

        if not stations or len(stations) < 2:
            continue

        if not trajectory or len(trajectory) < 2:
            continue

        stats['routes_with_stations'] += 1

        # 找每个站点在轨迹上的位置
        station_indices = []
        for st_name in stations:
            if st_name not in station_coords:
                continue
            st_coord = station_coords[st_name]
            idx, dist = find_nearest_idx(st_coord, trajectory)
            if idx >= 0 and dist <= 5.0:  # 5km 阈值
                station_indices.append((st_name, idx, dist))

        if len(station_indices) < 2:
            continue

        # 按轨迹位置排序
        station_indices.sort(key=lambda x: x[1])

        # 构建站对索引
        for i in range(len(station_indices) - 1):
            st_a = station_indices[i][0]
            st_b = station_indices[i + 1][0]
            idx_a = station_indices[i][1]
            idx_b = station_indices[i + 1][1]

            if idx_a == idx_b:
                continue

            # 提取线段
            segment = extract_segment(trajectory, idx_a, idx_b)

            if not segment or len(segment) < 2:
                stats['segments_empty'] += 1
                continue

            # 质量检查：线段长度 vs 站间直线距离
            seg_len = traj_length(segment)
            st_a_coord = station_coords[st_a]
            st_b_coord = station_coords[st_b]
            direct_dist = haversine_km(st_a_coord[0], st_a_coord[1],
                                       st_b_coord[0], st_b_coord[1])
            if direct_dist < 0.1:
                continue

            # 如果线段长度 > 直线距离的 5 倍，可能跨平行轨道，跳过
            if seg_len > direct_dist * 3:
                stats['segments_too_long'] += 1
                continue

            # 降采样
            downsampled = downsample_segment(segment, points_per_100km=25)

            # 存入缓存
            cache_key = (st_a, st_b, route_name)
            segment_cache[cache_key] = downsampled

            # 站对索引
            pair_key = f"{st_a}|{st_b}"
            if pair_key not in pair_index:
                pair_index[pair_key] = []
            if route_name not in pair_index[pair_key]:
                pair_index[pair_key].append(route_name)

            # 反向站对也记录
            pair_key_rev = f"{st_b}|{st_a}"
            if pair_key_rev not in pair_index:
                pair_index[pair_key_rev] = []
            if route_name not in pair_index[pair_key_rev]:
                pair_index[pair_key_rev].append(route_name)

            # 站点索引
            for st in [st_a, st_b]:
                if st not in station_index:
                    station_index[st] = []
                if route_name not in station_index[st]:
                    station_index[st].append(route_name)

            stats['segments_extracted'] += 1
            stats['total_segments_points'] += len(downsampled)

    print(f"\n  统计:")
    print(f"    处理路线: {stats['routes_processed']}")
    print(f"    有站点路线: {stats['routes_with_stations']}")
    print(f"    提取线段: {stats['segments_extracted']}")
    print(f"    线段过长(跳过): {stats['segments_too_long']}")
    print(f"    空线段: {stats['segments_empty']}")
    print(f"    总采样点数: {stats['total_segments_points']}")
    print(f"    站对数: {len(pair_index)}")
    print(f"    站点覆盖: {len(station_index)}")

    # ===== 保存 =====
    print("\n[3/4] 保存缓存...")
    with open(SEGMENT_OUTPUT, 'wb') as f:
        pickle.dump(segment_cache, f)
    file_size = os.path.getsize(SEGMENT_OUTPUT) / (1024 * 1024)
    print(f"  segment_cache.pkl: {file_size:.1f} MB ({len(segment_cache)} segments)")

    with open(PAIR_INDEX_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(pair_index, f, ensure_ascii=False)
    print(f"  station_pair_route_index.json: {len(pair_index)} pairs")

    with open(STATION_INDEX_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(station_index, f, ensure_ascii=False)
    print(f"  station_route_index.json: {len(station_index)} stations")

    # ===== 样例 =====
    print("\n[4/4] 样例:")
    sample_trains = ['京沪高速线', '京广高速线', '京九线', '陇海线']
    for route_name in sample_trains:
        if route_name not in route_geometries:
            continue
        route_stations = route_geometries[route_name].get('stations', [])
        route_segments = [(k, len(v)) for k, v in segment_cache.items()
                          if k[2] == route_name]
        print(f"  {route_name}: {len(route_stations)}站, {len(route_segments)}段")
        if route_segments:
            for k, cnt in route_segments[:5]:
                seg = segment_cache[k]
                seg_len = traj_length(seg)
                print(f"    {k[0]}→{k[1]}: {cnt}点, {seg_len:.1f}km")

    # 站对样例
    print("\n  站对样例:")
    sample_pairs = []
    for pair_key, routes in pair_index.items():
        if len(routes) > 1:
            sample_pairs.append((pair_key, routes))
    sample_pairs.sort(key=lambda x: -len(x[1]))
    for pair_key, routes in sample_pairs[:10]:
        st_a, st_b = pair_key.split('|')
        print(f"    {st_a}→{st_b}: {', '.join(routes)}")

    print("\n完成!")


if __name__ == '__main__':
    main()
