# -*- coding: utf-8 -*-
"""
酒店预订接口（restful-booker）

★ 为什么专门加这个被测系统 ★

    主被测站 AutomationExercise 的 14 个接口**一个都不带鉴权**，
    在它身上写不出「拿 token → 带 token 访问 → 无 token 被拒」这条链路。
    而鉴权恰恰是接口测试最常被问、线上也最容易出事的一块：
    越权访问、token 泄露、过期不失效，都是真实事故。

    restful-booker 是 Mark Winteringham 专门给接口测试练手做的，
    有完整的 token 流程，还故意留了几个不合理的行为让人找。

★ 这个 API 的两个坑（都写成了用例）★

    1. POST /auth 密码错了也返回 HTTP 200，
       只是 body 从 {"token": "..."} 变成 {"reason": "Bad credentials"}。
       只断言 status_code == 200 会把认证失败当成功放过去。
    2. DELETE 成功返回 201 Created。
       删除返回「已创建」是语义错误，REST 规范该给 200 或 204。

鉴权方式（两种都支持，各写了一条用例）：
    Cookie: token=<token>
    Authorization: Basic base64(admin:password123)
"""

import allure

from api.base_api import BaseApi

# 官方公开的演示账号，不是密钥泄露
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "password123"
# base64("admin:password123")
BASIC_AUTH = "Basic YWRtaW46cGFzc3dvcmQxMjM="


class BookingApi(BaseApi):

    # ★ 关掉退避重试 ★
    # BaseApi 把 403 当成服务端限流，会退避重试 4 次。
    # 但在这个 API 里 403 是**预期的鉴权失败响应**，不是限流 ——
    # 重试既救不回来，还会让每条反向用例白等十几秒。
    # 「什么该重试、什么不该重试」必须按接口语义定，不能一刀切。
    MAX_RETRY = 1

    # -----------------------------------------------------------
    # 鉴权
    # -----------------------------------------------------------
    @allure.step("接口：获取 token")
    def create_token(self, username=DEFAULT_USER, password=DEFAULT_PASSWORD):
        return self.post("/auth", json_body={"username": username,
                                             "password": password})

    def token_of(self, resp):
        """从响应里取 token，取不到返回 None（认证失败时就是 None）。"""
        return self.json_of(resp).get("token")

    def get_token(self):
        """直接拿一个可用 token，前置步骤用。"""
        return self.token_of(self.create_token())

    @staticmethod
    def auth_headers(token=None, basic=False):
        """
        拼鉴权头。
            token=None 且 basic=False -> 不带任何凭证（反向用例用）
        """
        headers = {"Accept": "application/json"}
        if basic:
            headers["Authorization"] = BASIC_AUTH
        elif token:
            headers["Cookie"] = "token=%s" % token
        return headers

    # -----------------------------------------------------------
    # 预订（读操作免鉴权，写操作要鉴权）
    # -----------------------------------------------------------
    @allure.step("接口：健康检查")
    def ping(self):
        return self.get("/ping")

    @allure.step("接口：查预订 id={booking_id}")
    def get_booking(self, booking_id):
        return self.get("/booking/%s" % booking_id,
                        headers={"Accept": "application/json"})

    @allure.step("接口：查全部预订 id")
    def list_bookings(self):
        return self.get("/booking", headers={"Accept": "application/json"})

    @allure.step("接口：创建预订")
    def create_booking(self, payload):
        return self.post("/booking", json_body=payload,
                         headers={"Accept": "application/json"})

    @allure.step("接口：整体更新预订 id={booking_id}")
    def update_booking(self, booking_id, payload, token=None, basic=False):
        return self.put("/booking/%s" % booking_id, json_body=payload,
                        headers=self.auth_headers(token, basic))

    @allure.step("接口：部分更新预订 id={booking_id}")
    def patch_booking(self, booking_id, payload, token=None, basic=False):
        return self.request("PATCH", "/booking/%s" % booking_id,
                            json_body=payload,
                            headers=self.auth_headers(token, basic))

    @allure.step("接口：删除预订 id={booking_id}")
    def delete_booking(self, booking_id, token=None, basic=False):
        return self.delete("/booking/%s" % booking_id,
                           headers=self.auth_headers(token, basic))
