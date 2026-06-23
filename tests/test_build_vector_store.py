"""测试 agent/build_vector_store.py —— MD5 计算、检查、保存"""
import os
import tempfile
from unittest import mock
from agent.build_vector_store import get_str_md5, check_md5, save_md5

class TestGetStrMd5:
    """测 get_str_md5 —— 纯函数, 无依赖"""

    def test_same_input_same_output(self):
        assert get_str_md5("hello") == get_str_md5("hello")

    def test_different_input_different_output(self):
        assert get_str_md5("hello") != get_str_md5("world")

    def test_empty_string_known_md5(self):
        # 空字符串 MD5 的标准值
        assert get_str_md5("") == "d41d8cd98f00b204e9800998ecf8427e"

    def test_chinese_text_works(self):
        result = get_str_md5("你好世界")
        assert len(result) == 32

    def test_md5_is_32_char_hex(self):
        result = get_str_md5("test")
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)

class TestCheckMd5:
    """测 check_md5 —— 需要临时目录放 MD5 文件"""

    def test_file_not_exists_returns_false(self, temp_dir):
        md5_file = os.path.join(temp_dir, "nonexistent.md5")
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5("abc123") is False

    def test_md5_found_returns_true(self, temp_dir):
        md5_file = os.path.join(temp_dir, "md5.txt")
        with open(md5_file, "w", encoding="utf-8") as f:
            f.write("abc123\n")
            f.write("def456\n")
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5("abc123") is True
            assert check_md5("def456") is True

    def test_md5_not_found_returns_false(self, temp_dir):
        md5_file = os.path.join(temp_dir, "md5.txt")
        with open(md5_file, "w", encoding="utf-8") as f:
            f.write("abc123\n")
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5("not_found") is False

    def test_empty_file_returns_false(self, temp_dir):
        md5_file = os.path.join(temp_dir, "md5.txt")
        with open(md5_file, "w", encoding="utf-8") as f:
            pass  # 空文件
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5("anything") is False

    def test_partial_match_does_not_count(self, temp_dir):
        """"abc" 不应匹配到 "abc123def"，必须是整行相等"""
        md5_file = os.path.join(temp_dir, "md5.txt")
        with open(md5_file, "w", encoding="utf-8") as f:
            f.write("abc123def\n")
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5("abc") is False

class TestSaveMd5:
    """测 save_md5"""

    def test_save_appends_to_file(self, temp_dir):
        md5_file = os.path.join(temp_dir, "md5.txt")
        with open(md5_file, "w", encoding="utf-8") as f:
            f.write("existing1\n")
        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            save_md5("new_value")
        with open(md5_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines()]
        assert "existing1" in lines
        assert "new_value" in lines

class TestMd5Integration:
    """端到端：计算 → 检查(无) → 保存 → 检查(有)"""

    def test_full_workflow(self, temp_dir):
        md5_file = os.path.join(temp_dir, "workflow.md5")
        computed = get_str_md5("需要去重的文本内容")

        with mock.patch("agent.build_vector_store.config_data") as cfg:
            cfg.md5_path = md5_file
            assert check_md5(computed) is False   # 第一次：不存在
            save_md5(computed)                     # 保存
            assert check_md5(computed) is True     # 第二次：存在