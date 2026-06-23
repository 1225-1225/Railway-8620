"""
测试 backend/schema.py —— Pydantic 数据校验
"""
import pytest
from backend.schemas import UserCreate, Token

class TestUserCreate:
    """测 UserCreate schema"""
    def test_valid_data(self):
        user = UserCreate(username="Alice", password="123")
        assert user.username == "Alice"
        assert user.password == "123"

    def test_model_dump(self):
        user = UserCreate(username="bob", passward="secret")
        assert user.model_dump() == {"username": "bob", "password": "secret"}

    def test_int_username_rejected(self):
        """username 是 str 类型, 传 int 应报错"""
        with pytest.raises(Exception):
            UserCreate(username=123, password="ok")

    def test_empty_string_accepted(self):
        """空字符串仍是合法 str, Pydantic 不会拒绝"""
        user = UserCreate(username="", password="ok")
        assert user.username == ""

class TestToken:
    """测 Token schema"""

    def test_valid_token(self):
        token = Token(access_token="eyJxxx", token_type="bearer")
        assert token.access_token == "eyJxxx"
        assert token.token_type == "bearer"
    
    def test_missing_access_token_raises(self):
        with pytest.raises(Exception):
            Token(token_type="bearer")

    def test_missing_token_type_raises(self):
        with pytest.raises(Exception):
            Token(access_token="abc")