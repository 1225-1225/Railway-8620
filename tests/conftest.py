import os
import sys
import tempfile

# ── 测试环境变量必须在 import backend.* 之前设置 ──────────────
# JWT_SECRET_KEY：生产中要求显式提供，测试环境注入固定值，避免 SECRET_KEY=None 导致签发/校验抛错
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-not-for-prod")
# DATABASE_URL：测试中大多 mock 掉 SessionLocal，但保留默认值避免导入 database.py 时意外写到仓库根目录
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_users.db")

# 确保项目根目录在 Python 搜索路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import pytest


@pytest.fixture
def temp_dir():
    """返回一个临时路径, 测试结束后自动删除"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(autouse=True)
def _reset_service_singletons():
    """每个测试用例前后重置 agent.tools 中的服务单例

    为什么需要：tools.py 改成模块级单例后，若某个测试 mock 了 RAGFlowClient
    的构造函数并触发了实例化，单例会残留，污染后续测试。
    autouse=True 保证每个测试独立。
    """
    # 在测试前重置（防止上一次残留）
    try:
        from agent.tools import reset_service_singletons
        reset_service_singletons()
    except Exception:
        # tools 模块在测试环境中可能因依赖缺失无法导入，留给具体测试处理
        pass
    yield
    # 在测试后重置（防止本次污染下一次）
    try:
        from agent.tools import reset_service_singletons
        reset_service_singletons()
    except Exception:
        pass