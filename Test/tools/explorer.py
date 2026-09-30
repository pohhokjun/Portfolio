# -*- coding: utf-8 -*-
"""
站点自动探索（爬虫）

【来源】从原 17_测试/explorer/web_explorer.py 迁移，改用新的配置体系。

★ 这是本项目最稀有的能力 ★

    99% 的自动化作品集都是「人写用例、机器执行」。
    这个模块反过来：让机器自己找出该测什么。

    做法：
        广度优先遍历站点，每个页面记录
        标题、状态码、加载耗时、所有链接、所有表单、所有接口调用、控制台报错

    产出：一份站点地图 JSON，交给 case_generator 生成巡检用例。

    面试话术：
        「手工维护用例的成本很高，页面一多就跟不上。
          我做了一个探索器，广度优先爬站，自动采集页面结构和接口调用，
          再自动生成巡检用例。这样新增页面不用人工加用例，
          适合做全站可用性的日常巡检。
          它不能替代功能测试 —— 业务规则还是要人来设计。」

安全设计：
    有 danger_keywords 黑名单，绝不点击 delete / logout / 提现 这类链接。
    这一点很重要，爬虫在生产环境乱点会出事故。
"""

import time
from collections import deque
from urllib.parse import urlparse

from config.settings import get_config, load_rules
from common.logger import get_logger
from tools import js_snippets as js
from tools.sitemap import Sitemap, Node, normalize, same_site

log = get_logger("explorer")


class SiteExplorer:
    def __init__(self, cfg=None, rules=None):
        self.cfg = cfg or get_config()
        self.rules = rules if rules is not None else load_rules("explore_rules")

        conf = self.cfg.get("explore", {}) or {}
        self.max_pages = int(conf.get("max_pages", 30))
        self.max_depth = int(conf.get("max_depth", 2))
        self.max_links = int(conf.get("max_links_per_page", 100))
        self.max_apis = int(conf.get("max_apis_per_page", 30))
        self.strip_query = bool(conf.get("strip_query", False))
        self.delay = float(conf.get("delay", 0.8))
        self.start_urls = conf.get("start_urls") or []

        self.include = self.rules.get("include_patterns", []) or []
        self.exclude = self.rules.get("exclude_patterns", []) or []
        self.danger = self.rules.get("danger_keywords", []) or []

    # -----------------------------------------------------------
    def _allowed(self, url, root):
        """判断这个 URL 能不能爬。安全第一。"""
        if not same_site(url, root):
            return False
        if any(p in url for p in self.exclude):
            return False
        # 危险操作绝不触碰
        if any(k in url.lower() for k in self.danger):
            return False
        if self.include and not any(p in url for p in self.include):
            return False
        path = urlparse(url).path
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in {"pdf", "zip", "rar", "xlsx", "png", "jpg", "jpeg",
                   "gif", "svg", "mp4", "exe", "css", "js"}:
            return False
        return True

    # -----------------------------------------------------------
    def explore(self, start_urls=None, progress=None):
        """
        执行探索。需要 playwright 已安装。

        参数：
            progress  回调函数 (done, total, text)，用于显示进度
        """
        from playwright.sync_api import sync_playwright

        roots = start_urls or self.start_urls or [self.cfg.base_url]
        root = roots[0]
        sm = Sitemap(root_url=root, env=self.cfg.tag)

        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.cfg.headless)
            ctx = browser.new_context(
                viewport={"width": int(self.cfg.get("viewport.width", 1440)),
                          "height": int(self.cfg.get("viewport.height", 900))},
                ignore_https_errors=True, user_agent=ua)
            ctx.set_default_timeout(self.cfg.timeout)
            ctx.set_default_navigation_timeout(self.cfg.nav_timeout)
            page = ctx.new_page()

            console_errors, requests_seen = [], []

            def on_console(msg):
                if msg.type == "error":
                    console_errors.append(msg.text[:200])

            def on_request(req):
                # 只记本站的接口。
                #
                # ★ 这里踩过一个很值钱的坑 ★
                #   不加这个判断，页面上的 Google 广告、统计脚本发的请求
                #   会被一并当成「本站接口」采集进来。实测 126 条接口里
                #   有 125 条是 doubleclick / googlesyndication 之类的广告域名，
                #   真正属于被测系统的只有 1 条。
                #
                #   后果比「浪费时间」严重得多：巡检报告里 99% 的结论
                #   说的是 Google 的服务器好不好，和被测系统没有半点关系。
                #   而且这些域名随时会返回 302/403，报告天天飘红，
                #   看的人很快就不看了 —— 一份没人信的报告等于没有。
                if (req.resource_type in ("xhr", "fetch")
                        and same_site(req.url, root)):
                    requests_seen.append({"method": req.method, "url": req.url})

            page.on("console", on_console)
            page.on("request", on_request)

            queue = deque((normalize(u, strip_query=self.strip_query), 0, "start")
                          for u in roots)
            visited = set()

            while queue and len(visited) < self.max_pages:
                url, depth, src = queue.popleft()
                if url in visited or depth > self.max_depth:
                    continue
                visited.add(url)

                if progress:
                    progress(len(visited),
                             min(self.max_pages, len(visited) + len(queue)),
                             url[:60])
                log.info("[%d/%d] 探索 %s", len(visited), self.max_pages, url)

                console_errors.clear()
                requests_seen.clear()
                node = Node(url=url, depth=depth, source=src)

                try:
                    resp = page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)

                    node.status = resp.status if resp else None
                    node.title = page.title()
                    timing = page.evaluate(js.PERF_TIMING) or {}
                    node.load_ms = timing.get("load_ms")
                    node.forms = page.evaluate(js.COLLECT_FORMS) or []
                    node.console_errors = list(console_errors)[:10]
                    node.apis = [{"method": r["method"], "url": r["url"],
                                  "page": url}
                                 for r in requests_seen[:self.max_apis]]

                    links = page.evaluate(js.COLLECT_LINKS) or []
                    node.links = links[:self.max_links]

                    for l in node.links:
                        nxt = normalize(l.get("href", ""), base=url,
                                        strip_query=self.strip_query)
                        if nxt and nxt not in visited and self._allowed(nxt, root):
                            queue.append((nxt, depth + 1, url))

                except Exception as exc:
                    node.error = str(exc)[:200]
                    log.warning("探索失败 %s: %s", url, exc)

                sm.add(node)
                if self.delay:
                    time.sleep(self.delay)

            browser.close()

        log.info("探索完成：页面 %d，表单 %d，接口 %d",
                 len(sm.nodes), len(sm.all_forms()), len(sm.all_apis()))
        return sm
