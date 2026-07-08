"""
铁路路线图绘制服务

基于 OSM 真实轨道几何（非车站拉直线），按车次代码绘制列车运行路线。
路径搜索策略：
  1. per-line A*：在匹配线路的 way 图上找最短路径（只走该线路轨道）
  2. 全图 A*：per-line 失败时回退到全国铁路图（保证跨线中转等场景）
  3. 直线兜底：全图 A* 也失败时直线连接

区间匹配三级策略：
  Tier 1: line_graph.json 的 segments 字典直查（手工维护，100% 准确）
  Tier 2: line_stations 中搜两站是否在同一线路（评分：连续性+相邻性+数据量）
  Tier 3: 空间兜底，用车站坐标在线路 bbox 索引里找候选线路（距离评分）
"""
import sqlite3
import json
import struct
import os
import re as re_module
import math
import folium
import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from settings import settings as config_data


# ===================== 线路名称别名映射 =====================
# GPKG 中的线路名 vs line_graph.json 中的 key
LINE_NAME_ALIAS = {
    "京沪高速铁路": "京沪高铁", "京沪高铁": "京沪高铁", "京沪线": "京沪线",
    "京沪三线": "京沪三线", "京九线": "京九线", "京广线": "京广线",
    "京广高速铁路": "京广高铁", "京广高铁": "京广高铁",
    "京哈高速铁路": "京哈高铁", "京哈高铁": "京哈高铁",
    "京张高铁": "京张高铁", "京张高速铁路": "京张高铁",
    "沪昆高速铁路": "沪昆高铁", "沪昆高铁": "沪昆高铁", "沪昆线": "沪昆线",
    "陇海线": "陇海线", "陇海铁路": "陇海线",
    "徐兰高速铁路": "徐兰高铁", "徐兰高铁": "徐兰高铁",
    "郑徐高速铁路": "郑徐高铁", "郑徐高铁": "郑徐高铁",
    "京雄城际铁路": "京雄城际", "京雄城际": "京雄城际",
    "京津城际铁路": "京津城际线", "京津城际": "京津城际线",
    # GPKG 使用"高速线"后缀 → line_graph 使用"高铁"后缀
    "京哈高速线": "京哈高铁", "合福高速线": "合福高铁",
    "广深港高速线": "广深港高铁", "成渝高速线": "成渝高铁",
    "昌九城际线": "昌九城际", "沪宁城际线": "沪宁城际",
    "沪昆高速线": "沪昆高铁", "津秦高速线": "津秦高铁",
    "京广高速线": "京广高铁", "京港高速线": "京港高铁",
    "宁杭高速线": "宁杭高铁", "大西高速线": "大西高铁",
    "沈大高速线": "沈大高铁", "沈佳高速线": "沈佳高铁",
    "哈大高速线": "哈大高铁", "贵广高速线": "贵广高铁",
    "西成高速线": "西成高铁", "兰新高速线": "兰新高铁",
    "海南东环高速线": "海南东环", "海南西环高速线": "海南西环",
    # GPKG 与 line_graph 命名完全不同
    "徐兰高速线": "郑西高铁",
    "京包客专线": "京张高铁",
    "南广线": "南广高铁",
    "津霸线": "津保铁路", "津霸客专线": "津保铁路",
    "兰新客专线": "兰新高铁", "西成客专线": "西成高铁", "贵广客专线": "贵广高铁",
    "合蚌客专线": "合蚌客专", "石济客专线": "石济客专",
    "哈大高速铁路": "哈大高铁", "沪宁城际铁路": "沪宁城际",
}

# 车站名别名（修 timetable 数据笔误）
STATION_ALIAS = {
    "潢水": "衡水",
}

# OSM other_tags 中 name:zh 提取正则
_NAME_ZH_RE = re_module.compile(r'"name:zh"\s*=>\s*"([^"]+)"')


