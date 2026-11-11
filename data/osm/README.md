# OSM 数据层

从 OSM 原始数据构建**铁路参考数据**的离线脚本。运行时（`agent/`）只消费 `out/` 下的产物，
不直接读 OSM 文件。

## 数据来源

- Geofabrik 中国快照：<https://download.geofabrik.de/asia/china-latest.osm.pbf>
- 许可：ODbL（需保留 attribution）
- 放置路径：`data/pbf/*.osm.pbf`（已在 `.gitignore` 中排除）

## 依赖

```bash
pip install osmium        # 预编译轮子约 1.9 MB，无 GDAL 依赖
```

## 为什么用 .osm.pbf 而不是 GPKG

| | `.osm.pbf` | `.gpkg`（GDAL 导出） |
|---|---|---|
| 体积 | 1.5 GB | 9.7 GB |
| 标签 | 原生 dict | `other_tags` 字符串，需正则反解 |
| 关系成员顺序 | 保留 `role` 与排列 | 合成为整体几何后**丢失** |
| 几何 | 库直接给坐标 | 需自写 WKB 解析（约 150 行）|

GPKG 仅在需要 QGIS 肉眼核查时临时导出。

## 数据源：为什么用 way 的 name 标签，不用 route 关系

**这是本项目最重要的一条经验。**

`route=railway` 关系收录极不完整。实测同一批线路：

| 线路 | 关系成员 way | `name` 标签 way | 关系漏掉 |
|---|---|---|---|
| 沪昆线 | 10 | 5360 | **99.8%** |
| 京沪线 | 2764 | 2762 | 0.4% |
| 京哈线 | 2078 | 2080 | 0.1% |

若只读关系，沪昆线几乎"凭空消失"（只剩 12 km）。

改用 `railway=rail` 且带 `name` 的 way 作数据源：

- 覆盖线路名 **3244 条**（关系法仅 1932 条，+68%）
- 覆盖 way **24 万个**
- 站点有线路归属比例 **93.1%**（关系法仅 52.8%）

## 里程为什么不能直接求和

OSM 把**每一股道**都画成独立 way，全部带同一个 `name`：

```python
{'railway':'rail','name':'京沪线','oneway':'yes'}              # 上行
{'railway':'rail','name':'京沪线','railway:track_ref':'II-II'}  # 下行
{'railway':'rail','name':'京沪线','passenger_lines':'3'}        # 第三股道
```

因此"所有 way 长度求和"得到约 2 倍里程（实测京沪 3093 vs 实际 1463，2.11×）。

**解法**：把该线路所有 way 建成图，取**地理上最远的一对端点**，在图上求**最短路** ——
最短路天然只走其中一条轨道。

再对多连通分量做「几何覆盖率去重」（平行轨道被覆盖 ≥50% 则丢弃），
最后在 >50 km 的跳变处切开，各段独立保留。

## 两站之间有多条线路时怎么选

这是运行时消歧的核心。**判据按优先级**：

1. **车次类型先验**（最强）：`G/D/C` → 高速线；`K/T/Z` → 普速线
2. **线路长度**：更长者更可能是主干线
3. **线路名特征**：含"联络线/走行/绕行/专用线"的降权
4. **绕行比质量门**：路径/直线比值须在 0.5~3.0，否则换下一条

线路等级判定规则（`RouteGeometry.line_grade`）：

| 判定 | 命中词 |
|---|---|
| `high_speed` | 高速、客专、高铁、城际 |
| `conventional` | 联络线、绕行、走行、疏解、专用线、货线、环线、支线 |
| `other` | 其余（含纯股道名如 `1道`）|

实测效果（京沪走廊）：

```
G1  (高速): 北京南->天津南  共同线路 1 ['京沪高铁']
T35 (特快): 北京->沧州      共同线路 1 ['京沪线']
G1  -> 3/3 段真实轨道，里程 1313 km（实际约 1318）
T35 -> 5/5 段真实轨道，里程 1077 km
```

## 构建结果（china-261109 快照）

```
Pass 1/2  带 name 的 way   240,008 / 426,092 总 way    12.3s
Pass 2/2  节点坐标         1,285,193 节点 / 17,536 站   44.2s
装配线路几何（单轨）        3,240 线成功 / 0 为空        21.5s
站点→线路索引              9,624 / 10,333 站 (93.1%)   131.1s
────────────────────────────────────────────────
总耗时 3.5 分钟
产物：stations.json 3.9MB / rail_lines.json 2.0MB / station_line_index.json 0.5MB
```

## 里程精度验收

20 条已知里程的干线，**17 条在 ±15% 内（85%）**：

