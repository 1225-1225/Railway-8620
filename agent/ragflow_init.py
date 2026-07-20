"""
RAGFlow 自动初始化脚本 (v0.26.4 适配版)

首次部署时运行一次，自动完成：
1. 等待 RAGFlow 服务就绪
2. 打入容器源码补丁（DashScope batch_size 等上游 bug）
3. 在容器内创建超级管理员（如不存在）
4. 在容器内直接创建 API Token
5. 密码加密 + 登录获取 Cookie
6. 注册嵌入模型 & LLM（.env 凭证 → RAGFlow 数据库）
7. 通过 REST API 创建知识库
8. 将 data/cleaned_txts/ 中的文档全部上传
9. 将凭证写入 .env
10. 标记完成

用法:
    python agent/ragflow_init.py

前置条件:
    - Docker 容器已在 docker-compose.ragflow.yml 中定义并启动
    - .env 中配置了 llm_api_key / embedding_api_key（或对应的环境变量名）
"""

import os
import sys
import time
import subprocess

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
from settings import settings as config_data

# ===== 配置 =====
RAGFLOW_HOST = config_data.ragflow_host
ADMIN_EMAIL = "admin@ragflow.io"
ADMIN_PASS = "admin"
DATASET_NAME = u"铁路知识库"
ENV_PATH = os.path.join(_project_root, ".env")
MARKER_FILE = os.path.join(_project_root, ".ragflow_initialized")
TXT_DIR = config_data.data_path
CONTAINER = "railway-8620-ragflow-1"
RETRY_INTERVAL = 5
MAX_RETRIES = 60

# RAGFlow v0.26.4 上游 Bug 修复（容器源码热补丁）
# 这些补丁在 docker compose down/up 后需要重新打入，因此集成在初始化流程中
RAGFLOW_PATCHES = {
    # DashScope text-embedding-v4 限制 batch_size ≤ 10，但 RAGFlow 写死 16
    "embedding_model.py": {
        "path": "/ragflow/rag/llm/embedding_model.py",
        "desc": "OpenAI_APIEmbed batch_size 16→10",
        # 精确替换：只改 OpenAI_APIEmbed 子类中的 batch_size=16
        "old": """class OpenAI_APIEmbed(OpenAIEmbed):
    _FACTORY_NAME = ["VLLM", "OpenAI-API-Compatible"]

    def encode(self, texts: list):
        return self._batched_encode(texts, self._call, batch_size=16, truncate_to=8191)

    def encode_queries(self, text):
        vectors, token_count = self._batched_encode([text], self._call, batch_size=16, truncate_to=8191)
        return vectors[0], token_count""",
        "new": """class OpenAI_APIEmbed(OpenAIEmbed):
    _FACTORY_NAME = ["VLLM", "OpenAI-API-Compatible"]

    def encode(self, texts: list):
        # DashScope text-embedding-v4 limits batch size to 10
        return self._batched_encode(texts, self._call, batch_size=10, truncate_to=8191)

    def encode_queries(self, text):
        vectors, token_count = self._batched_encode([text], self._call, batch_size=10, truncate_to=8191)
        return vectors[0], token_count""",
    },
    # parser_config 可能是 JSON 字符串而非 dict 的兼容处理
    "task_context.py": {
        "path": "/ragflow/rag/svr/task_executor_refactor/task_context.py",
        "desc": "parser_config str→dict 容错",
        "old": """    @property
    def parser_config(self) -> dict:
        return self._task.get("parser_config", {})""",
        "new": """    @property
    def parser_config(self) -> dict:
        val = self._task.get("parser_config", {})
        if isinstance(val, str):
            import json as _json
            try:
                return _json.loads(val)
            except Exception:
                return {}
        return val or {}""",
    },
}


# ======================================================================
# 工具函数
# ======================================================================

def log(msg: str):
    print(f"[RAGFlow Init] {msg}")


def wait_for_ragflow() -> bool:
    log(f"等待 RAGFlow 就绪 ({RAGFLOW_HOST}) ...")
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(
                f"{RAGFLOW_HOST}/api/v1/datasets", timeout=5
            )
            if resp.status_code < 500:
                log("RAGFlow 已就绪 ✅")
                return True
        except Exception:
            pass
        log(f"  等待中 ({i + 1}/{MAX_RETRIES}) ...")
        time.sleep(RETRY_INTERVAL)
    log("RAGFlow 未能就绪 ❌")
    return False


