# 🏗️ Railway-8620 项目构建全记录

> **用途**：从零复刻整个项目的施工手册。按本文档顺序阅读，可理解每一行代码为什么存在、怎么写出来的。
> **阅读方式**：先读「第 0 章 总览」建立全局观，再按施工阶段顺序复习。每章末尾有「面试考点」。
> **配套文档**：架构图见 `docs/architecture.md`，面试速查见 `docs/interview-prep.md`。

---

## 第 0 章 · 项目总览

### 0.1 一句话定位

基于 **LangGraph Agent + RAGFlow 向量检索 + FastAPI + Vue 3** 的中国铁路知识智能问答系统：流式对话、多轮记忆、车次查询、交互式路线地图、多用户独立会话。

### 0.2 技术栈全景

| 层         | 技术                                                    | 版本                  | 作用                              |
| ---------- | ------------------------------------------------------- | --------------------- | --------------------------------- |
| Agent 框架 | LangChain / LangGraph                                   | 1.3 / 1.2             | ReAct 循环、工具调用、状态持久化  |
| 向量检索   | RAGFlow（REST 对接）                                    | v0.26.4               | 237 篇文档的解析/分块/向量化/检索 |
| LLM        | 火山方舟 deepseek-v4-flash（OpenAI 兼容）               | -                     | 推理引擎，可换 DeepSeek/Anthropic |
| Embedding  | 阿里百炼 text-embedding-v4                              | -                     | 文档向量化（RAGFlow 内部使用）    |
| 后端       | FastAPI / SQLAlchemy / python-jose / argon2-cffi        | 0.137 / 2.0           | API、ORM、JWT、密码哈希           |
| 前端       | Vue 3 / TypeScript / Pinia / Vue Router / Vite          | 3.5 / 5.9 / 3 / 5 / 7 | SPA、状态、路由、构建             |
| 地图       | Folium（后端生成 HTML）+ Leaflet（iframe 内渲染）       | 0.20                  | 交互式路线图                      |
| 存储       | SQLite ×3（用户库 / checkpointer / session_meta 同库） | -                     | 零运维持久化                      |
| 部署       | Docker Compose / Nginx / GitHub Actions                 | -                     | 容器化、反代、CI                  |

### 0.3 目录结构（带职责注释）

```
Railway-8620/
├── settings.py                  # 全局配置：pydantic-settings + 代理类热更新
├── backend/                     # FastAPI 层
│   ├── api.py                   # 全部路由：聊天/流式/会话管理 + Agent 生命周期
│   ├── auth.py                  # JWT 签发/验证、argon2 密码、OAuth2 依赖
│   ├── database.py              # SQLAlchemy 引擎 + User 模型
│   └── schemas.py               # 请求/响应 Pydantic 模型
├── agent/                       # Agent 核心
│   ├── agent.py                 # AgentService：create_agent + SqliteSaver
│   ├── llm.py                   # LLM 工厂（openai/anthropic 双供应商）
│   ├── tools.py                 # 工具注册 + 日志装饰器 + RAGFlow 单例
│   ├── railway_tools.py         # 车次查询两件套（纯 JSON 检索）
│   ├── route_map_generator.py   # Folium 地图生成器
│   ├── ragflow_client.py        # RAGFlow REST 客户端封装
│   ├── ragflow_init.py          # RAGFlow 自动初始化 + 容器补丁
│   ├── ragflow_migrate.py       # 批量上传文档
│   ├── checkpoint_parser.py     # msgpack 二进制反解（历史会话）
│   └── chat_history.py          # JSON 文件存储（备用实现，未接入主流程）
├── frontend/src/
│   ├── main.ts                  # 入口：挂载 Pinia + Router
│   ├── App.vue                  # 根组件：页面过渡 + 30s 令牌巡检
│   ├── router/index.ts          # 路由表 + 守卫
│   ├── stores/auth.ts           # 认证状态 + JWT 过期解析
│   ├── services/api.ts          # Axios 实例 + 双拦截器
│   ├── views/                   # Login / Register / Chat(流式) / ChatLegacy
│   └── components/HistorySidebar.vue  # 会话侧边栏（重命名/删除）
├── data/
│   ├── cleaned_txts/            # 237 篇清洗后的知识文档（RAG 语料）
│   ├── train_details.json       # 9547 车次完整时刻表
│   ├── train_stations.json      # 9547 车次-站点映射
│   ├── station_coords.json      # 车站经纬度
│   └── maps/                    # 运行时生成的地图 HTML
├── mytools/                     # 数据管线：爬虫/清洗/合并（一次性脚本）
├── tests/                       # 90 个 pytest 用例
├── benchmarks/                  # 压测脚本 + 实测数据
├── docs/                        # 架构图 / 面试准备 / 本文档
├── Dockerfile                   # 后端镜像
├── docker-compose.yml           # backend + frontend 编排
├── docker-compose.ragflow.yml   # RAGFlow 五件套编排
├── start.ps1 / start.sh         # Docker 一键启动
├── start-local.ps1              # 本地开发一键启动
└── .github/workflows/ci.yml     # CI：lint + 测试 + 前端构建 + Docker
```

### 0.4 一次流式请求的完整旅程（背下来）

```
浏览器输入 → ChatView.sendMessage()
  → fetch POST /chat/stream {message, session_id} + Bearer token
  → Vite 代理/Nginx 反代 → FastAPI
  → get_current_user 解 JWT → 查 users.db → User 对象
  → thread_id = f"user_{user.id}_{session_id}"
  → _repair_incomplete_tool_calls_async() 修复上次中断的会话（线程池执行，不阻塞事件循环）
  → _get_agent() 懒加载双检锁取 Agent
  → run_in_executor(线程池, agent.stream(..., stream_mode="messages"))
  → LangGraph ReAct 循环：LLM 判断 → 调工具 → ToolMessage 回写 → 再问 LLM
      工具可能触发：RAGFlow 检索 / JSON 查车次 / Folium 画地图
  → 每步状态经 msgpack 序列化写入 checkpointer.db（WAL 模式）
  → AIMessageChunk 逐 token 冒泡 → SSE data: {"content": "..."}\n\n
  → 前端 ReadableStream 逐块解析 → 追加到消息数组 → 打字机效果
  → data: [DONE] 结束 → 前端刷新会话列表
```

---

# 阶段一 · 地基：配置与数据库

## 第 1 章 · settings.py —— 配置系统

**施工顺序**：这是全项目第一个文件，所有模块都依赖它。

### 1.1 Settings 类（pydantic-settings 声明式配置）

```python
class Settings(BaseSettings):
    ragflow_host: str = "http://localhost:9380"
    ragflow_api_key: str = ""
    ragflow_dataset_id: str = ""
    kwargs: int = 5                                # 检索 top_k
    ragflow_similarity_threshold: float = 0.0
    llm_provider: str = "openai"                   # openai / anthropic
    llm_api_key: str = ""
    llm_model_name: str = "deepseek-v4-flash"
    llm_base_url: str = ""
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    embedding_model_name: str = "text-embedding-v4"
    embedding_base_url: str = ""
    chat_history_storage_path: str = ""
    history_database_name: str = "chat_history_check_pointer"
    data_path: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

**要点**：

- 字段名 = `.env` 里的 key（大小写不敏感），自动注入
- `extra="ignore"`：.env 里有额外配置（如 COMPOSE_PROJECT_NAME）不报错

### 1.2 路径默认值补全

```python
def _apply_path_defaults(s: Settings):
    if not s.data_path:
        s.data_path = os.path.join(PROJECT_ROOT, "data", "cleaned_txts")
    if not s.chat_history_storage_path:
        s.chat_history_storage_path = os.path.join(PROJECT_ROOT, "chat_history")
