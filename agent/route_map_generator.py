"""
车次运行路线地图生成器（简化版）

将相邻站点用直线连接，不再使用真实铁路轨迹。
"""

import json
import os
import logging

logger = logging.getLogger("tool_calls")

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_MAP_DIR = os.path.join(_DATA_DIR, 'maps')

_COORDS_PATH = os.path.join(_DATA_DIR, 'station_coords.json')

_station_coords = None


# ─── 数据加载 ───────────────────────────────────────────────

def _load_station_coords():
    global _station_coords
    if _station_coords is None:
        with open(_COORDS_PATH, 'r', encoding='utf-8') as f:
            _station_coords = json.load(f)
    return _station_coords


def _get_station_coord(name: str):
    coords = _load_station_coords()
    return coords.get(name)


def get_train_stations(train_code: str) -> list:
    _TRAIN_DETAILS_PATH = os.path.join(_DATA_DIR, 'train_details.json')
    _TRAIN_STATIONS_PATH = os.path.join(_DATA_DIR, 'train_stations.json')
    if os.path.exists(_TRAIN_DETAILS_PATH):
        with open(_TRAIN_DETAILS_PATH, 'r', encoding='utf-8') as f:
            details = json.load(f)
        if train_code in details:
            return details[train_code].get('stations', [])
    with open(_TRAIN_STATIONS_PATH, 'r', encoding='utf-8') as f:
        stations = json.load(f)
    if train_code in stations:
        return stations[train_code].get('stations', [])
    return []


# ─── 地图绘制 ───────────────────────────────────────────────

def _generate_route_map(m, stations, line_color):
    """在地图上绘制车次路线（直线连接相邻站点）"""
    import folium

    for i in range(len(stations) - 1):
        s1, s2 = stations[i], stations[i + 1]
        c1 = _get_station_coord(s1)
        c2 = _get_station_coord(s2)
        if not c1 or not c2:
            continue

        tip = f"{s1} → {s2}"
        folium.PolyLine(
            locations=[[c1[1], c1[0]], [c2[1], c2[0]]],
            color=line_color,
            weight=3.5,
            opacity=0.8,
            tooltip=tip
        ).add_to(m)


def generate_train_route_map(train_code: str) -> str:
    """为指定车次生成运行路线地图"""
    try:
        import folium
    except ImportError:
        return "需要安装 folium: pip install folium"

    stations = get_train_stations(train_code)
    if not stations:
        return f"未找到车次 {train_code} 的信息"

    stations = [s for s in stations if s]
    if len(stations) < 2:
        return f"车次 {train_code} 的站点数据不足"

    first_coord = _get_station_coord(stations[0])
    last_coord = _get_station_coord(stations[-1])
    if not first_coord or not last_coord:
        return f"无法获取车站坐标"

    center_lat = (first_coord[1] + last_coord[1]) / 2
    center_lng = (first_coord[0] + last_coord[0]) / 2

    m = folium.Map(location=[center_lat, center_lng], zoom_start=6,
                   tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')

    _generate_route_map(m, stations, '#FF4444')

    station_coords_list = [(c, s) for s in stations if (c := _get_station_coord(s))]
    for idx, (coord, name) in enumerate(station_coords_list):
        lng, lat = coord
        if idx == 0:
            folium.Marker(location=[lat, lng], popup=f"🚉 {name}（始发站）",
                          tooltip=name, icon=folium.Icon(color='green', icon='play', prefix='fa')).add_to(m)
        elif idx == len(station_coords_list) - 1:
            folium.Marker(location=[lat, lng], popup=f"🚉 {name}（终点站）",
                          tooltip=name, icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa')).add_to(m)
        else:
            folium.CircleMarker(location=[lat, lng], radius=5, color='#3388ff',
                                fill=True, fill_color='#3388ff', popup=f"🚉 {name}", tooltip=name).add_to(m)

    title_html = (
        '<div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);'
        'z-index: 1000; background: white; padding: 10px 20px;'
        'border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'
        'font-size: 16px; font-weight: bold;">'
        f'🚄 {train_code} 运行路线图 | {stations[0]} → {stations[-1]}'
        '</div>'
    )
    m.get_root().html.add_child(folium.Element(title_html))

    os.makedirs(_MAP_DIR, exist_ok=True)
    map_path = os.path.join(_MAP_DIR, f"{train_code}_route.html")
    m.save(map_path)
    logger.info(f"地图已生成: {map_path}")
    return map_path


