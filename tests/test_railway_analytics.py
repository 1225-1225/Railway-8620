# -*- coding: utf-8 -*-
"""agent/railway_analytics.py 的测试

覆盖：
  * 区间速度计算的正确性（含跨零点、时刻缺失、无几何）
  * 线路站点反查（精确 / 模糊 / 不存在）
  * 站点车次反查（排序、limit、近似提示）
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import railway_analytics as ra


@pytest.fixture
def fake_details(tmp_path, monkeypatch):
    """构造两个车次：
    G1  07:00 出发，三站，正常时刻
    N1  23:50 出发，次日 00:30 到达（测试跨零点）
    """
    data = {
        "G1": {
            "train_code": "G1", "from": "A", "to": "C", "class": "高速",
            "stations": ["A", "B", "C"],
            "station_details": [
                {"name": "A", "arrive": "----", "depart": "07:00", "no": 1},
                {"name": "B", "arrive": "07:30", "depart": "07:32", "no": 2},
                {"name": "C", "arrive": "08:30", "depart": "08:30", "no": 3},
            ],
        },
        "N1": {
            "train_code": "N1", "from": "A", "to": "C", "class": "快速",
            "stations": ["A", "C"],
            "station_details": [
                {"name": "A", "arrive": "----", "depart": "23:50", "no": 1},
                {"name": "C", "arrive": "00:30", "depart": "00:30", "no": 2},
            ],
        },
    }
    path = tmp_path / "train_details.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(ra, "_details_path", str(path))
    monkeypatch.setattr(ra, "_details", None)
    yield data
    monkeypatch.setattr(ra, "_details", None)


class TestClockParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("07:31", 451),
        ("00:00", 0),
        ("23:59", 1439),
        ("----", None),
        ("", None),
        (None, None),
        ("坏数据", None),
    ])
    def test_parse_clock(self, raw, expected):
        assert ra._parse_clock(raw) == expected

    @pytest.mark.parametrize("minutes,expected", [
        (0, "0m"),
        (31, "31m"),
        (60, "1h00m"),
        (171, "2h51m"),
        (None, "?"),
    ])
    def test_format_duration(self, minutes, expected):
        assert ra._format_duration(minutes) == expected


class TestAnalyzeSpeed:
    def test_missing_train(self, fake_details):
        out = ra.analyze_train_speed.invoke({"train_code": "XXXX"})
        assert "未找到" in out

    def test_basic_output_structure(self, fake_details):
        out = ra.analyze_train_speed.invoke({"train_code": "G1"})
        assert "G1" in out
        assert "高速" in out
        assert "区间" in out
        assert "平均速度" in out  # 口径说明必须存在

    def test_cross_midnight(self, fake_details):
        """23:50 -> 00:30 应算作 40 分钟，而不是负数"""
        out = ra.analyze_train_speed.invoke({"train_code": "N1"})
        assert "40m" in out or "0h40m" in out

    def test_lowercase_code_normalized(self, fake_details):
        out = ra.analyze_train_speed.invoke({"train_code": " g1 "})
        assert "G1" in out

    def test_no_geometry_reported(self, fake_details, monkeypatch):
        """无几何数据时不能崩，应标注出来"""
        class _StubRG:
            def find_segment(self, a, b, cls=None):
                return None, "no_station"

        monkeypatch.setattr(
            "agent.route_geometry.get_route_geometry", lambda: _StubRG())
        out = ra.analyze_train_speed.invoke({"train_code": "G1"})
        assert "无几何" in out

    def test_speed_computed_from_geometry(self, fake_details, monkeypatch):
        """给定固定几何，验证速度数值"""
        class _StubRG:
            def find_segment(self, a, b, cls=None):
                # 每段固定 100km（纬度差约 0.9 度）
                if (a, b) == ("A", "B"):
                    return [[116.0, 39.0], [116.0, 39.9]], "line"
                return [[116.0, 39.9], [116.0, 40.8]], "line"

        monkeypatch.setattr(
            "agent.route_geometry.get_route_geometry", lambda: _StubRG())
        out = ra.analyze_train_speed.invoke({"train_code": "G1"})
        # A->B: 约 100km / 0.5h = 200km/h
        assert "km/h" in out
        # 粗略校验：应出现 190~210 之间的数值
        import re
        speeds = [float(x) for x in re.findall(r"(\d+)km/h", out)]
        assert any(180 <= s <= 220 for s in speeds), speeds


class TestListStationsOnLine:
    def test_unknown_line_gives_hint(self):
        out = ra.list_stations_on_line.invoke({"line_name": "不存在的线路XYZ"})
        assert "未找到" in out

    def test_empty_input(self):
        out = ra.list_stations_on_line.invoke({"line_name": "  "})
        assert "请提供" in out

    def test_fuzzy_match(self):
        out = ra.list_stations_on_line.invoke({"line_name": "京沪"})
        # 模糊匹配应给出候选列表
        assert "是否指" in out or "京沪" in out


class TestFindTrainsAtStation:
    def test_unknown_station(self, fake_details):
        out = ra.find_trains_at_station.invoke({"station": "不存在站"})
        assert "未找到" in out

    def test_finds_train(self, fake_details):
        out = ra.find_trains_at_station.invoke({"station": "A"})
        assert "G1" in out or "N1" in out

    def test_limit_respected(self, fake_details):
        out = ra.find_trains_at_station.invoke({"station": "A", "limit": 1})
        # 只有 G1/N1 两趟，limit=1 时应显示"显示前 1 个"
        assert "显示前" in out

    def test_empty_input(self, fake_details):
        out = ra.find_trains_at_station.invoke({"station": " "})
        assert "请提供" in out

    def test_class_distribution_shown(self, fake_details):
        out = ra.find_trains_at_station.invoke({"station": "A"})
        assert "车型分布" in out