| 线路 | 期望 | 实得 | 误差 |
|---|---|---|---|
| 京沪高铁 | 1318 | 1308 | **-0.8%** |
| 京哈线 | 1249 | 1248 | **-0.0%** |
| 贵广客专线 | 857 | 854 | **-0.4%** |
| 沪昆高速线 | 2264 | 2237 | -1.2% |
| 陇海线 | 1759 | 1733 | -1.5% |
| 京广线 | 2298 | 2259 | -1.7% |
| 京沪线 | 1463 | 1434 | -2.0% |
| 京哈高速线 | 1249 | 1213 | -2.9% |
| 成贵客专线 | 648 | 629 | -3.0% |
| 京九线 | 2400 | 2288 | -4.7% |
| 青藏线 | 1956 | 1842 | -5.8% |
| 胶济线 | 393 | 368 | -6.4% |
| 京广高速线 | 2298 | 2094 | -8.9% |
| 杭深线 | 1450 | 1319 | -9.0% |
| 襄渝线 | 899 | 787 | -12.4% |
| 沪昆线 | 2264 | 2543 | +12.3% |
| 兰新线 | 1892 | 2368 | +25.2% |
| 京包线 | 824 | 607 | -26.3% |
| 成昆线 | 1091 | 761 | -30.3% |

偏差较大的都是 OSM 数据本身有缺段（如成昆线部分区段用 `name=成昆线复线` 等不同名）。

**断裂点**：3240 条线路中仅 11 条含 >50 km 跳变（0.34%）。

## pyosmium 4.x API 备忘

实测踩过的坑：

```python
# 标签迭代产出 Tag 对象，不是字符串
for t in tags:                 # t.k / t.v
    if t.k.startswith("name:zh"): ...

# Header 没有 has_option()；多版本判断是属性不是方法
h = osmium.io.Reader(p).header()
h.has_multiple_object_versions    # bool

# 关系成员是位置参数 (ref, mtype, role)，且不在 mutable 命名空间下
M = osmium.osm.RelationMember
M(100, "w", "forward")

# 【性能关键】必须用 FileProcessor + Filter，不能用 SimpleHandler 全量回调
fp = osmium.FileProcessor(path, osmium.osm.NODE, thread_pool=osmium.io.ThreadPool(8))
fp.with_filter(osmium.filter.IdFilter(needed_ids))       # C++ 层过滤
fp.with_filter(osmium.filter.KeyFilter("railway"))       # 按标签键过滤
```

**性能实测**（扫描 1.5 亿节点找 5 万个）：

| 方案 | 耗时 |
|---|---|
| `SimpleHandler` 全量回调 | 698.6 s |
| `FileProcessor` + `IdFilter` + 8 线程 | **11.1 s** |

**63 倍差距**。`locations=True` 建全国节点索引更慢（实测 36 分钟），应避免。

## 脚本

### `probe_pbf.py` —— 可用性验证（只读）

在动手写提取逻辑之前，先确认这份 PBF 够不够用。

```bash
python data/osm/probe_pbf.py                       # 自动找 data/pbf/*.osm.pbf
python data/osm/probe_pbf.py D:/down/china.osm.pbf
python data/osm/probe_pbf.py --fast                # 跳过坐标索引
```

输出：文件结构 / 要素规模 / 关系有序性 / 站名对齐率。

### `build_reference.py` —— 构建参考数据

```bash
python data/osm/build_reference.py                 # 全量，约 3.5 分钟
python data/osm/build_reference.py --limit 50      # 调试：只处理 50 条线路
python data/osm/build_reference.py --out D:/tmp    # 指定输出目录
```

产物：

```
out/stations.json            17,536 站（含 name_zh / aliases / lines）
out/rail_lines.json          3,240 线（单轨几何 + 分段元数据）
out/station_line_index.json  站点 → 线路名
```

## 验收标准

| 指标 | 期望 | 不达标说明 |
|---|---|---|
| 线路名数 | ≈ 3200 | 远低 → 快照范围不对（如只下了某省）|
| 站点有线路归属 | ≥ 90% | 低 → 站名规范化或吸附半径需调整 |
| ±15% 内的已知干线 | ≥ 80% | 低 → 里程算法需排查 |
| 含 >50km 断裂的线路 | < 1% | 高 → 拼接容差需收紧 |

## 待办

- [x] `build_reference.py` —— 导出 stations / rail_lines / index
- [ ] `build_station_alias.py` —— 12306 站名 → OSM 要素 ID 精确对齐 + 人工 override
- [ ] 站名未命中的 12 个（马鞍山东、庐江西等）需 `station_override.json`
