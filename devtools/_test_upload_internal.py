import requests, json, sys, os

# Suppress noisy logs
os.environ['LITELLM_LOG'] = 'ERROR'
import warnings
warnings.filterwarnings('ignore')

from api.utils.crypt import crypt

# Login
enc = crypt('admin')
s = requests.Session()
r = s.post('http://127.0.0.1:80/api/v1/auth/login', 
           json={'email': 'admin@ragflow.io', 'password': enc})
print(f"Login: {r.json().get('code')} | {r.json().get('message', '')}")
print(f"Cookies: {dict(s.cookies)}")

# Upload
with open('/tmp/test_doc.txt', 'rb') as f:
    r2 = s.post(
        'http://127.0.0.1:80/api/v1/datasets/c8288990072b4f008f6cd56fec031cfa/documents',
        files={'file': ('test_doc.txt', f, 'text/plain')},
        timeout=120
    )
print(f"Upload: code={r2.json().get('code')} msg={r2.json().get('message', '')}")
if r2.json().get('code') == 0:
    data = r2.json().get('data', [])
    if data:
        print(f"Doc ID: {data[0].get('id', 'N/A')}")
