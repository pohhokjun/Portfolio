# -*- coding: utf-8 -*-
"""
接口契约测试（JSON Schema）

★ 这一层补的是什么洞 ★

    原来的接口用例断言的是「这次返回的数据对不对」：
        responseCode == 200
        products 不为空
        某个商品的价格大于 0

    这些断言有个共同问题 —— 它们只检查**你想到要检查的那几个点**。
    后端把 price 从 "Rs. 500" 改成 500（去掉了字符串包装），
    上面三条断言全都照样通过，但前端会直接崩。

    契约校验反过来做：把整个响应结构按一份**事先约定的规格**逐字段验，
    任何字段的类型、格式、取值范围出了约定，立刻报出来是哪条数据的哪个字段。

★ 契约放在本站的 data/schemas/*.json ★

    JSON Schema 是跨语言标准，这份文件前后端测试三方共用，
    可以直接贴进接口文档。写死在 Python 里就只有测试能看了。

★ 和 tests/visual/ 里那两条结构回归的区别 ★

    visual 那两条是「和上次比变了没」（回归）。
    这里是「符不符合约定」（契约）。
    上次要是就错的，回归发现不了；契约能。
"""

import allure
import pytest

from common import contract
from common.assertions import assert_equal

# 抽样条数。商品列表有几百条，全量校验又慢又刷屏；
# 结构问题基本都是整批一致的，抽 20 条足够暴露。
SAMPLE = 20


def _attach(name, payload, violations):
    allure.attach(
        "契约: %s\n违约 %d 处\n\n%s"
        % (name, len(violations),
           "\n".join("  %s\n    %s" % (v["path"], v["message"])
                     for v in violations[:30]) or "  （全部符合）"),
        name="契约校验_%s" % name,
        attachment_type=allure.attachment_type.TEXT)


@allure.epic("接口自动化")
@allure.feature("接口契约（JSON Schema）")
class TestApiContract:

    @allure.story("商品列表")
    @allure.title("CONTRACT_001 - 商品列表响应应符合契约")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "逐字段校验：\n"
        "  id       整数且 ≥ 1\n"
        "  name     非空字符串\n"
        "  price    必须形如 'Rs. 500'（后端一旦改成纯数字，前端会崩）\n"
        "  brand    非空字符串\n"
        "  category 必须带 category 和 usertype，usertype 只能是 Women/Men/Kids"
    )
    @pytest.mark.api
    @pytest.mark.p0
    def test_products_list_contract(self, product_api):
        body = product_api.json_of(product_api.get_all_products())
        violations = contract.find_violations(
            contract._truncate(body, SAMPLE),
            contract.load_schema("products_list"))
        _attach("products_list", body, violations)
        contract.validate(body, "products_list", sample_limit=SAMPLE)

    @allure.story("品牌列表")
    @allure.title("CONTRACT_002 - 品牌列表响应应符合契约")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_brands_list_contract(self, product_api):
        body = product_api.json_of(product_api.get_all_brands())
        violations = contract.find_violations(
            contract._truncate(body, SAMPLE),
            contract.load_schema("brands_list"))
        _attach("brands_list", body, violations)
        contract.validate(body, "brands_list", sample_limit=SAMPLE)

    @allure.story("商品搜索")
    @allure.title("CONTRACT_003 - 搜索结果应符合契约")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_search_contract(self, product_api):
        body = product_api.json_of(product_api.search_product("top"))
        violations = contract.find_violations(
            contract._truncate(body, SAMPLE),
            contract.load_schema("search_product"))
        _attach("search_product", body, violations)
        contract.validate(body, "search_product", sample_limit=SAMPLE)

    @allure.story("搜索边界")
    @allure.title("CONTRACT_004 - 搜不到结果时结构仍应完整")
    @allure.severity(allure.severity_level.NORMAL)
    @allure.description(
        "空结果是最容易出结构问题的地方：\n"
        "很多后端在没数据时直接不返回 products 字段，或者返回 null 而不是 []。\n"
        "前端拿到 undefined 去 .map() 就是白屏。"
    )
    @pytest.mark.api
    @pytest.mark.p1
    @pytest.mark.negative
    def test_empty_search_contract(self, product_api):
        body = product_api.json_of(
            product_api.search_product("绝对搜不到的关键词zzzxxx"))
        allure.attach(str(body)[:600], name="空结果响应体",
                      attachment_type=allure.attachment_type.TEXT)

        assert "products" in body, (
            "搜不到结果时也必须返回 products 字段（空数组），"
            "不能直接省略 —— 前端会拿到 undefined")
        assert isinstance(body["products"], list), (
            "products 必须是数组，实际是 %s。返回 null 前端一样会崩"
            % type(body["products"]).__name__)
        contract.validate(body, "search_product")
