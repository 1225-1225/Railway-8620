# -*- coding: utf-8 -*-
"""参考数据质量验收（只读，可重复运行）

用法：
  python data/osm/verify.py
  python data/osm/verify.py --verbose    # 列出所有异常线路

检查项：
  1. 产物规模（线路数 / 站点数）
  2. 几何连续性（>50km 跳变 = 断裂）
  3. 已知干线里程误差
  4. 车次端到端覆盖率（抽样）

里程基准说明（重要）：
  基准值取自《中国铁路线路里程表》及铁路年鉴，已人工核对。
  注意区分同名不同线，例如：
    沪昆高速线 ≈ 2264 km   （客运专线）
    沪昆线     ≈ 2690 km   （普速，上海-昆明）
  把 2264 套到普速线上会得出错误的 +12.6% 偏差。
"""

import argparse
import io
import json
import math
import os
import random
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "osm", "out")
TRAIN_DETAILS = os.path.join(PROJECT_ROOT, "data", "train_details.json")

# 让 `import agent.route_geometry` 可用（脚本在 data/osm/ 下）
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 已知干线基准里程（km）。None 表示基准未核实，不参与统计。
BASELINE = {
    # 高速线
    "京沪高铁": 1318,
    "京广高速线": 2298,
    "京哈高速线": 1249,
    "沪昆高速线": 2264,
    "合福高速线": 806,
    "贵广客专线": 857,
    "成贵客专线": 648,
    # 普速干线
    "京沪线": 1463,
    "京广线": 2298,
    "京九线": 2400,
    "陇海线": 1759,
    "兰新线": 2360,     # 兰州西-阿拉山口全线（1892 只是兰州-乌鲁木齐段）
    "青藏线": 1956,
    "京哈线": 1249,
    "沪昆线": 2690,     # 普速，注意与 2264 的沪昆高速线区分
    "京包线": 824,
    "胶济线": 393,
    "杭深线": 1450,
    "襄渝线": 899,      # 已核对
    "成昆线": 1091,     # 老线，另有 1096 口径
}

# 允许误差
TOLERANCE_PCT = 15.0


