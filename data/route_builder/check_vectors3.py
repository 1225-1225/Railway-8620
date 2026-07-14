"""查看向量库详情"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sqlite3, os

db_path = r'd:\PyCharm\Railway-8620\data\vector_database\chroma.sqlite3'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# collections
c.execute('SELECT id, name, dimension FROM collections')
for rid, name, dim in c.fetchall():
    cnt = c.execute('SELECT COUNT(*) FROM segments WHERE collection=?', [rid]).fetchone()[0]
    print(f"[{name}] dimension={dim}, segments={cnt}")

# 总向量数（从嵌入向量文件推断）
vec_dir = r'd:\PyCharm\Railway-8620\data\vector_database'
for item in os.listdir(vec_dir):
    full = os.path.join(vec_dir, item)
    if os.path.isdir(full):
        for f in ['data_level0.bin', 'length.bin']:
            fp = os.path.join(full, f)
            if os.path.exists(fp):
                sz = os.path.getsize(fp)
                print(f"  {item}/{f}: {sz} bytes")

conn.close()

# 总大小
total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(vec_dir) for f in fs)
print(f"\n总大小: {total/1024/1024:.2f} MB")
print(f"SQLite: {os.path.getsize(db_path)/1024:.1f} KB")
