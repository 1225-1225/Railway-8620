"""Initialize LLM factories and models from llm_factories.json
and set up embedding model for the admin tenant.
"""
import sys, os, json, time, logging
sys.path.insert(0, '/ragflow')

# Suppress noisy logs
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'

from api.db.db_models import LLMFactories, LLM, TenantLLM, Tenant, Database
from common.constants import LLMType

# ── 1. Load factory data from JSON ──────────────────────────────────────
conf_path = '/ragflow/conf/llm_factories.json'
with open(conf_path, 'r') as f:
    data = json.load(f)
factory_infos = data['factory_llm_infos']

print(f'Found {len(factory_infos)} factories in config')

# ── 2. Insert LLMFactories ──────────────────────────────────────────────
now_time = int(time.time() * 1000)
inserted_factories = 0
for finfo in factory_infos:
    name = finfo['name']
    exists = LLMFactories.select().where(LLMFactories.name == name).count()
    if exists:
        continue
    LLMFactories.create(
        name=name,
        logo=finfo.get('logo', ''),
        tags=finfo.get('tags', 'LLM'),
        rank=finfo.get('rank', 0),
        status='1',
        create_time=now_time,
        update_time=now_time,
    )
    inserted_factories += 1

print(f'Inserted {inserted_factories} factories')

# ── 3. Insert LLM models ────────────────────────────────────────────────
# Model types from tags
tag_to_type = {
    'LLM': LLMType.CHAT.value,
    'TEXT EMBEDDING': LLMType.EMBEDDING.value,
    'TEXT RE-RANK': LLMType.RERANK.value,
    'SPEECH2TEXT': LLMType.ASR.value,
    'IMAGE2TEXT': LLMType.VISION.value,
    'TTS': LLMType.TTS.value,
    'MODERATION': LLMType.CHAT.value,
}

inserted_llms = 0
for finfo in factory_infos:
    fid = finfo['name']
    for llm_info in finfo.get('llm', []):
        llm_name = llm_info['llm_name']
        model_type = tag_to_type.get(llm_info.get('model_type', 'LLM'), LLMType.CHAT.value)
        exists = LLM.select().where(
            LLM.llm_name == llm_name,
            LLM.fid == fid,
            LLM.model_type == model_type
        ).count()
        if exists:
            continue
        LLM.create(
            llm_name=llm_name,
            model_type=model_type,
            fid=fid,
            max_tokens=llm_info.get('max_tokens', 4096),
            tags=llm_info.get('model_type', 'LLM'),
            is_tools=llm_info.get('is_tools', False),
            status='1',
            create_time=now_time,
            update_time=now_time,
        )
        inserted_llms += 1

print(f'Inserted {inserted_llms} LLM models')

# ── 4. Check OpenAI-API-Compatible factory exists ────────────────────────
factory_name = 'OpenAI-API-Compatible'
fac = LLMFactories.select().where(LLMFactories.name == factory_name).first()
if fac:
    print(f'Factory {factory_name} exists')
else:
    print(f'ERROR: Factory {factory_name} NOT found!')
    sys.exit(1)

# ── 5. Add TenantLLM for embedding ──────────────────────────────────────
tenant_id = '1a422050838a11f19502ff4c5e1d5ab0'
model_name = 'text-embedding-v4'

# Check existing
existing = TenantLLM.select().where(
    TenantLLM.tenant_id == tenant_id,
    TenantLLM.llm_factory == factory_name,
    TenantLLM.model_type == LLMType.EMBEDDING.value,
).count()

if existing:
    print(f'TenantLLM embedding already exists, updating...')
    TenantLLM.update(
        llm_name=model_name,
        api_base='https://dashscope.aliyuncs.com/compatible-mode/v1',
        api_key='DASHSCOPE_API_KEY',
        update_time=now_time,
    ).where(
        TenantLLM.tenant_id == tenant_id,
        TenantLLM.llm_factory == factory_name,
        TenantLLM.model_type == LLMType.EMBEDDING.value,
    ).execute()
else:
    TenantLLM.create(
        tenant_id=tenant_id,
        llm_factory=factory_name,
        model_type=LLMType.EMBEDDING.value,
        llm_name=model_name,
        api_key='DASHSCOPE_API_KEY',
        api_base='https://dashscope.aliyuncs.com/compatible-mode/v1',
        max_tokens=4096,
        used_tokens=0,
        status='1',
        create_time=now_time,
        update_time=now_time,
    )
print(f'TenantLLM embedding set: {model_name}')

# ── 6. Update Tenant.embd_id ────────────────────────────────────────────
# The tenant needs embd_id set to the model reference
tenant = Tenant.select().where(Tenant.id == tenant_id).first()
if tenant:
    # Format: model_name@factory_name
    Tenant.update(embd_id=f'{model_name}@{factory_name}').where(Tenant.id == tenant_id).execute()
    print(f'Tenant.embd_id updated to: {model_name}@{factory_name}')
else:
    print('ERROR: Tenant not found!')

# ── 7. Verify ───────────────────────────────────────────────────────────
print(f'\nVerification:')
print(f'LLMFactories: {LLMFactories.select().count()}')
print(f'LLM: {LLM.select().count()}')
print(f'TenantLLM: {TenantLLM.select().count()}')

from api.db.joint_services.tenant_model_service import get_tenant_default_model_by_type
try:
    config = get_tenant_default_model_by_type(tenant_id, LLMType.EMBEDDING)
    print(f'Embedding config resolved: {json.dumps({k: v for k, v in config.items() if k != \"api_key\"}, indent=2)}')
    print('SUCCESS: Embedding model is configured!')
except Exception as e:
    print(f'FAIL: {e}')
