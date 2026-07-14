"""检查 Chroma 向量库的数据量"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3, os

db_path = r'd:\PyCharm\Railway-8620\data\vector_database\chroma.sqlite3'
print(f"向量库文件: {os.path.getsize(db_path)/1024:.1f} KB\n")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# collections
c.execute('SELECT id, name FROM collections')
for col in c.fetchall():
    print(f"集合: id={col[0]}, name={col[1]}")

# segments = document chunks
c.execute('SELECT COUNT(*) FROM segments')
seg_cnt = c.fetchone()[0]
print(f"\n文档块(segments)数: {seg_cnt}")

# embeddings count
c.execute('SELECT COUNT(*) FROM embeddings')
emb_cnt = c.fetchone()[0]
print(f"向量(embeddings)数: {emb_cnt}")

# 看看 embedding 维度
c.execute('PRAGMA table_info(embeddings)')
cols = [r[1] for r in c.fetchall()]
print(f"embeddings 列: {cols}")

conn.close()
