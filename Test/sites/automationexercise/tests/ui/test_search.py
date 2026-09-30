# -*- coding: utf-8 -*-
"""
商品搜索 UI 测试

演示：
    - 数据驱动覆盖有效/无效等价类
    - 搜索结果的内容校验（不只是「有结果」，还要检查结果是否相关）
"""

import allure
import pytest

from sites.automationexercise import DATA

from common.assertions import assert_true, SoftAssert
from common.data_reader import load_cases


@allure.epic("UI自动化")
@allure.feature("商品搜索")
class TestSearch:

    @allure.story("商品列表")
    @allure.title("PRODUCT_001 - 商品列表页应正常加载且有商品")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.ui
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_products_page_loaded(self, products_page):
        sa = SoftAssert()
        sa.true(products_page.is_loaded(), "商品页标题应可见")
        sa.true(products_page.product_count() > 0, "应至少显示一个商品")
        sa.assert_all()

    _cases, _ids = load_cases(DATA / "search_cases.yaml")

    @allure.story("搜索功能")
    @allure.title("{case[title]}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.ui
    @pytest.mark.p1
    @pytest.mark.parametrize("case", _cases, ids=_ids)
    def test_search(self, products_page, case):
        allure.dynamic.description(
            "用例ID: %s\n设计方法: %s\n关键词: %r\n预期有结果: %s"
            % (case["id"], case.get("method", ""),
               case["keyword"], case["expect_found"])
        )

        products_page.search(case["keyword"])

        assert_true(products_page.is_search_result_shown(),
                    "应显示搜索结果区域")

        count = products_page.product_count()
        allure.attach("关键词: %r\n结果数: %d" % (case["keyword"], count),
                      name="搜索结果统计",
                      attachment_type=allure.attachment_type.TEXT)

        if case["expect_found"]:
            assert_true(count > 0, "关键词 %r 应能搜到商品" % case["keyword"])
        else:
            assert_true(count == 0,
                        "关键词 %r 不应有结果，实际 %d 条" % (case["keyword"], count))

    @allure.story("搜索功能")
    @allure.title("SEARCH_008 - 搜索结果的商品名应与关键词相关")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "这条用例演示「深度断言」：\n"
        "只判断「有结果」是不够的，搜 tshirt 返回一堆裙子也是缺陷。\n"
        "所以要检查结果内容是否真的相关。\n\n"
        "★ 调试记录（面试可讲的真实经历）★\n"
        "  这条用例第一版写的是 keyword in name.lower()，结果相关度只有 33%%，\n"
        "  以为发现了搜索功能的缺陷。手工验证后发现 6 条结果全部相关，\n"
        "  只是商品名写法不统一：Tshirt / T-Shirt / T SHIRT 三种都有。\n"
        "  是我的断言逻辑太死板，不是被测系统的问题。\n"
        "  修正：比较前先做归一化（去掉空格和连字符）。\n"
        "  教训：自动化用例报错时，先确认是「真缺陷」还是「假失败」，\n"
        "        提单前必须手工复现，否则会消耗开发的信任。"
    )
    @pytest.mark.ui
    @pytest.mark.p2
    def test_search_result_relevance(self, products_page):
        keyword = "tshirt"
        products_page.search(keyword)

        assert_true(products_page.is_search_result_shown(), "应显示搜索结果")
        names = products_page.product_names()
        assert_true(len(names) > 0, "应有搜索结果")

        def normalize(text):
            """归一化：转小写并去掉空格和连字符，抹平命名差异。"""
            return text.lower().replace("-", "").replace(" ", "")

        target = normalize(keyword)
        matched = [n for n in names if target in normalize(n)]
        ratio = len(matched) / len(names)

        allure.attach(
            "关键词: %s\n结果总数: %d\n名称相关数: %d\n相关度: %.0f%%\n\n"
            "结果明细:\n%s"
            % (keyword, len(names), len(matched), ratio * 100,
               "\n".join("  %s %s" % ("[匹配]" if target in normalize(n)
                                     else "[不匹配]", n) for n in names[:15])),
            name="搜索相关度分析",
            attachment_type=allure.attachment_type.TEXT)

        assert_true(ratio >= 0.5,
                    "搜索结果相关度应过半，实际 %.0f%%（%d/%d）"
                    % (ratio * 100, len(matched), len(names)))
