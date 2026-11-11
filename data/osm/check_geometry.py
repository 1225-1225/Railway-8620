# -*- coding: utf-8 -*-
"""线路几何异常检测（只读）

替代"肉眼判断有没有穿山体"这类不可自动化的检查，用几何指标定位可疑线路。

检测三类问题：
  1. 方位突变：拼接点两侧走向夹角过大（>150°）= 折返，通常意味着拼接错误
  2. 异常直线：单个采样跨度过大且两端走向不一致
  3. 绕行比异常：整条线里程 / 端点直线距离 过大

用法：
  python data/osm/check_geometry.py
  python data/osm/check_geometry.py --top 20
  python data/osm/check_geometry.py --line 青藏线    # 只看某条线
"""

import argparse
import io
import json
import math
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "osm", "out")

# 采样点跨度超过此值才检查"两端走向是否一致"（km）
LONG_STEP_KM = 10.0
# 走向夹角超过此值判为折返（度）。180 = 完全掉头
REVERSAL_DEG = 150.0
# 整条线的绕行比上限
DETOUR_RATIO_MAX = 2.5


def haversine_km(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    dlat = (lat2 - lat1) * 111.0
    dlng = (lng2 - lng1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)


def bearing_deg(a, b):
    """a -> b 的方位角（0=正北，顺时针）"""
    (lng1, lat1), (lng2, lat2) = a, b
    dx = (lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    dy = lat2 - lat1
    return math.degrees(math.atan2(dx, dy)) % 360.0


def angle_diff(b1, b2):
    """两个方位角的夹角（0-180）"""
    d = abs(b1 - b2) % 360.0
    return d if d <= 180.0 else 360.0 - d


def traj_length(pts):
    return sum(haversine_km(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def find_reversals(geom):
    """找出方位突变点（拼接错误或折返的典型特征）"""
    out = []
    if len(geom) < 3:
        return out
    for i in range(1, len(geom) - 1):
        b1 = bearing_deg(geom[i - 1], geom[i])
        b2 = bearing_deg(geom[i], geom[i + 1])
        # 两侧都太短时不判断（噪声大）
        if haversine_km(geom[i - 1], geom[i]) < 0.5:
            continue
        if haversine_km(geom[i], geom[i + 1]) < 0.5:
            continue
        d = angle_diff(b1, b2)
        if d > REVERSAL_DEG:
            out.append((i, round(d, 1), haversine_km(geom[i - 1], geom[i + 1])))
    return out


def find_long_steps(geom):
    """找出跨度大且两端走向不一致的采样段"""
    out = []
    for i in range(len(geom) - 1):
        step = haversine_km(geom[i], geom[i + 1])
        if step <= LONG_STEP_KM:
            continue
        # 看这段的走向与前后段的走向是否延续
        if i > 0:
            prev_b = bearing_deg(geom[i - 1], geom[i])
            this_b = bearing_deg(geom[i], geom[i + 1])
            if angle_diff(prev_b, this_b) > 45.0:
                out.append((i, round(step, 1), round(angle_diff(prev_b, this_b), 1)))
        elif len(geom) > 2:
            this_b = bearing_deg(geom[i], geom[i + 1])
            next_b = bearing_deg(geom[i + 1], geom[i + 2])
            if angle_diff(this_b, next_b) > 45.0:
                out.append((i, round(step, 1), round(angle_diff(this_b, next_b), 1)))
    return out


def main():
    ap = argparse.ArgumentParser(description="线路几何异常检测")
    ap.add_argument("--top", type=int, default=15, help="每类最多列出多少条")
    ap.add_argument("--line", default=None, help="只检查指定线路")
    ap.add_argument("--min-km", type=float, default=50.0,
                    help="只检查长度超过此值的线路（km）")
    args = ap.parse_args()

    path = os.path.join(OUT_DIR, "rail_lines.json")
    if not os.path.exists(path):
        raise SystemExit(f"[错误] 产物不存在: {path}")
    with open(path, encoding="utf-8") as f:
        lines = json.load(f)["lines"]

    if args.line:
        if args.line not in lines:
            raise SystemExit(f"[错误] 未找到线路: {args.line}")
        targets = {args.line: lines[args.line]}
    else:
        targets = {n: ln for n, ln in lines.items()
                   if ln["km"] >= args.min_km}

    print("=" * 72)
    print(f"线路几何异常检测（{len(targets)} 条线路，长度 ≥{args.min_km:.0f}km）")
    print("=" * 72)

    rev_hits = []
    long_hits = []
    detour_hits = []

    for name, ln in targets.items():
        g = ln["geometry"]
        if len(g) < 3:
            continue

        for i, deg, span in find_reversals(g):
            rev_hits.append((name, i, deg, span))

        for i, step, deg in find_long_steps(g):
            long_hits.append((name, i, step, deg))

        straight = haversine_km(g[0], g[-1])
        if straight > 1.0:
            ratio = ln["km"] / straight
            if ratio > DETOUR_RATIO_MAX:
                detour_hits.append((name, round(ratio, 2), ln["km"], round(straight)))

    print(f"\n【1】方位突变（> {REVERSAL_DEG:.0f}°，折返特征）: {len(rev_hits)} 处")
    for h in sorted(rev_hits, key=lambda x: -x[2])[: args.top]:
        print(f"  {h[0]:20s} 索引{h[1]:4d} 夹角{h[2]:5.1f}° 跨度{h[3]:6.1f}km")

    print(f"\n【2】异常长跨（> {LONG_STEP_KM:.0f}km 且走向突变 >45°）: {len(long_hits)} 处")
    for h in sorted(long_hits, key=lambda x: -x[2])[: args.top]:
        print(f"  {h[0]:20s} 索引{h[1]:4d} 跨度{h[2]:5.1f}km 转角{h[3]:5.1f}°")

    print(f"\n【3】绕行比 > {DETOUR_RATIO_MAX}: {len(detour_hits)} 条")
    for h in sorted(detour_hits, key=lambda x: -x[1])[: args.top]:
        print(f"  {h[0]:20s} 比值{h[1]:5.2f} 里程{h[2]:7.0f}km 直线{h[3]:6d}km")

    print("\n" + "=" * 72)
    total = len(rev_hits) + len(long_hits)
    print(f"结论：几何异常 {total} 处 / {len(targets)} 条线路")
    if total == 0:
        print("      未发现折返或异常长跨，几何连续可信")
    else:
        print("      建议用 --line <名称> 逐条查看上下文")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
