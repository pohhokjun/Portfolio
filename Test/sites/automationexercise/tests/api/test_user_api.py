# -*- coding: utf-8 -*-
"""
用户接口测试（API 7-14）

本文件演示：
    - 测试数据的自动创建与清理（fixture yield）
    - 完整的数据生命周期测试：注册 -> 查询 -> 登录 -> 更新 -> 删除
    - 数据驱动的反向用例
    - 用例之间的依赖处理
"""

import allure
import pytest

from sites.automationexercise import DATA

from common.assertions import assert_equal, assert_true, assert_in, SoftAssert
from common.data_reader import load_cases
from common.faker_util import random_user


@allure.epic("接口自动化")
@allure.feature("用户模块")
class TestUserApi:

    # -----------------------------------------------------------
    # 正向用例
    # -----------------------------------------------------------
    @allure.story("登录校验")
    @allure.title("API07 - 正确的账号密码应校验通过")
    @allure.severity(allure.severity_level.BLOCKER)
    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.p0
    def test_verify_login_success(self, user_api, temp_user):
        """temp_user 这个 fixture 会自动注册账号，用完自动删除。"""
        resp = user_api.verify_login(temp_user["email"], temp_user["password"])

        assert_equal(user_api.biz_code(resp), 200, "业务响应码")
        assert_in("User exists", user_api.biz_message(resp), "登录成功提示")

    @allure.story("用户查询")
    @allure.title("API14 - 按邮箱查询用户详情")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.p1
    def test_get_user_detail(self, user_api, temp_user):
        resp = user_api.get_user_by_email(temp_user["email"])
        body = user_api.json_of(resp)

        sa = SoftAssert()
        sa.equal(user_api.biz_code(resp), 200, "业务响应码")
        sa.true("user" in body, "响应应包含 user 对象")

        user = body.get("user", {})
        sa.equal(user.get("email"), temp_user["email"], "邮箱应与注册时一致")
        sa.equal(user.get("name"), temp_user["name"], "用户名应与注册时一致")
        sa.assert_all()

    # -----------------------------------------------------------
    # 反向用例：数据驱动
    # -----------------------------------------------------------
    _login_cases, _login_ids = load_cases(DATA / "api_login_cases.yaml")

    @allure.story("登录校验-异常场景")
    @allure.title("{case[title]}")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p1
    @pytest.mark.parametrize("case", _login_cases, ids=_login_ids)
    def test_verify_login_negative(self, user_api, case):
        """
        反向用例数据驱动。
        yaml 里 email/password 为 null 表示该参数完全不传，
        用于验证接口的必填参数校验。
        """
        allure.dynamic.description(
            "用例ID: %s\n设计方法: %s\n预期业务码: %s"
            % (case["id"], case.get("method", ""), case["expect_code"])
        )

        resp = user_api.verify_login(case["email"], case["password"])

        sa = SoftAssert()
        sa.equal(user_api.biz_code(resp), case["expect_code"], "业务响应码")
        if case.get("expect_message"):
            sa.contains(user_api.biz_message(resp),
                        case["expect_message"][:30], "错误提示文案")
        sa.assert_all()

    @allure.story("请求方法校验")
    @allure.title("API09 - DELETE 请求登录接口应返回405")
    @allure.severity(allure.severity_level.NORMAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p2
    def test_delete_verify_login_not_allowed(self, user_api):
        resp = user_api.delete_verify_login()
        assert_equal(user_api.biz_code(resp), 405, "业务响应码应为405")

    # -----------------------------------------------------------
    # 完整生命周期：注册 -> 登录 -> 更新 -> 删除
    # -----------------------------------------------------------
    @allure.story("用户生命周期")
    @allure.title("E2E - 账号完整生命周期：注册→登录→更新→删除")
    @allure.severity(allure.severity_level.BLOCKER)
    @allure.description(
        "这是一条端到端接口用例，串联了 4 个接口。\n"
        "用例设计方法：场景法（业务流程法）\n"
        "价值：单个接口都通过，不代表流程能走通。"
    )
    @pytest.mark.api
    @pytest.mark.p0
    def test_user_lifecycle(self, user_api):
        user = random_user()
        sa = SoftAssert()

        # ---- 步骤1：注册 ----
        with allure.step("步骤1：注册新账号"):
            resp = user_api.create_account(user)
            sa.equal(user_api.biz_code(resp), 201, "注册应返回201")
            sa.contains(user_api.biz_message(resp), "User created", "注册成功提示")

        # ---- 步骤2：用新账号登录 ----
        with allure.step("步骤2：用新账号登录"):
            resp = user_api.verify_login(user["email"], user["password"])
            sa.equal(user_api.biz_code(resp), 200, "登录应返回200")

        # ---- 步骤3：更新账号信息 ----
        with allure.step("步骤3：更新账号信息"):
            user["firstname"] = "Updated"
            user["city"] = "UpdatedCity"
            resp = user_api.update_account(user)
            sa.equal(user_api.biz_code(resp), 200, "更新应返回200")

        # ---- 步骤4：验证更新生效 ----
        with allure.step("步骤4：查询验证更新是否生效"):
            resp = user_api.get_user_by_email(user["email"])
            detail = user_api.json_of(resp).get("user", {})
            sa.equal(detail.get("first_name"), "Updated", "名字应已更新")

        # ---- 步骤5：删除账号 ----
        with allure.step("步骤5：删除账号"):
            resp = user_api.delete_account(user["email"], user["password"])
            sa.equal(user_api.biz_code(resp), 200, "删除应返回200")

        # ---- 步骤6：验证删除后无法登录 ----
        with allure.step("步骤6：验证删除后账号不可用"):
            resp = user_api.verify_login(user["email"], user["password"])
            sa.equal(user_api.biz_code(resp), 404, "已删除账号登录应返回404")

        sa.assert_all()

    @allure.story("注册")
    @allure.title("API11 - 重复邮箱注册应被拒绝")
    @allure.severity(allure.severity_level.CRITICAL)
    @pytest.mark.api
    @pytest.mark.negative
    @pytest.mark.p1
    def test_create_duplicate_account(self, user_api, temp_user):
        """
        边界场景：用已存在的邮箱再注册一次。
        设计方法：等价类划分-无效等价类（唯一性约束）
        """
        duplicate = random_user()
        duplicate["email"] = temp_user["email"]     # 换成已存在的邮箱

        resp = user_api.create_account(duplicate)
        code = user_api.biz_code(resp)
        msg = user_api.biz_message(resp)

        allure.attach("业务码: %s\n提示: %s" % (code, msg),
                      name="重复注册的响应",
                      attachment_type=allure.attachment_type.TEXT)

        assert_true(code != 201,
                    "重复邮箱不应注册成功，实际返回 %s: %s" % (code, msg))
