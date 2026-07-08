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
    """验证 get_vector_store_service / get_route_map_service 单例行为"""

    def test_vector_store_service_is_singleton(self):
        """同一进程内多次获取应返回同一实例"""
        from agent.tools import get_vector_store_service, reset_service_singletons
        reset_service_singletons()
        with mock.patch("agent.tools.VectorStoreService", return_value=mock.MagicMock()):
            s1 = get_vector_store_service()
            s2 = get_vector_store_service()
            assert s1 is s2

    def test_route_map_service_is_singleton(self):
        from agent.tools import get_route_map_service, reset_service_singletons
        reset_service_singletons()
        with mock.patch("agent.tools.RouteMapService", return_value=mock.MagicMock()):
            s1 = get_route_map_service()
            s2 = get_route_map_service()
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


class TestRouteMapDrawingTool:
    """测试 route_map_drawing_tool —— 按车次代码绘制路线图"""

    def test_returns_map_url(self, temp_dir):
        """正常绘制：返回包含 [MAP]/maps/...html[/MAP] 的结果"""
        service = mock.MagicMock()
        service.draw_train_route.return_value = (
            os.path.join(temp_dir, "route_G1.html"),
            ["北京南", "南京南", "上海虹桥"],
        )

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import route_map_drawing_tool

            result = route_map_drawing_tool.invoke({"train_code": "G1"})

        assert "[MAP]/maps/route_G1.html[/MAP]" in result
        assert "北京南" in result
        assert "上海虹桥" in result
        assert "共 3 站" in result
        service.draw_train_route.assert_called_once_with("G1", temp_dir)

    def test_train_not_found_returns_hint(self, temp_dir):
        """车次不存在：返回未找到提示"""
        service = mock.MagicMock()
        service.draw_train_route.return_value = (None, None)

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import route_map_drawing_tool

            result = route_map_drawing_tool.invoke({"train_code": "X99999"})
            assert "未找到" in result
            assert "X99999" in result

    def test_service_exception_returns_error(self, temp_dir):
        """服务异常：返回错误提示，不抛异常"""
        service = mock.MagicMock()
        service.draw_train_route.side_effect = RuntimeError("GPKG 读取失败")

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import route_map_drawing_tool

            result = route_map_drawing_tool.invoke({"train_code": "G1"})
            assert "绘制路线图时出错" in result
            assert "GPKG 读取失败" in result

    def test_passes_train_code_correctly(self, temp_dir):
        """车次代码原样传递给服务（不大写化、不提取）"""
        service = mock.MagicMock()
        service.draw_train_route.return_value = (
            os.path.join(temp_dir, "route_K4174.html"),
            ["合肥", "北京西"],
        )

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import route_map_drawing_tool

            route_map_drawing_tool.invoke({"train_code": "K4174"})
            service.draw_train_route.assert_called_once_with("K4174", temp_dir)


