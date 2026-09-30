# -*- coding: utf-8 -*-
"""
站点适配器 —— 让质量属性测试不绑死在某一个被测系统上

★ 这个模式是从 14_浏览器/sites.py 借来的，值得单独说一下 ★

    那边的做法是：引擎只认 W3C 标准，框架专属的东西（Element UI 的
    .el-dialog、.v-modal 遮罩、私有的 .private-button）全部收进适配器。
    加一个新网站 = 复制一份配置改几行，引擎一行不用动。

    这里把同样的思路用在质量属性测试上。原因很实际：
    可访问性、响应式、性能、容错这四类检查的**逻辑**和被测系统无关 ——
    「页面不许横向溢出」对任何网站都成立。
    但**验收点**是系统专属的：主导航的选择器、商品卡片长什么样、
    要不要先登录。把这两者分开，一套用例就能对着任意站点跑。

    面试可以讲：这是「测试逻辑」和「站点知识」的分离，
    和 POM 把「操作」与「定位器」分开是同一个道理，只是上升了一层。

★ 为什么需要多个被测系统 ★

    AutomationExercise 有 Imunify360 机器人防护，跑密了会封 IP。
    封了之后**整套 UI 用例都跑不了** —— 演示、面试、CI 全部卡住。
    只依赖一个第三方站点，是自动化项目最脆弱的一环。

    SauceDemo 是 Sauce Labs 官方给自动化练手用的，不封 IP，
    而且内置了几个「故意有缺陷」的账号，正好用来验证
    我们的检查到底抓不抓得住问题 —— 这比全部通过有说服力得多。
"""

import yaml

from config.settings import SITES_DIR, list_sites

# ---------------------------------------------------------------
# 通用兜底：只用 W3C 标准的东西，任何网站都成立
# ---------------------------------------------------------------
PROFILE_DEFAULT = {
    "name": "通用",
    "domains": [],
    "login": None,
    "pages": [("首页", "/")],
    "nav": {},
    "product_card": "",
    "product_name": "",
    "product_price": "",
    "product_image": "img",
    "add_to_cart": "",
    "added_marker": "",       # 加购成功的标志（按钮变 Remove / 弹出「已加入」框）
    "cart_link": "",          # 去购物车的入口
    "cart_url": "",           # 购物车页地址（glob）
    "cart_item": "",
    # 第三方域名：挂了也不该影响主功能，容错用例会把它们全部阻断
    "third_party": [],
}


# ---------------------------------------------------------------
# 各站点的适配器写在 sites/<站>/site.yaml 的 profile 段
#   选择器是数据不是代码：加一个站点只写 yaml，这个文件一行不用动。
#   字段含义见上面的 PROFILE_DEFAULT；已知缺陷登记表的写法见 sites/saucedemo/site.yaml。
# ---------------------------------------------------------------
def _load():
    out = []
    for name in list_sites():
        raw = yaml.safe_load((SITES_DIR / name / "site.yaml").read_text(encoding="utf-8")) or {}
        if raw.get("profile"):
            out.append({**PROFILE_DEFAULT, **raw["profile"], "name": raw.get("name", name)})
    return out


PROFILES = _load()


def pick_profile(url):
    """按被测地址挑适配器。命中不了就用通用兜底。"""
    url = url or ""
    for p in PROFILES:
        for d in p["domains"]:
            if d and d in url:
                return p
    return PROFILE_DEFAULT


def profile_for(cfg):
    """从配置对象取适配器。用例层统一走这个入口：站点配了 profile 用它，没配按地址找。"""
    if cfg.get("profile"):
        return {**PROFILE_DEFAULT, **cfg.get("profile"), "name": cfg.get("name", cfg.site)}
    return pick_profile(cfg.base_url)
