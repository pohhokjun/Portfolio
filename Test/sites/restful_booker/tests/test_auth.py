# -*- coding: utf-8 -*-
"""
接口鉴权链路测试（restful-booker）

★ 这组用例补的是接口测试最核心的一块：鉴权 ★

    主被测站的 14 个接口全部裸奔，写不出鉴权用例。
    但真实项目里，接口测试的重头戏就是：
        1. 凭证怎么换 token
        2. 带 token 能不能干活
        3. 不带 / 带错 / 带别人的 token，会不会被拦住

    第 3 条是重点。功能测试关心「能不能用」，
    鉴权测试关心「不该能用的时候，是不是真的用不了」——
    越权访问是线上事故里最常见也最贵的一类。

用例设计方法：
    正向     AUTH_001 / 003 / 008
    反向     AUTH_002 / 004 / 005
    参数校验 AUTH_006
    场景法   AUTH_009（拿token→建→改→删→验证删干净）
"""

import allure
import pytest

from sites.restful_booker.api.booking_api import BookingApi, DEFAULT_USER, DEFAULT_PASSWORD
from common import contract
from common.assertions import assert_equal, assert_true, assert_in, SoftAssert
from common.logger import get_logger

log = get_logger("testcases.auth")


# ===============================================================
# fixture
# ===============================================================
@pytest.fixture(scope="module")
def booking_api(cfg):
    return BookingApi(cfg)


@pytest.fixture(scope="module")
def token(booking_api):
    """整组用例共用一个 token。真实项目里 token 也是复用的，不会每次都换。"""
    tk = booking_api.get_token()
    assert_true(tk, "前置条件：必须能拿到 token，否则整组用例没法跑")
    return tk


def _payload(first="QA", last="Auto", price=111):
    return {
        "firstname": first,
        "lastname": last,
        "totalprice": price,
        "depositpaid": True,
        "bookingdates": {"checkin": "2026-01-01", "checkout": "2026-01-05"},
        "additionalneeds": "Breakfast",
    }


@pytest.fixture
def booking(booking_api, token):
    """
    临时预订：建 → 用例使用 → 自动删。

    和 temp_user 一个套路 —— 用例自己造数据、自己收尾。
    不这么做的话，跑几十轮就在人家演示站上堆几百条垃圾数据。
    """
    resp = booking_api.create_booking(_payload())
    bid = booking_api.json_of(resp).get("bookingid")
    assert_true(bid, "前置条件：预订应创建成功")
    log.info("已创建预订: %s", bid)

    yield bid

    try:
        booking_api.delete_booking(bid, token=token)
        log.info("已清理预订: %s", bid)
    except Exception as exc:
        log.warning("清理预订失败 %s: %s", bid, exc)


