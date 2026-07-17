"""测试 agent/tools.py —— retriever_tool / 服务单例"""
from unittest import mock


class TestRetrieverTool:
    def test_returns_merged_docs(self):
        client = mock.MagicMock()
        client.search.return_value = [
            {"content": "文档A", "source": "a.txt", "similarity": 0.9, "img_id": ""},
            {"content": "文档B", "source": "b.txt", "similarity": 0.8, "img_id": ""},
        ]

        with mock.patch("agent.tools.get_ragflow_client", return_value=client):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "测试"})
            assert "文档A" in result
            assert "文档B" in result
            assert "\n\n" in result

    def test_returns_hint_when_no_results(self):
        client = mock.MagicMock()
        client.search.return_value = []

        with mock.patch("agent.tools.get_ragflow_client", return_value=client):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "不存在"})
            assert result == "未找到相关消息"

    def test_single_doc_no_extra_separator(self):
        client = mock.MagicMock()
        client.search.return_value = [
            {"content": "唯一文档", "source": "doc.txt", "similarity": 0.95, "img_id": ""},
        ]

        with mock.patch("agent.tools.get_ragflow_client", return_value=client):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "查"})
            assert "唯一文档" in result
            assert "\n\n" not in result

    def test_passes_query_correctly(self):
        client = mock.MagicMock()
        client.search.return_value = []

        with mock.patch("agent.tools.get_ragflow_client", return_value=client):
            from agent.tools import retriever_tool
            retriever_tool.invoke({"query": "前进型蒸汽机车"})
            client.search.assert_called_once()
            args, kwargs = client.search.call_args
            assert kwargs.get("query") == "前进型蒸汽机车"

    def test_single_result_has_no_number_prefix(self):
        """单条结果不应带编号前缀"""
        client = mock.MagicMock()
        client.search.return_value = [
            {"content": "单条内容", "source": "x.txt", "similarity": 0.9, "img_id": ""},
        ]
        with mock.patch("agent.tools.get_ragflow_client", return_value=client):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "test"})
            assert result == "1. 单条内容（来源: x.txt）"


class TestServiceSingleton:
    """验证 get_ragflow_client 单例行为"""

    def test_ragflow_client_is_singleton(self):
        from agent.tools import get_ragflow_client, reset_service_singletons
        reset_service_singletons()
        with mock.patch("agent.tools.RAGFlowClient", return_value=mock.MagicMock()):
            s1 = get_ragflow_client()
            s2 = get_ragflow_client()
            assert s1 is s2

    def test_reset_clears_singleton(self):
        from agent.tools import get_ragflow_client, reset_service_singletons
        reset_service_singletons()
        with mock.patch("agent.tools.RAGFlowClient", return_value=mock.MagicMock()):
            s1 = get_ragflow_client()
        reset_service_singletons()
        with mock.patch("agent.tools.RAGFlowClient", return_value=mock.MagicMock()):
            s2 = get_ragflow_client()
            assert s1 is not s2