"""
测试 backend/api.py —— 注册、登录、聊天接口的端到端测试

  测试策略:
    - 不启动真实服务器, 用 FastAPI 自带的 TestClient 在内存中发送请求
    - Mock 掉所有外部依赖: 数据库(SQLite)、Agent(LangGraph+LLM)、JWT 认证
    - 测试目标是验证路由逻辑(参数校验、状态码、响应格式), 不验证 LLM 生成质量
"""
import pytest
from unittest import mock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage  # 用于构造流式响应的真实消息对象
from argon2 import PasswordHasher              # 构造合法的 argon2 密码哈希

# 与后端 backend.auth.ph 行为一致的测试用哈希器
_ph = PasswordHasher()


def _hash_password(plain: str) -> str:
    """对明文密码做 argon2 哈希，模拟数据库中存储的密码字段"""
    return _ph.hash(plain)

# ── 导入 app 对象 ──────────────────────────────────────────────
# 注意: _agent 现在是懒加载（启动时为 None，首次请求时才创建）
# 导入 backend.api 不会触发 AgentService 初始化
# 测试通过 mock.patch("backend.api._agent") 直接替换, 不碰真实 LLM/Embedding
from backend.api import app
from backend.auth import get_current_user  # 用于 dependency_overrides 的 key

# ── TestClient 实例 ────────────────────────────────────────────
# TestClient 不启动真实 HTTP 服务器和端口
# 异步路由自动被 pytest-anyio 或 httpx 处理
# 请求在同一个进程内走完 FastAPI 的完整中间件/路由/依赖注入链
client = TestClient(app)

# ── 辅助函数 ───────────────────────────────────────────────────
def fake_current_user():
    """
    伪造一个已登录用户, 用于 mock 掉 get_current_user 依赖

    为什么不是纯 MagicMock():
      - 后端 /chat 路由会读取 current_user.id (拼接 thread_id)
      - MagicMock 默认返回子属性也是 MagicMock, 不是整数
      - 必须显式设 user.id = 1 (真实 int), 否则 ChatHistory 等地会接收 mock 对象进而异常

    返回:
      mock.MagicMock 对象, 其 .id=1, .username="Alice"
    """
    user = mock.MagicMock()
    user.id = 1               # 真实整数, 用于 f"user_{current_user.id}"
    user.username = "Alice"   # 真实字符串, 用于日志/鉴权逻辑
    return user


# ═══════════════════════════════════════════════════════════════
#  认证端点测试: /auth/register 和 /auth/login
#
#  这两个端点依赖:
#    - 数据库会话 (db: Session = Depends(get_db))
#    - 不需要 Agent
#
#  Mock 策略:
#    1. mock_db = mock.MagicMock() 模拟整个 SQLAlchemy 会话
#    2. 搭好链式调用链: db.query().filter().first() 的返回值
#    3. mock.patch("backend.database.SessionLocal") 拦截会话工厂
#       → 当后端写 db = SessionLocal() 时, 拿到的是 mock_db
# ═══════════════════════════════════════════════════════════════