def docker_exec(code: str) -> str:
    """在 RAGFlow 容器内执行 Python 代码并返回 stdout（过滤日志噪音）"""
    full_code = f"""
import warnings, logging, os
warnings.filterwarnings('ignore')
logging.getLogger().setLevel(logging.ERROR)
os.environ['LITELLM_LOG'] = 'ERROR'
{code}
""".strip()
    cmd = ["docker", "exec", CONTAINER, "python3", "-c", full_code]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # 过滤掉已知噪音行
        lines = []
        for line in result.stdout.splitlines() + result.stderr.splitlines():
            if any(skip in line for skip in [
                "pkg_resources", "LiteLLM:", "WARNING:",
                "SyntaxWarning", "UserWarning", "scholarly",
                "can't import", "Connection refused",
            ]):
                continue
            lines.append(line)
        out = "\n".join(lines).strip()
        if result.returncode != 0 and out:
            log(f"  [docker] {out[-200:]}")
        return out
    except Exception as e:
        log(f"  Docker exec 异常: {e}")
        return ""


def docker_exec_raw(code: str) -> subprocess.CompletedProcess:
    """执行容器命令，不过滤输出，用于需要精确判断返回码的场景"""
    cmd = ["docker", "exec", CONTAINER, "python3", "-c", code]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def apply_container_patches() -> bool:
    """给 RAGFlow 容器打入运行时补丁（上游 bug workaround）。

    返回 True 表示所有补丁已就绪（可能已打过，可能刚打好）。
    """
    log("检查/打入容器源码补丁 ...")
    all_ok = True

    for key, cfg in RAGFLOW_PATCHES.items():
        # 先检查是否需要打补丁
        check_code = f"""
with open('{cfg["path"]}', 'r') as f:
    content = f.read()
print('PATCHED' if '''{cfg["new"]}''' in content else 'NEEDS_PATCH')
"""
        result = docker_exec_raw(check_code)
        status = result.stdout.strip()

        if "PATCHED" in status:
            continue  # 已经打过了

        # 需要打补丁：用 Python 做精确替换
        old = cfg["old"]
        new = cfg["new"]
        patch_code = f"""
path = '{cfg["path"]}'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = {repr(old)}
new = {repr(new)}

if old not in content:
    print('MISSING: old string not found in file')
elif new in content:
    print('ALREADY_PATCHED')
else:
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('PATCHED')
"""
        result = docker_exec_raw(patch_code)
        out = result.stdout.strip()
        if "PATCHED" in out:
            log(f"  ✅ {cfg['desc']}")
        else:
            log(f"  ⚠️ {cfg['desc']}: {out}")
            if "MISSING" not in out:
                all_ok = False

    if any("PATCHED" in docker_exec_raw(
        f"""with open('{cfg["path"]}', 'r') as f: content = f.read(); print('PATCHED' if '''{cfg["new"]}''' in content else 'NEEDS_PATCH')"""
    ).stdout for cfg in RAGFLOW_PATCHES.values()):
        # 有补丁被打入，清除 pyc 缓存并重启
        docker_exec_raw(
            "import os, glob; [os.remove(f) for f in glob.glob('/ragflow/**/*.pyc', recursive=True)]; "
            "[os.rmdir(d) for d in glob.glob('/ragflow/**/__pycache__', recursive=True) if os.path.isdir(d)]"
        )
        log("  已打入新补丁，重启容器使其生效 ...")
        subprocess.run(["docker", "restart", CONTAINER], capture_output=True, timeout=30)
        time.sleep(15)  # 等容器完全启动

    return all_ok


def encrypt_password(password: str) -> str:
    code = f"""from api.utils.crypt import crypt; print(crypt('{password}'))"""
    return docker_exec(code)


def login_session() -> requests.Session | None:
    log("登录 RAGFlow ...")
    enc = encrypt_password(ADMIN_PASS)
    if not enc or len(enc) < 50:
        log(f"  密码加密失败")
        return None

    s = requests.Session()
    try:
        resp = s.post(
            f"{RAGFLOW_HOST}/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": enc},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            log(f"  登录成功: {data.get('message', 'OK')}")
            return s
        log(f"  登录失败: {data.get('message', resp.text[:100])}")
    except Exception as e:
        log(f"  登录异常: {e}")
    return None


