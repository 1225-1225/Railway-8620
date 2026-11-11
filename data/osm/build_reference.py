# -*- coding: utf-8 -*-
"""从 OSM .osm.pbf 构建铁路参考数据（离线，一次性）

## 数据源选择（重要）

不用 `route=railway` 关系，而是用 **way 的 name 标签**。原因：

  沪昆线有 5360 个 `railway=rail` 且 `name=沪昆线` 的 way，
  但对应的 `route=railway` 关系只收录了 10 个（0.2%）。
  若只读关系，绝大多数线路会"凭空消失"。

  实测：关系法只覆盖 1932 条线路；name 法覆盖 3244 条（+68%）。

## 里程为什么要特殊处理

OSM 把**每一股道**都画成独立 way，全部带同一个 name：

    {'railway':'rail','name':'京沪线','oneway':'yes'}             ← 上行
    {'railway':'rail','name':'京沪线','railway:track_ref':'II-II'} ← 下行
    {'railway':'rail','name':'京沪线','passenger_lines':'3'}       ← 第三股道

因此"所有 way 长度求和"会得到约 2 倍里程（实测京沪 3093 vs 实际 1463）。

解法：把该线路所有 way 建成图，取**地理上最远的一对端点**，
在图上求**最短路** —— 最短路天然只走其中一条轨道。

## 产物

  stations.json            站点表（以 OSM 要素 id 为主键）
  rail_lines.json          线路表（单轨几何 + 沿线站点）
  station_line_index.json  站点 -> 线路名

用法：
  python data/osm/build_reference.py
  python data/osm/build_reference.py --limit 50     # 调试：只处理 50 条线路
"""

import argparse
import array
import glob
import heapq
import io
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import osmium

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
PBF_DIR = os.path.join(PROJECT_ROOT, "data", "pbf")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "osm", "out")

LNG_MIN, LNG_MAX = 70.0, 140.0
LAT_MIN, LAT_MAX = 15.0, 55.0

METRO_STATION = {"subway", "light_rail", "monorail", "funicular", "tram"}

# 线路几何降采样
POINTS_PER_100KM = 30
MAX_POINTS_PER_LINE = 4000

# 站点吸附到线路的最大距离（km）
STATION_SNAP_KM = 3.0

# 线路名里出现这些词视为城市轨道，不作为国铁线路
METRO_NAME_HINTS = ("地铁", "Metro", "metro", "轻轨", "有轨电车", "磁浮", "捷运")


def log(msg):
    print(msg, flush=True)


def hr(title=""):
    print("\n" + "=" * 70, flush=True)
    if title:
        print(title, flush=True)
        print("=" * 70, flush=True)


# ────────────────────────────────────────────────────────────
#  几何工具
# ────────────────────────────────────────────────────────────