```

**为什么**：相对路径依赖 cwd，不可控；用 `__file__` 推导项目根目录绝对路径。

### 1.3 环境变量间接引用（安全设计）

```python
def _resolve_env_var_refs(s: Settings):
    import re
    _ENV_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")   # 形如 DEEPSEEK_API_KEY
    for field in ("llm_api_key", "embedding_api_key", "ragflow_api_key"):
        raw = getattr(s, field)
        if not raw:
            continue
        if _ENV_REF_RE.match(raw):
            if raw in os.environ and os.environ[raw]:
                setattr(s, field, os.environ[raw])
            else:
                setattr(s, field, "")   # 引用不存在 → 置空，绝不把字面量当 key
```

**踩坑记录（重要）**：

- 初版用 `raw in os.environ` 判断，但 pydantic-settings 读 `.env` 时**自动去掉引号**，导致 `llm_api_key="DEEPSEEK_API_KEY"` 的引号判断逻辑失效，字面量 `"DEEPSEEK_API_KEY"`（16 字符）被当真实 key 发给 DeepSeek → 401
- 修复：改用正则判断"值是否长得像环境变量名"，与引号无关

### 1.4 _SettingsProxy 代理类（运行时热更新）

```python
class _SettingsProxy:
    def __init__(self):
        object.__setattr__(self, "_settings", None)
        self._load()
    def _load(self):
        s = Settings()
        _apply_path_defaults(s)
        _resolve_env_var_refs(s)
        object.__setattr__(self, "_settings", s)
    def reload(self):
        self._load()
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._settings, name)
    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._settings, name, value)

settings = _SettingsProxy()   # 全局单例，所有模块 `from settings import settings`
```

**为什么用代理而不是直接暴露 Settings 实例**：

- `reload()` 后所有 `settings.xxx` 的读取都拿到新值（代理转发）
- `__getattr__` 拦截下划线开头属性避免内部状态泄漏
- 配合 `backend/api.py` 的 `reload_agent()` 实现"改 .env 不重启进程生效"

**面试考点**：代理模式的应用场景；pydantic-settings 的引号处理陷阱；为什么 API key 要支持环境变量间接引用（.env 可入库，真实 key 放 CI/CD 环境变量）。

## 第 2 章 · backend/database.py —— 用户模型

```python
load_dotenv()
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./users.db")
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)      # 存 argon2 哈希，非明文
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)   # 模块导入时自动建表

def get_db():
    db = SessionLocal()
    try:
        yield db          # FastAPI 依赖注入用的生成器
    finally:
        db.close()
```

**要点**：

- `check_same_thread=False`：FastAPI 线程池处理请求，SQLite 连接需跨线程
- `get_db` 是生成器依赖：请求结束自动关闭会话
- `create_all` 幂等：表存在则跳过

## 第 3 章 · backend/schemas.py —— 数据契约

```python
class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
```

**要点**：注册请求体和登录响应体的契约。`response_model=Token` 让 Swagger 文档自动生成响应示例。

---

# 阶段二 · 认证体系

## 第 4 章 · backend/auth.py —— JWT + argon2

### 4.1 常量与安全底线

```python
SECRET_KEY = os.getenv("JWT_SECRET_KEY")   # 未配置时为 None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 300          # 5 小时
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
ph = PasswordHasher()                      # argon2
```

**安全设计**：`SECRET_KEY=None` 时 `jwt.encode/decode` 直接抛错——**拒绝静默使用弱密钥**，宁可启动失败也不留后门。

### 4.2 密码验证（argon2）

```python
def authenticate_user(db, username, password):
    user = db.query(database.User).filter(database.User.username == username).first()
    if not user:
        return False
    try:
        ph.verify(user.password, password)
        return user
    except VerifyMismatchError:
        return False
```

**踩坑**：测试时若数据库存的是明文，argon2 抛 `InvalidHashError`（不是 `VerifyMismatchError`），不会被捕获 → 500。所以测试夹具必须用 `ph.hash()` 造数据。

### 4.3 JWT 签发

```python
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

**要点**：payload 里 `sub` 存用户名；`exp` 是 JWT 标准过期字段。

### 4.4 依赖注入式鉴权

```python
async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(database.get_db)):
    credentials_exception = HTTPException(401, "Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(database.User).filter(database.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user
```

**要点**：任何路由加 `current_user: User = Depends(get_current_user)` 即受保护；`algorithms` 显式指定防算法混淆攻击。

### 4.5 注册/登录路由

```python
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db = Depends(database.get_db)):
    if db.query(database.User).filter(database.User.username == user.username).first():
        raise HTTPException(400, "Username already registered")
    new_user = database.User(username=user.username, password=ph.hash(user.password))
    db.add(new_user); db.commit(); db.refresh(new_user)   # refresh 拿回自增 id
    access_token = create_access_token(data={"sub": new_user.username},
                                       expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(database.get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(401, "Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    ...  # 同上签发 token
```

**要点**：注册收 JSON，登录收 **Form**（`OAuth2PasswordRequestForm` 要求 `application/x-www-form-urlencoded`）——前端登录时必须用 `FormData`，这是常见联调坑。

**面试考点**：为什么选 argon2（内存困难，抗 GPU 爆破）；JWT 无状态鉴权流程；OAuth2PasswordRequestForm 与 Swagger Authorize 按钮的关系。

---

# 阶段三 · Agent 核心

## 第 5 章 · agent/llm.py —— LLM 工厂

```python
def create_llm(**kwargs):
    provider = config_data.llm_provider
    if provider == "openai":
        return ChatOpenAI(model=config_data.llm_model_name,
                          api_key=config_data.llm_api_key,
                          base_url=config_data.llm_base_url, **kwargs)
    elif provider == "anthropic":
        return ChatAnthropic(model=..., api_key=..., base_url=..., **kwargs)
```

**要点**：

- `**kwargs` 透传：`create_llm(streaming=True)` 把流式开关传给底层
- 火山方舟/DeepSeek 都兼容 OpenAI 协议 → 只换 `base_url` + `model_name` 即可切换供应商
- `api_key=""` 时 ChatOpenAI 构造直接抛 `OpenAIError: Missing credentials`（这是"空 key 不影响启动但影响首次请求"的原因）

## 第 6 章 · agent/railway_tools.py —— 车次查询工具

### 6.1 数据懒加载缓存

```python
_train_details = None
def _load_train_details():
    global _train_details
    if _train_details is None:
        with open(_train_details_path, 'r', encoding='utf-8') as f:
            _train_details = json.load(f)
        logger.info(f"加载 train_details.json: {len(_train_details)} 个车次")
    return _train_details
```

**为什么**：9547 车次 JSON 约 10MB+，进程内只加载一次；首次调用慢（0.4s），后续 0.005s。

### 6.2 车次类型优先级排序

```python
priority = {'G': 0, 'D': 1, 'C': 2, 'Z': 3, 'T': 4, 'K': 5}
results.sort(key=lambda x: (priority.get(x[0][0], 9), x[0]))
```

**要点**：先按车次首字母等级排，再按车次号排；未知前缀排最后（9）。

### 6.3 两个 @tool

```python
@tool(description="查询指定车次的详细信息，包括起讫站、列车类型、各站到达/发车时间。"
                  "输入为车次列表，例如 ['Z227'] 或 ['G1', 'G2']")
@log_tool_call
def query_train_info(train_codes: list) -> str:
    # 逐个查 details → 查不到的查 stations_basic → 都没有的收集进 not_found
    # 返回格式化文本（🚄 车次 (类型) / 起讫站 / 经停 N 站 / 逐站 到:xx 发:xx）

@tool(description="根据起讫站查询符合条件的车次列表。")
@log_tool_call
def query_trains_by_route(from_station: str, to_station: str, limit: int = 3) -> str:
    # 精确匹配 from/to → 排序 → 取前 limit → 从 details 补全详细信息
```

