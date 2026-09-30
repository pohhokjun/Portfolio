# -*- coding: utf-8 -*-
"""
站点地图数据结构

【来源】从原 17_测试/core/sitemap.py 迁移。

站点地图 = 爬虫探索出来的网站结构，包含每个页面的：
    URL、标题、状态码、加载耗时、链接、表单、接口调用、控制台报错
"""

import json
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag

from config.settings import ROOT


def normalize(url, base=None, strip_query=False):
    """URL 归一化，避免同一页面被当成多个。"""
    if not url:
        return ""
    url = url.strip()
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)          # 去掉 #锚点
    if strip_query and "?" in url:
        url = url.split("?", 1)[0]
    if url.endswith("/") and len(urlparse(url).path) > 1:
        url = url[:-1]
    return url


def same_site(url, root):
    try:
        return urlparse(url).netloc == urlparse(root).netloc
    except Exception:
        return False


class Node:
    """一个页面节点。"""

    def __init__(self, url, title="", depth=0, source=""):
        self.url = url
        self.title = title
        self.depth = depth
        self.source = source          # 从哪个页面跳过来的
        self.status = None
        self.load_ms = None
        self.links = []
        self.forms = []
        self.apis = []                # 页面加载时调用的 XHR/fetch 接口
        self.console_errors = []
        self.error = ""

    def to_dict(self):
        return {"url": self.url, "title": self.title, "depth": self.depth,
                "source": self.source, "status": self.status,
                "load_ms": self.load_ms, "links": self.links,
                "forms": self.forms, "apis": self.apis,
                "console_errors": self.console_errors, "error": self.error}

    @staticmethod
    def from_dict(d):
        n = Node(d.get("url", ""), d.get("title", ""),
                 d.get("depth", 0), d.get("source", ""))
        n.status = d.get("status")
        n.load_ms = d.get("load_ms")
        n.links = d.get("links", [])
        n.forms = d.get("forms", [])
        n.apis = d.get("apis", [])
        n.console_errors = d.get("console_errors", [])
        n.error = d.get("error", "")
        return n


class Sitemap:
    def __init__(self, root_url="", env=""):
        self.root_url = root_url
        self.env = env
        self.created = time.strftime("%Y-%m-%d %H:%M:%S")
        self.nodes = {}

    def add(self, node):
        self.nodes[node.url] = node
        return node

    def all_apis(self):
        """
        去重后的全部接口。

        每条要带上「是在哪个页面发现的」——
        巡检用例失败时，光有接口 URL 没法复现，得知道从哪进去才会触发。
        """
        seen = {}
        for n in self.nodes.values():
            for a in n.apis:
                key = "%s %s" % (a.get("method", "GET"), a.get("url", ""))
                if key not in seen:
                    item = dict(a)
                    item.setdefault("page", n.url)
                    seen[key] = item
        return list(seen.values())

    def all_forms(self):
        out = []
        for n in self.nodes.values():
            for f in n.forms:
                item = dict(f)
                item["page"] = n.url
                out.append(item)
        return out

    def to_dict(self):
        return {"root_url": self.root_url, "env": self.env,
                "created": self.created, "count": len(self.nodes),
                "nodes": [n.to_dict() for n in self.nodes.values()]}

    def save(self, path=None):
        path = Path(path or default_path(self.env))
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return str(path)

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        sm = Sitemap(d.get("root_url", ""), d.get("env", ""))
        sm.created = d.get("created", "")
        for nd in d.get("nodes", []):
            sm.add(Node.from_dict(nd))
        return sm

    def tree_text(self, max_nodes=100):
        lines = []
        for i, n in enumerate(sorted(self.nodes.values(),
                                     key=lambda x: (x.depth, x.url))):
            if i >= max_nodes:
                lines.append("... 其余 %d 个页面省略" % (len(self.nodes) - max_nodes))
                break
            lines.append("%s- %s  [%s] %s"
                         % ("  " * n.depth, n.title or "(无标题)",
                            n.status or "-", n.url))
        return "\n".join(lines)


def default_path(env="test"):
    return ROOT / "reports" / "sitemaps" / ("sitemap_%s.json" % env)
