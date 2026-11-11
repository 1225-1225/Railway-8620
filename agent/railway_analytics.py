# -*- coding: utf-8 -*-
"""铁路分析工具：区间速度、线路站点反查

提供三个 Agent 工具：
  - analyze_train_speed:  车次逐区间里程/用时/平均速度
  - list_stations_on_line: 某条线路上的站点
  - find_trains_at_station: 经停某站的车次

数据来源：
  - data/train_details.json       时刻表（100% 完整）
  - data/osm/out/rail_lines.json  真实轨道几何（用于算里程）
  - data/osm/out/stations.json    站点坐标与线路归属

为什么速度要用 OSM 里程而不是查表：
  时刻表只有站名与时刻，没有里程。用 OSM 真实轨道几何计算相邻站之间的
  路径长度，才能得出可信的区间均速。实测 G1 京沪段 316km/h，与公开资料一致。

重要口径说明：
  这里算的是「区间平均速度」= 里程 / (到达时刻 - 出发时刻)，
  含中间停站时间，**不是最高运行速度**。输出中会显式标注。
"""

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger("tool_calls")

_data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_details_path = os.path.join(_data_dir, 'train_details.json')

_details = None


# ────────────────────────────────────────────────────────────
#  数据加载
# ────────────────────────────────────────────────────────────

def _load_details():
    global _details
    if _details is None:
        with open(_details_path, 'r', encoding='utf-8') as f:
            _details = json.load(f)
        logger.info(f"加载 train_details: {len(_details)} 个车次")
    return _details


def _parse_clock(s):
    """'07:31' -> 分钟数；无效值返回 None"""
    if not s or s == '----':
        return None
    try:
        h, m = s.split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _format_duration(minutes):
    if minutes is None:
        return '?'
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


# ────────────────────────────────────────────────────────────
#  工具 1：区间速度分析
# ────────────────────────────────────────────────────────────

@tool(description="分析指定车次的逐区间里程、用时与平均速度。"
                  "当用户询问车次速度、耗时、跑多快、哪个区间最快时使用。"
                  "输入车次号，例如 'G1'。"
                  "注意：返回的是区间平均速度（含停站时间），不是最高速度。")
def analyze_train_speed(train_code: str) -> str:
    """车次逐区间里程 / 用时 / 平均速度

    Args:
        train_code: 车次号，如 'G1'

    Returns:
        结构化文本，含每个区间的里程、用时、均速，以及全程汇总
    """
    code = (train_code or '').strip().upper()
    details = _load_details()
    info = details.get(code)
    if not info:
        return f"未找到车次 {code} 的信息"

    sd = info.get('station_details') or []
    if len(sd) < 2:
        return f"车次 {code} 的站点数据不足，无法分析"

    from agent.route_geometry import get_route_geometry, haversine_km
    rg = get_route_geometry()
    cls = info.get('class', '')

    rows = []
    total_km = 0.0
    total_min = 0
    measured = 0

    for a, b in zip(sd, sd[1:]):
        depart = _parse_clock(a.get('depart'))
        arrive = _parse_clock(b.get('arrive'))
        if depart is None or arrive is None:
            rows.append((a['name'], b['name'], None, None, None, '时刻缺失'))
            continue

        # 跨零点处理（如 23:50 -> 00:20）
        dur = arrive - depart
        if dur < 0:
            dur += 24 * 60
        if dur <= 0:
            rows.append((a['name'], b['name'], None, dur, None, '时刻异常'))
            continue

        seg, source = rg.find_segment(a['name'], b['name'], cls)
        if not seg or len(seg) < 2:
            rows.append((a['name'], b['name'], None, dur, None, '无几何'))
            continue

        km = sum(haversine_km(seg[i], seg[i + 1]) for i in range(len(seg) - 1))
        speed = km / (dur / 60.0) if dur > 0 else 0

        total_km += km
        total_min += dur
        measured += 1
        rows.append((a['name'], b['name'], km, dur, speed,
                     '真实轨道' if source == 'line' else '估算直线'))

    lines = [f"🚄 {code}（{cls}）{info.get('from', '')} → {info.get('to', '')}"]
    lines.append(f"   共 {len(sd)} 站 / {len(sd) - 1} 个区间")
    lines.append("")
    lines.append("   区间                    里程      用时      均速")
    lines.append("   " + "-" * 56)

    for a, b, km, dur, speed, note in rows:
        label = f"{a} → {b}"
        if len(label) > 22:
            label = label[:21] + "…"
        if km is None:
            lines.append(f"   {label:<22} {'—':>7} {_format_duration(dur):>8}   {note}")
        else:
            lines.append(f"   {label:<22} {km:>6.0f}km {_format_duration(dur):>8} "
                         f"{speed:>6.0f}km/h")

    lines.append("")
    if total_min > 0:
        avg = total_km / (total_min / 60.0)
        lines.append(f"   全程：约 {total_km:.0f}km，"
                     f"用时 {_format_duration(total_min)}，"
                     f"平均 {avg:.0f}km/h")
        lines.append(f"   （{measured}/{len(rows)} 个区间有完整数据）")

    notes = {n for *_, n in rows if n in ('无几何', '估算直线', '时刻缺失', '时刻异常')}
    if '无几何' in notes:
        lines.append("   注：部分区间无 OSM 轨道数据，未计入统计")
    if '估算直线' in notes:
        lines.append("   注：部分区间为估算直线，里程可能略有偏差")

    lines.append("")
    lines.append("   口径：平均速度 = 区间里程 ÷（到达时刻 − 出发时刻），"
                 "含停站时间，非最高运行速度")

    return '\n'.join(lines)


