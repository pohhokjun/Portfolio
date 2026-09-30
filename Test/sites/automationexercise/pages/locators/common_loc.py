# -*- coding: utf-8 -*-
"""
全站通用元素

为什么定位器要单独放一个文件夹：
    页面改版时，元素定位是最容易变的部分，页面「行为」反而稳定。
    分开之后，改版只需要动 locators/，pages/ 里的业务逻辑一行不用改。

    面试话术：这是 POM 的进阶用法，叫「定位器与操作分离」。
"""


class CommonLoc:
    # 顶部导航
    NAV_HOME = 'a[href="/"]'
    NAV_PRODUCTS = 'a[href="/products"]'
    NAV_CART = 'a[href="/view_cart"]'
    NAV_LOGIN = 'a[href="/login"]'
    NAV_LOGOUT = 'a[href="/logout"]'
    NAV_DELETE_ACCOUNT = 'a[href="/delete_account"]'

    # 登录状态标识
    LOGGED_IN_AS = 'a:has-text("Logged in as")'

    # 广告相关（该站有 Google 广告，会遮挡点击）
    AD_IFRAME = 'iframe[id^="google_ads"]'
    AD_CLOSE = '#dismiss-button, .close-button, #close-fixedban'
