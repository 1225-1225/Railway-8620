"""测试 agent/tools.py —— retriever_tool / route_map_drawing_tool / 服务单例"""
import os
from unittest import mock


class TestRetrieverTool:
    def test_returns_merged_docs(self):
        doc1 = mock.MagicMock()
        doc1.page_content = "文档A"
        doc2 = mock.MagicMock()
        doc2.page_content = "文档B"

        ret = mock.MagicMock()
        ret.invoke.return_value = [doc1, doc2]

        vs = mock.MagicMock()
        vs.get_retriever.return_value = ret

        # 注意：tools.py 改为走 get_vector_store_service() 单例
        # mock VectorStoreService 类即可，单例首次访问时调用 VectorStoreService() 返回 vs
        with mock.patch("agent.tools.VectorStoreService", return_value=vs):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "测试"})
            assert "文档A" in result
            assert "文档B" in result
            assert "\n\n" in result

    def test_returns_hint_when_no_results(self):
        ret = mock.MagicMock()
        ret.invoke.return_value = []

        vs = mock.MagicMock()
        vs.get_retriever.return_value = ret

        with mock.patch("agent.tools.VectorStoreService", return_value=vs):
            from agent.tools import retriever_tool
            result = retriever_tool.invoke({"query": "不存在"})
            assert result == "未找到相关消息"

    def test_single_doc_no_extra_separator(self):
        doc = mock.MagicMock()
        doc.page_content = "唯一文档"

        ret = mock.MagicMock()
        ret.invoke.return_value = [doc]

        vs = mock.MagicMock()
        vs.get_retriever.return_value = ret

        with mock.patch("agent.tools.VectorStoreService", return_value=vs):
            from agent.tools import retriever_tool

            result = retriever_tool.invoke({"query": "查"})
            assert result == "唯一文档"
            assert "\n\n" not in result

    def test_passes_query_correctly(self):
        ret = mock.MagicMock()
        ret.invoke.return_value = []

        vs = mock.MagicMock()
        vs.get_retriever.return_value = ret

        with mock.patch("agent.tools.VectorStoreService", return_value=vs):
            from agent.tools import retriever_tool

            retriever_tool.invoke({"query": "前进型蒸汽机车"})
            ret.invoke.assert_called_once_with("前进型蒸汽机车")


class TestServiceSingleton:
    """验证 get_vector_store_service 单例行为"""

    def test_vector_store_service_is_singleton(self):
        """同一进程内多次获取应返回同一实例"""
        from agent.tools import get_vector_store_service, reset_service_singletons
        reset_service_singletons()
        with mock.patch("agent.tools.VectorStoreService", return_value=mock.MagicMock()):
            s1 = get_vector_store_service()
            s2 = get_vector_store_service()
            assert s1 is s2

    def test_reset_clears_singleton(self):
        from agent.tools import (
            get_vector_store_service,
            reset_service_singletons,
        )
        reset_service_singletons()
        with mock.patch("agent.tools.VectorStoreService", return_value=mock.MagicMock()):
            s1 = get_vector_store_service()
        reset_service_singletons()
        with mock.patch("agent.tools.VectorStoreService", return_value=mock.MagicMock()):
            s2 = get_vector_store_service()
            assert s1 is not s2