class TestAuthEndpoints:
    """测试注册和登录接口"""

    def test_register_success(self):
        """
        正常注册: 用户名未被占用 → 返回 JWT token

        Mock 数据库链路:
          db.query(User) → MagicMock
            .filter(User.username == "Alice") → MagicMock
              .first() → None  (代表数据库中没有重名用户)

        预期:
          200 OK + {access_token: "...", token_type: "bearer"}
        """
        # ── 1. 搭建假数据库会话 ──
        mock_db = mock.MagicMock()
        # 链式调用: db.query(...).filter(...).first() → None
        # None 表示"未查到重复用户名", 注册可以继续
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # ── 2. 替换数据库会话工厂 ──
        # 后端代码: db = SessionLocal() 会被拦截, 返回我们准备好的 mock_db
        with mock.patch("backend.database.SessionLocal") as mock_session_factory:
            mock_session_factory.return_value = mock_db

            # ── 3. 发送注册请求 ──
            # TestClient.post 模拟 HTTP POST 到 /auth/register
            # json= 参数自动设置 Content-Type: application/json
            response = client.post(
                "/auth/register",
                json={
                    "username": "Alice",
                    "password": "123456"
                }
            )

            # ── 4. 验证响应 ──
            # 200: 注册成功
            # 响应体应包含 JWT access_token 和 token_type
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_register_duplicate_username(self):
        """
        重复注册: 用户名已存在 → 返回 400

        与 test_register_success 的唯一区别:
          .first() 返回不是 None, 而是任意对象(代表已存在的用户记录)

        预期:
          400 Bad Request + detail 包含 "already registered"
        """
        mock_db = mock.MagicMock()
        # 返回非 None → 代表"用户名已占用"
        mock_db.query.return_value.filter.return_value.first.return_value = mock.MagicMock()

        with mock.patch("backend.database.SessionLocal") as mock_session_factory:
            mock_session_factory.return_value = mock_db

            response = client.post("/auth/register", json={
                "username": "alice",
                "password": "123456"
            })

            assert response.status_code == 400
            # 后端返回的 detail 消息中应包含关键字
            assert "already registered" in response.json()["detail"]

    def test_login_success(self):
        """
        正确密码登录 → 返回 JWT token

        登录与注册有两个区别:
          1. 请求格式: 登录用 data= (application/x-www-form-urlencoded)
             而不是 json= (application/json), 因为 OAuth2PasswordRequestForm 这么要求
          2. .first() 返回一个带 .password 属性的假用户对象

        预期:
          200 OK + {access_token: "...", token_type: "bearer"}
        """
        mock_db = mock.MagicMock()
        # 构造一个假用户, 其 password 字段存储 argon2 哈希（与生产一致）
        # 旧测试用明文 "secret" 会触发 argon2 InvalidHashError（不属于 VerifyMismatchError）
        # 导致 except 捕获不到, 登录接口 500 而不是 200
        fake_user = mock.MagicMock()
        fake_user.username = "Alice"
        fake_user.password = _hash_password("secret")
        mock_db.query.return_value.filter.return_value.first.return_value = fake_user

        with mock.patch("backend.database.SessionLocal") as mock_session_factory:
            mock_session_factory.return_value = mock_db

            # 登录接口用 data= (form 格式), 不是 json=
            # 因为后端用的是 OAuth2PasswordRequestForm 依赖
            response = client.post("/auth/login", data={
                "username": "Alice",
                "password": "secret"   # 与哈希前明文一致 → 认证通过
            })

            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"

    def test_login_wrong_password(self):
        """
        密码错误 → 返回 401

        实现原理:
          设假用户 password="correct"
          请求中传 password="wrong_password"
          后端 authenticate_user 比对发现不一致 → 返回 False → 401

        预期:
          401 Unauthorized
        """
        mock_db = mock.MagicMock()
        fake_user = mock.MagicMock()
        fake_user.username = "Alice"
        # 数据库存的是 "correct" 的 argon2 哈希, 输入 "wrong_password" 应触发 VerifyMismatchError
        fake_user.password = _hash_password("correct")
        mock_db.query.return_value.filter.return_value.first.return_value = fake_user

        with mock.patch("backend.database.SessionLocal") as mock_session_factory:
            mock_session_factory.return_value = mock_db

            response = client.post("/auth/login", data={
                "username": "alice",
                "password": "wrong_password"  # 与 correct 不匹配 → 认证失败
            })

            assert response.status_code == 401

    def test_login_user_not_found(self):
        """
        用户不存在 → 返回 401

        实现原理:
          .first() 返回 None → authenticate_user 判断用户不存在 → 返回 False → 401

        预期:
          401 Unauthorized
        """
        mock_db = mock.MagicMock()
        # None = 数据库中查不到该用户名
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with mock.patch("backend.database.SessionLocal") as mock_session_factory:
            mock_session_factory.return_value = mock_db

            response = client.post("/auth/login", data={
                "username": "ghost",    # 不存在的用户名
                "password": "any"
            })

            assert response.status_code == 401


# ═══════════════════════════════════════════════════════════════
#  /chat 端点测试
#
#  需要同时 mock 两样东西:
#    1. backend.api._agent → 懒加载, 未配置时为 None
#       直接 mock.patch("backend.api._agent") 替换, _get_agent() 会返回 mock 对象
#    2. get_current_user → 用 app.dependency_overrides 绕过 JWT 认证
# ═══════════════════════════════════════════════════════════════

