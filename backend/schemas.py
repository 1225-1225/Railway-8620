# backend/schemas.py
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    # 字段名必须保持 password：它是前端请求体的字段名（对外接口契约）。
    # 这里的值是**明文输入**——入库前必须 ph.hash()，
    # 对应 database.User 里那个存哈希的 password_hash 字段。
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str