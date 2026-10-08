from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

from settings import settings as config_data

# 数据库连接地址：统一从 settings 读取（来自 .env 的 DATABASE_URL，未配置则回退 users.db）
# 生产部署建议通过 .env 显式指定绝对路径，避免 cwd 不可控
SQLALCHEMY_DATABASE_URL = config_data.database_url
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    # 属性名特意叫 password_hash 而非 password：
    # 这个字段存的是 argon2 哈希，而请求体模型 schemas.UserCreate.password 是明文输入。
    # 两者同名时极易看混（甚至在 `User(..., password=ph.hash(user.password))` 里同现），
    # 改成语义明确的名字后，忘记 ph.hash() 一眼就能看出。
    #
    # Column("password", ...) 的第一个参数是**数据库列名**，所以沿用旧列名——
    # 已有 users.db 无需任何迁移。
    password_hash = Column("password", String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()