class TestChatEndpoint:
    """测试普通聊天接口 POST /chat"""

    def test_chat_requires_auth(self):
        """
        不带 token 直接访问 /chat → 应返回 401

        这是唯一不需要 mock 的 chat 测试:
          - 不 mock AgentService → 真实的 AgentService 初始化会报错
          - 但因为我们用的是 client = TestClient(app) 在模块级已导入
            不是在函数内才导入, app 已经在模块级初始化过了
            所以 AgentService() 已经在模块加载时执行
          - 不 mock get_current_user → FastAPI 的 Depends 会尝试真实解码 token
            但没有 token → 401

        预期:
          401 Unauthorized
        """
        # 注意: 这个测试依赖 AgentService 在模块导入时能成功初始化
        # 如果 AgentService.__init__ 报错(比如没装 Chroma), 这个测试也会失败
        response = client.post("/chat", json={"message": "你好"})
        assert response.status_code == 401

    def test_chat_success(self):
        """
        认证用户发送消息 → 返回 AI 回答

        核心 Mock:
          1. AgentService() 被拦截, 返回带 .agent 属性的假对象
          2. agent.invoke(...) 被拦截, 直接返回预制回答
          3. get_current_user 被拦截, 返回 fake_current_user()

        验证:
          - 200 OK
          - response["answer"] == 预制内容

        完整请求链路 (测试视角):
          请求 POST /chat {"message": "前进型蒸汽机车"}
            → get_current_user → 假用户(id=1)            [mock]
            → AgentService()  → 假 agent                 [mock]
            → agent.invoke(...) → {"messages": [假AI消息]} [mock]
            → 从 invoke 结果取 messages[-1].content
            → 返回 {"answer": "你好！我是铁路知识助手。"}
        """
        # ── 1. 伪造 Agent ──
        mock_agent = mock.MagicMock()

        # agent.invoke() 返回的结构: {"messages": [HumanMsg, ..., AIMsg]}
        # 后端取 messages[-1].content 作为回答
        mock_ai_msg = mock.MagicMock()
        mock_ai_msg.content = "你好！我是铁路知识助手。"   # 预制回答
        mock_agent.invoke.return_value = {"messages": [mock_ai_msg]}

        # ── 2. 绕过认证 ──
        user = fake_current_user()   # id=1, username="Alice"

        # ── 3. Mock ──
        # 直接替换模块级变量 backend.api._agent（agent 在模块加载时由 AgentService 初始化）
        # 同时用 FastAPI dependency_overrides 替代 get_current_user
        app.dependency_overrides[get_current_user] = lambda: user

        with mock.patch("backend.api._agent", mock_agent):
            # ── 4. 发送请求 ──
            response = client.post("/chat", json={"message": "前进型蒸汽机车"})

        # 清理 overrides, 避免污染后续测试
        del app.dependency_overrides[get_current_user]

        # ── 5. 验证响应 ──
        assert response.status_code == 200
        assert response.json()["answer"] == "你好！我是铁路知识助手。"

    def test_chat_passes_user_thread_id(self):
        """
        验证 user.id 被正确转为 thread_id 并传给 agent.invoke()

        为什么需要这个测试:
          - 后端用 f"user_{current_user.id}" 作为 LangGraph 的 thread_id
          - thread_id 是对话记忆隔离的关键: 不同用户有不同 thread_id
          - 如果 thread_id 不对, 所有用户的对话历史会串

        验证方式:
          不检查响应体, 用 mock_agent.invoke.call_args 抓取 invoke 被调用时的参数
          → 验证 config["configurable"]["thread_id"] == "user_1"

        call_args 结构:
          agent.invoke(input=input_data, config=config)
            → call_args[1]["config"] 就是传入的 config dict
            → call_args[1] 是关键字参数字典
        """
        mock_agent = mock.MagicMock()
        # invoke 必须返回非空结构, 否则后端 messages[-1] 会 IndexError
        mock_agent.invoke.return_value = {"messages": [mock.MagicMock(content="OK")]}

        user = fake_current_user()   # user.id = 1

        # 直接替换模块级 agent，绕过已初始化的 AgentService
        app.dependency_overrides[get_current_user] = lambda: user

        with mock.patch("backend.api._agent", mock_agent):
            # 发送请求
            client.post("/chat", json={"message": "测试"})

        # 清理 overrides
        del app.dependency_overrides[get_current_user]

        # ── 抓取 agent.invoke 被调用时的所有参数 ──
        # call_args 是 (args_tuple, kwargs_dict)
        # call_args[0] 是位置参数 (input=input_data 的那个 dict)
        # call_args[1] 是关键字参数 {"input": ..., "config": ...}
        call_args = mock_agent.invoke.call_args
        config = call_args[1]["config"]

            # 验证 thread_id 格式: "user_1"
        assert config["configurable"]["thread_id"] == "user_1"


