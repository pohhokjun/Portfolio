# -*- coding: utf-8 -*-
"""
商品接口测试（API 1-6）

本文件演示：
    - 正向用例（200）
    - 反向用例：不支持的请求方法（405）
    - 参数缺失用例（400）
    - 数据驱动（parametrize + yaml）
    - 响应结构校验（jsonschema）
    - 数据库落库校验（本项目特色）

★ 重要知识点 ★
    automationexercise 的接口，HTTP 状态码永远返回 200，
    真实业务码写在响应体的 responseCode 字段里。
    所以断言必须用 biz_code() 取业务码，而不是 resp.status_code。

    这在面试里是个很好的话题：
    「不能只看 HTTP 200 就认为接口没问题，要看业务返回码和数据内容。」
"""

import allure
import pytest

from sites.automationexercise import DATA

from common.assertions import (assert_equal, assert_true, assert_in,
                               assert_less_than, SoftAssert)
from common.data_reader import load_cases
from common import db_helper


@allure.epic("接口自动化")
@allure.feature("商品模块")
class TestProductApi:

    # -----------------------------------------------------------
    # 正向用例
    # -----------------------------------------------------------
    @allure.story("获取商品列表")
    @allure.title("API01 - GET 获取全部商品列表应返回200且数据非空")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_get_all_products(self, product_api):
        resp = product_api.get_all_products()
        body = product_api.json_of(resp)

        sa = SoftAssert()
        sa.status_code(resp.status_code, 200, "HTTP状态码")
        sa.equal(product_api.biz_code(resp), 200, "业务响应码")
        sa.true("products" in body, "响应包含 products 字段")
        sa.true(len(body.get("products", [])) > 0, "商品列表非空")
        sa.less_than(resp.elapsed_ms, 5000, "接口响应时间")
        sa.assert_all()

        # 数据内容抽查：第一个商品必须有完整字段
        first = body["products"][0]
        for field in ("id", "name", "price", "brand", "category"):
            assert_in(field, first, "商品对象应包含字段 %s" % field)

    @allure.story("获取品牌列表")
    @allure.title("API03 - GET 获取全部品牌列表")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_get_all_brands(self, product_api):
        resp = product_api.get_all_brands()
        body = product_api.json_of(resp)

        assert_equal(product_api.biz_code(resp), 200, "业务响应码")
        assert_true(len(body.get("brands", [])) > 0, "品牌列表应非空")

    # -----------------------------------------------------------
    # 反向用例：不支持的请求方法
    # -----------------------------------------------------------
    @allure.story("请求方法校验")
    @allure.title("API02 - POST 请求商品列表应返回405不支持")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p1
    def test_post_products_list_not_allowed(self, product_api):
        resp = product_api.post_products_list()
        assert_equal(product_api.biz_code(resp), 405, "业务响应码应为405")
        assert_in("not supported", product_api.biz_message(resp),
                  "错误提示应说明方法不支持")

    @allure.story("请求方法校验")
    @allure.title("API04 - PUT 请求品牌列表应返回405不支持")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p1
    def test_put_brands_list_not_allowed(self, product_api):
        resp = product_api.put_brands_list()
        assert_equal(product_api.biz_code(resp), 405, "业务响应码应为405")

    # -----------------------------------------------------------
    # 参数缺失用例
    # -----------------------------------------------------------
    @allure.story("参数校验")
    @allure.title("API06 - 搜索商品不传参数应返回400")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p0
    def test_search_without_param(self, product_api):
        resp = product_api.search_product_without_param()
        assert_equal(product_api.biz_code(resp), 400, "缺少必填参数应返回400")
        assert_in("search_product", product_api.biz_message(resp),
                  "错误信息应指出缺少哪个参数")

    # -----------------------------------------------------------
    # 数据驱动用例
    # -----------------------------------------------------------
    _search_cases, _search_ids = load_cases(DATA / "search_api_cases.yaml")

    @allure.story("商品搜索")
    @allure.title("API05 - 搜索商品：{case[title]}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.p1
    @pytest.mark.parametrize("case", _search_cases, ids=_search_ids)
    def test_search_product(self, product_api, case):
        """
        数据驱动示范：
            一个测试函数 + 5 条 yaml 数据 = 5 条独立用例
            加用例只需要改 yaml，不用碰代码。
        """
        allure.dynamic.description(
            "用例ID: %s\n关键词: %r\n预期业务码: %s"
            % (case["id"], case["keyword"], case["expect_code"])
        )

        resp = product_api.search_product(case["keyword"])
        body = product_api.json_of(resp)

        assert_equal(product_api.biz_code(resp), case["expect_code"], "业务响应码")

        products = body.get("products", [])
        if case["expect_has_result"]:
            assert_true(len(products) > 0,
                        "关键词 %r 应能搜到商品" % case["keyword"])
        # 注意：搜不到时该接口仍返回200和空列表，这是设计如此，不是bug

    # -----------------------------------------------------------
    # 数据库校验（本项目特色）
    # -----------------------------------------------------------
    @allure.story("数据一致性校验")
    @allure.title("DB01 - 商品数据落库后用SQL做完整性校验")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.p2
    def test_products_data_integrity_with_sql(self, product_api):
        """
        ★ 这条用例展示「接口 + 数据库」的端到端验证能力 ★

        步骤：
            1. 调接口拿到全部商品
            2. 落到本地 SQLite
            3. 用 SQL 检查数据质量问题

        检查的都是接口状态码看不出来的问题：
            - 商品名为空
            - 价格字段格式异常
            - 商品ID重复
            - 品牌字段缺失
        """
        resp = product_api.get_all_products()
        products = product_api.json_of(resp).get("products", [])
        assert_true(len(products) > 0, "前置条件：商品列表不能为空")

        total = db_helper.save_products(products)
        allure.attach("落库商品数: %d" % total, name="落库结果",
                      attachment_type=allure.attachment_type.TEXT)

        sa = SoftAssert()

        empty_name = db_helper.scalar(
            "SELECT COUNT(*) FROM products WHERE name IS NULL OR TRIM(name)=''")
        sa.equal(empty_name, 0, "不应存在商品名为空的记录")

        empty_price = db_helper.scalar(
            "SELECT COUNT(*) FROM products WHERE price IS NULL OR TRIM(price)=''")
        sa.equal(empty_price, 0, "不应存在价格为空的记录")

        bad_price = db_helper.scalar(
            "SELECT COUNT(*) FROM products WHERE price NOT LIKE 'Rs.%'")
        sa.equal(bad_price, 0, "价格格式应统一为 'Rs. xxx'")

        dup_id = db_helper.scalar(
            "SELECT COUNT(*) FROM ("
            "  SELECT id FROM products GROUP BY id HAVING COUNT(*) > 1)")
        sa.equal(dup_id, 0, "商品ID不应重复")

        empty_brand = db_helper.scalar(
            "SELECT COUNT(*) FROM products WHERE brand IS NULL OR TRIM(brand)=''")
        sa.equal(empty_brand, 0, "不应存在品牌为空的记录")

        # 把统计结果贴进报告，方便查看
        by_cat = db_helper.query(
            "SELECT category, COUNT(*) AS n FROM products"
            " GROUP BY category ORDER BY n DESC")
        allure.attach(
            "\n".join("%-20s %s" % (r["category"], r["n"]) for r in by_cat),
            name="分类商品数量统计",
            attachment_type=allure.attachment_type.TEXT)

        sa.assert_all()
