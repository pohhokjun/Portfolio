"""浏览器工具（Playwright + 本机 Chromium，无头）。框架自带，每个业务都有。

open_page：打开网页读文字和链接，只读，不用批准。
browser_run：按步骤操作（点、填、按键、截图、取文字），可能提交表单，所以算高风险、要批准。
业务配置 浏览器域名 限定能去哪些站（后缀匹配），空 = 不限。截图存工作区。
每次调用开一个新浏览器、用完关，不留登录态；要登录态的业务自己在 工具.py 里接已登录的浏览器（CDP）。
"""
import time
from urllib.parse import urlparse

import 环境
from 核心 import 业务
from 核心.工具 import 工具, 退回


def _查域名(url: str):
    if not url.startswith(("http://", "https://")):
        raise 退回("网址要以 http:// 或 https:// 开头")
    允许 = 业务.配置()["浏览器域名"]
    主机 = urlparse(url).hostname or ""
    if 允许 and not any(主机 == d or 主机.endswith("." + d) for d in 允许):
        raise 退回(f"{主机} 不在允许的域名里：{允许}")


def _开(p):
    b = p.chromium.launch()
    return b, b.new_page(viewport={"width": 1280, "height": 900})


@工具("open_page", "打开网页，读标题、正文文字（前 8000 字）和链接。只读。", {"url": str})
def 读网页(url: str):
    _查域名(url)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg = _开(p)
        try:
            pg.goto(url, timeout=30000, wait_until="domcontentloaded")
            pg.wait_for_timeout(800)
            链接 = pg.eval_on_selector_all("a[href]", "as => as.slice(0, 40).map(a => [a.innerText.trim().slice(0, 40), a.href])")
            return {"标题": pg.title(), "网址": pg.url, "正文": pg.inner_text("body")[:8000], "链接": 链接}
        finally:
            b.close()


@工具("browser_run", "按步骤操作网页。steps 每步 {action, target, value}：action = goto(target=网址) / click(target=选择器) / "
                    "fill(target=选择器, value=内容) / press(target=选择器, value=按键) / wait(value=毫秒) / text(target=选择器) / "
                    "screenshot(value=文件名)。会先等人批准。",
      {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
          "action": {"type": "string"}, "target": {"type": "string"}, "value": {"type": "string"}}, "required": ["action"]}}},
       "required": ["steps"]}, 高风险=True)
def 操作网页(steps: list):
    from playwright.sync_api import sync_playwright
    for s in steps:
        if s["action"] == "goto":
            _查域名(s.get("target", ""))
    结果 = []
    with sync_playwright() as p:
        b, pg = _开(p)
        try:
            for i, s in enumerate(steps, 1):
                动, 目, 值 = s["action"], s.get("target", ""), s.get("value", "")
                try:
                    if 动 == "goto":
                        pg.goto(目, timeout=30000, wait_until="domcontentloaded")
                        结果.append(f"{i}. 打开 {pg.url}")
                    elif 动 == "click":
                        pg.click(目, timeout=10000)
                        结果.append(f"{i}. 点了 {目}")
                    elif 动 == "fill":
                        pg.fill(目, 值, timeout=10000)
                        结果.append(f"{i}. 填了 {目}")
                    elif 动 == "press":
                        pg.press(目, 值, timeout=10000)
                        结果.append(f"{i}. 按了 {值}")
                    elif 动 == "wait":
                        pg.wait_for_timeout(min(int(值 or 1000), 15000))
                        结果.append(f"{i}. 等了 {值}ms")
                    elif 动 == "text":
                        结果.append(f"{i}. 文字：{pg.inner_text(目 or 'body', timeout=10000)[:4000]}")
                    elif 动 == "screenshot":
                        f = 环境.工作区 / (值 or f"截图_{time.strftime('%H%M%S')}.png")
                        pg.screenshot(path=str(f), full_page=True)
                        结果.append(f"{i}. 截图 {f}")
                    else:
                        raise 退回(f"第 {i} 步 action 不认识：{动}")
                except 退回:
                    raise
                except Exception as e:
                    结果.append(f"{i}. 失败：{type(e).__name__}: {str(e)[:200]}（后面的步骤没做）")
                    break
        finally:
            b.close()
    return "\n".join(结果)
