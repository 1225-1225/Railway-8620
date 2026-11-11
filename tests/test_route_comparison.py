# -*- coding: utf-8 -*-
"""多车次路线对比图的测试

覆盖：
  * 参数校验（车次数下限/上限、非法车次）
  * 输出文件命名规则（必须能被前端 MAP_URL_RE 匹配）
  * HTML 内容（图例、多种颜色、虚线说明）
  * Agent 工具的返回格式
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import route_map_generator as rmg

# 与前端 ChatView.vue 中的 MAP_URL_RE 保持一致
FRONTEND_MAP_RE = r"/maps/[A-Za-z0-9_-]+\.html"


@pytest.fixture
def outdir(tmp_path, monkeypatch):
    monkeypatch.setattr(rmg, "_MAP_DIR", str(tmp_path))
    return tmp_path


class TestComparisonValidation:
    def test_too_few_trains(self, outdir):
        assert "至少需要 2 个" in rmg.generate_comparison_map(["G1"])

    def test_empty_list(self, outdir):
        assert "至少需要 2 个" in rmg.generate_comparison_map([])

    def test_too_many_trains(self, outdir):
        codes = ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
        assert "最多支持 6 个" in rmg.generate_comparison_map(codes)

    def test_unknown_train(self, outdir):
        r = rmg.generate_comparison_map(["G1", "NOT_A_TRAIN"])
        assert "站点数据不足" in r or "无法" in r

    def test_duplicate_codes_deduped(self, outdir):
        """重复车次去重后只剩 1 个 -> 应报错"""
        assert "至少需要 2 个" in rmg.generate_comparison_map(["G1", "G1"])


class TestComparisonOutput:
    def test_file_created(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35"])
        assert p.endswith(".html")
        assert os.path.exists(p)

    def test_filename_matches_frontend_regex(self, outdir):
        """文件名必须能被前端 MAP_URL_RE 匹配，否则无法内嵌成卡片"""
        p = rmg.generate_comparison_map(["G1", "T35"])
        url = "/maps/" + os.path.basename(p)
        assert re.match(FRONTEND_MAP_RE, url), f"URL 无法匹配前端正则: {url}"

    def test_filename_ascii_only(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35", "Z227"])
        name = os.path.basename(p)
        assert re.match(r"^[A-Za-z0-9_.-]+$", name), f"文件名含非 ASCII: {name}"

    def test_lowercase_normalized(self, outdir):
        p = rmg.generate_comparison_map(["g1", "t35"])
        assert "G1" in os.path.basename(p)
        assert "T35" in os.path.basename(p)

    def test_html_has_legend(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35"])
        html = open(p, encoding="utf-8", errors="replace").read()
        assert "车次路线对比" in html
        assert "虚线" in html

    def test_html_has_multiple_colors(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35"])
        html = open(p, encoding="utf-8", errors="replace").read()
        # 两个车次应使用不同颜色
        assert rmg._COMPARE_COLORS[0][0] in html
        assert rmg._COMPARE_COLORS[1][0] in html

    def test_html_mentions_both_codes(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35"])
        html = open(p, encoding="utf-8", errors="replace").read()
        assert "G1" in html and "T35" in html

    def test_custom_title(self, outdir):
        p = rmg.generate_comparison_map(["G1", "T35"], title="高铁 vs 普速")
        html = open(p, encoding="utf-8", errors="replace").read()
        assert "高铁 vs 普速" in html

    def test_max_six_trains_ok(self, outdir):
        codes = ["G1", "G7", "T35", "Z227", "K454", "K569"]
        p = rmg.generate_comparison_map(codes)
        assert p.endswith(".html")
        assert os.path.exists(p)


class TestComparisonTool:
    def test_tool_returns_url(self, outdir):
        from agent.tools import compare_train_routes
        r = compare_train_routes.invoke({"train_codes": ["G1", "T35"]})
        assert "/maps/compare_" in r
        assert ".html" in r

    def test_tool_rejects_single(self, outdir):
        from agent.tools import compare_train_routes
        r = compare_train_routes.invoke({"train_codes": ["G1"]})
        assert "至少需要 2 个" in r

    def test_tool_passes_through_error(self, outdir):
        from agent.tools import compare_train_routes
        r = compare_train_routes.invoke({"train_codes": ["G1", "NOPE999"]})
        # 不应返回 URL，应返回错误说明
        assert "/maps/" not in r


class TestAgentRegistration:
    def test_tool_registered(self):
        from agent.agent import tools
        names = [t.name for t in tools]
        assert "compare_train_routes" in names

    def test_total_tool_count(self):
        from agent.agent import tools
        assert len(tools) == 8
