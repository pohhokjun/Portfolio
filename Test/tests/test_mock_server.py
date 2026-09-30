# -*- coding: utf-8 -*-
"""
Mock 服务的自测。

★ 为什么假服务也要写测试 ★

    mock 一旦和真接口的行为对不上，危害比没有 mock 更大：
    用例在 mock 上一片绿，上了真环境全红，还得反过来查是谁的问题。

    所以这里做两件事：
        1. 拿真接口的契约（sites/<站>/data/schemas/*.json）去校验 mock 的返回 ——
           契约是同一份，mock 骗不了它
        2. 把「真站点的怪脾气」逐条钉住：HTTP 永远 200、业务码在 body 里、
           注册传 firstname 查询回 first_name、空关键词返回 200 而不是 400

    走的是 127.0.0.1，不联网，所以归在框架自测里，几百毫秒跑完。
"""

import json
import urllib.request
import urllib.parse

import pytest

from common import contract
from sites.automationexercise.mock import Routes
from tools.mock_server import MockServer


@pytest.fixture(scope="module")
def mock_url():
    with MockServer(Routes) as server:
        yield server.url


def call(url, path, method="GET", data=None):
    """不走 requests，直接用标准库 —— 自测不该依赖被测对象的上游。"""
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url + path, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8")


def body_of(url, path, method="GET", data=None):
    return json.loads(call(url, path, method, data)[1])


class TestContractCompliance:
    """mock 的返回必须过真接口的契约。"""

    @pytest.mark.parametrize("path,schema", [
        ("/productsList", "products_list"),
        ("/brandsList", "brands_list"),
    ])
    def test_列表接口符合契约(self, mock_url, path, schema):
        assert contract.validate(body_of(mock_url, path), schema) == []

    def test_搜索结果符合契约(self, mock_url):
        body = body_of(mock_url, "/searchProduct", "POST",
                       {"search_product": "top"})
        assert contract.validate(body, "search_product") == []
        assert len(body["products"]) > 0

    def test_搜不到时结构仍完整(self, mock_url):
        body = body_of(mock_url, "/searchProduct", "POST",
                       {"search_product": "zzzznotexist"})
        assert contract.validate(body, "search_product") == []
        assert body["products"] == []

    def test_价格格式和真站点一致(self, mock_url):
        # 落库校验里有 "price NOT LIKE 'Rs.%'" 这条 SQL，
        # mock 要是写成 "500 Rs"，那条用例就会在 mock 上假失败
        for p in body_of(mock_url, "/productsList")["products"]:
            assert p["price"].startswith("Rs. ")


class TestSiteQuirks:
    """把真站点的约定钉死，别让 mock 自作主张改行为。"""

    def test_HTTP永远200业务码在body里(self, mock_url):
        status, raw = call(mock_url, "/productsList", "POST")
        assert status == 200
        assert json.loads(raw)["responseCode"] == 405

    @pytest.mark.parametrize("path,method", [
        ("/productsList", "POST"),
        ("/brandsList", "PUT"),
        ("/verifyLogin", "DELETE"),
    ])
    def test_不支持的方法返回405(self, mock_url, path, method):
        body = body_of(mock_url, path, method)
        assert body["responseCode"] == 405
        assert "not supported" in body["message"]

    def test_搜索缺参数返回400且指出字段名(self, mock_url):
        body = body_of(mock_url, "/searchProduct", "POST")
        assert body["responseCode"] == 400
        assert "search_product" in body["message"]

    def test_搜索空字符串返回200不是400(self, mock_url):
        # 传了参数只是值为空，和「没传参数」是两回事。
        # 表单解析默认会把空值丢掉，这里正是防那个坑的回归用例。
        body = body_of(mock_url, "/searchProduct", "POST",
                       {"search_product": ""})
        assert body["responseCode"] == 200
        assert body["products"] == []

    def test_登录缺参数返回400(self, mock_url):
        assert body_of(mock_url, "/verifyLogin", "POST",
                       {"email": "a@b.com"})["responseCode"] == 400


class TestUserLifecycle:
    """注册→登录→更新→删除，和 E2E 用例走的是同一条链路。"""

    def _user(self, email="qa_auto_mock@example.com"):
        return {"name": "mock_user", "email": email, "password": "Test@12345",
                "firstname": "Origin", "lastname": "Tester", "city": "Shenzhen"}

    def test_完整生命周期(self, mock_url):
        user = self._user("qa_auto_life@example.com")

        assert body_of(mock_url, "/createAccount", "POST",
                       user)["responseCode"] == 201
        assert body_of(mock_url, "/verifyLogin", "POST",
                       user)["responseCode"] == 200

        user["firstname"] = "Updated"
        assert body_of(mock_url, "/updateAccount", "PUT",
                       user)["responseCode"] == 200

        detail = body_of(mock_url, "/getUserDetailByEmail?email=%s"
                         % user["email"])
        # 注册字段叫 firstname，查询返回叫 first_name —— 真站点就这么别扭
        assert detail["user"]["first_name"] == "Updated"

        assert body_of(mock_url, "/deleteAccount", "DELETE",
                       user)["responseCode"] == 200
        assert body_of(mock_url, "/verifyLogin", "POST",
                       user)["responseCode"] == 404

    def test_重复邮箱注册被拒(self, mock_url):
        user = self._user("qa_auto_dup@example.com")
        assert body_of(mock_url, "/createAccount", "POST",
                       user)["responseCode"] == 201
        again = body_of(mock_url, "/createAccount", "POST", user)
        assert again["responseCode"] != 201
        assert "already exist" in again["message"]

    def test_密码不对不算登录成功(self, mock_url):
        user = self._user("qa_auto_pwd@example.com")
        call(mock_url, "/createAccount", "POST", user)
        wrong = dict(user, password="nope")
        assert body_of(mock_url, "/verifyLogin", "POST",
                       wrong)["responseCode"] == 404

    def test_查不存在的用户返回404(self, mock_url):
        assert body_of(mock_url, "/getUserDetailByEmail?email=ghost@x.com"
                       )["responseCode"] == 404


class TestFaultRoutes:
    """故障注入路由本身也要能用，不然故障用例测的是个寂寞。"""

    def test_指定状态码(self, mock_url):
        assert call(mock_url, "/_fault/status?code=503")[0] == 503

    def test_畸形JSON确实解析不了(self, mock_url):
        raw = call(mock_url, "/_fault/badjson")[1]
        with pytest.raises(ValueError):
            json.loads(raw)

    def test_拦截页是HTML不是JSON(self, mock_url):
        raw = call(mock_url, "/_fault/blocked")[1]
        assert raw.startswith("<!DOCTYPE html")
        assert "reload" in raw

    def test_限流N次后恢复(self, mock_url):
        call(mock_url, "/_fault/reset", "POST")
        assert call(mock_url, "/_fault/flaky?fail=2&key=t")[0] == 429
        assert call(mock_url, "/_fault/flaky?fail=2&key=t")[0] == 429
        status, raw = call(mock_url, "/_fault/flaky?fail=2&key=t")
        assert status == 200
        assert json.loads(raw)["attempts"] == 3

    def test_reset能把计数清零(self, mock_url):
        call(mock_url, "/_fault/flaky?fail=1&key=r")
        call(mock_url, "/_fault/reset", "POST")
        assert call(mock_url, "/_fault/flaky?fail=1&key=r")[0] == 429

    def test_未知故障名不会把服务打挂(self, mock_url):
        assert body_of(mock_url, "/_fault/nothing")["responseCode"] == 404
        assert body_of(mock_url, "/productsList")["responseCode"] == 200