class RouteMapService:
    """铁路路线图绘制服务（基于 OSM 真实轨道几何）

    构造时加载 GPKG + line_graph.json + timetable，预构建 way 几何和 bbox 索引。
    复用单例可让 per-line 图缓存和全图 A* 缓存跨请求命中。
    """

    def __init__(self):
        self.gpkg_path = config_data.route_map_gpkg_path
        self.line_graph_path = config_data.route_map_line_graph_path
        self.timetable_path = config_data.route_map_timetable_path

        # 加载 line_graph
        with open(self.line_graph_path, "r", encoding="utf-8") as f:
            self.line_graph = json.load(f)
        self.line_graph_ls = self.line_graph.get("line_stations", {})

        # 加载 timetable
        with open(self.timetable_path, "r", encoding="utf-8") as f:
            self.timetable = json.load(f)

        # 构建车站坐标
        self.st_coords = self._build_station_coords_map()

        # 加载 way 几何
        self.way_geoms = self._load_line_way_geometries()

        # 构建线路 bbox 索引（用于 Tier 3 空间兜底）
        self.line_bbox = {}
        for ln, ways in self.way_geoms.items():
            lons, lats = [], []
            for way in ways:
                for lon, lat in way:
                    lons.append(lon)
                    lats.append(lat)
            if lons:
                self.line_bbox[ln] = (min(lons), min(lats), max(lons), max(lats))

        # 预收集 line_graph 已知站名（用于站名归一化）
        self._known_stations = set()
        for sts in self.line_graph_ls.values():
            self._known_stations.update(sts)
        for seg_key in self.line_graph.get("segments", {}):
            a, b = seg_key.split("_", 1)
            self._known_stations.add(a)
            self._known_stations.add(b)

        # 预计算线路 way 数量（用于 Tier 2 评分）
        self._line_way_counts = {}
        try:
            conn = sqlite3.connect(self.gpkg_path)
            cur = conn.cursor()
            cur.execute("SELECT name, COUNT(*) FROM lines WHERE railway='rail' GROUP BY name")
            for nm, cnt in cur.fetchall():
                if nm:
                    self._line_way_counts[nm] = cnt
            conn.close()
        except Exception:
            pass

        # 缓存
        self._line_graph_cache = {}  # {line_name: (graph, kdtree, nodes)}
        self._global_graph = None
        self._global_kdtree = None
        self._global_nodes = None

        print(f"  [RouteMapService] 初始化完成: {len(self.st_coords)} 车站, "
              f"{len(self.way_geoms)} 线路, {len(self.timetable)} 车次")

    # ===================== 工具函数 =====================

    @staticmethod
    def _haversine_meters(lon1, lat1, lon2, lat2):
        """计算两点间球面距离（米）"""
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _densify_coords(coords, max_step=0.005):
        """加密坐标点：相邻点距离超过 max_step（度）时线性插值"""
        if not coords:
            return []
        result = [coords[0]]
        for i in range(1, len(coords)):
            lon1, lat1 = coords[i - 1]
            lon2, lat2 = coords[i]
            d = ((lon2 - lon1) ** 2 + (lat2 - lat1) ** 2) ** 0.5
            if d > max_step:
                n = int(math.ceil(d / max_step))
                for j in range(1, n + 1):
                    t = j / n
                    result.append((lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t))
            else:
                result.append((coords[i][0], coords[i][1]))
        return result

    @staticmethod
    def _thin_path(path, max_points=3000):
        """抽稀路径：保留形状的前提下减少点数"""
        n = len(path)
        if n <= max_points:
            return path
        step = math.ceil(n / max_points)
        thinned = path[::step]
        if thinned[-1] != path[-1]:
            thinned.append(path[-1])
        return thinned

    @staticmethod
    def _parse_wkb(blob):
        """解析 GPKG WKB 二进制几何数据，返回坐标列表 [(lon,lat), ...]"""
        if not blob or len(blob) < 9:
            return []
        offset = 0
        magic = blob[offset:offset + 2]
        offset += 2
        if magic == b'GP':
            offset += 6
            for try_offset in [offset, offset + 32, offset + 48, offset + 64]:
                if try_offset >= len(blob):
                    continue
                wkb_data = blob[try_offset:]
                if len(wkb_data) < 5:
                    continue
                if wkb_data[0] in (0, 1):
                    endian_check = '<' if wkb_data[0] == 1 else '>'
                    try:
                        gtype = struct.unpack_from(endian_check + 'I', wkb_data, 1)[0]
                        base = gtype % 1000
                        if base in (1, 2, 5):
                            offset = try_offset
                            break
                    except Exception:
                        continue
        else:
            offset = 0

        wkb_data = blob[offset:]
        endian = '<' if wkb_data[0] == 1 else '>'
        geom_type = struct.unpack_from(endian + 'I', wkb_data, 1)[0]
        has_z = bool((1000 <= geom_type < 2000) or (3000 <= geom_type < 4000))
        if geom_type >= 3000:
            base_type = geom_type - 3000
        elif geom_type >= 2000:
            base_type = geom_type - 2000
        elif geom_type >= 1000:
            base_type = geom_type - 1000
        else:
            base_type = geom_type
        coord_size = 3 if has_z else 2

        if base_type == 1:
            x, y = struct.unpack_from(endian + 'dd', wkb_data, 5)
            return [(x, y)]
        elif base_type in (2, 5):
            coords = []
            if base_type == 2:
                count = struct.unpack_from(endian + 'I', wkb_data, 5)[0]
                pos = 9
                for _ in range(count):
                    vals = struct.unpack_from(endian + 'd' * coord_size, wkb_data, pos)
                    coords.append((vals[0], vals[1]))
                    pos += 8 * coord_size
            else:
                count = struct.unpack_from(endian + 'I', wkb_data, 5)[0]
                pos = 9
                for _ in range(count):
                    sub_endian = '<' if wkb_data[pos] == 1 else '>'
                    sub_count = struct.unpack_from(sub_endian + 'I', wkb_data, pos + 5)[0]
                    pos2 = pos + 9
                    for _ in range(sub_count):
                        vals = struct.unpack_from(sub_endian + 'd' * coord_size, wkb_data, pos2)
                        coords.append((vals[0], vals[1]))
                        pos2 += 8 * coord_size
                    pos = pos2
            return coords
        return []

    # ===================== 数据加载 =====================

    def _build_station_coords_map(self):
        """从 GPKG 提取车站坐标（railway=station/halt 的点）"""
        conn = sqlite3.connect(self.gpkg_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, other_tags, geom FROM [china_railway_filteredosm__points] "
            "WHERE other_tags IS NOT NULL AND other_tags LIKE '%railway%'"
        )
        raw_stations = {}
        for name, tags_str, geom_blob in cur.fetchall():
            if not name:
                continue
            tags = {}
            if tags_str:
                for m in re_module.finditer(r'"([^"]+)"\s*=>\s*"([^"]*)"', tags_str):
                    tags[m.group(1)] = m.group(2)
            if tags.get("railway") not in ("station", "halt"):
                continue
            coords = self._parse_wkb(geom_blob)
            if coords:
                raw_stations[name] = coords[0]
        conn.close()

        # 别名映射：去"站"字 + 手动补充常见简称
        alias = {}
        for os_name, coord in raw_stations.items():
            alias[os_name] = coord
            if os_name.endswith("站"):
                alias[os_name[:-1]] = coord
        manual = {
            "北京南": "北京南站", "北京西": "北京西站", "北京": "北京站",
            "北京丰台": "北京丰台站", "天津": "天津站", "天津西": "天津西站",
            "天津南": "天津南站", "石家庄": "石家庄站", "郑州": "郑州站",
            "郑州东": "郑州东站", "济南": "济南站", "济南西": "济南西站",
            "徐州": "徐州站", "徐州东": "徐州东站", "南京": "南京站",
            "南京南": "南京南站", "上海": "上海站", "上海虹桥": "上海虹桥站",
            "上海南": "上海南站", "杭州": "杭州站", "杭州东": "杭州东站",
            "武汉": "武汉站", "武昌": "武昌站", "汉口": "汉口站",
            "广州": "广州站", "广州南": "广州南站", "广州东": "广州东站",
            "深圳": "深圳站", "深圳北": "深圳北站", "长沙": "长沙站",
            "长沙南": "长沙南站", "南昌": "南昌站", "南昌西": "南昌西站",
            "合肥": "合肥站", "合肥南": "合肥南站", "西安": "西安站",
            "西安北": "西安北站", "成都": "成都站", "成都东": "成都东站",
            "重庆北": "重庆北站", "重庆西": "重庆西站", "兰州": "兰州站",
            "兰州西": "兰州西站", "沈阳": "沈阳站", "沈阳北": "沈阳北站",
            "长春": "长春站", "长春西": "长春西站", "哈尔滨": "哈尔滨站",
            "哈尔滨西": "哈尔滨西站", "贵阳": "贵阳站", "贵阳北": "贵阳北站",
            "昆明": "昆明站", "昆明南": "昆明南站", "南宁": "南宁站",
            "南宁东": "南宁东站", "福州": "福州站", "福州南": "福州南站",
            "厦门": "厦门站", "厦门北": "厦门北站", "青岛": "青岛站",
            "青岛北": "青岛北站", "大连": "大连站", "大连北": "大连北站",
            "廊坊": "廊坊站", "沧州西": "沧州西站", "德州东": "德州东站",
            "泰安": "泰安站", "曲阜东": "曲阜东站", "宿州东": "宿州东站",
            "蚌埠南": "蚌埠南站", "定远": "定远站", "滁州": "滁州站",
            "镇江南": "镇江南站", "常州北": "常州北站", "无锡东": "无锡东站",
            "苏州北": "苏州北站", "昆山南": "昆山南站",
        }
        for short, os_name in manual.items():
            if short not in alias and os_name in raw_stations:
                alias[short] = raw_stations[os_name]

        print(f"  [RouteMapService] 提取了 {len(alias)} 个车站坐标")
        return alias

    def _load_line_way_geometries(self):
        """从 GPKG 加载每条铁路线的原始 way 几何，按线路名分组"""
        conn = sqlite3.connect(self.gpkg_path)
        cur = conn.cursor()
        cur.execute("SELECT name, other_tags, geom FROM lines WHERE railway = 'rail'")
        rows = cur.fetchall()
        conn.close()

        way_geoms = {}
        for name, other_tags, geom_blob in rows:
            line_name = name
            if not line_name and other_tags:
                m = _NAME_ZH_RE.search(other_tags)
                if m:
                    line_name = m.group(1)
            if not line_name:
                continue
            norm_name = LINE_NAME_ALIAS.get(line_name, line_name)
            coords = self._parse_wkb(geom_blob)
            if not coords or len(coords) < 2:
                continue
            if norm_name not in way_geoms:
                way_geoms[norm_name] = []
            way_geoms[norm_name].append(coords)

        total_ways = sum(len(v) for v in way_geoms.values())
        print(f"  [RouteMapService] 从 GPKG 加载了 {len(way_geoms)} 条线路的 {total_ways} 条 OSM way 几何")
        return way_geoms

    # ===================== Per-line 图构建（按线路名隔离的 A* 搜索）=====================

    def _get_line_graph(self, line_name):
        """为指定线路构建 NetworkX 图（懒加载缓存）"""
        if line_name in self._line_graph_cache:
            return self._line_graph_cache[line_name]

        ways = self.way_geoms.get(line_name, [])
        if not ways:
            self._line_graph_cache[line_name] = (None, None, None)
            return None, None, None

        G = nx.Graph()
        endpoints = []
        for way in ways:
            if len(way) < 2:
                continue
            for i in range(len(way) - 1):
                u, v = way[i], way[i + 1]
                dist = self._haversine_meters(u[0], u[1], v[0], v[1])
                if dist > 0:
                    if not G.has_edge(u, v) or dist < G[u][v]['weight']:
                        G.add_edge(u, v, weight=dist)
            endpoints.append(way[0])
            endpoints.append(way[-1])

        # 断段桥接：端点距离 < 0.01°（约 1.1km）的视为同一物理断点
        BRIDGE_THRESHOLD_DEG = 0.01
        if len(endpoints) >= 2:
            ep_arr = np.array(endpoints)
            ep_tree = cKDTree(ep_arr)
            pairs = ep_tree.query_pairs(r=BRIDGE_THRESHOLD_DEG, output_type='ndarray')
            for i, j in pairs:
                u = tuple(ep_arr[i])
                v = tuple(ep_arr[j])
                if u == v or u not in G or v not in G:
                    continue
                dist = self._haversine_meters(u[0], u[1], v[0], v[1])
                if not G.has_edge(u, v):
                    G.add_edge(u, v, weight=dist)
                elif dist < G[u][v]['weight']:
                    G[u][v]['weight'] = dist

        nodes = list(G.nodes)
        if not nodes:
            self._line_graph_cache[line_name] = (None, None, None)
            return None, None, None

        tree = cKDTree(np.array(nodes))
        self._line_graph_cache[line_name] = (G, tree, nodes)
        return G, tree, nodes

    def _find_path_on_line(self, line_name, coord1, coord2):
        """在指定线路的 way 图上用 A* 查找最短路径"""
        line_name = LINE_NAME_ALIAS.get(line_name, line_name)
        G, tree, nodes = self._get_line_graph(line_name)
        if G is None:
            return None

        _, idx1 = tree.query([coord1[0], coord1[1]])
        _, idx2 = tree.query([coord2[0], coord2[1]])
        node1 = tuple(nodes[idx1])
        node2 = tuple(nodes[idx2])

        if node1 == node2:
            return [node1]

        def heuristic(u, v):
            return self._haversine_meters(u[0], u[1], v[0], v[1])

        try:
            return nx.astar_path(G, node1, node2, heuristic=heuristic, weight='weight')
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # ===================== 全图 A*（兜底）=====================

    def _get_railway_graph(self):
        """从 GPKG 构建全国铁路 NetworkX 图（懒加载缓存）

        注意：OSM 中国铁路大量线路的 name 字段为空，中文线路名存放在
        other_tags 的 name:zh 子键里。这里和 _load_line_way_geometries 一样，
        对 name 为空的 way 从 other_tags 提取 name:zh，确保全图 A* 兜底时不丢线路。
        """
        if self._global_graph is not None:
            return self._global_graph, self._global_kdtree, self._global_nodes

        conn = sqlite3.connect(self.gpkg_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, other_tags, geom FROM lines WHERE railway = 'rail'"
        )
        rows = cur.fetchall()
        conn.close()

        G = nx.Graph()
        skipped_empty_name = 0
        for name, other_tags, geom_blob in rows:
            if not name or not name.strip():
                if other_tags:
                    m = _NAME_ZH_RE.search(other_tags)
                    if m:
                        name = m.group(1)
                if not name:
                    skipped_empty_name += 1
                    continue
            coords = self._parse_wkb(geom_blob)
            if not coords or len(coords) < 2:
                continue
            for i in range(len(coords) - 1):
                u = coords[i]
                v = coords[i + 1]
                dist = self._haversine_meters(u[0], u[1], v[0], v[1])
                if dist > 0:
                    if not G.has_edge(u, v) or dist < G[u][v]['weight']:
                        G.add_edge(u, v, weight=dist)

        nodes = list(G.nodes)
        tree = cKDTree(np.array(nodes))
        self._global_graph = G
        self._global_kdtree = tree
        self._global_nodes = nodes
        print(f"  [RouteMapService] 全图: {len(nodes)} 节点, {G.number_of_edges()} 边"
              + (f"（跳过 {skipped_empty_name} 条无名称线路）" if skipped_empty_name else ""))
        return G, tree, nodes

    def _find_path_astar(self, coord1, coord2):
        """在铁路图上用 A* 查找两坐标点间的最短铁路路径"""
        G, tree, nodes = self._get_railway_graph()
        _, idx1 = tree.query([coord1[0], coord1[1]])
        _, idx2 = tree.query([coord2[0], coord2[1]])
        node1 = tuple(nodes[idx1])
        node2 = tuple(nodes[idx2])

        if node1 == node2:
            return [node1]

        def heuristic(u, v):
            return self._haversine_meters(u[0], u[1], v[0], v[1])

        # 子图加速：用 bbox + cKDTree 圈定搜索范围
        margin = 0.5
        min_lon = min(coord1[0], coord2[0]) - margin
        max_lon = max(coord1[0], coord2[0]) + margin
        min_lat = min(coord1[1], coord2[1]) - margin
        max_lat = max(coord1[1], coord2[1]) + margin
        center = [(min_lon + max_lon) / 2, (min_lat + max_lat) / 2]
        radius = math.sqrt((max_lon - min_lon) ** 2 + (max_lat - min_lat) ** 2) / 2
        indices = tree.query_ball_point(center, radius)
        sub_nodes = [nodes[i] for i in indices]
        if node1 not in sub_nodes:
            sub_nodes.append(node1)
        if node2 not in sub_nodes:
            sub_nodes.append(node2)
        sub_g = G.subgraph(sub_nodes)

        try:
            return nx.astar_path(sub_g, node1, node2, heuristic=heuristic, weight='weight')
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            try:
                return nx.astar_path(G, node1, node2, heuristic=heuristic, weight='weight')
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return [node1, node2]  # 直线兜底

    # ===================== 站名归一化 =====================

    def _normalize_station(self, s):
        """把 timetable 站名归一化到 line_graph 已知站名。
        只处理"同站不同名"（距离<3km），不会把不同站强行关联。"""
        if s in self._known_stations:
            return s
        if s in STATION_ALIAS:
            return STATION_ALIAS[s]
        sc = self.st_coords.get(s)
        if not sc:
            return s
        best_name, best_dist = None, float('inf')
        for ks in self._known_stations:
            kc = self.st_coords.get(ks)
            if kc:
                d = self._haversine_meters(sc[0], sc[1], kc[0], kc[1])
                if d < best_dist:
                    best_dist = d
                    best_name = ks
        if best_name and best_dist < 3000:  # 3km 阈值
            return best_name
        return s

    # ===================== 区间匹配（Tier 1/2/3）=====================

    def _match_train_segments(self, train_stations):
        """匹配列车经过的线路段，返回 [(seg_key, line_name), ...]"""
        n = len(train_stations)
        if n < 2:
            return []
        segments_data = self.line_graph.get("segments", {})
        line_stations_data = self.line_graph.get("line_stations", {})
        result = []

        for i in range(n - 1):
            s1, s2 = train_stations[i], train_stations[i + 1]
            key = f"{s1}_{s2}"

            # --- Tier 1: segment 映射 ---
            candidates = segments_data.get(key, []) or segments_data.get(f"{s2}_{s1}", [])
            if candidates:
                if len(candidates) == 1:
                    result.append((key, candidates[0]))
                else:
                    prev_line = result[-1][1] if result else None
                    if prev_line in candidates:
                        result.append((key, prev_line))
                        continue
                    best_line, best_score = None, -1
                    for ln in candidates:
                        score = 1
                        j = i + 1
                        while j < n - 1:
                            nk = f"{train_stations[j]}_{train_stations[j + 1]}"
                            nc = segments_data.get(nk, []) or segments_data.get(
                                f"{train_stations[j + 1]}_{train_stations[j]}", [])
                            if ln in nc:
                                score += 1
                                j += 1
                            else:
                                break
                        if score > best_score:
                            best_score = score
                            best_line = ln
                    result.append((key, best_line))
                continue

            # --- Tier 2: 在 line_stations 中搜索 ---
            matched = None
            scored_lines = []
            prev_line = result[-1][1] if result else None
            for ln, sts in line_stations_data.items():
                if len(sts) < 2:
                    continue
                try:
                    i1, i2 = sts.index(s1), sts.index(s2)
                except ValueError:
                    continue
                idx_gap = abs(i2 - i1)
                score = 0
                if ln == prev_line:
                    score += 100
                if idx_gap == 1:
                    score += 50
                else:
                    score += max(0, 50 - idx_gap * 5)
                way_cnt = self._line_way_counts.get(ln, 0)
                score += min(20, way_cnt / 50)
                scored_lines.append((score, ln))
            if scored_lines:
                scored_lines.sort(key=lambda x: -x[0])
                matched = scored_lines[0][1]

            # --- Tier 3: 空间兜底（用车站坐标找 OSM way 所属线路）---
            if not matched:
                sc1 = self.st_coords.get(s1)
                sc2 = self.st_coords.get(s2)
                if sc1 and sc2:
                    margin = 0.3
                    s1_lines, s2_lines = set(), set()
                    for ln, (mn_lon, mn_lat, mx_lon, mx_lat) in self.line_bbox.items():
                        if (mn_lon - margin <= sc1[0] <= mx_lon + margin and
                                mn_lat - margin <= sc1[1] <= mx_lat + margin):
                            s1_lines.add(ln)
                        if (mn_lon - margin <= sc2[0] <= mx_lon + margin and
                                mn_lat - margin <= sc2[1] <= mx_lat + margin):
                            s2_lines.add(ln)
                    common = s1_lines & s2_lines
                    if common:
                        prev_line = result[-1][1] if result else None
                        best_line, best_score = None, -1e18
                        for ln in common:
                            G_ln, tree_ln, nodes_ln = self._get_line_graph(ln)
                            if G_ln is None or tree_ln is None:
                                continue
                            _, idx1 = tree_ln.query([sc1[0], sc1[1]])
                            _, idx2 = tree_ln.query([sc2[0], sc2[1]])
                            n1 = nodes_ln[idx1]
                            n2 = nodes_ln[idx2]
                            d1_m = self._haversine_meters(sc1[0], sc1[1], n1[0], n1[1])
                            d2_m = self._haversine_meters(sc2[0], sc2[1], n2[0], n2[1])
                            max_d_km = max(d1_m, d2_m) / 1000.0
                            score = 0
                            if ln == prev_line:
                                score += 100
                            score -= max_d_km
                            if score > best_score:
                                best_score = score
                                best_line = ln
                        if best_line is None:
                            best_line = max(common, key=lambda ln: len(self.way_geoms.get(ln, [])))
                        matched = best_line

            result.append((key, matched))
        return result

    # ===================== 绘图 =====================

    def _draw_train_route(self, train_code, stations, seg_matches, output_path):
        """在地图上绘制某趟列车的运行路线"""
        # 线路颜色映射
        line_names_used = sorted(set(ln for _, ln in seg_matches if ln))
        colors = [
            "#E60012", "#0066CC", "#00AA00", "#FF8800", "#8800FF",
            "#00AAAA", "#CC0066", "#AAAA00", "#FF4488", "#4488FF",
        ]
        line_color_map = {ln: colors[i % len(colors)] for i, ln in enumerate(line_names_used)}

        # 地图中心
        plot_coords = [self.st_coords[st] for st in stations if st in self.st_coords]
        if not plot_coords:
            print("  [RouteMapService] 没有车站坐标数据")
            return None
        center_lat = sum(lat for _, lat in plot_coords) / len(plot_coords)
        center_lon = sum(lon for lon, _ in plot_coords) / len(plot_coords)

        m = folium.Map(
            location=[center_lat, center_lon], zoom_start=5,
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr="OpenStreetMap", control_scale=True,
        )
        fg_route = folium.FeatureGroup(name="列车运行路线")
        fg_stations = folium.FeatureGroup(name="车站")

        # 对每个区间：per-line A* 优先，全图 A* 兜底
        for seg_key, line_name in seg_matches:
            s1, s2 = seg_key.split("_", 1)
            sc1 = self.st_coords.get(s1)
            sc2 = self.st_coords.get(s2)
            if not sc1 or not sc2:
                continue

            path = None
            source = ""

            # per-line A*
            ln_norm = LINE_NAME_ALIAS.get(line_name, line_name) if line_name else None
            if ln_norm and ln_norm in self.way_geoms:
                path = self._find_path_on_line(ln_norm, sc1, sc2)
                if path and len(path) >= 2:
                    source = f"per-line({ln_norm})"

            # 全图 A* 兜底
            if not path or len(path) < 2:
                path = self._find_path_astar(sc1, sc2)
                if path and len(path) >= 2:
                    source = f"全图A*({ln_norm or line_name or '未匹配'})"
                    print(f"  [RouteMapService] {seg_key}：退化 {source}")

            if not path or len(path) < 2:
                continue

            path = self._thin_path(path, max_points=3000)
            path = self._densify_coords(path)

            color = line_color_map.get(line_name, "#888888")
            label = line_name or "未匹配线路"
            folium_coords = [[lat, lon] for lon, lat in path]
            folium.PolyLine(
                folium_coords, color=color, weight=4, opacity=0.75,
                smoothFactor=0, noClip=True,
                popup=f"{label} [{source}]", tooltip=label,
            ).add_to(fg_route)

        # 车站标记
        for idx, st_name in enumerate(stations):
            coord = self.st_coords.get(st_name)
            if not coord:
                continue
            st_lon, st_lat = coord
            st_lines = []
            for seg_key, line_name in seg_matches:
                if line_name and (seg_key.startswith(st_name + "_") or seg_key.endswith("_" + st_name)):
                    if line_name not in st_lines:
                        st_lines.append(line_name)
            folium.CircleMarker(
                location=[st_lat, st_lon], radius=8, color="red",
                fill=True, fill_color="red", fill_opacity=0.9,
                popup=f"<b>{idx+1}. {st_name}</b><br>{', '.join(st_lines)}",
                tooltip=f"{idx+1}. {st_name}",
            ).add_to(fg_stations)
            folium.map.Marker(
                location=[st_lat, st_lon],
                icon=folium.DivIcon(
                    html=f'<div style="font-size:11pt;color:#333;font-weight:bold;'
                         f'text-shadow:1px 1px 2px white;white-space:nowrap;">'
                         f'{idx+1}. {st_name}</div>',
                    icon_size=(150, 20), icon_anchor=(0, 10),
                ),
            ).add_to(fg_stations)

        # 信息面板
        matched = sum(1 for _, l in seg_matches if l)
        total = len(seg_matches)
        info_html = f"""
        <div style="position:fixed;top:10px;right:10px;z-index:9999;
                    background:white;padding:10px;border-radius:5px;
                    box-shadow:0 0 10px rgba(0,0,0,0.3);font-size:13px;
                    max-width:300px;">
            <b>{train_code}</b><br>
            {stations[0]} → {stations[-1]}<br>
            共 {len(stations)} 站 {total} 区间 | 线路匹配 {matched}/{total}<br>
            线路: {", ".join(line_names_used) if line_names_used else "无"}
        </div>
        """
        m.get_root().html.add_child(folium.Element(info_html))

        # 自动适配视野
        all_coords = []
        for st in stations:
            if st in self.st_coords:
                lon, lat = self.st_coords[st]
                all_coords.append([lat, lon])
        if len(all_coords) >= 2:
            m.fit_bounds(
                [[min(lat for lat, _ in all_coords), min(lon for _, lon in all_coords)],
                 [max(lat for lat, _ in all_coords), max(lon for _, lon in all_coords)]]
            )

        fg_route.add_to(m)
        fg_stations.add_to(m)
        folium.LayerControl().add_to(m)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        m.save(output_path)
        print(f"  [RouteMapService] 已保存到 {output_path}")
        return output_path

    # ===================== 公开接口 =====================

    def draw_train_route(self, train_code, output_dir=None):
        """绘制指定车次的运行路线图

        参数:
            train_code: 车次号（如 "G1", "K4174", "Z227"）
            output_dir: 输出目录（默认用 settings.maps_output_dir）
        返回:
            (filepath, stations) 或 (None, None)
        """
        if train_code not in self.timetable:
            print(f"  [RouteMapService] 车次 {train_code} 不在 timetable 中")
            return None, None

        train = self.timetable[train_code]
        stations = [self._normalize_station(s["station_name"]) for s in train]
        segs = self._match_train_segments(stations)

        if output_dir is None:
            output_dir = config_data.maps_output_dir
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, f"route_{train_code}.html")
        result = self._draw_train_route(train_code, stations, segs, output_path)
        if result:
            return result, stations
        return None, None

    def find_trains_by_station(self, station_name):
        """查找经过指定车站的所有车次（用于按站查询场景）

        参数:
            station_name: 站名（会自动归一化）
        返回:
            [(train_code, station_list), ...]
        """
        norm = self._normalize_station(station_name)
        results = []
        for code, train in self.timetable.items():
            stations = [self._normalize_station(s["station_name"]) for s in train]
            if norm in stations:
                results.append((code, stations))
        return results

    def find_trains_between_stations(self, start_station, end_station):
        """查找从 start_station 到 end_station 的所有车次（精确站点匹配，按发车时间排序）

        参数:
            start_station: 起点站名（会自动归一化）
            end_station: 终点站名（会自动归一化）
        返回:
            [(train_code, departure_time, start_station, end_station, station_list), ...]
            departure_time 为起点站的发车时间（"HH:MM" 格式），按时间从早到晚排序
        """
        norm_start = self._normalize_station(start_station)
        norm_end = self._normalize_station(end_station)

        results = []
        for code, train in self.timetable.items():
            stations = [self._normalize_station(s["station_name"]) for s in train]
            try:
                idx_start = stations.index(norm_start)
                idx_end = stations.index(norm_end)
            except ValueError:
                continue
            # 顺序匹配：起点必须在终点之前
            if idx_start < idx_end:
                # 起点站的发车时间
                dep_time = train[idx_start].get("start_time", "") or ""
                # 始发站可能 start_time 为空，用 arrive_time 兜底
                if not dep_time or dep_time == "----":
                    dep_time = train[idx_start].get("arrive_time", "") or ""
                results.append((code, dep_time, norm_start, norm_end, stations))

        # 按发车时间从早到晚排序（"HH:MM" 字符串可直接排序）
        results.sort(key=lambda x: x[1])
        return results
