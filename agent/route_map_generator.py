"""
车次运行路线地图生成器

使用 OSM 真实轨道几何绘制车次路线；缺失数据的站段降级为直线并用虚线区分。
支持单车次地图（generate_train_route_map）与多车次对比图（generate_comparison_map）。
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

def _draw_train_line(m, stations, line_color, train_class=None):
    """在地图上绘制一个车次的路线，返回统计

    优先使用 OSM 真实轨道几何；缺失的站段退化为直线并用虚线区分。
    train_class 用于在两站之间有多条候选线路时消歧。
    """
    import folium

    from agent.route_geometry import get_route_geometry

    rg = get_route_geometry()
    stats = {"total": 0, "matched": 0, "fallback": 0, "missing": 0, "lines": []}
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
                color=line_color,
                weight=2.5,
                opacity=0.75,
                dash_array="6,8",
                tooltip=f"{s1} → {s2}（估算直线）",
            ).add_to(m)

    stats["lines"] = used_lines
    return stats


def _generate_route_map(m, stations, line_color, train_class=None):
    """在地图上绘制车次路线（单线，保留旧签名以兼容）"""
    return _draw_train_line(m, stations, line_color, train_class)


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


# ─── 多车次对比图 ──────────────────────────────────────────

# 对比图配色（最多 6 条线，超出循环使用）
_COMPARE_COLORS = [
    ("#E63946", "红色"),
    ("#1D3557", "深蓝"),
    ("#2A9D8F", "青绿"),
    ("#E76F51", "橙红"),
    ("#7209B7", "紫色"),
    ("#F4A261", "橙色"),
]


def generate_comparison_map(train_codes: list, title: str = "") -> str:
    """生成多个车次的路线对比图

    用于回答「G1 和 T35 走的路线有什么不同」这类问题：
    把多个车次的轨迹叠加在同一张地图上，用不同颜色区分。

    Args:
        train_codes: 车次号列表，2~6 个
        title: 可选标题

    Returns:
        生成的 HTML 文件路径；失败时返回错误说明字符串
    """
    try:
        import folium
    except ImportError:
        return "需要安装 folium: pip install folium"

    codes = []
    for c in (train_codes or []):
        c = str(c).strip().upper()
        if c and c not in codes:
            codes.append(c)

    if len(codes) < 2:
        return "对比图至少需要 2 个车次"
    if len(codes) > 6:
        return f"对比图最多支持 6 个车次（收到 {len(codes)} 个）"

    # 收集每个车次的站点与统计
    plans = []
    all_points = []
    for code in codes:
        stations = [s for s in get_train_stations(code) if s]
        if len(stations) < 2:
            return f"车次 {code} 的站点数据不足，无法对比"
        cls = get_train_class(code)
        plans.append({"code": code, "stations": stations, "class": cls})

    # 先算中心点与范围（用所有站点坐标）
    for p in plans:
        for s in p["stations"]:
            c = _get_station_coord(s)
            if c:
                all_points.append(c)

    if not all_points:
        return "无法获取车站坐标"

    avg_lat = sum(p[1] for p in all_points) / len(all_points)
    avg_lng = sum(p[0] for p in all_points) / len(all_points)

    m = folium.Map(location=[avg_lat, avg_lng], zoom_start=5,
                   tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>')

    # 逐车次绘制
    legend_rows = []
    for idx, p in enumerate(plans):
        color, color_name = _COMPARE_COLORS[idx % len(_COMPARE_COLORS)]
        stats = _draw_train_line(m, p["stations"], color, p["class"])
        p["stats"] = stats
        p["color"] = color
        p["color_name"] = color_name

        line_label = " / ".join(stats["lines"][:1]) if stats["lines"] else ""
        legend_rows.append({
            "code": p["code"],
            "class": p["class"],
            "color": color,
            "color_name": color_name,
            "from": p["stations"][0],
            "to": p["stations"][-1],
            "line": line_label,
            "matched": stats["matched"],
            "total": stats["total"],
            "points": len(p["stations"]),
        })

    # 只在第一个车次上标注站点，避免多点重叠成一团
    first = plans[0]
    sc = [(c, s) for s in first["stations"] if (c := _get_station_coord(s))]
    for i, (coord, name) in enumerate(sc):
        lng, lat = coord
        if i == 0:
            folium.Marker(location=[lat, lng], popup=f"🚉 {name}（{first['code']} 始发）",
                          tooltip=name,
                          icon=folium.Icon(color='green', icon='play', prefix='fa')).add_to(m)
        elif i == len(sc) - 1:
            folium.Marker(location=[lat, lng], popup=f"🚉 {name}（{first['code']} 终点）",
                          tooltip=name,
                          icon=folium.Icon(color='red', icon='flag-checkered', prefix='fa')).add_to(m)
        else:
            folium.CircleMarker(location=[lat, lng], radius=4, color='#666',
                                fill=True, fill_color='#999', fill_opacity=0.7,
                                popup=f"🚉 {name}", tooltip=name).add_to(m)

    # 图例：每个车次一行，含颜色/类型/起讫/精度
    rows_html = ""
    for r in legend_rows:
        rows_html += (
            '<div style="margin-top:6px;white-space:nowrap;">'
            f'<span style="display:inline-block;width:22px;height:3px;'
            f'background:{r["color"]};vertical-align:middle;margin-right:6px;"></span>'
            f'<b>{r["code"]}</b> <span style="color:#666;">({r["class"]})</span> '
            f'{r["from"]}→{r["to"]} '
            f'<span style="color:#888;font-size:11px;">'
            f'{r["points"]}站 · {r["matched"]}/{r["total"]} 段真实'
            + (f' · {r["line"]}' if r["line"] else '')
            + '</span></div>'
        )

    legend_html = (
        '<div style="position: fixed; bottom: 24px; left: 24px; z-index: 1000;'
        'background: white; padding: 10px 14px; border-radius: 8px;'
        'box-shadow: 0 2px 8px rgba(0,0,0,0.3); font-size: 13px; line-height: 1.6;'
        'max-width: 420px;">'
        '<div style="font-weight:bold;margin-bottom:2px;">🚄 车次路线对比</div>'
        + rows_html +
        '<div style="margin-top:8px;padding-top:6px;border-top:1px solid #eee;'
        'font-size:11px;color:#888;">'
        '虚线 = 该段无 OSM 轨道数据，按直线估算'
        '</div></div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    if not title:
        title = " vs ".join(c["code"] for c in plans)
    title_html = (
        '<div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);'
        'z-index: 1000; background: white; padding: 8px 18px;'
        'border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);'
        'font-size: 15px; font-weight: bold;">'
        f'🚄 {title}'
        '</div>'
    )
    m.get_root().html.add_child(folium.Element(title_html))

    # 自适应缩放
    try:
        m.fit_bounds([[min(p[1] for p in all_points), min(p[0] for p in all_points)],
                      [max(p[1] for p in all_points), max(p[0] for p in all_points)]],
                     padding=(40, 40))
    except Exception:
        pass

    os.makedirs(_MAP_DIR, exist_ok=True)
    # 文件名必须只含 [A-Za-z0-9_-]，否则前端 MAP_URL_RE 无法识别并转成地图卡片
    fname = "compare_" + "_".join(codes) + ".html"
    map_path = os.path.join(_MAP_DIR, fname)
    m.save(map_path)
    logger.info(f"对比图已生成: {map_path}")
    return map_path


