# -*- coding: utf-8 -*-
"""PBF 可用性验证脚本（只读，不写任何数据）

目的：在动手重写数据提取层之前，先用新下载的 .osm.pbf 实测三项关键指标，
      用真实读数回答"这份 PBF 够不够用"。

  1. 文件结构    —— 版本、生成器、时间戳、坐标范围
  2. 要素规模    —— 国铁站点 / 地铁站点 / railway 路段 / route=railway 关系
  3. 关系有序性  —— route=railway 关系的成员是否带 role 与顺序（决定能否免去去噪）
  4. 站名对齐    —— 12306 站名（data/train_details.json）能匹配上多少

用法：
  python data/osm/probe_pbf.py                      # 自动找 data/pbf/*.osm.pbf
  python data/osm/probe_pbf.py path/to/china.osm.pbf
  python data/osm/probe_pbf.py --fast               # 跳过坐标索引（快，但不校验坐标）

前置：pip install osmium
"""

import argparse
import collections
import glob
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import osmium

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
PBF_DIR = os.path.join(PROJECT_ROOT, "data", "pbf")
TRAIN_DETAILS = os.path.join(PROJECT_ROOT, "data", "train_details.json")

# 中国大陆经纬度粗筛（与旧 02 脚本的过滤条件一致）
LNG_MIN, LNG_MAX = 70.0, 140.0
LAT_MIN, LAT_MAX = 15.0, 55.0

# 地铁/轻轨等城市轨道，不能算国铁站点
METRO_STATION = {"subway", "light_rail", "monorail", "funicular", "tram"}

# 常见繁体 → 简体（OSM 港澳台要素用繁体，12306 用简体）
T2S_PAIRS = [
    ("龍", "龙"), ("門", "门"), ("東", "东"), ("華", "华"), ("陽", "阳"),
    ("廣", "广"), ("濟", "济"), ("寧", "宁"), ("遠", "远"), ("慶", "庆"),
    ("興", "兴"), ("義", "义"), ("貴", "贵"), ("蘭", "兰"), ("銀", "银"),
    ("連", "连"), ("雲", "云"), ("鄉", "乡"), ("鎮", "镇"), ("莊", "庄"),
    ("鐵", "铁"), ("車", "车"), ("號", "号"), ("廈", "厦"), ("萬", "万"),
    ("瀋", "沈"), ("遼", "辽"), ("灣", "湾"), ("開", "开"), ("關", "关"),
    ("閉", "闭"), ("橋", "桥"), ("頭", "头"), ("鋪", "铺"), ("驛", "驿"),
    ("區", "区"), ("縣", "县"), ("齊", "齐"), ("烏", "乌"), ("魯", "鲁"),
    ("術", "术"), ("豐", "丰"), ("國", "国"), ("島", "岛"), ("嶺", "岭"),
    ("臺", "台"), ("廬", "庐"), ("馬", "马"), ("貴", "贵"), ("遼", "辽"),
]
T2S = str.maketrans(dict(T2S_PAIRS))


# ────────────────────────────────────────────────────────────
#  站名规范化
# ────────────────────────────────────────────────────────────

def strip_bilingual(name: str) -> str:
    """剥离 OSM 双语后缀，如 '乌鲁木齐 ئۈرۈمچى' → '乌鲁木齐'

    OSM 新疆/西藏站名常把少数民族文字接在中文后用空格分隔。
    规则：最后一段若不含汉字，视为附加文字丢弃。
    """
    parts = name.split(" ")
    if len(parts) > 1 and not re.search(r"[\u4e00-\u9fff]", parts[-1]):
        return " ".join(parts[:-1]).strip()
    return name.strip()


def canonical(tags, raw_name: str) -> str:
    """取站点规范中文名：name:zh-Hans > name:zh > name:zh-Hant > 剥离双语后的 name"""
    for key in ("name:zh-Hans", "name:zh", "name:zh-Hant"):
        v = tags.get(key)
        if v:
            return v.strip()
    return strip_bilingual(raw_name or "")


def variants(name: str) -> set:
    """生成一个站名的所有可比对变体（简繁 + 去/加"站"字）"""
    if not name:
        return set()
    out = {name, name.translate(T2S)}
    base = name[:-1] if (name.endswith("站") and len(name) > 1) else name
    out.update({base, base.translate(T2S)})
    out.update({base + "站", (base + "站").translate(T2S)})
    return {v for v in out if v}


# ────────────────────────────────────────────────────────────
#  扫描处理器
# ────────────────────────────────────────────────────────────

