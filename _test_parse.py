"""验证 _parse_messages_from_checkpoint 修复"""
import sys, os, sqlite3, msgpack

# 直接测试解析逻辑
db = r'd:\PyCharm\Railway-8620\chat_history\chat_history_check_pointer'
conn = sqlite3.connect(db)

# 获取一个有消息的 checkpoint
row = conn.execute("SELECT thread_id, checkpoint FROM checkpoints ORDER BY rowid DESC LIMIT 1").fetchone()
conn.close()

tid, blob = row

# 复制 api.py 的修复后逻辑
def parse(blob):
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b'channel_values', data.get('channel_values', {}))
        if isinstance(cv, bytes):
            cv = msgpack.unpackb(cv)
        msgs = cv.get(b'messages', cv.get('messages', []))
        result = []
        for msg in msgs:
            if hasattr(msg, 'code') and msg.code == 5 and hasattr(msg, 'data'):
                inner = msgpack.unpackb(msg.data)
                if isinstance(inner, (list, tuple)) and len(inner) >= 3:
                    class_name = inner[1]
                    kw = inner[2]
                    if isinstance(kw, bytes):
                        kw = msgpack.unpackb(kw)
                    if isinstance(kw, dict):
                        content = kw.get('content', '')
                        if isinstance(content, bytes):
                            content = content.decode()
                        role = 'user' if class_name == 'HumanMessage' else ('assistant' if class_name == 'AIMessage' else '')
                        if role and content:
                            result.append({'role': role, 'content': content[:50] + '...' if len(str(content)) > 50 else content})
        return result
    except Exception as e:
        return [{'role': 'error', 'content': str(e)}]

print(f"thread: {tid[:40]}...")
msgs = parse(blob)
print(f"parsed {len(msgs)} messages:")
for m in msgs:
    print(f"  [{m['role']}] {m['content']}")
