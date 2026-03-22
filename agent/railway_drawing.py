import pickle
import json
import os
import time
import folium
import networkx as nx
from geopy.distance import geodesic
import config_data


class RailwayDrawingService:
    def __init__(self):
        self.city_to_node_path = config_data.city_to_node_path
        self.train_data_path = config_data.train_data_path
        self.railway_graph_path = config_data.railway_geojson_path
        stations_json_path = os.path.join(os.path.dirname(self.train_data_path), "stations.json")

        with open(self.city_to_node_path, "rb") as f:
            raw_city_to_node = pickle.load(f)

        self.city_to_node = {}
        for raw_name, coord in raw_city_to_node.items():
            norm_name = self.normalize_station_name(raw_name)
            if norm_name not in self.city_to_node:
                self.city_to_node[norm_name] = coord

        with open(self.train_data_path, "r", encoding="utf-8") as f:
            self.trains_data = json.load(f)

        self.trains = []
        self.station_to_trains = {}
        self.station_popularity = {}
        self.norm_to_raw_names = {}

        for item in self.trains_data:
            stations_dict = item.get("stations", {})
            sorted_items = sorted(stations_dict.items(), key=lambda x: int(x[0]))
            station_list_raw = [s[1] for s in sorted_items]
            station_list_norm = [self.normalize_station_name(s) for s in station_list_raw]

            train_obj = {
                "name": item.get("name"),
                "class": item.get("class"),
                "station_count": item.get("station_count", len(station_list_norm)),
                "station_list_raw": station_list_raw,
                "station_list_norm": station_list_norm
            }
            self.trains.append(train_obj)

            for norm_name, raw_name in zip(station_list_norm, station_list_raw):
                if norm_name not in self.station_to_trains:
                    self.station_to_trains[norm_name] = []
                if norm_name not in self.norm_to_raw_names:
                    self.norm_to_raw_names[norm_name] = []
                if raw_name not in self.norm_to_raw_names[norm_name]:
                    self.norm_to_raw_names[norm_name].append(raw_name)
                if train_obj not in self.station_to_trains[norm_name]:
                    self.station_to_trains[norm_name].append(train_obj)
                if raw_name not in self.station_popularity:
                    self.station_popularity[raw_name] = 0
                self.station_popularity[raw_name] += 1

        with open(self.railway_graph_path, "rb") as f:
            self.railway_graph = pickle.load(f)
        self._path_cache = {}

        # 城市 -> 站点映射表（来自 stations.json），用于模糊/兜底匹配
        self.city_to_stations = {}
        if os.path.exists(stations_json_path):
            try:
                with open(stations_json_path, "r", encoding="utf-8") as f:
                    stations_payload = json.load(f)
                for item in stations_payload.get("cities", []):
                    city_raw = item.get("city_name", "")
                    city_norm = self.normalize_city_name(city_raw)
                    station_list = item.get("stations", [])
                    if city_norm and station_list:
                        self.city_to_stations[city_norm] = station_list
            except Exception:
                # 如果读取失败，不影响主流程，只是无法做城市兜底
                self.city_to_stations = {}

    @staticmethod
    def _heuristic(u, v):
        # A* 启发式：使用大地距离（米）作为下界
        return geodesic((u[1], u[0]), (v[1], v[0])).meters

    def _subgraph_for_pair(self, u, v, margin=1.0):
        # 按经纬度包围盒裁剪子图，减少最短路搜索规模
        min_lng = min(u[0], v[0]) - margin
        max_lng = max(u[0], v[0]) + margin
        min_lat = min(u[1], v[1]) - margin
        max_lat = max(u[1], v[1]) + margin
        nodes = [n for n in self.railway_graph
                 if min_lng <= n[0] <= max_lng and min_lat <= n[1] <= max_lat]
        return self.railway_graph.subgraph(nodes)

    @staticmethod
    def normalize_station_name(name):
        if not isinstance(name, str):
            return name
        if name.endswith('站'):
            name = name[:-1]
        if name.endswith('火车站'):
            name = name[:-3]
        return name

    @staticmethod
    def normalize_city_name(name):
        if not isinstance(name, str):
            return name
        name = name.strip()
        for suffix in ["市", "地区", "自治州", "州", "盟"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
                break
        return name

    def find_trains_between(self, start, end):
        """
        精确匹配起点和终点，返回 (trains_info, actual_start, actual_end)
        如果未找到，返回 ([], None, None)
        """
        start_candidates = self._get_candidate_stations(start)
        end_candidates = self._get_candidate_stations(end)

        best_combo = None  # (result, actual_start, actual_end)
        best_score = None

        for s_raw in start_candidates:
            for e_raw in end_candidates:
                result = self._find_trains_internal(s_raw, e_raw)
                if not result:
                    continue
                first_len = result[0][0].get("station_count", len(result[0][0].get("station_list_norm", [])))
                score = first_len
                if best_score is None or score < best_score:
                    best_score = score
                    best_combo = (result, s_raw, e_raw)

        if best_combo:
            result, actual_start, actual_end = best_combo
            if len(result) > 3:
                result = result[:3]
            return result, actual_start, actual_end

        return [], None, None

    def _get_candidate_stations(self, name):
        """
        返回可能的站点原始名称列表：先精确匹配站名，再按城市映射兜底。
        排序优先使用出现频率高的站点，避免随机性。
        """
        norm_name = self.normalize_station_name(name)
        candidates = []

        # 1) 直接匹配站名
        if norm_name in self.norm_to_raw_names:
            candidates.extend(self.norm_to_raw_names[norm_name])

        # 2) 使用城市映射兜底
        city_key = self.normalize_city_name(name)
        city_candidates = []
        if city_key in self.city_to_stations:
            city_candidates = self.city_to_stations[city_key]
        else:
            # 兼容部分输入：若用户输入城市简称，尝试模糊包含
            for ck, st_list in self.city_to_stations.items():
                if city_key and (city_key in ck or ck in city_key):
                    city_candidates = st_list
                    break

        for raw_st in city_candidates:
            norm_st = self.normalize_station_name(raw_st)
            if norm_st in self.station_to_trains:
                candidates.append(raw_st)

        # 去重并按站点热度排序（出现次数多的优先）
        seen = set()
        unique_candidates = []
        for raw_st in candidates:
            if raw_st in seen:
                continue
            seen.add(raw_st)
            unique_candidates.append(raw_st)

        unique_candidates.sort(key=lambda x: -self.station_popularity.get(x, 0))
        return unique_candidates or [name]

    def _find_trains_internal(self, start, end):
        norm_start = self.normalize_station_name(start)
        norm_end = self.normalize_station_name(end)

        if norm_start not in self.station_to_trains or norm_end not in self.station_to_trains:
            return []
        start_trains = self.station_to_trains[norm_start]
        end_trains = self.station_to_trains[norm_end]
        common_trains = [t for t in start_trains if t in end_trains]

        result = []
        for train in common_trains:
            stations_norm = train["station_list_norm"]
            try:
                i_start = stations_norm.index(norm_start)
                i_end = stations_norm.index(norm_end)
                if i_start < i_end:
                    sub_stations_raw = train["station_list_raw"][i_start:i_end + 1]
                    result.append((train, sub_stations_raw))
            except ValueError:
                continue

        result.sort(key=lambda x: x[0]["station_count"])
        return result

    # ==================== HTML构建方法（简洁版）====================

    def _build_sidebar_html(self, trains_info, station_coords):
        """构建侧边栏HTML"""
        html = """
        <div id="train-sidebar" style="position: fixed; top: 10px; right: 10px; width: 300px; max-height: 90%; overflow-y: auto; background: white; border-radius: 8px; padding: 15px; box-shadow: 0 0 20px rgba(0,0,0,0.3); z-index: 1000; font-family: Arial, sans-serif; font-size: 14px;">
            <h3 style="margin-top: 0; margin-bottom: 10px;">车次信息</h3>
        """
        for train, sub_stations_raw in trains_info:
            html += f'<div style="margin-bottom: 18px; border-bottom: 1px solid #e0e0e0; padding-bottom: 10px;">'
            html += f'<div style="font-weight: bold; color: #2c3e50; margin-bottom: 6px;">{train["name"]}</div>'
            html += '<div style="line-height: 1.8;">'
            for idx, st in enumerate(sub_stations_raw):
                lng, lat = station_coords[st]
                html += f'<a href="javascript:void(0);" data-station="{st}" data-lat="{lat}" data-lng="{lng}" class="station-link" style="color: #3498db; text-decoration: none; margin-right: 5px;">{st}</a>'
                if idx < len(sub_stations_raw) - 1:
                    html += ' → '
            html += '</div></div>'
        html += "</div>"
        return html

    def _build_javascript_code(self, station_popup_json):
        """构建交互JavaScript代码"""
        return f"""
        <script>
        var stationPopupContent = {station_popup_json};

        document.addEventListener('DOMContentLoaded', function() {{
            var mapDivs = document.querySelectorAll('[id^="map_"]');
            var foliumMap = mapDivs.length > 0 ? window[mapDivs[0].id] : null;

            if (!foliumMap) return;

            function openStationPopup(stationName, lat, lng) {{
                var content = stationPopupContent[stationName];
                if (content) {{
                    foliumMap.closePopup();
                    L.popup().setLatLng([lat, lng]).setContent(content).openOn(foliumMap);
                }}
            }}

            setTimeout(function() {{
                document.querySelectorAll('.station-link').forEach(function(link) {{
                    link.addEventListener('click', function(e) {{
                        e.preventDefault();
                        openStationPopup(
                            this.getAttribute('data-station'),
                            parseFloat(this.getAttribute('data-lat')),
                            parseFloat(this.getAttribute('data-lng'))
                        );
                    }});
                }});
            }}, 500);
        }});
        </script>
        """

    def _path_between_stations(self, src_coord, dst_coord):
        """在铁路图上求两站间路径：子图+A*，失败回退全图，再失败直线"""
        key = (src_coord, dst_coord)
        if key in self._path_cache:
            return self._path_cache[key]

        # 先在裁剪子图上跑 A*
        try:
            sub_g = self._subgraph_for_pair(src_coord, dst_coord, margin=0.8)
            path_nodes = nx.astar_path(
                sub_g,
                source=src_coord,
                target=dst_coord,
                heuristic=self._heuristic,
                weight="weight"
            )
        except Exception:
            # 子图失败，回退全图 A*
            try:
                path_nodes = nx.astar_path(
                    self.railway_graph,
                    source=src_coord,
                    target=dst_coord,
                    heuristic=self._heuristic,
                    weight="weight"
                )
            except Exception:
                path_nodes = [src_coord, dst_coord]

        self._path_cache[key] = path_nodes
        return path_nodes

    @staticmethod
    def _thin_path(path_nodes):
        # 路径点过多时抽稀，降低绘制/序列化时间
        n = len(path_nodes)
        if n <= 500:
            return path_nodes
        if n <= 1200:
            step = 2
        elif n <= 2500:
            step = 3
        else:
            step = 5
        thinned = path_nodes[::step]
        if thinned[-1] != path_nodes[-1]:
            thinned.append(path_nodes[-1])
        return thinned

    # ==================== 主绘制方法 ====================

    def draw_trains_map(self, trains_info, actual_start, actual_end, output_dir):
        """绘制最多三条铁路线路地图（重构版 - HTML构建已抽象）"""
        if len(trains_info) > 3:
            trains_info = trains_info[:3]

        # 准备数据
        station_coords = {}
        station_trains = {}
        all_coords = []

        for train, sub_stations_raw in trains_info:
            train_name = train["name"]
            for raw_name in sub_stations_raw:
                norm_name = self.normalize_station_name(raw_name)
                if norm_name not in self.city_to_node:
                    raise ValueError(f"站点 '{raw_name}' 没有坐标信息")
                if raw_name not in station_coords:
                    station_coords[raw_name] = self.city_to_node[norm_name]
                all_coords.append(station_coords[raw_name])
                if raw_name not in station_trains:
                    station_trains[raw_name] = []
                if train_name not in station_trains[raw_name]:
                    station_trains[raw_name].append(train_name)

        if not all_coords:
            raise ValueError("没有可绘制的有效坐标")

        # 创建地图
        lngs, lats = zip(*all_coords)
        center_lat = (min(lats) + max(lats)) / 2
        center_lng = (min(lngs) + max(lngs)) / 2
        m = folium.Map(location=[center_lat, center_lng], zoom_start=6)

        colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'darkblue', 'darkgreen', 'cadetblue', 'pink']

        # 绘制线路
        for idx, (train, sub_stations_raw) in enumerate(trains_info):
            color = colors[idx % len(colors)]
            full_path = []
            for i in range(len(sub_stations_raw) - 1):
                u = station_coords[sub_stations_raw[i]]
                v = station_coords[sub_stations_raw[i + 1]]
                segment = self._path_between_stations(u, v)
                if i > 0 and segment:
                    segment = segment[1:]
                full_path.extend(segment)
            full_path = self._thin_path(full_path)
            lat_lngs = [(lat, lng) for (lng, lat) in full_path]
            folium.PolyLine(
                lat_lngs,
                color=color,
                weight=3,
                opacity=0.8,
                popup=f"车次: {train['name']}"
            ).add_to(m)

        # 标注站点
        station_popup_content = {}
        for raw_name, coord in station_coords.items():
            lng, lat = coord
            trains_at_station = station_trains.get(raw_name, [])
            popup_content = f"<b>{raw_name}</b><br>车次: {', '.join(trains_at_station)}"
            station_popup_content[raw_name] = popup_content
            icon = folium.Icon(color="red") if raw_name in (actual_start, actual_end) else folium.Icon(color="blue", icon="info-sign")
            folium.Marker([lat, lng], popup=folium.Popup(popup_content, max_width=300), icon=icon).add_to(m)

        # 添加HTML元素（使用抽象方法）
        station_popup_json = json.dumps(station_popup_content, ensure_ascii=False)
        sidebar_html = self._build_sidebar_html(trains_info, station_coords)
        js_code = self._build_javascript_code(station_popup_json)

        m.get_root().html.add_child(folium.Element(js_code))
        m.get_root().html.add_child(folium.Element(sidebar_html))

        # 保存文件
        timestamp = int(time.time())
        filename = f"trains_{actual_start}_{actual_end}_{timestamp}.html".replace(" ", "_")
        filepath = os.path.join(output_dir, filename)
        m.save(filepath)
        return filepath, [t[0] for t in trains_info]