def ensure_superuser() -> bool:
    log("检查/创建管理员账号 ...")
    code = """
from api.db.init_data import init_superuser
from api.db.services.user_service import UserService
u = UserService.query(email='admin@ragflow.io')
if u:
    print('EXISTS:' + u[0].id)
else:
    init_superuser()
    v = UserService.query(email='admin@ragflow.io')
    print('CREATED:' + v[0].id if v else 'FAILED')
"""
    out = docker_exec(code)
    ok = "EXISTS" in out or "CREATED" in out
    log(f"  {'✅' if ok else '❌'} {out[:100]}")
    return ok


def create_api_token() -> str | None:
    log("创建 API Token ...")
    code = """
import uuid
from api.db.db_models import APIToken
from api.db.services.user_service import UserService
u = UserService.query(email='admin@ragflow.io')
if not u: print('ERR_NO_USER'); exit()
tid = u[0].id
tok = APIToken.select().where(APIToken.tenant_id == tid, APIToken.source == 'agent').first()
if tok:
    print('TOKEN:' + tok.token)
else:
    t = 'rag_' + uuid.uuid4().hex
    APIToken.create(tenant_id=tid, token=t, source='agent')
    print('TOKEN:' + t)
"""
    out = docker_exec(code)
    if out.startswith("TOKEN:"):
        token = out[6:]
        log(f"  ✅ {token[:20]}...")
        return token
    log(f"  ❌ {out[:100]}")
    return None


def configure_models() -> bool:
    """在 RAGFlow 中注册嵌入模型和 LLM 模型（从 .env 读取凭证）。

    RAGFlow v0.26.4 模型管理是三层结构：
      TenantModelProvider → TenantModelInstance → TenantModel
    光有 .env 不够，必须在数据库里注册才能让 task executor 找到模型。
    """
    log("配置嵌入模型和 LLM ...")

    code = f"""
import uuid, json
from api.db.db_models import (
    TenantModelProvider, TenantModelInstance, TenantModel, Tenant
)
from api.db.services.user_service import UserService

u = UserService.query(email='admin@ragflow.io')
if not u: print('ERR_NO_USER'); exit()
tid = u[0].id

# ---- Provider ----
prov_name = "OpenAI-API-Compatible"
prov = TenantModelProvider.select().where(
    TenantModelProvider.tenant_id == tid,
    TenantModelProvider.provider_name == prov_name,
).first()
if prov:
    prov_id = prov.id
    print(f'PROVIDER_EXISTS:{{prov_id}}')
else:
    prov_id = uuid.uuid4().hex
    TenantModelProvider.insert(
        id=prov_id, tenant_id=tid, provider_name=prov_name,
    ).execute()
    print(f'PROVIDER_CREATED:{{prov_id}}')

# ---- Instance (embedding, DashScope) ----
emb_instance_name = "dashscope"
emb_extra = json.dumps({{"base_url": "{config_data.embedding_base_url}"}})
emb_inst = TenantModelInstance.select().where(
    TenantModelInstance.provider_id == prov_id,
    TenantModelInstance.instance_name == emb_instance_name,
).first()
if emb_inst:
    emb_inst_id = emb_inst.id
    print(f'EMB_INST_EXISTS:{{emb_inst_id}}')
else:
    emb_inst_id = uuid.uuid4().hex
    TenantModelInstance.insert(
        id=emb_inst_id,
        instance_name=emb_instance_name,
        provider_id=prov_id,
        api_key="{config_data.embedding_api_key}",
        status="active",
        extra=emb_extra,
    ).execute()
    print(f'EMB_INST_CREATED:{{emb_inst_id}}')

# ---- Instance (LLM, DeepSeek) ----
llm_instance_name = "deepseek"
llm_extra = json.dumps({{"base_url": "{config_data.llm_base_url}"}})
llm_inst = TenantModelInstance.select().where(
    TenantModelInstance.provider_id == prov_id,
    TenantModelInstance.instance_name == llm_instance_name,
).first()
if llm_inst:
    llm_inst_id = llm_inst.id
    print(f'LLM_INST_EXISTS:{{llm_inst_id}}')
else:
    llm_inst_id = uuid.uuid4().hex
    TenantModelInstance.insert(
        id=llm_inst_id,
        instance_name=llm_instance_name,
        provider_id=prov_id,
        api_key="{config_data.llm_api_key}",
        status="active",
        extra=llm_extra,
    ).execute()
    print(f'LLM_INST_CREATED:{{llm_inst_id}}')

# ---- Embedding model ----
emb_model = TenantModel.select().where(
    TenantModel.provider_id == prov_id,
    TenantModel.instance_id == emb_inst_id,
    TenantModel.model_name == "{config_data.embedding_model_name}",
).first()
if emb_model:
    emb_model_id = emb_model.id
    print(f'EMB_MODEL_EXISTS:{{emb_model_id}}')
else:
    emb_model_id = uuid.uuid4().hex
    TenantModel.insert(
        id=emb_model_id,
        model_name="{config_data.embedding_model_name}",
        provider_id=prov_id,
        instance_id=emb_inst_id,
        model_type=2,  # LLMType.EMBEDDING
        status="active",
        extra=json.dumps({{"max_tokens": 8192}}),
    ).execute()
    print(f'EMB_MODEL_CREATED:{{emb_model_id}}')

# ---- LLM model ----
chat_model = TenantModel.select().where(
    TenantModel.provider_id == prov_id,
    TenantModel.instance_id == llm_inst_id,
    TenantModel.model_name == "{config_data.llm_model_name}",
).first()
if chat_model:
    chat_model_id = chat_model.id
    print(f'CHAT_MODEL_EXISTS:{{chat_model_id}}')
else:
    chat_model_id = uuid.uuid4().hex
    TenantModel.insert(
        id=chat_model_id,
        model_name="{config_data.llm_model_name}",
        provider_id=prov_id,
        instance_id=llm_inst_id,
        model_type=1,  # LLMType.CHAT
        status="active",
        extra=json.dumps({{"max_tokens": 65536}}),
    ).execute()
    print(f'CHAT_MODEL_CREATED:{{chat_model_id}}')

# ---- 写入 Tenant 默认模型引用 ----
embd_ref = "{config_data.embedding_model_name}@{emb_instance_name}@{prov_name}"
llm_ref = "{config_data.llm_model_name}@{llm_instance_name}@{prov_name}"
Tenant.update(embd_id=embd_ref, llm_id=llm_ref).where(Tenant.id == tid).execute()
print(f'TENANT_UPDATED: embd={{embd_ref}} llm={{llm_ref}}')
"""
    out = docker_exec(code)
    ok = "TENANT_UPDATED" in out
    log(f"  {'✅' if ok else '❌'} {out[:200]}")
    return ok


