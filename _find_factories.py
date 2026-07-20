"""Find LLM factory names in RAGFlow source."""
import os
import re

base = '/ragflow'
factories = set()

for root, dirs, files in os.walk(os.path.join(base, 'common')):
    for fname in files:
        if fname.endswith('.py'):
            try:
                with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Look for factory names
                    matches = re.findall(r"'([^']*OpenAI[^']*)'|\"([^\"]*OpenAI[^\"]*)\"", content)
                    for m in matches:
                        name = m[0] or m[1]
                        if name:
                            factories.add(name)
            except:
                pass

for f in sorted(factories):
    print(f)

print("\n=== Also check specific names ===")
# Check constants file
const_path = '/ragflow/common/constants.py'
if os.path.exists(const_path):
    with open(const_path, 'r') as f:
        content = f.read()
        for line in content.splitlines():
            if 'EMBEDDING' in line or 'Factory' in line or 'factory' in line.lower():
                print(f'  {line.strip()[:120]}')