# ────────────────────────────────────────────────────────────
#  工具 2：线路上的站点
# ────────────────────────────────────────────────────────────

@tool(description="查询某条铁路线路上的站点列表。"
                  "当用户问「京沪线上有哪些站」「某条线经过哪些地方」时使用。"
                  "输入线路名，例如 '京沪线' 或 '京沪高铁'。")
def list_stations_on_line(line_name: str) -> str:
    """列出某条线路上的站点

    Args:
        line_name: 线路名，如 '京沪线'

    Returns:
        按线路几何顺序排列的站点列表
    """
    from agent.route_geometry import get_route_geometry

    name = (line_name or '').strip()
    if not name:
        return "请提供线路名"

    rg = get_route_geometry()
    rg._ensure_loaded()

    # 线路名精确匹配；找不到时给近似提示
    if name not in rg._lines:
        candidates = [n for n in rg._lines if name in n or n in name]
        if not candidates:
            return f"未找到线路「{name}」"
        top = sorted(candidates, key=lambda n: -rg._lines[n]['km'])[:5]
        return (f"未找到线路「{name}」。是否指：\n"
                + "\n".join(f"  · {n}（{rg._lines[n]['km']:.0f}km）" for n in top))

    ln = rg._lines[name]
    rg._build_line_station_index()
    stations = rg._line_stations.get(name, [])

    if not stations:
        return (f"线路「{name}」上没有匹配到站点"
                f"（线路全长 {ln['km']:.0f}km）")

    # _line_stations 存的是 [(sid, st), ...]，统一解包
    st_list = [st for _sid, st in stations]

    # 按在线路几何上的位置排序（用最近几何点的索引近似投影位置）
    geom = ln['geometry']
    step = max(1, len(geom) // 500)

    def _pos(st):
        best_i, best_d = 0, float('inf')
        slng, slat = st['lng'], st['lat']
        for i in range(0, len(geom), step):
            p = geom[i]
            d = (p[0] - slng) ** 2 + (p[1] - slat) ** 2
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    ordered = sorted(st_list, key=_pos)

    names = []
    for st in ordered:
        nm = st.get('name_zh') or st.get('name') or ''
        if nm and nm not in names:
            names.append(nm)

    lines = [f"🛤️ {name}",
             f"   全长 {ln['km']:.0f}km"
             + (f"，线路编号 {ln['ref']}" if ln.get('ref') else ''),
             f"   沿线站点 {len(names)} 个（从 {names[0]} 到 {names[-1]}）"
             if names else f"   沿线站点 0 个",
             ""]
    # 每行 6 个
    for i in range(0, len(names), 6):
        lines.append("   " + " · ".join(names[i:i + 6]))

    lines.append("")
    lines.append("   注：站点来自 OSM 沿线 3km 吸附，可能有遗漏或误纳；"
                 "排列方向取决于 OSM 线路几何走向")
    return '\n'.join(lines)


# ────────────────────────────────────────────────────────────
#  工具 3：经停某站的车次
# ────────────────────────────────────────────────────────────

@tool(description="查询经停某个车站的车次列表。"
                  "当用户问「郑州东有哪些车」「某站停哪些车」时使用。"
                  "输入站名，例如 '郑州东'。可选 limit 控制返回数量（默认 10）。")
def find_trains_at_station(station: str, limit: int = 10) -> str:
    """列出经停某站的车次

    Args:
        station: 站名，如 '郑州东'
        limit: 最多返回多少个车次，默认 10

    Returns:
        车次列表，含类型与经停序号
    """
    name = (station or '').strip()
    if not name:
        return "请提供站名"

    details = _load_details()
    hits = []
    for code, info in details.items():
        stations = info.get('stations') or []
        if name in stations:
            hits.append((code, info, stations.index(name) + 1))

    if not hits:
        # 给近似提示
        sample = set()
        for info in details.values():
            for s in info.get('stations') or []:
                if name in s or s in name:
                    sample.add(s)
        hint = ""
        if sample:
            hint = "\n是否指：\n" + "\n".join(f"  · {s}" for s in sorted(sample)[:5])
        return f"未找到经停「{name}」的车次{hint}"

    # 排序：G > D > C > Z > T > K
    priority = {'G': 0, 'D': 1, 'C': 2, 'Z': 3, 'T': 4, 'K': 5}
    hits.sort(key=lambda x: (priority.get(x[0][0], 9), x[0]))

    total = len(hits)
    shown = hits[:max(1, limit)]

    lines = [f"🚉 {name}：共 {total} 个车次经停"
             + (f"（显示前 {len(shown)} 个）" if total > len(shown) else ""),
             ""]

    by_class = {}
    for code, info, idx in hits:
        by_class.setdefault(info.get('class', '其他'), 0)
        by_class[info.get('class', '其他')] += 1
    lines.append("   车型分布：" + "，".join(
        f"{k} {v}" for k, v in sorted(by_class.items(), key=lambda x: -x[1])))
    lines.append("")

    for code, info, idx in shown:
        n = len(info.get('stations') or [])
        lines.append(f"   {code:<7} {info.get('class', ''):<5} "
                     f"{info.get('from', '')}→{info.get('to', '')}  "
                     f"（第 {idx}/{n} 站）")

    lines.append("")
    lines.append("   提示：可用 query_train_info 查具体车次的时刻表")
    return '\n'.join(lines)