def get_existing_dataset_id() -> str | None:
    """检查知识库是否已存在，返回其 ID"""
    code = f"""
from api.db.services.user_service import UserService
from api.db.db_models import Knowledgebase
u = UserService.query(email='admin@ragflow.io')
if not u: print('ERR_NO_USER'); exit()
tid = u[0].id
kb = Knowledgebase.select().where(
    Knowledgebase.tenant_id == tid,
    Knowledgebase.name == "{DATASET_NAME}"
).first()
if kb:
    print('KB:' + kb.id)
else:
    print('KB_NOT_FOUND')
"""
    out = docker_exec(code)
    if out.startswith("KB:"):
        return out[3:]
    return None


def create_dataset(session: requests.Session) -> str | None:
    log(f"创建知识库 '{DATASET_NAME}' ...")
    try:
        resp = session.post(
            f"{RAGFLOW_HOST}/api/v1/datasets",
            json={"name": DATASET_NAME},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0:
            ds = data.get("data", {})
            ds_id = ds.get("id", "") or ds.get("dataset_id", "")
            if ds_id:
                log(f"  ✅ {ds_id}")
                return ds_id
        log(f"  响应 (code={data.get('code')}): {resp.text[:200]}")
    except Exception as e:
        log(f"  异常: {e}")
    return None


def create_dataset_fallback() -> str | None:
    """先检查是否存在，不存在则容器内创建"""
    existing = get_existing_dataset_id()
    if existing:
        log(f"  知识库已存在，复用: {existing}")
        return existing

    log(f"容器内创建知识库 '{DATASET_NAME}' ...")
    code = f"""
import uuid, json
from api.db.services.user_service import UserService
from api.db.db_models import Knowledgebase
u = UserService.query(email='admin@ragflow.io')
if not u: print('ERR_NO_USER'); exit()
tid = u[0].id
ds_id = uuid.uuid4().hex
Knowledgebase.insert(
    id=ds_id,
    name="{DATASET_NAME}",
    tenant_id=tid,
    parser_id='naive',
    parser_config=json.dumps({{}}),
    permission='me',
    created_by=tid,
).execute()
print('DS:' + ds_id)
"""
    out = docker_exec(code)
    if out.startswith("DS:"):
        ds_id = out[3:]
        log(f"  ✅ {ds_id}")
        return ds_id
    log(f"  ❌ {out[:100]}")
    return None


def upload_documents(session: requests.Session, ds_id: str):
    if not TXT_DIR or not os.path.isdir(TXT_DIR):
        log(f"文档目录不存在: {TXT_DIR}，跳过上传")
        return

    txt_files = sorted(f for f in os.listdir(TXT_DIR) if f.endswith(".txt"))
    if not txt_files:
        log("没有找到 .txt 文档，跳过上传")
        return

    log(f"找到 {len(txt_files)} 个文档，开始上传...")
    url = f"{RAGFLOW_HOST}/api/v1/datasets/{ds_id}/documents"
    ok = 0
    ng = 0

    for i, fname in enumerate(txt_files):
        fpath = os.path.join(TXT_DIR, fname)
        try:
            with open(fpath, "rb") as f:
                resp = session.post(
                    url,
                    files={"file": (fname, f, "text/plain")},
                    timeout=120,
                )
                data = resp.json()
                if data.get("code") == 0:
                    ok += 1
                else:
                    ng += 1
                    if ng <= 3:
                        log(f"  ❌ {fname}: {data.get('message', resp.text[:80])}")
        except Exception as e:
            ng += 1
            if ng <= 3:
                log(f"  ❌ {fname}: {e}")
        if (i + 1) % 30 == 0:
            log(f"  进度: {i + 1}/{len(txt_files)} (成功 {ok})")

    log(f"上传完成: 成功 {ok}, 失败 {ng}")


def write_env(updates: dict):
    lines = []
    updated = set()
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if "=" in s and not s.startswith("#"):
                    k = s.split("=", 1)[0].strip()
                    if k in updates:
                        lines.append(f'{k}="{updates[k]}"\n')
                        updated.add(k)
                        continue
                lines.append(line)

    for k, v in updates.items():
        if k not in updated:
            lines.append(f'{k}="{v}"\n')
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)
    log(".env 已更新 ✅")


