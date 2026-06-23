import os
import sys
import tempfile
import pytest

# 确保项目根目录在 Python 搜索路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

@pytest.fixture
def temp_dir():
    """返回一个临时路径, 测试结束后自动删除"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir