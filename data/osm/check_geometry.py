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

# 采样点跨度超过此值才检查（km）
LONG_STEP_KM = 10.0
# 单跨超过此值即报「超长跨度」，无需看转角（降采样造成不了这么大的间距）
SEVERE_SPAN_KM = 25.0
# 走向夹角超过此值判为折返（度）。180 = 完全掉头
REVERSAL_DEG = 150.0
# 判定真实弯道/折返的最小凸起高度（km）。
# 低于此值三点几乎共线，属于抖动，不算异常。
# 实测真实小半径弯道凸起 0.37~1.93km，抖动 0.18~0.29km。
CURVE_MIN_BUMP_KM = 0.3
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


def triangle_height_km(a, b, c):
    """点 b 相对弦 a-c 的垂直距离（km）

    用来区分「真实弯道」与「抖动」：
      真实弯道：折返点明显偏离前后点连线（凸起 > 0.3km）
      抖动    ：三点几乎共线（凸起 < 0.3km），只是方向算出来接近 180°

    这是判定 150° 夹角是否为真异常的关键 —— 只看夹角会把
    大量真实的小半径弯道误报。
    """
    span = haversine_km(a, c)
    if span < 0.01:
        return 0.0
    lat = math.radians((a[1] + b[1] + c[1]) / 3)
    kx = 111.0 * math.cos(lat)
    ky = 111.0
    ax, ay = a[0] * kx, a[1] * ky
    bx, by = b[0] * kx, b[1] * ky
    cx, cy = c[0] * kx, c[1] * ky
    area = abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2.0
    return 2.0 * area / span


def find_reversals(geom):
    """找出「真实折返」（拼接错误），排除真实弯道与抖动

    三级筛选：
      1. 夹角 > REVERSAL_DEG（150°）
      2. 凸起 > CURVE_MIN_BUMP_KM（0.3km）—— 排除共线抖动
      3. 跨度不极端 —— 极长跨度属于数据缺口，单独归入第 2 类

    这样第 1 类只报"真的折回去了"，实测从 28 处降到个位数。
    """
    out = []
    if len(geom) < 3:
        return out
    for i in range(1, len(geom) - 1):
        a, b, c = geom[i - 1], geom[i], geom[i + 1]
        if haversine_km(a, b) < 0.05 or haversine_km(b, c) < 0.05:
            continue
        d = angle_diff(bearing_deg(a, b), bearing_deg(b, c))
        if d <= REVERSAL_DEG:
            continue
        bump = triangle_height_km(a, b, c)
        if bump < CURVE_MIN_BUMP_KM:
            continue          # 共线抖动，不算异常
        out.append((i, round(d, 1), haversine_km(a, c), round(bump, 2)))
    return out


def find_long_steps(geom):
    """找出跨度大且「几何不连续」的采样段

    为什么不能只看跨度：
      降采样按 30 点/100km 输出，直线区段自然会出现 10-20km 间距。
      实测全线路 316 处 >10km 单跨，其中 294 处（93%）在 10-20km，
      这些是正常的，不是缺节点。

    判定「真异常」需要更强的证据：
      a) 跨越 >25km（远超降采样能造成的程度）
      b) 且该段两端走向突变 >45°（说明中间有拐点被跳过）
    满足 (a) 或 (a+b) 才报。
    """
    out = []
    for i in range(len(geom) - 1):
        step = haversine_km(geom[i], geom[i + 1])
        if step <= LONG_STEP_KM:
            continue

        # 计算这一跨两侧的走向夹角
        turn = None
        if i > 0:
            prev_b = bearing_deg(geom[i - 1], geom[i])
            this_b = bearing_deg(geom[i], geom[i + 1])
            turn = angle_diff(prev_b, this_b)
        elif len(geom) > 2:
            this_b = bearing_deg(geom[i], geom[i + 1])
            next_b = bearing_deg(geom[i + 1], geom[i + 2])
            turn = angle_diff(this_b, next_b)

        if turn is None:
            continue

        severe_span = step > SEVERE_SPAN_KM
        sharp_turn = turn > 45.0

        if severe_span or (step > 15.0 and sharp_turn):
            kind = "超长跨度" if severe_span else "跨度过大且转角急"
            out.append((i, round(step, 1), round(turn, 1), kind))
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

        for i, deg, span, bump in find_reversals(g):
            rev_hits.append((name, i, deg, span, bump))

        for i, step, deg, kind in find_long_steps(g):
            long_hits.append((name, i, step, deg, kind))

        straight = haversine_km(g[0], g[-1])
        if straight > 1.0:
            ratio = ln["km"] / straight
            if ratio > DETOUR_RATIO_MAX:
                detour_hits.append((name, round(ratio, 2), ln["km"], round(straight)))

    print(f"\n【1】真实折返（夹角 >{REVERSAL_DEG:.0f}° 且凸起 >{CURVE_MIN_BUMP_KM}km）: "
          f"{len(rev_hits)} 处")
    for h in sorted(rev_hits, key=lambda x: -x[2])[: args.top]:
        print(f"  {h[0]:20s} 索引{h[1]:4d} 夹角{h[2]:5.1f}° 跨度{h[3]:6.1f}km 凸起{h[4]:5.2f}km")

    print(f"\n【2】异常长跨（>15km 且转角 >45°，或 >{SEVERE_SPAN_KM:.0f}km）: "
          f"{len(long_hits)} 处")
    for h in sorted(long_hits, key=lambda x: -x[2])[: args.top]:
        print(f"  {h[0]:20s} 索引{h[1]:4d} 跨度{h[2]:5.1f}km 转角{h[3]:5.1f}° {h[4]}")

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