**工具设计心得（面试高频）**：

- **description 就是给 LLM 看的 API 文档**：写清输入格式（`['Z227']` 列表而非字符串）能显著降低 LLM 传参错误率
- 返回**格式化文本**而非 JSON：LLM 读文本更稳，且能直接引用到回答里
- 查不到时返回明确提示（`❌ 未找到以下车次: xxx`）而非抛异常——让 LLM 能向用户解释

## 第 7 章 · agent/route_map_generator.py —— 地图生成器

### 7.1 输出目录（环境变量可覆盖）

```python
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'data'))
_MAP_DIR = os.getenv("maps_output_dir", os.path.join(_DATA_DIR, 'maps'))
```

**踩坑记录**：初版硬编码 `data/maps`，但 docker-compose 注入 `maps_output_dir=/app/shared/maps`（共享卷给 Nginx）→ Docker 里地图写错位置，Nginx 404。修复：`os.getenv` 优先，本地默认兜底。同一 bug 还出现在 `backend/api.py` 的静态挂载处——**两处必须指向同一目录**。

### 7.2 生成流程

```python
def generate_train_route_map(train_code: str) -> str:
    stations = get_train_stations(train_code)          # 先 details 后 stations 兜底
    if len(stations) < 2:
        return f"车次 {train_code} 的站点数据不足"      # 错误也返回文本，不抛异常
    # 中心点 = 始发/终点坐标中点，zoom 6
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6, tiles=OSM, attr=...)
    _generate_route_map(m, stations, '#FF4444')        # 相邻站两两连线 PolyLine
    for idx, (coord, name) in enumerate(station_coords_list):
        if idx == 0:      folium.Marker(..., icon=folium.Icon(color='green', icon='play'))       # 始发 🟢
        elif idx == last: folium.Marker(..., icon=folium.Icon(color='red', icon='flag-checkered'))  # 终点 🔴
        else:             folium.CircleMarker(..., radius=5, color='#3388ff')                        # 中间 🔵
    m.get_root().html.add_child(folium.Element(title_html))   # 顶部标题栏
    m.save(map_path)                                   # 自包含 HTML（内嵌 Leaflet JS/CSS）
    return map_path
```

**设计决策**：

- 相邻站**直线连接**而非真实铁路轨迹（简化版；真实轨迹数据在 `data/handle_gpkg/` 有 GeoPandas 处理脚本，未接入）
- 错误返回中文字符串（"未找到车次 xxx 的信息"），LLM 能直接转述给用户
- 生成的 HTML 自包含，iframe 直接加载无需额外依赖

## 第 8 章 · agent/tools.py —— 工具注册中心

### 8.1 日志装饰器

```python
def log_tool_call(func):
    @functools.wraps(func)          # 保留原函数名/docstring（LangChain 内省需要！）
    def wrapper(*args, **kwargs):
        start = time.time()
        logger.info(f"调用工具: {func.__name__}，参数: {kwargs}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"工具 {func.__name__} 执行成功，耗时: {time.time()-start:.3f}秒")
            return result
        except Exception as e:
            logger.error(f"工具执行失败: {e}", exc_info=True)
            raise                    # 重新抛出，保持原有行为
    return wrapper
```

**关键细节**：`@functools.wraps` 不能省——LangChain 通过 `__name__`/`__doc__` 内省工具，丢了会导致工具名变 `wrapper`。

**装饰器顺序**：`@tool` 在最上，`@log_tool_call` 在下——先包装日志再注册为工具。

### 8.2 RAGFlow 客户端单例

```python
_ragflow_client: RAGFlowClient | None = None

def get_ragflow_client() -> RAGFlowClient:
    global _ragflow_client
    if _ragflow_client is None:
        _ragflow_client = RAGFlowClient(host=..., api_key=..., dataset_id=...)
    return _ragflow_client

def reset_service_singletons():
    """仅用于测试隔离"""
    global _ragflow_client
    _ragflow_client = None
```

**为什么单例**：内部持有 `requests.Session`（连接池），每次重建浪费连接。`reset` 配合 conftest 的 autouse fixture 保证测试互不污染。

### 8.3 检索工具

```python
@tool(description="检索向量库, 寻找匹配的知识")
@log_tool_call
def retriever_tool(query: str):
    client = get_ragflow_client()
    results = client.search(query=query, top_k=config_data.kwargs,
                            similarity_threshold=config_data.ragflow_similarity_threshold)
    if not results:
        return "未找到相关消息"
    formatted = [f"{i}. {r['content']}（来源: {r['source']}）" for i, r in enumerate(results, 1)]
    return "\n\n".join(formatted)
```

**细节**：带来源文件名 → LLM 回答可引用出处；RAGFlow 挂掉时 `search` 内部捕获异常返回 `[]` → 工具返回"未找到"而非崩溃（但 LLM 会反复重试检索，这是压测发现的延迟问题）。

## 第 9 章 · agent/agent.py —— AgentService

```python
class AgentService:
    def __init__(self):
        os.makedirs(config_data.chat_history_storage_path, exist_ok=True)
        db_path = os.path.join(config_data.chat_history_storage_path,
                               config_data.history_database_name)
        # ── SQLite 并发三件套 ──
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        self.conn.execute("PRAGMA journal_mode=WAL")      # 读写不互斥
        self.conn.execute("PRAGMA busy_timeout=30000")    # 写锁等待 30s 而非立刻报错
        self.conn.execute("PRAGMA synchronous=NORMAL")    # 性能与安全的平衡
        self.checkpointer = SqliteSaver(self.conn)
        self.agent = create_agent(
            model=create_llm(streaming=True),
            tools=[retriever_tool, query_train_info, query_trains_by_route, generate_route_map],
            system_prompt="你是一位知晓中国铁路和机车知识的专家。..."
                          "工具使用指南：1.问车次信息→query_train_info  2.问两地车次→query_trains_by_route
                           3.要地图→generate_route_map  4.既要信息又要地图→先查后画  5.直接展示详细信息",
            checkpointer=self.checkpointer,
        )

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
```

**四个关键决策**：

1. **check_same_thread=False**：api.py 在线程池里跑 `agent.stream()`，连接必须跨线程；SqliteSaver 内部有 `threading.Lock` 保护写路径
2. **WAL 模式**：读不阻塞写、写不阻塞读——20 线程并发测试不出现 `database is locked` 的前提
3. **system_prompt 写工具使用指南**：LLM 选工具的准确率大幅提升（尤其"先查信息再画图"的组合指令）
4. **close() 吞异常**：reload/关闭时连接可能已断，清理失败不应影响主流程

**面试考点**：SQLite WAL 原理；为什么不用 PostgreSQL（单机演示零运维，架构上 SQLAlchemy 已解耦可随时换）；多轮记忆的实现原理（checkpointer 按 thread_id 存全量消息历史）。

---

# 阶段四 · API 层（backend/api.py，最复杂的文件）

## 第 10 章 · 应用骨架与生命周期

```python
# ── 有界线程池（拒绝无界！）──
_AGENT_POOL_SIZE = int(os.getenv("AGENT_THREAD_POOL_SIZE", "8"))
_agent_executor = ThreadPoolExecutor(max_workers=_AGENT_POOL_SIZE, thread_name_prefix="agent-worker")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield                                    # 启动：无需预热（Agent 懒加载）
    if _agent_service is not None:
        _agent_service.close()               # 关闭：释放 SQLite 连接
    _agent_executor.shutdown(wait=True)      # 等待在跑任务结束

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, ...)
app.include_router(auth.router)

# ── 地图静态挂载（与生成目录一致！）──
_maps_dir = os.getenv("maps_output_dir", os.path.normpath(.../data/maps))
os.makedirs(_maps_dir, exist_ok=True)
app.mount("/maps", StaticFiles(directory=_maps_dir), name="maps")
```

