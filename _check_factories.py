"""Check LLM factories config file in RAGFlow."""
import os, json, sys
sys.path.insert(0, '/ragflow')

from common import settings

# Check FACTORY_LLM_INFOS
infos = settings.FACTORY_LLM_INFOS
print(f'FACTORY_LLM_INFOS type: {type(infos)}')
if isinstance(infos, list):
    print(f'Count: {len(infos)}')
    for fact in infos[:3]:
        print(f'  name={fact.get("name", "?")} keys={list(fact.keys())[:10]}')
    # Look for OpenAI-compatible
    for fact in infos:
        name = fact.get('name', '')
        if 'openai' in name.lower() or 'api' in name.lower() or 'compatible' in name.lower():
            print(f'\nFOUND: {name}')
            print(json.dumps(fact, indent=2, ensure_ascii=False)[:800])

# Also check conf directory directly
conf_path = '/ragflow/conf/llm_factories.json'
print(f'\nFile exists: {os.path.exists(conf_path)}')
if os.path.exists(conf_path):
    with open(conf_path, 'r') as f:
        data = json.load(f)
    factories = data.get('factory_llm_infos', [])
    print(f'Total factories in file: {len(factories)}')
    for fact in factories:
        name = fact.get('name', '')
        if 'openai' in name.lower() or 'api' in name.lower():
            print(f'  {name} - types: {fact.get("model_types", fact.get("tags", "?"))}')
