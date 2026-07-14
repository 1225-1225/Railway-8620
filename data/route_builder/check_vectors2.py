"""快速查向量数据量"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sqlite3, os

db_path = r'd:\PyCharm\Railway-8620\data\vector_database\chroma.sqlite3'
conn = sqlite3.connect(db_path)
c = conn.cursor()

tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"表: {len(tables)} 个")

# 关键表
for t in ['segments', 'embeddings', 'embedding_metadata']:
    try:
        cnt = c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f"  {t}: {cnt} 条")
    except:
        pass

# collections
for r in c.execute('SELECT uuid, name FROM collections').fetchall():
    uuid, name = r
    # 这个 collection 的 segments
    try:
        cnt = c.execute('SELECT COUNT(*) FROM segments WHERE collection_id=?', [uuid]).fetchone()[0]
        print(f"  Collection '{name}': {cnt} segments")
    except:
        pass

conn.close()

# 目录大小
vec_dir = r'd:\PyCharm\Railway-8620\data\vector_database'
total = 0
for root, dirs, files in os.walk(vec_dir):
    for f in files:
        total += os.path.getsize(os.path.join(root, f))
print(f"\n向量库总大小: {total/1024:.1f} KB ({total/1024/1024:.2f} MB)")
