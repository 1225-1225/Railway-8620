import sys
sys.path.insert(0, '/ragflow')
import json

with open('/ragflow/api/db/services/task_service.py', 'r') as f:
    content = f.read()

old = """        doc = docs[0]

        msg = f"\\n{datetime.now().strftime('%H:%M:%S')} Task has been received.\""""

new = """        doc = docs[0]

        # Patch: parse JSON strings from DB
        if isinstance(doc.get("parser_config"), str):
            try:
                doc["parser_config"] = json.loads(doc["parser_config"])
            except Exception:
                doc["parser_config"] = {}
        if isinstance(doc.get("kb_parser_config"), str):
            try:
                doc["kb_parser_config"] = json.loads(doc["kb_parser_config"])
            except Exception:
                doc["kb_parser_config"] = {}

        msg = f"\\n{datetime.now().strftime('%H:%M:%S')} Task has been received.\""""

if old in content:
    content = content.replace(old, new)
    print('Patched get_task successfully')
else:
    print('ERROR: Target not found!')
    for i, line in enumerate(content.split('\n')):
        if 'doc = docs[0]' in line:
            print(f'Found at line {i+1}: {repr(line[:80])}')

with open('/ragflow/api/db/services/task_service.py', 'w') as f:
    f.write(content)

print('Done')
