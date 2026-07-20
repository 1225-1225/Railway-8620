import sys
sys.path.insert(0, '/ragflow')

with open('/ragflow/rag/llm/embedding_model.py', 'r') as f:
    content = f.read()

# Find OpenAI_APIEmbed class and add encode override
old = """class OpenAI_APIEmbed(OpenAIEmbed):
    _FACTORY_NAME = ["VLLM", "OpenAI-API-Compatible"]

    def __init__(self, key, model_name, base_url):
        if not base_url:
            raise ValueError("url cannot be None")
        base_url = ensure_v1(base_url)
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model_name = model_name.split("___")[0]"""

new = """class OpenAI_APIEmbed(OpenAIEmbed):
    _FACTORY_NAME = ["VLLM", "OpenAI-API-Compatible"]

    def __init__(self, key, model_name, base_url):
        if not base_url:
            raise ValueError("url cannot be None")
        base_url = ensure_v1(base_url)
        self.client = OpenAI(api_key=key, base_url=base_url)
        self.model_name = model_name.split("___")[0]

    def encode(self, texts: list):
        # DashScope text-embedding-v4 limits batch size to 10
        return self._batched_encode(texts, self._call, batch_size=10, truncate_to=8191)

    def encode_queries(self, text):
        vectors, token_count = self._batched_encode([text], self._call, batch_size=10, truncate_to=8191)
        return vectors[0], token_count"""

if old in content:
    content = content.replace(old, new)
    print('Patched OpenAI_APIEmbed successfully')
else:
    print('ERROR: Target not found!')
    # Debug
    for i, line in enumerate(content.split('\n')):
        if 'class OpenAI_APIEmbed' in line:
            for j in range(i, min(i+15, len(content.split('\n')))):
                print(f'  {content.split(chr(10))[j]}')
            break

with open('/ragflow/rag/llm/embedding_model.py', 'w') as f:
    f.write(content)

print('Done')