def haversine_km(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def traj_length(pts):
    return sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def downsample(pts, per_100km=POINTS_PER_100KM, cap=MAX_POINTS_PER_LINE):
    """按里程等距降采样；始终保留首尾点"""
    if len(pts) <= 2:
        return [[round(p[0], 5), round(p[1], 5)] for p in pts]

    total = traj_length(pts)
    if total < 0.05:
        return [[round(pts[0][0], 5), round(pts[0][1], 5)],
                [round(pts[-1][0], 5), round(pts[-1][1], 5)]]

    target = max(2, min(cap, int(total / 100.0 * per_100km)))
    if target >= len(pts):
        return [[round(p[0], 5), round(p[1], 5)] for p in pts]

    step = total / (target - 1)
    out = [pts[0]]
    acc = 0.0
    nxt = step
    for i in range(1, len(pts) - 1):
        acc += haversine_km(pts[i - 1], pts[i])
        if acc >= nxt:
            out.append(pts[i])
            nxt += step
    out.append(pts[-1])
    return [[round(p[0], 5), round(p[1], 5)] for p in out]


# ────────────────────────────────────────────────────────────
#  图算法
# ────────────────────────────────────────────────────────────

def build_graph(way_ids, way_refs, coords):
    """把一组 way 建成无向图（节点 = OSM node id，边权 = 实际距离）"""
    adj = defaultdict(list)
    for wid in way_ids:
        ids = way_refs.get(wid)
        if not ids:
            continue
        prev = None
        for nid in ids:
            c = coords.get(nid)
            if c is None:
                prev = None
                continue
            if prev is not None and prev != nid:
                w = haversine_km(coords[prev], c)
                adj[prev].append((nid, w))
                adj[nid].append((prev, w))
            prev = nid
    return adj


def dijkstra(adj, src):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    seen = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def connected_components(adj):
    seen = set()
    comps = []
    for start in adj:
        if start in seen:
            continue
        stack = [start]
        comp = set()
        while stack:
            u = stack.pop()
            if u in comp:
                continue
            comp.add(u)
            for v, _ in adj[u]:
                if v not in comp:
                    stack.append(v)
        seen |= comp
        comps.append(comp)
    return comps


def geo_farthest(adj, coords, src):
    """从 src 出发，按地理直线距离找最远节点"""
    base = coords.get(src)
    if not base:
        return src, 0.0
    best, best_d = src, -1.0
    for n in adj:
        c = coords.get(n)
        if not c:
            continue
        d = haversine_km(base, c)
        if d > best_d:
            best, best_d = n, d
    return best, best_d


def single_track_path(adj, coords):
    """在含多股道的图上，提取"一条轨道"的走向

    做法：按地理直线距离找到线路两端，再求最短路。
    最短路天然只走其中一条轨道，因此里程不会翻倍。

    注意：平行轨道在车站处相连会形成"梯子图"（一串环），
    最短路可能沿环绕行造成 30km 尺度的折返（实测湘桂线、
    京哈线、中老昆万线）。因此对路径做折返检测，一旦发现
    就换用"优先朝目标方向推进"的启发式搜索。
    """
    if not adj:
        return [], 0.0
    start = next(iter(adj))
    a, _ = geo_farthest(adj, coords, start)
    b, _ = geo_farthest(adj, coords, a)
    if a == b:
        return [], 0.0

    path, km = _dijkstra_path(adj, a, b)
    if not path:
        return [], 0.0

    # 折返检测：真实铁路不会在 30km 尺度掉头
    if _path_has_reversal(path, coords):
        path2, km2 = _directional_search(adj, coords, a, b)
        if path2 and not _path_has_reversal(path2, coords):
            return path2, km2

    return path, km


def _dijkstra_path(adj, a, b):
    dist, prev = dijkstra(adj, a)
    if b not in dist:
        return [], 0.0
    path = [b]
    cur = b
    while cur != a:
        cur = prev.get(cur)
        if cur is None:
            return [], 0.0
        path.append(cur)
    path.reverse()
    return path, dist[b]


def _path_has_reversal(node_path, coords, max_deg=150.0, min_seg_km=0.5):
    """路径中是否存在方位突变（折返）"""
    if len(node_path) < 3:
        return False
    pts = [coords[n] for n in node_path if n in coords]
    for i in range(1, len(pts) - 1):
        if haversine_km(pts[i - 1], pts[i]) < min_seg_km:
            continue
        if haversine_km(pts[i], pts[i + 1]) < min_seg_km:
            continue
        b1 = bearing_deg(pts[i - 1], pts[i])
        b2 = bearing_deg(pts[i], pts[i + 1])
        if angle_diff(b1, b2) > max_deg:
            return True
    return False


def _directional_search(adj, coords, a, b, penalty_deg=60.0):
    """带方向惩罚的 Dijkstra

    目标方向 = a -> b 的大圆方位。对"反向推进"的边加重惩罚，
    使搜索倾向于沿线路主方向前进，绕开平行轨道形成的环。
    """
    target_bearing = bearing_deg(coords[a], coords[b])
    dist = {a: 0.0}
    prev = {}
    pq = [(0.0, a)]
    seen = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        if u == b:
            break
        for v, w in adj[u]:
            nd = d + w
            cu, cv = coords.get(u), coords.get(v)
            if cu and cv:
                back = angle_diff(bearing_deg(cu, cv), target_bearing)
                # 反向（>90°）加倍惩罚；60-90° 轻度惩罚
                if back > 90.0:
                    nd += w * 1.5
                elif back > penalty_deg:
                    nd += w * 0.3
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    if b not in prev and a != b:
        return [], 0.0

    path = [b]
    cur = b
    while cur != a:
        cur = prev.get(cur)
        if cur is None:
            return [], 0.0
        path.append(cur)
    path.reverse()

    # 返回真实里程（不用带惩罚的距离）
    real = sum(haversine_km(coords[path[i]], coords[path[i + 1]])
               for i in range(len(path) - 1)
               if path[i] in coords and path[i + 1] in coords)
    return path, real


def path_covered_ratio(pts, grid, cell=0.02, tol_km=2.0):
    """pts 中多大比例落在 grid 已有点的 tol_km 内"""
    if not pts:
        return 0.0
    hit = 0
    for p in pts:
        cx, cy = int(p[0] / cell), int(p[1] / cell)
        found = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in grid.get((cx + dx, cy + dy), ()):
                    if haversine_km(p, q) <= tol_km:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            hit += 1
    return hit / len(pts)


def add_to_grid(pts, grid, cell=0.02):
    for p in pts:
        grid.setdefault((int(p[0] / cell), int(p[1] / cell)), []).append(p)



def bearing_deg(a, b):
    """a -> b 的方位角（0=正北，顺时针）"""
    (lng1, lat1), (lng2, lat2) = a, b
    dx = (lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    dy = lat2 - lat1
    return math.degrees(math.atan2(dx, dy)) % 360.0


def angle_diff(b1, b2):
    d = abs(b1 - b2) % 360.0
    return d if d <= 180.0 else 360.0 - d



def stitch_pieces_along_axis(pieces, max_gap_km=30.0):
    """沿线路主轴排序后拼接分段

    为什么不能只按"端点最近"贪心拼接：
      线路被切成多段时，各段方向可能相反。实测湘桂线 3 段
      （532/250/225 km）按端点最近拼接会在中段产生 34.7km 折返。

    做法：
      1. 用所有分段的端点拟合线路主轴方向（取相距最远的两点）
      2. 把每段投影到主轴上，得到区间 [t_min, t_max]
      3. 按 t_min 排序
      4. 逐段拼接时，方向取"使其 t 递增"的那一端
    """
    if not pieces:
        return [], 0.0
    if len(pieces) == 1:
        return list(pieces[0]), traj_length(pieces[0])

    # 主轴：所有端点中最远的一对
    all_pts = [p for pts in pieces for p in (pts[0], pts[-1])]
    o = all_pts[0]
    a, _ = max(((p, haversine_km(o, p)) for p in all_pts), key=lambda x: x[1])
    b, _ = max(((p, haversine_km(a, p)) for p in all_pts), key=lambda x: x[1])

    (lng1, lat1), (lng2, lat2) = a, b
    dx = lng2 - lng1
    dy = lat2 - lat1
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return list(pieces[0]), traj_length(pieces[0])
    ux, uy = dx / norm, dy / norm

    def project(p):
        return (p[0] - lng1) * ux + (p[1] - lat1) * uy

    # 每段：(t_min, t_max, pts, 是否需翻转)
    entries = []
    for pts in pieces:
        t0, t1 = project(pts[0]), project(pts[-1])
        if t0 <= t1:
            entries.append((t0, t1, pts, False))
        else:
            entries.append((t1, t0, pts, True))
    entries.sort(key=lambda x: x[0])

    chain = []
    for t0, t1, pts, rev in entries:
        seg = pts[::-1] if rev else pts
        if not chain:
            chain = list(seg)
            continue
        gap = haversine_km(chain[-1], seg[0])
        if gap > max_gap_km:
            # 接不上就尝试接在链首（线路可能从另一端开始）
            if haversine_km(seg[-1], chain[0]) <= max_gap_km:
                chain = list(seg) + chain
            continue
        chain.extend(seg[1:])

    cleaned = []
    for p in chain:
        if not cleaned or (abs(cleaned[-1][0] - p[0]) > 1e-7
                           or abs(cleaned[-1][1] - p[1]) > 1e-7):
            cleaned.append(p)
    return cleaned, traj_length(cleaned)


def assemble_line(adj, coords, dedup_ratio=0.5, max_gap_km=30.0):
    """装配一条线路的单轨几何

    多条 way 会形成多个连通分量（缺段、跨 bbox 等）。
    每个分量提取一条轨道，按几何覆盖率去重平行轨道，再按端点就近拼接。

    max_gap_km 控制拼接容差：端点相距超过此值视为独立支线，不硬接
    （硬接会在图上画出长直线，里程也会虚高）。
    实测沪昆线若不设此限，会因拼接断开的分支而多算 51%。
    """
    comps = connected_components(adj)
    pieces = []
    for comp in comps:
        if len(comp) < 2:
            continue
        sub = {u: [(v, w) for v, w in adj[u] if v in comp] for u in comp}
        node_path, km = single_track_path(sub, coords)
        if len(node_path) < 2:
            continue
        pts = [coords[n] for n in node_path if n in coords]
        if len(pts) >= 2:
            pieces.append((km, pts))

    if not pieces:
        return [], 0.0

    pieces.sort(key=lambda x: -x[0])

    kept = []
    grid = {}
    for km, pts in pieces:
        if kept and path_covered_ratio(pts, grid) >= dedup_ratio:
            continue
        kept.append((km, pts))
        add_to_grid(pts, grid)

    # 沿主轴排序拼接（避免"端点最近"贪心在方向各异的段间产生折返）
    return stitch_pieces_along_axis([pts for _, pts in kept], max_gap_km)


def split_at_big_gaps(pts, max_gap_km=50.0):
    """把几何在超大间距处切开，返回所有有效分段

    拼接后若仍存在 > max_gap_km 的跳变，说明是错误接续，
    会在图上画出长直线。此时切开，各段独立保留。

    返回 [(长度km, 点列), ...]，按长度降序。
    """
    if len(pts) < 2:
        return []

    segments = []
    cur = [pts[0]]
    for i in range(1, len(pts)):
        if haversine_km(pts[i - 1], pts[i]) > max_gap_km:
            if len(cur) >= 2:
                segments.append(cur)
            cur = [pts[i]]
        else:
            cur.append(pts[i])
    if len(cur) >= 2:
        segments.append(cur)

    result = [(traj_length(s), s) for s in segments if len(s) >= 2]
    result.sort(key=lambda x: -x[0])
    return result


# ────────────────────────────────────────────────────────────
#  站点沿线匹配（空间网格加速）
# ────────────────────────────────────────────────────────────

def make_grid(points, cell=0.05):
    g = defaultdict(list)
    for p in points:
        g[(int(p[0] / cell), int(p[1] / cell))].append(p)
    return g


def near_any(pt, grid, tol_km, cell=0.05):
    cx, cy = int(pt[0] / cell), int(pt[1] / cell)
    r = int(tol_km / (cell * 111.0)) + 1
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            for q in grid.get((cx + dx, cy + dy), ()):
                if haversine_km(pt, q) <= tol_km:
                    return True
    return False


# ────────────────────────────────────────────────────────────
#  Pass 1：收集带 name 的铁路 way（同时拿到节点引用）
# ────────────────────────────────────────────────────────────

class WayCollector:
    def __init__(self):
        self.lines = defaultdict(set)        # name -> {way_id}
        self.way_refs = {}                   # way_id -> array('q')
        self.line_tags = {}                  # name -> {ref, usage, operator}
        self.raw_ways = 0
        self.named_ways = 0

    def scan(self, path, thread_pool):
        fp = osmium.FileProcessor(path, osmium.osm.WAY, thread_pool=thread_pool)
        fp.with_filter(osmium.filter.KeyFilter("railway"))
        for w in fp:
            if w.tags.get("railway") != "rail":
                continue
            self.raw_ways += 1

            name = (w.tags.get("name") or "").strip()
            if not name:
                continue

            ids = array.array("q")
            for n in w.nodes:
                ids.append(n.ref)
            if len(ids) < 2:
                continue

            self.named_ways += 1
            self.lines[name].add(w.id)
            self.way_refs[w.id] = ids

            if name not in self.line_tags:
                self.line_tags[name] = {
                    "ref": (w.tags.get("ref") or "").strip(),
                    "usage": (w.tags.get("usage") or "").strip(),
                    "operator": (w.tags.get("operator") or "").strip(),
                }


# ────────────────────────────────────────────────────────────
#  Pass 2：节点坐标 + 站点
# ────────────────────────────────────────────────────────────

class NodeCollector:
    def __init__(self, thread_pool):
        self.thread_pool = thread_pool
        self.coords = {}
        self.stations = {}
        self.station_nodes = 0

    def scan_nodes(self, path, needed_nodes):
        if not needed_nodes:
            return
        fp = osmium.FileProcessor(path, osmium.osm.NODE,
                                  thread_pool=self.thread_pool)
        fp.with_filter(osmium.filter.IdFilter(needed_nodes))
        for n in fp:
            if n.location.valid():
                self.coords[n.id] = (n.location.lon, n.location.lat)

    def scan_stations(self, path):
        fp = osmium.FileProcessor(path, osmium.osm.NODE,
                                  thread_pool=self.thread_pool)
        fp.with_filter(osmium.filter.KeyFilter("railway"))
        for n in fp:
            if n.tags.get("railway") not in ("station", "halt"):
                continue
            self.station_nodes += 1
            if not n.location.valid():
                continue
            lat, lng = n.location.lat, n.location.lon
            if not (LNG_MIN <= lng <= LNG_MAX and LAT_MIN <= lat <= LAT_MAX):
                continue
            self.stations[n.id] = self._make(n, lat, lng)

    @staticmethod
    def _make(n, lat, lng):
        t = n.tags
        raw = t.get("name") or ""

        name_zh = ""
        for key in ("name:zh-Hans", "name:zh", "name:zh-Hant"):
            v = t.get(key)
            if v:
                name_zh = v.strip()
                break

        is_metro = (
            t.get("station") in METRO_STATION
            or t.get("subway") == "yes"
            or "MTR" in (t.get("network") or "")
        )
        if is_metro:
            kind, priority = "metro", 0
        elif (t.get("train") == "yes" or t.get("uic_ref")
              or t.get("railway:ref") or t.get("importance")):
            kind, priority = "national_rail", 2
        else:
            kind, priority = "rail", 1

        aliases = []
        for key in ("alt_name", "old_name", "name:en"):
            v = t.get(key)
            if v:
                aliases.extend(x.strip() for x in re.split(r"[;|]", v) if x.strip())

        return {
            "name": raw,
            "name_zh": name_zh,
            "name_en": (t.get("name:en") or "").strip(),
            "ref": (t.get("railway:ref") or t.get("uic_ref") or "").strip(),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "kind": kind,
            "priority": priority,
            "aliases": aliases[:8],
        }


# ────────────────────────────────────────────────────────────
#  主流程
# ────────────────────────────────────────────────────────────

def find_pbf(arg):
    if arg:
        if not os.path.exists(arg):
            raise SystemExit(f"[错误] 文件不存在: {arg}")
        return arg
    cands = sorted(glob.glob(os.path.join(PBF_DIR, "*.osm.pbf")))
    if not cands:
        raise SystemExit(f"[错误] 未在 {PBF_DIR} 找到 *.osm.pbf")
    return max(cands, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser(description="从 OSM PBF 构建铁路参考数据")
    ap.add_argument("--pbf", default=None, help="PBF 路径（默认自动找最新）")
    ap.add_argument("--out", default=OUT_DIR, help="输出目录")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 条线路（调试）")
    args = ap.parse_args()

    path = find_pbf(args.pbf)
    hr("构建铁路参考数据")
    log(f"  输入: {path} ({os.path.getsize(path)/1024**3:.2f} GB)")
    log(f"  输出: {args.out}")

    os.makedirs(args.out, exist_ok=True)
    t_all = time.time()
    thread_pool = osmium.io.ThreadPool(8)

    # ── Pass 1 ──
    hr("Pass 1/2  收集带 name 的铁路 way")
    t0 = time.time()
    wc = WayCollector()
    wc.scan(path, thread_pool)
    log(f"  railway=rail way: {wc.raw_ways:,}")
    log(f"  其中带 name:      {wc.named_ways:,}")
    log(f"  唯一线路名:       {len(wc.lines):,}")
    log(f"  耗时: {time.time() - t0:.1f}s")

    # 过滤城市轨道
    dropped_metro = [n for n in wc.lines if any(h in n for h in METRO_NAME_HINTS)]
    for n in dropped_metro:
        del wc.lines[n]
    if dropped_metro:
        log(f"  剔除城市轨道线路名: {len(dropped_metro)}")

    if args.limit:
        names = sorted(wc.lines, key=lambda n: -len(wc.lines[n]))[: args.limit]
        wc.lines = {n: wc.lines[n] for n in names}
        log(f"  [debug] 限制为 {len(wc.lines)} 条线路")

    # ── Pass 2 ──
    hr("Pass 2/2  节点坐标与站点")
    needed = set()
    for wids in wc.lines.values():
        for wid in wids:
            refs = wc.way_refs.get(wid)
            if refs:
                needed.update(refs)
    log(f"  需要节点数: {len(needed):,}")

    t0 = time.time()
    nc = NodeCollector(thread_pool)
    nc.scan_nodes(path, needed)
    log(f"  节点坐标: {len(nc.coords):,}")
    nc.scan_stations(path)
    log(f"  站点 node: {nc.station_nodes:,}  有效: {len(nc.stations):,}")
    log(f"  耗时: {time.time() - t0:.1f}s")

    coords = nc.coords

    # ── 装配线路 ──
    hr("装配线路几何（单轨）")
    t0 = time.time()
    rail_lines = {}
    empty = 0
    total_pts = 0

    for name, wids in wc.lines.items():
        adj = build_graph(wids, wc.way_refs, coords)
        chain, km = assemble_line(adj, coords)
        if len(chain) < 2:
            empty += 1
            continue

        # 拼接后若仍有大跳变，切开成多个独立分段（都在同一线路名下）
        segments = split_at_big_gaps(chain, max_gap_km=50.0)
        if not segments:
            empty += 1
            continue

        pts = []
        seg_meta = []
        segment_start = None
        segment_end = None
        for seg_km, seg_pts in segments:
            ds = downsample(seg_pts)
            seg_meta.append({
                "km": round(seg_km, 1),
                "point_count": len(ds),
                "start": [round(seg_pts[0][0], 5), round(seg_pts[0][1], 5)],
                "end": [round(seg_pts[-1][0], 5), round(seg_pts[-1][1], 5)],
            })
            if segment_start is None:
                segment_start = seg_pts[0]
            segment_end = seg_pts[-1]
            pts.extend(ds)

        total_km = sum(k for k, _ in segments)
        tags = wc.line_tags.get(name, {})

        # 完整度评估：只在明显异常时提示，避免噪声（80% 线路是短支线，不该告警）
        warnings = []
        if len(seg_meta) > 3:
            warnings.append("多段拼接")
        # 主干线（>200km）若主段占比 <60%，说明被切得很碎、可能有缺段
        if total_km > 200 and seg_meta:
            main_ratio = seg_meta[0]["km"] / total_km
            if main_ratio < 0.6:
                warnings.append("主段占比低")
        # 主干线（>200km）单段但端点间直线距离远小于里程（绕行异常）
        if total_km > 200 and len(seg_meta) == 1:
            g0, g1 = segment_start, segment_end
            if g0 and g1:
                straight = haversine_km(g0, g1)
                if straight > 0 and total_km / straight > 2.5:
                    warnings.append("绕行比异常")

        rail_lines[name] = {
            "name": name,
            "ref": tags.get("ref", ""),
            "usage": tags.get("usage", ""),
            "operator": tags.get("operator", ""),
            "way_count": len(wids),
            "km": round(total_km, 1),
            "segment_count": len(seg_meta),
            "segments": seg_meta,
            "point_count": len(pts),
            "geometry": pts,
            "warnings": warnings,
        }
        total_pts += len(pts)

    log(f"  成功: {len(rail_lines):,}  为空: {empty}")
    log(f"  总点数: {total_pts:,}")
    log(f"  耗时: {time.time() - t0:.1f}s")

    # ── 站点 -> 线路 ──
    hr("建立站点 -> 线路索引")
    t0 = time.time()
    rail_stations = {sid: st for sid, st in nc.stations.items()
                     if st["kind"] != "metro"}

    line_grids = {n: make_grid(ln["geometry"]) for n, ln in rail_lines.items()}

    station_lines = defaultdict(list)
    for sid, st in rail_stations.items():
        pt = (st["lng"], st["lat"])
        for name, grid in line_grids.items():
            if near_any(pt, grid, STATION_SNAP_KM):
                station_lines[sid].append(name)

    log(f"  国铁站点: {len(rail_stations):,}")
    log(f"  有线路归属: {len(station_lines):,}"
        f" ({len(station_lines)/max(1,len(rail_stations)):.1%})")
    log(f"  耗时: {time.time() - t0:.1f}s")

    # ── 写盘 ──
    hr("写盘")
    meta = {
        "pbf": os.path.basename(path),
        "pbf_bytes": os.path.getsize(path),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "way_name_tags",
        "station_count": len(nc.stations),
        "line_count": len(rail_lines),
    }

    stations_out = {}
    for sid, st in nc.stations.items():
        stations_out[f"node/{sid}"] = {
            **{k: st[k] for k in ("name", "name_zh", "name_en", "ref",
                                  "lat", "lng", "kind", "priority", "aliases")},
            "lines": station_lines.get(sid, []),
        }

    p1 = os.path.join(args.out, "stations.json")
    with open(p1, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "stations": stations_out}, f, ensure_ascii=False)
    log(f"  {p1}  {os.path.getsize(p1)/1024/1024:.1f} MB  ({len(stations_out):,} 站)")

    p2 = os.path.join(args.out, "rail_lines.json")
    with open(p2, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "lines": rail_lines}, f, ensure_ascii=False)
    log(f"  {p2}  {os.path.getsize(p2)/1024/1024:.1f} MB  ({len(rail_lines):,} 线)")

    p3 = os.path.join(args.out, "station_line_index.json")
    index = {f"node/{sid}": names for sid, names in station_lines.items()}
    with open(p3, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    log(f"  {p3}  {os.path.getsize(p3)/1024/1024:.1f} MB")

    hr("完成")
    log(f"  总耗时: {(time.time() - t_all)/60:.1f} 分钟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