**为什么有界线程池**：默认 `run_in_executor(None)` 用无界池——并发请求无限建线程，且所有请求共享同一 SQLite 连接，线程爆炸会放大锁竞争。8 是经验值（受 LLM 并发配额限制，再多也没用）。

## 第 11 章 · Agent 单例生命周期

```python
_agent = None            # LangGraph agent 实例（测试 mock 直接替换这个）
_agent_service = None    # 持有 SQLite 连接，用于 close
_agent_lock = threading.Lock()

def _get_agent():
    global _agent, _agent_service
    if _agent is None:                       # 第一次检查（无锁快路径）
        with _agent_lock:
            if _agent is None:               # 第二次检查（锁内防重复创建）
                _agent_service = AgentService()
                _agent = _agent_service.agent
    return _agent

def reload_agent():
    global _agent, _agent_service
    with _agent_lock:
        old_service = _agent_service
        new_service = AgentService()
        _agent_service = new_service         # 先替换引用（中间态对外可用）
        _agent = new_service.agent
        if old_service is not None:
            old_service.close()              # 再关旧连接
```

**双检锁**：避免每次请求都抢锁；**先建新再关旧**：reload 期间服务不中断。

## 第 12 章 · 请求模型与校验

```python
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{0,64}$")   # 模块级！不能放类里

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, v: str) -> str:
        if not _SESSION_ID_RE.match(v):
            raise ValueError("session_id 只能包含字母、数字、下划线或连字符，且长度不超过 64")
        return v

    @field_validator("message")
    @classmethod
    def _validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("消息内容不能为空")
        if len(v) > 8000:
            raise ValueError("消息内容过长（上限 8000 字符）")
        return v
```

**踩坑记录（本项目最典型的 bug）**：`_SESSION_ID_RE` 最初定义为**类属性**，Pydantic v2 把 `_` 前缀类属性当 `ModelPrivateAttr`，`cls._SESSION_ID_RE.match(v)` 抛 `AttributeError` → **所有 /chat 请求 500**。修复：提为模块级常量。这个 bug 是自研压测脚本跑出来的。

**为什么校验 session_id**：它会被拼进 `thread_id` 并作为 SQLite 查询条件，不限制字符就是注入漏洞。

## 第 13 章 · 会话历史反解（checkpoint_parser.py）

LangGraph SqliteSaver 的存储格式（必须理解才能写解析器）：

```
checkpoints 表.checkpoint 字段 = msgpack bytes
  └─ unpack 后 = {v, ts, channel_values: {messages: [...]}}
       └─ 每条消息 = ['msgpack', <bytes>]          ← JsonPlusSerializer.dumps_typed 的 typed 格式
            └─ unpack <bytes> = ExtType(code=5, data=<bytes>)
                 └─ unpack data = ['module路径', 'ClassName', {kwargs: {content: ..., ...}}]
```

解析器实现（`agent/checkpoint_parser.py`）：

```python
_MSGPACK_EXT_CODE = 5

def _extract_one(msg):
    # 格式 1：ExtType(5) 直接出现
    if hasattr(msg, "code") and msg.code == 5:
        return _extract_typed_message(msg)
    # 格式 2：['msgpack', bytes] 包装
    if isinstance(msg, (list, tuple)) and len(msg) >= 2:
        data = _unpack_bytes(msg[1])
        if hasattr(data, "code") and data.code == 5:
            return _extract_typed_message(data)
        if isinstance(data, dict):
            return _extract_plain_dict_message(data)
        return None
    # 格式 3：纯 dict
    if isinstance(msg, dict):
        return _extract_plain_dict_message(msg)
    return None

def _extract_typed_message(ext):
    inner = _unpack_bytes(ext.data)          # ['module', 'ClassName', {kwargs}]
    class_name, kw = inner[1], inner[2]
    content = kw.get("content", "")
    if class_name == "HumanMessage":                    role = "user"
    elif class_name in ("AIMessage", "AIMessageChunk"): role = "assistant"
    else: return None                                   # System/Tool 消息过滤
    return {"role": role, "content": content}

def _extract_messages_list(cv):
    # messages 可能是 list / dict 包装 / 藏在 __start__ 里 → 三级兜底
    ...

def parse_messages_from_checkpoint(blob: bytes) -> list:
    try:
        data = msgpack.unpackb(blob)
        cv = data.get(b"channel_values", data.get("channel_values", {}))
        ...
        return [parsed for msg in raw_messages if (parsed := _extract_one(msg))]
    except Exception as e:
        logger.warning("解析失败: %s", e)
        return []          # ← 永不抛异常，读历史不影响主流程
```

**设计哲学**：LangGraph 版本升级会改内部格式（dict 包装、`__start__` 等），没有官方读取 API → **防御式解析**：多格式兼容 + 任何失败返回空。测试用**真实的 `JsonPlusSerializer`** 构造 blob，保证与线上格式一致。

## 第 14 章 · 会话管理接口（4 个）

```python
@app.get("/chat/sessions")
def list_sessions(current_user = Depends(get_current_user)):
    prefix = f"user_{current_user.id}_"
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    _ensure_session_meta_table(conn)
    # 1. 扫 checkpoints：metadata.source == "input" 的首条 → thread_id 去重
    #    preview = parse_first_message(...) or "新对话"
    #    created_at = parse_checkpoint_ts(...)
    # 2. session_meta 自定义标题覆盖 preview
    # 3. 按日期分组（今天/昨天/...），组内按时间降序，组间按日期降序
    return {"groups": sorted_groups}

@app.get("/chat/sessions/{thread_id:path}")
def get_session_messages(thread_id, current_user):
    if not thread_id.startswith(f"user_{current_user.id}"):   # 越权校验
        return {"messages": []}
    # 取最新一条 checkpoint → parse_messages_from_checkpoint

@app.put("/chat/sessions/{thread_id:path}")
def rename_session(thread_id, request: RenameRequest, current_user):
    # 越权校验 → 会话必须存在于 checkpoints → UPSERT session_meta
    # RenameRequest.title 校验：非空、≤100 字符

@app.delete("/chat/sessions/{thread_id:path}")
def delete_session(thread_id, current_user):
    # 越权校验 → DELETE checkpoints + writes + session_meta 三表
    # deleted == 0 → "会话不存在"
```

**session_meta 表**（与 checkpointer 同库）：

```python
def _ensure_session_meta_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS session_meta (
        thread_id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at TEXT NOT NULL)""")
```

**为什么能同库**：SqliteSaver 只管自己的 checkpoints/writes 表，额外建表互不干扰——省掉第二个数据库文件。

**`{thread_id:path}`**：path 转换器允许 thread_id 含 `/`（虽然当前不含，但防止 UUID 被路由误切）。

## 第 15 章 · 聊天接口（核心中的核心）

### 15.1 非流式 /chat

```python
@app.post("/chat")
def chat(request: ChatRequest, current_user = Depends(get_current_user)):
    session_suffix = f"_{request.session_id}" if request.session_id else ""
    thread_id = f"user_{current_user.id}{session_suffix}"
    config = {"configurable": {"thread_id": thread_id}}
    agent = _get_agent()
    _repair_incomplete_tool_calls(agent, config)
    result = agent.invoke(input={"messages": [{"role": "user", "content": request.message}]},
                          config=config)
    return {"answer": result["messages"][-1].content}
```

### 15.2 中断修复机制

