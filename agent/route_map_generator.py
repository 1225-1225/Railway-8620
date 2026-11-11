"""
车次运行路线地图生成器（简化版）

将相邻站点用直线连接，不再使用真实铁路轨迹。
"""

import json
import os
import logging

from settings import settings as config_data

logger = logging.getLogger("tool_calls")

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
# 地图输出目录：统一从 settings.maps_output_dir 读取（与 backend/api.py 的 /maps 静态挂载同源）
#   - Docker 部署时由 docker-compose.yml 注入 maps_output_dir=/app/shared/maps
#     （共享卷挂载给前端 Nginx 提供 /maps/ 静态访问）
#   - 本地开发时回退到 data/maps
_MAP_DIR = config_data.maps_output_dir

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
    """站名 -> (lng, lat)

    优先用 OSM 参考数据（覆盖 17536 站，含同名消歧），
    回退到旧的 station_coords.json。
    """
    try:
        from agent.route_geometry import get_route_geometry
        c = get_route_geometry().station_coord(name)
        if c:
            return c
    except Exception:
        pass
    coords = _load_station_coords()
    return coords.get(name)


def get_train_stations(train_code: str) -> list:
    """返回车次的经停站列表"""
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


def get_train_class(train_code: str) -> str:
    """返回车次类型（高铁/动车/城际/直特/特快/快速…），用于线路消歧"""
    for fname in ('train_details.json', 'train_stations.json'):
        path = os.path.join(_DATA_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        info = data.get(train_code)
        if info:
            return info.get('class', '') or info.get('train_class', '')
    return ''


# ─── 地图绘制 ───────────────────────────────────────────────

def _generate_route_map(m, stations, line_color, train_class=None):
    """在地图上绘制车次路线

    优先使用 OSM 真实轨道几何；缺失的站段退化为直线并用虚线区分，
    让用户一眼看出哪一段是估算的。

    train_class 用于在两站之间有多条候选线路时消歧
    （G/D/C 优先高速线，K/T/Z 优先普速线）。
    """
    import folium

    from agent.route_geometry import get_route_geometry

    rg = get_route_geometry()
    stats = {"total": 0, "matched": 0, "fallback": 0, "missing": 0, "lines": {}}
    used_lines = []

    for i in range(len(stations) - 1):
        s1, s2 = stations[i], stations[i + 1]
        stats["total"] += 1

        # 记录本次命中的线路名（用于标题展示与调试）
        sa, sb = rg.resolve_station(s1), rg.resolve_station(s2)
        if sa and sb:
            for cand in rg._candidates(sa, sb, train_class):
                if cand not in used_lines:
                    used_lines.append(cand)
                    break

        seg, source = rg.find_segment(s1, s2, train_class)

        if source == "no_station" or not seg:
            # 连坐标都没有：退回本地 station_coords.json
            c1 = _get_station_coord(s1)
            c2 = _get_station_coord(s2)
            if not c1 or not c2:
                stats["missing"] += 1
                continue
            seg = [list(c1), list(c2)]
            source = "fallback"

        if source == "line":
            stats["matched"] += 1
            folium.PolyLine(
                locations=[[p[1], p[0]] for p in seg],
                color=line_color,
                weight=3.5,
                opacity=0.85,
                tooltip=f"{s1} → {s2}",
            ).add_to(m)
        else:
            stats["fallback"] += 1
            folium.PolyLine(
                locations=[[p[1], p[0]] for p in seg],
                color="#999999",
                weight=2.5,
                opacity=0.9,
                dash_array="6,8",
                tooltip=f"{s1} → {s2}（估算直线）",
            ).add_to(m)

    stats["lines"] = used_lines
    return stats


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

    train_class = get_train_class(train_code)
    stats = _generate_route_map(m, stations, '#FF4444', train_class)

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

    # 图例：说明实线/虚线的含义
    legend_html = (
        '<div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;'
        'background: white; padding: 10px 14px; border-radius: 8px;'
        'box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 13px; line-height: 1.7;">'
        '<div><span style="display:inline-block;width:26px;height:3px;'
        'background:#FF4444;vertical-align:middle;"></span> 真实轨道</div>'
        '<div><span style="display:inline-block;width:26px;height:0;'
        'border-top:2px dashed #999;vertical-align:middle;"></span> 估算直线</div>'
        '</div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    # 标题栏：附带线路名与真实轨道覆盖率，便于判断精度
    line_label = ""
    if stats.get("lines"):
        line_label = " · " + " / ".join(stats["lines"][:2])
    matched = stats.get("matched", 0)
    total = stats.get("total", 1)
    accuracy = f"{matched}/{total} 段真实轨道"

    title_html = (
        '<div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);'
        'z-index: 1000; background: white; padding: 10px 20px;'
        'border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'
        'font-size: 16px; font-weight: bold; text-align: center;">'
        f'🚄 {train_code} 运行路线图 | {stations[0]} → {stations[-1]}'
        f'<div style="font-size:12px;font-weight:normal;color:#666;margin-top:4px;">'
        f'{line_label.strip(" ·")} {accuracy}</div>'
        '</div>'
    )
    m.get_root().html.add_child(folium.Element(title_html))

    os.makedirs(_MAP_DIR, exist_ok=True)
    map_path = os.path.join(_MAP_DIR, f"{train_code}_route.html")
    m.save(map_path)
    logger.info(f"地图已生成: {map_path}")
    return map_path


