# -*- coding: utf-8 -*-
"""
接口请求基类

设计说明（面试必讲）：
    所有接口请求都走这一层，好处：
        1. 统一超时、重试、请求头
        2. 统一日志：每个请求的 URL/参数/响应/耗时都记录
        3. 统一把请求和响应贴到 Allure 报告里 —— 提 bug 时直接有证据
        4. 将来要换 requests 为 httpx，只改这一个文件

    这就是「封装」的意义：变化点收敛到一处。

★★★ 本项目实战踩坑记录（面试可直接讲这个故事）★★★

    现象：单独跑接口用例全部通过，批量跑就有一半失败。
    排查：打日志发现失败时响应体不是 JSON，而是一段 HTML，
          内容是「5秒后自动刷新」的等待页。
    结论：被测站点有反爬限流，请求过密时返回拦截页而非真实数据。
    处理：
        1. 识别限流页（响应不是 JSON 且包含刷新脚本）
        2. 自动退避重试，间隔递增
        3. 请求之间加最小间隔，主动降低频率

    价值：这正是「用例不稳定（Flaky Test）」的典型案例。
          面试问「你遇到过用例时好时坏怎么办」，
          答：先看是环境问题还是用例问题，用日志定位，
              本项目就是通过响应体日志发现是服务端限流，
              最终用重试 + 限速解决，而不是简单地加 sleep。
"""

import json
import time

import allure
import requests

from config.settings import get_config
from common.logger import get_logger

log = get_logger("api")

# 限流拦截页的特征：返回的是 HTML 且带自动刷新脚本
_BLOCK_MARKERS = ("window.location.reload", "<!DOCTYPE html", "<html")

# IP 被机器人防护封禁的特征
_IP_BAN_MARKERS = ("Imunify360", "bot-protection", "Access denied")


class SiteBlockedError(RuntimeError):
    """被测站点的机器人防护封禁了当前 IP。属于环境问题，不是产品缺陷。"""


