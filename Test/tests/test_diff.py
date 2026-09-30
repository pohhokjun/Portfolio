# -*- coding: utf-8 -*-
"""差异比对工具的自测（文本 / 图像 / 字典）。"""

from pathlib import Path

import pytest

from common.diff import dict_diff, image_diff, text_diff, text_similarity

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


class TestTextDiff:

    def test_完全相同没有差异行(self):
        assert text_diff("a\nb", "a\nb") == []

    def test_有差异能标出增删(self):
        out = "\n".join(text_diff("a\nb", "a\nc"))
        assert "-b" in out and "+c" in out

    def test_None当空串处理(self):
        assert text_diff(None, None) == []
        assert text_diff(None, "a") != []

    def test_相似度(self):
        assert text_similarity("abc", "abc") == 1.0
        assert text_similarity("abc", "xyz") == 0.0
        assert 0 < text_similarity("abcd", "abcx") < 1


class TestImageDiff:

    def test_两张一样的图差异为零(self, png):
        a = png("a", color=WHITE)
        b = png("b", color=WHITE)
        res = image_diff(a, b)
        assert res["ok"] is True
        assert res["changed_ratio"] == 0.0

    def test_全变了差异为百分百(self, png):
        a = png("a", color=WHITE)
        b = png("b", color=BLACK)
        assert image_diff(a, b)["changed_ratio"] == 1.0

    def test_局部变化按面积算比例(self, png):
        # 40x40=1600 像素，改掉 20x20=400 个，正好 25%
        a = png("a", size=(40, 40), color=WHITE)
        b = png("b", size=(40, 40), color=WHITE,
                boxes=[((0, 0, 20, 20), BLACK)])
        assert image_diff(a, b)["changed_ratio"] == pytest.approx(0.25)

    def test_屏蔽区域内的变化不算差异(self, png):
        # 这就是 ignore_boxes 的用途：遮住时间戳、轮播图、广告
        a = png("a", size=(40, 40), color=WHITE)
        b = png("b", size=(40, 40), color=WHITE,
                boxes=[((0, 0, 20, 20), BLACK)])
        res = image_diff(a, b, ignore_boxes=[[0, 0, 20, 20]])
        assert res["changed_ratio"] == 0.0

    def test_低于像素阈值的噪声被忽略(self, png):
        # 字体渲染、抗锯齿会带来 1~2 的像素差，不该判为界面变化
        a = png("a", color=(255, 255, 255))
        b = png("b", color=(250, 250, 250))
        assert image_diff(a, b, threshold=30)["changed_ratio"] == 0.0
        assert image_diff(a, b, threshold=3)["changed_ratio"] == 1.0

    def test_尺寸不一致要报出来而不是缩放后硬比(self, png):
        # 页面高度变了通常就是真的布局回归，缩放会把它抹掉
        a = png("a", size=(40, 40))
        b = png("b", size=(40, 80))
        res = image_diff(a, b)
        assert res["size_mismatch"] is True
        assert res["changed_ratio"] == 1.0
        assert "尺寸不一致" in res["reason"]

    def test_文件不存在时返回未比对而不是崩(self, png, tmp_path):
        res = image_diff(png("a"), str(tmp_path / "没有这个文件.png"))
        assert res["ok"] is None

    def test_生成标红差异图(self, png, tmp_path):
        a = png("a", size=(40, 40), color=WHITE)
        b = png("b", size=(40, 40), color=WHITE,
                boxes=[((0, 0, 20, 20), BLACK)])
        out = tmp_path / "子目录" / "diff.png"
        res = image_diff(a, b, out_path=str(out))
        assert Path(res["diff_image"]).exists()      # 父目录会自动建

    def test_不传out_path就不生成差异图(self, png):
        assert image_diff(png("a"), png("b"))["diff_image"] == ""


class TestDictDiff:

    def test_完全相同没差异(self):
        assert dict_diff({"a": 1}, {"a": 1}) == []

    def test_值变了(self):
        out = dict_diff({"a": 1}, {"a": 2})
        assert out == [{"path": "a", "baseline": 1, "current": 2}]

    def test_字段消失(self):
        # 接口契约里最要命的一种变化
        out = dict_diff({"a": 1}, {})
        assert out[0]["path"] == "a" and out[0]["current"] is None

    def test_字段新增(self):
        out = dict_diff({}, {"a": 1})
        assert out[0]["path"] == "a" and out[0]["baseline"] is None

    def test_嵌套结构用点号表示路径(self):
        out = dict_diff({"a": {"b": {"c": 1}}}, {"a": {"b": {"c": 2}}})
        assert out[0]["path"] == "a.b.c"

    def test_类型变了也要报(self):
        # int 变 string 是前端最怕的后端偷偷改字段
        out = dict_diff({"price": 100}, {"price": "100"})
        assert len(out) == 1

    def test_None当空字典处理(self):
        assert dict_diff(None, None) == []
        assert len(dict_diff(None, {"a": 1})) == 1

    def test_差异按字段名排序保证结果稳定(self):
        out = dict_diff({"z": 1, "a": 1}, {"z": 2, "a": 2})
        assert [c["path"] for c in out] == ["a", "z"]