# ===============================================================
# 用例
# ===============================================================
@allure.epic("接口自动化")
@allure.feature("鉴权与权限")
class TestAuth:

    # -----------------------------------------------------------
    # 换 token
    # -----------------------------------------------------------
    @allure.story("获取凭证")
    @allure.title("AUTH_001 - 正确账密应能换到 token")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_create_token_success(self, booking_api):
        resp = booking_api.create_token()
        tk = booking_api.token_of(resp)

        sa = SoftAssert()
        sa.status_code(resp.status_code, 200, "HTTP状态码")
        sa.true(bool(tk), "响应里应有 token")
        sa.true(len(tk or "") >= 10, "token 长度应合理，实际: %r" % tk)
        sa.assert_all()

    @allure.story("获取凭证")
    @allure.title("AUTH_002 - 错误密码不应换到 token")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "★ 这条用例专治「只看状态码」★\n"
        "这个接口密码错了**照样返回 HTTP 200**，\n"
        "只是 body 从 {\"token\":...} 变成 {\"reason\":\"Bad credentials\"}。\n"
        "只断言 status_code == 200 的话，认证失败会被当成功放过去。\n"
        "所以断言必须打在业务字段上，不能停在 HTTP 层。")
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p0
    def test_wrong_password_gets_no_token(self, booking_api):
        resp = booking_api.create_token(DEFAULT_USER, "definitely_wrong_pwd")
        body = booking_api.json_of(resp)

        sa = SoftAssert()
        sa.status_code(resp.status_code, 200, "HTTP状态码（这个接口失败也给200）")
        sa.true("token" not in body, "认证失败时不该下发 token")
        sa.contains(body.get("reason", ""), "Bad credentials", "失败原因")
        sa.assert_all()

    @allure.story("获取凭证")
    @allure.title("AUTH_003 - 不存在的用户名不应换到 token")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p1
    def test_unknown_user_gets_no_token(self, booking_api):
        resp = booking_api.create_token("nobody_qa_2026", DEFAULT_PASSWORD)
        body = booking_api.json_of(resp)

        assert_true("token" not in body, "未知用户不该下发 token")
        # 提示文案不该区分「用户不存在」和「密码错误」——
        # 区分了就等于给攻击者一个枚举有效用户名的口子
        assert_in("Bad credentials", body.get("reason", ""),
                  "提示应与密码错误一致，不泄露用户是否存在")

    # -----------------------------------------------------------
    # 带 token 干活
    # -----------------------------------------------------------
    @allure.story("持凭证访问")
    @allure.title("AUTH_004 - 带 token 应能整体更新预订")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_update_with_token(self, booking_api, booking, token):
        new = _payload("Updated", "ByToken", 999)
        resp = booking_api.update_booking(booking, new, token=token)
        body = booking_api.json_of(resp)

        sa = SoftAssert()
        sa.status_code(resp.status_code, 200, "HTTP状态码")
        sa.equal(body.get("firstname"), "Updated", "名字应已更新")
        sa.equal(body.get("totalprice"), 999, "金额应已更新")
        sa.assert_all()

        # 光看更新接口的回显不够，得再查一次确认真落库了 ——
        # 「接口返回成功」和「数据真的改了」是两回事
        check = booking_api.json_of(booking_api.get_booking(booking))
        assert_equal(check.get("firstname"), "Updated", "重新查询应看到新值")

    @allure.story("持凭证访问")
    @allure.title("AUTH_005 - Basic Auth 也应能更新（第二种鉴权方式）")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_update_with_basic_auth(self, booking_api, booking):
        resp = booking_api.update_booking(
            booking, _payload("Basic", "Auth", 555), basic=True)

        assert_equal(resp.status_code, 200, "Basic Auth 应同样被接受")
        assert_equal(booking_api.json_of(resp).get("firstname"), "Basic",
                     "更新应生效")

    @allure.story("持凭证访问")
    @allure.title("AUTH_006 - 带 token 应能部分更新（PATCH）")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_patch_with_token(self, booking_api, booking, token):
        resp = booking_api.patch_booking(
            booking, {"firstname": "Patched"}, token=token)
        body = booking_api.json_of(resp)

        sa = SoftAssert()
        sa.status_code(resp.status_code, 200, "HTTP状态码")
        sa.equal(body.get("firstname"), "Patched", "改的字段应变")
        # PATCH 的语义是「只改我传的」，没传的字段必须原样保留。
        # 很多实现会把没传的字段清空，这是 PATCH 最常见的缺陷。
        sa.equal(body.get("lastname"), "Auto", "没传的字段不该被清掉")
        sa.assert_all()

    # -----------------------------------------------------------
    # 不该能用的时候，必须用不了
    # -----------------------------------------------------------
    @allure.story("越权拦截")
    @allure.title("AUTH_007 - 不带任何凭证不应能修改")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p0
    def test_update_without_token_rejected(self, booking_api, booking):
        resp = booking_api.update_booking(booking, _payload("Hacker", "NoAuth"))

        assert_equal(resp.status_code, 403, "无凭证修改应被拒绝")

        # 只看到 403 还不够 —— 必须确认数据真没被改动。
        # 见过接口返回 403、后台却已经写进去的实现，
        # 光断言状态码是抓不住的。
        check = booking_api.json_of(booking_api.get_booking(booking))
        assert_true(check.get("firstname") != "Hacker",
                    "被拒绝后数据不能有任何变化")

    @allure.story("越权拦截")
    @allure.title("AUTH_008 - 伪造的 token 不应能修改")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p0
    def test_update_with_forged_token_rejected(self, booking_api, booking):
        resp = booking_api.update_booking(
            booking, _payload("Hacker", "Forged"), token="deadbeef12345")

        assert_equal(resp.status_code, 403, "伪造 token 应被拒绝")

        check = booking_api.json_of(booking_api.get_booking(booking))
        assert_true(check.get("lastname") != "Forged", "数据不能被改动")

    @allure.story("越权拦截")
    @allure.title("AUTH_009 - 不带凭证不应能删除")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p0
    def test_delete_without_token_rejected(self, booking_api, booking):
        resp = booking_api.delete_booking(booking)

        assert_equal(resp.status_code, 403, "无凭证删除应被拒绝")

        # 确认没被删掉：删除类越权比修改类更致命，数据没了就找不回来
        check = booking_api.get_booking(booking)
        assert_equal(check.status_code, 200, "被拒绝后预订应仍然存在")

    # -----------------------------------------------------------
    # 完整链路
    # -----------------------------------------------------------
    @allure.story("鉴权全链路")
    @allure.title("E2E_AUTH - 换token→建→改→删→验证删干净")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "场景法用例，串起鉴权的完整生命周期。\n"
        "单个接口都通过，不代表串起来能走通 —— 尤其是 token 这种有状态的东西。\n\n"
        "★ 顺带记一个该 API 的缺陷 ★\n"
        "  DELETE 成功返回 201 Created。删除返回「已创建」是语义错误，\n"
        "  REST 规范应给 200 或 204。用例照实断言 201，\n"
        "  同时在 学习教程.html 缺陷管理一节留档 —— \n"
        "  「按现状写断言」和「记录它不合理」不冲突，两件事都要做。")
    @pytest.mark.api
    @pytest.mark.p0
    def test_auth_lifecycle(self, booking_api):
        sa = SoftAssert()

        with allure.step("步骤1：用账密换 token"):
            tk = booking_api.get_token()
            sa.true(bool(tk), "应拿到 token")

        with allure.step("步骤2：创建预订"):
            resp = booking_api.create_booking(_payload("Life", "Cycle", 300))
            bid = booking_api.json_of(resp).get("bookingid")
            sa.true(bool(bid), "应返回预订号")

        with allure.step("步骤3：带 token 修改"):
            resp = booking_api.update_booking(
                bid, _payload("Life", "Updated", 400), token=tk)
            sa.equal(resp.status_code, 200, "带 token 修改应成功")

        with allure.step("步骤4：确认修改真的落库"):
            body = booking_api.json_of(booking_api.get_booking(bid))
            sa.equal(body.get("lastname"), "Updated", "查询应看到新值")

        with allure.step("步骤5：带 token 删除"):
            resp = booking_api.delete_booking(bid, token=tk)
            # 照现状断言 201，不合理之处已在缺陷报告留档
            sa.equal(resp.status_code, 201, "带 token 删除应成功（该API返回201）")

        with allure.step("步骤6：确认真的删掉了"):
            sa.equal(booking_api.get_booking(bid).status_code, 404,
                     "已删除的预订应查不到")

        sa.assert_all()

    # -----------------------------------------------------------
    # 契约
    # -----------------------------------------------------------
    @allure.story("接口契约")
    @allure.title("AUTH_CONTRACT - 预订详情应符合契约")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_booking_contract(self, booking_api, booking):
        body = booking_api.json_of(booking_api.get_booking(booking))
        contract.validate(body, "booking")