```python
def _repair_incomplete_tool_calls(agent, config):
    state = agent.get_state(config)
    if state is None or not state.values:
        return
    messages = state.values.get('messages', [])
    last = messages[-1]
    if hasattr(last, 'tool_calls') and last.tool_calls:
        # 最后一条是带 tool_calls 的 AIMessage 但没有 ToolMessage → 未闭合
        try:
            agent.invoke(input=None, config=config)   # 框架自动补完工具执行
        except Exception as e:
            logger.warning("修复失败: %s", e)

async def _repair_incomplete_tool_calls_async(agent, config):
    """异步包装：在线程池中执行，不阻塞事件循环"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _agent_executor,
        lambda: _repair_incomplete_tool_calls(agent, config),
    )
```

**场景还原**：流式请求 300s 超时被切断时，Agent 可能正停在"LLM 要求调工具"这一步 → checkpoint 里留下悬空的 tool_calls → 下次同 thread_id 请求，LLM API 直接拒绝这种非法消息序列 → **会话永久损坏**。修复 = 请求前检测 + `invoke(None)` 让 LangGraph 走完工具节点。

**两个版本的使用场景（重要设计细节）**：

| 端点 | 调用方式 | 原因 |
|---|---|---|
| `/chat`（同步 `def`） | 直接调用 `_repair_incomplete_tool_calls()` | FastAPI 自动把同步端点扔进线程池，阻塞的是工作线程不是事件循环 |
| `/chat/stream`（`async def`） | `await _repair_incomplete_tool_calls_async()` | async 端点跑在事件循环里，同步的 `get_state`/`invoke`（SQLite + 潜在 LLM 调用）会卡住**所有**并发请求，必须经 `run_in_executor` 扔进有界线程池 |

> **踩坑记录**：初版两个端点都直接调用同步修复函数——async 端点里修复期间（最坏 30s，工具内部超时）事件循环被阻塞，其他用户的请求全部卡住。这是代码审查时主动发现并修复的真实瑕疵：**async 端点里任何同步阻塞调用都必须走 executor**，与 15.3 的流式处理是同一条原则。

### 15.3 流式 /chat/stream（全项目最精妙的 40 行）

```python
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, current_user = Depends(get_current_user)):
    ...
    _SENTINEL = object()                      # 哨兵对象

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            # ① 建流：同步 agent.stream() 扔进线程池，60s 超时
            stream_iter = iter(await asyncio.wait_for(
                loop.run_in_executor(_agent_executor,
                    lambda: agent.stream(input_data, config=config, stream_mode="messages")),
                timeout=60.0))

            def _next_chunk():
                try:
                    return next(stream_iter)
                except StopIteration:
                    return _SENTINEL          # ② 哨兵替代 StopIteration

            while True:
                # ③ 单块 300s 超时
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(_agent_executor, _next_chunk), timeout=300.0)
                if chunk is _SENTINEL:
                    break
                msg = chunk[0] if isinstance(chunk, tuple) else chunk
                if isinstance(msg, (AIMessage, AIMessageChunk)) and msg.content:
                    yield f"data: {json.dumps({'content': msg.content}, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'error': '操作超时...'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"              # ④ 永远正常结束流

    return StreamingResponse(generate(), media_type="text/event-stream")
```

**四个设计点（面试必考）**：

1. **为什么不能直接 `async for`**：`agent.stream()` 是同步阻塞生成器，直接放事件循环会卡死所有并发请求
2. **为什么用哨兵**：同步生成器的 `StopIteration` 穿越 `asyncio.Future` 会被包装成 `RuntimeError`，破坏迭代语义——用哨兵对象标记结束从根上规避
3. **双层超时**：建流 60s（LLM 连接慢）+ 单块 300s（工具执行慢，如地图生成 6s、RAGFlow 重试 4s×N）
4. **错误也走 SSE**：推送 `{"error": ...}` 事件后 `[DONE]` 正常收尾——前端不会无限转圈

**面试考点**：asyncio 事件循环阻塞问题；run_in_executor 原理；SSE vs WebSocket 的选型（单向推送 SSE 更轻）；为什么 stream_mode="messages"（拿到 token 级 chunk）。

---

# 阶段五 · RAG 知识库

## 第 16 章 · agent/ragflow_client.py —— REST 客户端

```python
class RAGFlowClient:
    def __init__(self, host, api_key, dataset_id):
        self._session = requests.Session()               # 连接池复用
        self._session.headers["Authorization"] = f"Bearer {api_key}"

    def search(self, query, top_k=5, similarity_threshold=0.0) -> list[dict]:
        payload = {"question": query, "dataset_ids": [self.dataset_id],
                   "top_k": top_k, "similarity_threshold": similarity_threshold}
        try:
            resp = self._session.post(f"{self.base_url}/api/v1/retrieval",
                                      json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:                    # RAGFlow 业务错误码
                return []
            return [{"content": c.get("content",""), "source": c.get("source",""),
                     "similarity": c.get("similarity",0.0)} for c in data["data"]["chunks"]]
        except requests.RequestException:
            return []                                    # 网络异常 → 空结果不崩溃
```

**要点**：所有方法失败返回空/False 而非抛异常——检索挂了不应炸掉整个对话。还有 `list_datasets` / `upload_document` / `register` / `login`（RSA 加密密码）等方法支撑初始化流程。

## 第 17 章 · agent/ragflow_init.py —— 自动初始化 + 容器补丁（最大亮点）

### 17.1 十步初始化流程

```
等待就绪(60×5s 轮询) → 打容器补丁 → 容器内建管理员 → 容器内建 API Token
→ RSA 加密密码登录拿 Cookie → 容器内注册 Embedding/LLM 模型（三层结构）
→ REST 建知识库 → 上传 237 篇文档 → 凭证写回 .env → 写 .ragflow_initialized 标记
```

### 17.2 容器补丁机制（RAGFLOW_PATCHES）

```python
RAGFLOW_PATCHES = {
    "embedding_model.py": {
        "path": "/ragflow/rag/llm/embedding_model.py",
        "desc": "OpenAI_APIEmbed batch_size 16→10",
        "old": """class OpenAI_APIEmbed(OpenAIEmbed):
    ...batch_size=16...""",          # 精确的旧代码片段
        "new": """class OpenAI_APIEmbed(OpenAIEmbed):
    ...batch_size=10...""",          # 精确的新代码片段
    },
    "task_context.py": {...parser_config str→dict 容错...},
}

def apply_container_patches():
    for key, cfg in RAGFLOW_PATCHES.items():
        # ① 先检测：新代码已在文件里 → 跳过（幂等！）
        check = docker_exec_raw(f"print('PATCHED' if '''{cfg['new']}''' in content else 'NEEDS_PATCH')")
        # ② 未打则容器内 Python 精确替换 content.replace(old, new, 1)
        # ③ 打了新补丁 → 清 __pycache__ → docker restart → sleep(15)
```

**两个上游 bug**：

1. DashScope text-embedding-v4 限制 batch_size ≤ 10，RAGFlow 写死 16 → 批量向量化必失败
2. `parser_config` 部分路径是 JSON 字符串而非 dict → 解析任务崩溃

**为什么这么设计（面试重点）**：

- 改 Docker 镜像源码 → 重新 build 慢、版本升级被覆盖
- 补丁定义为"旧→新"字符串对 → **幂等可重入**（容器重启后自动补打，检测先行）
- `docker exec` 容器内执行 → 不侵入镜像
- `repr()` 注入代码字符串 → 处理转义

### 17.3 容器内执行 Python 的封装

```python
def docker_exec(code: str) -> str:
    full_code = f"import warnings, logging...{code}"   # 压掉日志噪音
    cmd = ["docker", "exec", CONTAINER, "python3", "-c", full_code]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # 过滤 pkg_resources/LiteLLM/Warning 等噪音行，只留业务输出
```

