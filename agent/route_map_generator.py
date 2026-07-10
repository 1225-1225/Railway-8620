"""
车次运行路线地图生成器

基于真实铁路路线网络（data/railway_routes.json + data/railway_graph.json）
为车次生成 folium 交互式地图，标注车站和运行路线。

车次站点序列匹配策略：
1. 对车次的每对相邻站 (s_i, s_{i+1})，在 railway_graph 中查找匹配的路线段
2. 如果匹配到，取该路线段的完整中间站序列获得经度纬度点
3. 如果未匹配，直接取两站坐标连线
"""

import json
import os
import logging

logger = logging.getLogger("tool_calls")

# ===== 路径配置 =====
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_MAP_DIR = os.path.join(_DATA_DIR, 'maps')

_COORDS_PATH = os.path.join(_DATA_DIR, 'station_coords.json')
_GRAPH_PATH = os.path.join(_DATA_DIR, 'railway_graph.json')
_ROUTES_PATH = os.path.join(_DATA_DIR, 'railway_routes.json')
_TRAIN_DETAILS_PATH = os.path.join(_DATA_DIR, 'train_details.json')
_TRAIN_STATIONS_PATH = os.path.join(_DATA_DIR, 'train_stations.json')

# 缓存
_station_coords = None
_railway_graph = None
_route_by_name = None


def _load_station_coords():
    global _station_coords
    if _station_coords is None:
        with open(_COORDS_PATH, 'r', encoding='utf-8') as f:
            _station_coords = json.load(f)
    return _station_coords


def _load_railway_graph():
    global _railway_graph
    if _railway_graph is None:
        with open(_GRAPH_PATH, 'r', encoding='utf-8') as f:
            _railway_graph = json.load(f)
    return _railway_graph