# ======================================================================
# 主流程
# ======================================================================

def main():
    log("=" * 50)
    log("RAGFlow v0.26.4 自动化初始化")
    log("=" * 50)

    # 已初始化检查
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if "=" in s and not s.startswith("#"):
                    k, _, v = s.partition("=")
                    env[k.strip()] = v.strip().strip("\"'")

    if env.get("ragflow_api_key") and env.get("ragflow_dataset_id"):
        if os.path.exists(MARKER_FILE):
            log("已初始化，跳过")
            return
        log("凭证已存在但标记缺失，重新初始化...")

    # 1. 等待
    if not wait_for_ragflow():
        sys.exit(1)

    # 2. 打入容器补丁（上游 bug workaround：DashScope batch_size 等）
    apply_container_patches()

    # 3. 管理员
    ensure_superuser()

    # 4. API Token
    api_key = create_api_token()
    if not api_key:
        log("API Token 创建失败 ❌")
        sys.exit(1)

    # 5. 登录
    session = login_session()
    if not session:
        log("登录失败 ❌")
        sys.exit(1)

    # 6. 注册嵌入模型 & LLM（把 .env 凭证写入 RAGFlow 数据库）
    configure_models()

    # 7. 知识库
    ds_id = create_dataset(session)
    if not ds_id:
        ds_id = create_dataset_fallback()
    if not ds_id:
        log("知识库创建失败 ❌")
        sys.exit(1)

    # 8. 上传文档
    upload_documents(session, ds_id)

    # 9. 写入 .env
    write_env({"ragflow_api_key": api_key, "ragflow_dataset_id": ds_id})

    # 10. 标记
    with open(MARKER_FILE, "w") as f:
        f.write(f"initialized_at={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"dataset_id={ds_id}\n")

    log("=" * 50)
    log("🎉 RAGFlow 初始化完成！")
    log(f"   知识库: {DATASET_NAME}")
    log(f"   dataset_id: {ds_id}")
    log(f"   api_key: {api_key[:30]}...")
    log("=" * 50)


if __name__ == "__main__":
    main()
