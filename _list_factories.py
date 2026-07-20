import json

with open("/ragflow/conf/llm_factories.json") as f:
    data = json.load(f)

for factory in data["factory_llm_infos"]:
    print(f"Factory: {factory['name']}")
    for llm in factory.get("llm", [])[:3]:
        print(f"  - {llm.get('llm_name', 'N/A')} ({llm.get('model_type', 'N/A')})")
    if len(factory.get("llm", [])) > 3:
        print(f"  ... and {len(factory['llm']) - 3} more")
    print()
