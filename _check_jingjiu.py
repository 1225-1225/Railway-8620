"""检查京九线的各种名称变体"""
import sys
import sqlite3
import re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect(r'd:\PyCharm\Railway-8620\data\pbf\china_output.gpkg')
c = conn.cursor()

# 1. multilinestrings 中所有包含"京九"的名称
print("=== multilinestrings 中含'京九'的名称 ===")
c.execute("SELECT DISTINCT name FROM multilinestrings WHERE name LIKE '%京九%' ORDER BY name")
for r in c.fetchall():
    print(f'  {r[0]}')

# 2. lines 表中所有包含"京九"的名称
print("\n=== lines 表中含'京九'的名称及 railway 类型 ===")
c.execute("SELECT DISTINCT l.name, l.railway, COUNT(*) as cnt FROM lines l WHERE l.name LIKE '%京九%' GROUP BY l.name, l.railway ORDER BY l.name")
for r in c.fetchall():
    print(f'  {r[0]} (railway={r[1]}, {r[2]}条)')

# 3. 检查京九线在 multilinestrings 中的完整 other_tags
print("\n=== 京九线的 other_tags ===")
c.execute("SELECT name, other_tags FROM multilinestrings WHERE name = '京九线'")
for r in c.fetchall():
    print(f'  {r[0]}: {r[1]}')

# 4. 京九线在 lines 表中的 bbox
print("\n=== 京九线(lines)的 bbox ===")
c.execute("""
    SELECT MIN(r.minx), MAX(r.maxx), MIN(r.miny), MAX(r.maxy)
    FROM lines l
    JOIN rtree_lines_geom r ON l.fid = r.id
    WHERE l.name = '京九线' AND l.railway = 'rail'
""")
r = c.fetchone()
if r and r[0]:
    print(f'  lng[{r[0]:.4f}, {r[1]:.4f}], lat[{r[2]:.4f}, {r[3]:.4f}]')

# 5. 检查 lines 表中"京九"相关轨道的名称和区域
print("\n=== lines 表中含'京九'的路线在 rtree 中的首尾坐标 ===")
# 使用 rtree 获取京九线路线的分布范围
c.execute("""
    SELECT l.name, l.railway, r.minx, r.maxx, r.miny, r.maxy
    FROM lines l
    JOIN rtree_lines_geom r ON l.fid = r.id
    WHERE l.name LIKE '%京九%' AND l.railway = 'rail'
    LIMIT 20
""")
for r in c.fetchall():
    print(f'  {r[0]} (railway={r[1]}): x[{r[2]:.2f},{r[3]:.2f}] y[{r[4]:.2f},{r[5]:.2f}]')

# 6. 找北京到衡水沿着京九线有哪些路线
print("\n=== 途径北京丰台站附近的铁路路线 ===")
c.execute("""
    SELECT name FROM multilinestrings
    WHERE other_tags LIKE '%"route"=>"railway"%'
      AND (name LIKE '%京九%' OR name LIKE '%京沪%' OR name LIKE '%京雄%' OR name LIKE '%京广%' OR name LIKE '%丰台%' OR name LIKE '%北京%')
    ORDER BY name
""")
for r in c.fetchall():
    print(f'  {r[0]}')

conn.close()
