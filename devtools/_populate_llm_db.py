"""Populate LLMFactories and LLM tables from llm_factories.json."""
import sys, os, json, time, logging
sys.path.insert(0, '/ragflow')
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'

from api.db.db_models import LLMFactories, LLM
from common.constants import LLMType

conf_path = '/ragflow/conf/llm_factories.json'
with open(conf_path, 'r') as fp:
    data = json.load(fp)
factory_infos = data['factory_llm_infos']

tag_to_type = {
    'LLM': LLMType.CHAT.value,
    'TEXT EMBEDDING': LLMType.EMBEDDING.value,
    'TEXT RE-RANK': LLMType.RERANK.value,
    'SPEECH2TEXT': LLMType.ASR.value,
    'IMAGE2TEXT': LLMType.VISION.value,
    'TTS': LLMType.TTS.value,
    'MODERATION': LLMType.CHAT.value,
}

now = int(time.time() * 1000)

# Insert factories
count_f = 0
for finfo in factory_infos:
    name = finfo['name']
    if not LLMFactories.select().where(LLMFactories.name == name).count():
        LLMFactories.create(
            name=name,
            logo=finfo.get('logo', ''),
            tags=finfo.get('tags', 'LLM'),
            rank=finfo.get('rank', 0),
            status='1',
            create_time=now, update_time=now,
        )
        count_f += 1
print(f'Factories: {count_f} inserted (total: {LLMFactories.select().count()})')

# Insert LLM models
count_m = 0
for finfo in factory_infos:
    fid = finfo['name']
    for llm_info in finfo.get('llm', []):
        llm_name = llm_info['llm_name']
        model_type_raw = llm_info.get('model_type', 'LLM')
        
        # Handle case where model_type is a list
        if isinstance(model_type_raw, list):
            model_types = model_type_raw
        else:
            model_types = [model_type_raw]
        
        for mt in model_types:
            model_type = tag_to_type.get(mt, LLMType.CHAT.value)
            if not LLM.select().where(
                LLM.llm_name == llm_name,
                LLM.fid == fid,
                LLM.model_type == model_type
            ).count():
                LLM.create(
                    llm_name=llm_name,
                    model_type=model_type,
                    fid=fid,
                    max_tokens=llm_info.get('max_tokens', 4096),
                    tags=mt,
                    is_tools=llm_info.get('is_tools', False),
                    status='1',
                    create_time=now, update_time=now,
                )
                count_m += 1
print(f'LLM models: {count_m} inserted (total: {LLM.select().count()})')

# Summary
print(f'\nSummary:')
for f in LLMFactories.select():
    count = LLM.select().where(LLM.fid == f.name).count()
    if count > 0:
        print(f'  {f.name}: {count} models')
