# -*- coding: utf-8 -*-
"""商品列表页"""

import allure

from common.logger import get_logger
from sites.automationexercise.pages.site_page import SitePage
from sites.automationexercise.pages.locators.products_loc import ProductsLoc

log = get_logger("page.products")


class ProductsPage(SitePage):
    PATH = "/products"

    @allure.step("验证商品页已加载")
    def is_loaded(self):
        return self.is_visible(ProductsLoc.ALL_PRODUCTS_TITLE)

    @allure.step("搜索商品: {keyword}")
    def search(self, keyword):
        self.fill(ProductsLoc.SEARCH_INPUT, keyword, "搜索框")
        self.click(ProductsLoc.SEARCH_BUTTON, "搜索按钮")
        self.page.wait_for_timeout(1000)      # 等结果渲染
        return self

    def is_search_result_shown(self):
        return self.is_visible(ProductsLoc.SEARCHED_TITLE, timeout=8000)

    def product_count(self):
        return self.count(ProductsLoc.PRODUCT_CARDS)

    def product_names(self):
        return self.get_all_texts(ProductsLoc.PRODUCT_NAMES)

    @allure.step("把第 {index} 个商品加入购物车")
    def add_to_cart(self, index=1):
        """index 从 1 开始，符合业务人员的习惯。"""
        buttons = self.page.locator(ProductsLoc.ADD_TO_CART_ALL)
        total = buttons.count()
        if index < 1 or index > total:
            raise IndexError("商品序号 %d 超出范围，当前页共 %d 个可加购商品"
                             % (index, total))
        loc = buttons.nth(index - 1)

        # ★ 偶发失败排查记录，这一段是本项目最典型的一个稳定性问题 ★
        #
        #   现象：连着加购两个商品，第二个大概三次里挂一次，
        #         报「等 #cartModal 可见超时 30 秒」。
        #   排查：把按钮坐标和「该坐标上最顶层的元素」打出来，
        #         发现第二个按钮滚动后停在 y≈866，而 viewport 高 900 ——
        #         正好被站点底部那条固定广告条盖住。
        #   为什么原来的写法救不了：
        #         scroll_into_view_if_needed 只做「最小滚动」，
        #         元素刚露出下边缘就停，正好停在固定广告条底下；
        #         而 click(force=True) 会跳过所有可点性检查，
        #         照样往那个坐标点下去 —— 点到的是广告，不是按钮。
        #         force 看着像是「更稳」，实际是把问题藏起来了。
        #   现在的做法：
        #         1) 滚到视口正中，固定的页头页脚都盖不到
        #         2) 用普通 click，Playwright 会自动等遮挡物让开
        #         3) 真等不到（广告赖着不走）才退回派发 DOM 事件
        loc.evaluate("el => el.scrollIntoView({block: 'center', inline: 'center'})")
        self.dismiss_ads()
        try:
            loc.click(timeout=10000)
        except Exception:
            log.warning("按钮被遮挡，改用派发事件的方式加购第 %d 个商品", index)
            loc.dispatch_event("click")
        self.wait_for(ProductsLoc.CART_MODAL)
        return self

    @allure.step("进入购物车页")
    def go_cart(self):
        """
        从商品页直接跳购物车。

        注意别用 products_page.open('/view_cart')：
        open() 返回的是 self，也就是 ProductsPage，
        拿到手的对象上根本没有 item_count() 这些购物车方法。
        页面对象之间的跳转必须显式返回目标页对象。
        """
        from sites.automationexercise.pages.cart_page import CartPage
        return CartPage(self.page, self.cfg).open()

    @allure.step("弹窗中点击继续购物")
    def continue_shopping(self):
        """
        关掉加购成功的弹窗。

        ★ 这里原来是 wait_for_timeout(600)，是一条偶发失败的根源 ★
            Bootstrap 的 modal 关闭有淡出动画，遮罩 .modal-backdrop 消失得更晚。
            600 毫秒大多数时候够，网络一卡就不够 ——
            上一个弹窗还没关完就点下一个「加入购物车」，
            Bootstrap 会直接忽略这次 show，弹窗再也不出现，
            用例卡在等弹窗上超时 30 秒才失败，报错信息还完全指错了地方。

            正确做法：等一个明确的条件（弹窗和遮罩都消失），
            好了就走，最多等到超时。固定 sleep 既慢又不可靠。
        """
        self.click(ProductsLoc.MODAL_CONTINUE, "继续购物")
        self.page.locator(ProductsLoc.CART_MODAL).first.wait_for(
            state="hidden", timeout=self.cfg.timeout)
        self.page.wait_for_function(
            "() => !document.querySelector('.modal-backdrop')",
            timeout=self.cfg.timeout)
        return self

    @allure.step("弹窗中点击查看购物车")
    def view_cart(self):
        from sites.automationexercise.pages.cart_page import CartPage
        self.click(ProductsLoc.MODAL_VIEW_CART, "查看购物车")
        return CartPage(self.page, self.cfg)
