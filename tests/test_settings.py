"""
测试 settings.py —— 默认值、环境变量读取、路径补全

注意：Chroma 相关配置（collection_name, chunk_size 等）已移除，
      现在配置专注于 RAGFlow。
"""
import os 
from unittest import mock

class TestSettingsDefaults:
    """验证 Settings 类每个字段的默认值"""

    def test_default_ragflow_host(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_host == "http://localhost:9380"

    def test_default_kwargs(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.kwargs == 5

    def test_default_similarity_threshold(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_similarity_threshold == 0.0

    def test_default_llm_provider(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.llm_provider == "openai"

    def test_default_ragflow_api_key_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_api_key == ""

    def test_default_ragflow_dataset_id_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_dataset_id == ""


class TestSettingsFromEnv:
    """验证settings能从环境变量中读取值"""

    def test_model_name_from_env(self):
        with mock.patch.dict(os.environ, {"llm_model_name":"deepseek-v4-air"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.llm_model_name == "deepseek-v4-air"

    def test_api_key_from_env(self):
        with mock.patch.dict(os.environ, {"llm_api_key":"sk-test-114514"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.llm_api_key == "sk-test-114514"

    def test_embedding_api_key_from_env(self):
        with mock.patch.dict(os.environ, {"embedding_api_key":"sk-test-1919810"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.embedding_api_key == "sk-test-1919810"

    def test_ragflow_api_key_from_env(self):
        with mock.patch.dict(os.environ, {"ragflow_api_key":"sk-ragflow-001"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_api_key == "sk-ragflow-001"

    def test_ragflow_host_from_env(self):
        with mock.patch.dict(os.environ, {"ragflow_host": "http://192.168.1.100:9380"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_host == "http://192.168.1.100:9380"

    def test_ragflow_dataset_id_from_env(self):
        with mock.patch.dict(os.environ, {"ragflow_dataset_id": "ds-001"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.ragflow_dataset_id == "ds-001"

    def test_base_url_from_env(self):
        with mock.patch.dict(os.environ, {"llm_base_url": "https://my-proxy.com/v1"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.llm_base_url == "https://my-proxy.com/v1"

    def test_embedding_model_from_env(self):
        with mock.patch.dict(os.environ, {"embedding_model_name": "text-embedding-v3"}, clear=True):
            from settings import Settings
            s = Settings()
            assert s.embedding_model_name == "text-embedding-v3"


class TestSettingsPathResolution:
    """验证settings.py的底部自动补全逻辑"""

    def test_data_path_not_empty(self):
        from settings import settings as s
        assert s.data_path != ""

    def test_chat_history_storage_path_not_empty(self):
        from settings import settings as s
        assert s.chat_history_storage_path != ""


class TestSettingsMeta:
    """Settings 类的元行为"""

    def test_session_config_is_dict(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert isinstance(s.session_config, dict)
            assert "configurable" in s.session_config

    def test_extra_fields_ignored(self):
        """extra='ignore'->不存在的字段不会出现"""
        with mock.patch.dict(os.environ, {}, clear=True):
            from settings import Settings
            s = Settings()
            assert not hasattr(s, "this_never_existed")