import os
import pickle
import glob
import geopandas as gpd
import pandas as pd
import networkx as nx
from shapely.geometry import LineString, Point
from geopy.distance import geodesic
from scipy.spatial import cKDTree
import numpy as np
from tqdm import tqdm

# ========== 请修改为你的根目录和输出目录 ==========
ROOT_DIR = r"E:\Download\fromIDM\unzipmaps"   # 存放各省文件夹的根目录
OUTPUT_DIR = r"E:\PyCharm\LangChain-8620\data"            # 输出目录
# =================================================

def find_shp_files(base_dir, pattern):
    """递归查找符合 pattern 的所有 shapefile 路径（支持分卷 *_1, *_2）"""
    return glob.glob(os.path.join(base_dir, '**', pattern), recursive=True)

def load_and_merge_shp(file_list, desc="读取文件"):
    """读取多个 shapefile 并合并为一个 GeoDataFrame"""
    gdfs = []
    for f in tqdm(file_list, desc=desc):
        try:
            gdf = gpd.read_file(f)
            gdfs.append(gdf)
        except Exception as e:
            print(f"读取 {f} 时出错：{e}")
    if not gdfs:
        return None
    return pd.concat(gdfs, ignore_index=True)

# ================= 1. 收集并合并铁路线 =================
print("正在搜索铁路线文件...")
railway_files = find_shp_files(ROOT_DIR, 'gis_osm_railways_free_*.shp')
print(f"找到 {len(railway_files)} 个铁路线文件")

if not railway_files:
    raise FileNotFoundError("未找到任何铁路线文件")

print("正在合并铁路线数据...")
railways_all = load_and_merge_shp(railway_files, desc="合并铁路线")
if railways_all is None:
    raise RuntimeError("铁路线数据为空")

print(f"合并后铁路线总数：{len(railways_all)}")
print("字段列表：", railways_all.columns.tolist())
print("fclass 分布：", railways_all['fclass'].value_counts().head(10))

# 根据文档，普通铁路（包括高铁）的 fclass 为 'rail'
railways = railways_all[railways_all['fclass'] == 'rail'].copy()
print(f"筛选后普通铁路线数量：{len(railways)}")

# ================= 2. 收集并合并火车站 =================
print("\n正在搜索火车站文件...")
station_files = find_shp_files(ROOT_DIR, 'gis_osm_transport_free_*.shp')
print(f"找到 {len(station_files)} 个火车站文件")

if not station_files:
    raise FileNotFoundError("未找到任何火车站文件")

print("正在合并火车站数据...")
stations_all = load_and_merge_shp(station_files, desc="合并火车站")
if stations_all is None:
    raise RuntimeError("火车站数据为空")

print(f"合并后火车站总数：{len(stations_all)}")
print("字段列表：", stations_all.columns.tolist())
print("fclass 分布：", stations_all['fclass'].value_counts())

# 根据需求，只保留 railway_station（5601），排除 railway_halt
stations = stations_all[stations_all['fclass'] == 'railway_station'].copy()
print(f"筛选后火车站数量（仅 railway_station）：{len(stations)}")

# ================= 3. 提取站点信息 =================
stations_info = {}
for idx, row in stations.iterrows():
    name = row.get('name', None)
    if pd.isna(name) or name == '':
        continue
    geom = row.geometry
    if geom.geom_type != 'Point':
        continue
    if name not in stations_info:   # 同名站只保留第一个（可根据需要调整）
        lng, lat = geom.x, geom.y
        stations_info[name] = {
            'province': None,       # OSM 免费版无省份信息，可后续补充
            'city': None,
            'lng': lng,
            'lat': lat
        }
print(f"有效站点信息数：{len(stations_info)}")

# ================= 4. 构建铁路图 =================
def build_graph_from_railways(gdf):
    """将 GeoDataFrame 中的 LineString 转换为 networkx 图"""
    G = nx.Graph()
    for idx, row in tqdm(gdf.iterrows(), total=len(gdf), desc="构建图"):
        geom = row.geometry
        if not isinstance(geom, LineString):
            continue
        coords = list(geom.coords)  # 每个坐标 (lon, lat)
        if len(coords) < 2:
            continue
        nodes = [(lon, lat) for lon, lat in coords]
        for i in range(len(nodes)-1):
            u = nodes[i]
            v = nodes[i+1]
            # 计算两点间精确大地距离（米）
            dist = geodesic((u[1], u[0]), (v[1], v[0])).meters
            G.add_edge(u, v, weight=dist)
    return G

print("\n开始构建全国铁路图...")
G = build_graph_from_railways(railways)
print(f"图构建完成：节点数 {G.number_of_nodes()}，边数 {G.number_of_edges()}")

# ================= 5. 保存文件 =================
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 保存铁路图
with open(os.path.join(OUTPUT_DIR, 'china_railway.pkl'), 'wb') as f:
    pickle.dump(G, f)
print("已保存：china_railway.pkl")

# 保存站点信息
with open(os.path.join(OUTPUT_DIR, 'stations.pkl'), 'wb') as f:
    pickle.dump(stations_info, f)
print("已保存：stations.pkl")

# ================= 6. 构建站点到图节点的映射 =================
print("\n构建站点到最近节点的映射...")
nodes = list(G.nodes)
node_coords = np.array(nodes)          # shape (N, 2) 每行 (lon, lat)
tree = cKDTree(node_coords)

city_to_node = {}
for name, info in tqdm(stations_info.items(), desc="匹配节点"):
    lon, lat = info['lng'], info['lat']
    dist, idx = tree.query((lon, lat))
    nearest_node = nodes[idx]
    city_to_node[name] = nearest_node
    # 可选：打印距离过大的站点（用于调试）
    # if dist * 111320 > 5000:
    #     print(f"警告：{name} 距离最近节点 {dist*111320:.0f} 米")

print(f"共映射 {len(city_to_node)} 个站点")

with open(os.path.join(OUTPUT_DIR, 'city_to_node.pkl'), 'wb') as f:
    pickle.dump(city_to_node, f)
print("已保存：city_to_node.pkl")

print("\n所有处理完成！")