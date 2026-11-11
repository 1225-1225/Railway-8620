# -*- coding: utf-8 -*-
"""agent/route_geometry.py 的测试

覆盖：
  * 参考数据缺失时优雅降级（不抛异常）
  * 站名解析（精确 / 去"站"后缀 / 别名）
  * 同线路站对截取真实几何
  * 绕远路径被质量门拒绝
  * 中间站桥接
  * build_route 的统计口径
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.route_geometry import RouteGeometry, haversine_km, traj_length


@pytest.fixture
def fake_data(tmp_path):
    """构造一份最小参考数据

    线路 L1 是一条从 (116.0, 39.0) 到 (117.0, 39.0) 的折线，
    中间经过 (116.5, 39.0)。站点 A/B 在两端，C 在中间。
    """
    geom = [[116.0 + i * 0.1, 39.0] for i in range(11)]

    lines = {
        "L1": {
            "osm_id": 1, "name": "L1", "ref": "", "from": "A", "to": "B",
            "operator": "", "member_count": 1, "km": 85.0,
            "point_count": len(geom), "geometry": geom,
        }
    }
    stations = {
        "node/1": {"name": "A", "name_zh": "A", "name_en": "", "ref": "",
                   "lat": 39.0, "lng": 116.0, "kind": "national_rail",
                   "priority": 2, "aliases": [], "lines": ["L1"]},
        "node/2": {"name": "B", "name_zh": "B", "name_en": "", "ref": "",
                   "lat": 39.0, "lng": 117.0, "kind": "national_rail",
                   "priority": 2, "aliases": [], "lines": ["L1"]},
        "node/3": {"name": "C", "name_zh": "C", "name_en": "", "ref": "",
                   "lat": 39.0, "lng": 116.5, "kind": "national_rail",
                   "priority": 2, "aliases": ["C站"], "lines": ["L1"]},
    }

    (tmp_path / "rail_lines.json").write_text(
        json.dumps({"meta": {}, "lines": lines}, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "stations.json").write_text(
        json.dumps({"meta": {}, "stations": stations}, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def rg(fake_data):
    """每个测试用独立实例，避免单例串味"""
    RouteGeometry._instance = None
    obj = RouteGeometry(data_dir=fake_data)
    yield obj
    RouteGeometry._instance = None


class TestLineGrade:
    """线路等级判定（消歧的基础）"""

    @pytest.mark.parametrize("name,expected", [
        ("京沪高铁", "high_speed"),
        ("沪昆高速线", "high_speed"),
        ("京广高速线", "high_speed"),
        ("沪宁城际线", "high_speed"),
        ("合福高速线", "high_speed"),
        ("京沪京广联络线", "conventional"),
        ("济南动车走行A线", "conventional"),
        ("京沪三线", "other"),
        ("京沪线", "other"),
        ("1道", "other"),
        ("II道", "other"),
        ("", "other"),
    ])
    def test_grade(self, name, expected):
        assert RouteGeometry.line_grade(name) == expected


class TestDisambiguation:
    """两站间有多条线路时，按车次类型选对的那条"""

    @pytest.fixture
    def two_line_data(self, tmp_path):
        """同一对站 A/B 之间有两条平行线路：
        HS（高速线，走北侧）与 CV（普速线，走南侧）
        站点放在两条线之间，距各 2km，都在吸附阈值内。
        """
        hs = [[116.0, 39.02], [116.5, 39.02], [117.0, 39.02]]
        cv = [[116.0, 38.98], [116.5, 38.98], [117.0, 38.98]]
        lines = {
            "测试高速线": {"osm_id": 1, "name": "测试高速线", "ref": "", "usage": "",
                           "operator": "", "way_count": 1, "km": 90.0,
                           "segment_count": 1, "segments": [],
                           "point_count": 3, "geometry": hs},
            "测试线": {"osm_id": 2, "name": "测试线", "ref": "", "usage": "",
                       "operator": "", "way_count": 1, "km": 90.0,
                       "segment_count": 1, "segments": [],
                       "point_count": 3, "geometry": cv},
        }
        base = {"name_en": "", "ref": "", "kind": "national_rail",
                "priority": 2, "aliases": [],
                "lines": ["测试高速线", "测试线"]}
        stations = {
            "node/1": {**base, "name": "A", "name_zh": "A", "lat": 39.0, "lng": 116.0},
            "node/2": {**base, "name": "B", "name_zh": "B", "lat": 39.0, "lng": 117.0},
        }
        (tmp_path / "rail_lines.json").write_text(
            json.dumps({"meta": {}, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "stations.json").write_text(
            json.dumps({"meta": {}, "stations": stations}, ensure_ascii=False), encoding="utf-8")
        return str(tmp_path)

    @pytest.fixture
    def rg2(self, two_line_data):
        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=two_line_data)
        yield obj
        RouteGeometry._instance = None

    def test_high_speed_train_uses_high_speed_line(self, rg2):
        seg, source = rg2.find_segment("A", "B", train_class="高速")
        assert source == "line"
        # 高速线在北侧 39.02
        assert seg[0][1] == pytest.approx(39.02)

    def test_conventional_train_uses_conventional_line(self, rg2):
        seg, source = rg2.find_segment("A", "B", train_class="快速")
        assert source == "line"
        # 普速线在南侧 38.98
        assert seg[0][1] == pytest.approx(38.98)

    def test_no_class_does_not_crash(self, rg2):
        seg, source = rg2.find_segment("A", "B")
        assert source == "line"
        assert len(seg) == 3


class TestStationConflict:
    """同名站在 OSM 里可能对应多个要素（如'新和'既是广东地铁站，
    也是新疆南疆线车站）。必须按优先级选国铁，而不是先到先得。"""

    @pytest.fixture
    def conflict_data(self, tmp_path):
        # 同一站名 '新和' 两个要素：地铁站（广东）与国铁站（新疆）
        stations = {
            "node/1": {"name": "新和", "name_zh": "新和", "name_en": "", "ref": "",
                       "lat": 23.41, "lng": 113.46, "kind": "metro",
                       "priority": 0, "aliases": [], "lines": []},
            "node/2": {"name": "新和", "name_zh": "新和", "name_en": "", "ref": "",
                       "lat": 41.57, "lng": 82.62, "kind": "rail",
                       "priority": 1, "aliases": [], "lines": ["南疆线"]},
            "node/3": {"name": "新和站", "name_zh": "新和", "name_en": "", "ref": "",
                       "lat": 41.57, "lng": 82.62, "kind": "national_rail",
                       "priority": 2, "aliases": [], "lines": ["南疆线"]},
        }
        lines = {"南疆线": {"osm_id": 1, "name": "南疆线", "ref": "", "usage": "",
                            "operator": "", "way_count": 1, "km": 100.0,
                            "segment_count": 1, "segments": [], "point_count": 3,
                            "geometry": [[82.0, 41.5], [82.6, 41.57], [83.0, 41.69]]}}
        (tmp_path / "rail_lines.json").write_text(
            json.dumps({"meta": {}, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "stations.json").write_text(
            json.dumps({"meta": {}, "stations": stations}, ensure_ascii=False), encoding="utf-8")
        return str(tmp_path)

    @pytest.fixture
    def rgc(self, conflict_data):
        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=conflict_data)
        yield obj
        RouteGeometry._instance = None

    def test_prefers_national_rail_over_metro(self, rgc):
        st = rgc.resolve_station("新和")
        assert st["kind"] == "national_rail"
        assert st["lng"] == pytest.approx(82.62)
        assert st["lat"] == pytest.approx(41.57)

    def test_not_guangdong_metro_coords(self, rgc):
        """绝不能解析到广东地铁站坐标"""
        st = rgc.resolve_station("新和")
        assert not (st["lng"] == pytest.approx(113.46))

    def test_with_station_suffix(self, rgc):
        st = rgc.resolve_station("新和站")
        assert st["kind"] == "national_rail"


class TestBridging:
    """跨线车次：两站不共享线路时用中间站桥接"""

    @pytest.fixture
    def bridge_data(self, tmp_path):
        """构造 A - X - B 三段线路，A/B 不共享线路但都连 X

        几何：A(116.0) --L1-- X(116.5) --L2-- B(117.0)，同纬度
        """
        l1 = [[116.0, 39.0], [116.3, 39.0], [116.5, 39.0]]
        l2 = [[116.5, 39.0], [116.8, 39.0], [117.0, 39.0]]
        lines = {
            "L1": {"osm_id": 1, "name": "L1", "ref": "", "usage": "",
                   "operator": "", "way_count": 1, "km": 43.0,
                   "segment_count": 1, "segments": [], "point_count": 3,
                   "geometry": l1},
            "L2": {"osm_id": 2, "name": "L2", "ref": "", "usage": "",
                   "operator": "", "way_count": 1, "km": 43.0,
                   "segment_count": 1, "segments": [], "point_count": 3,
                   "geometry": l2},
        }
        base = {"name_en": "", "ref": "", "kind": "national_rail",
                "priority": 2, "aliases": []}
        stations = {
            "node/1": {**base, "name": "A", "name_zh": "A",
                       "lat": 39.0, "lng": 116.0, "lines": ["L1"]},
            "node/2": {**base, "name": "X", "name_zh": "X",
                       "lat": 39.0, "lng": 116.5, "lines": ["L1", "L2"]},
            "node/3": {**base, "name": "B", "name_zh": "B",
                       "lat": 39.0, "lng": 117.0, "lines": ["L2"]},
        }
        (tmp_path / "rail_lines.json").write_text(
            json.dumps({"meta": {}, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "stations.json").write_text(
            json.dumps({"meta": {}, "stations": stations}, ensure_ascii=False), encoding="utf-8")
        return str(tmp_path)

    @pytest.fixture
    def rgb(self, bridge_data):
        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=bridge_data)
        yield obj
        RouteGeometry._instance = None

    def test_one_hop_bridge(self, rgb):
        seg, source = rgb.find_segment("A", "B", "高速")
        assert source == "line"
        assert seg[0] == [116.0, 39.0]
        assert seg[-1] == [117.0, 39.0]

    def test_bridge_does_not_use_endpoint_as_middle(self, rgb):
        """中间站不能与端点重合（防止 A->A->B 自环）"""
        mid = rgb._best_bridge(
            rgb.resolve_station("A"), rgb.resolve_station("B"),
            (116.0, 39.0), (117.0, 39.0), 86.0)
        # X 是唯一合法中间站，不能选中 A 或 B
        assert mid is not None
        assert mid["name_zh"] == "X"

    def test_no_path_returns_fallback(self, rgb):
        """B 与一个孤立站之间无通路 -> 直线"""
        rgb._ensure_loaded()
        rgb._stations["node/9"] = {
            "name": "Z", "name_zh": "Z", "name_en": "", "ref": "",
            "lat": 20.0, "lng": 100.0, "kind": "national_rail",
            "priority": 2, "aliases": [], "lines": ["L9"],
        }
        rgb._name_index["Z"] = rgb._stations["node/9"]
        rgb._line_stations = None
        seg, source = rgb.find_segment("A", "Z", "高速")
        assert source == "fallback"


class TestAvailability:
    def test_available_when_files_exist(self, rg):
        assert rg.available is True

    def test_unavailable_when_missing(self, tmp_path):
        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=str(tmp_path / "nope"))
        assert obj.available is False
        RouteGeometry._instance = None

    def test_missing_data_degrades_gracefully(self, tmp_path):
        """数据缺失时不能抛异常，应返回 no_station"""
        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=str(tmp_path / "nope"))
        seg, source = obj.find_segment("A", "B")
        assert seg is None
        assert source == "no_station"
        RouteGeometry._instance = None


class TestStationResolve:
    def test_exact(self, rg):
        assert rg.resolve_station("A")["lng"] == 116.0

    def test_alias(self, rg):
        assert rg.resolve_station("C站")["lng"] == 116.5

    def test_strip_suffix(self, rg):
        """'A站' 应能解析到 'A'"""
        assert rg.resolve_station("A站")["lng"] == 116.0

    def test_unknown(self, rg):
        assert rg.resolve_station("不存在") is None

    def test_station_coord(self, rg):
        assert rg.station_coord("A") == (116.0, 39.0)


class TestFindSegment:
    def test_same_line_returns_real_geometry(self, rg):
        seg, source = rg.find_segment("A", "B")
        assert source == "line"
        assert len(seg) == 11
        assert seg[0] == [116.0, 39.0]
        assert seg[-1] == [117.0, 39.0]

    def test_reverse_direction(self, rg):
        seg, source = rg.find_segment("B", "A")
        assert source == "line"
        assert seg[0] == [117.0, 39.0]
        assert seg[-1] == [116.0, 39.0]

    def test_partial_segment(self, rg):
        """A -> C 应只截取前半段"""
        seg, source = rg.find_segment("A", "C")
        assert source == "line"
        assert seg[0] == [116.0, 39.0]
        assert seg[-1] == [116.5, 39.0]
        assert len(seg) == 6

    def test_unknown_station(self, rg):
        seg, source = rg.find_segment("A", "不存在")
        assert seg is None
        assert source == "no_station"

    def test_no_common_line_falls_back(self, rg):
        """两站不共享线路且无中间站 -> 直线"""
        rg._ensure_loaded()
        rg._stations["node/9"] = {
            "name": "Z", "name_zh": "Z", "name_en": "", "ref": "",
            "lat": 20.0, "lng": 100.0, "kind": "national_rail",
            "priority": 2, "aliases": [], "lines": ["L9"],
        }
        rg._name_index["Z"] = rg._stations["node/9"]
        seg, source = rg.find_segment("A", "Z")
        assert source == "fallback"
        assert len(seg) == 2


class TestQualityGate:
    def test_detour_rejected(self, tmp_path):
        """绕远 3 倍以上的路径必须被拒绝"""
        # 一条绕大圈的线路：A(116,39) -> (116,45) -> (117,45) -> B(117,39)
        geom = [[116.0, 39.0], [116.0, 45.0], [117.0, 45.0], [117.0, 39.0]]
        lines = {"LOOP": {"osm_id": 1, "name": "LOOP", "ref": "", "from": "A",
                          "to": "B", "operator": "", "member_count": 1,
                          "km": 1300.0, "point_count": 4, "geometry": geom}}
        stations = {
            "node/1": {"name": "A", "name_zh": "A", "name_en": "", "ref": "",
                       "lat": 39.0, "lng": 116.0, "kind": "national_rail",
                       "priority": 2, "aliases": [], "lines": ["LOOP"]},
            "node/2": {"name": "B", "name_zh": "B", "name_en": "", "ref": "",
                       "lat": 39.0, "lng": 117.0, "kind": "national_rail",
                       "priority": 2, "aliases": [], "lines": ["LOOP"]},
        }
        (tmp_path / "rail_lines.json").write_text(
            json.dumps({"meta": {}, "lines": lines}, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "stations.json").write_text(
            json.dumps({"meta": {}, "stations": stations}, ensure_ascii=False), encoding="utf-8")

        RouteGeometry._instance = None
        obj = RouteGeometry(data_dir=str(tmp_path))
        seg, source = obj.find_segment("A", "B")
        # 绕远 13 倍，必须降级为直线
        assert source == "fallback"
        assert len(seg) == 2
        RouteGeometry._instance = None


class TestBuildRoute:
    def test_stats(self, rg):
        pts, stats = rg.build_route(["A", "C", "B"])
        assert stats["total"] == 2
        assert stats["matched"] == 2
        assert stats["fallback"] == 0
        assert stats["missing"] == 0
        assert len(pts) == 11

    def test_missing_station_counted(self, rg):
        pts, stats = rg.build_route(["A", "不存在", "B"])
        assert stats["total"] == 2
        assert stats["missing"] == 2

    def test_single_station(self, rg):
        pts, stats = rg.build_route(["A"])
        assert stats["total"] == 0
        assert pts == []


class TestHelpers:
    def test_haversine_zero(self):
        assert haversine_km((116.0, 39.0), (116.0, 39.0)) == 0.0

    def test_haversine_known_distance(self):
        """北京到上海直线约 1060 km"""
        d = haversine_km((116.4, 39.9), (121.5, 31.2))
        assert 1000 < d < 1120

    def test_traj_length(self):
        pts = [[116.0, 39.0], [116.0, 40.0]]
        assert 110 < traj_length(pts) < 112