class Probe(osmium.SimpleHandler):
    def __init__(self, want_coords: bool):
        super().__init__()
        self.want_coords = want_coords

        # 站点
        self.station_nodes = 0
        self.station_named = 0
        self.station_cn = 0
        self.station_national = 0
        self.station_metro = 0
        self.station_with_zh = 0
        self.station_index = {}

        # 路网
        self.rail_ways = 0
        self.rail_ways_named = 0

        # 线路关系
        self.route_relations = 0
        self.route_named = 0
        self.route_members_total = 0
        self.route_other_type = 0
        self.route_sample = None
        self.route_member_roles = collections.Counter()
        self.route_name_samples = []

    def node(self, n):
        tags = n.tags
        if tags.get("railway") not in ("station", "halt"):
            return
        self.station_nodes += 1

        raw = tags.get("name") or ""
        if not raw:
            return
        self.station_named += 1

        is_metro = (
            tags.get("station") in METRO_STATION
            or tags.get("subway") == "yes"
            or "MTR" in (tags.get("network") or "")
        )
        if is_metro:
            self.station_metro += 1
        else:
            self.station_national += 1

        if any(t.k.startswith("name:zh") for t in tags):
            self.station_with_zh += 1

        if not self.want_coords or not n.location.valid():
            return
        lat, lng = n.location.lat, n.location.lon
        if not (LNG_MIN <= lng <= LNG_MAX and LAT_MIN <= lat <= LAT_MAX):
            return
        self.station_cn += 1

        name = canonical(tags, raw)
        if not name:
            return

        # 同名冲突：国铁(2) > 未标注(1) > 地铁(0)
        if is_metro:
            priority = 0
        elif (tags.get("train") == "yes" or tags.get("uic_ref")
              or tags.get("railway:ref")):
            priority = 2
        else:
            priority = 1

        prev = self.station_index.get(name)
        if prev is None or priority > prev["priority"]:
            self.station_index[name] = {
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "priority": priority,
                "is_metro": is_metro,
            }

    def way(self, w):
        if w.tags.get("railway") != "rail":
            return
        self.rail_ways += 1
        if w.tags.get("name"):
            self.rail_ways_named += 1

    def relation(self, r):
        route = r.tags.get("route")
        if route not in ("railway", "train", "subway", "light_rail", "tram", "monorail"):
            return
        if route != "railway":
            self.route_other_type += 1
            return

        self.route_relations += 1
        name = r.tags.get("name") or ""
        if name:
            self.route_named += 1
            if len(self.route_name_samples) < 10:
                self.route_name_samples.append(name)

        members = list(r.members)
        self.route_members_total += len(members)
        for m in members:
            self.route_member_roles[m.role or "(空)"] += 1

        if self.route_sample is None and len(members) >= 20:
            self.route_sample = {
                "name": name or "(未命名)",
                "total_members": len(members),
                "head": [
                    {"type": m.type, "role": m.role or "(空)", "ref": m.ref}
                    for m in members[:8]
                ],
            }


# ────────────────────────────────────────────────────────────
#  报告
# ────────────────────────────────────────────────────────────

def hr(title=""):
    print("\n" + "=" * 70)
    if title:
        print(title)
        print("=" * 70)


def read_header(path):
    reader = osmium.io.Reader(path)
    h = reader.header()
    box = h.box()
    info = {
        "generator": h.get("generator"),
        "replication_timestamp": h.get("osmosis_replication_timestamp"),
        "bbox": (
            [round(box.bottom_left.lon, 3), round(box.bottom_left.lat, 3),
             round(box.top_right.lon, 3), round(box.top_right.lat, 3)]
            if box.valid() else None
        ),
        # 历史文件（.osh）才会带多版本对象；普通快照为 False
        "multiple_object_versions": bool(h.has_multiple_object_versions),
    }
    reader.close()
    return info


def load_12306_names():
    if not os.path.exists(TRAIN_DETAILS):
        return collections.Counter()
    with open(TRAIN_DETAILS, encoding="utf-8") as f:
        details = json.load(f)
    counter = collections.Counter()
    for info in details.values():
        for s in info.get("stations", []):
            s = (s or "").strip()
            if s:
                counter[s] += 1
    return counter


