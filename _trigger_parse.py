"""Temporary script to trigger RAGFlow document parsing."""
import requests
import json
import subprocess
import os

HOST = "http://localhost:9380"
EMAIL = "admin@ragflow.io"
PASS = "admin"
KB_ID = "c8288990072b4f008f6cd56fec031cfa"
CONTAINER = "railway-8620-ragflow-1"


def docker_exec(code: str) -> str:
    full_code = f"""
import warnings, logging, os
warnings.filterwarnings('ignore')
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'
{code}
""".strip()
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "python3", "-c", full_code],
        capture_output=True, text=True, timeout=60,
    )
    out = result.stdout + result.stderr
    skip_words = [
        "pkg_resources", "LiteLLM:", "WARNING:",
        "SyntaxWarning", "UserWarning", "scholarly",
        "can't import", "Connection refused",
    ]
    lines = [l for l in out.splitlines() if not any(w in l for w in skip_words)]
    return "\n".join(lines).strip()


def main():
    # 1. Encrypt password
    print("Encrypting password...")
    enc = docker_exec(f"from api.utils.crypt import crypt; print(crypt('{PASS}'))")
    print(f"  Encrypted length: {len(enc)}")

    # 2. Login
    print("Logging in...")
    s = requests.Session()
    resp = s.post(
        f"{HOST}/api/v1/auth/login",
        json={"email": EMAIL, "password": enc},
        timeout=10,
    )
    print(f"  Login: {resp.json()}")

    # 3. Get all document IDs
    print("Getting document IDs...")
    doc_ids_code = f"""
from api.db.db_models import Document
import json
docs = Document.select(Document.id).where(Document.kb_id == '{KB_ID}')
print(json.dumps([d.id for d in docs]))
"""
    ids_json = docker_exec(doc_ids_code)
    all_ids = json.loads(ids_json)
    print(f"  Total documents: {len(all_ids)}")

    # 4. Parse in batches
    print(f"Starting parse for {len(all_ids)} documents...")
    batch_size = 50
    total_batches = (len(all_ids) + batch_size - 1) // batch_size
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i:i + batch_size]
        batch_num = i // batch_size + 1
        resp = s.post(
            f"{HOST}/api/v1/datasets/{KB_ID}/documents/parse",
            json={"document_ids": batch},
            timeout=120,
        )
        data = resp.json()
        print(f"  Batch {batch_num}/{total_batches}: code={data.get('code')}, {data.get('data', data.get('message', ''))}")

    print("Done! All documents submitted for parsing.")


if __name__ == "__main__":
    main()
