# -*- coding: utf-8 -*-
"""
本站所有页面的基类：框架的 BasePage + 这个站特有的东西（广告按钮、登录标识）。

为什么不直接写进 pages/base_page.py：
    「右上角显示 Logged in as」是这个站的长相，换个站就不成立。
    框架层只放对任何网站都对的操作，站点知识留在站点目录里。
"""

from pages.base_page import BasePage
from sites.automationexercise.pages.locators.common_loc import CommonLoc


class SitePage(BasePage):
    AD_CLOSE = tuple(CommonLoc.AD_CLOSE.split(", "))

    def is_logged_in(self):
        return self.is_visible(CommonLoc.LOGGED_IN_AS, timeout=3000)

    def logged_in_name(self):
        return self.get_text(CommonLoc.LOGGED_IN_AS).replace("Logged in as", "").strip()

    def logout(self):
        if self.is_logged_in():
            self.click(CommonLoc.NAV_LOGOUT, "退出登录")
        return self
