# -*- coding: utf-8 -*-
"""同城枢纽换乘提示

提供两个 Agent 工具：
  - find_same_city_stations: 某城市有哪些火车站
  - suggest_transfer:         某次行程是否可以换乘（同城换站 / 同站换车）

## 能力边界（重要）

本模块只做「提示」，不做真实换乘规划：

  能做：识别同城多站、列出两站间是否有直达接驳车次、给出换乘建议方向
  不能做：精确换乘时刻衔接（需要完整运行图 + 中转换乘算法）

与 12306 的换乘方案有本质差距，输出中会明确说明。

## 同城识别规则

不给每个站手写城市归属（2700 个站不可维护），改用「命名规律 + 白名单」：

  1. 「城市名 + 方位词」：北京南 / 上海虹桥 → 归到 北京 / 上海
  2. 少量例外白名单：上海虹桥、北京丰台、郑州航空港 等非方位词后缀
  3. 只保留车次 ≥ MIN_TRAINS 的站，过滤镇级小站（避免「渭南镇」误归「渭南」）

实测识别出 143 个多站枢纽，误判基本为零。
"""

import json
import logging
import os
import re

from langchain_core.tools import tool

logger = logging.getLogger("tool_calls")

_data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_details_path = os.path.join(_data_dir, 'train_details.json')

# 站点至少有多少车次才参与枢纽识别（过滤镇级/乘降所小站）
MIN_TRAINS = 50

# 方位词后缀
_AZ_RE = re.compile(r"^(.*?)(东|西|南|北)$")

# 非方位词后缀但确实是同城主力站的例外
_EXTRA_HUBS = {
    "上海": ["上海虹桥"],
    "北京": ["北京丰台", "北京朝阳"],
    "深圳": ["深圳坪山"],
    "郑州": ["郑州航空港"],
}

_details = None
_hubs = None
_station_trains = None
_station_to_hub = None


# ────────────────────────────────────────────────────────────
#  数据加载与索引
# ────────────────────────────────────────────────────────────

def _load_details():
    global _details
    if _details is None:
        with open(_details_path, 'r', encoding='utf-8') as f:
            _details = json.load(f)
        logger.info(f"[analytics] 加载 train_details: {len(_details)} 个车次")
    return _details


def _build_indexes():
    """构建 枢纽映射 / 站点车次索引（懒加载）"""
    global _hubs, _station_trains, _station_to_hub
    if _hubs is not None:
        return

    details = _load_details()

    # 站点 -> 经停车次列表
    station_trains = {}
    for code, info in details.items():
        for idx, s in enumerate(info.get('stations') or []):
            station_trains.setdefault(s, []).append((code, info, idx + 1))

    used = set(station_trains)

    # 枢纽识别
    groups = {}
    for s in used:
        if len(station_trains[s]) < MIN_TRAINS:
            continue
        m = _AZ_RE.match(s)
        if m:
            base = m.group(1)
            if base in used:
                groups.setdefault(base, {base}).add(s)

    for city, extras in _EXTRA_HUBS.items():
        if city in used:
            for e in extras:
                if e in used:
                    groups.setdefault(city, {city}).add(e)

    # 只保留确实多站的
    groups = {k: v for k, v in groups.items() if len(v) >= 2}

    # 站名 -> 所属枢纽
    station_to_hub = {}
    for city, sts in groups.items():
        for s in sts:
            station_to_hub[s] = city

    _hubs = groups
    _station_trains = station_trains
    _station_to_hub = station_to_hub
    logger.info(f"[analytics] 识别 {len(groups)} 个多站枢纽")


# ────────────────────────────────────────────────────────────
#  工具 1：同城车站列表
# ────────────────────────────────────────────────────────────

@tool(description="查询某个城市有哪几个火车站（同城多站）。"
                  "当用户问「北京有几个火车站」「上海有哪些站」时使用。"
                  "输入城市名或其中一个站名，例如 '北京' 或 '北京南'。")
def find_same_city_stations(city_or_station: str) -> str:
    """列出同城车站

    Args:
        city_or_station: 城市名（北京）或任一车站名（北京南）

    Returns:
        该城市的所有车站及各自车次数
    """
    name = (city_or_station or '').strip()
    if not name:
        return "请提供城市名或站名"

    _build_indexes()

    # 输入是城市名，或某个已知枢纽站
    city = name if name in _hubs else _station_to_hub.get(name)
    if not city:
        # 给近似提示
        near = [c for c in _hubs if name in c or c in name]
        if near:
            return ("未找到同城多站信息。是否指：\n"
                    + "\n".join(f"  · {c}（{len(_hubs[c])} 站）" for c in near[:5]))
        return f"「{name}」不是多站枢纽城市，或该站车次较少未被收录"

    stations = sorted(_hubs[city])

    lines = [f"🏙️ {city}：共 {len(stations)} 个火车站", ""]
    for s in stations:
        n = len(_station_trains.get(s) or [])
        lines.append(f"   {s:<10} {n:>5} 个车次经停")

    # 同城站之间的接驳
    hub = _hubs[city]
    links = []
    for a in sorted(hub):
        for b in sorted(hub):
            if a >= b:
                continue
            for code, info, _idx in (_station_trains.get(a) or []):
                st = info.get('stations') or []
                if b in st and st.index(a) < st.index(b):
                    links.append((a, b, code))
                    break

    if links:
        lines.append("")
        lines.append(f"   同城站间有 {len(links)} 组直达接驳，例如：")
        for a, b, code in links[:5]:
            lines.append(f"     {a} → {b}  乘 {code}")

    lines.append("")
    lines.append("   注：同城不同站之间通常需地铁/公交接驳，"
                 "跨站换乘请预留 60 分钟以上")
    return '\n'.join(lines)


