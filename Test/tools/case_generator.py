# -*- coding: utf-8 -*-
"""
用例自动生成

【来源】从原 17_测试/core/case_gen.py 迁移。

把探索出来的站点地图，转换成 pytest 可以直接执行的巡检用例数据（yaml）。

生成三类用例：
    smoke   每个页面能否打开、状态码、有无错误文案、有无控制台报错
    link    页面内链接可达性
    api     探测到的接口可用性

★ 和 portfolio 手写用例的区别 ★

    手写用例：验证业务规则（金额算得对不对、流程走不走得通）
    生成用例：验证基础可用性（页面开不开、链接断没断、接口通不通）

    前者需要人的业务理解，后者纯粹是覆盖广度。
    两者互补，都留在这个项目里。
"""

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import yaml

from config.settings import get_config, load_rules

# None = 当前站点的 data/。框架自测会把它指到临时目录
DATA_DIR = None
from tools.sitemap import same_site
from common.logger import get_logger

log = get_logger("case_gen")


def _cid(prefix, *parts):
    h = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]
    return "%s_%s" % (prefix, h)


def _short(url):
    p = urlparse(url)
    path = (p.path or "/").strip("/") or "首页"
    return path.replace("/", "_")[:40]


class CaseGenerator:
    def __init__(self, cfg=None, rules=None):
        self.cfg = cfg or get_config()
        self.rules = rules if rules is not None else load_rules("explore_rules")
        self.skip_patterns = self.rules.get("skip_url_patterns", []) or []
        self.forbidden = self.rules.get("forbidden_text", []) or []
        self.max_per_kind = int(self.cfg.get("case_gen.max_per_kind", 200))

    def _skip(self, url):
        return any(p in url for p in self.skip_patterns)

    # -----------------------------------------------------------
    def generate(self, sitemap):
        cases = {
            "smoke": self.gen_smoke(sitemap),
            "link": self.gen_link(sitemap),
            "api": self.gen_api(sitemap),
        }
        total = sum(len(v) for v in cases.values())
        log.info("共生成巡检用例 %d 条 (smoke=%d, link=%d, api=%d)",
                 total, len(cases["smoke"]), len(cases["link"]), len(cases["api"]))
        return cases

    def gen_smoke(self, sitemap):
        out = []
        for node in sitemap.nodes.values():
            if self._skip(node.url) or node.error:
                continue
            out.append({
                "id": _cid("smoke", node.url),
                "title": "页面可访问 - %s" % (node.title or _short(node.url)),
                "url": node.url,
                "expect_status": [200],
                "forbidden_text": self.forbidden,
                "check_console": True,
            })
            if len(out) >= self.max_per_kind:
                break
        return out

    def gen_link(self, sitemap):
        out = []
        for node in sitemap.nodes.values():
            if self._skip(node.url) or not node.links:
                continue
            hrefs = [l.get("href") for l in node.links[:30] if l.get("href")]
            if not hrefs:
                continue
            out.append({
                "id": _cid("link", node.url),
                "title": "链接可用性 - %s" % (node.title or _short(node.url)),
                "page": node.url,
                "links": hrefs,
            })
            if len(out) >= self.max_per_kind:
                break
        return out

    def gen_api(self, sitemap):
        """
        只对本站接口生成用例。

        第三方域名（广告、统计、地图）的请求也会被浏览器发出来，
        但它们不属于被测系统。把它们做成用例，报告就变成了
        「Google 的服务器今天好不好」，既没意义又必然偶发失败。
        探索阶段已经滤过一次，这里再挡一道，
        免得早先爬的旧站点地图把脏数据带进来。
        """
        root = sitemap.root_url or self.cfg.base_url
        out = []
        for api in sitemap.all_apis():
            url = api.get("url", "")
            if not url or self._skip(url) or not same_site(url, root):
                continue
            out.append({
                "id": _cid("api", api.get("method", "GET"), url),
                "title": "接口可用 - %s %s" % (api.get("method", "GET"), _short(url)),
                "method": api.get("method", "GET"),
                "url": url,
                "from_page": api.get("page", ""),
                "expect_status": [200, 201, 204],
                "max_ms": 5000,
            })
            if len(out) >= self.max_per_kind:
                break
        return out

    # -----------------------------------------------------------
    def save(self, cases, filename="crawl_cases.yaml"):
        """
        写入本站的 data/ 目录，供 testcases/crawl/ 下的用例读取。

        ★ 关键设计：保留人工修改 ★
            重新生成时，如果某条用例已存在，保留人工改过的 enabled 字段。
            否则每次重新爬站，人工关掉的用例又会被打开。
        """
        path = Path(DATA_DIR or self.cfg.data_dir) / filename

        existing = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old = yaml.safe_load(f) or {}
                for kind, items in (old.get("cases", {}) or {}).items():
                    for item in items:
                        existing[item.get("id")] = item
            except Exception:
                pass

        added, kept = 0, 0
        for kind, items in cases.items():
            for item in items:
                cid = item["id"]
                if cid in existing:
                    # 保留人工设置的 enabled
                    item["enabled"] = existing[cid].get("enabled", True)
                    kept += 1
                else:
                    item.setdefault("enabled", True)
                    added += 1

        payload = {
            "generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "base_url": self.cfg.base_url,
            "cases": cases,
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True,
                           sort_keys=False, width=200)

        log.info("巡检用例已写入 %s（新增 %d，保留 %d）", path, added, kept)
        return {"path": str(path), "added": added, "kept": kept}