class TestStationRouteDrawingTool:
    """测试 station_route_drawing_tool —— 按起终点站查找车次并绘制路线图"""

    def test_multiple_trains_all_success(self, temp_dir):
        """正常绘制多趟车次：返回包含多个 [MAP] 块的结果"""
        service = mock.MagicMock()
        service.find_trains_between_stations.return_value = [
            ("G1", "07:00", "北京南", "上海虹桥", ["北京南", "南京南", "上海虹桥"]),
            ("G13", "10:00", "北京南", "上海虹桥", ["北京南", "上海虹桥"]),
        ]
        service.draw_train_route.side_effect = [
            (os.path.join(temp_dir, "route_G1.html"), ["北京南", "南京南", "上海虹桥"]),
            (os.path.join(temp_dir, "route_G13.html"), ["北京南", "上海虹桥"]),
        ]

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            result = station_route_drawing_tool.invoke({
                "start_station": "北京南", "end_station": "上海虹桥"
            })

        assert "[MAP]/maps/route_G1.html[/MAP]" in result
        assert "[MAP]/maps/route_G13.html[/MAP]" in result
        assert "G1（07:00 发车" in result
        assert "G13（10:00 发车" in result
        assert "（共 2 趟）" in result
        assert service.find_trains_between_stations.called
        assert service.draw_train_route.call_count == 2

    def test_no_trains_found(self, temp_dir):
        """无匹配车次：返回未找到提示"""
        service = mock.MagicMock()
        service.find_trains_between_stations.return_value = []

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            result = station_route_drawing_tool.invoke({
                "start_station": "火星", "end_station": "月球"
            })
            assert "未找到" in result
            assert "火星" in result
            assert "月球" in result

    def test_train_not_in_timetable_graceful(self, temp_dir):
        """某趟车不在 timetable（draw 返回 None）：标注提示，不中断其他车次"""
        service = mock.MagicMock()
        service.find_trains_between_stations.return_value = [
            ("G1", "07:00", "北京南", "上海虹桥", ["北京南", "上海虹桥"]),
            ("G99", "12:00", "北京南", "上海虹桥", ["北京南", "上海虹桥"]),
        ]
        service.draw_train_route.side_effect = [
            (os.path.join(temp_dir, "route_G1.html"), ["北京南", "上海虹桥"]),
            (None, None),  # G99 不在 timetable
        ]

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            result = station_route_drawing_tool.invoke({
                "start_station": "北京南", "end_station": "上海虹桥"
            })

        assert "[MAP]/maps/route_G1.html[/MAP]" in result
        assert "未找到时刻表数据" in result
        assert "G99" in result

    def test_draw_exception_graceful(self, temp_dir):
        """某趟车绘制失败：捕获异常，标注失败信息，不中断其他车次"""
        service = mock.MagicMock()
        service.find_trains_between_stations.return_value = [
            ("G1", "07:00", "北京南", "上海虹桥", ["北京南", "上海虹桥"]),
            ("G13", "10:00", "北京南", "上海虹桥", ["北京南", "上海虹桥"]),
        ]
        service.draw_train_route.side_effect = [
            (os.path.join(temp_dir, "route_G1.html"), ["北京南", "上海虹桥"]),
            RuntimeError("GPKG 数据损坏"),
        ]

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            result = station_route_drawing_tool.invoke({
                "start_station": "北京南", "end_station": "上海虹桥"
            })

        assert "[MAP]/maps/route_G1.html[/MAP]" in result
        assert "绘制失败" in result
        assert "GPKG 数据损坏" in result
        assert service.draw_train_route.call_count == 2

    def test_passes_station_names_correctly(self, temp_dir):
        """起终点站名原样传递给 find_trains_between_stations"""
        service = mock.MagicMock()
        service.find_trains_between_stations.return_value = [
            ("K4174", "13:40", "合肥", "北京西", ["合肥", "淮南", "北京西"]),
        ]
        service.draw_train_route.return_value = (
            os.path.join(temp_dir, "route_K4174.html"), ["合肥", "淮南", "北京西"]
        )

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            station_route_drawing_tool.invoke({
                "start_station": "合肥", "end_station": "北京西"
            })

        service.find_trains_between_stations.assert_called_once_with("合肥", "北京西")

    def test_max_20_trains_limit(self, temp_dir):
        """超过 20 趟车次时只画前 20 趟，输出提示"""
        service = mock.MagicMock()
        trains = [(f"G{i}", f"{6+i//60:02d}:{i%60:02d}", "北京南", "上海虹桥", ["北京南", "上海虹桥"])
                  for i in range(30)]
        service.find_trains_between_stations.return_value = trains
        service.draw_train_route.return_value = (
            os.path.join(temp_dir, "route_G0.html"), ["北京南", "上海虹桥"]
        )

        with mock.patch("agent.tools.get_route_map_service", return_value=service), \
             mock.patch("agent.tools.config_data") as cfg:
            cfg.maps_output_dir = temp_dir
            from agent.tools import station_route_drawing_tool

            result = station_route_drawing_tool.invoke({
                "start_station": "北京南", "end_station": "上海虹桥"
            })

        assert "（仅展示前 20 趟，共 30 趟）" in result
        assert service.draw_train_route.call_count == 20