# ────────────────────────────────────────────────────────────
#  工具 2：换乘提示
# ────────────────────────────────────────────────────────────

@tool(description="判断一段行程是否需要换乘，并给出提示。"
                  "当用户问「北京到上海怎么换乘」「有没有直达」「需要中转吗」时使用。"
                  "输入出发站与到达站，例如 from_station='北京南', to_station='上海虹桥'。"
                  "注意：只做提示，不做精确时刻衔接规划。")
def suggest_transfer(from_station: str, to_station: str) -> str:
    """判断并提示换乘方案

    Args:
        from_station: 出发站
        to_station: 到达站

    Returns:
        直达情况 + 同城换站建议 + 能力边界说明
    """
    a = (from_station or '').strip()
    b = (to_station or '').strip()
    if not a or not b:
        return "请提供出发站和到达站"

    details = _load_details()
    _build_indexes()

    # 1) 直达车次
    direct = []
    for code, info in details.items():
        st = info.get('stations') or []
        if a in st and b in st and st.index(a) < st.index(b):
            direct.append((code, info.get('class', ''), info.get('from', ''),
                           info.get('to', '')))

    hub_a = _station_to_hub.get(a)
    hub_b = _station_to_hub.get(b)

    lines = [f"🚏 {a} → {b}", ""]

    if direct:
        # 按车型优先排序
        priority = {'G': 0, 'D': 1, 'C': 2, 'Z': 3, 'T': 4, 'K': 5}
        direct.sort(key=lambda x: (priority.get(x[0][0], 9), x[0]))
        lines.append(f"   ✅ 有 {len(direct)} 趟直达车次，无需换乘：")
        for code, cls, f, t in direct[:8]:
            lines.append(f"      {code:<7} {cls:<5} {f}→{t}")
        if len(direct) > 8:
            lines.append(f"      …… 另有 {len(direct) - 8} 趟")
        lines.append("")
        lines.append("   提示：可用 query_train_info 查具体时刻与经停站")
        return '\n'.join(lines)

    lines.append("   ❌ 无直达车次")

    # 2) 同城换站建议
    suggestions = []
    if hub_a and hub_b and hub_a != hub_b:
        for sa in sorted(_hubs[hub_a]):
            for sb in sorted(_hubs[hub_b]):
                for code, info, _i in (_station_trains.get(sa) or []):
                    st = info.get('stations') or []
                    if sb in st and st.index(sa) < st.index(sb):
                        suggestions.append((sa, sb, code, hub_a, hub_b))
                        break

    if suggestions:
        lines.append("")
        lines.append(f"   💡 换站方案：{hub_a} 与 {hub_b} 是相邻枢纽，可跨城接驳")
        for sa, sb, code, ha, hb in suggestions[:6]:
            note = ""
            if sa != a:
                note += f"（需先从 {a} 到 {sa}，同城）"
            if sb != b:
                note += f"（需再从 {sb} 到 {b}，同城）"
            lines.append(f"      {sa} → {sb}  乘 {code}{note}")

    # 3) 同城不同站：提示换站
    if hub_a and hub_a == hub_b and a != b:
        lines.append("")
        lines.append(f"   💡 {a} 与 {b} 同属 {hub_a}，可乘同城接驳车次：")
        cnt = 0
        for sa in sorted(_hubs[hub_a]):
            for code, info, _i in (_station_trains.get(sa) or []):
                st = info.get('stations') or []
                if b in st and st.index(sa) < st.index(b):
                    lines.append(f"      {sa} → {b}  乘 {code}")
                    cnt += 1
                    break
            if cnt >= 4:
                break

    if not suggestions and not (hub_a and hub_a == hub_b):
        lines.append("")
        lines.append("   建议：可尝试查询相邻大站，或考虑经枢纽城市中转")

    lines.append("")
    lines.append("   ⚠️ 说明：本工具只做连接关系提示，"
                 "不含精确换乘时刻衔接（需完整运行图）。"
                 "实际出行请以 12306 换乘方案为准。")
    return '\n'.join(lines)