### 17.4 模型注册（RAGFlow v0.26.4 三层结构）

```
TenantModelProvider（OpenAI-API-Compatible）
  └─ TenantModelInstance（dashscope / deepseek，带 api_key + base_url）
       └─ TenantModel（具体模型名，model_type: 1=CHAT 2=EMBEDDING）
最后 Tenant.update(embd_id="模型名@实例名@供应商名", llm_id=...) 写默认引用
```

**为什么要在数据库里注册**：光有 .env 不够，task executor 从 RAGFlow 自己的表里找模型凭证。

## 第 18 章 · 数据管线（mytools/）

| 脚本                                            | 职责            | 关键实现                                                                                                                                  |
| ----------------------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `scrap_trains.py`                             | 爬车次列表      | requests + lxml XPath（`//div[@class="train_index_cz"]//ul/li`），verify=False 禁 SSL 警告                                              |
| `clean_text.py`                               | 清洗 237 篇文档 | 12 步正则：markdown 标题→保留结构、去链接/图片/引用、去 HTML 标签、零宽字符、多空格、目录行、纯符号行、纯 URL 行；输出处理报告（压缩率） |
| `merge_trains.py` / `add_count.py`          | 合并车次数据    | -                                                                                                                                         |
| `exact_stations.py` / `get_city_station.py` | 站点坐标提取    | 产出 station_coords.json                                                                                                                  |

**数据流**：爬取 → 清洗 → `data/cleaned_txts/`（RAG 语料）+ JSON（工具数据源）→ `ragflow_migrate.py` 批量上传。

---

# 阶段六 · 前端

## 第 19 章 · 入口与全局（main.ts / App.vue）

```typescript
// main.ts —— 三行骨架
const app = createApp(App)
app.use(createPinia())     // 状态管理先于路由（router 守卫里用 store）
app.use(router)
app.mount('#app')
```

```vue
<!-- App.vue —— 令牌巡检 -->
<script setup lang="ts">
let timer: ReturnType<typeof setInterval> | null = null
function checkTokenExpiry() {
  if (authStore.token && isTokenExpired(authStore.token)) {
    authStore.logout()
    if (route.path !== '/login')
      router.push({ path: '/login', query: { redirect: route.fullPath } })
  }
}
onMounted(() => { timer = setInterval(checkTokenExpiry, 30_000) })   // 每 30s 巡检
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
```

**要点**：路由守卫只拦"导航时"，长时间停留页面的过期靠这个定时器兜底。全局样式：CSS reset + Inter 字体 + 毛玻璃变量。

## 第 20 章 · stores/auth.ts —— 认证状态

```typescript
// 手写 JWT payload 解析（不引第三方库）
function parseJwtPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  const base64 = (parts[1] ?? '').replace(/-/g, '+').replace(/_/g, '/')   // base64url → base64
  return JSON.parse(decodeURIComponent(atob(base64).split('').map(
    c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join('')))  // 处理 UTF-8
}

export function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token)
  if (!payload || typeof payload.exp !== 'number') return true   // 解析失败=过期（安全兜底）
  return payload.exp * 1000 < Date.now() - 10_000                // 提前 10 秒判定
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const isLoggedIn = computed(() => !!token.value && !isTokenExpired(token.value))
  async function login(data) {
    const formData = new FormData()                // 登录是 Form 格式！
    formData.append('username', data.username); formData.append('password', data.password)
    const res = await api.post('/auth/login', formData)
    setToken(res.data.access_token)                // 注册接口直接返回 token，无需二次登录
  }
  ...
})
```

**细节**：base64url 的 `-_` 替换、UTF-8 中文解码、提前 10s 判过期（防请求发出瞬间过期）、解析失败视为过期。

## 第 21 章 · services/api.ts —— Axios 双拦截器

```typescript
const api = axios.create({ baseURL: '', timeout: 60000 })   // 空=相对路径：dev 走 Vite 代理，prod 走 Nginx

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    if (isTokenExpired(token)) {          // 发请求前主动检查
      localStorage.removeItem('token')
      router.push('/login')
      return Promise.reject(new axios.Cancel('Token expired'))
    }
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {  // 服务端判过期
      localStorage.removeItem('token')
      router.push('/login')
    }
    return Promise.reject(error)
  },
)
```

## 第 22 章 · router/index.ts —— 路由与守卫

```typescript
const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/login', component: LoginView, meta: { requiresGuest: true } },
  { path: '/register', component: RegisterView, meta: { requiresGuest: true } },
  { path: '/chat', component: ChatStreamView, meta: { requiresAuth: true } },
  { path: '/chat/legacy', component: ChatLegacyView },   // 非流式版保留
  { path: '/:pathMatch(.*)*', redirect: '/login' },      // 通配兜底
]
const WHITELIST = ['/login', '/register']
router.beforeEach((to, _from, next) => {
  if (WHITELIST.includes(to.path)) {
    if (authStore.isLoggedIn) { next('/chat'); return }  // 已登录访问登录页 → 跳聊天
    next(); return
  }
  if (!authStore.isLoggedIn) {
    authStore.logout()
    next({ path: '/login', query: { redirect: to.fullPath } })   // 登录后回跳
    return
  }
  next()
})
```

所有视图组件 `() => import(...)` 动态导入 → 代码分割，首屏只加载登录页。

## 第 23 章 · LoginView.vue —— 登录页

- 表单校验（required）+ focus 状态样式 + 错误抖动动画（`errorShake` 500ms）
- 登录成功读 `route.query.redirect` 回跳
- 错误提取链：`axiosError.response.data.detail` → `Error.message` → 兜底文案
- 装饰元素 + 卡片 hover 效果（纯 CSS）

## 第 24 章 · ChatView.vue —— 聊天主界面（前端最复杂）

### 24.1 Markdown + 代码高亮 + 地图卡片渲染

```typescript
marked.setOptions({ breaks: true, gfm: true })
const renderer = new marked.Renderer()
renderer.code = ({ text, lang }) => {          // marked v17：对象参数！
  const language = lang || 'text'
  const valid = hljs.getLanguage(language) ? language : 'text'
  return `<pre><code class="hljs language-${valid}">${hljs.highlight(text, { language: valid }).value}</code></pre>`
}
marked.setOptions({ renderer })

const MAP_URL_RE = /\/maps\/[A-Za-z0-9_\-]+\.html/

function renderContent(raw: string): string {
  const mapUrls: string[] = []
  const safe = raw.replace(MAP_URL_RE, (url) => {       // ① 先抽走地图 URL 换占位符
    mapUrls.push(url)
    return `__MAP_CARD_${mapUrls.length - 1}__`
  })
  let html = marked(safe) as string                     // ② 再渲染 markdown
  html = html.replace(/__MAP_CARD_(\d+)__/g, (_, idx) => {
    const url = mapUrls[Number(idx)]
    return url ? renderMapCard(url) : ''                // ③ 还原为 iframe 卡片
  })
  return html
}

function renderMapCard(url: string): string {
  return `<div class="map-card">
    <div class="map-card-header">🗺️ 交互式路线地图</div>
    <iframe src="${url}" class="map-frame" loading="lazy"></iframe>
    <a class="map-card-link" href="${url}" target="_blank">在新窗口打开 ↗</a>
  </div>`
}
```

**为什么先抽占位符**：地图 URL 直接进 markdown 可能被链接语法干扰；占位符保证卡片 HTML 原样输出。

### 24.2 SSE 流式接收 + 停止生成

