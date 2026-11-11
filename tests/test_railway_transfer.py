# -*- coding: utf-8 -*-
"""同城枢纽换乘提示的测试

覆盖：
  * 枢纽识别规则（方位词归并、例外白名单、小站过滤）
  * 同城站列表输出
  * 换乘提示的三种分支（有直达 / 同城换站 / 无方案）
  * 能力边界说明必须出现
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import railway_transfer as rt


@pytest.fixture
def fake_data(tmp_path, monkeypatch):
    """构造一个最小数据集：
    - 城市 A 有三个站：A / A东 / A西（A东、A西 车次够多）
    - 城市 B 有 B / B南
    - 小站 A镇 车次很少，不应被归入 A
    - A -> B 有直达；A东 -> B南 无直达
    """
    def train(code, cls, stations):
        return {
            "train_code": code, "class": cls,
            "from": stations[0], "to": stations[-1],
            "stations": stations,
            "station_details": [
                {"name": s, "arrive": "07:00", "depart": "07:01", "no": i + 1}
                for i, s in enumerate(stations)
            ],
        }

    data = {}
    # 让 A / A东 / A西 / B / B南 都达到 MIN_TRAINS 门槛
    for i in range(rt.MIN_TRAINS + 5):
        data[f"G{1000+i}"] = train(f"G{1000+i}", "高速", ["A", "A东", "B"])
    for i in range(rt.MIN_TRAINS + 5):
        data[f"D{2000+i}"] = train(f"D2000{i}", "动车", ["A", "A西", "B南"])
    for i in range(rt.MIN_TRAINS + 5):
        data[f"K{3000+i}"] = train(f"K3000{i}", "快速", ["B", "B南", "C"])
    # 小站 A镇 只出现在少数车次
    data["G9001"] = train("G9001", "高速", ["A", "A镇"])
    data["G9002"] = train("G9002", "高速", ["A镇", "B"])

    path = tmp_path / "train_details.json"
    import json
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(rt, "_details_path", str(path))
    monkeypatch.setattr(rt, "_details", None)
    monkeypatch.setattr(rt, "_hubs", None)
    monkeypatch.setattr(rt, "_station_trains", None)
    monkeypatch.setattr(rt, "_station_to_hub", None)
    yield data
    monkeypatch.setattr(rt, "_details", None)
    monkeypatch.setattr(rt, "_hubs", None)
    monkeypatch.setattr(rt, "_station_trains", None)
    monkeypatch.setattr(rt, "_station_to_hub", None)


class TestHubDetection:
    def test_hub_recognized(self, fake_data):
        rt._build_indexes()
        assert "A" in rt._hubs
        assert set(rt._hubs["A"]) >= {"A", "A东", "A西"}

    def test_small_station_filtered(self, fake_data):
        """车次不足 MIN_TRAINS 的小站不能并入枢纽"""
        rt._build_indexes()
        assert "A镇" not in rt._hubs.get("A", set())

    def test_station_to_hub_mapping(self, fake_data):
        rt._build_indexes()
        assert rt._station_to_hub.get("A东") == "A"
        assert rt._station_to_hub.get("B南") == "B"

    def test_single_station_city_excluded(self, fake_data):
        """只有 1 个站的城市不算枢纽"""
        rt._build_indexes()
        for city, sts in rt._hubs.items():
            assert len(sts) >= 2


class TestSameCityStations:
    def test_by_city_name(self, fake_data):
        out = rt.find_same_city_stations.invoke({"city_or_station": "A"})
        assert "A东" in out and "A西" in out

    def test_by_station_name(self, fake_data):
        out = rt.find_same_city_stations.invoke({"city_or_station": "A东"})
        assert "共 3 个火车站" in out or "A" in out

    def test_unknown(self, fake_data):
        out = rt.find_same_city_stations.invoke({"city_or_station": "不存在城市"})
        assert "未找到" in out or "不是多站枢纽" in out

    def test_empty(self, fake_data):
        out = rt.find_same_city_stations.invoke({"city_or_station": "  "})
        assert "请提供" in out


class TestSuggestTransfer:
    def test_direct_exists(self, fake_data):
        out = rt.suggest_transfer.invoke({"from_station": "A", "to_station": "B"})
        assert "直达" in out
        assert "无需换乘" in out

    def test_no_direct_same_hub(self, fake_data):
        """A东 -> A西 同城无直达，应给接驳建议"""
        # 先构造 A东 -> A西 的场景：数据里没有这条直达
        out = rt.suggest_transfer.invoke({"from_station": "A东", "to_station": "A西"})
        assert "无直达" in out
        assert "同属" in out or "接驳" in out

    def test_no_direct_cross_hub(self, fake_data):
        out = rt.suggest_transfer.invoke({"from_station": "A东", "to_station": "B南"})
        assert "无直达" in out

    def test_capability_boundary_stated(self, fake_data):
        """必须说明不含精确时刻衔接"""
        out = rt.suggest_transfer.invoke({"from_station": "A东", "to_station": "B南"})
        assert "12306" in out
        assert "不含精确换乘时刻" in out or "只做连接关系提示" in out

    def test_empty_input(self, fake_data):
        out = rt.suggest_transfer.invoke({"from_station": "", "to_station": "B"})
        assert "请提供" in out

    def test_reverse_direction_not_matched(self, fake_data):
        """B -> A 方向未定义，不应误报直达"""
        out = rt.suggest_transfer.invoke({"from_station": "B", "to_station": "A"})
        assert "无直达" in out


class TestRegistration:
    def test_both_tools_registered(self):
        from agent.agent import tools
        names = [t.name for t in tools]
        assert "find_same_city_stations" in names
        assert "suggest_transfer" in names
