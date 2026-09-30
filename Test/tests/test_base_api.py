# -*- coding: utf-8 -*-
"""接口基类的自测。

这里全部用假的 Response，一个网络请求都不发。
被测站点的限流、封禁这些场景，真去触发既不可控也不道德，
造假数据反而能把每种分支都稳定覆盖到 —— 这就是打桩的价值。
"""

import pytest
import requests

from api import base_api as BA
from api.base_api import BaseApi


class FakeResponse:
    """够用就好的假响应：只实现被测代码真正会碰的几个成员。"""

    def __init__(self, status_code=200, text="{}", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("不是合法的 JSON")
        return self._json


@pytest.fixture
def api(make_cfg, monkeypatch):
    """一个不限速、不真的等待的 BaseApi。"""
    monkeypatch.setattr(BA.time, "sleep", lambda s: None)
    BaseApi._last_request_at = 0.0
    client = BaseApi(make_cfg({"api_url": "http://例子/api", "api_timeout": 5}),
                     min_interval=0)
    client.MAX_RETRY = 3
    return client


class TestIsBlocked:
    """识别「本该返回 JSON，实际返回了 HTML 拦截页」。"""

    def test_正常JSON对象不算被拦(self):
        assert BaseApi._is_blocked(FakeResponse(text='{"a":1}')) is False

    def test_正常JSON数组不算被拦(self):
        assert BaseApi._is_blocked(FakeResponse(text='[1,2]')) is False

    def test_前面有空白的JSON也不算被拦(self):
        assert BaseApi._is_blocked(FakeResponse(text='\n  {"a":1}')) is False

    def test_空响应不算被拦(self):
        # 空响应是另一类问题（接口没数据），不该混进限流重试里
        assert BaseApi._is_blocked(FakeResponse(text="")) is False
        assert BaseApi._is_blocked(FakeResponse(text="   ")) is False

    def test_HTML等待页判为被拦(self):
        html = '<!DOCTYPE html><html><script>window.location.reload()</script>'
        assert BaseApi._is_blocked(FakeResponse(200, html)) is True

    @pytest.mark.parametrize("code", [404, 500, 502])
    def test_非200的HTML错误页不算被拦(self, code):
        # ★ 回归用例 ★
        # 原来只看响应体是不是 HTML，不看状态码。
        # 实测 POST /cdn-cgi/rum 返回 404 + Cloudflare 的 HTML 错误页，
        # 被判成「服务端限流」退避重试 4 次，白等 15 秒，
        # 日志还打出「检测到服务端限流(HTTP 404)」这种错得离谱的结论。
        # 404/500 是真实错误，必须立刻报出来。
        html = '<!DOCTYPE html><html><body>Not Found</body></html>'
        assert BaseApi._is_blocked(FakeResponse(code, html)) is False

    def test_纯文本不算被拦(self):
        assert BaseApi._is_blocked(FakeResponse(text="服务器开小差了")) is False


class TestIsIpBanned:
    """区分「产品缺陷」和「IP 被机器人防护封了」。"""

    def test_403带Imunify360标记判为封禁(self):
        r = FakeResponse(403, "Access denied by Imunify360 bot-protection.")
        assert BaseApi.is_ip_banned(r) is True

    def test_普通403不算封禁(self):
        # 真的权限不足是产品行为，必须当失败报出来，不能被跳过
        assert BaseApi.is_ip_banned(FakeResponse(403, '{"message":"无权限"}')) is False

    def test_200不算封禁(self):
        assert BaseApi.is_ip_banned(FakeResponse(200, "Imunify360")) is False

    def test_None不算封禁(self):
        assert BaseApi.is_ip_banned(None) is False

    def test_标记出现在很靠后的位置就不认(self):
        # 只看前 500 字符，避免把正常页面里偶然出现的词误判成封禁
        assert BaseApi.is_ip_banned(FakeResponse(403, "x" * 600 + "Imunify360")) is False


class TestResponseParsing:

    def test_解析合法JSON(self):
        assert BaseApi.json_of(FakeResponse(json_data={"a": 1})) == {"a": 1}

    def test_解析失败返回空字典而不是抛异常(self):
        assert BaseApi.json_of(FakeResponse(text="<html>")) == {}

    def test_业务码优先取responseCode(self):
        # 这个站点不管成功失败 HTTP 都是 200，真结果在 body 里
        r = FakeResponse(200, json_data={"responseCode": 404})
        assert BaseApi.biz_code(r) == 404

    def test_取不到业务码时退回HTTP状态码(self):
        assert BaseApi.biz_code(FakeResponse(500, text="<html>")) == 500

    def test_业务消息(self):
        r = FakeResponse(json_data={"message": "User created!"})
        assert BaseApi.biz_message(r) == "User created!"

    def test_没有message时返回空串(self):
        assert BaseApi.biz_message(FakeResponse(json_data={})) == ""


class TestRequestRetry:

    def _stub(self, api, responses):
        """把 session.request 换成按顺序吐预设响应。"""
        calls = []

        def fake(**kwargs):
            calls.append(kwargs)
            item = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(item, Exception):
                raise item
            return item

        api.session.request = fake
        return calls

    def test_一次成功不重试(self, api):
        calls = self._stub(api, [FakeResponse(200, '{"ok":1}')])
        resp = api.get("/x")
        assert resp.status_code == 200
        assert len(calls) == 1

    def test_拼出完整URL(self, api):
        calls = self._stub(api, [FakeResponse(200, "{}")])
        api.get("/productsList")
        assert calls[0]["url"] == "http://例子/api/productsList"

    def test_传绝对地址时不再拼接(self, api):
        calls = self._stub(api, [FakeResponse(200, "{}")])
        api.get("http://别的域名/x")
        assert calls[0]["url"] == "http://别的域名/x"

    def test_遇到403会退避重试(self, api):
        calls = self._stub(api, [FakeResponse(403, "{}")])
        api.get("/x")
        assert len(calls) == api.MAX_RETRY

    def test_遇到429会退避重试(self, api):
        calls = self._stub(api, [FakeResponse(429, "{}")])
        api.get("/x")
        assert len(calls) == api.MAX_RETRY

    def test_遇到HTML拦截页会重试(self, api):
        calls = self._stub(api, [FakeResponse(200, "<!DOCTYPE html><html>")])
        api.get("/x")
        assert len(calls) == api.MAX_RETRY

    def test_返回HTML错误页的404不重试(self, api):
        calls = self._stub(api, [FakeResponse(404, "<!DOCTYPE html><html>404</html>")])
        api.get("/x")
        assert len(calls) == 1

    def test_重试中途成功就停下(self, api):
        calls = self._stub(api, [FakeResponse(403, "{}"),
                                 FakeResponse(200, '{"ok":1}'),
                                 FakeResponse(200, '{"ok":1}')])
        assert api.get("/x").status_code == 200
        assert len(calls) == 2

    def test_404这类真实业务错误不重试(self, api):
        # 只有限流才重试。真的 404 重试三次只会浪费时间
        calls = self._stub(api, [FakeResponse(404, '{"responseCode":404}')])
        api.get("/x")
        assert len(calls) == 1

    def test_网络异常会重试(self, api):
        calls = self._stub(api, [requests.ConnectionError("连不上")])
        with pytest.raises(requests.RequestException):
            api.get("/x")
        assert len(calls) == api.MAX_RETRY

    def test_网络异常重试后成功(self, api):
        calls = self._stub(api, [requests.ConnectionError("连不上"),
                                 FakeResponse(200, '{"ok":1}')])
        assert api.get("/x").status_code == 200
        assert len(calls) == 2

    def test_响应上会挂耗时毫秒数(self, api):
        self._stub(api, [FakeResponse(200, "{}")])
        assert isinstance(api.get("/x").elapsed_ms, int)

    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
    def test_四个快捷方法传对了HTTP方法(self, api, method):
        calls = self._stub(api, [FakeResponse(200, "{}")])
        getattr(api, method.lower())("/x")
        assert calls[0]["method"] == method


class TestThrottle:

    def test_限速会等待(self, make_cfg, monkeypatch):
        slept = []
        monkeypatch.setattr(BA.time, "sleep", lambda s: slept.append(s))
        # 不去 patch time.time —— 那是全局的，会波及 pytest 自己的计时。
        # 直接把「上次请求时间」设成 0.1 秒前，效果一样且没有副作用。
        BaseApi._last_request_at = BA.time.time() - 0.1
        BaseApi(make_cfg({"api_url": "http://x", "api_timeout": 5}),
                min_interval=0.5)._throttle()
        assert slept and slept[0] == pytest.approx(0.4, abs=0.05)

    def test_min_interval为0时不等待(self, make_cfg, monkeypatch):
        slept = []
        monkeypatch.setattr(BA.time, "sleep", lambda s: slept.append(s))
        BaseApi(make_cfg({"api_url": "http://x", "api_timeout": 5}),
                min_interval=0)._throttle()
        assert slept == []

    def test_距离够久就不等待(self, make_cfg, monkeypatch):
        slept = []
        monkeypatch.setattr(BA.time, "sleep", lambda s: slept.append(s))
        BaseApi._last_request_at = 0.0        # 相当于「很久以前」
        BaseApi(make_cfg({"api_url": "http://x", "api_timeout": 5}),
                min_interval=0.5)._throttle()
        assert slept == []


def test_默认带上真实浏览器UA(make_cfg):
    # 无头浏览器和裸 requests 的默认 UA 会被反爬直接拦掉
    api = BaseApi(make_cfg({"api_url": "http://x", "api_timeout": 5}))
    assert "Chrome" in api.session.headers["User-Agent"]
