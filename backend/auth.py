# backend/auth.py
# 认证模块：处理用户的注册、登录、JWT 令牌签发与验证

# === 导入标准库 ===
from datetime import datetime, timedelta   # 时间处理：获取当前时间、计算过期时间
import os

# === 加载 .env 文件到环境变量（供 os.getenv 读取） ===
from dotenv import load_dotenv
load_dotenv()

# === 导入第三方库 ===
from jose import JWTError, jwt              # JWT 库：jwt.encode 签发令牌，jwt.decode 验证令牌
from fastapi import APIRouter, Depends, HTTPException, status  # FastAPI：路由、依赖注入、HTTP 异常、状态码
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer  # OAuth2：提取表单登录数据、提取 Bearer Token
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# === 导入项目内部模块 ===
from sqlalchemy.orm import Session          # SQLAlchemy：数据库会话类型注解
from . import database, schemas             # 同级包：database（数据库模型）、schemas（请求/响应数据结构）

# ============================================================
# 常量与配置
# ============================================================

# JWT 签名密钥：必须通过环境变量 .env 中的 JWT_SECRET_KEY 提供
# 未配置时为 None，create_access_token / jwt.decode 会直接抛错（拒绝静默使用弱密钥）
SECRET_KEY = os.getenv("JWT_SECRET_KEY")

# JWT 签名算法：HS256（HMAC-SHA256，对称加密，签验共用同一个密钥）
ALGORITHM = "HS256"

# 令牌默认过期时间：300 分钟（5 小时）
ACCESS_TOKEN_EXPIRE_MINUTES = 300  # 5h

# OAuth2 Bearer Token 提取器
# 自动从请求头 "Authorization: Bearer <token>" 中提取 token 字符串
# tokenUrl 告诉 Swagger 文档去哪里获取 token（用于交互式文档中的 "Authorize" 按钮）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# 创建一个 PasswordHasher 实例
ph = PasswordHasher()


# ============================================================
# 辅助函数
# ============================================================

def authenticate_user(db: Session, username: str, password: str):
    """
    验证用户身份。
    参数：
        db       — 数据库会话
        username — 用户名
        password — 明文密码
    返回：
        验证通过 → User 对象
        验证失败 → False
    """
    # 在 User 表中按用户名精确查找
    user = db.query(database.User).filter(database.User.username == username).first()
    # 如果用户不存在 或 密码不匹配 -> 返回 False
    if not user:
        return False
    try:
        ph.verify(user.password, password)
        # 验证通过，返回用户对象
        return user
    except VerifyMismatchError:
        return False



def create_access_token(data: dict, expires_delta: timedelta = None):
    """
    生成 JWT 访问令牌。
    参数：
        data          — 要编码到 payload 中的数据（必须包含 "sub" 字段表示用户身份）
        expires_delta — 可选，自定义过期时间
    返回：
        JWT 令牌字符串
    """
    # 1. 拷贝 data，避免修改传入的原始字典
    to_encode = data.copy()

    # 2. 计算过期时间
    if expires_delta:
        # 有自定义过期时间：当前 UTC 时间 + 传入的 timedelta
        expire = datetime.utcnow() + expires_delta
    else:
        # 无自定义过期时间：默认 15 分钟后过期
        expire = datetime.utcnow() + timedelta(minutes=15)

    # 3. 将过期时间 "exp" 注入 payload（JWT 标准字段）
    to_encode.update({"exp": expire})

    # 4. 使用密钥和指定算法对 payload 进行签名，生成 JWT 字符串
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ============================================================
# 依赖函数
# ============================================================

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    """
    FastAPI 依赖注入函数。
    作用：解析请求中的 JWT 令牌 → 解码 → 查数据库 → 返回当前用户。
    用在需要登录才能访问的路由中。

    参数由 FastAPI 自动注入：
        token - 通过 oauth2_scheme 从 Authorization 头提取
        db    - 通过 database.get_db 获取数据库会话
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(database.User).filter(database.User.username == username).first()
    if user is None:
        raise credentials_exception

    return user


# ============================================================
# 路由
# ============================================================

# 创建一个路由器，所有路由的前缀都是 "/auth"，在 API 文档中归类到 "auth" 标签下
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    POST /auth/register
    注册新用户。
    请求体（JSON）：{"username": "xxx", "password": "xxx"}  → 由 UserCreate schema 校验
    响应体（JSON）：{"access_token": "eyJ...", "token_type": "bearer"}
    """
    # 1. 检查用户名是否已被注册
    existing_user = db.query(database.User).filter(database.User.username == user.username).first()
    if existing_user:
        # 400 请求错误：用户名已存在
        raise HTTPException(status_code=400, detail="Username already registered")

    # 2. 创建新用户
    new_user = database.User(username=user.username, password=ph.hash(user.password))

    # 3. 写入数据库
    db.add(new_user)    # 添加到会话
    db.commit()         # 提交事务
    db.refresh(new_user)  # 刷新实例（从数据库加载自动生成的字段，如 id）

    # 4. 为新用户签发 JWT 令牌（按配置的 5 小时过期）
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.username}, expires_delta=access_token_expires
    )

    # 5. 返回令牌
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    """
    POST /auth/login
    用户登录。
    请求体（Form 格式）：username=xxx&password=xxx   → 由 OAuth2PasswordRequestForm 自动解析
    响应体（JSON）：{"access_token": "eyJ...", "token_type": "bearer"}
    """
    # 1. 验证用户名和密码
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        # 用户名或密码错误 → 401 未授权
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 验证通过，签发 JWT 令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )

    # 3. 返回令牌
    return {"access_token": access_token, "token_type": "bearer"}
