"""测试 backend/database.py —— User ORM 模型与CRUD"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, User

@pytest.fixture
def db():
    """每个测试独立的 SQLite 内存数据库"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

class TestUserModel:
    """测 ORM 模型定义"""
    def test_create_and_query(self, db):
        user = User(username="test", password="123")
        db.add(user)
        db.commit()

        found = db.query(User).filter(User.username == "test").first()
        assert found is not None
        assert found.password == "123"

    def test_id_auto_increment(self, db):
        u1 = User(username="a", password="1")
        u2 = User(username="b", password="2")
        db.add_all([u1, u2])
        db.commit()
        assert u2.id == u1.id + 1

    def test_username_unique(self, db):
        db.add(User(username="dup", password="1"))
        db.commit()
        db.add(User(username="dup", password="2"))
        with pytest.raises(Exception):
            # 违反 UNIQUE 约束
            db.commit()
        
    def test_password_cannot_be_null(self, db):
        db.add(User(username="test", password=None))
        with pytest.raises(Exception):
            db.commit()

    def test_create_at_auto_filled(self, db):
        user = User(username="time_test", password="1")
        db.add(user)
        db.commit()
        assert user.created_at is not None

class TestUserCrud:
    """测 CRUD 操作"""
    def test_delete(self, db):
        user = User(username="del", password="1")
        db.add(user)
        db.commit()
        db.delete(user)
        db.commit()

        found = db.query(User).filter(User.username == "del").first()
        assert found is None
    
    def test_bulk_insert_and_count(self, db):
        users = [User(username=f"u{i}", password=f"p{i}") for i in range(5)]
        db.add_all(users)
        db.commit()
        assert db.query(User).count() == 5