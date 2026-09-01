"""Verify get_chunking_config works after Tenant fix."""
import warnings, logging, os
warnings.filterwarnings('ignore')
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'

from api.db.services.document_service import DocumentService

# Test get_chunking_config for a sample document
config = DocumentService.get_chunking_config('112a1518838f11f1890731e84d20a1a3')
if config:
    print('SUCCESS: Config is NOT None!')
    print(f'Keys: {sorted(config.keys())}')
    print(f'parser_config: {config.get("parser_config", "N/A")}')
    print(f'parser_id: {config.get("parser_id", "N/A")}')
    print(f'language: {config.get("language", "N/A")}')
    print(f'embd_id: {config.get("embd_id", "N/A")}')
    print(f'tenant_id: {config.get("tenant_id", "N/A")}')
else:
    print('FAIL: Config is still None!')
