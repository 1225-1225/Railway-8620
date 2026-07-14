import json, math

routes = json.load(open(r'd:\PyCharm\Railway-8620\data\cleaned_route_geometries.json', 'r', encoding='utf-8'))
coords = json.load(open(r'd:\PyCharm\Railway-8620\data\station_coords.json', 'r', encoding='utf-8'))

print("=== 京九/京广相关路线 ===")
for name in sorted(routes.keys()):
    if '京九' in name or '京广' in name:
        info = routes[name]
        traj = info['trajectory']
        if traj:
            lats = [p[1] for p in traj]
            lngs = [p[0] for p in traj]
            st = info.get('stations', [])
            print(f"{name}: {len(traj)}pts, {info['total_km']}km, lat=[{min(lats):.2f},{max(lats):.2f}], {len(st)}站")

# 检查哪些路线经过衡水附近
print("\n=== 经过衡水附近的路线 ===")
hs = coords.get('衡水', [115.685, 37.743])
for name, info in routes.items():
    traj = info['trajectory']
    if not traj:
        continue
    best_d = 999
    for lng, lat in traj:
        dlat = (lat - hs[1]) * 111
        dlng = (lng - hs[0]) * 111 * math.cos(math.radians(hs[1]))
        d = math.sqrt(dlat*dlat + dlng*dlng)
        if d < best_d:
            best_d = d
    if best_d < 15:
        print(f"  {name}: dist={best_d:.1f}km")

# 检查哪些路线经过北京西附近
print("\n=== 经过北京西附近的路线 ===")
bx = coords.get('北京西', [116.315, 39.894])
for name, info in routes.items():
    traj = info['trajectory']
    if not traj:
        continue
    best_d = 999
    for lng, lat in traj:
        dlat = (lat - bx[1]) * 111
        dlng = (lng - bx[0]) * 111 * math.cos(math.radians(bx[1]))
        d = math.sqrt(dlat*dlat + dlng*dlng)
        if d < best_d:
            best_d = d
    if best_d < 10:
        print(f"  {name}: dist={best_d:.1f}km")

# 检查哪些路线经过北京丰台附近
print("\n=== 经过北京丰台附近的路线 ===")
bf = coords.get('北京丰台', [116.295, 39.850])
for name, info in routes.items():
    traj = info['trajectory']
    if not traj:
        continue
    best_d = 999
    for lng, lat in traj:
        dlat = (lat - bf[1]) * 111
        dlng = (lng - bf[0]) * 111 * math.cos(math.radians(bf[1]))
        d = math.sqrt(dlat*dlat + dlng*dlng)
        if d < best_d:
            best_d = d
    if best_d < 10:
        print(f"  {name}: dist={best_d:.1f}km")
