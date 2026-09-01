"""Read resolved API keys from settings."""
import sys
sys.path.insert(0, 'd:/PyCharm/Railway-8620')
from settings import _SettingsProxy
proxy = _SettingsProxy()
s = proxy._settings
print(f'llm_api_key set: {bool(s.llm_api_key)}')
print(f'llm_api_key first 8: {s.llm_api_key[:8] if s.llm_api_key else "EMPTY"}')
print(f'embedding_api_key set: {bool(s.embedding_api_key)}')
print(f'embedding_api_key first 8: {s.embedding_api_key[:8] if s.embedding_api_key else "EMPTY"}')
print(f'llm_provider: {s.llm_provider}')
print(f'llm_model_name: {s.llm_model_name}')
print(f'llm_base_url: {s.llm_base_url}')
print(f'embedding_provider: {s.embedding_provider}')
print(f'embedding_model_name: {s.embedding_model_name}')
print(f'embedding_base_url: {s.embedding_base_url}')