```typescript
let abortController: AbortController | null = null

async function sendMessage() {
  ...
  abortController = new AbortController()
  const response = await fetch('/chat/stream', { ..., signal: abortController.signal })
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let assistantMessage = ''
  messages.value.push({ role: 'assistant', content: '' })
  const lastIndex = messages.value.length - 1

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const chunk = decoder.decode(value, { stream: true })   // 流式解码（多字节中文安全）
    for (const line of chunk.split('\n\n')) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6).trim()
      if (data === '[DONE]') continue
      const parsed = JSON.parse(data)
      if (parsed.content) {
        assistantMessage += parsed.content
        const msg = messages.value[lastIndex]
        if (msg) msg.content = assistantMessage             // noUncheckedIndexedAccess 需判空
        scrollToBottom()
      } else if (parsed.error) {
        assistantMessage += `\n\n⚠️ 服务异常：${parsed.error}`
        sessionId.value = crypto.randomUUID()               // 放弃坏会话，下次用新 id
        activeThreadId.value = ''
      }
    }
  }
  ...
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      // 用户主动停止：不算错误，保留已生成内容
      const msg = messages.value[messages.value.length - 1]
      if (msg && msg.role === 'assistant') msg.content += '\n\n⏹️ (已停止生成)'
      return
    }
    ...  // 401 → 跳登录；其他 → 错误提示 + 换新会话
  }
  finally {
    loading.value = false
    abortController = null
    fetchSessions()                                          // 刷新侧边栏
  }
}

function stopGenerating() { abortController?.abort() }
onBeforeUnmount(() => abortController?.abort())              // 组件卸载防泄漏
```

### 24.3 会话管理

```typescript
function extractSessionId(threadId: string): string {
  return threadId.split('_').slice(2).join('_')   // user_{id}_{session_id} → session_id
}                                                  // slice(2)+join：session_id 本身可含下划线

async function renameSession(threadId: string, newTitle: string) {
  const res = await fetch(`/chat/sessions/${encodeURIComponent(threadId)}`, {
    method: 'PUT', headers: {...}, body: JSON.stringify({ title: newTitle }) })
  if ((await res.json()).ok) fetchSessions()
}

async function deleteSession(threadId: string) {
  if (!window.confirm('确定删除这个会话吗？')) return
  ... DELETE → 若删的是当前会话：清空消息区 + 换新 sessionId
}
```

## 第 25 章 · HistorySidebar.vue —— 侧边栏

```vue
<!-- 行内重命名：编辑态 input 替换预览 -->
<input v-if="renamingId === session.thread_id"
       v-model="renamingTitle" class="rename-input" maxlength="100"
       @click.stop
       @vue:mounted="focusRenameInput"          <!-- 挂载即聚焦+全选 -->
       @keyup.enter="confirmRename(session.thread_id)"
       @keyup.esc="cancelRename"
       @blur="confirmRename(session.thread_id)" />
```

```typescript
function focusRenameInput(event: unknown) {
  const el = (event as { el?: HTMLInputElement }).el   // Vue mounted 钩子参数是 VNode
  el?.focus(); el?.select()
}
function confirmRename(threadId: string) {
  if (renamingId.value !== threadId) return   // 防止 enter+blur 双触发
  const title = renamingTitle.value.trim()
  renamingId.value = ''
  if (title) emit('rename-session', threadId, title)
}
```

**踩坑记录**：

- `v-for` 里 `ref="renameInputRef"` 收集为**数组**，`input.focus is not a function` → 改用 `@vue:mounted` 钩子从 VNode 取 `el`
- 最初用 `window.prompt`，自动化测试环境不支持 → 行内编辑体验也更好
- `confirmRename` 的 `renamingId !== threadId` 守卫：Enter 触发后 blur 又触发一次，第二次直接跳过

**日期分组**：`formatDateHeader` → 今天/昨天/本周星期几/原始日期。

---

# 阶段七 · 测试体系（90 个用例）

## 第 26 章 · 测试架构

### conftest.py（全局夹具）

```python
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-not-for-prod")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_users.db")
# 必须在 import backend.* 之前设置！

@pytest.fixture(autouse=True)
def _reset_service_singletons():
    from agent.tools import reset_service_singletons
    reset_service_singletons()      # 前置重置
    yield
    reset_service_singletons()      # 后置重置（防 mock 残留污染）
```

### test_api.py 的 Mock 策略（端到端）

```python
# ① 伪造用户：MagicMock 但 id/username 必须是真实类型
def fake_current_user():
    user = mock.MagicMock()
    user.id = 1                    # 真实 int（thread_id 拼接用）
    user.username = "Alice"
    return user

# ② 绕过认证：dependency_overrides
app.dependency_overrides[get_current_user] = lambda: user

# ③ 替换 Agent：直接 patch 模块级变量
with mock.patch("backend.api._agent", mock_agent):
    response = client.post("/chat", json={...})
del app.dependency_overrides[get_current_user]   # 用完必清！

# ④ mock 数据库链：db.query().filter().first() 链式返回
mock_db.query.return_value.filter.return_value.first.return_value = None

# ⑤ 流式测试必须用真 AIMessage（后端 isinstance 检查，MagicMock 过不了）
real_msg = AIMessage(content="hello")
mock_agent.stream.return_value = [(real_msg, {})]
```

### test_concurrency.py（并发集成测试）

```python
# 真实 SqliteSaver + 假 LLM（FakeMessagesListChatModel，不联网）+ 20 线程
fake_llm = FakeMessagesListChatModel(responses=[AIMessage(content="ok")])
agent = create_agent(model=fake_llm, tools=[], checkpointer=saver)

def test_concurrent_invokes_no_locked_errors(sqlite_agent):
    # 20 线程并发 invoke 不同 thread_id → 断言无异常、结果完整

def test_thread_id_isolation(sqlite_agent):
    # A 问两轮、B 问一轮 → get_state 互相验证不串话

def test_agent_service_uses_wal_mode():
    with mock.patch("agent.agent.create_llm", return_value=mock.MagicMock()):
        service = AgentService()      # mock LLM：测试不依赖真实 API key
        assert service.conn.execute("PRAGMA journal_mode").fetchone()[0].upper() == "WAL"
```

### test_checkpoint_parsing.py（用真实序列化器造数据）

```python
def _make_blob(messages, ts=...) -> bytes:
    serde = JsonPlusSerializer()                       # 与 SqliteSaver 完全一致
    typed_msgs = [serde.dumps_typed(m) for m in messages]
    checkpoint = {"v": 1, "ts": ts, "channel_values": {"messages": typed_msgs}}
    _, blob = serde.dumps_typed(checkpoint)
    return blob
```

**为什么**：手造 msgpack 格式容易与真实格式偏差；用官方序列化器构造 = 测试即真实。

### 会话管理测试（tmp_path 造库）

```python
@pytest.fixture
def checkpoint_db(self, tmp_path):
    db_path = tmp_path / "checkpointer.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE checkpoints (...)")   # 手建最小表结构
    conn.execute("INSERT INTO checkpoints (thread_id, metadata) VALUES ('user_1_test-session', '{}')")
    return str(db_path)

# 测试时把 _get_checkpointer_db 指向临时库
with mock.patch("backend.api._get_checkpointer_db", return_value=checkpoint_db):
    response = client.put("/chat/sessions/user_1_test-session", json={"title": "我的车次查询"})
```

覆盖：重命名成功/空标题 422/越权 ok=False/不存在 ok=False + 删除成功（验证 DB 真的清了）/不存在。

**测试金字塔总结**：单元（schemas/settings/llm/tools）→ 集成（API 端到端 Mock）→ 并发（真 SqliteSaver 多线程）→ 格式兼容（真序列化器）。

---

# 阶段八 · 部署与工程化

## 第 29 章 · Docker

### 后端 Dockerfile