def _load_routes_by_name():
    """返回 {route_name: {stations: [...], from: ..., to: ...}}"""
    global _route_by_name
    if _route_by_name is not None:
        return _route_by_name
    
    with open(_ROUTES_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    _route_by_name = {}
    for r in data.get('routes', []):
        name = r.get('name', '')
        if name:
            _route_by_name[name] = r
        alt = name.replace('线', '')
        if alt != name:
            _route_by_name[alt] = r
    
    return _route_by_name


def get_train_stations(train_code: str) -> list:
    """获取车次的经停站列表"""
    # 先从完整信息查
    if os.path.exists(_TRAIN_DETAILS_PATH):
        with open(_TRAIN_DETAILS_PATH, 'r', encoding='utf-8') as f:
            details = json.load(f)
        if train_code in details:
            return details[train_code].get('stations', [])
    
    # 从基础数据查
    with open(_TRAIN_STATIONS_PATH, 'r', encoding='utf-8') as f:
        stations = json.load(f)
    if train_code in stations:
        return stations[train_code].get('stations', [])
    
    return []


def _get_station_coord(name: str):
    """获取车站坐标，返回 (lng, lat) 或 None"""
    coords = _load_station_coords()
    return coords.get(name)


def _resolve_route_points(station_a: str, station_b: str, coords: dict) -> list:
    """解析站A到站B的路线坐标点序列
    
    策略：
    1. 在 railway_graph 中查找相邻站对
    2. 如果找到，用 route_name 从 railway_routes 取完整中间站序列
    3. 将站名映射为坐标
    4. 如果没找到，直接返回两站坐标
    """
    graph = _load_railway_graph()
    routes = _load_routes_by_name()
    
    adj_key = f"{station_a}|{station_b}"
    rev_key = f"{station_b}|{station_a}"
    
    # 查找匹配的路线
    matched_segments = []
    
    if adj_key in graph.get('adjacency', {}):
        matched_segments = graph['adjacency'][adj_key]
    elif rev_key in graph.get('adjacency', {}):
        # 反向匹配
        matched_segments = graph['adjacency'][rev_key]
    
    coord_a = _get_station_coord(station_a)
    coord_b = _get_station_coord(station_b)
    
    if matched_segments and coord_a and coord_b:
        # 取第一个匹配的路线
        segment_info = matched_segments[0]
        route_name_raw = segment_info['route_name']
        
        # 从 route_name 提取纯名称（去掉 [ref] 后缀）
        if '[' in route_name_raw:
            route_name = route_name_raw.split('[')[0]
        else:
            route_name = route_name_raw
        
        # 在 routes 中查找完整站点序列
        if route_name in routes:
            route_stations = routes[route_name].get('stations', [])
            if len(route_stations) >= 2:
                # 找到 a 和 b 在路线中的位置
                try:
                    idx_a = route_stations.index(station_a)
                    idx_b = route_stations.index(station_b)
                    
                    if idx_a < idx_b:
                        segment_stations = route_stations[idx_a:idx_b + 1]
                    else:
                        segment_stations = route_stations[idx_b:idx_a + 1][::-1]
                    
                    # 转换为坐标
                    points = []
                    for s in segment_stations:
                        c = coords.get(s)
                        if c:
                            points.append(c)
                    return points
                except ValueError:
                    pass
    
    # 实在不行，直接返回两站坐标
    if coord_a and coord_b:
        return [coord_a, coord_b]
    return []


def generate_train_route_map(train_code: str) -> str:
    """为指定车次生成运行路线地图
    
    Args:
        train_code: 车次号，如 'Z227'
    
    Returns:
        地图 HTML 文件路径，或错误信息
    """
    try:
        import folium
    except ImportError:
        return "需要安装 folium: pip install folium"
    
    stations = get_train_stations(train_code)
    if not stations:
        return f"未找到车次 {train_code} 的信息"
    
    coords = _load_station_coords()
    
    # 计算地图中心点（取第一个和最后一个车站的中点）
    first_coord = _get_station_coord(stations[0])
    last_coord = _get_station_coord(stations[-1])
    
    if not first_coord or not last_coord:
        return f"无法获取车站坐标（{stations[0]} 或 {stations[-1]}）"
    
    center_lat = (first_coord[1] + last_coord[1]) / 2
    center_lng = (first_coord[0] + last_coord[0]) / 2
    
    # 创建地图（folium 要求 [纬度, 经度]）
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6,
                   tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')
    
    # 收集所有路线段并绘制
    all_points = []
    seen_segments = set()
    line_color = '#FF4444'
    
    for i in range(len(stations) - 1):
        s1, s2 = stations[i], stations[i + 1]
        segment_key = (s1, s2)
        if segment_key in seen_segments:
            continue
        seen_segments.add(segment_key)
        
        segment_points = _resolve_route_points(s1, s2, coords)
        for pt in segment_points:
            if pt not in all_points:
                all_points.append(pt)
        
        # 绘制路线段
        if len(segment_points) >= 2:
            folium.PolyLine(
                locations=[(lat, lng) for (lng, lat) in segment_points],
                color=line_color,
                weight=3.5,
                opacity=0.8,
                tooltip=f"{s1} → {s2}"
            ).add_to(m)
    
    # 绘制车站标记
    station_coords_list = []
    for s in stations:
        c = _get_station_coord(s)
        if c:
            station_coords_list.append((c, s))
    
    # 起讫站特殊标记（大、颜色不同）
    for idx, (coord, name) in enumerate(station_coords_list):
        lng, lat = coord
        if idx == 0:
            # 起点
            folium.Marker(
                location=[lat, lng],
                popup=f"🚉 {name}（始发站）",
                tooltip=name,
                icon=folium.Icon(color='green', icon='play', prefix='fa')
            ).add_to(m)
        elif idx == len(station_coords_list) - 1:
            # 终点
            folium.Marker(
                location=[lat, lng],
                popup=f"🚉 {name}（终点站）",
                tooltip=name,
                icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa')
            ).add_to(m)
        else:
            # 中间站
            folium.CircleMarker(
                location=[lat, lng],
                radius=5,
                color='#3388ff',
                fill=True,
                fill_color='#3388ff',
                popup=f"🚉 {name}",
                tooltip=name
            ).add_to(m)
    
    # 添加标题
    title_html = f'''
    <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%); 
                z-index: 1000; background: white; padding: 10px 20px; 
                border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                font-size: 16px; font-weight: bold;">
        🚄 {train_code} 运行路线图 | {stations[0]} → {stations[-1]}
    </div>
    '''
    m.get_root().html.add_child(folium.Element(title_html))
    
    # 保存
    os.makedirs(_MAP_DIR, exist_ok=True)
    map_path = os.path.join(_MAP_DIR, f"{train_code}_route.html")
    m.save(map_path)
    
    logger.info(f"地图已生成: {map_path}")
    return map_path


def generate_multi_train_route_map(train_codes: list) -> str:
    """为多个车次生成运行路线地图（用不同颜色区分）
    
    Args:
        train_codes: 车次号列表
    
    Returns:
        地图 HTML 文件路径
    """
    try:
        import folium
    except ImportError:
        return "需要安装 folium: pip install folium"
    
    all_stations_list = []
    first_station = None
    last_station = None
    
    # 收集所有车次信息
    train_info_list = []
    for code in train_codes:
        stations = get_train_stations(code)
        if len(stations) >= 2:
            train_info_list.append((code, stations))
            if first_station is None:
                first_station = stations[0]
            last_station = stations[-1]
    
    if not train_info_list:
        return "未找到任何车次信息"
    
    coords = _load_station_coords()
    
    # 计算中心点
    fc = _get_station_coord(first_station) if first_station else None
    lc = _get_station_coord(last_station) if last_station else None
    center_lat = ((fc[1] if fc else 30) + (lc[1] if lc else 30)) / 2
    center_lng = ((fc[0] if fc else 120) + (lc[0] if lc else 120)) / 2
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6,
                   tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')
    
    # 颜色列表
    colors = ['#FF4444', '#4466FF', '#44BB44', '#FF8800', '#9944FF', '#FF44AA']
    
    # 收集所有途经站
    all_stations_set = set()
    
    for idx, (code, stations) in enumerate(train_info_list):
        color = colors[idx % len(colors)]
        seen_segments = set()
        train_station_coords = []
        
        for i in range(len(stations) - 1):
            s1, s2 = stations[i], stations[i + 1]
            seg_key = (s1, s2)
            if seg_key in seen_segments:
                continue
            seen_segments.add(seg_key)
            
            segment_pts = _resolve_route_points(s1, s2, coords)
            
            if len(segment_pts) >= 2:
                folium.PolyLine(
                    locations=[(lat, lng) for (lng, lat) in segment_pts],
                    color=color,
                    weight=3,
                    opacity=0.8,
                    tooltip=f"{code}: {s1} → {s2}"
                ).add_to(m)
        
        # 收集站坐标
        for s in stations:
            c = _get_station_coord(s)
            if c:
                train_station_coords.append((c, s))
                all_stations_set.add((c[0], c[1], s))
    
    # 标记公共车站
    for lng, lat, name in all_stations_set:
        # 检查是否为多个车次的共有站
        folium.CircleMarker(
            location=[lat, lng],
            radius=5,
            color='#666666',
            fill=True,
            fill_color='#999999',
            popup=f"🚉 {name}",
            tooltip=name
        ).add_to(m)
    
    # 添加标题
    codes_str = ', '.join(c for c, _ in train_info_list)
    m.get_root().html.add_child(folium.Element(f'''
    <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%); 
                z-index: 1000; background: white; padding: 10px 20px; 
                border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                font-size: 16px; font-weight: bold;">
        🚄 多车次运行路线对比 | {codes_str}
    </div>
    '''))
    
    # 图例
    legend_html = '<div style="position: fixed; bottom: 20px; right: 20px; z-index: 1000; background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);"><b>图例</b><br>'
    for idx, (code, _) in enumerate(train_info_list):
        color = colors[idx % len(colors)]
        legend_html += f'<span style="color:{color};">─</span> {code}<br>'
    legend_html += '</div>'
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # 保存
    os.makedirs(_MAP_DIR, exist_ok=True)
    map_path = os.path.join(_MAP_DIR, "multi_train_routes.html")
    m.save(map_path)
    
    logger.info(f"多车次地图已生成: {map_path}")
    return map_path