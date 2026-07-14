"""诊断京九线 lines 表补充失败原因"""
import sys
import sqlite3
import re
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect(r'd:\PyCharm\Railway-8620\data\pbf\china_output.gpkg')
c = conn.cursor()

# 1. 京九线在 lines 表中的分布
print("=== 京九线 lines 表分布 ===")
c.execute("SELECT railway, COUNT(*) as cnt FROM lines WHERE name = '京九线' GROUP BY railway ORDER BY cnt DESC")
for r in c.fetchall():
    print(f'  railway={r[0]}: {r[1]}条')

# 2. 只取 railway=rail 的分析
c.execute("SELECT MIN(r.miny), MAX(r.maxy), MIN(r.minx), MAX(r.maxx), COUNT(*) FROM lines l JOIN rtree_lines_geom r ON l.fid = r.id WHERE l.name = '京九线' AND l.railway = 'rail'")
r = c.fetchone()
print(f'\n  铁路=rail: lat[{r[0]:.4f}, {r[1]:.4f}], lng[{r[2]:.4f}, {r[3]:.4f}], {r[4]}条')

# 3. 看 north/south 分布
c.execute("""
    SELECT 
        CASE 
            WHEN r.miny < 26 THEN '南段(深圳-赣州)'
            WHEN r.miny < 30 THEN '中段(赣州-阜阳)' 
            WHEN r.miny < 35 THEN '北段(阜阳-衡水)'
            ELSE '京段(衡水-北京)'
        END as zone,
        COUNT(*) as cnt
    FROM lines l
    JOIN rtree_lines_geom r ON l.fid = r.id
    WHERE l.name = '京九线' AND l.railway = 'rail'
    GROUP BY zone
    ORDER BY MIN(r.miny)
""")
print('\n  各区段分布:')
for r in c.fetchall():
    print(f'    {r[0]}: {r[1]}条')

# 4. 检查 multilinestrings 中京九线的上限
c.execute("SELECT fid, name, other_tags FROM multilinestrings WHERE name = '京九线'")
for r in c.fetchall():
    print(f'\n  multilinestrings: fid={r[0]}, name={r[1]}')
    print(f'  other_tags: {r[2]}')

# 5. 看 multilinestrings 的 bbox
c.execute("SELECT r.minx, r.maxx, r.miny, r.maxy FROM rtree_multilinestrings_geom r JOIN multilinestrings m ON r.id = m.fid WHERE m.name = '京九线'")
r = c.fetchone()
if r:
    print(f'  multilinestrings bbox: lng[{r[0]:.4f}, {r[1]:.4f}], lat[{r[2]:.4f}, {r[3]:.4f}]')

conn.close()