```dockerfile
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ ...  # 部分包需编译
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt    # 先装依赖（缓存层优化！）
COPY . .
RUN mkdir -p /app/shared/maps /app/chat_history /app/data && chmod -R 777 ...
VOLUME ["/app/chat_history", "/app/shared/maps", "/app/data"]
CMD ["uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

**层缓存技巧**：requirements 先 COPY 单独装依赖 → 代码改动不触发重装依赖。

### 前端 Dockerfile（多阶段）

```dockerfile
FROM node:22-alpine AS builder
COPY package.json package-lock.json ./
RUN npm ci                              # ci 比 install 快且严格按 lock
COPY . .
RUN npm run build-only
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

### docker-compose.yml 关键设计

```yaml
backend:
  environment:
    - maps_output_dir=/app/shared/maps          # 地图写共享卷
    - DATABASE_URL=sqlite:////app/data/users.db # 绝对路径（named volume）
  volumes:
    - ./chat_history:/app/chat_history          # 绑定挂载：对话持久化到宿主机
    - backend_data:/app/data
    - maps_data:/app/shared/maps
frontend:
  volumes:
    - maps_data:/usr/share/nginx/maps:ro        # Nginx 只读挂同一卷 → /maps/ 静态直出
```

**地图链路**：后端生成 → 共享卷 → Nginx 直接静态服务（不经后端转发）。

### nginx.conf 要点

```nginx
location / { try_files $uri $uri/ /index.html; }   # SPA 路由回退
location /maps/ { alias /usr/share/nginx/maps/; }
location /chat/ {
  proxy_pass http://backend:8000;                   # 容器名即 DNS
  proxy_buffering off;                              # SSE 必须关缓冲！
  proxy_read_timeout 300s;                          # 匹配后端单块超时
}
```

## 第 30 章 · CI（.github/workflows/ci.yml）

4 个并行 job：

1. **lint**：`ruff check . --select E9,F63,F7,F82`（只查致命错误，continue-on-error）
2. **test**：Python 3.10/3.11 矩阵 + `pytest-cov` 覆盖率 + pip 缓存（`hashFiles('requirements.txt')`）
3. **frontend**：`npm ci` → `type-check` → `build-only`（node 22 + npm 缓存）
4. **docker**：buildx 构建前后端镜像（push: false 只验证可构建）

顶层 `concurrency: group: ci-${{ github.ref }}, cancel-in-progress: true`——同分支新 push 取消旧跑。

## 第 31 章 · 启动脚本

### start-local.ps1（本地开发）

```powershell
$PythonCmd = "python"
if (Test-Path "C:/Users/1225/.conda/envs/railway-8620/python.exe") { $PythonCmd = ... }  # 自动找 conda
if (-not (Test-Path ".env")) { exit 1 }                                                   # 配置检查
$backend = Start-Process -FilePath $PythonCmd -ArgumentList "-m","uvicorn",... -PassThru -WindowStyle Hidden
# 健康检查：轮询 /docs 最多 15s，就绪才继续
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source   # Windows 必须 npm.cmd！
$frontend = Start-Process -FilePath $npmCmd -ArgumentList "run","dev" ... -PassThru
```

**踩坑**：`Start-Process npm` 找不到（Windows npm 是 npm.cmd）；PowerShell 字符串里的中文括号会被解析器误判。

### start.ps1（Docker 版）

`docker compose up -d` + 可选 `ragflow` 参数（起 RAGFlow 五件套 + 跑 `ragflow_init.py` 自动初始化）。

## 第 32 章 · 压测（benchmarks/）

```python
# benchmark_api.py 核心逻辑
token = get_token(base_url)                    # 注册或登录拿 JWT
with ThreadPoolExecutor(max_workers=concurrency) as pool:
    futures = [pool.submit(send_one, httpx.Client(...), token, message) for _ in range(requests)]
# 统计：QPS = requests/total_time；P50/P95/P99 = 排序后按分位取值×1000ms
# sys.stdout.reconfigure(encoding="utf-8")     # Windows GBK 控制台输出 emoji 必需
```

**实测数据**（并发 5 / 10 请求）：成功率 100%，QPS 0.4，平均延迟 12.5s，P95 27.2s。
**结论**：瓶颈在 LLM 推理 + RAGFlow 未启动时 Agent 反复重试检索（每次 4s 超时），系统本身（认证/路由/checkpoint）开销极小。

---

# 第 33 章 · 踩坑总录（面试弹药库）

| #  | 坑                        | 现象                                           | 解法                                         |
| -- | ------------------------- | ---------------------------------------------- | -------------------------------------------- |
| 1  | 同步流式阻塞事件循环      | 并发请求全卡死                                 | run_in_executor 有界线程池                   |
| 2  | StopIteration 穿越 Future | RuntimeError 破坏迭代                          | 哨兵对象`_SENTINEL`                        |
| 3  | Pydantic`_` 前缀类属性  | `cls._RE.match` AttributeError → 全接口 500 | 提为模块级常量                               |
| 4  | pydantic-settings 去引号  | 字面量 "DEEPSEEK_API_KEY" 被当 key → 401      | 正则判断环境变量引用                         |
| 5  | 地图路径三处不一致        | Docker 里 /maps 404                            | `maps_output_dir` 环境变量统一             |
| 6  | 未闭合 tool_calls         | 超时中断后会话永久损坏                         | 请求前`_repair_incomplete_tool_calls`      |
| 7  | msgpack ExtType(5)        | 历史会话无法读取                               | 三级降级解析 + 永不抛异常                    |
| 8  | RAGFlow batch_size=16     | DashScope 限 10 → 向量化失败                  | 容器补丁（幂等精确替换）                     |
| 9  | marked v17 renderer 签名  | TS 类型错误                                    | `code({text, lang})` 对象参数              |
| 10 | noUncheckedIndexedAccess  | 数组索引访问 TS 报错                           | 全部判空                                     |
| 11 | v-for 中 ref 是数组       | `input.focus is not a function`              | `@vue:mounted` 钩子取 el                   |
| 12 | window.prompt             | 自动化环境不支持                               | 行内编辑                                     |
| 13 | functools.wraps 遗漏      | 工具名变 wrapper                               | 装饰器必加 wraps                             |
| 14 | 登录 Form vs JSON         | 422 校验错误                                   | OAuth2PasswordRequestForm 用 FormData        |
| 15 | Windows GBK 控制台        | emoji 输出 UnicodeEncodeError                  | `sys.stdout.reconfigure(encoding="utf-8")` |
| 16 | Start-Process npm         | 找不到可执行文件                               | `Get-Command npm.cmd`                      |
| 17 | SQLite 并发锁             | database is locked                             | WAL + busy_timeout + check_same_thread=False |
| 18 | 无界线程池                | 线程爆炸放大锁竞争                             | `ThreadPoolExecutor(max_workers=8)`        |
| 19 | 测试明文密码              | argon2 InvalidHashError 500                    | 夹具用`ph.hash()` 造数据                   |
| 20 | mock 残留污染             | 单例跨测试泄漏                                 | autouse fixture 前后 reset                   |
| 21 | async 端点里的同步阻塞调用 | 修复期间事件循环被卡，其他请求全停             | `_repair_incomplete_tool_calls_async` 走 executor |

---

# 第 34 章 · 复习路线建议

**第一遍（理解骨架，2h）**：第 0 章 → 第 9 章（Agent）→ 第 15 章（流式）→ 0.4 的请求旅程
**第二遍（吃透细节，3h）**：第 13 章（反解）→ 第 17 章（补丁）→ 第 24 章（前端流式）→ 第 33 章（踩坑）
**第三遍（模拟面试）**：对着每章末尾的「面试考点」自问自答；让 AI 模拟追问

**必须能白板手写的三段代码**：

1. `chat_stream` 的 generate()（哨兵 + 双超时 + executor）
2. `_extract_one` 三级降级解析
3. `sendMessage` 的 reader 循环 + AbortError 处理
