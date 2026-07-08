import sqlite3, os

db = r'd:\PyCharm\Railway-8620\chat_history\chat_history_check_pointer'
print(f"DB exists: {os.path.exists(db)}")
print(f"DB size: {os.path.getsize(db) if os.path.exists(db) else 0}")

if os.path.exists(db):
    conn = sqlite3.connect(db)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"Tables: {[t[0] for t in tables]}")
    if tables:
        for t in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
            print(f"  {t[0]}: {cnt} rows")
    conn.close()