def main():
    ap = argparse.ArgumentParser(description="验证 OSM PBF 是否可用于铁路数据提取")
    ap.add_argument("pbf", nargs="?", default=None,
                    help="PBF 路径（默认自动搜索 data/pbf/*.osm.pbf）")
    ap.add_argument("--fast", action="store_true",
                    help="跳过坐标索引与站名对齐（更快）")
    args = ap.parse_args()

    path = args.pbf
    if not path:
        cands = sorted(glob.glob(os.path.join(PBF_DIR, "*.osm.pbf")))
        if not cands:
            print(f"[错误] 未在 {PBF_DIR} 找到 *.osm.pbf")
            print("       请先下载，例如：")
            print("       https://download.geofabrik.de/asia/china-latest.osm.pbf")
            return 1
        path = max(cands, key=os.path.getmtime)
    if not os.path.exists(path):
        print(f"[错误] 文件不存在: {path}")
        return 1

    size_gb = os.path.getsize(path) / 1024 ** 3
    hr("1. 文件结构")
    print(f"  路径: {path}")
    print(f"  大小: {size_gb:.2f} GB")
    for k, v in read_header(path).items():
        print(f"  {k}: {v}")
    print(f"  修改时间: {time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(path)))}")

    want_coords = not args.fast
    hr("2. 要素扫描" + ("" if want_coords else "（--fast，不建坐标索引）"))
    print("  正在扫描" + ("（含节点坐标索引，较慢）..." if want_coords else "..."))
    t0 = time.time()
    handler = Probe(want_coords=want_coords)
    handler.apply_file(path, locations=want_coords, idx="sparse_mem_array")
    elapsed = time.time() - t0

    denom = handler.station_nodes or 1
    print(f"\n  耗时: {elapsed:.1f} 秒")
    print(f"\n  【站点】railway=station/halt 的 node: {handler.station_nodes:,}")
    print(f"    有 name:             {handler.station_named:,}")
    print(f"    国铁（非地铁）:       {handler.station_national:,}")
    print(f"    地铁/轻轨/缆车:       {handler.station_metro:,}")
    print(f"    带 name:zh*:         {handler.station_with_zh:,}  "
          f"({handler.station_with_zh / denom:.1%})")
    if want_coords:
        print(f"    落在中国经纬度范围内: {handler.station_cn:,}")
        print(f"    去重后唯一站名:       {len(handler.station_index):,}")

    print(f"\n  【路网】railway=rail 的 way: {handler.rail_ways:,}")
    print(f"    其中带 name:         {handler.rail_ways_named:,}")

    print(f"\n  【线路】route=railway 关系: {handler.route_relations:,}")
    print(f"    其中带 name:         {handler.route_named:,}")
    print(f"    成员总数:             {handler.route_members_total:,}")
    print(f"    成员 role 分布:       {dict(handler.route_member_roles.most_common(6))}")
    print(f"    （其他 route 类型已跳过: {handler.route_other_type:,}）")

    hr("3. route=railway 关系的有序性")
    if handler.route_sample:
        s = handler.route_sample
        print(f"  样例: {s['name']}  共 {s['total_members']} 个成员")
        print("  前 8 个成员（顺序与 role 均为 OSM 原生，无需启发式去噪）:")
        for i, m in enumerate(s["head"], 1):
            print(f"    {i}. type={m['type']:<4} role={m['role']:<12} ref={m['ref']}")
    else:
        print("  [!] 未找到成员数 >= 20 的关系，无法验证有序性")

    if handler.route_name_samples:
        print(f"\n  线路名样例: {', '.join(handler.route_name_samples[:8])}")

    if want_coords and handler.station_index:
        hr("4. 站名对齐（12306 → OSM）")
        names = load_12306_names()
        if not names:
            print("  [!] 未找到 data/train_details.json，跳过")
        else:
            index = handler.station_index
            exact, metro_only, miss = [], [], []
            for name in names:
                # 枚举所有变体，收集全部候选，取优先级最高者。
                # 不能"命中即停"：OSM 里 '北京西'(地铁) 与 '北京西站'(国铁)
                # 常分属两个 key，先命中谁取决于 set 的任意顺序。
                cand = [index[v] for v in variants(name) if v in index]
                if not cand:
                    miss.append(name)
                    continue
                best = max(cand, key=lambda x: x["priority"])
                if best["is_metro"]:
                    metro_only.append(name)
                else:
                    exact.append(name)

            total = len(names)
            print(f"  12306 唯一站名: {total:,}")
            print(f"    纯国铁命中:   {len(exact):,}  ({len(exact) / total:.2%})")
            print(f"    仅地铁兜底:   {len(metro_only):,}  ({len(metro_only) / total:.2%})")
            print(f"    未命中:       {len(miss):,}  ({len(miss) / total:.2%})")

            weighted = sum(names.values())
            hit_w = sum(names[x] for x in exact)
            print(f"\n  按车次站次加权覆盖率: {hit_w / weighted:.2%}  "
                  f"({hit_w:,}/{weighted:,})")

            if metro_only:
                print(f"\n  仅地铁兜底: {', '.join(metro_only[:12])}")
            if miss:
                print("\n  未命中 Top20（按出现次数）:")
                for name in sorted(miss, key=lambda x: -names[x])[:20]:
                    print(f"    {name:<14} {names[name]:>5} 次")

            print(f"\n  结论: {'[可用]' if len(exact) / total >= 0.95 else '[覆盖率偏低，需人工 override]'}")

    hr("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
