# -*- coding: utf-8 -*-
"""
接口契约校验模块的自测。

契约校验器写松了，后果和断言写松了一样：
接口结构已经变了，用例还是全绿。所以这一层要重点测「它抓不抓得住」。
"""

import json

import pytest
from jsonschema import Draft202012Validator

from common import contract
from common.contract import (ContractError, find_violations, list_schemas,
                             load_schema, validate)

GOOD_PRODUCT = {
    "id": 1, "name": "Blue Top", "price": "Rs. 500", "brand": "Polo",
    "category": {"category": "Tops", "usertype": {"usertype": "Women"}},
}


def payload(*products, code=200):
    return {"responseCode": code, "products": list(products) or [GOOD_PRODUCT]}


class TestSchemaFiles:
    """契约文件本身必须是合法的。写错了会让所有校验静默失效。"""

    def test_契约文件不为空(self):
        assert list_schemas(), "sites/*/data/schemas/ 下一份契约都没有"

    @pytest.mark.parametrize("name", list_schemas())
    def test_是合法JSON(self, name):
        assert isinstance(load_schema(name), dict)

    @pytest.mark.parametrize("name", list_schemas())
    def test_schema自身符合JSON_Schema规范(self, name):
        # schema 写错（比如 "type": "integar" 拼错）不会报错，
        # 只会让那条规则永远不生效 —— 必须先校验 schema 本身
        Draft202012Validator.check_schema(load_schema(name))

    @pytest.mark.parametrize("name", list_schemas())
    def test_每份契约都写了标题(self, name):
        # 契约是要给前后端一起看的，没标题没人知道它管哪个接口
        assert load_schema(name).get("title"), "%s 没有 title" % name

    def test_文件不存在时报错信息带路径(self):
        with pytest.raises(FileNotFoundError) as e:
            load_schema("根本没有这份契约")
        assert "根本没有这份契约" in str(e.value)


class TestFindViolations:

    def test_合规数据零违约(self):
        assert find_violations(payload(), load_schema("products_list")) == []

    def test_类型错了要抓到(self):
        bad = dict(GOOD_PRODUCT, id="1")          # int 写成了 string
        v = find_violations(payload(bad), load_schema("products_list"))
        assert any(x["path"] == "products.0.id" for x in v)

    def test_字段少了要抓到(self):
        bad = {k: val for k, val in GOOD_PRODUCT.items() if k != "price"}
        v = find_violations(payload(bad), load_schema("products_list"))
        assert any("price" in x["message"] for x in v)

    def test_空字符串要抓到(self):
        # 字段在、类型对，但是空的 —— 这种最容易漏
        bad = dict(GOOD_PRODUCT, name="")
        v = find_violations(payload(bad), load_schema("products_list"))
        assert any(x["path"] == "products.0.name" for x in v)

    def test_格式不对要抓到(self):
        bad = dict(GOOD_PRODUCT, price="500")     # 少了 Rs. 前缀
        v = find_violations(payload(bad), load_schema("products_list"))
        assert any(x["path"] == "products.0.price" for x in v)

    def test_枚举外的值要抓到(self):
        bad = dict(GOOD_PRODUCT,
                   category={"category": "Tops", "usertype": {"usertype": "外星人"}})
        v = find_violations(payload(bad), load_schema("products_list"))
        assert any("外星人" in x["message"] for x in v)

    def test_业务码不是200要抓到(self):
        v = find_violations(payload(code=404), load_schema("products_list"))
        assert any(x["path"] == "responseCode" for x in v)

    def test_空列表要抓到(self):
        # 接口通了但一条数据都没有，是典型的「假成功」
        v = find_violations({"responseCode": 200, "products": []},
                            load_schema("products_list"))
        assert any(x["path"] == "products" for x in v)

    def test_一次返回全部违约而不是只报第一个(self):
        # 这是这个模块存在的主要理由：一轮暴露所有问题
        bad = dict(GOOD_PRODUCT, id="1", name="", price="500")
        v = find_violations(payload(bad), load_schema("products_list"))
        paths = {x["path"] for x in v}
        assert {"products.0.id", "products.0.name", "products.0.price"} <= paths

    def test_违约路径能定位到第几条数据(self):
        # 500 条商品里第 3 条坏了，报告必须说得出「第 3 条」
        v = find_violations(payload(GOOD_PRODUCT, GOOD_PRODUCT,
                                    dict(GOOD_PRODUCT, id="x")),
                            load_schema("products_list"))
        assert any(x["path"].startswith("products.2.") for x in v)

    def test_违约按路径排序保证输出稳定(self):
        bad = dict(GOOD_PRODUCT, id="1", name="", price="500")
        a = [x["path"] for x in find_violations(payload(bad), load_schema("products_list"))]
        b = [x["path"] for x in find_violations(payload(bad), load_schema("products_list"))]
        assert a == b

    def test_根级错误路径显示为根(self):
        v = find_violations([], load_schema("products_list"))
        assert v and v[0]["path"] == "(根)"


class TestValidate:

    def test_合规就静默通过(self):
        assert validate(payload(), "products_list") == []

    def test_不合规抛ContractError(self):
        with pytest.raises(ContractError):
            validate(payload(dict(GOOD_PRODUCT, id="1")), "products_list")

    def test_ContractError是断言失败的一种(self):
        # 继承 AssertionError，pytest 才会当成「用例失败」而不是「用例出错」
        assert issubclass(ContractError, AssertionError)

    def test_报错信息要能直接拿去提bug(self):
        with pytest.raises(ContractError) as e:
            validate(payload(dict(GOOD_PRODUCT, price="500")), "products_list")
        msg = str(e.value)
        assert "products_list" in msg          # 哪个接口
        assert "products.0.price" in msg       # 哪个字段
        assert "1 处违约" in msg                # 几处

    def test_违约太多时只列前二十条(self):
        many = [dict(GOOD_PRODUCT, id="x") for _ in range(30)]
        with pytest.raises(ContractError) as e:
            validate(payload(*many), "products_list")
        assert "其余 10 条见附件" in str(e.value)

    def test_抽样校验只看前N条(self):
        # 前 2 条是好的，第 3 条坏 —— 抽样 2 条就该放过
        items = [GOOD_PRODUCT, GOOD_PRODUCT, dict(GOOD_PRODUCT, id="x")]
        assert validate(payload(*items), "products_list", sample_limit=2) == []
        with pytest.raises(ContractError):
            validate(payload(*items), "products_list")

    def test_抽样不影响非列表字段(self):
        with pytest.raises(ContractError):
            validate(payload(code=500), "products_list", sample_limit=1)


class TestBrandsAndSearch:

    def test_品牌契约(self):
        good = {"responseCode": 200, "brands": [{"id": 1, "brand": "Polo"}]}
        assert validate(good, "brands_list") == []
        with pytest.raises(ContractError):
            validate({"responseCode": 200, "brands": [{"id": 1}]}, "brands_list")

    def test_搜索允许空结果但字段必须在(self):
        # 搜不到东西是正常业务结果，不该判违约
        assert validate({"responseCode": 200, "products": []},
                        "search_product") == []
        # 但字段整个不见了就是违约
        with pytest.raises(ContractError):
            validate({"responseCode": 200}, "search_product")


def test_契约目录指向data下的schemas(sandbox):
    # 契约跟着站点走：sites/<站>/data/schemas/。sandbox 换掉的只是测试数据目录，
    # contract 在 import 时就把各站的契约目录找好了 —— 这条用例把这个行为固定下来
    assert contract.SCHEMA_DIRS
    assert all(d.name == "schemas" and d.parent.name == "data" for d in contract.SCHEMA_DIRS)