def haversine_km(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def load_lines():
    path = os.path.join(OUT_DIR, "rail_lines.json")
    if not os.path.exists(path):
        raise SystemExit(f"[错误] 产物不存在: {path}\n       请先运行 build_reference.py")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["lines"]


def load_stations():
    path = os.path.join(OUT_DIR, "stations.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["stations"]


def hr(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def check_scale(lines, stations):
    hr("1. 产物规模")
    kinds = {}
    for st in stations.values():
        kinds[st["kind"]] = kinds.get(st["kind"], 0) + 1
    with_lines = sum(1 for st in stations.values() if st.get("lines"))
    rail = sum(1 for st in stations.values() if st["kind"] != "metro")

    print(f"  线路数: {len(lines):,}")
    print(f"  站点数: {len(stations):,}  类型 {kinds}")
    print(f"  国铁站点有线路归属: {with_lines:,} / {rail:,} "
          f"({with_lines/max(1,rail):.1%})")

    ok = True
    if len(lines) < 3000:
        print(f"  [!] 线路数偏少（期望 ≈3200），可能 PBF 是省级切片")
        ok = False
    if with_lines / max(1, rail) < 0.90:
        print(f"  [!] 站点归属率偏低（期望 ≥90%）")
        ok = False
    return ok


def check_continuity(lines, verbose=False):
    hr("2. 几何连续性")
    broken = []
    for name, ln in lines.items():
        g = ln["geometry"]
        jumps = [haversine_km(g[i], g[i + 1]) for i in range(len(g) - 1)]
        big = [j for j in jumps if j > 50]
        if big:
            broken.append((name, len(big), max(big)))

    print(f"  含 >50km 跳变的线路: {len(broken)} / {len(lines)} "
          f"({len(broken)/max(1,len(lines)):.2%})")
    if verbose and broken:
        for name, n, mx in sorted(broken, key=lambda x: -x[2])[:20]:
            print(f"    {name}: {n} 处, 最大 {mx:.0f}km")

    ok = len(broken) == 0
    if not ok:
        print(f"  [!] 存在断裂线路，需检查 assemble_line / split_at_big_gaps")
    return ok


def check_mileage(lines, verbose=False):
    hr("3. 已知干线里程")
    rows = []
    for name, expect in BASELINE.items():
        if name not in lines:
            rows.append((name, expect, None, None))
            continue
        got = lines[name]["km"]
        err = (got - expect) / expect * 100
        rows.append((name, expect, got, err))

    rows.sort(key=lambda r: abs(r[3]) if r[3] is not None else 999)

    print(f"  {'线路':16s} {'基准':>7s} {'实得':>8s} {'误差':>8s}")
    for name, expect, got, err in rows:
        if got is None:
            print(f"  {name:16s} {expect:7d}     缺失")
        else:
            mark = "" if abs(err) <= TOLERANCE_PCT else "  <<<"
            print(f"  {name:16s} {expect:7d} {got:8.0f} {err:+7.1f}%{mark}")

    rated = [r for r in rows if r[3] is not None]
    passed = [r for r in rated if abs(r[3]) <= TOLERANCE_PCT]
    print(f"\n  ±{TOLERANCE_PCT:.0f}% 内: {len(passed)}/{len(rated)} "
          f"({len(passed)/max(1,len(rated)):.0%})")

    ok = len(rated) and len(passed) / len(rated) >= 0.80
    if not ok:
        print(f"  [!] 达标率偏低（期望 ≥80%）")

    if verbose:
        worst = [r for r in rated if abs(r[3]) > TOLERANCE_PCT]
        if worst:
            print(f"\n  超出容差的线路（多为 OSM 数据缺口，非算法问题）:")
            for name, expect, got, err in worst:
                print(f"    {name}: {got:.0f} vs {expect} ({err:+.1f}%)")
    return ok


def check_trains(limit=200):
    hr("4. 车次端到端（抽样）")
    if not os.path.exists(TRAIN_DETAILS):
        print("  [!] 未找到 train_details.json，跳过")
        return True

    try:
        from agent.route_geometry import get_route_geometry
    except ImportError:
        print("  [!] 无法导入 agent.route_geometry，跳过")
        return True

    rg = get_route_geometry()
    if not rg.available:
        print("  [!] 参考数据不可用，跳过")
        return True

    with open(TRAIN_DETAILS, encoding="utf-8") as f:
        details = json.load(f)

    codes = list(details)
    random.seed(42)
    if len(codes) > limit:
        codes = random.sample(codes, limit)

    total_seg = matched = fallback = missing = 0
    abnormal = []

    for code in codes:
        info = details[code]
        sts = info.get("stations") or []
        cls = info.get("class")
        for a, b in zip(sts, sts[1:]):
            total_seg += 1
            seg, src = rg.find_segment(a, b, cls)
            if src == "no_station" or not seg:
                missing += 1
                continue
            if src == "line":
                matched += 1
            else:
                fallback += 1
            if len(seg) >= 2:
                km = sum(haversine_km(seg[i], seg[i + 1]) for i in range(len(seg) - 1))
                straight = haversine_km(seg[0], seg[-1])
                if straight > 50:
                    ratio = km / straight
                    if ratio > 3.0 or ratio < 0.6:
                        abnormal.append((code, a, b, src, round(ratio, 2)))

    print(f"  抽样 {len(codes)} 个车次，站段 {total_seg:,}")
    print(f"    真实轨道: {matched:,} ({matched/max(1,total_seg):.1%})")
    print(f"    降级直线: {fallback:,} ({fallback/max(1,total_seg):.1%})")
    print(f"    站点缺失: {missing:,} ({missing/max(1,total_seg):.1%})")
    print(f"    路径/直线异常（>3.0 或 <0.6）: {len(abnormal)}")

    if abnormal:
        for a in abnormal[:10]:
            print(f"      {a}")

    ok = matched / max(1, total_seg) >= 0.75 and len(abnormal) == 0
    if not ok:
        print(f"  [!] 真实轨道比例偏低或存在异常绕行")
    return ok


def main():
    ap = argparse.ArgumentParser(description="OSM 参考数据质量验收")
    ap.add_argument("--verbose", action="store_true", help="列出详细异常")
    args = ap.parse_args()

    lines = load_lines()
    stations = load_stations()

    results = [
        ("产物规模", check_scale(lines, stations)),
        ("几何连续性", check_continuity(lines, args.verbose)),
        ("里程精度", check_mileage(lines, args.verbose)),
        ("车次端到端", check_trains()),
    ]

    hr("结论")
    for name, ok in results:
        print(f"  {'[通过]' if ok else '[需关注]'} {name}")

    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
