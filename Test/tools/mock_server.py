# -*- coding: utf-8 -*-
"""
本地 Mock 接口服务

★ 为什么要自己起一个假服务（面试重点）★

    在此之前，所有接口用例都吊在 automationexercise 这一个第三方站点上。
    它挂了、限流了、封了 IP，用例就全跑不了 —— 单点依赖。

    更要命的是有一整类场景，真站点根本造不出来：
        服务端 500、响应超时、返回半截 JSON、连续限流后恢复。
    这些恰恰是线上最常出问题、也最该测的分支。

    所以补一层 mock：
        1. 离线可跑     pytest -m api --mock，断网也能演示
        2. 结果可控     想要什么返回给什么，不看第三方脸色
        3. 能造故障     500/超时/畸形JSON/限流，一条命令注入

    这就是「契约先行」的做法：接口的约定固定下来（sites/<站>/data/schemas/*.json），
    mock 按约定造数据，用例按约定断言，三方对齐。
    真实工作里前端和测试都是这么在后端还没写完时就开工的。

★ 框架和站点分开 ★
    这里只有骨架：收发请求、路由分发、故障注入 —— 对哪个系统都一样。
    各站点的接口写在 sites/<名>/mock.py 的 Routes 里（方法名 _h_<路径>），
    起服务时把要的 Routes 拼进来。加一个新站点的 mock，这个文件一行不用改。

用法：
    pytest -m api --mock                        site.yaml 的 mock 指向谁就起谁
    python -m tools.mock_server automationexercise wallet   手动起服务，用 curl / Postman 探索

注意：只 mock 接口，不 mock 页面。UI 用例仍然打真站点。
"""

import importlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 限流拦截页：和真站点被反爬拦下时返回的东西同构，
# 用来验证 BaseApi 的识别与退避重试逻辑真的会被触发
_BLOCK_PAGE = ("<!DOCTYPE html><html><head><script>"
               "setTimeout(function(){window.location.reload()},5000)"
               "</script></head><body>Please wait...</body></html>")


class MockRoutes:
    """站点路由的基类。BUGS = 这个站能埋的缺陷；init_server(srv) 给服务器挂状态（不能叫 setup：会盖掉 BaseHTTPRequestHandler.setup，连接直接断）。"""
    BUGS = {}

    @staticmethod
    def init_server(srv):
        pass


def load_routes(module):
    """"sites.wallet.mock" 或站点名 "wallet" → 它的 Routes 类。"""
    return importlib.import_module(module if "." in module else "sites.%s.mock" % module).Routes


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---- 基础设施 --------------------------------------------
    def log_message(self, *_args):
        """默认会往 stderr 刷访问日志，测试输出会被淹掉。"""

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        if raw.lstrip().startswith("{"):
            try:
                return json.loads(raw)
            except ValueError:
                return {}
        # requests 的 data=dict 默认发的是表单编码。
        # keep_blank_values 必须开：搜索空字符串是一条正经用例，
        # 默认参数会把 "search_product=" 整个丢掉，变成「没传参数」，
        # 于是 mock 返回 400 而真站点返回 200 —— 假服务和真服务行为分叉。
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def _send(self, payload, status=200, ctype="application/json"):
        raw = (payload if isinstance(payload, (str, bytes))
               else json.dumps(payload)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _biz(self, code, **extra):
        """
        真站点的约定：HTTP 永远 200，业务码在 responseCode 里。
        这是个很常见的设计，接口测试必须区分「HTTP码」和「业务码」，
        只断言 status_code==200 是抓不到问题的。
        """
        body = {"responseCode": code}
        body.update(extra)
        self._send(body)

    # ---- 路由 ------------------------------------------------
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method):
        url = urlparse(self.path)
        path = url.path.rstrip("/")
        if path.startswith("/api"):
            path = path[4:] or "/"
        query = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        body = self._body() if method in ("POST", "PUT", "DELETE") else {}

        if path.startswith("/_fault"):
            return self._fault(path[7:], query)

        handler = getattr(self, "_h" + path.replace("/", "_"), None)
        if handler is None:
            return self._biz(404, message="Not found: %s" % path)
        handler(method, query, body)

    # ---- 故障注入 --------------------------------------------
    def _fault(self, what, query):
        store = self.server.fault_state

        if what == "/status":
            code = int(query.get("code", 500))
            return self._send({"responseCode": code, "message": "mock fault"},
                              status=code)

        if what == "/badjson":
            # 半截 JSON：网关截断、编码错乱时的真实形态。
            # 用例要验证的是「框架不炸」，而不是「一定能解析」。
            return self._send('{"responseCode": 200, "products": [{"id": 1,',
                              ctype="application/json")

        if what == "/blocked":
            # 每次都返回拦截页 —— 重试到耗尽为止
            return self._send(_BLOCK_PAGE, ctype="text/html")

        if what == "/flaky":
            # 前 N 次限流，之后恢复：验证退避重试真的能救回来
            fail = int(query.get("fail", 2))
            key = query.get("key", "default")
            with store["lock"]:
                store["hits"][key] = store["hits"].get(key, 0) + 1
                hit = store["hits"][key]
            if hit <= fail:
                return self._send({"message": "Too Many Requests"}, status=429)
            return self._biz(200, message="recovered", attempts=hit)

        if what == "/slow":
            time.sleep(int(query.get("ms", 2000)) / 1000.0)
            return self._biz(200, message="slow but ok")

        if what == "/reset":
            with store["lock"]:
                store["hits"].clear()
            return self._biz(200, message="reset")

        return self._biz(404, message="unknown fault: %s" % what)


class MockServer:
    """起在随机端口上的假接口服务。用 start() 拿到 api 根地址。"""

    def __init__(self, *routes, port=0, bugs=()):
        known = {k for r in routes for k in r.BUGS}
        unknown = set(bugs) - known
        if unknown:
            raise ValueError("未知的埋点缺陷: %s" % unknown)
        self.routes = routes
        self.port = port
        self.bugs = set(bugs)
        self._httpd = None
        self._thread = None

    def start(self):
        # 路由类在前、骨架在后：_route 用 getattr 找 _h_xxx，站点方法优先
        handler = type("Handler", (*self.routes, _Handler), {})
        # 端口传 0 让操作系统分配空闲端口 —— 并行执行时不会互相抢端口
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._httpd.fault_state = {"hits": {}, "lock": threading.Lock()}
        self._httpd.bugs = self.bugs
        for r in self.routes:
            r.init_server(self._httpd)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.url

    @property
    def url(self):
        return "http://127.0.0.1:%d/api" % self.port

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.stop()



if __name__ == "__main__":
    import sys
    server = MockServer(*[load_routes(s) for s in sys.argv[1:]], port=8899)
    print("Mock 接口服务已启动: %s（站点: %s）" % (server.start(), " ".join(sys.argv[1:]) or "只有故障注入"))
    print("造个故障: curl '%s/_fault/status?code=500'" % server.url)
    print("Ctrl+C 停止")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
