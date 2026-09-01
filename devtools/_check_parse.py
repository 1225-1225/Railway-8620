"""Check document parse progress."""
import warnings, logging, os
warnings.filterwarnings('ignore')
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'

from api.db.db_models import Document

kb_id = 'c8288990072b4f008f6cd56fec031cfa'

total = Document.select().where(Document.kb_id == kb_id).count()
print(f'Total docs: {total}')

labels = {'0': 'UNSTART', '1': 'RUNNING', '2': 'CANCEL', '3': 'DONE', '4': 'FAIL'}

for run_val in ['0', '1', '2', '3', '4']:
    count = Document.select().where(
        Document.kb_id == kb_id,
        Document.run == run_val
    ).count()
    print(f'  run={run_val} ({labels.get(run_val, "?")}): {count}')

print()
print('Sample running docs:')
docs = Document.select().where(
    Document.kb_id == kb_id,
    Document.run == '1'
).limit(5)
for d in docs:
    print(f'  {d.name[:50]} progress={d.progress} msg={str(d.progress_msg)[:60]}')

print()
print('Sample done docs:')
docs = Document.select().where(
    Document.kb_id == kb_id,
    Document.run == '3'
).limit(5)
for d in docs:
    print(f'  {d.name[:50]} status={d.status}')

print()
print('Sample failed docs:')
docs = Document.select().where(
    Document.kb_id == kb_id,
    Document.run == '4'
).limit(5)
for d in docs:
    print(f'  {d.name[:50]} msg={str(d.progress_msg)[:80]}')