if __name__ == "__main__":
    print("===== 铁路绘图测试工具（精确匹配版） =====")
    print("输入起点和终点站名，例如：北京 上海")
    print("输入 'q' 或 'exit' 退出")

    service = RailwayDrawingService()

    while True:
        try:
            line = input("\n请输入起点和终点（用空格分隔）: ").strip()
            if not line:
                continue
            if line.lower() in ('q', 'exit', 'quit'):
                break
            parts = line.split()
            if len(parts) < 2:
                print("格式错误，请输入两个站名，用空格分隔")
                continue
            start, end = parts[0], parts[1]

            print(f"正在查询 {start} 到 {end} 的车次...")
            trains_info, actual_start, actual_end = service.find_trains_between(start, end)

            if not trains_info:
                print(f"未找到从 {start} 到 {end} 的车次")
                continue

            print(f"找到 {len(trains_info)} 个车次（实际使用站名: {actual_start} -> {actual_end}）:")
            for idx, (train, stations) in enumerate(trains_info, 1):
                print(f"  {idx}. {train['name']}: {' -> '.join(stations)}")

            output_dir = config_data.maps_output_dir
            os.makedirs(output_dir, exist_ok=True)
            try:
                filepath, valid_trains = service.draw_trains_map(trains_info, actual_start, actual_end, output_dir)
                print(f"地图已生成: {filepath}")
            except Exception as e:
                print(f"生成地图时出错: {e}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"发生错误: {e}")

    print("测试结束。")