# ═══════════════════════════════════════════════════════════════
#  /chat/stream 端点测试
#
#  与 /chat 的区别:
#    - 后端调用 agent.stream() 而不是 agent.invoke()
#    - 响应是 SSE (Server-Sent Events) 格式
#    - Content-Type: text/event-stream
#    - 响应体按 data: {...}\n\n 格式逐条发送
# ═══════════════════════════════════════════════════════════════

class TestChatStreamEndpoint:
    """测试流式聊天接口 POST /chat/stream"""

    def test_stream_requires_auth(self):
        """
        不带 token → 应返回 401

        与 test_chat_requires_auth 同理:
          - 不 mock 任何东西
          - FastAPI 的 Depends(get_current_user) 没有 token → 401
        """
        response = client.post("/chat/stream", json={"message": "你好"})
        assert response.status_code == 401

    def test_stream_yields_sse_format(self):
        """
        流式响应应包含 SSE (Server-Sent Events) 格式的数据

        Mock 策略:
          - agent.stream() 返回迭代器: [(AIMessage, metadata), ...]
          - 我们设它返回一个元组: (mock_msg, {})
            mock_msg.content = "流式"

        后端 generate() 的循环逻辑:
          for chunk in agent.stream(...):
            → 取出 (AIMessage, {})
            → 取 msg.content = "流式"
            → yield 'data: {"content": "流式"}\n\n'
          yield "data: [DONE]\n\n"

        验证:
          - 200 OK
          - Content-Type 包含 "text/event-stream"
          - 响应体包含 SSE 格式的 data 行和 [DONE] 结束标记
        """
        user = fake_current_user()

        # ── 1. 构造 stream 返回值 ──
        # agent.stream() 返回可迭代对象, 每个元素是 (消息, 元数据) 的元组
        # 必须用真实 AIMessage 对象, 因为后端的 isinstance(msg, (AIMessage, AIMessageChunk)) 检查
        # mock.MagicMock() 不通过 isinstance 检查, 会导致内容块被跳过
        real_msg = AIMessage(content="hello")

        mock_agent = mock.MagicMock()
        # stream 返回一个列表(可迭代), 只包含一个元组 → 产生一条 SSE 数据后结束
        mock_agent.stream.return_value = [(real_msg, {})]

        # ── 2. Mock ──
        # 直接替换模块级 agent
        app.dependency_overrides[get_current_user] = lambda: user

        with mock.patch("backend.api._agent", mock_agent):
            response = client.post("/chat/stream", json={"message": "你好"})

        # 清理 overrides
        del app.dependency_overrides[get_current_user]

        # ── 3. 验证 SSE 格式的响应 ──
        assert response.status_code == 200
        # SSE 协议的标准 Content-Type
        assert "text/event-stream" in response.headers["content-type"]

        # 响应体文本应包含:
        #   data: {"content": "hello"}  ← 一条 SSE 消息 (ASCII 避免 json.dumps Unicode 转义)
        #   data: [DONE]                ← SSE 结束标记
        body = response.text
        assert 'data: {"content": "hello"}' in body
        assert "data: [DONE]" in body

    def test_stream_pushes_error_event_on_exception(self):
        """
        验证：agent.stream() 抛异常时，后端应推送一条 error 事件并正常结束流

        回归 Bug：旧实现 generate() 没有 try/except，stream 抛错会直接中断
        StreamingResponse，前端一直转圈。修复后应推送 data: {"error": ...} 再 [DONE]。
        """
        user = fake_current_user()

        mock_agent = mock.MagicMock()
        # stream() 抛异常，模拟 LLM 调用失败 / 网络错误
        mock_agent.stream.side_effect = RuntimeError("LLM 服务不可用")

        app.dependency_overrides[get_current_user] = lambda: user

        with mock.patch("backend.api._agent", mock_agent):
            response = client.post("/chat/stream", json={"message": "你好"})

        del app.dependency_overrides[get_current_user]

        # 即使内部异常，HTTP 层应仍 200（SSE 已经开始），通过事件传递错误
        assert response.status_code == 200
        body = response.text
        # 必须包含 error 事件 + 结束标记，避免前端永久挂起
        assert '"error"' in body
        assert "LLM 服务不可用" in body
        assert "data: [DONE]" in body