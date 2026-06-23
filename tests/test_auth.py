"""
测试 backend/auth.py —— JWT 令牌生成、校验、用户认证
"""
# === 导入标准库 ===
from datetime import timedelta       # 时间差类型：用于自定义 JWT 过期时间

# === 导入测试框架 ===
from unittest import mock            # mock：伪造对象，替代真实的数据库会话
import pytest                        # pytest：断言框架

# === 导入第三方库 ===
from jose import jwt                  # JWT 库：jwt.decode 解码验证测试中生成的 token

# === 导入被测模块 ===
from backend.auth import create_access_token, authenticate_user  # 被测函数
from backend.auth import SECRET_KEY, ALGORITHM                   # 密钥和算法常量


# ============================================================
# 测试类一：create_access_token —— JWT 令牌生成
# ============================================================

class TestCreateAccessToken:
    """测 create_access_token —— 真实生成，不 mock，直接解码验证"""

    def test_create_valid_jwt(self):
        """
        验证：生成的 JWT 能被正确解码，且包含传入的数据。
        """
        # 第1步：生成一个 token，payload 中放入用户名 "alice"
        token = create_access_token(data={"sub": "alice"})

        # 第2步：用同一个 SECRET_KEY 和 ALGORITHM 解码，验证 token 合法性
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 第3步：断言解码后的 sub 字段就是 "alice"
        assert payload["sub"] == "alice"
        # 第4步：断言 token 中包含过期时间 exp 字段
        assert "exp" in payload

    def test_custom_expiry(self):
        """
        验证：传入自定义过期时间后，token 的 exp 字段正常存在。
        """
        # 生成 token，明确指定 60 分钟后过期
        token = create_access_token(
            data={"sub": "bob"},
            expires_delta=timedelta(minutes=60)      # 自定义 60 分钟过期
        )
        # 解码验证
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # 确保 exp 字段存在（精确的时间值不容易断言，只验证存在即可）
        assert "exp" in payload

    def test_different_users_different_tokens(self):
        """
        验证：不同用户生成的 token 不一样（即使 data 只有 sub 不同）。
        """
        t1 = create_access_token(data={"sub": "alice"})
        t2 = create_access_token(data={"sub": "bob"})
        # 两个 token 字符串必须不同
        assert t1 != t2

    def test_extra_data_preserved(self):
        """
        验证：payload 中的额外字段（如 role）能被完整保留。
        """
        # 在 data 中放入 sub 和额外的 role 字段
        token = create_access_token(data={"sub": "alice", "role": "admin"})
        # 解码验证
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # role 字段应该被保留在 payload 中
        assert payload["role"] == "admin"


# ============================================================
# 测试类二：JWT 解码异常
# ============================================================

class TestJwtDecoding:
    """解码异常情况 —— 密钥不对、算法不对都应报错"""

    def test_wrong_key_fails(self):
        """
        验证：用错误密钥解码 -> 抛异常（签名验证失败）。
        """
        # 先生成一个正常的 token
        token = create_access_token(data={"sub": "test"})
        # 用错误密钥解码，预期抛出异常
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-key", algorithms=[ALGORITHM])

    def test_wrong_algorithm_fails(self):
        """
        验证：用错误算法解码 -> 抛异常。
        token 用 HS256 签发的，拿 RS256 去验应当失败。
        """
        # 先生成一个正常的 token（HS256 签名）
        token = create_access_token(data={"sub": "test"})
        # 用 RS256 算法去解码，预期抛出异常
        with pytest.raises(Exception):
            jwt.decode(token, SECRET_KEY, algorithms=["RS256"])


# ============================================================
# 测试类三：authenticate_user —— 用户认证
# ============================================================

class TestAuthenticateUser:
    """
    测 authenticate_user —— 需要 mock SQLAlchemy Session。
    因为测试环境没有真实数据库，用 mock.MagicMock() 伪造 db 的行为。
    """

    def test_correct_password_returns_user(self):
        """
        验证：密码正确 → 返回用户对象。
        """
        # 1. 创建一个假的数据库会话对象（不连接真实数据库）
        db = mock.MagicMock()

        # 2. 创建一个假的用户对象，设置密码为 "secret123"
        fake_user = mock.MagicMock()
        fake_user.password = "secret123"

        # 3. 配置 db 的行为：当调用 db.query(...).filter(...).first() 时，返回 fake_user
        #    SQLAlchemy 的链式调用: db.query(User).filter(User.username == "alice").first()
        #    mock 需要模拟整个调用链：
        #      db.query()           → query_mock
        #      query_mock.filter()  → filter_mock
        #      filter_mock.first()  → .return_value = fake_user
        db.query.return_value.filter.return_value.first.return_value = fake_user

        # 4. 调用被测函数，传入伪造的 db、用户名 "alice"、密码 "secret123"
        result = authenticate_user(db, "alice", "secret123")

        # 5. 密码匹配 → 应该返回 fake_user 对象
        assert result == fake_user

    def test_wrong_password_returns_false(self):
        """
        验证：密码错误 → 返回 False。
        """
        # 1. 伪造 db 和用户对象
        db = mock.MagicMock()
        fake_user = mock.MagicMock()
        fake_user.password = "correct_password"       # 正确密码是 "correct_password"
        db.query.return_value.filter.return_value.first.return_value = fake_user

        # 2. 用错误密码调用 authenticate_user
        result = authenticate_user(db, "alice", "wrong_password")

        # 3. 断言返回 False（认证失败）
        assert result is False

    def test_user_not_found_returns_false(self):
        """
        验证：用户不存在 → 返回 False。
        """
        # 1. 伪造 db，让查询返回 None（表示用户不存在）
        db = mock.MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        # 2. 调用被测函数，用户名 "ghost" 不存在
        result = authenticate_user(db, "ghost", "any")

        # 3. 断言返回 False
        assert result is False
