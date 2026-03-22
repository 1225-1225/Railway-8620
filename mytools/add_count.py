import osmium
import geopandas as gpd
from shapely.geometry import LineString
from collections import defaultdict
from shapely import wkt
from collections import Counter

# 创建坐标索引器 + 几何工厂
location_store = osmium.index.create_map(
    "flex_mem")  # 创建一个内存中的节点位置索引器（flex_mem 是一种高效存储结构），它负责把每个节点的 ID 与其坐标对应起来，便于后续查询。
wkt_factory = osmium.geom.WKTFactory()  # 用来将 OSM 数据（way）转换为 WKT 格式的字符串，为了更方便地转成 shapely.geometry 中的几何对象。


# 自定义处理器
class RailwayHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.railways = []

    def node(self, n):
        if n.location.valid():
            location_store.set(n.id, n.location)

    def way(self, w, TARGET_RAILWAYS=["rail"]):
        if 'railway' in w.tags and w.tags['railway'] in TARGET_RAILWAYS:
            try:
                linestring_wkt = wkt_factory.create_linestring(
                    w)  # 它会读取这个 way 的所有节点，查找它们的坐标，并拼成一个 LINESTRING 的 WKT 字符串。 它会自动调用我们之前填入的 location_store 来取坐标！
                geom = wkt.loads(
                    linestring_wkt)  # 把上一步生成的 LINESTRING(...) 字符串变成 shapely 的 LineString 对象，用于后续保存成 .shp 或 GeoDataFrame
                self.railways.append({
                    'id': w.id,
                    'railway': w.tags['railway'],
                    'name': w.tags.get('name', ''),
                    'geometry': geom
                })
            except Exception as e:
                # print(f"忽略失败的 way {w.id}: {e}")
                pass


# 应用处理器
handler = RailwayHandler()
handler.apply_file(r"E:\PyCharm\LangChain-8620\data\china-latest.osm.pbf",
                   locations=True)  # 设置 locations=True 使其自动绑定节点位置

# 输出统计
print(f"选中了 {len(handler.railways)} 条符合条件的铁路")
counts = Counter(f['railway'] for f in handler.railways)
for k, v in counts.items():
    print(f"{k:<15} {v} 条")

# 转为 GeoDataFrame
gdf = gpd.GeoDataFrame(handler.railways, geometry='geometry', crs="EPSG:4326")

# 保存为 Shapefile
gdf.to_file("E:\PyCharm\LangChain-8620\data\china-latest.shp", driver="ESRI Shapefile", encoding="utf-8")
print("已保存为shapefile")