class BaseApi:
    # 两次请求之间的最小间隔（秒），主动限速，避免触发服务端反爬
    MIN_INTERVAL = 0.35
    # 遇到限流时的重试次数与退避基数
    MAX_RETRY = 4
    BACKOFF = 1.6

    _last_request_at = 0.0      # 类变量：所有实例共享，实现全局限速

    def __init__(self, cfg=None, min_interval=None):
        self.cfg = cfg or get_config()
        self.base = self.cfg.api_url
        self.timeout = self.cfg.api_timeout
        # 性能测试需要真并发，可以传 min_interval=0 关掉主动限速
        self.min_interval = self.MIN_INTERVAL if min_interval is None else min_interval
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
        })

    # -----------------------------------------------------------
    # 核心请求方法
    # -----------------------------------------------------------
    def request(self, method, path, params=None, data=None,
                json_body=None, headers=None, **kwargs):
        url = path if path.startswith("http") else "%s%s" % (self.base, path)
        method = method.upper()

        resp = None
        elapsed = 0
        for attempt in range(1, self.MAX_RETRY + 1):
            self._throttle()

            start = time.time()
            try:
                resp = self.session.request(
                    method=method, url=url, params=params, data=data,
                    json=json_body, headers=headers,
                    timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                log.warning("第%d次请求异常 %s %s -> %s", attempt, method, url, exc)
                if attempt >= self.MAX_RETRY:
                    raise
                time.sleep(self.BACKOFF ** attempt)
                continue

            elapsed = round((time.time() - start) * 1000)
            BaseApi._last_request_at = time.time()

            # 403/429 是服务端限流，同样需要退避重试
            if not self._is_blocked(resp) and resp.status_code not in (403, 429):
                break

            wait = round(self.BACKOFF ** attempt, 1)
            log.warning("检测到服务端限流(HTTP %s)，%.1fs 后重试 (%d/%d) %s %s",
                        resp.status_code, wait, attempt, self.MAX_RETRY, method, url)
            time.sleep(wait)

        log.info("%s %s -> %s (%dms)", method, url, resp.status_code, elapsed)
        self._attach_to_allure(method, url, params, data, json_body, resp, elapsed)

        resp.elapsed_ms = elapsed
        return resp

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    # -----------------------------------------------------------
    # 限流处理
    # -----------------------------------------------------------
    def _throttle(self):
        """主动限速：保证两次请求之间至少间隔 min_interval 秒。"""
        if not self.min_interval:
            return
        gap = time.time() - BaseApi._last_request_at
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)

    @staticmethod
    def is_ip_banned(resp):
        """
        判断是否被站点的机器人防护封禁 IP。

        ★ 实战记录（面试可讲的重要一课）★
            本项目连续跑了几百次请求后，站点返回：
              403 {"message": "Access denied by Imunify360 bot-protection.
                               IPs used for automation should be whitelisted"}

            这是环境问题，不是被测系统的缺陷。
            如果框架把它当成用例失败，会产生大量假失败，
            让人误以为系统坏了 —— 这在真实项目里会造成严重的信任危机。

            正确做法：识别出来，把用例标记为「跳过」而不是「失败」，
            并明确提示原因和解决办法。
            这就是「区分环境失败与产品失败」，是资深测试的基本素养。

            真实项目中的解法：让运维把自动化机器的 IP 加入白名单。
        """
        if resp is None or resp.status_code != 403:
            return False
        text = (resp.text or "")[:500]
        return any(m in text for m in _IP_BAN_MARKERS)

    @staticmethod
    def _is_blocked(resp):
        """
        判断是否被限流拦截。

        特征：HTTP 200，但接口本该返回 JSON，实际返回了 HTML 等待页。
        这里不能只看状态码 —— 拦截页也是 200。

        ★ 但也不能不看状态码，这里踩过坑 ★
            原来的写法只认「响应体是 HTML」，不管状态码。
            结果任何返回 HTML 错误页的 4xx/5xx 都被当成限流：
            实测一个 POST /cdn-cgi/rum 返回 404 + Cloudflare 的 HTML 错误页，
            框架判定为「服务端限流」，退避重试了 4 次，白等 15 秒，
            日志里还写着「检测到服务端限流(HTTP 404)」—— 结论完全是错的。

            404、500 是真实的接口错误，要立刻报出来让人去查，
            重试只会把问题拖慢并掩盖掉。限流页的特征是「200 + HTML」，
            必须两个条件同时成立。
        """
        if resp.status_code != 200:
            return False
        text = (resp.text or "")[:400]
        if not text.strip():
            return False
        if text.lstrip().startswith(("{", "[")):
            return False
        return any(m in text for m in _BLOCK_MARKERS)

    # -----------------------------------------------------------
    # 响应解析
    # -----------------------------------------------------------
    @staticmethod
    def json_of(resp):
        """
        安全地解析 JSON。

        ★ 重要知识点 ★
        automationexercise 的接口不管成功失败，HTTP 状态码都返回 200，
        真实的业务码写在响应体的 responseCode 字段里。

        面试话术：接口测试不能只看 HTTP 状态码。
        很多系统统一返回 200，把业务结果放在 body 的 code 字段里，
        断言必须打到业务码和数据内容层面。
        """
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def biz_code(resp):
        """取业务响应码。取不到时退回 HTTP 状态码。"""
        body = BaseApi.json_of(resp)
        return body.get("responseCode", resp.status_code)

    @staticmethod
    def biz_message(resp):
        body = BaseApi.json_of(resp)
        return body.get("message", "")

    @staticmethod
    def _attach_to_allure(method, url, params, data, json_body, resp, elapsed):
        """把请求响应全文贴进 Allure 报告，失败时不用重现就能定位。"""
        try:
            req_info = {"method": method, "url": url, "params": params,
                        "form_data": data, "json_body": json_body}
            allure.attach(json.dumps(req_info, ensure_ascii=False, indent=2),
                          name="请求信息",
                          attachment_type=allure.attachment_type.JSON)
            allure.attach(resp.text[:5000],
                          name="响应内容 (HTTP %s, %dms)" % (resp.status_code, elapsed),
                          attachment_type=allure.attachment_type.TEXT)
        except Exception:
            pass
