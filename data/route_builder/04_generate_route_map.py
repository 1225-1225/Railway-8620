"""
车次路线图生成器
根据车次号，从 OSM 铁路数据中匹配真实轨道走向，生成 folium 交互式地图

用法：
  python 04_generate_route_map.py Z227
  python 04_generate_route_map.py G1 --output D:/maps/

也可作为模块导入：
  from generate_route_map import generate_route_map
  result = generate_route_map('Z227')
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import math
import pickle

DATA_DIR = r"d:\PyCharm\Railway-8620\data"
DEFAULT_OUTPUT_DIR = r"d:\PyCharm\Railway-8620\frontend\public\maps"

TRAIN_DETAILS = os.path.join(DATA_DIR, 'train_details.json')
STATION_COORDS = os.path.join(DATA_DIR, 'station_coords.json')
ROUTE_GEOMETRIES = os.path.join(DATA_DIR, 'cleaned_route_geometries.json')
SEGMENT_CACHE = os.path.join(DATA_DIR, 'segment_cache.pkl')
PAIR_INDEX = os.path.join(DATA_DIR, 'station_pair_route_index.json')
STATION_INDEX = os.path.join(DATA_DIR, 'station_route_index.json')

_data = None


# ─── 工具函数 ───────────────────────────────────────────────

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


def downsample_segment(points, points_per_100km=25):
    if len(points) <= 2:
        return [list(p) for p in points]
    total_km = traj_length(points)
    target_count = max(2, int(total_km / 100.0 * points_per_100km))
    if target_count >= len(points):
        return [list(p) for p in points]

    cumulative = [0.0]
    for i in range(len(points) - 1):
        cumulative.append(cumulative[-1] + haversine_km(
            points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]))

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
    result.append(list(points[-1]))
    return result


# ─── 数据加载 ───────────────────────────────────────────────

def load_data():
    global _data
    if _data is not None:
        return _data

    print("加载数据...")
    _data = {}

    with open(STATION_COORDS, 'r', encoding='utf-8') as f:
        _data['station_coords'] = json.load(f)
    print(f"  站点坐标: {len(_data['station_coords'])}")

    with open(ROUTE_GEOMETRIES, 'r', encoding='utf-8') as f:
        _data['route_geometries'] = json.load(f)
    print(f"  路线几何: {len(_data['route_geometries'])}")

    with open(SEGMENT_CACHE, 'rb') as f:
        _data['segment_cache'] = pickle.load(f)
    print(f"  线段缓存: {len(_data['segment_cache'])}")

    with open(PAIR_INDEX, 'r', encoding='utf-8') as f:
        _data['pair_index'] = json.load(f)
    print(f"  站对索引: {len(_data['pair_index'])}")

    with open(STATION_INDEX, 'r', encoding='utf-8') as f:
        _data['station_index'] = json.load(f)
    print(f"  站点索引: {len(_data['station_index'])}")

    with open(TRAIN_DETAILS, 'r', encoding='utf-8') as f:
        _data['train_details'] = json.load(f)
    print(f"  车次数据: {len(_data['train_details'])}")

    return _data


# ─── 站名匹配 ───────────────────────────────────────────────

def resolve_station(name, station_coords):
    """尝试匹配站名（多种策略）"""
    name = name.replace(' ', '').strip()

    if name in station_coords:
        return name

    # 尝试加/去 "站" 后缀
    for v in [name + '站', name.rstrip('站')]:
        if v and v in station_coords:
            return v

    # 尝试去掉常见城市前缀
    for prefix in ['北京', '上海', '广州', '深圳', '天津', '重庆', '成都',
                   '武汉', '南京', '杭州', '西安', '郑州', '长沙', '沈阳',
                   '哈尔滨', '长春', '济南', '青岛', '大连', '昆明', '贵阳',
                   '南宁', '兰州', '太原', '石家庄', '合肥', '南昌', '福州']:
        if name.startswith(prefix):
            short = name[len(prefix):]
            if short and short in station_coords:
                return short

    return None


# ─── 线段查找 ───────────────────────────────────────────────

def _try_direct_cache(station_a, station_b, data):
    """直接从缓存中查找线段（两个方向都试）"""
    segment_cache = data['segment_cache']
    pair_index = data['pair_index']

    best_seg = None
    best_len = float('inf')

    # 正向 A→B
    pair_key = f"{station_a}|{station_b}"
    if pair_key in pair_index:
        for route in pair_index[pair_key]:
            key = (station_a, station_b, route)
            if key in segment_cache:
                seg = segment_cache[key]
                seg_len = traj_length(seg)
                if seg_len < best_len:
                    best_len = seg_len
                    best_seg = seg

    # 反向 B→A
    pair_key_rev = f"{station_b}|{station_a}"
    if pair_key_rev in pair_index:
        for route in pair_index[pair_key_rev]:
            key = (station_b, station_a, route)
            if key in segment_cache:
                seg = list(reversed([list(p) for p in segment_cache[key]]))
                seg_len = traj_length(seg)
                if seg_len < best_len:
                    best_len = seg_len
                    best_seg = seg

    return best_seg


def _try_intermediate(station_a, station_b, train_stations, data):
    """通过中间站点拼接线段"""
    station_index = data['station_index']
    route_geometries = data['route_geometries']

    if station_a not in station_index or station_b not in station_index:
        return None

    routes_a = set(station_index[station_a])
    routes_b = set(station_index[station_b])
    common_routes = routes_a & routes_b

    if not common_routes:
        return None

    train_stations_set = set(train_stations)
    best_route = None
    best_score = -1
    best_intermediate = None

    for route in common_routes:
        route_stations = route_geometries[route].get('stations', [])
        coverage = len(set(route_stations) & train_stations_set)

        idx_a = route_stations.index(station_a) if station_a in route_stations else -1
        idx_b = route_stations.index(station_b) if station_b in route_stations else -1
        if idx_a < 0 or idx_b < 0:
            continue

        if idx_a < idx_b:
            intermediates = route_stations[idx_a:idx_b + 1]
        else:
            intermediates = list(reversed(route_stations[idx_b:idx_a + 1]))

        score = coverage * 100 - len(intermediates)
        if score > best_score:
            best_score = score
            best_route = route
            best_intermediate = intermediates

    if not best_intermediate or len(best_intermediate) < 2:
        return None

    # 拼接子线段
    full_seg = []
    coords = data['station_coords']

    for i in range(len(best_intermediate) - 1):
        st_from = best_intermediate[i]
        st_to = best_intermediate[i + 1]
        sub_seg = _try_direct_cache(st_from, st_to, data)

        if sub_seg:
            sub_seg = [list(p) for p in sub_seg]
            if full_seg:
                if (abs(full_seg[-1][0] - sub_seg[0][0]) < 0.001 and
                        abs(full_seg[-1][1] - sub_seg[0][1]) < 0.001):
                    full_seg.extend(sub_seg[1:])
                else:
                    full_seg.extend(sub_seg)
            else:
                full_seg = list(sub_seg)
        else:
            # 子线段不在缓存中，用直线
            if st_from in coords and st_to in coords:
                if full_seg:
                    full_seg.append(list(coords[st_to]))
                else:
                    full_seg.append(list(coords[st_from]))
                    full_seg.append(list(coords[st_to]))

    return full_seg if full_seg else None


def _find_nearest_on_traj(coord, traj, max_check=800):
    """在轨迹上找离坐标最近的点索引和距离"""
    step = max(1, len(traj) // max_check)
    best_d = float('inf')
    best_idx = 0
    for i in range(0, len(traj), step):
        d = haversine_km(coord[0], coord[1], traj[i][0], traj[i][1])
        if d < best_d:
            best_d = d
            best_idx = i
    # 精细搜索
    start = max(0, best_idx - step)
    end = min(len(traj), best_idx + step + 1)
    for i in range(start, end):
        d = haversine_km(coord[0], coord[1], traj[i][0], traj[i][1])
        if d < best_d:
            best_d = d
            best_idx = i
    return best_idx, best_d


def _find_all_nearby_on_traj(coord, traj, max_dist_km=15.0, max_results=8):
    """在轨迹上找所有离坐标 max_dist_km 内的点（避免重复区域）。
    返回 [(idx, dist), ...] 按距离排序，且索引间隔 > 50 以避免聚集。
    """
    step = max(1, len(traj) // 2000)
    candidates = []
    for i in range(0, len(traj), step):
        d = haversine_km(coord[0], coord[1], traj[i][0], traj[i][1])
        if d <= max_dist_km:
            candidates.append((i, d))

    # 精细搜索：对每个粗筛候选，在其邻域内做精细搜索
    refined = []
    for idx, d in candidates:
        start = max(0, idx - step)
        end = min(len(traj), idx + step + 1)
        local_best_d = d
        local_best_idx = idx
        for i in range(start, end):
            dd = haversine_km(coord[0], coord[1], traj[i][0], traj[i][1])
            if dd < local_best_d:
                local_best_d = dd
                local_best_idx = i
        refined.append((local_best_idx, local_best_d))

    # 去重：索引间隔 > 50
    refined.sort(key=lambda x: x[1])
    result = []
    for idx, d in refined:
        if all(abs(idx - r[0]) > 50 for r in result):
            result.append((idx, d))
        if len(result) >= max_results:
            break
    return result


def _try_direct_trajectory(station_a, station_b, data, max_dist_km=15.0):
    """当缓存查找失败时，直接从路线轨迹中提取线段。
    改进：找到所有近邻点，选择最短有效线段。
    """
    coords = data['station_coords']
    route_geometries = data['route_geometries']

    if station_a not in coords or station_b not in coords:
        return None

    coord_a = coords[station_a]
    coord_b = coords[station_b]
    direct_dist = haversine_km(coord_a[0], coord_a[1], coord_b[0], coord_b[1])

    # 找到同时经过 A 和 B 附近的路线
    routes_near_a = []
    routes_near_b = []

    for route_name, route_info in route_geometries.items():
        traj = route_info['trajectory']
        if not traj or len(traj) < 2:
            continue
        # 快速 bbox 过滤
        lngs = [p[0] for p in traj]
        lats = [p[1] for p in traj]
        margin = max_dist_km / 111.0
        near_a = (min(lngs) - margin <= coord_a[0] <= max(lngs) + margin and
                  min(lats) - margin <= coord_a[1] <= max(lats) + margin)
        near_b = (min(lngs) - margin <= coord_b[0] <= max(lngs) + margin and
                  min(lats) - margin <= coord_b[1] <= max(lats) + margin)

        if near_a:
            pts_a = _find_all_nearby_on_traj(coord_a, traj, max_dist_km)
            for idx, d in pts_a:
                routes_near_a.append((route_name, idx, d))
        if near_b:
            pts_b = _find_all_nearby_on_traj(coord_b, traj, max_dist_km)
            for idx, d in pts_b:
                routes_near_b.append((route_name, idx, d))

    common = set(r[0] for r in routes_near_a) & set(r[0] for r in routes_near_b)
    if not common:
        return None

    # 按 route 分组
    a_by_route = {}
    for r_name, idx, d in routes_near_a:
        a_by_route.setdefault(r_name, []).append((idx, d))
    b_by_route = {}
    for r_name, idx, d in routes_near_b:
        b_by_route.setdefault(r_name, []).append((idx, d))

    best_seg = None
    best_score = -999

    for route_name in common:
        traj = route_geometries[route_name]['trajectory']
        pts_a = a_by_route[route_name]
        pts_b = b_by_route[route_name]

        # 对每对 (a_idx, b_idx) 尝试提取线段，选最短的
        for idx_a, dist_a in pts_a:
            for idx_b, dist_b in pts_b:
                if idx_a == idx_b:
                    continue

                # 提取线段
                if idx_a < idx_b:
                    seg = [list(p) for p in traj[idx_a:idx_b + 1]]
                else:
                    seg = [list(p) for p in reversed(traj[idx_b:idx_a + 1])]

                seg_len = traj_length(seg)

                # 质量检查
                if direct_dist > 0.1:
                    ratio = seg_len / direct_dist
                    if ratio > 4:
                        continue  # 跳过过长的线段
                    if ratio < 0.5:
                        continue  # 跳过过短的线段（错误近邻点）

                # 评分：线段短 + 距离近
                score = -dist_a - dist_b - seg_len * 0.01
                if direct_dist > 0.1:
                    ratio = seg_len / direct_dist
                    if ratio <= 1.5:
                        score += 100
                    elif ratio <= 2:
                        score += 50
                    elif ratio <= 3:
                        score += 20

                if score > best_score:
                    best_score = score
                    best_seg = seg

    return best_seg


def find_segment(station_a, station_b, train_stations, data):
    """查找两个站点之间的最佳线段"""
    coords = data['station_coords']

    # 解析站名
    resolved_a = resolve_station(station_a, coords)
    resolved_b = resolve_station(station_b, coords)

    if not resolved_a or not resolved_b:
        return None, 'no_station', None, None

    # Step 1: 直接缓存查找
    seg = _try_direct_cache(resolved_a, resolved_b, data)
    if seg:
        seg = [list(p) for p in seg]
        direct_dist = haversine_km(
            coords[resolved_a][0], coords[resolved_a][1],
            coords[resolved_b][0], coords[resolved_b][1]
        )
        seg_len = traj_length(seg)
        if direct_dist < 0.1 or seg_len <= direct_dist * 3:
            return seg, 'cache', resolved_a, resolved_b

    # Step 2: 中间站点拼接
    seg = _try_intermediate(resolved_a, resolved_b, train_stations, data)
    if seg:
        return seg, 'intermediate', resolved_a, resolved_b

    # Step 3: 直接从路线轨迹提取（15km 后备）
    seg = _try_direct_trajectory(resolved_a, resolved_b, data, max_dist_km=15.0)
    if seg:
        return seg, 'trajectory', resolved_a, resolved_b

    # Step 4: 直接从路线轨迹提取（30km 大半径后备）
    seg = _try_direct_trajectory(resolved_a, resolved_b, data, max_dist_km=30.0)
    if seg:
        return seg, 'trajectory_wide', resolved_a, resolved_b

    # Step 5: 直线后备
    return ([list(coords[resolved_a]), list(coords[resolved_b])],
            'fallback', resolved_a, resolved_b)


# ─── 地图生成 ───────────────────────────────────────────────

def generate_route_map(train_code, output_dir=None):
    """根据车次号生成路线图"""
    data = load_data()
    train_details = data['train_details']

    if train_code not in train_details:
        return {'error': f'车次 {train_code} 不存在'}

    train_info = train_details[train_code]
    stations = train_info['stations']
    station_details = train_info.get('station_details', [])

    print(f"\n{'=' * 60}")
    print(f"车次: {train_code} ({train_info.get('from', '')} → {train_info.get('to', '')})")
    print(f"类型: {train_info.get('class', '')}")
    print(f"站点({len(stations)}): {' → '.join(stations)}")
    print(f"{'=' * 60}")

    # 为每个相邻站对查找线段
    all_points = []
    segment_info = []
    found_count = 0
    fallback_count = 0
    no_station_count = 0
    unmatched = []

    for i in range(len(stations) - 1):
        st_a = stations[i]
        st_b = stations[i + 1]

        seg, source, res_a, res_b = find_segment(st_a, st_b, stations, data)

        if seg:
            if source in ('cache', 'intermediate', 'trajectory'):
                found_count += 1
            elif source == 'fallback':
                fallback_count += 1
            elif source == 'no_station':
                no_station_count += 1
                unmatched.append(f"{st_a}→{st_b}")
                continue

            # 降采样
            seg = downsample_segment(seg, points_per_100km=25)

            # 拼接（去重复首尾点）
            if all_points and seg:
                if (abs(all_points[-1][0] - seg[0][0]) < 0.001 and
                        abs(all_points[-1][1] - seg[0][1]) < 0.001):
                    all_points.extend(seg[1:])
                else:
                    all_points.extend(seg)
            else:
                all_points.extend(seg)

            seg_len = traj_length(seg)
            segment_info.append({
                'from': st_a,
                'to': st_b,
                'source': source,
                'points': len(seg),
                'km': round(seg_len, 1)
            })
        else:
            no_station_count += 1
            unmatched.append(f"{st_a}→{st_b}")

    total_km = traj_length(all_points)
    print(f"\n线段统计:")
    print(f"  匹配成功: {found_count}")
    print(f"  直线后备: {fallback_count}")
    print(f"  站点缺失: {no_station_count}")
    print(f"  总点数: {len(all_points)}")
    print(f"  总里程: {total_km:.0f}km")

    for si in segment_info:
        status = '✓' if si['source'] in ('cache', 'intermediate', 'trajectory') else '⚠'
        print(f"  {status} {si['from']}→{si['to']}: {si['points']}点, {si['km']}km ({si['source']})")

    if unmatched:
        print(f"\n  未匹配站对: {', '.join(unmatched)}")

    # 生成 folium 地图
    try:
        import folium
    except ImportError:
        print("\nfolium 未安装，输出坐标 JSON")
        return {
            'train_code': train_code,
            'points': all_points,
            'segment_info': segment_info,
            'total_km': total_km,
        }

    # 中心点
    if all_points:
        avg_lng = sum(p[0] for p in all_points) / len(all_points)
        avg_lat = sum(p[1] for p in all_points) / len(all_points)
    else:
        avg_lng, avg_lat = 116.0, 35.0

    m = folium.Map(location=[avg_lat, avg_lng], zoom_start=6,
                   tiles='CartoDB positron')

    # 画路线 (folium 用 [lat, lng])
    if all_points:
        folium_coords = [[p[1], p[0]] for p in all_points]
        folium.PolyLine(
            folium_coords,
            color='#2563eb',
            weight=3,
            opacity=0.8,
            smoothFactor=0,
            noClip=True
        ).add_to(m)

    # 标注站点
    coords = data['station_coords']
    for i, st in enumerate(stations):
        resolved = resolve_station(st, coords)
        if not resolved:
            continue

        lat, lng = coords[resolved][1], coords[resolved][0]
        is_endpoint = (i == 0 or i == len(stations) - 1)

        arrive = ''
        depart = ''
        if i < len(station_details):
            arrive = station_details[i].get('arrive', '')
            depart = station_details[i].get('depart', '')

        popup_text = f"<b>{st}</b>"
        if arrive and arrive != '----':
            popup_text += f"<br>到: {arrive}"
        if depart and depart != '----':
            popup_text += f"<br>发: {depart}"
        if is_endpoint:
            popup_text = f"★ {popup_text}"

        folium.CircleMarker(
            location=[lat, lng],
            radius=8 if is_endpoint else 5,
            color='#dc2626' if is_endpoint else '#2563eb',
            fill=True,
            fill_color='#dc2626' if is_endpoint else '#2563eb',
            fill_opacity=0.8,
            popup=folium.Popup(popup_text, max_width=200)
        ).add_to(m)

    # 自适应缩放
    if all_points:
        bounds = [
            [min(p[1] for p in all_points), min(p[0] for p in all_points)],
            [max(p[1] for p in all_points), max(p[0] for p in all_points)]
        ]
        m.fit_bounds(bounds, padding=(30, 30))

    # 保存
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    html_path = os.path.join(output_dir, f'{train_code}.html')
    m.save(html_path)
    print(f"\n地图已保存: {html_path}")

    return {
        'html_path': html_path,
        'train_code': train_code,
        'from': train_info.get('from', ''),
        'to': train_info.get('to', ''),
        'class': train_info.get('class', ''),
        'station_count': len(stations),
        'segments_found': found_count,
        'segments_fallback': fallback_count,
        'segments_no_station': no_station_count,
        'total_points': len(all_points),
        'total_km': round(total_km, 1),
        'segment_info': segment_info,
        'unmatched': unmatched,
    }


def search_trains_by_station(from_station, to_station, output_dir=None):
    """搜索经过指定站点的车次，按发车时间排序，生成路线图"""
    data = load_data()
    train_details = data['train_details']

    results = []
    for code, info in train_details.items():
        stations = info['stations']
        from_idx = -1
        to_idx = -1
        for i, s in enumerate(stations):
            s_clean = s.replace(' ', '').strip()
            if s_clean == from_station.replace(' ', '').strip():
                from_idx = i
            if s_clean == to_station.replace(' ', '').strip():
                to_idx = i

        if from_idx >= 0 and to_idx > from_idx:
            depart = ''
            if from_idx < len(info.get('station_details', [])):
                depart = info['station_details'][from_idx].get('depart', '')
            results.append((code, depart, from_idx, to_idx))

    results.sort(key=lambda x: x[1])

    print(f"\n找到 {len(results)} 趟 {from_station} → {to_station} 的车次:")
    maps = []
    for code, depart, _, _ in results:
        print(f"  {code} 发车: {depart}")
        result = generate_route_map(code, output_dir)
        if 'html_path' in result:
            maps.append(result)

    return maps


def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成车次路线图')
    parser.add_argument('train_code', nargs='?', help='车次号 (如 Z227)')
    parser.add_argument('--from', dest='from_station', help='出发站')
    parser.add_argument('--to', dest='to_station', help='到达站')
    parser.add_argument('--output', default=None, help='输出目录')
    args = parser.parse_args()

    if args.from_station and args.to_station:
        search_trains_by_station(args.from_station, args.to_station, args.output)
    elif args.train_code:
        result = generate_route_map(args.train_code, args.output)
        if 'error' in result:
            print(f"\n错误: {result['error']}")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
