# -*- coding: utf-8 -*-
"""铁路线路几何消费层（运行时）

从 data/osm/out/ 读取离线构建的参考数据，为车次提供真实轨道几何。

设计要点：
  * 不依赖线路的"整体里程"——OSM 的 route=railway 关系常把上行/下行
    平行轨道都收录，整体拼接后里程会偏大或偏小。
  * 业务只需要"相邻两站之间"的局部几何，因此按站对从线路几何中截取。
    实测 93.7% 的站对路径/直线比值落在 0.8~2.5（中位 1.06），精度足够。
  * 数据缺失时优雅降级为直线，不抛异常。

用法：
    from agent.route_geometry import RouteGeometry
    rg = RouteGeometry()
    seg, source = rg.find_segment("合肥", "北京丰台")
    # seg: [[lng, lat], ...]  source: "line" | "fallback"
"""

import json
import logging
import math
import os
import re
import threading

logger = logging.getLogger("tool_calls")

# 站对路径/直线比值超过此值视为错配（绕远路）
MAX_DETOUR_RATIO = 3.0
# 站点到线路几何的最大吸附距离（km）
MAX_SNAP_KM = 5.0


def haversine_km(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def traj_length(pts):
    return sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


class RouteGeometry:
    """线路几何查询（懒加载 + 线程安全单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self, data_dir=None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        if data_dir is None:
            try:
                from settings import settings as config_data
                data_dir = config_data.route_data_dir
            except Exception:
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                data_dir = os.path.join(root, "data", "osm", "out")

        self.data_dir = data_dir
        self._lines = None
        self._stations = None
        self._name_index = None
        self._load_lock = threading.Lock()

    # ── 加载 ──────────────────────────────────────────────

    @property
    def available(self):
        return (os.path.exists(os.path.join(self.data_dir, "rail_lines.json"))
                and os.path.exists(os.path.join(self.data_dir, "stations.json")))

    def _ensure_loaded(self):
        if self._lines is not None:
            return
        with self._load_lock:
            if self._lines is not None:
                return

            lines_path = os.path.join(self.data_dir, "rail_lines.json")
            stations_path = os.path.join(self.data_dir, "stations.json")

            if not os.path.exists(lines_path) or not os.path.exists(stations_path):
                logger.warning("OSM 参考数据缺失，路线图将退化为直线: %s", self.data_dir)
                self._lines = {}
                self._stations = {}
                self._name_index = {}
                return

            with open(lines_path, encoding="utf-8") as f:
                self._lines = json.load(f).get("lines", {})
            with open(stations_path, encoding="utf-8") as f:
                self._stations = json.load(f).get("stations", {})

            # 站名 -> 站点记录（name_zh 优先，其次 name / aliases）
            index = {}
            for sid, st in self._stations.items():
                for key in (st.get("name_zh"), st.get("name")):
                    if key and key not in index:
                        index[key] = st
                for alias in st.get("aliases") or []:
                    if alias and alias not in index:
                        index[alias] = st
            self._name_index = index

            logger.info("已加载 OSM 参考数据: %d 条线路, %d 个站点",
                        len(self._lines), len(self._stations))

    # ── 查询 ──────────────────────────────────────────────

    def resolve_station(self, name):
        """站名 -> 站点记录（含 lng/lat/lines）"""
        self._ensure_loaded()
        if not name:
            return None
        key = name.replace(" ", "").strip()
        st = self._name_index.get(key)
        if st:
            return st
        # 去/加"站"后缀
        if key.endswith("站"):
            st = self._name_index.get(key[:-1])
        else:
            st = self._name_index.get(key + "站")
        return st

    def station_coord(self, name):
        st = self.resolve_station(name)
        return (st["lng"], st["lat"]) if st else None

    @staticmethod
    def _nearest_index(pt, geom):
        best_i, best_d = 0, float("inf")
        for i, p in enumerate(geom):
            d = haversine_km(pt, p)
            if d < best_d:
                best_i, best_d = i, d
        return best_i, best_d

    # ── 线路等级判定（用于消歧）──────────────────────────

    # 线路名里出现这些词 => 高速铁路
    HIGH_SPEED_HINTS = ("高速", "客专", "高铁", "城际")
    # 线路名里出现这些词 => 明显是普速干线（不含"线"的宽泛匹配）
    CONVENTIONAL_HINTS = ("联络线", "绕行", "走行", "疏解", "专用线", "货线",
                          "到达线", "出发线", "直通线", "环线", "支线")
    # 纯股道名（如 "1道"、"II道"）不是线路
    TRACK_NAME_RE = None

    @classmethod
    def line_grade(cls, name):
        """判线路等级：'high_speed' | 'conventional' | 'other'

        判据来自 OSM 线路命名惯例：
          高速线 / 客专线 / 高铁 / 城际线  => 高速铁路
          联络线 / 绕行线 / 专用线 / 环线   => 普速或支线
        """
        if not name:
            return "other"
        if re.search(r"^\d+道$|^[IVX]+道$", name):
            return "other"
        for h in cls.HIGH_SPEED_HINTS:
            if h in name:
                return "high_speed"
        for h in cls.CONVENTIONAL_HINTS:
            if h in name:
                return "conventional"
        return "other"

    def _candidates(self, sa, sb, train_class=None):
        """列出两站共同的候选线路，按"优先级 + 长度"排序

        消歧依据（优先级从高到低）：
          1. 车次类型先验：G/D/C 优先高速线；K/T/Z 优先普速线
          2. 线路长度：更长的更可能是主干线
          3. 线路名不含"联络线/走行线"等支线特征
        """
        names = set(sa.get("lines") or []) & set(sb.get("lines") or [])
        if not names:
            return []

        # 车次类型 -> 期望等级
        want = None
        if train_class in ("高铁", "高速", "动车", "城际"):
            want = "high_speed"
        elif train_class in ("直特", "直达特快", "特快", "快速", "普快", "普客"):
            want = "conventional"

        line_km = self._line_km
        grade_of = self.line_grade
        conv = self.CONVENTIONAL_HINTS

        def score(name):
            grade = grade_of(name)
            s = 0.0
            if want and grade == want:
                s += 1000.0
            elif want and grade != "other":
                s -= 200.0
            # 长度是次要因素（对数缩放，避免超长线路压倒一切）
            s += math.log10(max(line_km(name), 1.0)) * 10.0
            if grade == "other" and any(h in name for h in conv):
                s -= 50.0
            return s

        return sorted(names, key=score, reverse=True)

    def _line_km(self, name):
        ln = self._lines.get(name)
        if not ln:
            return 0.0
        return ln.get("km") or 0.0

    def find_segment(self, from_station, to_station, train_class=None):
        """查两站之间的真实轨道几何

        Args:
            from_station, to_station: 站名
            train_class: 车次类型（"高铁"/"动车"/"直特"/"快速"…），
                         用于在多条候选线路中消歧；None 则仅按长度排序

        Returns:
            (points, source)
              points: [[lng, lat], ...]；失败时返回两站直线
              source: "line"（真实轨道）| "fallback"（直线）| "no_station"
        """
        self._ensure_loaded()

        sa = self.resolve_station(from_station)
        sb = self.resolve_station(to_station)
        if not sa or not sb:
            return None, "no_station"

        pa = (sa["lng"], sa["lat"])
        pb = (sb["lng"], sb["lat"])
        straight = haversine_km(pa, pb)

        # 1) 两站同属一条线路：按优先级逐个尝试截取
        seg = self._segment_on_common_line(sa, sb, pa, pb, straight, train_class)
        if seg:
            return seg, "line"

        # 2) 不共享线路：找一个同时连接两站的中间站，分两段拼接
        seg = self._segment_via_intermediate(sa, sb, pa, pb, straight, train_class)
        if seg:
            return seg, "line"

        return [list(pa), list(pb)], "fallback"

    def _segment_on_common_line(self, sa, sb, pa, pb, straight, train_class=None):
        """两站同属一条线路时，从该线路几何中截取"""
        for name in self._candidates(sa, sb, train_class):
            ln = self._lines.get(name)
            if not ln:
                continue
            geom = ln["geometry"]
            ia, da = self._nearest_index(pa, geom)
            ib, db = self._nearest_index(pb, geom)
            if ia == ib:
                continue
            if da > MAX_SNAP_KM or db > MAX_SNAP_KM:
                continue

            seg = geom[ia:ib + 1] if ia < ib else list(reversed(geom[ib:ia + 1]))
            if len(seg) < 2:
                continue

            if straight > 0.5:
                ratio = traj_length(seg) / straight
                if ratio > MAX_DETOUR_RATIO or ratio < 0.5:
                    continue

            return [[round(p[0], 5), round(p[1], 5)] for p in seg]
        return None

    def _segment_via_intermediate(self, sa, sb, pa, pb, straight, train_class=None):
        """两站不共享线路时，找一个中间站桥接

        典型场景：合肥 -> 北京丰台。两站分属不同线路，
        但都连到同一个枢纽站（如徐州），可拆成两段。
        """
        lines_a = set(sa.get("lines") or [])
        lines_b = set(sb.get("lines") or [])
        if not lines_a or not lines_b:
            return None

        # 候选中间站：同时出现在 A 的线路与 B 的线路上的站点
        best = None
        for sid, st in self._stations.items():
            if st.get("kind") == "metro":
                continue
            st_lines = set(st.get("lines") or [])
            if not st_lines:
                continue
            if not (st_lines & lines_a) or not (st_lines & lines_b):
                continue

            pc = (st["lng"], st["lat"])
            # 中间站必须真的在 A、B 之间（避免绕远）
            detour = haversine_km(pa, pc) + haversine_km(pc, pb)
            if straight > 0.5 and detour / straight > 1.6:
                continue

            if best is None or detour < best[0]:
                best = (detour, st)

        if best is None:
            return None

        mid = best[1]
        pc = (mid["lng"], mid["lat"])
        seg1 = self._segment_on_common_line(sa, mid, pa, pc,
                                            haversine_km(pa, pc), train_class)
        seg2 = self._segment_on_common_line(mid, sb, pc, pb,
                                            haversine_km(pc, pb), train_class)
        if not seg1 or not seg2:
            return None

        merged = seg1 + seg2[1:]
        if straight > 0.5:
            ratio = traj_length(merged) / straight
            if ratio > MAX_DETOUR_RATIO:
                return None
        return merged

    def build_route(self, stations, train_class=None):
        """为一串站点构建完整路线

        Args:
            stations: 站名序列
            train_class: 车次类型，用于在多条候选线路中消歧

        Returns:
            (points, stats)
              points: [[lng, lat], ...]
              stats: {"total": n, "matched": n, "fallback": n, "missing": n,
                      "lines": {线路名: 使用次数}}
        """
        points = []
        stats = {"total": 0, "matched": 0, "fallback": 0, "missing": 0,
                 "lines": {}}

        for i in range(len(stations) - 1):
            stats["total"] += 1
            seg, source = self.find_segment(stations[i], stations[i + 1], train_class)

            if source == "no_station" or not seg:
                stats["missing"] += 1
                continue
            if source == "line":
                stats["matched"] += 1
            else:
                stats["fallback"] += 1

            if points and seg:
                if (abs(points[-1][0] - seg[0][0]) < 1e-4
                        and abs(points[-1][1] - seg[0][1]) < 1e-4):
                    points.extend(seg[1:])
                else:
                    points.extend(seg)
            else:
                points.extend(seg)

        return points, stats


def get_route_geometry():
    """获取全局单例"""
    return RouteGeometry()
